from __future__ import annotations
"""LLM-based Consistency Metric Evaluator

Purpose:
  Provide a higher-signal consistency evaluation across multiple generated summaries
  compared to heuristic fuzzy similarity by leveraging the existing WSO2-proxied
  AzureChatOpenAI model for:
    1. Key fact extraction from the ground truth.
    2. Key fact extraction from each generated summary (optional, for recall/precision).
    3. Fact classification (Supported / Contradicted / Missing / Irrelevant) per summary.

Outputs:
  - faithfulness: proportion of ground-truth facts supported (micro average across summaries)
  - contradiction_rate: proportion of ground-truth facts contradicted by at least one summary
  - redundancy: average duplicate fact rate within summaries (optional signal)
  - coverage: average fraction of ground-truth facts mentioned per summary
  - precision: average fraction of a summary's extracted facts that map to ground-truth facts
  - stability: for each fact, presence ratio across summaries (like key_fact_stability)
  - consistency_score: weighted composite

Design Notes:
  - Deterministic temperature (0) for reproducibility.
  - JSON parsing with graceful fallback.
  - Batching & concurrency to reduce latency (can be disabled).
  - Caching layer (in-memory) to avoid re-extracting identical text facts.

Scoring Formula (default weights, sum=1):
  score = 0.30*faithfulness + 0.15*(1-contradiction_rate) + 0.15*coverage + 0.15*precision + 0.25*stability

Pass Criteria:
  - consistency_score >= threshold and faithfulness >= component_floor and stability >= component_floor

Configuration knobs exposed via LLMConsistencyConfig.
"""

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Tuple

from hello.ml.evaluation.metrics.base_model import ModelForEvaluation
from hello.services.config import settings
from hello.ml.logger import GLOBAL_LOGGER as logger
from hello.ml.exception.custom_exception import MultiAgentWorkflowException

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_BRACES_RE = re.compile(r"\{.*\}", re.DOTALL)
_FLOAT_RE = re.compile(r"(?<![0-9.])([01](?:\.\d+)?)")


@dataclass
class LLMConsistencyConfig:
    weight_faithfulness: float = 0.30
    weight_non_contradiction: float = 0.15  # applied to (1 - contradiction_rate)
    weight_coverage: float = 0.15
    weight_precision: float = 0.15
    weight_stability: float = 0.25
    threshold: float = 0.65
    component_floor: float = 0.5
    max_facts: int = 12
    include_detail: bool = True
    concurrent: bool = True
    strict_mode: bool = False  # if True require 0 contradiction for pass

class LLMConsistencyMetricEvaluator(ModelForEvaluation):
    def __init__(self, config: Optional[LLMConsistencyConfig] = None, *, model_name: str = "gpt-4.1"):
        super().__init__(model_name=model_name)
        self.config = config or LLMConsistencyConfig()
        # Normalize weights
        total = (
            self.config.weight_faithfulness +
            self.config.weight_non_contradiction +
            self.config.weight_coverage +
            self.config.weight_precision +
            self.config.weight_stability
        )
        if abs(total - 1.0) > 1e-6:
            logger.info(f"Adjusting LLMConsistency weights from {total:.3f} to 1.0")
            self.config.weight_faithfulness /= total
            self.config.weight_non_contradiction /= total
            self.config.weight_coverage /= total
            self.config.weight_precision /= total
            self.config.weight_stability /= total
        self._fact_cache: Dict[str, List[str]] = {}

    # -------------- LLM Invocation Helpers --------------
    async def _ainvoke(self, prompt: str) -> str:
        llm = self.llm
        try:
            if hasattr(llm, "ainvoke"):
                res = await llm.ainvoke(prompt)
                return res.content if hasattr(res, "content") else str(res)
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, lambda: llm.invoke(prompt).content)
        except Exception as e:
            MultiAgentWorkflowException.log_exception(e, "LLMConsistencyMetricEvaluator")
            raise MultiAgentWorkflowException(f"Failed LLM invocation during consistency eval: {str(e)}")

    # -------------- Prompt Templates --------------
    @staticmethod
    def _fact_extraction_prompt(text: str, max_facts: int) -> str:
        return f"""Extract up to {max_facts} DISTINCT, atomic factual statements from the text below.
Return STRICT JSON with field facts: [<string>, ...]
Guidelines:
- Each fact should be self-contained and verifiable.
- Avoid redundancy or overlapping phrasing.
- Exclude generic narrative filler.
Text:\n{text}\nOutput ONLY JSON."""

    @staticmethod
    def _fact_classification_prompt(facts: List[str], summary: str) -> str:
        joined = "\n".join(f"- {f}" for f in facts)
        return f"""You are a fact classification assistant.
Given the list of ground truth facts and ONE generated summary, classify each fact relative to the summary.
Labels:
  SUPPORTED: Summary clearly expresses the fact (allow paraphrase).
  CONTRADICTED: Summary asserts the opposite or materially conflicting info.
  MISSING: Fact not present.
  IRRELEVANT: Fact is unrelated (should be rare if facts are well-formed).
Return STRICT JSON: {{"classifications": [{{"fact": <string>, "label": <SUPPORTED|CONTRADICTED|MISSING|IRRELEVANT>}}...]}}
Ground Truth Facts:\n{joined}\n\nSummary:\n{summary}\nOutput ONLY JSON."""

    @staticmethod
    def _summary_fact_extraction_prompt(summary: str, max_facts: int) -> str:
        return f"""Extract up to {max_facts} concise factual statements from the summary.
Return STRICT JSON: {{"facts": ["fact1", "fact2", ...]}}.
Focus on concrete claims (entities, numbers, relationships). Avoid splitting trivial fragments.
Summary:\n{summary}\nOutput ONLY JSON."""

    # -------------- Parsing Utilities --------------
    @staticmethod
    def _extract_json_block(text: str) -> Optional[str]:
        if not text:
            return None
        m = _JSON_FENCE_RE.search(text)
        if m:
            return m.group(1)
        m2 = _BRACES_RE.search(text)
        return m2.group(0) if m2 else None

    @classmethod
    def _parse_json(cls, text: str) -> Optional[Dict[str, Any]]:
        block = cls._extract_json_block(text)
        if not block:
            return None
        try:
            return json.loads(block)
        except Exception:
            return None

    # -------------- Fact Extraction --------------
    async def _extract_facts(self, text: str, *, is_ground_truth: bool) -> List[str]:
        key = ("GT:" if is_ground_truth else "SUM:") + text
        if key in self._fact_cache:
            if settings.AGENTS_DEBUG:
                logger.info(f"[LLMConsistencyMetric] Cache hit for {'ground_truth' if is_ground_truth else 'summary'} facts: {len(self._fact_cache[key])}")
            return self._fact_cache[key]
        prompt = self._fact_extraction_prompt(text, self.config.max_facts)
        try:
            raw = await self._ainvoke(prompt)
            data = self._parse_json(raw) or {}
            facts = data.get("facts")
            if isinstance(facts, list):
                cleaned = []
                seen = set()
                for f in facts:
                    if not isinstance(f, str):
                        continue
                    s = f.strip()
                    if not s:
                        continue
                    low = s.lower()
                    if low in seen:
                        continue
                    seen.add(low)
                    cleaned.append(s)
                self._fact_cache[key] = cleaned
                if settings.AGENTS_DEBUG:
                    head = cleaned[:5]
                    logger.info(f"[LLMConsistencyMetric] Extracted {'ground' if is_ground_truth else 'summary'} facts (n={len(cleaned)}): {head}")
                return cleaned
        except Exception as e:
            MultiAgentWorkflowException.log_exception(e, "LLMConsistencyMetricEvaluator")
            if settings.AGENTS_DEBUG:
                logger.info(f"[LLMConsistencyMetric] Fact extraction error: {e}")
        self._fact_cache[key] = []
        return []

    # -------------- Fact Classification --------------
    async def _classify_facts_for_summary(self, ground_facts: List[str], summary: str) -> List[Dict[str, str]]:
        if not ground_facts:
            return []
        prompt = self._fact_classification_prompt(ground_facts, summary)
        try:
            raw = await self._ainvoke(prompt)
            data = self._parse_json(raw) or {}
            cl = data.get("classifications")
            if isinstance(cl, list):
                out = []
                for c in cl:
                    if not isinstance(c, dict):
                        continue
                    fact = c.get("fact")
                    label = c.get("label")
                    if isinstance(fact, str) and isinstance(label, str):
                        out.append({"fact": fact.strip(), "label": label.strip().upper()})
                if settings.AGENTS_DEBUG:
                    counts = {}
                    for item in out:
                        counts[item['label']] = counts.get(item['label'], 0) + 1
                    logger.info(f"[LLMConsistencyMetric] Classification labels distribution: {counts}")
                return out
        except Exception as e:
            MultiAgentWorkflowException.log_exception(e, "LLMConsistencyMetricEvaluator")
            if settings.AGENTS_DEBUG:
                logger.info(f"[LLMConsistencyMetric] Classification error: {e}")
        return []

    async def _extract_summary_facts(self, summary: str) -> List[str]:
        prompt = self._summary_fact_extraction_prompt(summary, self.config.max_facts)
        try:
            raw = await self._ainvoke(prompt)
            data = self._parse_json(raw) or {}
            facts = data.get("facts")
            if isinstance(facts, list):
                cleaned = []
                seen = set()
                for f in facts:
                    if isinstance(f, str):
                        s = f.strip()
                        if s and s.lower() not in seen:
                            seen.add(s.lower())
                            cleaned.append(s)
                return cleaned
        except Exception as e:
            MultiAgentWorkflowException.log_exception(e, "LLMConsistencyMetricEvaluator")
        return []

    # -------------- Scoring Components --------------
    def _compute_components(
        self,
        *,
        ground_facts: List[str],
        all_classifications: List[List[Dict[str, str]]],
        summary_facts_list: List[List[str]],
    ) -> Dict[str, Any]:
        if not ground_facts:
            return {
                "faithfulness": None,
                "contradiction_rate": None,
                "coverage": None,
                "precision": None,
                "stability": None,
                "consistency_score": None,
                "passed": None,
                "detail": {"reason": "No ground truth facts extracted"},
            }
        n_summaries = len(all_classifications)
        # Map ground fact -> presence counts
        presence_counts = {f: 0 for f in ground_facts}
        contradicted_flags = {f: False for f in ground_facts}
        supported_total = 0
        total_ground_fact_instances = len(ground_facts) * n_summaries

        logger.info(f"All Classifications: {all_classifications}")
        logger.info(f"len(all_classifications): {len(all_classifications)}")
        logger.info(f"n_summaries: {n_summaries}")
        logger.info(f"total_ground_fact_instances: {total_ground_fact_instances}")
        logger.info(f"contradicted_flags: {contradicted_flags}")

        for cls in all_classifications:
            # Build mapping for this summary
            fact_to_label = {c["fact"].lower(): c["label"] for c in cls if "fact" in c and "label" in c}
            for gf in ground_facts:
                lab = fact_to_label.get(gf.lower())
                if lab == "SUPPORTED":
                    supported_total += 1
                    presence_counts[gf] += 1
                elif lab == "CONTRADICTED":
                    contradicted_flags[gf] = True
        faithfulness = supported_total / total_ground_fact_instances if total_ground_fact_instances else 0.0
        contradiction_rate = sum(1 for v in contradicted_flags.values() if v) / len(ground_facts)
        coverage = sum(presence_counts.values()) / (len(ground_facts) * n_summaries) if n_summaries else 0.0
        # Precision: proportion of summary facts that map to some ground fact (string containment heuristic)
        precisions = []
        ground_low = [g.lower() for g in ground_facts]
        for sfacts in summary_facts_list:
            if not sfacts:
                continue
            mapped = 0
            for sf in sfacts:
                sl = sf.lower()
                if any(sl in g or g in sl for g in ground_low):
                    mapped += 1
            precisions.append(mapped / len(sfacts))
        precision = sum(precisions) / len(precisions) if precisions else 0.0
        stability = sum(c / n_summaries for c in presence_counts.values()) / len(ground_facts) if ground_facts else 0.0
        # Composite
        score = (
            self.config.weight_faithfulness * faithfulness +
            self.config.weight_non_contradiction * (1 - contradiction_rate) +
            self.config.weight_coverage * coverage +
            self.config.weight_precision * precision +
            self.config.weight_stability * stability
        )
        passed = (
            score >= self.config.threshold and
            faithfulness >= self.config.component_floor and
            stability >= self.config.component_floor and
            (contradiction_rate == 0.0 if self.config.strict_mode else True)
        )
        detail = {
            "ground_facts": ground_facts,
            "presence_counts": presence_counts,
            "contradicted_facts": [f for f, flag in contradicted_flags.items() if flag],
            "summary_precisions": precisions,
        }
        if settings.AGENTS_DEBUG:
            logger.info(
                "[LLMConsistencyMetric] Components -> faithfulness={:.3f} contradiction_rate={:.3f} coverage={:.3f} precision={:.3f} stability={:.3f} score={:.3f}".format(
                    faithfulness, contradiction_rate, coverage, precision, stability, score
                )
            )
        return {
            "faithfulness": faithfulness,
            "contradiction_rate": contradiction_rate,
            "coverage": coverage,
            "precision": precision,
            "stability": stability,
            "consistency_score": score,
            "passed": passed,
            "detail": detail if self.config.include_detail else None,
        }

    # -------------- Public API --------------
    async def aevaluate(self, ground_truth: str, summaries: List[str]) -> Dict[str, Any]:
        summaries = [s for s in summaries if s and s.strip()]
        if not ground_truth or not ground_truth.strip():
            raise ValueError("Ground truth summary must be provided")
        if not summaries:
            raise ValueError("At least one summary required")

        # 1. Extract ground truth facts
        try:
            ground_facts = await self._extract_facts(ground_truth, is_ground_truth=True)
        except MultiAgentWorkflowException:
            # already logged upstream
            raise
        except Exception as e:
            MultiAgentWorkflowException.log_exception(e, "LLMConsistencyMetricEvaluator")
            raise MultiAgentWorkflowException(f"Failed extracting ground facts: {str(e)}")
        if settings.AGENTS_DEBUG:
            logger.info(f"[LLMConsistencyMetric] Ground facts count: {len(ground_facts)}")
            logger.info(f"Ground Facts: {ground_facts}")
        if not ground_facts:
            logger.info("No ground truth facts extracted; returning null metrics")
            return {
                "faithfulness": None,
                "contradiction_rate": None,
                "coverage": None,
                "precision": None,
                "stability": None,
                "consistency_score": None,
                "passed": None,
                "detail": {"reason": "No ground truth facts extracted"},
            }

        # 2. For each summary: classify ground facts + extract its own facts
        classify_tasks = [self._classify_facts_for_summary(ground_facts, s) for s in summaries]
        summary_fact_tasks = [self._extract_summary_facts(s) for s in summaries]



        try:
            if self.config.concurrent:
                all_classifications, summary_facts_list = await asyncio.gather(
                    asyncio.gather(*classify_tasks),
                    asyncio.gather(*summary_fact_tasks)
                )
            else:
                all_classifications = []
                for t in classify_tasks:
                    all_classifications.append(await t)
                summary_facts_list = []
                for t in summary_fact_tasks:
                    summary_facts_list.append(await t)
        except Exception as e:
            MultiAgentWorkflowException.log_exception(e, "LLMConsistencyMetricEvaluator")
            raise MultiAgentWorkflowException(f"Failed during classification or summary fact extraction: {str(e)}")

        if settings.AGENTS_DEBUG:
            logger.info(f"All classifications: {all_classifications}")

            logger.info(f"Summary Facts: {summary_facts_list}")
        # 3. Compute components
        try:
            return self._compute_components(
                ground_facts=ground_facts,
                all_classifications=all_classifications,
                summary_facts_list=summary_facts_list,
            )
        except Exception as e:
            MultiAgentWorkflowException.log_exception(e, "LLMConsistencyMetricEvaluator")
            raise MultiAgentWorkflowException(f"Failed computing consistency components: {str(e)}")

    def evaluate(self, ground_truth: str, summaries: List[str]) -> Dict[str, Any]:
        async def _run():
            return await self.aevaluate(ground_truth, summaries)
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

if __name__ == "__main__":
    gt = (
"""In Q2 2025 the Minneapolis/St. Paul Industrial market reported a total availability rate of 6.2%, up 50 bps quarter-over-quarter and up 60 bps year-over-year, with a 220 bps increase over the past 3 years. Direct availability was 5.4% in Q2 2025, up 40 bps quarter-over-quarter and up 30 bps year-over-year, with a 170 bps increase over the past 3 years. Available sublease space stood at 0.8% in Q2 2025, an increase of 10 bps quarter-over-quarter and an increase 30 bps year-over-year. Sublease availability is above the 3-years quarterly average."""
    )
    summaries = [
"""In Q2 2025 the market reported a total availability rate of 6.2%, up 50 bps quarter-over-quarter and up 60 bps year-over-year, with a 220 bps increase over the past 3 years. Direct availability was 5.4% in Q2 2025, up 40 bps quarter-over-quarter and up 30 bps year-over-year, with a 170 bps increase over the past 3 years. Available sublease space stood at 0.8% in Q2 2025, up 10 bps quarter-over-quarter and an increase 30 bps year-over-year. Sublease availability is above the 3-years quarterly average.
""",
"""In Q2 2025 the Industrial market reported a total availability rate of 6.2%, up 50 bps quarter-over-quarter and up 60 bps year-over-year, with a 220 bps increase over the past 3 years. Direct availability was 5.4% in Q2 2025, up 40 bps quarter-over-quarter and up 30 bps year-over-year, with a 170 bps increase over the past 3 years. Available sublease space stood at 0.8% in Q2 2025, up 10 bps quarter-over-quarter and an increase 30 bps year-over-year. Sublease availability is above the 3-years quarterly average.
""",
"""In Q2 2025 the market reported a total availability rate of 6.2%, up 50 bps quarter-over-quarter and up 60 bps year-over-year, with a 220 bps increase over the past 3 years. Direct availability was 5.4% in Q2 2025, up 40 bps quarter-over-quarter and up 30 bps year-over-year, with a 170 bps increase over the past 3 years. Available sublease space stood at 0.8% in Q2 2025, up 10 bps quarter-over-quarter and an increase 30 bps year-over-year. Sublease availability is above the 3-years quarterly average.
""", 
"""In Q2 2025 the market reported a total availability rate of 6.2%, up 50 bps quarter-over-quarter and up 60 bps year-over-year, with a 220 bps increase over the past 3 years. Direct availability was 5.4% in Q2 2025, up 40 bps quarter-over-quarter and up 30 bps year-over-year, with a 170 bps increase over the past 3 years. Available sublease space stood at 0.8% in Q2 2025, up 10 bps quarter-over-quarter and an increase 30 bps year-over-year. Sublease availability is above the 3-years quarterly average.
""", 
"""In Q2 2025 the market reported a total availability rate of 6.2%, up 50 bps quarter-over-quarter and up 60 bps year-over-year, with a 220 bps increase over the past 3 years. Direct availability was 5.4% in Q2 2025, up 40 bps quarter-over-quarter and up 30 bps year-over-year, with a 170 bps increase over the past 3 years. Available sublease space stood at 0.8% in Q2 2025, up 10 bps quarter-over-quarter and an increase 30 bps year-over-year. Sublease availability is above the 3-years quarterly average.
"""

    ]
    evaluator = LLMConsistencyMetricEvaluator()
    response = evaluator.evaluate(gt, summaries)
    for key, value in response.items():
        if key == 'detail':
            logger.info("detail:")
            for sub_key, sub_value in value.items():
                logger.info("----------------------------")
                logger.info(f"  {sub_key}: {sub_value}")
        else:
            logger.info(f"{key}: {value}")
