"""
LLM Observability for Datadog

Datadog LLM Observability docs:
- Enabling via ddtrace-run / LLMObs.enable(): https://docs.datadoghq.com/llm_observability/instrumentation/sdk/?tab=python
- Span decorators & annotation: see same SDK reference
- Custom evaluations: https://docs.datadoghq.com/llm_observability/evaluations/submit_evaluations/
"""

from __future__ import annotations

import os
import re
from dotenv import load_dotenv
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import (
    Any,
    Dict,
    Iterable,
    List,
    Mapping,
    MutableMapping,
    Optional,
    Sequence,
    Tuple,
    Union,
)

# Core Datadog LLM Observability APIs
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import (
    workflow,
    llm,
    retrieval,
    tool,
    task,
    embedding,
)
from ddtrace.llmobs.utils import Prompt

from hello.ml.logger import GLOBAL_LOGGER as logger

load_dotenv(".env")


JSON = Union[str, int, float, bool, None, Mapping[str, Any], Sequence[Any]]


# ---------- Config & Enabler ----------


@dataclass(frozen=True)
class LLMObsConfig:
    """Minimal config for LLM Observability."""

    ml_app: Optional[str] = None  # falls back to DD_LLMOBS_ML_APP / DD_SERVICE
    site: Optional[str] = None  # e.g., "us5.datadoghq.com"
    api_key: Optional[str] = None  # required for agentless
    env: Optional[str] = None  # maps to DD_ENV
    service: Optional[str] = None  # maps to DD_SERVICE
    agentless: bool = False  # set True if not running the Datadog Agent
    integrations_enabled: bool = True  # auto-instrument supported LLM SDKs


def enable(cfg: LLMObsConfig) -> None:
    """
    Programmatic enablement (don't mix with ddtrace-run).
    Mirrors Datadog's LLMObs.enable(...) parameters.
    """
    LLMObs.enable(
        ml_app=cfg.ml_app,
        api_key=cfg.api_key,
        site=cfg.site,
        env=cfg.env,
        service=cfg.service,
        agentless_enabled=cfg.agentless,
        integrations_enabled=cfg.integrations_enabled,
    )


# ---------- Light PII Redaction (optional) ----------


@dataclass
class RedactionRules:
    mask: str = "‹redacted›"
    patterns: Tuple[re.Pattern, ...] = field(
        default_factory=lambda: (
            re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),  # emails
            re.compile(r"\b(?:\d[ -]*?){13,19}\b"),  # card-ish
            re.compile(r"\b\d{3}[-.\s]?\d{2,3}[-.\s]?\d{4}\b"),  # phone-like
            re.compile(
                r"(?:apikey|token|secret|password)\s*[:=]\s*[^\s,;]+", re.I
            ),  # keys
        )
    )


def _redact_text(text: str, rules: Optional[RedactionRules]) -> str:
    if not rules:
        return text
    for pat in rules.patterns:
        text = pat.sub(rules.mask, text)
    return text


def _redact_obj(obj: JSON, rules: Optional[RedactionRules]) -> JSON:
    if not rules:
        return obj
    if isinstance(obj, str):
        return _redact_text(obj, rules)
    if isinstance(obj, Mapping):
        return {k: _redact_obj(v, rules) for k, v in obj.items()}
    if isinstance(obj, Sequence) and not isinstance(obj, (str, bytes, bytearray)):
        return [_redact_obj(v, rules) for v in obj]
    return obj


# ---------- Annotation Helpers (shape-safe & portable) ----------


def record_llm_io(
    *,
    messages_in: Sequence[Mapping[str, Any]],
    messages_out: Optional[Sequence[Mapping[str, Any]]] = None,
    metadata: Optional[Mapping[str, JSON]] = None,
    metrics: Optional[Mapping[str, float]] = None,
    tags: Optional[Mapping[str, JSON]] = None,
    redact: Optional[RedactionRules] = None,
) -> None:
    """
    Annotate the active LLM span with chat-style I/O.
    Input/Output format follows Datadog SDK examples: [{"role": "user|system|assistant", "content": "..."}]
    """
    LLMObs.annotate(
        input_data=_redact_obj(list(messages_in), redact),
        output_data=_redact_obj(list(messages_out) if messages_out else None, redact),
        metadata=dict(metadata or {}),
        metrics=dict(metrics or {}),
        tags=dict(tags or {}),
    )


def record_retrieval(
    *,
    question: Union[str, Mapping[str, Any]],
    documents: Sequence[Mapping[str, JSON]],
    tags: Optional[Mapping[str, JSON]] = None,
    redact: Optional[RedactionRules] = None,
) -> None:
    """
    Annotate a retrieval span; each doc may include: id, score, text, name, source, etc.
    """
    LLMObs.annotate(
        input_data=_redact_obj(question, redact),
        output_data=_redact_obj([dict(doc) for doc in documents], redact),
        tags=dict(tags or {}),
    )


def record_embedding(
    *,
    text: str,
    vector: Optional[Sequence[float]] = None,
    metrics: Optional[Mapping[str, float]] = None,
    tags: Optional[Mapping[str, JSON]] = None,
    redact: Optional[RedactionRules] = None,
) -> None:
    """
    Annotate an embedding span. Input format differs from LLM spans: {"text": "..."}.
    """
    LLMObs.annotate(
        input_data={"text": _redact_text(text, redact) if redact else text},
        output_data=list(vector) if vector is not None else None,
        metrics=dict(metrics or {}),
        tags=dict(tags or {}),
    )


@contextmanager
def prompt_context(
    *,
    template: str,
    variables: Mapping[str, JSON],
    name: Optional[str] = None,
    tags: Optional[Mapping[str, JSON]] = None,
) -> Any:
    """
    Context manager to attach prompt template + variables and optional span name override
    to *auto-instrumented* spans created under this context.
    """
    with LLMObs.annotation_context(
        prompt=Prompt(template=template, variables=dict(variables)),
        name=name,
        tags=dict(tags or {}),
    ):
        yield


# ---------- Evaluations (scores/labels tied to current span) ----------


def submit_evaluation(
    *,
    label: str,
    value: Union[float, str],
    metric_type: str = "score",  # "score" or "categorical"
    ml_app: Optional[str] = None,  # defaults to configured app
    tags: Optional[Mapping[str, JSON]] = None,
) -> Tuple[str, str]:
    """
    Submit a custom evaluation bound to the current span (e.g., RAGAS score, safety, thumbs_up).
    Returns (trace_id, span_id) for auditing.
    """
    span_ctx = LLMObs.export_span(span=None)  # current active span
    # SDK exposes submit_evaluation(...) (name may vary between versions).
    try:
        LLMObs.submit_evaluation(
            span=span_ctx,
            ml_app=ml_app,
            label=label,
            metric_type=metric_type,
            value=value,
            tags=dict(tags or {}),
        )
    except AttributeError:
        # Older/alt method name
        LLMObs.submit_evaluation_for(  # type: ignore[attr-defined]
            span=span_ctx,
            ml_app=ml_app,
            label=label,
            metric_type=metric_type,
            value=value,
            tags=dict(tags or {}),
        )
    return (str(span_ctx.get("trace_id")), str(span_ctx.get("span_id")))


# ---------- Re-export Datadog's decorators for convenience ----------

__all__ = [
    "enable",
    "LLMObsConfig",
    "RedactionRules",
    "record_llm_io",
    "record_retrieval",
    "record_embedding",
    "prompt_context",
    "workflow",
    "llm",
    "retrieval",
    "tool",
    "task",
    "embedding",
]

enable(
    LLMObsConfig(
        ml_app=os.getenv("DD_LLMOBS_ML_APP", "my-rag-app"),
        site=os.getenv("DD_SITE"),  # e.g. "us5.datadoghq.com"
        api_key=os.getenv("DD_API_KEY"),  # required for agentless
        env=os.getenv("DD_ENV", "prod"),
        service=os.getenv("DD_SERVICE", "rag-api"),
        agentless=bool(os.getenv("DD_LLMOBS_AGENTLESS_ENABLED", "0") in ("1", "true")),
    )
)

REDACT = RedactionRules()


@retrieval(name="retrieve_kb")
def retrieve_chunks(question: str):
    # ... your vector store lookup returning list of dicts
    docs = [{"id": "a1", "score": 0.92, "text": "...", "name": "kb://policy-v3"}]
    record_retrieval(question=question, documents=docs, redact=REDACT)
    return docs


@embedding(model_name="text-embedding-3", model_provider="openai")
def build_embedding(text: str):
    vec = [0.01, -0.02]  # example
    record_embedding(text=text, vector=vec, metrics={"input_tokens": 12})
    return vec


@llm(model_name="gpt-4o-mini", model_provider="openai", name="generate_answer")
def call_model(messages):
    # ... call your LLM client (OpenAI/Anthropic/etc.)
    response = {
        "choices": [{"message": {"role": "assistant", "content": "Here you go"}}]
    }
    # If your SDK provides token usage, add it here
    record_llm_io(
        messages_in=messages,
        messages_out=[response["choices"][0]["message"]],
        metrics={"total_tokens": 123, "input_tokens": 77, "output_tokens": 46},
        redact=REDACT,
        tags={
            "route": "answer",
            "gen_ai.system": "openai",
        },  # portable tag for OTel alignment
    )
    submit_evaluation(
        label="thumbs_up", value=1.0, metric_type="score", tags={"source": "ui"}
    )
    return response


@workflow(name="rag_pipeline")
def handle_query(user_q: str):
    chunks = retrieve_chunks(user_q)
    # Attach prompt template context to auto spans
    with prompt_context(
        name="rag_prompt",
        template="Answer the question using context: {{context}}\nQ: {{question}}",
        variables={"question": user_q, "context": " ".join(d["text"] for d in chunks)},
    ):
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": user_q},
        ]
        return call_model(messages)


def handle_query(user_q: str):
    chunks = retrieve_chunks(user_q)
    # Attach prompt template context to auto spans
    with prompt_context(
        name="rag_prompt",
        template="Answer the question using context: {{context}}\nQ: {{question}}",
        variables={"question": user_q, "context": " ".join(d["text"] for d in chunks)},
    ):
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": user_q},
        ]
        call_model(messages)
        return call_model(messages)


if __name__ == "__main__":
    user_q = "Tell me about GenAI."
    result = handle_query(user_q)
    logger.info(result)
