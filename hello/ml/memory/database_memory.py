from __future__ import annotations

import asyncio
import json
import os
import sys
from dataclasses import dataclass, field
from psycopg import AsyncClientCursor
from typing import Any, List, Optional, TypedDict, Mapping

from dotenv import load_dotenv

from hello.ml.logger import GLOBAL_LOGGER as logger

load_dotenv(".env")

from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage
from langgraph.graph import StateGraph, END, START

# SQLAlchemy (async, PostgreSQL)
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    CheckConstraint,
    Index,
    func,
    select,
    insert,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
from sqlalchemy.orm import registry

mapper_registry = registry()
metadata = mapper_registry.metadata

# ------------------------ DB Layer (PostgreSQL / async) ------------------------


def _normalize_content(content: Any) -> str:
    """Coerce message content (str/dict/list) to a safe string for storage."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for part in content:
            if isinstance(part, dict):
                if isinstance(part.get("text"), str):
                    parts.append(part["text"])
                elif isinstance(part.get("content"), str):
                    parts.append(part["content"])
                else:
                    parts.append(str(part))
            else:
                parts.append(str(part))
        return "\n".join([p for p in parts if p])
    if isinstance(content, dict):
        if isinstance(content.get("text"), str):
            return content["text"]
        if isinstance(content.get("content"), str):
            return content["content"]
        return json.dumps(content, ensure_ascii=False)
    return str(content)


# --- Table definitions (same schema, Postgres-friendly) ---
from sqlalchemy import Table

messages = Table(
    "messages",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column(
        "created_at",
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    ),
    Column("thread_id", String(255), nullable=False),
    Column("user_id", String(255)),
    Column("session_id", String(255)),
    Column("role", String(16), nullable=False),
    Column("content_text", Text, nullable=False),
    Column("content_json", JSONB),
    CheckConstraint(
        "role IN ('system','user','assistant','tool')", name="ck_messages_role"
    ),
    Index("idx_messages_thread_created", "thread_id", "id"),
)

conversations = Table(
    "conversations",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column(
        "created_at",
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    ),
    Column("session_id", String(255)),
    Column("user_id", String(255), nullable=False),
    Column("user_query", Text, nullable=False),
    # keep the spelling per your prior schema
    Column("response_from_llm", Text, nullable=False),
)


@dataclass
class DB:
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL"))
    _engine: AsyncEngine = field(init=False)

    def __post_init__(self) -> None:
        # Tuned pool; pre_ping avoids broken connections; recycle for long-lived apps.
        self._engine = create_async_engine(
            self.database_url,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
            pool_recycle=1800,
            connect_args={"cursor_factory": AsyncClientCursor},  # optional
        )

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    async def ensure_schema(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(metadata.create_all)

    # Message-level storage -------------------------------------------------

    async def append_message(
        self,
        *,
        thread_id: str,
        role: str,  # "user" | "assistant" | "system" | "tool"
        content: Any,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> int:
        text = _normalize_content(content)
        # Store structured content when it's list/dict; else leave JSONB NULL
        structured = content if isinstance(content, (dict, list)) else None

        stmt = (
            insert(messages)
            .values(
                thread_id=thread_id,
                user_id=user_id,
                session_id=session_id,
                role=role,
                content_text=text,
                content_json=structured,
            )
            .returning(messages.c.id)
        )
        async with self.engine.begin() as conn:
            res = await conn.execute(stmt)
            return int(res.scalar_one())

    async def fetch_history_messages(
        self, *, thread_id: str, limit: int
    ) -> List[Mapping[str, Any]]:
        stmt = (
            select(messages.c.role, messages.c.content_text)
            .where(messages.c.thread_id == thread_id)
            .order_by(messages.c.id.desc())
            .limit(limit)
        )
        async with self.engine.connect() as conn:
            rows = (await conn.execute(stmt)).mappings().all()
        rows.reverse()  # chronological
        return rows

    async def log_turn_pair(
        self, *, session_id: Optional[str], user_id: str, user_text: Any, ai_text: Any
    ) -> None:
        user_text_str = _normalize_content(user_text)
        ai_text_str = _normalize_content(ai_text)
        stmt = insert(conversations).values(
            session_id=session_id,
            user_id=user_id,
            user_query=user_text_str,
            response_from_llm=ai_text_str,
        )
        async with self.engine.begin() as conn:
            await conn.execute(stmt)


# ------------------------ Graph (async nodes) ------------------------
class AgentState(TypedDict, total=False):
    user_id: str
    session_id: Optional[str]
    thread_id: str
    question: str
    answer: str
    history_k: int
    reasoning_effort: str
    model_id: str
    # keep messages in state between nodes
    messages: List[BaseMessage]


def build_graph(db: DB) -> Any:
    """
    START -> prepare -> call_model -> persist -> END
    """

    def make_llm(model_id: str, effort: str):
        # pass reasoning explicitly
        return init_chat_model(
            model=model_id,  # e.g. "openai:gpt-5" or "openai:gpt-5-thinking"
            reasoning={"effort": effort},
        )

    async def _build_messages_from_db(thread_id: str, k: int) -> List[BaseMessage]:
        sys_msg = SystemMessage(
            content="You are a concise, helpful assistant. Use prior turns for context."
        )
        rows = await db.fetch_history_messages(thread_id=thread_id, limit=k)
        messages: List[BaseMessage] = [sys_msg]
        for r in rows:
            role = r["role"]
            text = r["content_text"]
            if role == "user":
                messages.append(HumanMessage(content=text))
            elif role == "assistant":
                messages.append(AIMessage(content=text))
        return messages

    async def prepare(state: AgentState) -> AgentState:
        """Load history for thread from DB, append current user message."""
        thread_id = state["thread_id"]
        k = int(state.get("history_k", 20))
        messages = await _build_messages_from_db(thread_id, k)
        messages.append(HumanMessage(content=_normalize_content(state["question"])))
        return {"messages": messages}

    async def call_model(state: AgentState) -> AgentState:
        """Call the LLM with messages; rebuild from DB if messages missing (safety)."""
        msgs = state.get("messages")
        if not msgs:
            thread_id = state["thread_id"]
            k = int(state.get("history_k", 20))
            msgs = await _build_messages_from_db(thread_id, k)
            msgs.append(HumanMessage(content=_normalize_content(state["question"])))

        llm = make_llm(
            state.get("model_id", "openai:gpt-5"),
            state.get("reasoning_effort", "medium"),
        )
        # invoke in a worker thread to avoid blocking event loop
        result = await asyncio.to_thread(llm.invoke, msgs)

        answer_text = _normalize_content(getattr(result, "content", result))
        return {"answer": answer_text}

    async def persist(state: AgentState) -> AgentState:
        """Persist BOTH the user question and AI answer as messages; also log the pair."""
        user_id = state["user_id"]
        session_id = state.get("session_id")
        thread_id = state["thread_id"]

        user_text = _normalize_content(state["question"])
        ai_text = _normalize_content(state.get("answer", ""))

        await db.append_message(
            thread_id=thread_id,
            role="user",
            content=user_text,
            user_id=user_id,
            session_id=session_id,
        )
        await db.append_message(
            thread_id=thread_id,
            role="assistant",
            content=ai_text,
            user_id=user_id,
            session_id=session_id,
        )
        await db.log_turn_pair(
            session_id=session_id, user_id=user_id, user_text=user_text, ai_text=ai_text
        )
        return {}

    g = StateGraph(AgentState)
    g.add_node("prepare", prepare)
    g.add_node("call_model", call_model)
    g.add_node("persist", persist)

    g.add_edge(START, "prepare")
    g.add_edge("prepare", "call_model")
    g.add_edge("call_model", "persist")
    g.add_edge("persist", END)
    return g.compile()  # async-capable


# ------------------------ Runner (async + sync wrapper) ------------------------


async def generate_response_async(
    app,
    db: DB,
    *,
    q: str,
    user_id: str,
    session_id: Optional[str],
    model_id: str,
    history_k: int,
    reasoning: str,
) -> str:
    thread_id = f"{user_id}:{session_id or 'default'}"
    state_in: AgentState = {
        "user_id": user_id,
        "session_id": session_id,
        "thread_id": thread_id,
        "question": q,
        "history_k": history_k,
        "reasoning_effort": reasoning,
        "model_id": model_id,
    }
    out = await app.ainvoke(state_in)
    return out.get("answer", "")


async def _main_async(user_id: str, session_id: Optional[str], prompt: str) -> str:
    os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY", "")
    if not os.environ["OPENAI_API_KEY"]:
        logger.info("ERROR: Please set OPENAI_API_KEY (env or .env).", file=sys.stderr)
        return ""

    db = DB(database_url=(os.getenv("DATABASE_URL")))
    await db.ensure_schema()
    app = build_graph(db)

    result = await generate_response_async(
        app,
        db,
        q=prompt,
        user_id=user_id,
        session_id=session_id,
        model_id="openai:gpt-5",
        history_k=20,
        reasoning="medium",
    )
    return result


def main(user_id: str, session_id: Optional[str], prompt: str) -> str:
    """Synchronous entrypoint compatible with existing callers."""
    return asyncio.run(_main_async(user_id, session_id, prompt))


if __name__ == "__main__":
    user_id, session_id = "user_123", "demo"
    prompt = "Which should be a better option from latency point of view?"

    result = main(user_id, session_id, prompt)
    logger.info(result)
