import copy
import json
import random
from typing import Any

from hello.services.data_fetch import fetch_section_data
from hello.schemas import SectionRequest, ParallelWorkflowRequest
from hello.ml.utils.data_transformation import DataTransformer
from hello.ml.logger import GLOBAL_LOGGER as logger


def _random_sentence() -> str:
    subjects = [
        "Vacancy rates",
        "Leasing activity",
        "Net absorption",
        "Development pipeline",
        "Rental growth",
        "Investor sentiment",
    ]
    verbs = ["remained", "improved", "softened", "accelerated", "stabilized"]
    qualifiers = [
        "modestly",
        "notably",
        "in line with expectations",
        "amid shifting macro trends",
        "as demand normalized",
    ]
    tails = [
        "across core submarkets.",
        "supported by resilient tenant demand.",
        "even as supply deliveries increased.",
        "with landlords retaining pricing power.",
        "as occupiers prioritized flight-to-quality moves.",
    ]
    return f"{random.choice(subjects)} {random.choice(verbs)} {random.choice(qualifiers)} {random.choice(tails)}"


def _weave_numbers(data: list[dict[str, Any]]) -> str:
    # Pick two values if present and weave into a short factual clause
    try:
        if data and isinstance(data[0], dict):
            d0 = data[0]
            if "vacancy_rate" in d0 and "net_absorption" in d0:
                return f"Vacancy registered near {d0['vacancy_rate']}% while net absorption printed around {d0['net_absorption']:,}."
            if "metric" in d0 and "current" in d0:
                return f"Key metric {d0['metric']} stood at {d0['current']}."
    except Exception:
        pass
    return ""


async def generate_text(section: str, data: list[dict[str, Any]], prompt: str) -> str:
    """Stub AI agent text generation.

    Replace later with a call to your LLM provider. For now we produce a
    deterministic, readable paragraph guided by the prompt and data.
    """
    random.seed(hash(prompt + section) % (2**32 - 1))
    intro = f"{prompt.strip()[:140]}" if prompt else f"Commentary for {section}"
    facts = _weave_numbers(data)
    body = " ".join(_random_sentence() for _ in range(3))
    parts = [intro.rstrip(".") + ".", facts, body]
    return " ".join([p for p in parts if p])


async def generate_commentary(
    section: str, prompt: str, params: dict[str, Any]
) -> dict[str, Any]:
    """High-level helper used by the API to fetch data for a section and
    generate commentary text.

    Returns a dict with {"section", "text", "data"}.
    """
    data = await fetch_section_data(section, params)
    text = await generate_text(section, data, prompt)
    return {"section": section, "text": text, "data": data}


async def generate_section_llm(sections: list[SectionRequest]):
    """Temporary stub. Prints the inbound payload and returns a fixed string.

    Later, replace with a real LLM call using the provided dictionary.
    """
    try:
        # original_sections = copy.deepcopy(sections)
        # transformed_sections: list[SectionRequest] = []
        # transformer = DataTransformer()
        # # Data transformation for input_data of each section
        # try:
        #     for idx, section in enumerate(sections):
        #         try:
        #             section_dict = section.model_dump() if hasattr(section, "model_dump") else dict(section)  # type: ignore
        #             input_data = section_dict.get("input_data")
        #             if input_data:
        #                 transformed_inputs: list[str] = []
        #                 for jdx, raw in enumerate(input_data):
        #                     try:
        #                         # Ensure we have a dict for processing
        #                         parsed = json.loads(raw) if isinstance(raw, str) else raw
        #                         processed = transformer.process(parsed)
        #                         # Preserve schema contract: list of JSON strings
        #                         transformed_inputs.append(json.dumps(processed, indent=2))
        #                     except Exception:
        #                         logger.exception(
        #                             f"generate_section_llm input_data item transform failed section_index={idx} item_index={jdx}; skipping item"
        #                         )
        #                         continue
        #                 section_dict["input_data"] = transformed_inputs
        #             transformed_sections.append(SectionRequest(**section_dict))
        #         except Exception:
        #             # Keep original section if its transformation fails entirely
        #             logger.exception(
        #                 f"generate_section_llm section transform failed; preserving original section at index {idx}"
        #             )
        #             transformed_sections.append(section)
        #
        #     # Use transformed list going forward
        #     sections = transformed_sections
        # except Exception as e:
        #     logger.exception("generate_section_llm section transformations failed; using original sections")
        #     sections = original_sections

        from hello.routers.agents import invoke_parallel_workflow
        result = await invoke_parallel_workflow(payload=ParallelWorkflowRequest(sections=sections))
        logger.info(f"Response from LLM generate_section_llm: \n{result.model_dump()}")
        return result.section_results
    except Exception as e:
        logger.exception("LLM generate_section_llm EXCEPTION")
        raise e
