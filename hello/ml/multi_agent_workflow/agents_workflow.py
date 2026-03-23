import sys
import time
import json

from langgraph.graph import END, START, StateGraph

from hello.ml.agents.data_check_agent import DataCheckAgent
from hello.ml.agents.session_summary_agent import SessionSummaryAgent
from hello.ml.agents.unit_check_agent import UnitCheckAgent
from hello.ml.agents.validation_agent import ValidationAgent
from hello.ml.agents.consolidation_summary_agent import ConsolidationSummaryAgent
from hello.ml.exception.custom_exception import MultiAgentWorkflowException
from hello.ml.logger import GLOBAL_LOGGER as logger
from hello.ml.multi_agent_workflow.state import State
from hello.services.config import settings


class AgentsWorkflow:
    """
    AgentsWorkflow class that orchestrates the multi-agent workflow.
    """

    MAX_RETRIES = 3  # Maximum number of retries per agent

    def __init__(self):
        pass

    def _initialize_retry_counters(self, state: State) -> None:
        """
        Initialize retry counters and feedback if they don't exist.
        """
        # Initialize retry counters with explicit checks
        state.setdefault("summary_agent_retries", 0)
        state.setdefault("unit_check_agent_retries", 0)
        state.setdefault("data_check_agent_retries", 0)
        state.setdefault("validation_agent_retries", 0)
        # Initialize improvement feedback
        state.setdefault("improvement_feedback", "")

    def _collect_feedback(
        self, state: State, agent_name: str, validation_content: str
    ) -> None:
        """
        Collect feedback from failed validations to improve the summary.
        Expects JSON format with status and reason fields.
        """
        import json

        try:
            # Try to parse as JSON first
            validation_json = json.loads(validation_content)
            status = validation_json.get("status", "").upper()
            reason = validation_json.get("reason", "")

            if status == "FAIL" and reason:
                # Add to existing feedback with agent context
                existing_feedback = state.get("improvement_feedback", "")
                new_feedback = f"\n{agent_name} Issues: {reason}"

                if existing_feedback:
                    state["improvement_feedback"] = existing_feedback + new_feedback
                else:
                    state["improvement_feedback"] = new_feedback.strip()

                logger.info(
                    f"Collected JSON feedback from {agent_name}: {reason[:100]}..."
                )

        except json.JSONDecodeError:
            # Fallback to old text parsing if JSON parsing fails
            if "FAIL" in validation_content.upper():
                # Extract the feedback portion after FAIL
                feedback_part = validation_content
                if "FAIL" in validation_content:
                    # Try to extract detailed feedback after FAIL
                    parts = validation_content.split("FAIL", 1)
                    if len(parts) > 1:
                        feedback_part = parts[1].strip()

                # Add to existing feedback with agent context
                existing_feedback = state.get("improvement_feedback", "")
                new_feedback = f"\n{agent_name} Issues: {feedback_part}"

                if existing_feedback:
                    state["improvement_feedback"] = existing_feedback + new_feedback
                else:
                    state["improvement_feedback"] = new_feedback.strip()

                logger.info(
                    f"Collected text feedback from {agent_name}: {feedback_part[:100]}..."
                )

    def _check_validation_status(self, validation_content: dict) -> bool:
        """
        Standardized validation status check using base agent logic.
        Returns True if validation passed, False if failed.
        """
        status = str(validation_content.get("status", "")).upper()
        return status == "PASS"

    def summary_agent(self, state: State) -> State:
        """
        Summary agent that generates a summary of the input data.
        """
        start_time = time.time()
        try:
            self._initialize_retry_counters(state)

            current_retries = state.get("summary_agent_retries", 0)
            logger.info(
                f"Summary agent called (Loop #{current_retries + 1}, Attempt {current_retries + 1}/{self.MAX_RETRIES + 1})"
            )

            # Increment retry counter
            state["summary_agent_retries"] = current_retries + 1

            # Calling the SessionSummaryAgent
            summary = SessionSummaryAgent(dict(state)).generate_summary()

            # Handle both str and list content types
            if isinstance(summary.content, str):
                state["summary_result"] = summary.content.strip()

            # Reset all validation agent retries when coming from summary agent
            state["unit_check_agent_retries"] = 0
            state["data_check_agent_retries"] = 0
            state["validation_agent_retries"] = 0

            # Clear improvement feedback after successful summary generation
            # to start fresh for the next iteration
            if current_retries == 1:  # First attempt, clear any old feedback
                state["improvement_feedback"] = ""

            # Log execution time
            execution_time = time.time() - start_time
            logger.info(f"Summary Agent completed in {execution_time:.2f}s (Loop #{current_retries + 1})")

            # No need to set next_node - fanout edges will automatically trigger all 3 validators
            return state
        except Exception as e:
            MultiAgentWorkflowException.log_exception(e, "summary_agent")
            raise e


    def consolidation_summary_agent(self, state: State) -> State:
        """Consolidate the summary results from the summary agent"""
        start_time = time.time()
        try:
            self._initialize_retry_counters(state)

            current_retries = state.get("consolidated_summary_agent_retries", 0)
            logger.info(
                f"Consolidated Summary Agent called (Loop #{current_retries + 1}, Attempt {current_retries + 1}/{self.MAX_RETRIES + 1})"
            )

            # Increment retry counter
            state["consolidated_summary_agent_retries"] = current_retries + 1

            # Reset all validation agent retries when coming from summary agent
            state["unit_check_agent_retries"] = 0
            state["data_check_agent_retries"] = 0
            state["validation_agent_retries"] = 0

            # Clear improvement feedback after successful summary generation
            # to start fresh for the next iteration
            if current_retries == 1:  # First attempt, clear any old feedback
                state["improvement_feedback"] = ""

            # Calling the ConsolidationSummaryAgent
            consolidated_summary = ConsolidationSummaryAgent(dict(state)).generate_summary()

            if isinstance(consolidated_summary.content, str):
                state["consolidated_summary_result"] = consolidated_summary.content.strip()

            # Log execution time
            execution_time = time.time() - start_time
            logger.info(f"Consolidated Summary Agent completed in {execution_time:.2f}s (Loop #{current_retries + 1})")

            # No need to set next_node - fanout edges will automatically trigger all 3 validators
            return state
        except Exception as e:
            MultiAgentWorkflowException.log_exception(e, "consolidated_summary_agent")
            raise e



    def unit_check_agent(self, state: State) -> State:
        """
        Unit check agent that validates the units of the input data.
        """
        start_time = time.time()
        try:
            self._initialize_retry_counters(state)

            current_retries = state.get("unit_check_agent_retries", 0)
            summary_loop = state.get("summary_agent_retries", 0)
            logger.info(
                f"Unit Check Agent starting (Summary Loop #{summary_loop}, Unit Attempt {current_retries + 1}/{self.MAX_RETRIES + 1})"
            )

            # Increment retry counter
            state["unit_check_agent_retries"] = current_retries + 1

            # Use the standardized UnitCheckAgent to validate units
            unit_checker = UnitCheckAgent(dict(state))
            validation_result = unit_checker.validate()

            # Store the validation result in state for output display
            state["unit_check_result"] = validation_result

            # Log execution time
            execution_time = time.time() - start_time
            logger.info(f"Unit Check Agent completed in {execution_time:.2f}s (Summary Loop #{summary_loop})")

            # Return ONLY the field we modified to avoid parallel update conflicts
            return {"unit_check_result": validation_result}
        except Exception as e:
            MultiAgentWorkflowException.log_exception(e, "unit_check_agent")
            raise e

    def data_check_agent(self, state: State) -> State:
        """
        Data check agent that validates the consistency of numbers in the summary against the input data.
        """
        start_time = time.time()
        try:
            self._initialize_retry_counters(state)

            current_retries = state.get("data_check_agent_retries", 0)
            summary_loop = state.get("summary_agent_retries", 0)
            logger.info(
                f"Data Check Agent starting (Summary Loop #{summary_loop}, Data Attempt {current_retries + 1}/{self.MAX_RETRIES + 1})"
            )

            # Increment retry counter
            state["data_check_agent_retries"] = current_retries + 1

            # Use the standardized DataCheckAgent to validate data consistency
            data_checker = DataCheckAgent(dict(state))
            validation_result = data_checker.validate()

            # Store the validation result in state for output display
            state["data_check_result"] = validation_result

            # Log execution time
            execution_time = time.time() - start_time
            logger.info(f"Data Check Agent completed in {execution_time:.2f}s (Summary Loop #{summary_loop})")

            # Return ONLY the field we modified to avoid parallel update conflicts
            return {"data_check_result": validation_result}
        except Exception as e:
            MultiAgentWorkflowException.log_exception(e, "data_check_agent")
            raise e

    def validation_agent(self, state: State) -> State:
        """
        Validation agent that performs comprehensive quality critique and assessment (replaces critical_check_agent).
        """
        start_time = time.time()
        try:
            self._initialize_retry_counters(state)

            current_retries = state.get("validation_agent_retries", 0)
            summary_loop = state.get("summary_agent_retries", 0)
            logger.info(
                f"Validation Agent starting (Summary Loop #{summary_loop}, Validation Attempt {current_retries + 1}/{self.MAX_RETRIES + 1})"
            )

            # Increment retry counter
            state["validation_agent_retries"] = current_retries + 1

            # Use the ValidationAgent to perform comprehensive quality critique
            validator = ValidationAgent(dict(state))
            validation_result = validator.validate()

            # Store the validation result in state for output display
            state["final_validation_result"] = validation_result

            # Log execution time
            execution_time = time.time() - start_time
            logger.info(f"Validation Agent completed in {execution_time:.2f}s (Summary Loop #{summary_loop})")

            # Return ONLY the field we modified to avoid parallel update conflicts
            return {"final_validation_result": validation_result}

        except Exception as e:
            MultiAgentWorkflowException.log_exception(e, "validation_agent")
            raise e

    # ---------------------- PARALLEL VALIDATION AGGREGATOR ----------------------

    def parallel_validation_aggregator(self, state: State) -> State:
        """
        Aggregate results from the 3 parallel validators (simple fanout).
        All validators run in parallel via multiple edges from summary_agent.

        Routes to:
        - END if all validations pass
        - summary_agent if any validation fails (with retry logic)
        """
        start_time = time.time()
        try:
            if state.get("error_occurred_in_agent") or state.get("max_retries_exceeded_in_agent"):
                logger.error("Error or max retries exceeded in one of the validation agents, marking workflow as rejected")
                state["workflow_approved"] = False
                state["next_node"] = "__end__"
                return state

            if settings.AGENTS_DEBUG:
                logger.info("🧮 PARALLEL VALIDATION AGGREGATOR")
                logger.info(f"Unit Check Result:\n")
                logger.info(state.get("unit_check_result"))
                logger.info(f"Data Check Result:\n")
                logger.info(state.get("data_check_result"))
                logger.info(f"Final Validation Result:\n")
                logger.info(state.get("final_validation_result"))

            self._initialize_retry_counters(state)

            summary_loop = state.get("summary_agent_retries", 0)
            logger.info(f"Aggregating parallel validation results (Summary Loop #{summary_loop})")

            # Get results from state (already populated by the 3 parallel validators)
            unit_check_result = state.get("unit_check_result", {})
            data_check_result = state.get("data_check_result", {})
            final_validation_result = state.get("final_validation_result", {})

            logger.info(f"Received results from 3 validators")

            # Convert results to strings for validation
            if hasattr(unit_check_result, "content"):
                unit_check_content = json.loads(unit_check_result.content.strip())
            else:
                unit_check_content = unit_check_result

            if hasattr(data_check_result, "content"):
                data_check_content = json.loads(data_check_result.content.strip())
            else:
                data_check_content = data_check_result

            if hasattr(final_validation_result, "content"):
                validation_content = json.loads(final_validation_result.content.strip())
            else:
                validation_content = final_validation_result

            # Check each validation status
            unit_check_passed = unit_check_result.get("status", {}).upper() == "PASS"
            data_check_passed = data_check_result.get("status", {}).upper() == "PASS"
            validation_passed = validation_content.get("status", {}).upper() == "PASS"

            # Log individual validation results with clear formatting
            logger.info(f"")
            logger.info(f"  Unit Check: {'PASS' if unit_check_passed else 'FAIL'}")
            logger.info(f"  Data Check: {'PASS' if data_check_passed else 'FAIL'}")
            logger.info(f"  Validation: {'PASS' if validation_passed else 'FAIL'}")
            logger.info(f"")

            # Determine if all validations passed
            all_passed = unit_check_passed and data_check_passed and validation_passed
            state["all_validations_passed"] = all_passed

            # Store parallel validation results
            state["parallel_validation_results"] = {
                "unit_check_passed": unit_check_passed,
                "data_check_passed": data_check_passed,
                "validation_passed": validation_passed,
            }

            if all_passed:
                # All validations passed - end workflow
                state["workflow_approved"] = True
                state["next_node"] = "__end__"
                logger.info(f"All parallel validations PASSED - workflow approved (Loop #{summary_loop})")
            else:
                # Collect feedback from failed validations - not needed for now
                # if not unit_check_passed:
                #     self._collect_feedback(state, "Unit Check", unit_check_content)
                # if not data_check_passed:
                #     self._collect_feedback(state, "Data Check", data_check_content)
                # if not validation_passed:
                #     self._collect_feedback(state, "Validation Check", validation_content)

                # Increment summary retry counter (since we're going back to summary)
                current_summary_retries = state.get("summary_agent_retries", 0)

                # Check if we've exceeded max retries
                if current_summary_retries >= self.MAX_RETRIES:
                    logger.error(
                        f"Parallel validation failed after {self.MAX_RETRIES} summary attempts (Loop #{current_summary_retries}), workflow marked as rejected"
                    )
                    state["workflow_approved"] = False
                    state["next_node"] = "__end__"
                else:
                    logger.warning(
                        f"Parallel validation failed - returning to consolidated summary_agent (Loop #{current_summary_retries}/{self.MAX_RETRIES})"
                    )
                    state["next_node"] = "consolidated_summary_agent"

            execution_time = time.time() - start_time
            logger.info(f"Aggregator completed in {execution_time:.2f}s (Summary Loop #{summary_loop})")

            return state

        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"Error in validation_aggregator after {execution_time:.2f}s: {e}")
            MultiAgentWorkflowException.log_exception(e, "validation_aggregator")
            raise MultiAgentWorkflowException(
                "Error in validation_aggregator", sys.exc_info()
            )

    def route_from_aggregator(self, state: State) -> str:
        """
        Route from aggregator based on validation results.
        Returns: "summary_agent" if retry needed, "__end__" if complete
        """
        try:
            next_node = state.get("next_node", "__end__")
            all_passed = state.get("all_validations_passed", False)
            current_retries = state.get("summary_agent_retries", 0)

            # Validate the routing decision
            valid_routes = ["__end__", "summary_agent"]
            if next_node not in valid_routes:
                logger.warning(
                    f"Invalid route '{next_node}' from aggregator, defaulting to __end__"
                )
                next_node = "__end__"

            logger.info(
                f"Routing from aggregator to: {next_node} (all_passed: {all_passed}, retry: {current_retries}/{self.MAX_RETRIES})"
            )
            return next_node
        except Exception as e:
            logger.error(f"Error in route_from_aggregator: {e}")
            return "__end__"  # Safe fallback

    def route_from_validation_aggregator(self, state: State) -> str:
        """
        Enhanced routing function for validation_aggregator with better error handling.
        """
        try:
            next_node = state.get("next_node", "__end__")
            all_passed = state.get("all_validations_passed", False)
            current_retries = state.get("summary_agent_retries", 0)

            # Validate the routing decision
            valid_routes = ["__end__", "summary_agent"]
            if next_node not in valid_routes:
                logger.warning(
                    f"Invalid route '{next_node}' from validation_aggregator, defaulting to __end__"
                )
                next_node = "__end__"

            logger.info(
                f"Routing from validation_aggregator to: {next_node} (all_passed: {all_passed}, retry: {current_retries}/{self.MAX_RETRIES})"
            )
            return next_node
        except Exception as e:
            logger.error(f"Error in route_from_validation_aggregator: {e}")
            return "__end__"  # Safe fallback

    def route_from_unit_check(self, state: State) -> str:
        """
        Enhanced routing function for unit_check_agent with better error handling.
        """
        try:
            next_node = state.get("next_node", "summary_agent")
            current_retries = state.get("unit_check_agent_retries", 0)

            # Validate the routing decision
            valid_routes = ["data_check_agent", "summary_agent"]
            if next_node not in valid_routes:
                logger.warning(
                    f"Invalid route '{next_node}' from unit_check_agent, defaulting to summary_agent"
                )
                next_node = "summary_agent"

            logger.info(
                f"Routing from unit_check_agent to: {next_node} (retry: {current_retries}/{self.MAX_RETRIES})"
            )
            return next_node
        except Exception as e:
            logger.error(f"Error in route_from_unit_check: {e}")
            return "summary_agent"  # Safe fallback

    def route_from_data_check(self, state: State) -> str:
        """
        Enhanced routing function for data_check_agent with better error handling.
        """
        try:
            next_node = state.get("next_node", "validation_agent")
            current_retries = state.get("data_check_agent_retries", 0)

            # Validate the routing decision
            valid_routes = ["validation_agent", "summary_agent"]
            if next_node not in valid_routes:
                logger.warning(
                    f"Invalid route '{next_node}' from data_check_agent, defaulting to validation_agent"
                )
                next_node = "validation_agent"

            logger.info(
                f"Routing from data_check_agent to: {next_node} (retry: {current_retries}/{self.MAX_RETRIES})"
            )
            return next_node
        except Exception as e:
            logger.error(f"Error in route_from_data_check: {e}")
            return "validation_agent"  # Safe fallback

    def route_from_validation(self, state: State) -> str:
        """
        Enhanced routing function for validation_agent with better error handling.
        """
        try:
            next_node = state.get("next_node", "__end__")
            current_retries = state.get("validation_agent_retries", 0)

            # Validate the routing decision
            valid_routes = ["__end__", "summary_agent"]
            if next_node not in valid_routes:
                logger.warning(
                    f"Invalid route '{next_node}' from validation_agent, defaulting to __end__"
                )
                next_node = "__end__"

            logger.info(
                f"Routing from validation_agent to: {next_node} (retry: {current_retries}/{self.MAX_RETRIES})"
            )
            return next_node
        except Exception as e:
            logger.error(f"Error in route_from_validation: {e}")
            return "__end__"  # Safe fallback

    def build_validation_subgraph(self) -> StateGraph:
        """
        Build the validation subgraph for parallel validation execution.
        Each validator runs independently through this subgraph.
        """
        logger.info("🏗️  Building validation subgraph")

        validation_builder = StateGraph(ValidationWorkerState)

        # Add validation worker node and completion node
        validation_builder.add_node("validator", self._validation_worker_node)
        validation_builder.add_node("completion", self._validation_completion)

        # Simple flow: START → validator → completion → END
        validation_builder.add_edge(START, "validator")
        validation_builder.add_edge("validator", "completion")
        validation_builder.add_edge("completion", END)

        logger.info("Validation subgraph built successfully")
        return validation_builder

    def build_workflow(self) -> StateGraph:
        """
        Builds the multi-agent workflow with SIMPLE PARALLEL VALIDATION using fanout edges.

        Flow (fanout/fan-in):
        START → summary_agent → unit_check_agent ↘
                              → data_check_agent  → aggregator → {END or summary_agent}
                              → validation_agent ↗
        """
        try:
            logger.info("🏗️  Building workflow with simple parallel validation fanout")

            workflow = StateGraph(State)

            # Add all nodes
            workflow.add_node("summary_agent", self.summary_agent)
            workflow.add_node("unit_check_agent", self.unit_check_agent)
            workflow.add_node("data_check_agent", self.data_check_agent)
            workflow.add_node("validation_agent", self.validation_agent)
            workflow.add_node("aggregator", self.parallel_validation_aggregator)

            # Entry point
            workflow.add_edge(START, "summary_agent")

            # FANOUT: summary_agent → 3 validators in parallel (simple edges)
            workflow.add_edge("summary_agent", "unit_check_agent")
            workflow.add_edge("summary_agent", "data_check_agent")
            workflow.add_edge("summary_agent", "validation_agent")

            # FAN-IN: All 3 validators → aggregator (simple edges)
            workflow.add_edge("unit_check_agent", "aggregator")
            workflow.add_edge("data_check_agent", "aggregator")
            workflow.add_edge("validation_agent", "aggregator")

            # Aggregator routing (conditional)
            workflow.add_conditional_edges(
                "aggregator",
                self.route_from_aggregator,
                {
                    "summary_agent": "summary_agent",
                    "__end__": END,
                },
            )

            logger.info("Workflow built successfully with simple fanout/fan-in")
            return workflow
        except Exception as e:
            MultiAgentWorkflowException.log_exception(e, "build_workflow")
            raise MultiAgentWorkflowException("Error in build_workflow", sys.exc_info())


if __name__ == "__main__":
    from hello.ml.exception.custom_exception import MultiAgentWorkflowException
    from hello.ml.logger import GLOBAL_LOGGER as logger
    from hello.ml.multi_agent_workflow.agents_workflow import AgentsWorkflow

    workflow = AgentsWorkflow().build_workflow()

    input_data = """
    [{'Quarter': 'Q2 2022', 'Overall': 18.01, 'Class A': 21.1, 'Class B': 17.0},
    {'Quarter': 'Q3 2022', 'Overall': 17.7, 'Class A': 20.8, 'Class B': 16.6},
    {'Quarter': 'Q4 2022', 'Overall': 17.49, 'Class A': 19.7, 'Class B': 17.2},
    {'Quarter': 'Q1 2023', 'Overall': 17.6, 'Class A': 20.4, 'Class B': 16.8},
    {'Quarter': 'Q2 2023', 'Overall': 17.72, 'Class A': 20.4, 'Class B': 17.1},
    {'Quarter': 'Q3 2023', 'Overall': 17.99, 'Class A': 21.1, 'Class B': 17.1},
    {'Quarter': 'Q4 2023', 'Overall': 17.95, 'Class A': 21.0, 'Class B': 17.2},
    {'Quarter': 'Q1 2024', 'Overall': 18.36, 'Class A': 20.9, 'Class B': 18.1},
    {'Quarter': 'Q2 2024', 'Overall': 18.96, 'Class A': 22.3, 'Class B': 17.9},
    {'Quarter': 'Q3 2024', 'Overall': 19.19, 'Class A': 22.0, 'Class B': 18.7},
    {'Quarter': 'Q4 2024', 'Overall': 19.13, 'Class A': 21.8, 'Class B': 18.8},
    {'Quarter': 'Q1 2025', 'Overall': 18.65, 'Class A': 21.0, 'Class B': 18.5},
    {'Quarter': 'Q2 2025', 'Overall': 18.29, 'Class A': 20.4, 'Class B': 18.4}]
    """

    app = workflow.compile()
    result = app.invoke({"session_type": "vacancy", "input_data": input_data})  # type: ignore
    logger.info(result["summary_result"])
