from __future__ import annotations

import os
import re
from dataclasses import dataclass
from dotenv import load_dotenv
from typing import Any, Dict, Generator, Iterable, Optional

from ddtrace.llmobs import LLMObs  # Datadog LLM Observability
from openai import OpenAI, AsyncOpenAI  # Official OpenAI SDK

from hello.ml.logger import GLOBAL_LOGGER as logger

load_dotenv(".env")  # take environment variables from .env.

# ---------------------------
# Small PII redaction hook
# ---------------------------
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"(\+?\d[\d(). -]{7,}\d)")


def _redact_text(s: str) -> str:
    s = _EMAIL.sub("[redacted-email]", s or "")
    s = _PHONE.sub("[redacted-phone]", s)
    return s


def _span_processor(span):
    # Runs just before Datadog emits the span.
    for side in ("input", "output"):
        msgs = getattr(span, side, None) or []
        for m in msgs:
            if isinstance(m, dict) and "content" in m and isinstance(m["content"], str):
                m["content"] = _redact_text(m["content"])
    return span


# ---------------------------
# Datadog enablement
# ---------------------------
def enable_llmobs(
    *,
    ml_app: str,
    agentless: bool = False,  # True,
    service: Optional[str] = None,
    env: Optional[str] = None,
) -> None:
    """
    Programmatic enablement. Use this OR ddtrace-run (not both).
    """
    LLMObs.enable(  # See SDK docs for parameters & defaults
        ml_app=ml_app,
        agentless_enabled=agentless,
        api_key=os.getenv("DD_API_KEY"),
        site=os.getenv("DD_SITE"),
        service=service or os.getenv("DD_SERVICE"),
        env=env or os.getenv("DD_ENV"),
        integrations_enabled=True,  # auto-instrument OpenAI
        span_processor=_span_processor,
    )


# ---------------------------
# OpenAI client wrapper
# ---------------------------
@dataclass(slots=True)
class OpenAISettings:
    model: str = (os.getenv("OPENAI_MODEL"),)
    # temperature: float = 0.3
    max_output_tokens: int = 800


class OpenAITextClient:
    """
    Thin, production-friendly wrapper around OpenAI Responses API
    that returns the model's text and usage. Datadog auto-instruments
    the underlying SDK calls.  (API: responses.create/stream)"""

    def __init__(
        self, settings: OpenAISettings | None = None, *, api_key: Optional[str] = None
    ):
        self.settings = settings or OpenAISettings()
        key = os.getenv("OPENAI_API_KEY")
        self.client = OpenAI(api_key=key)
        self.async_client = AsyncOpenAI(api_key=key)

    # ---- sync, non-streaming ----
    def generate(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        tags: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        tag_map = {"ml.route": "generate"}
        if user_id:
            tag_map["user.id"] = user_id
        if tags:
            tag_map.update(tags)

        # Tag the auto-instrumented OpenAI span
        with LLMObs.annotation_context(tags=tag_map):
            resp = self.client.responses.create(
                model=self.settings.model,
                # Responses API: structured input; system goes in 'instructions'
                input=[
                    {
                        "role": "user",
                        "content": [{"type": "input_text", "text": prompt}],
                    }
                ],
                instructions=system,
                # temperature=self.settings.temperature,
                max_output_tokens=self.settings.max_output_tokens,
            )

        # Robustly extract text (prefer output_text; fallbacks if SDK shape changes)
        text = getattr(resp, "output_text", None)
        if text is None:
            try:
                # Fallback: concatenate output message content parts (Responses format)
                items = getattr(resp, "output", []) or []
                parts = []
                for it in items:
                    if getattr(it, "type", "") == "message":
                        for c in getattr(it, "content", []) or []:
                            if getattr(c, "type", "") in ("output_text", "text"):
                                parts.append(
                                    getattr(c, "text", None)
                                    or getattr(c, "value", None)
                                    or ""
                                )
                text = "".join(p for p in parts if p)
            except Exception:
                text = None

        # Attach usage metrics to the active span (tokens -> Datadog)
        usage = getattr(resp, "usage", None)
        metrics = None
        if usage:
            metrics = {
                "input_tokens": getattr(usage, "input_tokens", None),
                "output_tokens": getattr(usage, "output_tokens", None),
                "total_tokens": getattr(usage, "total_tokens", None),
            }
            LLMObs.annotate(metrics={k: v for k, v in metrics.items() if v is not None})

        return {"text": text, "usage": metrics, "raw": resp}

    # ---- sync streaming ----
    def stream(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        tags: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        include_usage: bool = True,  # ensures a usage chunk at the end when supported
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Yields {"event":"delta","text": str} for streamed tokens,
               then a final {"event":"completed","text": full, "usage": {...}}.
        """
        tag_map = {"ml.route": "stream"}
        if user_id:
            tag_map["user.id"] = user_id
        if tags:
            tag_map.update(tags)

        with LLMObs.annotation_context(tags=tag_map):
            with self.client.responses.stream(
                model=self.settings.model,
                input=[
                    {
                        "role": "user",
                        "content": [{"type": "input_text", "text": prompt}],
                    }
                ],
                instructions=system,
                temperature=self.settings.temperature,
                max_output_tokens=self.settings.max_output_tokens,
                stream_options={
                    "include_usage": include_usage
                },  # usage in final chunk (OpenAI)
            ) as stream:
                full = []
                for event in stream:
                    # Responses streaming event types include "response.output_text.delta"
                    if getattr(event, "type", "") == "response.output_text.delta":
                        delta = getattr(event, "delta", "")
                        if delta:
                            full.append(delta)
                            yield {"event": "delta", "text": delta}

                final = stream.get_final_response()
                usage = getattr(final, "usage", None)
                metrics = None
                if usage:
                    metrics = {
                        "input_tokens": getattr(usage, "input_tokens", None),
                        "output_tokens": getattr(usage, "output_tokens", None),
                        "total_tokens": getattr(usage, "total_tokens", None),
                    }
                    LLMObs.annotate(
                        metrics={k: v for k, v in metrics.items() if v is not None}
                    )
                yield {"event": "completed", "text": "".join(full), "usage": metrics}


def main(prompt: str):
    enable_llmobs(ml_app="cbre-app")
    llm = OpenAITextClient(OpenAISettings())

    res = llm.generate(prompt, system="Be concise.")
    # logger.info(res["text"])
    # logger.info(res["usage"])
    return res["text"]


if main() == "__main__":
    prompt = "What is the gpt-5?"
    result = main(prompt=prompt)
    logger.info("RESULT:", result)
