from typing import Annotated, TypedDict, Any, List, Dict, Optional
import operator


# ---------------------- MAIN WORKFLOW STATE (PLAIN TYPEDDICT FOR PARALLEL SUPPORT) ----------------------


class State(TypedDict):
    """
    Main workflow state using plain TypedDict to support parallel validation.
    MessagesState inheritance was removed because it prevents parallel node execution.
    """
    # Messages field (previously inherited from MessagesState, now manual)
    messages: Annotated[List, operator.add]

    # Core workflow fields
    session_type: str
    input_data: str
    summary_result: str
    consolidated_summary_result: str
    next_node: str

    # Validation results - individual fields
    data_check_result: Any
    unit_check_result: Any
    final_validation_result: Any
    # Workflow status
    workflow_approved: bool
    # Feedback for improvements (collected from failed validations)
    improvement_feedback: str
    # Retry counters for each agent (max 3 retries per agent)
    summary_agent_retries: int
    unit_check_agent_retries: int
    data_check_agent_retries: int
    validation_agent_retries: int
    consolidated_summary_agent_retries: int

    # User feedback
    user_feedback: Optional[str]

    # Parallel validation support
    parallel_validation_results: dict  # Stores results from parallel validation execution
    all_validations_passed: bool  # Track if all parallel validations passed

    # Exception and Error Tracking
    error_occurred_in_agent: Dict[str, bool]
    max_retries_exceeded_in_agent: Dict[str, bool]
