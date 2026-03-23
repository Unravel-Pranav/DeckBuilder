from __future__ import annotations

import asyncio, time
from fastapi import APIRouter, HTTPException, Request, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, Any
import json
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select

from hello import models
from hello.schemas import (
    WorkflowRequest,
    WorkflowResponse,
    WorkflowStatusResponse,
    ParallelWorkflowRequest,
    ParallelWorkflowResponse,
    SectionRequest,
    GenerateTitleRequest,
    GenerateTitleResponse
)
from hello.services.agent_service import generate_commentary, generate_section_llm
from hello.ml.agents.title_generation_agent import TitleGenerationAgent
from hello.services.multi_agent_workflow_service import workflow_service
from hello.services.database import get_session
from hello.services.snowflake_service import fetch_snowflake_data
from hello.services.config import settings
from hello.ml.logger import GLOBAL_LOGGER as logger
from hello.utils.sql_utils import render_sql_template
from hello.utils.commentary_utils.text_generator import generate_market_narrative
from hello.ml.evaluation.metrics.confidence_metric import ConfidenceMetric
from hello.ml.utils.data_transformation import DataTransformer
from hello.ml.utils.snowflake_exception import NoDataReturnedFromSnowflakeException
from hello.utils.auth_utils import require_auth
from hello.utils.utils import get_latest_complete_quarter


router = APIRouter(dependencies=[Depends(require_auth)])
env = settings.TESTING_ENV


class GenerateIn(BaseModel):
    section: str
    prompt: Optional[str] = None
    report_type: Optional[str] = None
    market: Optional[str] = None
    property_type: Optional[str] = None
    period_from: Optional[str] = None
    period_to: Optional[str] = None
    extra: Optional[dict[str, Any]] = None


@router.post("/generate")
async def generate_section_commentary(payload: GenerateIn, request: Request):
    """Generate commentary via agent service.

    Debug logging: prints inbound request metadata and payload; prints response JSON
    before returning to the client.
    """
    try:
        logger.info(
            "AGENTS /generate request",
            method=request.method,
            url=str(request.url),
            client=getattr(request.client, "host", None),
        )
        logger.info("AGENTS /generate body", payload=payload.model_dump())
    except Exception:
        pass
    params = {
        "report_type": payload.report_type,
        "market": payload.market,
        "property_type": payload.property_type,
        "period_from": payload.period_from,
        "period_to": payload.period_to,
    }
    if payload.extra:
        params.update(payload.extra)

    try:
        result = await generate_commentary(payload.section, payload.prompt or "", params)
        logger.info("AGENTS /generate response", result=result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("AGENTS /generate error", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to generate commentary")


class LLMPreviewIn(BaseModel):
    """Loose schema for Section Builder preview.

    Accepts any dict payload describing the section configuration that the UI
    wants to preview. We intentionally keep this open so the frontend can
    evolve shape without breaking this stub.
    """
    payload: dict


@router.post("/llm-generate-preview")
async def llm_generate_preview(request: Request, stream: bool = Query(default=False)):
    """Stub endpoint used by Section Builder's "Generate Preview".

    - Reads JSON body as a dictionary (complete section configuration)
    - Calls generate_section_llm with the dictionary
    - Returns { "text": "agent generated successfully" }
    """
    try:
        request_obj = await request.json()
        payload = request_obj.get("payload") if isinstance(request_obj, dict) and "payload" in request_obj else request_obj
    except Exception:
        logger.info("AGENTS /llm-generate-preview invalid JSON Payload body")
        raise HTTPException(status_code=400, detail="Invalid JSON Payload")

    _log_request_info(request, payload)

    report_automation_mode = payload.get("report_parameters", {}).get("automation_mode", "tier1").lower()
    
    try:
        if report_automation_mode == "tier1":
            # Stream events via SSE when requested
            if stream:
                return await _handle_tier1_mode_streaming(payload)
            return await _handle_tier1_mode(payload)
        elif report_automation_mode == "tier3":
            return _handle_tier3_mode(payload)
        else:
            raise HTTPException(status_code=400, detail="Invalid report automation mode")
    except NoDataReturnedFromSnowflakeException as e:
        logger.error("AGENTS /llm-generate-preview error", error=e.to_dict())
        raise HTTPException(status_code=404, detail="No data returned from Snowflake for the given SQL query.")
    except Exception as e:
        logger.error("AGENTS /llm-generate-preview error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


def _log_request_info(request: Request, payload: dict):
    """Log request information for debugging."""
    logger.info("AGENTS /llm-generate-preview request",
                method=request.method,
                url=str(request.url),
                client=getattr(request.client, "host", None))
    logger.info("AGENTS /llm-generate-preview payload", payload=payload)


async def _handle_tier1_mode(payload: dict) -> dict[str, str]:
    """Handle tier1 automation mode processing."""
    try:
        _render_sql_templates(payload)
        data_list = await _fetch_snowflake_data_if_needed(payload)
        return await _generate_llm_response(payload, data_list)
    except Exception as e:
        raise e


def _render_sql_templates(payload: dict):
    """Render SQL templates in the payload."""
    try:
        payload["commentary_sql"] = render_sql_template(payload.get("commentary_sql"), payload)
        payload["commentary_sql_list"] = [
            render_sql_template(sql_template, payload) 
            for sql_template in payload.get("commentary_sql_list", [])
        ]
        payload["tables_sql"] = [
            render_sql_template(sql_template, payload) 
            for sql_template in payload.get("tables_sql", [])
        ]
        payload["charts_sql"] = [
            render_sql_template(sql_template, payload) 
            for sql_template in payload.get("charts_sql", [])
        ]
        logger.info(f"AGENTS /llm-generate-preview updated-payload\n {json.dumps(payload, indent=2)}")
    except Exception as e:
        logger.error("AGENTS /llm-generate-preview error", error=str(e))
        raise HTTPException(status_code=400, detail="Failed to render SQL template. Please check the SQL syntax and rerun the query.")


async def _fetch_snowflake_data_if_needed(payload: dict) -> list[str]:
    """Fetch data from Snowflake if in CBRE environment."""
    data_list = []
    if env == "CBRE":
        sql_list = payload.get("commentary_sql_list", []) or []
        for idx, sql in enumerate(sql_list):
            if not sql:
                continue
            try:
                db_response = fetch_snowflake_data(sql)
                data_list.append(json.dumps(db_response, indent=2))
            except Exception as err:
                sql_preview = " ".join(str(sql).split())
                if len(sql_preview) > 200:
                    sql_preview = sql_preview[:200] + "…"
                logger.exception(
                    "AGENTS /llm-generate-preview Snowflake query failed",
                    extra={
                        "sql_index": idx,
                        "section": payload.get("section_name"),
                        "sql_preview": sql_preview,
                    },
                )
                raise HTTPException(
                    status_code=500,
                    detail=(
                        "An error occurred while executing the query. Please check the SQL syntax and rerun the query. "
                        f"(query #{idx + 1})"
                    ),
                ) from err
    return data_list


async def _generate_llm_response(payload: dict, data_list: list[str]) -> dict[str, str]:
    """Generate LLM response based on payload and data."""

    # initialize empty confidence metric result
    confidence_metric_result = {}
    if env == 'CBRE':
        section_name = payload.get("section_name")
        consolidation_prompt = payload.get("adjust_prompt", "")
        sql_prompts = payload.get("commentary_prompt_list", [])
        prompt_obj = {"consolidation_prompt": consolidation_prompt, "sql_prompts": sql_prompts}

        # if data_list and isinstance(data_list, list):
        #     try:
        #         original_data_list = data_list.copy()
        #         transformer = DataTransformer()
        #         transformed_data_list: list[str] = []
        #         for idx, raw in enumerate(data_list):
        #             try:
        #                 parsed = json.loads(raw) if isinstance(raw, str) else raw
        #                 processed = transformer.process(parsed)
        #                 # Keep schema contract: list of JSON strings
        #                 transformed_data_list.append(json.dumps(processed, indent=2))
        #             except Exception as err:
        #                 logger.warning("Data transform skipped index %d: %s", idx, err)
        #                 # Preserve original item so downstream still has data
        #                 transformed_data_list.append(raw)
        #         data_list = transformed_data_list
        #     except Exception as e:
        #         logger.error("Error in data transformation: %s", str(e))
        #         data_list = original_data_list  # Fallback to original data

        section = SectionRequest(
            section_id=section_name, 
            section_name=section_name, 
            session_type=section_name,
            input_data=data_list, 
            prompt=prompt_obj
        )
        
        results = await generate_section_llm([section])
        section_result = results.get(section_name)
        
        if section_result and section_result.error:
            raise RuntimeError(section_result.error)
        
        final_response = section_result.summary_result if section_result else 'agent generated successfully'

        try:
            # Confidence Metric calculation
            if final_response and final_response != "Agent couldn't generate the commentary, Please try again...":
                cm = ConfidenceMetric(final_response, data_list)
                cm_result = await cm.get_confidence_metric_pydantic(section_name=section_name)  # returns dict with verifications & score
                if hasattr(cm_result, "model_dump"):
                    confidence_metric_result = cm_result.model_dump()
                elif hasattr(cm_result, "dict"):
                    confidence_metric_result = cm_result.dict()
                else:
                    confidence_metric_result = cm_result

                if settings.AGENTS_DEBUG:
                    logger.info("Confidence metric full result for %s: %s", section_name, confidence_metric_result)
        except Exception as e:
            logger.error("AGENTS /llm-generate-preview confidence metric error", error=str(e))
            confidence_metric_result = {}
    else:
        final_response = 'agent generated successfully'

    logger.info("AGENTS /llm-generate-preview response", response=final_response)
    return {"text": final_response, 
            "confidence_metric_details": confidence_metric_result}


async def _handle_tier1_mode_streaming(payload: dict) -> StreamingResponse:
    """Stream LangGraph events as Server-Sent Events (SSE) for Tier1 mode.

    Produces events of types: custom, values, error, done.
    """
    # Build a single SectionRequest dict
    section_name = payload.get("section_name")
    consolidation_prompt = payload.get("adjust_prompt", "")
    sql_prompts = payload.get("commentary_prompt_list", [])
    prompt_obj = {"consolidation_prompt": consolidation_prompt, "sql_prompts": sql_prompts}
    
    if env != "CBRE":
        async def _dummy_stream():
            # start
            completion_json = {"state": {"node": "summary_generation_successful", "status": "end",
                                         "description": f"Summary generation successful!",
                                         "summary_result": "agent generated successfully"}}
            yield "event: agent_status\n" + f"data: {json.dumps(completion_json, default=str)}\n\n"
            # done
            confidence_metric_payload = {"state": {"node": "confidence_metric_calculation", "status": "end",
                                                   "description": f"Confidence metric calculation successful!",
                                                   "confidence_metric_details": {"confidence_score": 100}}}
            yield "event: agent_status\n" + f"data: {json.dumps(confidence_metric_payload, default=str)}\n\n"

        return StreamingResponse(_dummy_stream(), media_type="text/event-stream")
    
    try:
        _render_sql_templates(payload)
        data_list = await _fetch_snowflake_data_if_needed(payload)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("AGENTS /llm-generate-preview[stream] error", error=str(e))
        raise HTTPException(status_code=400, detail="Failed to prepare streaming payload")

    # if data_list and isinstance(data_list, list):
    #     original_data_list = data_list.copy()
    #     try:
    #         transformer = DataTransformer()
    #         transformed_data_list: list[str] = []
    #         for idx, raw in enumerate(data_list):
    #             try:
    #                 parsed = json.loads(raw) if isinstance(raw, str) else raw
    #                 processed = transformer.process(parsed)
    #                 # Keep schema contract: list of JSON strings
    #                 transformed_data_list.append(json.dumps(processed, indent=2))
    #             except Exception as err:
    #                 logger.warning("Data transform skipped index %d: %s", idx, err)
    #                 # Preserve original item so downstream still has data
    #                 transformed_data_list.append(raw)
    #         data_list = transformed_data_list
    #     except Exception as e:
    #         logger.error("Error in data transformation: %s", str(e))
    #         data_list = original_data_list  # Fallback to original data

    section = SectionRequest(
        section_id=section_name,
        section_name=section_name,
        session_type=section_name,
        input_data=data_list,
        prompt=prompt_obj,
    )

    # Ensure workflow is ready and get compiled graph
    if not workflow_service.is_parallel_ready():
        raise HTTPException(status_code=503, detail="Parallel multi-agent workflow service is not ready")
    graph = workflow_service.get_compiled_parallel_workflow()
    if graph is None:
        raise HTTPException(status_code=503, detail="Parallel workflow is unavailable")

    # Prepare initial state (aligns with service.invoke_parallel_workflow)
    start_time = time.time()
    initial_state = {
        "processing_mode": "parallel",
        "sections": [section.model_dump()],
        "section_results": {},
        "completed_sections": [],
        "failed_sections": [],
        "messages": [],
        "parallel_start_time": start_time,
    }

    async def event_generator():
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        final_state_holder = {"state": None}

        def _produce():
            try:
                for chunk, mode, state in graph.stream(
                    initial_state, stream_mode=["custom", "values"], subgraphs=True
                ):
                    msg = {"state": state, "type": mode}
                    if mode == "values":
                        final_state_holder["state"] = state
                    asyncio.run_coroutine_threadsafe(queue.put(msg), loop)
            except Exception as e:
                asyncio.run_coroutine_threadsafe(
                    queue.put({"type": "error", "error": str(e)}), loop
                )
            finally:
                asyncio.run_coroutine_threadsafe(queue.put({"type": "done"}), loop)

        # Run the blocking producer in a worker thread
        producer_task = asyncio.create_task(asyncio.to_thread(_produce))
        try:
            while True:
                event = await queue.get()
                et = event.get("type")
                if et == "values":
                    continue
                if et == "done":
                    # Compute final text from last values state (if available)
                    final_text = ""
                    try:
                        st = final_state_holder.get("state") or {}
                        section_results = (st or {}).get("section_results") or {}
                        section_out = section_results.get(section_name) or {}
                        final_text = section_out.get("summary_result")
                        if section_out.get("error"):
                            # payload = {"error": section_out.get("error")}
                            # yield "event: error\n" + f"data: {json.dumps(payload, default=str)}\n\n"
                            if final_text:
                                final_text = "Need Human Review:\n\n" + final_text
                            completion_json = {"state": {"node": "summary_generation_successful", "status": "end",
                                                         "description": f"Summary generation successful!",
                                                         "summary_result": final_text}}
                            yield "event: agent_status\n" + f"data: {json.dumps(completion_json, default=str)}\n\n"
                            break
                        completion_json = {"state": {"node": "summary_generation_successful", "status": "end", "description": f"Summary generation successful!",
                        "summary_result": final_text}}
                        yield "event: agent_status\n" + f"data: {json.dumps(completion_json, default=str)}\n\n"
                    except Exception as e:
                        logger.error("AGENTS /llm-generate-preview[stream] summary result error", error=str(e))
                        completion_json = {"state": {"node": "summary_generation_failed", "status": "error", "description": f"Summary generation failed!",
                        "summary_result": final_text}}
                        yield "event: agent_status\n" + f"data: {json.dumps(completion_json, default=str)}\n\n"
                        payload = {"error": str(e)}
                        yield "event: error\n" + f"data: {json.dumps(payload, default=str)}\n\n"
                        break
                    # Confidence metric (mirror non-streaming behavior)
                    confidence_metric_details = {}
                    try:
                        if env == 'CBRE' and final_text and final_text != "Agent couldn't generate the commentary, Please try again...":
                            confidence_metric_payload = {"state": {"node": "confidence_metric_calculation", "status": "start", "description": f"Confidence metric calculation started!"}}
                            yield "event: agent_status\n" + f"data: {json.dumps(confidence_metric_payload, default=str)}\n\n"
                            cm = ConfidenceMetric(final_text, data_list)
                            cm_result = await cm.get_confidence_metric_pydantic(section_name=section_name)
                            # Convert to a serializable dict if it's a pydantic model
                            if hasattr(cm_result, "model_dump"):
                                confidence_metric_details = cm_result.model_dump()
                            elif hasattr(cm_result, "dict"):
                                confidence_metric_details = cm_result.dict()
                            else:
                                confidence_metric_details = cm_result  # hope it's JSON serializable
                            try:
                                score = getattr(cm_result, "confidence_score", None)
                                verifs = getattr(cm_result, "verifications", None)
                                logger.info(
                                    "Confidence metric score=%s factors=%s",
                                    f"{score:.4f}" if isinstance(score, (int, float)) else score,
                                    len(verifs) if isinstance(verifs, (list, tuple)) else None,
                                )
                                if settings.AGENTS_DEBUG:
                                    logger.info("Confidence metric full result for %s: %s", section_name, cm_result)
                            except Exception:
                                pass
                            confidence_metric_payload = {"state": {"node": "confidence_metric_calculation", "status": "end", "description": f"Confidence metric calculation successful!",
                            "confidence_metric_details": confidence_metric_details}}
                            yield "event: agent_status\n" + f"data: {json.dumps(confidence_metric_payload, default=str)}\n\n"
                    except Exception as cm_err:
                        logger.error("AGENTS /llm-generate-preview[stream] confidence metric error", error=str(cm_err))
                        confidence_metric_details = {}
                        confidence_metric_payload = {"state": {"node": "confidence_metric_calculation", "status": "error", "description": f"Confidence metric calculation failed!",
                        "confidence_metric_details": confidence_metric_details}}
                        yield "event: agent_status\n" + f"data: {json.dumps(confidence_metric_payload, default=str)}\n\n"
                    break
                if et == "error":
                    payload = {"error": event.get("error")}
                    yield "event: error\n" + f"data: {json.dumps(payload, default=str)}\n\n"
                    continue
                # Forward custom/value updates
                yield f"event: agent_status\n" + f"data: {json.dumps(event, default=str)}\n\n"
        finally:
            # Ensure the background thread is cancelled when client disconnects
            try:
                producer_task.cancel()
            except Exception:
                pass

    return StreamingResponse(event_generator(), media_type="text/event-stream")


def _handle_tier3_mode(payload: dict) -> dict[str, str]:
    """Handle tier3 automation mode processing."""
    normalized_section_name = payload.get("section", {}).get("sectionAlias", "").replace(" ", "_").lower()
    logger.info("AGENTS /llm-generate-preview tier3 mode - invoking generate_market_narrative")

    if env == 'CBRE':
        try:
            response = generate_market_narrative(
                payload.get("report_parameters"),
                paragraph_keys=[normalized_section_name]
            )
        except Exception as e:
            logger.error(f"Commentary generation failed in Tier 3 mode: {str(e)}")
            raise HTTPException(status_code=500, detail="Commentary generation failed, check section names and try again.")
    else:
        response = {normalized_section_name: "Tier3 commentary generated successfully"}
    logger.info("AGENTS /llm-generate-preview response", response=response)
    return {"text": response.get(normalized_section_name)}


class ChartPreviewIn(BaseModel):
    # Minimum fields for compatibility
    sql: Optional[str] = None
    property_type: Optional[str] = None
    market: Optional[str] = None
    limit: Optional[int] = 50
    # Extended rich configuration from Section Builder
    section: Optional[dict[str, Any]] = None
    report_parameters: Optional[dict[str, Any]] = None
    template: Optional[dict[str, Any]] = None
    elements: Optional[list[dict[str, Any]]] = None
    chart: Optional[dict[str, Any]] = None


def _is_multi_geography_property_sub_type(property_sub_type: str | None) -> bool:
    """Check if the property_sub_type supports multi-geography report generation."""
    if not property_sub_type:
        return False
    return property_sub_type.lower() in [
        pst.lower() for pst in settings.MULTI_GEOGRAPHY_PROPERTY_SUB_TYPES
    ]


def _build_items_to_process_for_preview(
    report_params: dict,
) -> list[tuple[str | None, str | None, str | None]]:
    """Build list of (market, geo_item, geo_level) tuples for preview.
    
    Returns:
        List of (market, geo_item, geo_level) tuples
    """
    # Extract market - enforce single market
    defined_markets = report_params.get("defined_markets") or []
    if isinstance(defined_markets, str):
        defined_markets = [defined_markets]
    
    if len(defined_markets) > 1:
        logger.warning(
            "Multi-geography preview: Multiple markets provided. "
            "Using first market only: %s (ignoring: %s)",
            defined_markets[0],
            defined_markets[1:]
        )
    
    market = defined_markets[0] if defined_markets else None
    
    # Build list of geography selections
    specific_geographies: list[tuple[str, str]] = []
    
    # Add vacancy index selections
    vacancy_index = report_params.get("vacancy_index") or []
    if isinstance(vacancy_index, str):
        vacancy_index = [vacancy_index]
    for item in vacancy_index:
        if item and item != "All":
            specific_geographies.append((item, "Vacancy Index"))
    
    # Add submarket selections
    submarket = report_params.get("submarket") or []
    if isinstance(submarket, str):
        submarket = [submarket]
    for item in submarket:
        if item and item != "All":
            specific_geographies.append((item, "Submarket"))
    
    # Add district selections
    district = report_params.get("district") or []
    if isinstance(district, str):
        district = [district]
    for item in district:
        if item and item != "All":
            specific_geographies.append((item, "District"))
    
    if not specific_geographies:
        # No specific geographies selected - use market-level
        return [(market, None, None)]
    
    return [(market, item, level) for item, level in specific_geographies]


def _build_params_for_geography(
    base_params: dict,
    market: str | None,
    geo_item: str | None,
    geo_level: str | None,
) -> dict:
    """Create a copy of report params with single geography values set."""
    import copy
    params = copy.deepcopy(base_params)
    
    # Set single market
    params["defined_markets"] = [market] if market else []
    
    # Reset all geography choices
    params["vacancy_index"] = []
    params["submarket"] = []
    params["district"] = []
    
    # Set only the relevant geography choice
    if geo_item and geo_level:
        if geo_level == "Vacancy Index":
            params["vacancy_index"] = [geo_item]
        elif geo_level == "Submarket":
            params["submarket"] = [geo_item]
        elif geo_level == "District":
            params["district"] = [geo_item]
    
    return params


@router.post("/preview-chart")
async def preview_chart(payload: ChartPreviewIn, request: Request) -> dict[str, Any]:
    """Return chart data for preview. Executes payload.sql on Snowflake.

    For multi-geography property sub types, renders SQL for first valid geography
    combination and returns that data for preview.

    Response shape: { "data": [ { "quarter": str, "net_absorption": number, "vacancy_rate": number }, ... ] }
    """
    logger.info(
        "AGENTS /preview-chart request",
        method=request.method,
        url=str(request.url),
        client=getattr(request.client, "host", None),
    )
    payload_dict = payload.model_dump()
    logger.info("AGENTS /preview-chart body", payload=payload_dict)
    logger.info("[AGENTS][/preview-chart] PAYLOAD =\n" + json.dumps(payload_dict, indent=2, default=str))

    # Determine which quarter should be used for rendering SQL
    report_params = payload_dict.get("report_parameters") or {}
    payload_dict["report_parameters"] = report_params
    run_quarter_value = (report_params.get("run_quarter") or "").lower()
    actual_quarter = report_params.get("quarter")
    if run_quarter_value == "dynamic":
        actual_quarter = get_latest_complete_quarter()
        logger.info("AGENTS /preview-chart detected Dynamic run_quarter. Using latest complete quarter: %s", actual_quarter)
    elif run_quarter_value == "fixed":
        actual_quarter = report_params.get("quarter")
    if actual_quarter:
        report_params["quarter"] = actual_quarter

    # Check for multi-geography property sub type
    property_sub_type = report_params.get("property_sub_type")
    is_multi_geography = _is_multi_geography_property_sub_type(property_sub_type)
    
    if is_multi_geography:
        # Build items to process for all geography combinations
        items_to_process = _build_items_to_process_for_preview(report_params)
        logger.info(
            "AGENTS /preview-chart: Multi-geography mode with %d combinations",
            len(items_to_process)
        )
        
        # Use first geography combination for preview
        if items_to_process:
            first_market, first_geo_item, first_geo_level = items_to_process[0]
            # Modify report_params to use single geography
            modified_params = _build_params_for_geography(
                report_params, first_market, first_geo_item, first_geo_level
            )
            payload_dict["report_parameters"] = modified_params
            logger.info(
                "AGENTS /preview-chart: Using first geography for preview: market=%s, geo=%s (%s)",
                first_market, first_geo_item, first_geo_level
            )

    try:
        rendered_sql = render_sql_template(payload.sql, payload_dict)
        logger.info(f"AGENTS /preview-chart rendered-sql: \n{rendered_sql}")
    except Exception as e:
        logger.error("AGENTS /preview-chart error", error=str(e))
        raise HTTPException(status_code=400, detail="Failed to render SQL template. Please check the SQL syntax and rerun the query.")
    
    try:
        if env == "CBRE":
            data = fetch_snowflake_data(rendered_sql)
            if payload.limit and payload.limit > 0:
                data = data[: payload.limit]
        else:
            # Dummy data for non-CBRE environments
            data = [
                {"quarter": "Q1 2022", "net_absorption": 1.2, "vacancy_rate": 18.5},
                {"quarter": "Q2 2022", "net_absorption": 1.5, "vacancy_rate": 18.0},
                {"quarter": "Q3 2022", "net_absorption": -0.5, "vacancy_rate": 18.3},
                {"quarter": "Q4 2022", "net_absorption": 0.8, "vacancy_rate": 17.9},
                {"quarter": "Q1 2023", "net_absorption": 1.0, "vacancy_rate": 17.6},
                {"quarter": "Q2 2023", "net_absorption": 1.3, "vacancy_rate": 17.4},
                {"quarter": "Q3 2023", "net_absorption": -0.2, "vacancy_rate": 17.7},
                {"quarter": "Q4 2023", "net_absorption": 0.6, "vacancy_rate": 17.5},
                {"quarter": "Q1 2024", "net_absorption": 0.9, "vacancy_rate": 17.2},
                {"quarter": "Q2 2024", "net_absorption": 1.4, "vacancy_rate": 16.9},
                {"quarter": "Q3 2024", "net_absorption": -0.1, "vacancy_rate": 17.1},
                {"quarter": "Q4 2024", "net_absorption": 0.7, "vacancy_rate": 16.8},
                {"quarter": "Q1 2025", "net_absorption": 1.1, "vacancy_rate": 16.5},
                {"quarter": "Q2 2025", "net_absorption": 1.2, "vacancy_rate": 16.3},
            ]
            if payload.limit and payload.limit > 0:
                data = data[: payload.limit]
        response = {"data": data}
        logger.info("AGENTS /preview-chart response", response=response)
        return response
    except NoDataReturnedFromSnowflakeException as e:
        logger.error("AGENTS /preview-chart error", error=e.to_dict())
        raise HTTPException(status_code=404, detail="No data returned from Snowflake.")
    except Exception as e:
        logger.error("AGENTS /preview-chart error", error=str(e))
        raise HTTPException(status_code=400, detail="An error occurred while executing the query. Please check the SQL syntax and rerun the query.")


@router.get("/conversations/section/{section_id}")
async def list_conversations_for_section(
    section_id: int,
    report_id: int | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """Return conversations/messages for a report section scoped to a report."""
    if report_id is None:
        return []

    try:
        stmt = (
            select(models.AgentConversation)
            .options(selectinload(models.AgentConversation.messages))
            .where(models.AgentConversation.report_id == int(report_id))
            .where(models.AgentConversation.report_section_id == int(section_id))
            .order_by(models.AgentConversation.created_at.desc())
        )
        result = await session.execute(stmt)
        conversations = result.scalars().unique().all()

        payload: list[dict[str, Any]] = []
        for conv in conversations:
            messages = sorted(conv.messages, key=lambda m: m.created_at or datetime.min)
            payload.append(
                {
                    "id": conv.id,
                    "agent_name": conv.agent_name,
                    "created_at": conv.created_at,
                    "last_message_at": conv.last_message_at,
                    "messages": [
                        {
                            "id": msg.id,
                            "role": msg.role,
                            "content": msg.content,
                            "created_at": msg.created_at,
                        }
                        for msg in messages
                    ],
                }
            )
        logger.info(
            "AGENTS /conversations/section response section_id=%s report_id=%s count=%s",
            section_id,
            report_id,
            len(payload),
        )
        return payload
    except Exception as e:
        logger.error(
            "AGENTS /conversations/section error section_id=%s report_id=%s",
            section_id,
            report_id,
            exc_info=e,
        )
        return []


@router.get("/conversations/report-section/{report_section_id}")
async def list_conversations_for_report_section(
    report_section_id: int,
    report_id: int | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """Return conversations/messages for a specific report section."""
    try:
        stmt = (
            select(models.AgentConversation)
            .options(selectinload(models.AgentConversation.messages))
            .where(models.AgentConversation.report_section_id == int(report_section_id))
            .order_by(models.AgentConversation.created_at.desc())
        )
        if report_id is not None:
            stmt = stmt.where(models.AgentConversation.report_id == int(report_id))

        result = await session.execute(stmt)
        conversations = result.scalars().unique().all()

        payload: list[dict[str, Any]] = []
        for conv in conversations:
            messages = sorted(conv.messages, key=lambda m: m.created_at or datetime.min)
            payload.append(
                {
                    "id": conv.id,
                    "agent_name": conv.agent_name,
                    "created_at": conv.created_at,
                    "last_message_at": conv.last_message_at,
                    "messages": [
                        {
                            "id": msg.id,
                            "role": msg.role,
                            "content": msg.content,
                            "created_at": msg.created_at,
                        }
                        for msg in messages
                    ],
                }
            )
        logger.info(
            "AGENTS /conversations/report-section response report_section_id=%s count=%s",
            report_section_id,
            len(payload),
        )
        return payload
    except Exception as e:
        logger.error(
            "AGENTS /conversations/report-section error report_section_id=%s",
            report_section_id,
            exc_info=e,
        )
        return []


class TablePreviewIn(BaseModel):
    sql: Optional[str] = None
    property_type: Optional[str] = None
    market: Optional[str] = None
    limit: Optional[int] = 20
    # Extended rich configuration from Section Builder
    section: Optional[dict[str, Any]] = None
    report_parameters: Optional[dict[str, Any]] = None
    template: Optional[dict[str, Any]] = None
    elements: Optional[list[dict[str, Any]]] = None
    table: Optional[dict[str, Any]] = None


@router.post("/preview-table")
async def preview_table(payload: TablePreviewIn, request: Request) -> dict[str, Any]:
    """Return table rows for preview. Executes payload.sql on Snowflake.

    For multi-geography property sub types, renders SQL for first valid geography
    combination and returns that data for preview.

    Response shape: { "rows": [ { "metric": str, "current": str, "previous": str, "change": str }, ... ] }
    """
    logger.info(
        "AGENTS /preview-table request",
        method=request.method,
        url=str(request.url),
        client=getattr(request.client, "host", None),
    )
    payload_dict = payload.model_dump()
    logger.info("AGENTS /preview-table body", payload=payload_dict)
    logger.info(
        "[AGENTS][/preview-table] payload_dump\n%s",
        json.dumps(payload_dict, indent=2, default=str),
    )

    # Determine which quarter should be used for rendering SQL
    report_params = payload_dict.get("report_parameters") or {}
    payload_dict["report_parameters"] = report_params
    run_quarter_value = (report_params.get("run_quarter") or "").lower()
    actual_quarter = report_params.get("quarter")
    if run_quarter_value == "dynamic":
        actual_quarter = get_latest_complete_quarter()
        logger.info(
            "AGENTS /preview-table detected Dynamic run_quarter. Using latest complete quarter: %s",
            actual_quarter,
        )
    elif run_quarter_value == "fixed":
        actual_quarter = report_params.get("quarter")
    if actual_quarter:
        report_params["quarter"] = actual_quarter

    # Check for multi-geography property sub type
    property_sub_type = report_params.get("property_sub_type")
    is_multi_geography = _is_multi_geography_property_sub_type(property_sub_type)
    
    if is_multi_geography:
        # Build items to process for all geography combinations
        items_to_process = _build_items_to_process_for_preview(report_params)
        logger.info(
            "AGENTS /preview-table: Multi-geography mode with %d combinations",
            len(items_to_process)
        )
        
        # Use first geography combination for preview
        if items_to_process:
            first_market, first_geo_item, first_geo_level = items_to_process[0]
            # Modify report_params to use single geography
            modified_params = _build_params_for_geography(
                report_params, first_market, first_geo_item, first_geo_level
            )
            payload_dict["report_parameters"] = modified_params
            logger.info(
                "AGENTS /preview-table: Using first geography for preview: market=%s, geo=%s (%s)",
                first_market, first_geo_item, first_geo_level
            )

    try:
        rendered_sql = render_sql_template(payload.sql, payload_dict)
        logger.info("AGENTS /preview-table rendered-sql\n%s", rendered_sql)
    except Exception as e:
        logger.error("AGENTS /preview-table render error", exc_info=e)
        raise HTTPException(status_code=400,
                            detail="Failed to render SQL template. Please check the SQL syntax and rerun the query.")
    
    try:
        if env == "CBRE":
            rows = fetch_snowflake_data(rendered_sql)
        else:
            rows = [
                {
                    "metric": "Vacancy Rate",
                    "current": "12.8%",
                    "previous": "13.2%",
                    "change": "-0.4%",
                },
                {
                    "metric": "Avg Rent PSF",
                    "current": "$68.50",
                    "previous": "$67.80",
                    "change": "+$0.70",
                },
                {
                    "metric": "Net Absorption",
                    "current": "2.4M SF",
                    "previous": "2.2M SF",
                    "change": "+0.2M SF",
                },
                {
                    "metric": "Lease Rate",
                    "current": "2.1% QoQ",
                    "previous": "1.8% QoQ",
                    "change": "+0.3%",
                },
            ]
        if payload.limit and payload.limit > 0:
            rows = rows[: payload.limit]
        response = {"rows": rows}
        return response
    except NoDataReturnedFromSnowflakeException as e:
        logger.error("AGENTS /preview-table error", error=e.to_dict())
        raise HTTPException(status_code=404, detail="No data returned from Snowflake.")
    except Exception as e:
        logger.error("AGENTS /preview-table error", exc_info=e)
        raise HTTPException(status_code=400, detail="An error occurred while executing the query. Please check the SQL syntax and rerun the query.")


class PreviewCommentaryIn(BaseModel):
    section_name: str
    template_name: Optional[str] = None
    property_type: Optional[str] = None
    default_prompt: Optional[str] = None
    adjust_prompt: Optional[str] = None
    report_section_id: Optional[int] = None
    report_id: Optional[int] = None
    start_conversation: Optional[bool] = False
    charts: list[str] = []
    tables: list[str] = []


@router.post("/preview-commentary")
async def preview_commentary(
    payload: PreviewCommentaryIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Stub commentary preview. For now, just echoes back the received payload
    as a JSON-stringified 'text'. Later, this will call the AI agent.
    """
    import json

    # Debug: Log inbound
    try:
        logger.info(
            "AGENTS /preview-commentary request",
            method=request.method,
            url=str(request.url),
            client=getattr(request.client, "host", None),
        )
        logger.info("AGENTS /preview-commentary body", payload=payload.model_dump())
    except Exception:
        pass

    text = json.dumps(payload.model_dump(), indent=2)

    # Persist conversation + messages (first generate creates conversation)
    conversation_id: int | None = None
    try:
        # Resolve user by header; create if missing
        email = (
            request.headers.get("x-user-email")
            or request.headers.get("X-User-Email")
            or "user@local"
        )
        user = await session.scalar(
            select(models.User).where(models.User.email == email).limit(1)
        )
        if not user:
            user = models.User(email=email, username="user")
            session.add(user)
            await session.flush()

        agent_name = f"{payload.section_name} agent"
        conversation = None
        report_section: models.ReportSection | None = None

        if payload.report_section_id:
            try:
                report_section = await session.get(models.ReportSection, int(payload.report_section_id))
            except Exception:
                report_section = None

        if report_section is None and payload.report_id is not None:
            result = await session.execute(
                select(models.ReportSection)
                .where(models.ReportSection.report_id == int(payload.report_id))
                .where(
                    (models.ReportSection.key == payload.section_name)
                    | (models.ReportSection.name == payload.section_name)
                )
                .limit(1)
            )
            report_section = result.scalars().first()

        if report_section and payload.report_id is not None:
            stmt = (
                select(models.AgentConversation)
                .where(models.AgentConversation.agent_name == agent_name)
                .where(models.AgentConversation.is_active.is_(True))
                .where(models.AgentConversation.report_id == int(payload.report_id))
                .where(models.AgentConversation.report_section_id == int(report_section.id))
                .order_by(models.AgentConversation.created_at.desc())
                .limit(1)
            )
            res = await session.execute(stmt)
            conversation = res.scalars().first()

            if conversation is None and payload.start_conversation:
                conversation = models.AgentConversation(
                    report_id=int(payload.report_id),
                    report_section_id=int(report_section.id),
                    agent_name=agent_name,
                    created_by=user.id,
                    is_active=True,
                    meta={
                        "template_name": payload.template_name,
                        "property_type": payload.property_type,
                        "report_id": int(payload.report_id),
                        "created_by_label": "user",
                    },
                    last_message_at=datetime.utcnow(),
                )
                session.add(conversation)
                await session.flush()

        if conversation:
            parts: list[str] = []
            if payload.default_prompt:
                parts.append(f"Default prompt:\n{payload.default_prompt}")
            if payload.adjust_prompt:
                parts.append(f"Adjust prompt:\n{payload.adjust_prompt}")
            if not parts:
                parts.append("(no prompt provided)")
            user_content = "\n\n".join(parts)

            session.add(
                models.AgentMessage(
                    conversation_id=conversation.id,
                    role="user",
                    content=user_content,
                    payload={
                        "charts": payload.charts or [],
                        "tables": payload.tables or [],
                    },
                    created_by=user.id,
                )
            )

            session.add(
                models.AgentMessage(
                    conversation_id=conversation.id,
                    role="agent",
                    content=text,
                    payload={"format": "jsonified-selection"},
                )
            )

            conversation.last_message_at = datetime.utcnow()
            await session.commit()
            conversation_id = conversation.id
    except Exception as e:
        # Do not fail preview on persistence issues; log and continue
        logger.error("AGENTS /preview-commentary persistence error", error=str(e))
        try:
            await session.rollback()
        except Exception:
            pass

    response = {
        "section": payload.section_name,
        "text": text,
        "conversation_id": conversation_id,
    }

    try:
        logger.info("AGENTS /preview-commentary response", response=response)
    except Exception:
        pass

    return response


# Multi-Agent Workflow Endpoints
@router.post("/workflow/invoke", response_model=WorkflowResponse)
async def invoke_workflow(payload: WorkflowRequest) -> WorkflowResponse:
    """
    Invoke the multi-agent workflow to analyze input data and generate summaries.

    This endpoint processes a single section through the 4-agent pipeline:
    Summary Agent → Unit Check Agent → Data Check Agent → Validation Agent
    """
    try:
        if not workflow_service.is_ready():
            logger.error("Multi-agent workflow service is not ready")
            raise HTTPException(
                status_code=503, detail="Multi-agent workflow service is not ready"
            )

        logger.info(f"Invoking workflow for session_type: {payload.session_type}")
        result = await workflow_service.invoke_workflow(
            session_type=payload.session_type,
            input_data=payload.input_data,
            timeout=payload.timeout
        )
        logger.info("Workflow invocation completed successfully")
        return WorkflowResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Workflow invocation failed: {str(e)}"
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)


@router.post("/workflow/parallel", response_model=ParallelWorkflowResponse)
async def invoke_parallel_workflow(
    payload: ParallelWorkflowRequest,
) -> ParallelWorkflowResponse:
    """
    Invoke the parallel multi-agent workflow to analyze multiple sections concurrently.

    This endpoint uses LangGraph Send API for true parallel processing of multiple
    sections, providing significant performance improvements over sequential processing.
    """
    try:
        if not workflow_service.is_parallel_ready():
            logger.error("Parallel multi-agent workflow service is not ready")
            raise HTTPException(
                status_code=503,
                detail="Parallel multi-agent workflow service is not ready",
            )

        logger.info(f"Invoking parallel workflow for {len(payload.sections)} sections")
        result = await workflow_service.invoke_parallel_workflow(
            sections=payload.sections,
            timeout=payload.timeout
        )
        logger.info("Parallel workflow invocation completed successfully")
        return ParallelWorkflowResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Parallel workflow invocation failed: {str(e)}"
        logger.error(error_msg)
        # Return error response with proper structure
        from hello.schemas import ParallelExecutionStats
        return ParallelWorkflowResponse(
            success=False,
            section_results={},
            parallel_stats=ParallelExecutionStats(
                total_sections=len(payload.sections),
                successful_sections=0,
                failed_sections=len(payload.sections),
                total_execution_time=0.0,
                average_section_time=0.0,
                max_section_time=0.0,
                min_section_time=0.0,
            ),
            error=error_msg,
        )


@router.get("/workflow/status", response_model=WorkflowStatusResponse)
async def get_workflow_status() -> WorkflowStatusResponse:
    """
    Get the current status of both sequential and parallel multi-agent workflow services.

    Returns health information including service readiness and compilation status.
    """
    try:
        status = workflow_service.get_status()
        return WorkflowStatusResponse(**status)
    except Exception as e:
        logger.error(f"Failed to get workflow status: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get workflow status: {str(e)}"
        )

@router.post("/generate-title")
def generate_title(payload: GenerateTitleRequest) -> GenerateTitleResponse:
    """
    Generate a title for a given list of summaries.
    """
    try:
        if env == "CBRE":
            title_generation_agent = TitleGenerationAgent(state={"summaries": payload.sections_commentary})
            result = title_generation_agent.generate_title()
            title_sequence = json.loads(result.content)
            return GenerateTitleResponse(title_sequence=title_sequence)
        else:
            return GenerateTitleResponse(title_sequence={"1": "Industrial Availability Rises; Absorption Remains Negative",
                                                         "2": "Construction Pipeline Down; Deliveries Up Q/Q, Down Y/Y",
                                                         "3": "Sublease Space Expands as Availability Pressures Persist"})
    except Exception as e:
        logger.error(f"Failed to generate title: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to generate title: {str(e)}")