"""
Parallel Multi-Agent Workflow using native LangGraph Send API.

This module implements parallel processing of multiple sections using LangGraph's
Send API for fan-out/fan-in patterns. Each section is processed independently
through the complete agent pipeline.
"""

import time
import asyncio
import json
from typing import List, Dict, Any, Optional, TypedDict, Annotated, Iterable
import operator
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send
from langgraph.config import get_stream_writer

from hello.ml.logger import GLOBAL_LOGGER as logger
from hello.ml.multi_agent_workflow.agents_workflow import AgentsWorkflow


# ---------------------- INPUT MODERATION ----------------------


class InputModerationError(Exception):
    """Raised when input moderation detects a security threat."""

    def __init__(self, conclusion: str, risk_score: int, reasoning: str):
        self.conclusion = conclusion
        self.risk_score = risk_score
        self.reasoning = reasoning
        super().__init__(f"Input moderation threat detected: {conclusion} (risk: {risk_score}), reasoning: {reasoning}")


# ---------------------- CONTENT FILTER ERROR ----------------------


class ContentFilterError(Exception):
    """Raised when Azure OpenAI content filter blocks the request."""

    def __init__(self, message: str, triggered_filters: list[str] = None, raw_error: dict = None):
        self.message = message
        self.triggered_filters = triggered_filters or []
        self.raw_error = raw_error or {}
        super().__init__(f"Content filter triggered: {', '.join(triggered_filters) if triggered_filters else 'unknown filter'}")


def detect_moderation_response(summary_result: str) -> dict | None:
    """
    Check if the summary result is a moderation JSON response indicating a threat.
    
    Args:
        summary_result: The output from the summary agent.
        
    Returns:
        Parsed moderation dict if threat detected, None if safe/normal summary.
    """
    if not summary_result or not isinstance(summary_result, str):
        return None
    
    text = summary_result.strip()
    
    # Check if it looks like JSON (starts with { and ends with })
    if not (text.startswith("{") and text.endswith("}")):
        return None
    
    try:
        parsed = json.loads(text)
        # Validate it has the moderation response structure
        if (
            isinstance(parsed, dict)
            and "conclusion" in parsed
            and "risk_score" in parsed
            and "reasoning" in parsed
        ):
            # Check if conclusion indicates a threat (not "safe")
            if parsed["conclusion"].lower() != "safe":
                return parsed
    except json.JSONDecodeError:
        pass
    
    return None


def detect_content_filter_response(summary_result: str) -> dict | None:
    """
    Check if the summary result is an Azure OpenAI content filter error response.
    
    This detects both:
    1. The formatted user-friendly message from wso2_openai_model_loader.py
    2. The raw JSON error format from Azure OpenAI
    
    Args:
        summary_result: The output from the summary agent.
        
    Returns:
        Dict with filter info if content filter detected, None otherwise.
        Returns: {"message": str, "triggered_filters": list, "raw_error": dict}
    """
    if not summary_result or not isinstance(summary_result, str):
        return None
    
    text = summary_result.strip()
    
    # Check for the formatted user-friendly message from wso2_openai_model_loader.py
    if "⚠️ **Content Policy Notice**" in text or "Content Policy Notice" in text:
        # Extract triggered filters if mentioned
        triggered_filters = []
        filter_names = ["hate", "jailbreak", "self_harm", "sexual", "violence"]
        for filter_name in filter_names:
            if filter_name in text.lower():
                triggered_filters.append(filter_name)
        
        return {
            "message": text,
            "triggered_filters": triggered_filters,
            "raw_error": {}
        }
    
    # Check if it's the raw JSON error format from Azure OpenAI
    if text.startswith("{") and text.endswith("}"):
        try:
            parsed = json.loads(text)
            error = parsed.get("error", {})
            
            # Check for content filter error signatures
            if (
                error.get("code") == "content_filter" or
                error.get("innererror", {}).get("code") == "ResponsibleAIPolicyViolation"
            ):
                # Extract triggered filters
                triggered_filters = []
                content_filter_result = error.get("innererror", {}).get("content_filter_result", {})
                for filter_name, filter_data in content_filter_result.items():
                    if isinstance(filter_data, dict):
                        if filter_data.get("filtered") or filter_data.get("detected"):
                            triggered_filters.append(filter_name)
                
                return {
                    "message": error.get("message", "Content filter triggered"),
                    "triggered_filters": triggered_filters,
                    "raw_error": parsed
                }
        except json.JSONDecodeError:
            pass
    
    return None

# ---------------------- SECTION SUBGRAPH STATE ----------------------

def merge_error_flags(a: Dict[str, bool] | None, b: Dict[str, bool] | None) -> Dict[str, bool]:
    if a is None:
        return b or {}
    if b is None:
        return a
    merged = dict(a)
    for k, v in b.items():
        merged[k] = merged.get(k, False) or v
    return merged

class SectionWorkflowState(TypedDict):
    """State for individual section processing through 4-agent pipeline"""

    # Section identification
    section_id: str
    section_name: str

    # Input data
    session_type: str
    input_data: list[str]
    prompt: dict

    # Agent processing state (compatible with existing agents_workflow.py)
    summary_agent_retries: int
    unit_check_agent_retries: int
    data_check_agent_retries: int
    validation_agent_retries: int
    consolidation_summary_agent_retries: int
    improvement_feedback: str
    workflow_approved: bool
    # messages: List[str]
    # Messages field (previously inherited from MessagesState, now manual)
    messages: Annotated[List, operator.add]
    all_validations_passed: bool

    # Results from each agent
    summary_results: List[Any]
    summary_result: Any
    unit_check_result: dict
    data_check_result: dict
    final_validation_result: dict

    # Execution tracking
    execution_start_time: float
    execution_time: float
    success: bool
    error: Optional[str]
    retry_counts: Dict[str, int]
    outputs: List[Any]

    # Routing
    next_node: str

    # User feedback
    user_feedback: Optional[str]

    # Exception and Error Tracking
    error_occurred_in_agent: Annotated[Dict[str, bool], merge_error_flags]
    max_retries_exceeded_in_agent: Annotated[Dict[str, bool], merge_error_flags]


# ---------------------- MAIN WORKFLOW STATE ----------------------


class ParallelWorkflowState(TypedDict):
    """Main parallel workflow state"""

    # Input sections
    sections: List[Dict[str, Any]]
    processing_mode: str
    timeout: float

    # Processing state
    outputs: Annotated[List[Any], operator.add]
    total_sections: int
    successful_sections: int
    failed_sections: int
    start_time: float
    end_time: float
    total_execution_time: float

    # Results collection
    section_results: Dict[str, Any]
    parallel_stats: Dict[str, Any]


# ---------------------- PARALLEL WORKFLOW CLASS ----------------------


class ParallelAgentsWorkflow:
    """
    Parallel multi-agent workflow using LangGraph Send API.

    Processes multiple sections concurrently through the complete agent pipeline,
    replacing the ThreadPoolExecutor workaround with native LangGraph parallel execution.
    """

    MAX_RETRIES = 4  # Maximum number of retries per agent

    def __init__(self):
        # Reuse the single-section workflow logic
        self.single_workflow = AgentsWorkflow()

    # ---------------------- SECTION SUBGRAPH NODES ----------------------

    async def _run_parallel_asyncio(self, items: Iterable[Any], worker):
        # Fire all coroutines concurrently
        loop = asyncio.get_running_loop()
        tasks = []
        for item in items:
            tasks.append(loop.run_in_executor(None, worker, item))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return results

    def _section_summary_agent(
        self, state: SectionWorkflowState
    ) -> SectionWorkflowState:
        """Summary agent node for section subgraph"""
        try:
            section_id = state["section_id"]
            retries = state["summary_agent_retries"]
            input_data_list = state.get("input_data", [])

            writer = get_stream_writer()
            if retries >= self.MAX_RETRIES:
                logger.warning(f"[{section_id}] Summary Agent - Max retries reached")
                writer({
                    "section_id": section_id,
                    "node": "summary_agent",
                    "status": "max_retries",
                    "attempt": retries,
                    "description": "Unable to generate a summary after multiple attempts. Moving forward with the process..."
                })
                return {
                    # "summary_result": "",
                    "summary_agent_retries": retries + 1,
                    "max_retries_exceeded_in_agent": {"summary_agent": True},
                }

            if retries == 0:
                writer({
                    "section_id": section_id,
                    "node": "summary_agent",
                    "status": "start",
                    "attempt": retries + 1,
                    "description": "Starting to analyze and summarize your data. This will create an initial summary of the information provided..."
                })
            else:
                writer({
                    "section_id": section_id,
                    "node": "summary_agent",
                    "status": "start",
                    "attempt": retries + 1,
                    "description": "Validation checks failed. Re-generating the summary..."
                })

            logger.info(
                f"[{section_id}] Summary Agent - Processing (attempt {retries + 1})"
            )
            # Use existing single workflow logic
            workflow_state = {
                "session_type": state["session_type"],
                "input_data": state["input_data"],
                "summary_agent_retries": retries,
                "unit_check_result": state.get("unit_check_result", {}),
                "data_check_result": state.get("data_check_result", {}),
                "final_validation_result": state.get("final_validation_result", {}),
                "messages": state.get("messages", []),
                "summary_result": state.get("summary_result", ""),
            }

            # result = self.single_workflow.summary_agent(workflow_state)
            if len(input_data_list) > 1:
                sql_prompts = state["prompt"].get("sql_prompts", [])
                workflow_state_list = []
                for index, input_data in enumerate(input_data_list):
                    state_copy = workflow_state.copy()
                    state_copy["input_data"] = input_data
                    state_copy["prompt"] = sql_prompts[index] if index < len(sql_prompts) else ""
                    workflow_state_list.append(state_copy)

                results = asyncio.run(self._run_parallel_asyncio(workflow_state_list, self.single_workflow.summary_agent))
                logger.info(f"[{section_id}] Summary Agent - Results: {results}")

                summaries_list = []
                for res in results:
                    if isinstance(res, Exception):
                        raise res
                    
                    summary_text = res.get("summary_result", "")
                    
                    # Check if summary agent returned a moderation JSON (threat detected)
                    moderation_result = detect_moderation_response(summary_text)
                    if moderation_result:
                        logger.warning(
                            f"[{section_id}] Input moderation threat detected: "
                            f"{moderation_result['conclusion']} (risk: {moderation_result['risk_score']})"
                        )
                        raise InputModerationError(
                            conclusion=moderation_result["conclusion"],
                            risk_score=moderation_result["risk_score"],
                            reasoning=moderation_result["reasoning"]
                        )
                    
                    # Check if summary agent returned a content filter error
                    content_filter_result = detect_content_filter_response(summary_text)
                    if content_filter_result:
                        logger.warning(
                            f"[{section_id}] Content filter triggered: "
                            f"{content_filter_result['triggered_filters']}"
                        )
                        raise ContentFilterError(
                            message=content_filter_result["message"],
                            triggered_filters=content_filter_result["triggered_filters"],
                            raw_error=content_filter_result["raw_error"]
                        )
                    
                    summaries_list.append(summary_text)

                writer({
                    "section_id": section_id,
                    "node": "summary_agent",
                    "status": "end",
                    "multi": True,
                    "description": "Summary generation completed successfully. Generated summaries for multiple SQL data sets."
                })
                return {
                    "summary_results": summaries_list,
                    "summary_agent_retries": retries + 1
                }
            else:
                workflow_state["user_feedback"] = state.get("user_feedback", "")
                workflow_state["prompt"] = state["prompt"].get("consolidation_prompt", "")
                results = self.single_workflow.summary_agent(workflow_state)
                final_summary = results.get("summary_result", "")
                # Check if summary agent returned a moderation JSON (threat detected)
                moderation_result = detect_moderation_response(final_summary)
                if moderation_result:
                    logger.warning(
                        f"[{section_id}] Input moderation threat detected: "
                        f"{moderation_result['conclusion']} (risk: {moderation_result['risk_score']})"
                    )
                    raise InputModerationError(
                        conclusion=moderation_result["conclusion"],
                        risk_score=moderation_result["risk_score"],
                        reasoning=moderation_result["reasoning"]
                    )
                # Check if summary agent returned a content filter error
                content_filter_result = detect_content_filter_response(final_summary)
                if content_filter_result:
                    logger.warning(
                        f"[{section_id}] Content filter triggered: "
                        f"{content_filter_result['triggered_filters']}"
                    )
                    raise ContentFilterError(
                        message=content_filter_result["message"],
                        triggered_filters=content_filter_result["triggered_filters"],
                        raw_error=content_filter_result["raw_error"]
                    )
                writer({
                    "section_id": section_id,
                    "node": "summary_agent",
                    "status": "end",
                    "multi": False,
                    "description": f"Summary generation completed successfully. Summary: '{final_summary}'"
                })
                return {
                    "summary_results": [final_summary],
                    "summary_agent_retries": retries + 1,
                }

        except InputModerationError as e:
            logger.error(f"[{section_id}] Summary Agent - Input moderation blocked: {e.conclusion}")
            writer = get_stream_writer()
            writer({
                "section_id": section_id,
                "node": "summary_agent",
                "status": "error",
                "message": f"Input moderation threat detected: {e.conclusion} (risk: {e.risk_score})",
                "description": f"Input blocked by moderation: {e.reasoning}"
            })
            raise e
            # return {
            #     "summary_results": [""],
            #     "error_occurred_in_agent": {"summary_agent": True}
            # }
        except ContentFilterError as e:
            logger.error(f"[{section_id}] Summary Agent - Content filter triggered: {e.triggered_filters}")
            writer = get_stream_writer()
            writer({
                "section_id": section_id,
                "node": "summary_agent",
                "status": "error",
                "message": f"Content filter triggered: {', '.join(e.triggered_filters) if e.triggered_filters else 'unknown filter'}",
                "description": "Your request was blocked by the content safety filter. Please modify your prompt and try again."
            })
            raise e
            # return {
            #     "summary_results": [e.message],
            #     "error_occurred_in_agent": {"summary_agent": True}
            # }
        except Exception as e:
            logger.error(f"[{section_id}] Summary Agent error: {str(e)}")
            writer = get_stream_writer()
            writer({
                "section_id": section_id,
                "node": "summary_agent",
                "status": "error",
                "message": str(e),
                "description": "Encountered an issue while generating the summary. The system will attempt to continue with the available information."
            })
            return {
                "summary_results": [""],
                "error_occurred_in_agent": {"summary_agent": True}
            }

    def _section_consolidation_summary_agent(self, state: SectionWorkflowState) -> SectionWorkflowState:
        """Consolidate the summary results from the summary agent"""
        try:
            section_id = state["section_id"]
            retries = state["consolidation_summary_agent_retries"]
            input_data_list = state.get("input_data", [])
            list_of_summary_results = state.get("summary_results", [])

            writer = get_stream_writer()
            if retries >= self.MAX_RETRIES:
                writer({
                    "section_id": section_id,
                    "node": "consolidation_summary_agent",
                    "status": "max_retries",
                    "attempt": retries,
                    "description": "Unable to consolidate summaries after multiple attempts. Proceeding with the individual summaries..."
                })
                return {
                    # "summary_result": "",
                    "consolidation_summary_agent_retries": retries + 1,
                    "max_retries_exceeded_in_agent": {"consolidation_summary_agent": True},
                }

            if retries == 0:
                writer({
                    "section_id": section_id,
                    "node": "consolidation_summary_agent",
                    "status": "start",
                    "attempt": retries + 1,
                    "description": "Combining multiple summaries into one cohesive narrative. This ensures all important information is captured in a single, comprehensive summary..."
                })
            else:
                writer({
                    "section_id": section_id,
                    "node": "consolidation_summary_agent",
                    "status": "start",
                    "attempt": retries + 1,
                    "description": "Validation checks failed. Re-generating the summary..."
                })

            logger.info(
                f"[{section_id}] Consolidation Summary Agent - Processing (attempt {retries + 1})"
            )

            if len(input_data_list) > 1:
                workflow_state = {
                    "session_type": state["session_type"],
                    "input_data": input_data_list,
                    "unit_check_result": state.get("unit_check_result", {}),
                    "data_check_result": state.get("data_check_result", {}),
                    "final_validation_result": state.get("final_validation_result", {}),
                    "summary_results": list_of_summary_results,
                    "messages": state.get("messages", []),
                    "user_feedback": state.get("user_feedback", ""),
                    "prompt": state["prompt"].get("consolidation_prompt", ""),
                    "summary_result": state.get("summary_result", ""),
                }

                results = self.single_workflow.consolidation_summary_agent(workflow_state)
                consolidated_summary = results.get("consolidated_summary_result", "")
                
                # Check if consolidation agent returned a moderation JSON (threat detected)
                moderation_result = detect_moderation_response(consolidated_summary)
                if moderation_result:
                    logger.warning(
                        f"[{section_id}] Consolidation input moderation threat detected: "
                        f"{moderation_result['conclusion']} (risk: {moderation_result['risk_score']})"
                    )
                    raise InputModerationError(
                        conclusion=moderation_result["conclusion"],
                        risk_score=moderation_result["risk_score"],
                        reasoning=moderation_result["reasoning"]
                    )
                
                # Check if consolidation agent returned a content filter error
                content_filter_result = detect_content_filter_response(consolidated_summary)
                if content_filter_result:
                    logger.warning(
                        f"[{section_id}] Consolidation content filter triggered: "
                        f"{content_filter_result['triggered_filters']}"
                    )
                    raise ContentFilterError(
                        message=content_filter_result["message"],
                        triggered_filters=content_filter_result["triggered_filters"],
                        raw_error=content_filter_result["raw_error"]
                    )
                
                writer({
                    "section_id": section_id,
                    "node": "consolidation_summary_agent",
                    "status": "end",
                    "description": f"Successfully consolidated all summaries into a unified report section. "
                                   f"The content is now ready for validation. Summary: '{consolidated_summary}'"

                })
                return {
                    "summary_result": consolidated_summary,
                    "consolidation_summary_agent_retries": retries + 1
                }
            else:
                writer({
                    "section_id": section_id,
                    "node": "consolidation_summary_agent",
                    "status": "end",
                    "description": "Single summary detected - no consolidation needed. Proceeding with the original summary."
                })
                return {
                    "summary_result": list_of_summary_results[0],
                    "consolidation_summary_agent_retries": retries + 1
                }
        except InputModerationError as e:
            logger.error(f"[{section_id}] Consolidation Summary Agent - Input moderation blocked: {e.conclusion}")
            writer = get_stream_writer()
            writer({
                "section_id": section_id,
                "node": "consolidation_summary_agent",
                "status": "error",
                "message": f"Input moderation threat detected: {e.conclusion} (risk: {e.risk_score})",
                "description": f"Input blocked by moderation: {e.reasoning}"
            })
            raise e
            # return {
            #     "summary_result": "",
            #     "error_occurred_in_agent": {"consolidation_summary_agent": True}
            # }
        except ContentFilterError as e:
            logger.error(f"[{section_id}] Consolidation Summary Agent - Content filter triggered: {e.triggered_filters}")
            writer = get_stream_writer()
            writer({
                "section_id": section_id,
                "node": "consolidation_summary_agent",
                "status": "error",
                "message": f"Content filter triggered: {', '.join(e.triggered_filters) if e.triggered_filters else 'unknown filter'}",
                "description": "Your request was blocked by the content safety filter. Please modify your prompt and try again."
            })
            raise e
            # return {
            #     "summary_result": e.message,
            #     "error_occurred_in_agent": {"consolidation_summary_agent": True}
            # }
        except Exception as e:
            logger.error(f"[{section_id}] Consolidation Summary Agent error: {str(e)}")
            writer = get_stream_writer()
            writer({
                "section_id": section_id,
                "node": "consolidation_summary_agent",
                "status": "error",
                "description": "Encountered an issue while consolidating summaries. The system will proceed with the available content."
            })
            return {
                "summary_results": [""],
                "error_occurred_in_agent": {"summary_agent": True}
            }

    def _section_unit_check_agent(
        self, state: SectionWorkflowState
    ) -> SectionWorkflowState:
        """Unit check agent node for section subgraph"""
        try:
            section_id = state["section_id"]
            retries = state["unit_check_agent_retries"]

            logger.info(
                f"[{section_id}] Unit Check Agent - Processing (attempt {retries + 1})"
            )

            writer = get_stream_writer()
            if retries >= self.MAX_RETRIES:
                logger.warning(f"[{section_id}] Unit Check Agent - Max retries reached")
                writer({
                    "section_id": section_id,
                    "node": "unit_check_agent",
                    "status": "max_retries",
                    "attempt": retries,
                    "description": "Unable to verify units after multiple attempts. The summary will be used as-is, but please review the units manually."
                })
                return {
                    "unit_check_result": {},
                    "unit_check_agent_retries": retries + 1,
                    "max_retries_exceeded_in_agent": {"unit_check_agent": True},
                }
            writer({
                "section_id": section_id,
                "node": "unit_check_agent",
                "status": "start",
                "attempt": retries + 1,
                "description": "Checking units and formatting in your summary. This ensures all numbers, percentages, and measurements are displayed correctly..."
            })

            workflow_state = {
                "summary_result": state["summary_result"],
                "session_type": state["session_type"],
                "input_data": state["input_data"],
                "unit_check_agent_retries": retries,
                "improvement_feedback": state.get("improvement_feedback", ""),
                "messages": state.get("messages", []),
            }

            result = self.single_workflow.unit_check_agent(workflow_state)

            parsed_result = json.loads(result.get("unit_check_result").content)
            status = parsed_result.get("status")
            reason = parsed_result.get("reason")
            if status == "PASS":
                writer({
                    "section_id": section_id,
                    "node": "unit_check_agent",
                    "status": "end",
                    "description": f"Unit verification {status}.\nReason: {reason}"
                })
            else:
                writer({
                    "section_id": section_id,
                    "node": "unit_check_agent",
                    "status": "error",
                    "description": f"Unit verification {status}.\nReason: {reason}"
                })
            return {
                "unit_check_result": parsed_result,
                "unit_check_agent_retries": retries + 1,
                "messages": result.get("messages", []),
            }

        except Exception as e:
            logger.error(f"[{section_id}] Unit Check Agent error: {str(e)}")
            writer = get_stream_writer()
            writer({
                "section_id": section_id,
                "node": "unit_check_agent",
                "status": "error",
                "description": "Encountered an issue during unit verification. The summary will proceed without unit validation - please review units manually."
            })
            return {
                "unit_check_result": {},
                "error_occurred_in_agent": {"unit_check_agent": True}
            }

    def _section_data_check_agent(
        self, state: SectionWorkflowState
    ) -> SectionWorkflowState:
        """Data check agent node for section subgraph"""
        try:
            section_id = state["section_id"]
            retries = state["data_check_agent_retries"]

            logger.info(
                f"[{section_id}] Data Check Agent - Processing (attempt {retries + 1})"
            )

            if retries >= self.MAX_RETRIES:
                logger.warning(f"[{section_id}] Data Check Agent - Max retries reached")
                writer = get_stream_writer()
                writer({
                    "section_id": section_id,
                    "node": "data_check_agent",
                    "status": "max_retries",
                    "attempt": retries,
                    "description": "Unable to verify data accuracy after multiple attempts. Please review the data points in your summary manually."
                })
                return {
                    "data_check_result": "",
                    "data_check_agent_retries": retries + 1,
                    "max_retries_exceeded_in_agent": {"data_check_agent": True},
                }
            writer = get_stream_writer()
            writer({
                "section_id": section_id,
                "node": "data_check_agent",
                "status": "start",
                "attempt": retries + 1,
                "description": "Verifying data accuracy in your summary. This step ensures all facts and figures match the source data..."
            })
            workflow_state = {
                "summary_result": state["summary_result"],
                "input_data": state["input_data"],
                "session_type": state["session_type"],
                "data_check_agent_retries": retries,
                "improvement_feedback": state.get("improvement_feedback", ""),
                "messages": state.get("messages", []),
            }

            result = self.single_workflow.data_check_agent(workflow_state)

            parsed_result = json.loads(result.get("data_check_result").content)
            status = parsed_result.get("status")
            reason = parsed_result.get("reason")
            if status == "PASS":
                writer({
                    "section_id": section_id,
                    "node": "data_check_agent",
                    "status": "end",
                    "description": f"Data verification {status}.\nReason: {reason}"
                })
            else:
                writer({
                    "section_id": section_id,
                    "node": "data_check_agent",
                    "status": "error",
                    "description": f"Data verification {status}.\nReason: {reason}"
                })
            return {
                "data_check_result": parsed_result,
                "data_check_agent_retries": retries + 1,
                "messages": result.get("messages", []),
            }

        except Exception as e:
            logger.error(f"[{section_id}] Data Check Agent error: {str(e)}")
            writer = get_stream_writer()
            writer({
                "section_id": section_id,
                "node": "data_check_agent",
                "status": "error",
                "description": "Encountered an issue during data verification. The summary will proceed, but please verify the data points manually."
            })
            return {
                "data_check_result": {},
                "error_occurred_in_agent": {"data_check_agent": True}
            }

    def _section_validation_agent(
        self, state: SectionWorkflowState
    ) -> SectionWorkflowState:
        """Validation agent node for section subgraph"""
        try:
            section_id = state["section_id"]
            retries = state["validation_agent_retries"]

            logger.info(
                f"[{section_id}] Validation Agent - Processing (attempt {retries + 1})"
            )

            if retries >= self.MAX_RETRIES:
                logger.warning(f"[{section_id}] Validation Check Agent - Max retries reached")
                writer = get_stream_writer()
                writer({
                    "section_id": section_id,
                    "node": "validation_check_agent",
                    "status": "max_retries",
                    "attempt": retries,
                    "description": "Unable to complete final validation after multiple attempts. The summary will be provided as-is for your review."
                })
                return {
                    "final_validation_result": "",
                    "validation_agent_retries": retries + 1,
                    "max_retries_exceeded_in_agent": {"validation_check_agent": True},
                }
            writer = get_stream_writer()
            writer({
                "section_id": section_id,
                "node": "validation_check_agent",
                "status": "start",
                "attempt": retries + 1,
                "description": "Performing final quality check on your summary. This ensures the content is complete, accurate, and ready for use..."
            })
            workflow_state = {
                "summary_result": state["summary_result"],
                "input_data": state["input_data"],
                "unit_check_result": state.get("unit_check_result", {}),
                "data_check_result": state.get("data_check_result", {}),
                "session_type": state["session_type"],
                "validation_agent_retries": retries,
                "improvement_feedback": state.get("improvement_feedback", ""),
                "messages": state.get("messages", []),
                "user_feedback": state.get("user_feedback", ""),
                "prompt": state["prompt"].get("consolidation_prompt", ""),
            }

            result = self.single_workflow.validation_agent(workflow_state)
            execution_time = time.time() - state["execution_start_time"]

            parsed_result = json.loads(result.get("final_validation_result").content)
            status = parsed_result.get("status")
            reason = parsed_result.get("reason")
            if status == "PASS":
                writer({
                    "section_id": section_id,
                    "node": "validation_check_agent",
                    "status": "end",
                    "description": f"Validation {status}.\nReason: {reason}"
                })
            else:
                writer({
                    "section_id": section_id,
                    "node": "validation_check_agent",
                    "status": "error",
                    "description": f"Validation {status}.\nReason: {reason}"
                })
            logger.info(
                f"[{section_id}] Validation Agent - {'APPROVED' if status == "PASS" else 'REJECTED'}"
            )
            return {
                "final_validation_result": parsed_result,
                "validation_agent_retries": retries + 1,
                "execution_time": execution_time,
            }

        except Exception as e:
            logger.error(f"[{section_id}] Validation Agent error: {str(e)}")
            writer = get_stream_writer()
            writer({
                "section_id": section_id,
                "node": "validation_check_agent",
                "status": "error",
                "description": "Encountered an issue during final validation. The summary will be provided for your review without full validation."
            })
            return {
                "final_validation_result": {},
                "error_occurred_in_agent": {"validation_check_agent": True}
            }

    def _section_parallel_validation_aggregator(self, state: SectionWorkflowState) -> SectionWorkflowState:
        """Aggregator node to collect validation results from all agents"""
        try:
            section_id = state["section_id"]
            logger.info(f"[{section_id}] Aggregator - Collecting validation results")
            result = self.single_workflow.parallel_validation_aggregator(state)
            is_workflow_approved = result.get("workflow_approved", False)

            writer = get_stream_writer()
            writer({
                "section_id": section_id,
                "node": "reviewing_all_agents_check",
                "status": "end" if is_workflow_approved else "error",
                "description": f"Quality checks completed. {'All validations passed! Your summary is ready.' if is_workflow_approved else 'Some checks identified areas for improvement. The system will refine your summary.'}"
            })

            next_node = "consolidation_summary_agent" if len(state.get("input_data", [])) > 1 else "summary_agent"
            if is_workflow_approved:
                next_node = "completion"

            if (is_workflow_approved == False) and (state.get("error_occurred_in_agent") or state.get("max_retries_exceeded_in_agent")):
                return {
                    "next_node": "completion",
                    "workflow_approved": is_workflow_approved,
                    "success": is_workflow_approved,
                }
            return {
                "all_validations_passed": is_workflow_approved,
                "next_node": next_node,
                "workflow_approved": is_workflow_approved,
                "success": is_workflow_approved,
            }
        except Exception as e:
            logger.error(f"[{section_id}] Aggregator error: {str(e)}")
            return {
                "all_validations_passed": False,
                "next_node": "completion",
                "workflow_approved": False,
                "error": str(e),
                "success": False,
            }

    def _create_section_result_output(
        self,
        state: SectionWorkflowState,
        is_approved: bool,
        execution_time: float,
        error: str = None,
    ) -> Dict[str, Any]:
        """Create standardized section result output"""
        return {
            "section_id": state["section_id"],
            "section_name": state["section_name"],
            "success": is_approved,
            "summary_result": state.get("summary_result"),
            "workflow_approved": is_approved,
            "retry_counts": {
                "summary_agent": state.get("summary_agent_retries", 0),
                "unit_check_agent": state.get("unit_check_agent_retries", 0),
                "data_check_agent": state.get("data_check_agent_retries", 0),
                "validation_agent": state.get("validation_agent_retries", 0),
            },
            "execution_time": execution_time,
            "validation_results": {
                "unit_check_result": state.get("unit_check_result"),
                "data_check_result": state.get("data_check_result"),
                "final_validation_result": state.get("final_validation_result"),
            },
            "error": error,
        }

    # ---------------------- CONDITIONAL EDGE ROUTING ----------------------
    #
    # def _route_from_unit_check(self, state: SectionWorkflowState) -> str:
    #     """Route from unit check agent based on next_node"""
    #     return state.get("next_node", "__end__")
    #
    # def _route_from_data_check(self, state: SectionWorkflowState) -> str:
    #     """Route from data check agent based on next_node"""
    #     return state.get("next_node", "__end__")
    #
    # def _route_from_summary(self, state: SectionWorkflowState) -> str:
    #     """Route from summary agent based on next_node"""
    #     return state.get("next_node", "__end__")
    #
    # def _route_from_validation(self, state: SectionWorkflowState) -> str:
    #     """Route from validation based on result"""
    #     validation_result = state.get("final_validation_result", "")
    #
    #     if "PASS" in str(validation_result).upper():
    #         return "completion"
    #     else:
    #         # Check if we've reached max retries
    #         if state.get("validation_agent_retries", 0) >= self.MAX_RETRIES:
    #             return "completion"
    #         return "summary_agent"  # Retry from summary

    def _route_from_aggregator(self, state: SectionWorkflowState) -> str:
        """
        Route from aggregator based on validation results.
        Returns: "consolidation_summary_agent" if retry needed, "completion" if complete
        """
        try:
            next_node = state.get("next_node", "completion")
            all_passed = state.get("all_validations_passed", False)
            current_retries = state.get("consolidation_summary_agent_retries", 0)

            # Validate the routing decision
            valid_routes = ["completion", "consolidation_summary_agent", "summary_agent"]
            if next_node not in valid_routes:
                logger.warning(
                    f"Invalid route '{next_node}' from aggregator, defaulting to completion"
                )
                next_node = "completion"

            logger.info(
                f"Routing from aggregator to: {next_node} (all_passed: {all_passed}, retry: {current_retries}/{self.MAX_RETRIES})"
            )
            return next_node
        except Exception as e:
            logger.error(f"Error in route_from_aggregator: {e}")
            return "completion"  # Safe fallback


    def _route_check_if_feedback_provided(self, state: SectionWorkflowState) -> str:
        input_data = state.get("input_data", [])
        feedback_provided = state.get("user_feedback", False)
        next_node = "summary_agent"
        if len(input_data) > 1 and feedback_provided:
            next_node = "consolidation_summary_agent"
        return next_node


    # ---------------------- MAIN WORKFLOW NODES ----------------------

    def initialize_processing(
        self, state: ParallelWorkflowState
    ) -> ParallelWorkflowState:
        """Initialize parallel processing state"""
        sections = state.get("sections", [])

        logger.info(
            f"Initializing Send API parallel processing for {len(sections)} sections"
        )

        writer = get_stream_writer()
        writer({
            "node": "Initialized_and_triggered_workflow_agent",
            "description": f"Starting to process your report with {len(sections)} section{'s' if len(sections) != 1 else ''}.",
            "status": "end"
        })

        return {
            "total_sections": len(sections),
            "successful_sections": 0,
            "failed_sections": 0,
            "start_time": time.time(),
            "section_results": {},
            "parallel_stats": {},
        }

    def dispatch_sections_for_parallel_processing(self, state: ParallelWorkflowState):
        """
        CRITICAL: This function returns Send objects for LangGraph to route sections
        to parallel section_worker nodes.

        This is a conditional edge function - it MUST return Send objects, not state updates.
        """
        sections = state.get("sections", [])

        if not sections:
            logger.warning("No sections to process")
            return []

        logger.info(f"Dispatching {len(sections)} sections via Send API")

        # writer = get_stream_writer()
        # writer({
        #     "stage": "dispatch_start",
        #     "count": len(sections),
        #     "description": f"Preparing to process {len(sections)} section{'s' if len(sections) != 1 else ''} in parallel. This approach significantly reduces the total processing time."
        # })

        sends = []
        for section_data in sections:
            # Prepare section state for the subgraph
            if section_data.get("feedback") is not None:
                user_feedback = section_data["feedback"]
            else:
                user_feedback = ""
            section_state = {
                "section_id": section_data["section_id"],
                "section_name": section_data["section_name"],
                "session_type": section_data["session_type"],
                "input_data": section_data["input_data"],
                "prompt": section_data.get("prompt", ""),
                "user_feedback": user_feedback,
                # Initialize agent retry counters
                "summary_agent_retries": 0,
                "unit_check_agent_retries": 0,
                "data_check_agent_retries": 0,
                "validation_agent_retries": 0,
                "consolidation_summary_agent_retries": 0,
                # Initialize state
                "improvement_feedback": "",
                "workflow_approved": False,
                "messages": [],
                "execution_start_time": time.time(),
                "success": False,
                "error": None,
                "next_node": "summary_agent",
            }

            send_obj = Send("section_worker", section_state)
            sends.append(send_obj)

            logger.info(f"   Created Send object for: {section_data['section_id']}")
            # writer({
            #     "stage": "dispatch",
            #     "section_id": section_data["section_id"],
            #     "section_name": section_data["section_name"],
            #     "description": f"Starting analysis for '{section_data['section_name']}'. This section will be processed through multiple quality checks."
            # })

        logger.info(f"Returning {len(sends)} Send objects for parallel execution")
        # writer({
        #     "stage": "dispatch_end",
        #     "count": len(sends),
        #     "description": f"All {len(sends)} section{'s' if len(sends) != 1 else ''} are now being processed simultaneously. You'll see updates as each section progresses."
        # })
        return sends

    def finalize_results(self, state: ParallelWorkflowState) -> ParallelWorkflowState:
        """Finalize and aggregate results from all sections"""
        outputs = state.get("outputs", [])
        end_time = time.time()
        start_time = state.get("start_time", end_time)
        total_execution_time = end_time - start_time

        logger.info(f"Finalizing results for {len(outputs)} sections")

        # Aggregate section results
        section_results = {}
        successful_sections = 0
        failed_sections = 0
        execution_times = []

        for output in outputs:
            section_id = output["section_id"]
            section_results[section_id] = output

            if output.get("success", False):
                successful_sections += 1
            else:
                failed_sections += 1

            execution_times.append(output.get("execution_time", 0))

        # Calculate statistics
        total_sections = len(outputs)
        average_section_time = (
            sum(execution_times) / len(execution_times) if execution_times else 0
        )
        max_section_time = max(execution_times) if execution_times else 0
        min_section_time = min(execution_times) if execution_times else 0

        parallel_stats = {
            "total_sections": total_sections,
            "successful_sections": successful_sections,
            "failed_sections": failed_sections,
            "total_execution_time": total_execution_time,
            "average_section_time": average_section_time,
            "max_section_time": max_section_time,
            "min_section_time": min_section_time,
        }

        logger.info(
            f"Parallel processing complete: {successful_sections}/{total_sections} successful"
        )

        # writer = get_stream_writer()
        # writer({
        #     "node": "completion",
        #     "status": "end",
        #     "description": f"Report generation completed! Successfully processed {successful_sections} out of {total_sections} section{'s' if total_sections != 1 else ''}. Total time: {total_execution_time:.1f} seconds."
        # })
        

        return {
            "section_results": section_results,
            "parallel_stats": parallel_stats,
            "successful_sections": successful_sections,
            "failed_sections": failed_sections,
            "total_execution_time": total_execution_time,
            "end_time": end_time,
        }

    def _section_completion(self, state: SectionWorkflowState) -> SectionWorkflowState:
        """Complete section processing and format results for state collection"""
        section_id = state["section_id"]
        section_name = state.get("section_name", f"Section {section_id}")

        # Calculate execution time if not provided
        start_time = state.get("execution_start_time", time.time())
        execution_time = time.time() - start_time

        # Determine success based on workflow completion
        success = state.get("workflow_approved", False)

        error = ""
        if state.get("error_occurred_in_agent"):
            error = "We encountered an issue while processing this section. Please try again by clicking the generate button. If the problem persists, contact support for assistance."
            
        elif state.get("max_retries_exceeded_in_agent"):
            error = "We were unable to complete this section after multiple attempts. This may be due to complex data or formatting requirements. Please try again with a simpler request or different parameters. If you continue to experience issues, contact support for assistance."

        # Format the section result for the state reducer
        section_result = {
            "section_id": section_id,
            "section_name": section_name,
            "success": success,
            "summary_result": state.get("summary_result"),
            "unit_check_result": state.get("unit_check_result"),
            "data_check_result": state.get("data_check_result"),
            "final_validation_result": state.get("final_validation_result"),
            "workflow_approved": success,
            "retry_counts": {
                "summary_agent": state.get("summary_agent_retries", 0),
                "unit_check_agent": state.get("unit_check_agent_retries", 0),
                "data_check_agent": state.get("data_check_agent_retries", 0),
                "validation_agent": state.get("validation_agent_retries", 0),
            },
            "improvement_feedback": state.get("improvement_feedback"),
            "execution_time": execution_time,
            "error": error,
        }

        logger.info(f"[{section_id}] Section completed - Success: {success}")
        # writer = get_stream_writer()
        # writer({
        #     "section_id": section_id,
        #     "node": "completion",
        #     "status": "end",
        #     "description": f"Section '{section_name}' processing {'completed successfully' if success else 'finished with issues'}. {'The content is ready for your review.' if success else 'Please review and consider making adjustments.'}"
        # })

        # Return the result that will be collected by the state reducer
        return {"outputs": [section_result]}

    # ---------------------- WORKFLOW BUILDERS ----------------------

    def build_section_subgraph(self) -> StateGraph:
        """Build the section subgraph for processing individual sections"""
        section_builder = StateGraph(SectionWorkflowState)

        # Add agent nodes
        section_builder.add_node("summary_agent", self._section_summary_agent)
        section_builder.add_node("consolidation_summary_agent", self._section_consolidation_summary_agent)
        section_builder.add_node("unit_check_agent", self._section_unit_check_agent)
        section_builder.add_node("data_check_agent", self._section_data_check_agent)
        section_builder.add_node("validation_agent", self._section_validation_agent)
        section_builder.add_node("aggregator", self._section_parallel_validation_aggregator)
        section_builder.add_node("completion", self._section_completion)

        # Set entry point
        # section_builder.add_edge(START, "summary_agent")

        # Conditional Entry Point
        section_builder.add_conditional_edges(START,
                                              self._route_check_if_feedback_provided,
                                              {"consolidation_summary_agent": "consolidation_summary_agent",
                                               "summary_agent": "summary_agent"})

        section_builder.add_edge("summary_agent", "consolidation_summary_agent")

        # FANOUT: summary_agent → 3 validators in parallel (simple edges)
        section_builder.add_edge("consolidation_summary_agent", "unit_check_agent")
        section_builder.add_edge("consolidation_summary_agent", "data_check_agent")
        section_builder.add_edge("consolidation_summary_agent", "validation_agent")

        # FAN-IN: All 3 validators → aggregator (simple edges)
        section_builder.add_edge("unit_check_agent", "aggregator")
        section_builder.add_edge("data_check_agent", "aggregator")
        section_builder.add_edge("validation_agent", "aggregator")

        # Aggregator routing (conditional)
        section_builder.add_conditional_edges(
            "aggregator",
            self._route_from_aggregator,
            {
                "consolidation_summary_agent": "consolidation_summary_agent",
                "summary_agent": "summary_agent",
                "completion": "completion",
            },
        )
        # Complete the section and return results
        section_builder.add_edge("completion", END)

        logger.info("Workflow built successfully with simple fanout/fan-in")
        return section_builder

    def build_parallel_workflow(self):
        """Build the main parallel workflow with Send API routing"""
        logger.info("🏗️  Building Send API parallel workflow")

        # Build section subgraph
        section_subgraph = self.build_section_subgraph()

        # Create main workflow builder
        main_builder = StateGraph(ParallelWorkflowState)

        # Add main workflow nodes
        main_builder.add_node("initialize", self.initialize_processing)
        main_builder.add_node("section_worker", section_subgraph.compile())
        main_builder.add_node("finalize", self.finalize_results)

        # Add edges
        main_builder.add_edge(START, "initialize")

        # CRITICAL: This conditional edge returns Send objects for parallel processing
        main_builder.add_conditional_edges(
            "initialize",
            self.dispatch_sections_for_parallel_processing,
            {"section_worker": "section_worker"},
        )

        main_builder.add_edge("section_worker", "finalize")
        main_builder.add_edge("finalize", END)

        logger.info("Send API parallel workflow built successfully")
        return main_builder.compile()


# ---------------------- FACTORY FUNCTION FOR COMPATIBILITY ----------------------


def create_parallel_workflow_with_send_api() -> ParallelAgentsWorkflow:
    """Factory function to create a parallel workflow instance"""
    return ParallelAgentsWorkflow()


if __name__ == "__main__":
    """Test the Send API parallel workflow directly"""
    logger.info("🧪 TESTING SEND API PARALLEL WORKFLOW")
    logger.info("=" * 60)

    try:
        # Create workflow
        workflow = ParallelAgentsWorkflow()
        graph = workflow.build_parallel_workflow()

        # Test data
        test_input = {
            "sections": [
                {
                    "section_id": "test_vacancy",
                    "section_name": "Test Vacancy Analysis",
                    "session_type": "vacancy",
                    "input_data": ['[{"Quarter": "Q2 2025", "Overall": 18.29}]'],
                    "prompt": {"consolidation_prompt": "summarize the data"},
                }
            ],
            "processing_mode": "parallel",
            "timeout": 300.0,
            "outputs": [],
            "total_sections": 0,
            "successful_sections": 0,
            "failed_sections": 0,
            "start_time": 0.0,
            "end_time": 0.0,
            "total_execution_time": 0.0,
            "section_results": {},
            "parallel_stats": {},
        }

        logger.info(f"Testing with {len(test_input['sections'])} section(s)")

        # Execute
        start_time = time.time()
        result = graph.invoke(test_input)
        execution_time = time.time() - start_time

        logger.info(f"Execution time: {execution_time:.2f}s")
        logger.info(f"Results: {result.get('parallel_stats', {})}")
        logger.info("Send API test completed successfully!")

        ## Streaming example with intermediate states (https://docs.langchain.com/oss/python/langgraph/streaming#values)
        final_state = None
        for chunk, stream_mode, state in graph.stream(test_input, stream_mode=["custom", "values"], subgraphs=True):
            if chunk:
                logger.info(f"\033[93mChunk: {chunk}\033[0m")  # Yellow color
            if stream_mode == "custom":
                # logger.info(f"\033[96mCustom Stream: {state}\033[0m")  # Cyan color
                logger.info(f"\033[96mNotification: {state}\033[0m")
            elif stream_mode == "values":
                final_state = state
                logger.info(f"\033[92mIntermediate State Update: {state}\033[0m")  # Green color
        import json

        logger.info(f"Final State:\n {final_state}")

    except Exception as e:
        logger.info(f"Test failed: {str(e)}")
        import traceback

        traceback.logger.info_exc()
