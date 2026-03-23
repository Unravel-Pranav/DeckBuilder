from __future__ import annotations
"""Modular LLM Hallucination Evaluator

This module provides a structured class for hallucination scoring similar to
`FactualCorrectnessEvaluator` and `LLMConsistencyMetricEvaluator` patterns.

Public Sync API:
    evaluator = LLMHallucinationEvaluator()
    result = evaluator.evaluate(ground_truth, generated)

Public Async API:
    result = await evaluator.aevaluate(ground_truth, generated)

Returned dict fields:
    hallucination_score: float | None   # unsupported_claims / total_claims
    unsupported_claims_ratio: float | None  # alias of hallucination_score
    total_claims: int | None
    unsupported_claims: int | None
    extracted_claims: list[str] | None
    raw_model_text: str | None
    error: str | None  (invocation_failed | parse_failed | None)

Pass/Fail is intentionally not included here (composition left to orchestrator).
"""

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from hello.ml.evaluation.metrics.base_model import ModelForEvaluation
from hello.ml.exception.custom_exception import MultiAgentWorkflowException
from hello.ml.logger import GLOBAL_LOGGER as logger
from hello.services.config import settings

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_BRACE_RE = re.compile(r"\{.*\}", re.DOTALL)

PROMPT_TEMPLATE = """You are a rigorous hallucination detection assistant.
Given a GROUND TRUTH reference and a GENERATED SUMMARY:
1. Extract factual CLAIMS from the generated summary (distinct, atomic, verifiable).
2. Label each claim relative to the ground truth as one of:
     - SUPPORTED (clearly in reference)
     - CONTRADICTED (reference states opposite/conflicting info)
     - NOT_FOUND (no explicit support in reference)
3. Output STRICT JSON ONLY in the schema:
{{
    \"claims\": [
        {{\"claim\": \"<text>\", \"label\": \"SUPPORTED|CONTRADICTED|NOT_FOUND\"}}
    ]
}}
GROUND TRUTH:\n{ground_truth}\n
GENERATED SUMMARY:\n{generated}\n
Output ONLY JSON. No commentary.
"""

@dataclass
class HallucinationEvalConfig:
    max_retries: int = 1  # simple hook for future extension
    include_detail: bool = True

class LLMHallucinationEvaluator(ModelForEvaluation):
    """Modular evaluator providing sync + async hallucination scoring.

    Parameters
    ----------
    config : HallucinationEvalConfig | None
        Configuration (model name etc.). Ignored if `llm` is explicitly supplied.
    llm : Any | None
        Pre-initialized LLM/chat model instance. If provided, the base class
        initialization is skipped and this instance is used directly.
    model_name : str | None
        Optional override for model name when not supplying `llm`. If omitted,
        the value from config (or default) is used.
    """

    def __init__(
        self,
        config: Optional[HallucinationEvalConfig] = None,
        model_name: str = "gpt-4o-mini"
    ):
        self.config = config or HallucinationEvalConfig()
        super().__init__(model_name=model_name)

    # ---------------- Prompt + Parse Helpers ----------------
    @staticmethod
    def _build_prompt(ground_truth: str, generated: str) -> str:
        return PROMPT_TEMPLATE.format(ground_truth=ground_truth.strip(), generated=generated.strip())

    @staticmethod
    def _extract_json_block(text: str) -> Optional[Dict[str, Any]]:
        if not text:
            return None
        m = _JSON_FENCE_RE.search(text)
        block = m.group(1) if m else None
        if not block:
            m2 = _BRACE_RE.search(text)
            if m2:
                block = m2.group(0)
        if not block:
            return None
        try:
            return json.loads(block)
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def _compute_metrics(entries: List[Dict[str, Any]]):
        claims: List[str] = []
        unsupported = 0
        for e in entries:
            if not isinstance(e, dict):
                continue
            ct = e.get("claim")
            label = (e.get("label") or "").upper().strip()
            if not isinstance(ct, str) or not ct.strip():
                continue
            claims.append(ct.strip())
            if label in {"CONTRADICTED", "NOT_FOUND"}:
                unsupported += 1
        total = len(claims)
        score = (unsupported / total) if total else None
        return claims, unsupported, total, score

    # ---------------- Async Core ----------------
    async def aevaluate(self, ground_truth: str, generated: str) -> Dict[str, Any]:

        if settings.AGENTS_DEBUG:
            logger.info("--------------------------------")
            logger.info("Evaluating hallucination...")
            logger.info("--------------------------------")
        if not ground_truth or not ground_truth.strip():
            raise ValueError("ground_truth must be a non-empty string")
        if not generated or not generated.strip():
            raise ValueError("generated summary must be a non-empty string")

        prompt = self._build_prompt(ground_truth, generated)
        raw_response: Optional[str] = None
        try:
            llm = self.llm
            if hasattr(llm, "ainvoke"):
                res = await llm.ainvoke(prompt)
                raw_response = res.content if hasattr(res, "content") else str(res)
            else:
                loop = asyncio.get_running_loop()
                raw_response = await loop.run_in_executor(None, lambda: llm.invoke(prompt).content)
        except Exception as e:  # noqa: BLE001
            MultiAgentWorkflowException.log_exception(e, "LLMHallucinationEvaluator")
            return {
                "hallucination_score": None,
                "unsupported_claims_ratio": None,
                "total_claims": None,
                "unsupported_claims": None,
                "extracted_claims": None,
                "raw_model_text": raw_response,
                "error": f"invocation_failed: {e}",
            }

        data = self._extract_json_block(raw_response)
        if settings.AGENTS_DEBUG:
            logger.info(f"[LLMHallucinationEvaluator] raw_response: {raw_response}")
            logger.info(f"[LLMHallucinationEvaluator] parsed: {data}")
        if not data or "claims" not in data or not isinstance(data["claims"], list):
            return {
                "hallucination_score": None,
                "unsupported_claims_ratio": None,
                "total_claims": None,
                "unsupported_claims": None,
                "extracted_claims": None,
                "raw_model_text": raw_response,
                "error": "parse_failed",
            }

        claims, unsupported, total, score = self._compute_metrics(data["claims"])
        if settings.AGENTS_DEBUG:
            logger.info(
                f"[LLMHallucinationEvaluator] total={total} unsupported={unsupported} score={score}"
            )
        return {
            "hallucination_score": score,
            "unsupported_claims_ratio": (unsupported / total) if total else None,
            "total_claims": total,
            "unsupported_claims": unsupported,
            "extracted_claims": claims,
            "raw_model_text": raw_response,
            "error": None,
        }

    # ---------------- Sync Wrapper ----------------
    def evaluate(self, ground_truth: str, generated: str) -> Dict[str, Any]:
        async def _run():
            return await self.aevaluate(ground_truth, generated)
        try:
            return asyncio.run(_run())
        except RuntimeError:
            import concurrent.futures
            def _thread():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    return loop.run_until_complete(_run())
                finally:
                    loop.close()
            with concurrent.futures.ThreadPoolExecutor() as ex:
                return ex.submit(_thread).result()

if __name__ == "__main__":  # Simple smoke test
    gt = (
        """In Q2 2025 the Minneapolis/St. Paul Industrial market reported a total availability rate of 6.2%, up 50 bps quarter-over-quarter and up 60 bps year-over-year, with a 220 bps increase over the past 3 years."""
    )
    gen = (
        """In Q2 2025 the market availability was 6.2%, rising 50 bps QoQ and 60 bps YoY, diverging from a previous flat trend and adding an invented claim about vacancy dropping."""
    )
    evaluator = LLMHallucinationEvaluator()
    logger.info(evaluator.evaluate(gt, gen))
