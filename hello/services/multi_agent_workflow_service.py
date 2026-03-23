"""
Multi-Agent Workflow Service

This service manages the lifecycle of the multi-agent workflow, providing
a singleton pattern for workflow compilation and thread-safe execution.
The workflow is compiled once during startup and reused for all requests.
"""

import asyncio
import time
from typing import Any, Dict, Optional
from threading import Lock

from hello.ml.multi_agent_workflow.agents_workflow import AgentsWorkflow
from hello.ml.multi_agent_workflow.parallel_agents_workflow import (
    ParallelAgentsWorkflow,
)
from hello.ml.multi_agent_workflow.parallel_models import SectionData, ParallelState
from hello.ml.logger import GLOBAL_LOGGER as logger
from hello.ml.exception.custom_exception import MultiAgentWorkflowException


class MultiAgentWorkflowService:
    """
    Singleton service for managing the multi-agent workflow.

    This service ensures that:
    1. Workflow is compiled once during initialization
    2. Thread-safe execution for concurrent requests
    3. Proper error handling and logging
    4. Performance optimization through workflow reuse
    """

    _instance: Optional["MultiAgentWorkflowService"] = None
    _lock = Lock()

    def __new__(cls) -> "MultiAgentWorkflowService":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        # Prevent multiple initialization of singleton
        if hasattr(self, "_initialized"):
            return

        self._initialized = True
        self._compiled_workflow = None
        self._compiled_parallel_workflow = None
        self._workflow_ready = False
        self._parallel_workflow_ready = False
        self._initialization_error: Optional[str] = None
        logger.info("MultiAgentWorkflowService instance created")

    async def initialize(self) -> bool:
        """
        Initialize and compile both single and parallel workflows during application startup.

        Returns:
            bool: True if initialization successful, False otherwise
        """
        try:
            logger.info("Initializing MultiAgentWorkflowService...")

            # Create single workflow instance
            workflow_instance = AgentsWorkflow()

            # Build and compile the single workflow graph
            logger.info("Building single workflow graph...")
            workflow_graph = workflow_instance.build_workflow()

            logger.info("Compiling single workflow...")
            self._compiled_workflow = workflow_graph.compile()

            # Create parallel workflow instance
            parallel_workflow_instance = ParallelAgentsWorkflow()

            # Build and compile the parallel workflow graph
            logger.info("Building parallel workflow graph...")
            self._compiled_parallel_workflow = (
                parallel_workflow_instance.build_parallel_workflow()
            )

            self._workflow_ready = True
            self._parallel_workflow_ready = True
            self._initialization_error = None

            logger.info(
                "MultiAgentWorkflowService initialized successfully (single + parallel)"
            )
            return True

        except Exception as e:
            error_msg = f"Failed to initialize MultiAgentWorkflowService: {str(e)}"
            logger.error(error_msg)
            MultiAgentWorkflowException.log_exception(
                e, "MultiAgentWorkflowService.initialize"
            )

            self._workflow_ready = False
            self._parallel_workflow_ready = False
            self._initialization_error = error_msg
            return False

    def is_ready(self) -> bool:
        """
        Check if the workflow service is ready to handle requests.

        Returns:
            bool: True if workflow is compiled and ready
        """
        return self._workflow_ready and self._compiled_workflow is not None

    def is_parallel_ready(self) -> bool:
        """
        Check if the parallel workflow service is ready to handle requests.

        Returns:
            bool: True if parallel workflow is compiled and ready
        """
        return (
            self._parallel_workflow_ready
            and self._compiled_parallel_workflow is not None
        )

    def get_status(self) -> Dict[str, Any]:
        """
        Get the current status of the workflow service.

        Returns:
            Dict containing service status information
        """
        return {
            "ready": self.is_ready(),
            "parallel_ready": self.is_parallel_ready(),
            "initialized": hasattr(self, "_initialized"),
            "error": self._initialization_error,
            "workflow_compiled": self._compiled_workflow is not None,
            "parallel_workflow_compiled": self._compiled_parallel_workflow is not None,
        }

    async def invoke_workflow(
        self,
        session_type: str,
        input_data: str,
        timeout: Optional[float] = 300.0,  # 5 minutes default timeout
    ) -> Dict[str, Any]:
        """
        Invoke the compiled workflow with the provided inputs.

        Args:
            session_type: Type of session (e.g., "vacancy", "leasing")
            input_data: JSON string containing the data to analyze
            timeout: Optional timeout in seconds

        Returns:
            Dict containing the workflow execution results

        Raises:
            MultiAgentWorkflowException: If workflow is not ready or execution fails
        """
        if not self.is_ready() or self._compiled_workflow is None:
            error_msg = (
                f"Workflow service not ready. Error: {self._initialization_error}"
            )
            logger.error(error_msg)
            raise MultiAgentWorkflowException(error_msg)

        start_time = time.time()

        try:
            logger.info(f"Invoking workflow for session_type: {session_type}")

            # Prepare the initial state
            initial_state = {
                "messages": [],
                "session_type": session_type,
                "input_data": input_data,
                "summary_agent_retries": 0,
                "unit_check_agent_retries": 0,
                "data_check_agent_retries": 0,
                "validation_agent_retries": 0,
                "improvement_feedback": "",
            }

            # Execute workflow with timeout and recursion limit
            config = {"recursion_limit": 50}  # Increase recursion limit to handle retry loops
            if timeout:
                result = await asyncio.wait_for(
                    asyncio.to_thread(self._compiled_workflow.invoke, initial_state, config),
                    timeout=timeout,
                )
            else:
                result = await asyncio.to_thread(
                    self._compiled_workflow.invoke, initial_state, config
                )

            execution_time = time.time() - start_time

            # Process and format the result
            formatted_result = self._format_workflow_result(result, execution_time)

            logger.info(f"Workflow completed successfully in {execution_time:.2f}s")
            return formatted_result

        except asyncio.TimeoutError:
            execution_time = time.time() - start_time
            error_msg = f"Workflow execution timed out after {timeout}s"
            logger.error(error_msg)
            raise MultiAgentWorkflowException(error_msg)

        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = f"Workflow execution failed: {str(e)}"
            logger.error(error_msg)
            MultiAgentWorkflowException.log_exception(
                e, "MultiAgentWorkflowService.invoke_workflow"
            )
            raise MultiAgentWorkflowException(error_msg)

    async def invoke_parallel_workflow(
        self,
        sections: list,
        timeout: Optional[float] = 300.0,
    ) -> Dict[str, Any]:
        """
        Invoke the compiled parallel workflow with multiple sections.

        Args:
            sections: List of section data to process in parallel
            timeout: Optional timeout in seconds per section

        Returns:
            Dict containing the parallel workflow execution results

        Raises:
            MultiAgentWorkflowException: If workflow is not ready or execution fails
        """
        if not self.is_parallel_ready() or self._compiled_parallel_workflow is None:
            error_msg = f"Parallel workflow service not ready. Error: {self._initialization_error}"
            logger.error(error_msg)
            raise MultiAgentWorkflowException(error_msg)

        start_time = time.time()

        try:
            logger.info(f"Invoking parallel workflow for {len(sections)} sections")

            # Convert section objects to SectionData objects
            section_objects = []
            for section_request in sections:
                # Convert SectionRequest to dict and then to SectionData
                if hasattr(section_request, 'model_dump'):
                    # It's a Pydantic model, convert to dict
                    section_dict = section_request.model_dump()
                elif hasattr(section_request, 'dict'):
                    # Pydantic v1 compatibility
                    section_dict = section_request.dict()
                elif isinstance(section_request, dict):
                    # Already a dict
                    section_dict = section_request
                else:
                    # Convert whatever it is to dict
                    section_dict = dict(section_request)

                section_obj = SectionData(**section_dict)
                section_objects.append(section_obj)

            # Prepare the initial parallel state
            initial_state = {
                "processing_mode": "parallel",
                "sections": [section.model_dump() for section in section_objects],
                "section_results": {},
                "completed_sections": [],
                "failed_sections": [],
                "messages": [],
                "parallel_start_time": start_time,
            }

            # Execute parallel workflow with timeout and recursion limit
            config = {"recursion_limit": 50}  # Increase recursion limit to handle retry loops
            if timeout:
                result = await asyncio.wait_for(
                    asyncio.to_thread(
                        self._compiled_parallel_workflow.invoke, initial_state, config
                    ),
                    timeout=timeout
                    * len(sections),  # Scale timeout by number of sections
                )
            else:
                result = await asyncio.to_thread(
                    self._compiled_parallel_workflow.invoke, initial_state, config
                )

            execution_time = time.time() - start_time

            # Process and format the parallel result
            formatted_result = self._format_parallel_workflow_result(
                result, execution_time
            )

            logger.info(
                f"Parallel workflow completed successfully in {execution_time:.2f}s"
            )
            return formatted_result

        except asyncio.TimeoutError:
            execution_time = time.time() - start_time
            error_msg = f"Parallel workflow execution timed out after {timeout * len(sections) if timeout else 'N/A'}s"
            logger.error(error_msg)
            raise MultiAgentWorkflowException(error_msg)

        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = f"Parallel workflow execution failed: {str(e)}"
            logger.error(error_msg)
            MultiAgentWorkflowException.log_exception(
                e, "MultiAgentWorkflowService.invoke_parallel_workflow"
            )
            raise MultiAgentWorkflowException(error_msg)

    def _format_workflow_result(
        self, result: Dict[str, Any], execution_time: float
    ) -> Dict[str, Any]:
        """
        Format the raw workflow result into a clean response structure.

        Args:
            result: Raw result from workflow execution
            execution_time: Time taken for execution in seconds

        Returns:
            Formatted result dictionary
        """
        # Extract summary result
        summary_result = None
        if "summary_result" in result:
            summary = result["summary_result"]
            if hasattr(summary, "content"):
                summary_result = summary.content
            else:
                summary_result = str(summary)

        # Extract validation results
        validation_results = {}
        for key in [
            "unit_check_result",
            "data_check_result",
            "final_validation_result",
        ]:
            if key in result:
                validation_obj = result[key]
                if hasattr(validation_obj, "content"):
                    validation_results[key] = validation_obj.content
                else:
                    validation_results[key] = str(validation_obj)

        # Extract retry counts
        retry_counts = {
            "summary_agent": result.get("summary_agent_retries", 0),
            "unit_check_agent": result.get("unit_check_agent_retries", 0),
            "data_check_agent": result.get("data_check_agent_retries", 0),
            "validation_agent": result.get("validation_agent_retries", 0),
        }

        # Format the final response
        formatted_result = {
            "success": True,
            "summary_result": summary_result,
            "workflow_approved": result.get("workflow_approved", False),
            "retry_counts": retry_counts,
            "improvement_feedback": result.get("improvement_feedback"),
            "validation_results": validation_results,
            "execution_time": round(execution_time, 2),
            "error": None,
        }

        return formatted_result

    def _format_parallel_workflow_result(
        self, result: Dict[str, Any], execution_time: float
    ) -> Dict[str, Any]:
        """
        Format the raw parallel workflow result into a clean response structure.

        Args:
            result: Raw result from parallel workflow execution
            execution_time: Total time taken for execution in seconds

        Returns:
            Formatted parallel result dictionary
        """
        try:
            # Extract section results from the workflow result
            section_results_data = result.get("section_results", {})
            parallel_stats_data = result.get("parallel_stats", {})

            # Convert section results to proper format
            formatted_section_results = {}
            successful_count = 0
            failed_count = 0

            for section_id, section_result_data in section_results_data.items():
                # Extract validation results if available
                validation_results = {}
                for key in [
                    "unit_check_result",
                    "data_check_result",
                    "final_validation_result",
                ]:
                    if key in section_result_data:
                        validation_results[key] = section_result_data[key]

                # Create formatted section response
                formatted_section_results[section_id] = {
                    "section_id": section_result_data.get("section_id", section_id),
                    "section_name": section_result_data.get(
                        "section_name", f"Section {section_id}"
                    ),
                    "success": section_result_data.get("success", False),
                    "summary_result": section_result_data.get("summary_result"),
                    "workflow_approved": section_result_data.get(
                        "workflow_approved", False
                    ),
                    "retry_counts": section_result_data.get("retry_counts", {}),
                    "improvement_feedback": section_result_data.get(
                        "improvement_feedback"
                    ),
                    "validation_results": validation_results,
                    "execution_time": section_result_data.get("execution_time", 0.0),
                    "error": section_result_data.get("error"),
                }

                if section_result_data.get("success", False):
                    successful_count += 1
                else:
                    failed_count += 1

            # Format parallel execution stats
            if parallel_stats_data:
                formatted_stats = {
                    "total_sections": parallel_stats_data.get(
                        "total_sections", len(formatted_section_results)
                    ),
                    "successful_sections": parallel_stats_data.get(
                        "successful_sections", successful_count
                    ),
                    "failed_sections": parallel_stats_data.get(
                        "failed_sections", failed_count
                    ),
                    "total_execution_time": parallel_stats_data.get(
                        "total_execution_time", execution_time
                    ),
                    "average_section_time": parallel_stats_data.get(
                        "average_section_time", 0.0
                    ),
                    "max_section_time": parallel_stats_data.get(
                        "max_section_time", 0.0
                    ),
                    "min_section_time": parallel_stats_data.get(
                        "min_section_time", 0.0
                    ),
                }
            else:
                # Fallback stats if not available
                formatted_stats = {
                    "total_sections": len(formatted_section_results),
                    "successful_sections": successful_count,
                    "failed_sections": failed_count,
                    "total_execution_time": execution_time,
                    "average_section_time": 0.0,
                    "max_section_time": 0.0,
                    "min_section_time": 0.0,
                }

            # Format the final parallel response
            formatted_result = {
                "success": failed_count == 0,  # Success if all sections succeeded
                "section_results": formatted_section_results,
                "parallel_stats": formatted_stats,
                "error": None
                if failed_count == 0
                else f"{failed_count} out of {len(formatted_section_results)} sections failed",
            }

            return formatted_result

        except Exception as e:
            logger.error(f"Error formatting parallel workflow result: {str(e)}")
            return {
                "success": False,
                "section_results": {},
                "parallel_stats": {
                    "total_sections": 0,
                    "successful_sections": 0,
                    "failed_sections": 0,
                    "total_execution_time": execution_time,
                    "average_section_time": 0.0,
                    "max_section_time": 0.0,
                    "min_section_time": 0.0,
                },
                "error": f"Error formatting parallel workflow result: {str(e)}",
            }


    def get_compiled_parallel_workflow(self):
        """
        Accessor for the compiled parallel workflow graph, intended for
        read-only streaming use by API routers.

        Returns:
            The compiled LangGraph workflow instance or None if not ready.
        """
        return self._compiled_parallel_workflow

# Global singleton instance
workflow_service = MultiAgentWorkflowService()
