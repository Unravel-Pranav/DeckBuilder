"""
Parallel processing models for multi-agent workflow.

This module defines the data structures needed for parallel section processing
using LangGraph's Send API.
"""

from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field
from langgraph.graph import MessagesState


class SectionData(BaseModel):
    """
    Data structure for individual section processing.

    Each section contains its own input data and processing parameters.
    """

    section_id: str = Field(description="Unique identifier for the section")
    section_name: str = Field(description="Human-readable name for the section")
    session_type: str = Field(
        description="Type of session (e.g., 'vacancy', 'leasing')"
    )
    input_data: List[str] = Field(description="List of strings containing the data to analyze")
    prompt: dict = Field(
        default=None, description="Custom prompt for this section"
    )
    feedback: Optional[str] = Field(
        default=None, description="Feedback from previous processing"
    )

    class Config:
        frozen = True  # Immutable for thread safety


class SectionResult(BaseModel):
    """
    Result of processing a single section through the multi-agent workflow.
    """

    section_id: str = Field(description="Unique identifier for the section")
    section_name: str = Field(description="Human-readable name for the section")
    success: bool = Field(description="Whether the section processing succeeded")

    # Agent results
    summary_result: Optional[str] = Field(default=None, description="Generated summary")
    unit_check_result: Optional[str] = Field(
        default=None, description="Unit validation result"
    )
    data_check_result: Optional[str] = Field(
        default=None, description="Data validation result"
    )
    final_validation_result: Optional[str] = Field(
        default=None, description="Final validation result"
    )

    # Processing metadata
    workflow_approved: bool = Field(
        default=False, description="Whether workflow was approved"
    )
    retry_counts: Dict[str, int] = Field(
        default_factory=dict, description="Retry counts per agent"
    )
    improvement_feedback: Optional[str] = Field(
        default=None, description="Collected feedback"
    )
    execution_time: float = Field(description="Time taken for this section")
    error: Optional[str] = Field(default=None, description="Error message if failed")


class ParallelExecutionStats(BaseModel):
    """
    Statistics for parallel execution of multiple sections.
    """

    total_sections: int = Field(description="Total number of sections processed")
    successful_sections: int = Field(description="Number of sections that succeeded")
    failed_sections: int = Field(description="Number of sections that failed")
    total_execution_time: float = Field(description="Total parallel execution time")
    average_section_time: float = Field(description="Average time per section")
    max_section_time: float = Field(description="Longest section processing time")
    min_section_time: float = Field(description="Shortest section processing time")


class ParallelState(MessagesState):
    """
    Enhanced state for parallel multi-agent workflow processing.

    Extends MessagesState to support parallel processing of multiple sections
    while maintaining compatibility with existing single-section processing.
    """

    # Original single-section fields (for backwards compatibility)
    session_type: str
    input_data: str
    summary_result: str
    next_node: str

    # Single section validation results
    unit_check_result: str
    data_check_result: str
    final_validation_result: str

    # Single section workflow status
    workflow_approved: bool
    improvement_feedback: str

    # Single section retry counters
    summary_agent_retries: int
    unit_check_agent_retries: int
    data_check_agent_retries: int
    validation_agent_retries: int

    # Parallel processing fields
    sections: List[SectionData] = Field(
        default_factory=list, description="Sections to process in parallel"
    )
    section_results: Dict[str, SectionResult] = Field(
        default_factory=dict, description="Results per section"
    )
    completed_sections: List[str] = Field(
        default_factory=list, description="List of completed section IDs"
    )
    failed_sections: List[str] = Field(
        default_factory=list, description="List of failed section IDs"
    )
    processing_mode: str = Field(
        default="single", description="Processing mode: 'single' or 'parallel'"
    )

    # Parallel execution metadata
    parallel_start_time: Optional[float] = Field(
        default=None, description="Start time of parallel processing"
    )
    parallel_stats: Optional[ParallelExecutionStats] = Field(
        default=None, description="Execution statistics"
    )


class SectionProcessingMessage(BaseModel):
    """
    Message structure for section processing in parallel workflow.

    Used with LangGraph Send API to dispatch sections to parallel processors.
    """

    section: SectionData = Field(description="Section data to process")
    workflow_config: Dict[str, Any] = Field(
        default_factory=dict, description="Workflow configuration"
    )

    class Config:
        frozen = True  # Immutable for thread safety
