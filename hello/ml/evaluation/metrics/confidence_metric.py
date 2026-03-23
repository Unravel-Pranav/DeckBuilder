"""Confidence Metric module.

Provides functionality to extract factual statements from a generated commentary
and verify those facts against a transformed dataset using an LLM.
"""

from __future__ import annotations
import sys
from typing import List, Sequence, Any, Dict
from pydantic import BaseModel, Field
import json

from hello.ml.logger import GLOBAL_LOGGER as logger
from hello.ml.exception.custom_exception import MultiAgentWorkflowException
from hello.ml.utils.model_factory import get_model_loader
from hello.services.config import settings


def compute_confidence_level(score: float) -> str:
    """
    Map a 0–100 confidence score to a qualitative level using configurable thresholds.

    Thresholds (from settings, defaults shown):
        - score < CONFIDENCE_LOW_MAX (60)       -> "low"
        - score < CONFIDENCE_MEDIUM_MAX (80)    -> "medium"
        - score >= CONFIDENCE_MEDIUM_MAX        -> "high"
    """
    try:
        low_max = float(getattr(settings, "CONFIDENCE_LOW_MAX", 60.0))
        med_max = float(getattr(settings, "CONFIDENCE_MEDIUM_MAX", 80.0))
    except Exception:
        low_max, med_max = 60.0, 80.0

    # Clamp to [0, 100] just in case
    score = max(0.0, min(100.0, float(score)))

    if score < low_max:
        return "low"
    if score < med_max:
        return "medium"
    return "high"


# Pydantic response models (moved from global schemas to keep metric self-contained)
class FactVerificationResult(BaseModel):
    fact: str
    supported: bool
    reason: str | None = None

    @classmethod
    def from_dataclass(cls, dv: Any) -> "FactVerificationResult":
        return cls(fact=getattr(dv, "fact"), supported=getattr(dv, "supported"), reason=getattr(dv, "reason", None))


class ConfidenceMetricResult(BaseModel):
    verifications: List[FactVerificationResult] = Field(default_factory=list)
    confidence_score: float
    confidence_level: str
    supported_count: int
    total_count: int

    @classmethod
    def build(
        cls,
        verifications: List[Any],
        confidence_score: float,
        confidence_level: str | None = None,
    ) -> "ConfidenceMetricResult":
        fv_models = [
            v if isinstance(v, FactVerificationResult) else FactVerificationResult.from_dataclass(v)
            for v in verifications
        ]
        supported = sum(1 for v in fv_models if v.supported)
        total = len(fv_models)
        level = confidence_level or compute_confidence_level(confidence_score)
        return cls(
            verifications=fv_models,
            confidence_score=confidence_score,
            confidence_level=level,
            supported_count=supported,
            total_count=total,
        )


 # Removed legacy FactVerification dataclass; using Pydantic FactVerificationResult uniformly.


class ConfidenceMetric:
    """Extract and verify facts from commentary using an LLM.

    Parameters
    ----------
    commentary: str
        The generated commentary text.
    transformed_data: Sequence[Any]
        Structured transformed data (list/dicts) used for fact verification.
    model_name: str
        Identifier for the model to load.
    reasoning_effort: str
        Reasoning effort for model (provider specific).
    temperature: float
        Sampling temperature.
    llm_client: Optional custom client implementing generate(prompt)->str. If provided, model_name etc. ignored.
    """

    def __init__(
        self,
        commentary: str,
        transformed_data: Sequence[Any]
    ) -> None:
        self.commentary = commentary
        self.transformed_data = transformed_data
        self.provider = settings.C_METRIC_MODEL_PROVIDER
        self.model_loader = get_model_loader(provider=self.provider)
        self._model_name = settings.C_METRIC_MODEL_NAME
        self._thinking_enabled = settings.C_METRIC_MODEL_THINKING_ENABLED
        self._reasoning_effort = None
        logger.info(f"ConfidenceMetric init: thinking_enabled={self._thinking_enabled}")
        if self._thinking_enabled:
            logger.info("Thinking enabled for ConfidenceMetric with level: %s", settings.C_METRIC_MODEL_REASONING_EFFECT)
            self._reasoning_effort = settings.C_METRIC_MODEL_REASONING_EFFECT
        self._temperature = settings.C_METRIC_MODEL_TEMPERATURE
        self.llm = self.model_loader.load_model(
            model_name=self._model_name,
            reasoning_effort=self._reasoning_effort,
            temperature=self._temperature,
        )
        self.last_verifications: List[FactVerificationResult] | None = None
        self.last_confidence_score: float | None = None
        
        # Use a single formatted string for structlog compatibility (avoid multiple positional args)
        logger.info(
            "%s initialized with provider = %s, model = %s, thinking_enabled = %s, reasoning_effort = %s, temperature = %s",
            self.__class__.__name__,
            self.provider,
            self._model_name,
            self._thinking_enabled,
            self._reasoning_effort,
            self._temperature,
        )

    def _reload_llm(self) -> None:
        """Reload LLM client (e.g., to refresh access token) using the same configuration."""
        logger.info("Reloading LLM client due to authentication failure; attempting to refresh token and model.")
        self.model_loader = get_model_loader(provider=self.provider)
        self.llm = self.model_loader.load_model(
            model_name=self._model_name,
            reasoning_effort=self._reasoning_effort,
            temperature=self._temperature,
        )

    def _invoke_with_fallback(self, prompt: str) -> Any:
        """Sync invoke with one-time fallback on invalid credentials: reload and retry."""
        try:
            raw = self.llm.invoke(prompt)
            return raw
        except Exception as e:
                self._reload_llm()
                return self.llm.invoke(prompt)

    async def _ainvoke_with_fallback(self, prompt: str) -> Any:
        """Async invoke with one-time fallback on invalid credentials: reload and retry."""
        try:
            raw = await self.llm.ainvoke(prompt)
            return raw
        except Exception as e:
            self._reload_llm()
            return await self.llm.ainvoke(prompt)

    def extract_facts(self, section_name: str = None) -> List[str]:
        """Extract atomic factual statements from the commentary.

        Returns
        -------
        list[str]
            List of fact strings.
        Raises
        ------
        ValueError
            If the LLM output is not a JSON array of strings.
        """
        try:
            prompt = f"""
Extract the facts from the provided commentary. 
The extracted facts will later be utilized to verify the accuracy of the commentary against the provided dataset.

OUTPUT FORMAT (STRICT):
Return ONLY a valid JSON array of strings. The entire response MUST be a single JSON array value. No surrounding prose, headers, keys, code fences, or trailing commas. If there are no qualifying facts, return [].

FACT DEFINITION & RULES (each array element must satisfy ALL):
- Each fact must be a self-contained clause or sentence that can stand alone when removed from the commentary.
- No transformation: do NOT convert, round, or reformulate numbers (e.g., do not turn "2.3 million sq. ft." into "2,300,000 sq. ft.").
- Exclude:
   - Purely subjective or evaluative language unless directly tied to a quantitative figure present in the same clause.
   - Duplicates (include a fact only once even if repeated).
   - Fragments that lose required context when isolated.
- No inference or synthesis beyond explicitly stated text.
- You MAY include the minimal surrounding clause or sentence necessary to preserve the original context for a fact, but do NOT invent, merge, or paraphrase facts across multiple sentences.
- Ensure the JSON is valid: use double quotes around strings and escape any internal quotes.


PROCEDURE YOU MUST FOLLOW:
1. Identify candidate sentences/clauses.
2. Filter using the rules above.
3. Return the JSON array of fact strings only. Do not include explanations.

Example output (format only, not to be inferred or reworded): ["Q2 2025 delivered 2.3 million sq. ft.", "3.5 million sq. ft. was under construction in Q2 2025"]

COMMENTARY:
{self.commentary.strip()}
"""

            if settings.AGENTS_DEBUG:
                logger.info(f"Prompt for facts extraction for section '{section_name}': {prompt}")


            # Call LLM with fallback to handle 401/Invalid Credentials by reloading and retrying once
            raw = self._invoke_with_fallback(prompt)
            raw_text = self._ensure_text(raw)
            facts = self._parse_json_array_of_strings(raw_text)
            logger.info("Extracted %d facts", len(facts))
            return facts
        except Exception as e:
            MultiAgentWorkflowException.log_exception(e, "extract_facts")
            raise MultiAgentWorkflowException("Error in extract_facts", 
                                              sys.exc_info())

    @staticmethod
    def _parse_json_array_of_strings(raw: str) -> List[str]:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise MultiAgentWorkflowException(f"LLM output not valid JSON: {e}; raw snippet={raw[:200]!r}") from e
        if not isinstance(data, list) or not all(isinstance(x, str) for x in data):
            raise MultiAgentWorkflowException(f"Expected JSON array of strings; got type={type(data).__name__}")
        return data

    async def get_confidence_metric(self, section_name: str = None) -> dict:
        """Verify extracted facts against transformed data using the LLM and compute confidence score.

        Returns
        -------
        dict
            {
              'verifications': List[FactVerificationResult],
              'confidence_score': float,   # 0–100 scale
              'confidence_level': str      # 'low' | 'medium' | 'high'
            }
        """
        try:
            facts = self.extract_facts(section_name=section_name)

            if settings.AGENTS_DEBUG:
                logger.info("Extracted facts for verification for section '%s': %s", section_name, facts)

            dataset_json = ""
            for num, item in enumerate(self.transformed_data):
                dataset_json += f"Input data {num + 1}:\n{item}\n"

            prompt = f"""
You are a fact-checking assistant. Given COMMENTARY, DATASET, and FACTS, mark each fact as supported either by DATASET (or derived from DATASET) or not supported. 

Return ONLY a valid JSON array of objects with keys: "fact" (string), "supported" (boolean), and "reason" (string explaining the decision and referencing the relevant data or computation). Do not include any additional text before or after the JSON.

IMPORTANT: If a fact is not present in the DATASET (i.e., the data does not contain information to verify or contradict the fact), mark it as supported (supported: true). If a fact cannot be derived from the DATASET using the computation rules, also mark it as supported (supported: true). Only mark a fact as not supported if it directly contradicts the data in the DATASET.

Use the COMMENTARY to understand the context and original phrasing of each fact. This helps verify formatting, intent, and ensures facts are evaluated as they appeared in the COMMENTARY.

Formatting rules that are considered while verifying facts:
- Square footage: Always express area as a number followed by "sq. ft.". For values ≥ 1,000,000, you MUST convert to millions and use the singular word "million" (e.g., 1,124,428 → "1.1 million sq. ft.", 2,345,678 → "2.3 million sq. ft."). This conversion is required formatting, not number invention. For smaller values, keep the full number (e.g., "800,000 sq. ft.", "100,000 sq. ft."). Never write "2.3 millions sq. ft.", "millions of sq. ft.", or "million square feet".
- Quarters as "Q1 2024"
- Percentages: one decimal place (e.g., 44.0%, not 44% or 44.00%)
    - Round to one decimal: 1.83% → 1.8%, 44.05% → 44.1%, 5.99% → 6.0%
- Dollar amounts: two decimal places (e.g., $12,345.67, not $12,345 or $12,345.6)
- Write the word "negative" instead of a minus sign
- Use comma separators for thousands in currencies and square footage where applicable.

Data consistency & accuracy rules that are considered while verifying facts:
- Numeric accuracy: every value must come from the input data or is a correct computation.
- Calculation verification:
    - QoQ change (%) = (current − prior_quarter) / prior_quarter × 100
    - YoY change (%) = (current − same_quarter_last_year) / same_quarter_last_year × 100
    - Basis points (Vacancy section only) = (current% − prior%) × 100 (report sign as "negative" when < 0)
    - Cumulative totals: latest quarter + prior quarters; label "over the last N years"
    - If the denominator is 0 or missing for any percentage change, omit the delta instead of reporting ∞ or N/A.
- Strictly No hallucinations: do not allow numbers absent from the input data.
- Range sanity: values must be within plausible ranges implied by the input data.
- Context preservation: ensure numbers retain the correct units and meaning.
- Tolerances: allow ±0.1 percentage points for percentage values, ±10 basis points for vacancy deltas, and currency rounded to the nearest cent.
- Comparator availability: if the prior comparator is missing or equals 0, percent deltas must be omitted.
  

COMMENTARY:
{self.commentary.strip()}

DATASET:
{dataset_json}

FACTS:
{json.dumps(facts, indent=2)}
            """ 
            if settings.AGENTS_DEBUG:
                logger.info(f"Prompt for facts verification for section '{section_name}': {prompt}")

            # Async call with fallback to handle 401/Invalid Credentials by reloading and retrying once
            raw = await self._ainvoke_with_fallback(prompt)
            raw_text = self._ensure_text(raw)
            verifications = self._parse_verification_results(raw_text)
            score_fraction = self.compute_confidence_score(verifications)
            # Convert to 0-100 scale and round
            score = round(score_fraction * 100, 2)
            level = compute_confidence_level(score)
            self.last_verifications = verifications
            self.last_confidence_score = score
            logger.info(
                "Verified %d facts (%d supported) | score_fraction=%.4f | score_percent=%.2f | level=%s",
                len(verifications),
                sum(r.supported for r in verifications),
                score_fraction,
                score,
                level,
            )
            return {
                "verifications": verifications,
                "confidence_score": score,
                "confidence_level": level,
            }
        except Exception as e:
            MultiAgentWorkflowException.log_exception(e, "get_confidence_metric")
            raise MultiAgentWorkflowException("Error in get_confidence_metric", sys.exc_info())

    async def get_confidence_metric_pydantic(self, section_name: str = None) -> ConfidenceMetricResult:
        """Same as get_confidence_metric but returns a Pydantic model for API serialization.

        Returns
        -------
        ConfidenceMetricResult
            Pydantic response object with counts and score.
        """
        raw = await self.get_confidence_metric(section_name=section_name)
        return ConfidenceMetricResult.build(
            raw["verifications"],
            raw["confidence_score"],
            raw.get("confidence_level"),
        )
    # --- Confidence scoring ------------------------------------------------------------------
    def confidence_score(self) -> float:
        """Return confidence score on a 0-100 scale.

        Returns
        -------
        float
            Percentage value (0 to 100). Returns 0.0 if no facts.
        """
        if self.last_confidence_score is not None:
            return self.last_confidence_score
        result = self.get_confidence_metric()
        return result["confidence_score"]

    @staticmethod
    def compute_confidence_score(verifications: Sequence[FactVerificationResult]) -> float:
        total = len(verifications)
        if total == 0:
            return 0.0
        supported = sum(1 for v in verifications if v.supported)
        return supported / total

    @staticmethod
    def _parse_verification_results(raw: str) -> List[FactVerificationResult]:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as e:
            raise MultiAgentWorkflowException(f"Verification output not valid JSON: {e}; raw snippet={raw[:200]!r}") from e
        if not isinstance(payload, list):
            raise MultiAgentWorkflowException(f"Expected list of objects; got type={type(payload).__name__}")
        results: List[FactVerificationResult] = []
        for item in payload:
            if not isinstance(item, dict):
                raise MultiAgentWorkflowException(f"Item not dict: type={type(item).__name__}")
            if "fact" not in item or "supported" not in item:
                raise MultiAgentWorkflowException("Missing required keys 'fact' or 'supported'")
            fact = item["fact"]
            supported = item["supported"]
            reason = item.get("reason")
            if not isinstance(fact, str) or not isinstance(supported, bool):
                raise MultiAgentWorkflowException("Invalid types: 'fact' must be str and 'supported' must be bool")
            if reason is not None and not isinstance(reason, str):
                reason = str(reason)
            results.append(FactVerificationResult(fact=fact, supported=supported, reason=reason))
        return results

    @staticmethod
    def _ensure_text(raw: Any) -> str:
        """Normalize LLM invoke output to text.

        Supports LangChain AIMessage/list responses and plain strings.
        """
        if isinstance(raw, str):
            return raw
        # LangChain AIMessage or similar
        content = getattr(raw, "content", None)
        if content is not None and isinstance(content, str):
            return content
        # If list of messages
        if isinstance(raw, list):
            parts = []
            for m in raw:
                c = getattr(m, "content", None)
                if c is None:
                    c = str(m)
                parts.append(c)
            return "\n".join(parts)
        # Fallback: convert to string
        return str(raw)

if __name__ == "__main__":
    import asyncio

    async def main():
        transformed_data_list = [
            [{'PROPERTY_CLASS': 'Class B', 'PERIOD': '2022 Q2', 'PERIOD_LABEL': 'Q2 2022', 'VACANCY_RATE': 15.7, 'AVG_ASKING_RATE': 38.33}, {'PROPERTY_CLASS': 'Class A', 'PERIOD': '2022 Q2', 'PERIOD_LABEL': 'Q2 2022', 'VACANCY_RATE': 18.9, 'AVG_ASKING_RATE': 49.37}, {'PROPERTY_CLASS': 'Class B', 'PERIOD': '2022 Q3', 'PERIOD_LABEL': 'Q3 2022', 'VACANCY_RATE': 16.5, 'AVG_ASKING_RATE': 37.77}, {'PROPERTY_CLASS': 'Class A', 'PERIOD': '2022 Q3', 'PERIOD_LABEL': 'Q3 2022', 'VACANCY_RATE': 19.8, 'AVG_ASKING_RATE': 48.98}, {'PROPERTY_CLASS': 'Class A', 'PERIOD': '2022 Q4', 'PERIOD_LABEL': 'Q4 2022', 'VACANCY_RATE': 21.2, 'AVG_ASKING_RATE': 49.65}, {'PROPERTY_CLASS': 'Class B', 'PERIOD': '2022 Q4', 'PERIOD_LABEL': 'Q4 2022', 'VACANCY_RATE': 15.9, 'AVG_ASKING_RATE': 37.75}, {'PROPERTY_CLASS': 'Class B', 'PERIOD': '2023 Q1', 'PERIOD_LABEL': 'Q1 2023', 'VACANCY_RATE': 16.4, 'AVG_ASKING_RATE': 37.44}, {'PROPERTY_CLASS': 'Class A', 'PERIOD': '2023 Q1', 'PERIOD_LABEL': 'Q1 2023', 'VACANCY_RATE': 21.8, 'AVG_ASKING_RATE': 51.12}, {'PROPERTY_CLASS': 'Class B', 'PERIOD': '2023 Q2', 'PERIOD_LABEL': 'Q2 2023', 'VACANCY_RATE': 17.0, 'AVG_ASKING_RATE': 37.23}, {'PROPERTY_CLASS': 'Class A', 'PERIOD': '2023 Q2', 'PERIOD_LABEL': 'Q2 2023', 'VACANCY_RATE': 22.2, 'AVG_ASKING_RATE': 51.35}, {'PROPERTY_CLASS': 'Class A', 'PERIOD': '2023 Q3', 'PERIOD_LABEL': 'Q3 2023', 'VACANCY_RATE': 23.1, 'AVG_ASKING_RATE': 51.55}, {'PROPERTY_CLASS': 'Class B', 'PERIOD': '2023 Q3', 'PERIOD_LABEL': 'Q3 2023', 'VACANCY_RATE': 17.3, 'AVG_ASKING_RATE': 36.98}, {'PROPERTY_CLASS': 'Class A', 'PERIOD': '2023 Q4', 'PERIOD_LABEL': 'Q4 2023', 'VACANCY_RATE': 24.0, 'AVG_ASKING_RATE': 51.24}, {'PROPERTY_CLASS': 'Class B', 'PERIOD': '2023 Q4', 'PERIOD_LABEL': 'Q4 2023', 'VACANCY_RATE': 17.7, 'AVG_ASKING_RATE': 36.5}, {'PROPERTY_CLASS': 'Class A', 'PERIOD': '2024 Q1', 'PERIOD_LABEL': 'Q1 2024', 'VACANCY_RATE': 25.1, 'AVG_ASKING_RATE': 51.16}, {'PROPERTY_CLASS': 'Class B', 'PERIOD': '2024 Q1', 'PERIOD_LABEL': 'Q1 2024', 'VACANCY_RATE': 17.6, 'AVG_ASKING_RATE': 36.73}, {'PROPERTY_CLASS': 'Class B', 'PERIOD': '2024 Q2', 'PERIOD_LABEL': 'Q2 2024', 'VACANCY_RATE': 18.1, 'AVG_ASKING_RATE': 37.93}, {'PROPERTY_CLASS': 'Class A', 'PERIOD': '2024 Q2', 'PERIOD_LABEL': 'Q2 2024', 'VACANCY_RATE': 25.9, 'AVG_ASKING_RATE': 51.38}, {'PROPERTY_CLASS': 'Class A', 'PERIOD': '2024 Q3', 'PERIOD_LABEL': 'Q3 2024', 'VACANCY_RATE': 26.2, 'AVG_ASKING_RATE': 51.04}, {'PROPERTY_CLASS': 'Class B', 'PERIOD': '2024 Q3', 'PERIOD_LABEL': 'Q3 2024', 'VACANCY_RATE': 18.8, 'AVG_ASKING_RATE': 37.51}, {'PROPERTY_CLASS': 'Class B', 'PERIOD': '2024 Q4', 'PERIOD_LABEL': 'Q4 2024', 'VACANCY_RATE': 18.3, 'AVG_ASKING_RATE': 37.94}, {'PROPERTY_CLASS': 'Class A', 'PERIOD': '2024 Q4', 'PERIOD_LABEL': 'Q4 2024', 'VACANCY_RATE': 26.4, 'AVG_ASKING_RATE': 51.66}, {'PROPERTY_CLASS': 'Class B', 'PERIOD': '2025 Q1', 'PERIOD_LABEL': 'Q1 2025', 'VACANCY_RATE': 18.7, 'AVG_ASKING_RATE': 37.85}, {'PROPERTY_CLASS': 'Class A', 'PERIOD': '2025 Q1', 'PERIOD_LABEL': 'Q1 2025', 'VACANCY_RATE': 26.6, 'AVG_ASKING_RATE': 51.91}, {'PROPERTY_CLASS': 'Class B', 'PERIOD': '2025 Q2', 'PERIOD_LABEL': 'Q2 2025', 'VACANCY_RATE': 18.7, 'AVG_ASKING_RATE': 37.98}, {'PROPERTY_CLASS': 'Class A', 'PERIOD': '2025 Q2', 'PERIOD_LABEL': 'Q2 2025', 'VACANCY_RATE': 26.8, 'AVG_ASKING_RATE': 51.81}], 
            [{'PROPERTY_CLASS': 'Class A', 'PERIOD': '2025 Q2', 'PERIOD_LABEL': 'Q2 2025', 'SUBMARKET': 'Downtown Los Angeles', 'AVG_ASKING_LEASE_RATE': '46.28'}, {'PROPERTY_CLASS': 'Class B', 'PERIOD': '2025 Q2', 'PERIOD_LABEL': 'Q2 2025', 'SUBMARKET': 'Downtown Los Angeles', 'AVG_ASKING_LEASE_RATE': '38.18'}, {'PROPERTY_CLASS': 'Class B', 'PERIOD': '2025 Q2', 'PERIOD_LABEL': 'Q2 2025', 'SUBMARKET': 'East Downtown', 'AVG_ASKING_LEASE_RATE': '36.53'}, {'PROPERTY_CLASS': 'Class A', 'PERIOD': '2025 Q2', 'PERIOD_LABEL': 'Q2 2025', 'SUBMARKET': 'East Downtown', 'AVG_ASKING_LEASE_RATE': '58.79'}, {'PROPERTY_CLASS': 'Class B', 'PERIOD': '2025 Q2', 'PERIOD_LABEL': 'Q2 2025', 'SUBMARKET': 'Hollywood/Wilshire Corridor', 'AVG_ASKING_LEASE_RATE': '42.77'}, {'PROPERTY_CLASS': 'Class A', 'PERIOD': '2025 Q2', 'PERIOD_LABEL': 'Q2 2025', 'SUBMARKET': 'Hollywood/Wilshire Corridor', 'AVG_ASKING_LEASE_RATE': '43.45'}, {'PROPERTY_CLASS': 'Class B', 'PERIOD': '2025 Q2', 'PERIOD_LABEL': 'Q2 2025', 'SUBMARKET': 'Mid-Counties', 'AVG_ASKING_LEASE_RATE': '25.18'}, {'PROPERTY_CLASS': 'Class A', 'PERIOD': '2025 Q2', 'PERIOD_LABEL': 'Q2 2025', 'SUBMARKET': 'Mid-Counties', 'AVG_ASKING_LEASE_RATE': '33.45'}, {'PROPERTY_CLASS': 'Class A', 'PERIOD': '2025 Q2', 'PERIOD_LABEL': 'Q2 2025', 'SUBMARKET': 'San Fernando Valley', 'AVG_ASKING_LEASE_RATE': '34.86'}, {'PROPERTY_CLASS': 'Class B', 'PERIOD': '2025 Q2', 'PERIOD_LABEL': 'Q2 2025', 'SUBMARKET': 'San Fernando Valley', 'AVG_ASKING_LEASE_RATE': '28.66'}, {'PROPERTY_CLASS': 'Class B', 'PERIOD': '2025 Q2', 'PERIOD_LABEL': 'Q2 2025', 'SUBMARKET': 'San Gabriel Valley', 'AVG_ASKING_LEASE_RATE': '28.74'}, {'PROPERTY_CLASS': 'Class A', 'PERIOD': '2025 Q2', 'PERIOD_LABEL': 'Q2 2025', 'SUBMARKET': 'San Gabriel Valley', 'AVG_ASKING_LEASE_RATE': '33.27'}, {'PROPERTY_CLASS': 'Class A', 'PERIOD': '2025 Q2', 'PERIOD_LABEL': 'Q2 2025', 'SUBMARKET': 'South Bay', 'AVG_ASKING_LEASE_RATE': '42.76'}, {'PROPERTY_CLASS': 'Class B', 'PERIOD': '2025 Q2', 'PERIOD_LABEL': 'Q2 2025', 'SUBMARKET': 'South Bay', 'AVG_ASKING_LEASE_RATE': '33.56'}, {'PROPERTY_CLASS': 'Class A', 'PERIOD': '2025 Q2', 'PERIOD_LABEL': 'Q2 2025', 'SUBMARKET': 'Tri-Cities/Glendale', 'AVG_ASKING_LEASE_RATE': '48.56'}, {'PROPERTY_CLASS': 'Class B', 'PERIOD': '2025 Q2', 'PERIOD_LABEL': 'Q2 2025', 'SUBMARKET': 'Tri-Cities/Glendale', 'AVG_ASKING_LEASE_RATE': '37.85'}, {'PROPERTY_CLASS': 'Class A', 'PERIOD': '2025 Q2', 'PERIOD_LABEL': 'Q2 2025', 'SUBMARKET': 'West Los Angeles', 'AVG_ASKING_LEASE_RATE': '68.04'}, {'PROPERTY_CLASS': 'Class B', 'PERIOD': '2025 Q2', 'PERIOD_LABEL': 'Q2 2025', 'SUBMARKET': 'West Los Angeles', 'AVG_ASKING_LEASE_RATE': '53.89'}]
             ]

        generated_commentary = """ 
The overall average direct asking lease rate in Q2 2025 is $44.90 per sq. ft., essentially unchanged from $44.88 per sq. ft. in Q1 2025 and up 0.5% year-over-year from $44.66 per sq. ft. Class A asking rents edged down quarter-over-quarter from $51.91 per sq. ft. to $51.81 per sq. ft., while remaining 0.8% higher than a year ago. Class B asking rents ticked up from $37.85 per sq. ft. in Q1 2025 to $37.98 per sq. ft. in Q2 2025 and are effectively flat year-over-year, rising just 0.1% from $37.93 per sq. ft. Overall, recent rent growth is modest, with Class A slightly outperforming the broader market.
West Los Angeles posts the highest average direct asking rate on a combined Class A and B basis at $60.97 per sq. ft., with Class A space there reaching $68.04 per sq. ft. At the low end, Mid-Counties records the lowest combined rate at $29.32 per sq. ft., including $25.18 per sq. ft. for Class B space, while the San Gabriel Valley averages $31.01 per sq. ft. combined.
        """
        data_set_list = [json.dumps(i, indent=2) for i in transformed_data_list]      
        cm = ConfidenceMetric(generated_commentary, data_set_list)
        # Use pydantic version for clean serialization
        output = await cm.get_confidence_metric_pydantic()
        for v in output.verifications:
            logger.info(v)
        logger.info(f"Confidence Score: {output.confidence_score:.2f}")
        # Serialize with model_dump()
        logger.info(json.dumps(output.model_dump(), indent=2))

    asyncio.run(main())