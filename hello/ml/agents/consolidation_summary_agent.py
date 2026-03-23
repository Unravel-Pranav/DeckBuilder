import sys
from typing import Any, Dict, List, Optional

from langchain_core.messages import BaseMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.prebuilt import create_react_agent

from hello.ml.agents.base_agent import BaseAgent
from hello.ml.exception.custom_exception import MultiAgentWorkflowException
from hello.ml.logger import GLOBAL_LOGGER as logger
from hello.services.config import settings
from hello.ml.utils.config_loader import load_agent_prompts


class ConsolidationSummaryAgent(BaseAgent):
    # Use HIGH reasoning for summary generation (complex task)
    # REASONING_EFFORT = "medium"
    # Specify which agent config key to use from settings.agents_config
    AGENT_CONFIG_KEY = "consolidation_agent"
    

    def __init__(self, state: Dict[str, Any]) -> None:
        # Load prompt and few shot examples before calling super().__init__
        self.session_type = state.get("session_type", "")
        self.prompt = state.get("prompt", "")  # User's section template/prompt
        
        # Load all prompts for this agent
        self.agent_prompts = load_agent_prompts("consolidation_summary_agent")
        self.system_prompt = self.agent_prompts.get("system_prompt", "")
        self.user_prompt_template = self.agent_prompts.get("user_prompt", "")
        
        super().__init__(state)

    def _initialize_agent_specific_attributes(self) -> None:
        """Initialize agent-specific attributes from state."""
        list_of_data = self.state.get("input_data", [])
        list_of_summary = self.state.get("summary_results", [])
        unit_check_result = self.state.get("unit_check_result", {})
        data_check_result = self.state.get("data_check_result", {})
        final_validation_result = self.state.get("final_validation_result", {})
        self.summary_results = self._preprocess_summary_results(list_of_summary)
        self.input_data = self._preprocess_input_data(list_of_data)
        self.user_feedback = self.state.get("user_feedback", "")
        self.unit_check_result = unit_check_result if unit_check_result.get("status") == "FAIL" else None
        self.data_check_result = data_check_result if data_check_result.get("status") == "FAIL" else None
        self.final_validation_result = final_validation_result if final_validation_result.get("status") == "FAIL" else None
        self.previous_summary = self.state.get("summary_result", "")

    def _get_agent_goal(self) -> str:
        """Default implementation - not used in this agent."""
        return ""

    def _create_agent(self):
        """Create ReAct agent with dynamic prompting for session summarization."""
        return create_react_agent(
            model=self.model,
            tools=[],  # No tools needed for direct summarization
            prompt=self._dynamic_prompt,
        )

    def _dynamic_prompt(
        self, state: Dict[str, Any], config: Optional[RunnableConfig] = None
    ) -> List[BaseMessage]:
        """Dynamic prompt that combines system and user prompts for consolidation summarization."""

        # Get configuration from config if available
        cfg = (config or {}).get("configurable", {})

        # Extract data from state/config
        summary_results = cfg.get("summary_results", self.summary_results)
        input_data = cfg.get("input_data", self.input_data)
        feedback_instructions = cfg.get(
            "feedback_instructions", self._get_feedback_instructions()
        )
        prompt = cfg.get("prompt", self.prompt)
        previous_summary = cfg.get("previous_summary", self.previous_summary)

        # Build user message content from the user prompt template
        user_content = self.user_prompt_template.format(
            summary_results=summary_results,
            feedback_instructions=feedback_instructions,
            input_data=input_data,
            prompt=prompt,
            previous_summary=previous_summary
        )

        # Build messages list with system prompt and formatted user prompt
        messages: list[BaseMessage] = [
            SystemMessage(content=self.system_prompt)
        ]
        
        # Add the formatted user message
        from langchain_core.messages import HumanMessage
        messages.append(HumanMessage(content=user_content))
        
        # Add any existing messages from state
        if state.get("messages"):
            messages.extend(state["messages"])

        return messages

    def generate_summary(self) -> BaseMessage:
        """Generate a comprehensive summary using dynamic ReAct agent."""
        try:
            logger.info("Starting SessionSummaryAgent summary generation process")

            # DEBUG: Print the exact final prompts being sent to the LLM
            try:
                feedback_instructions = self._get_feedback_instructions()

                # Build the exact user prompt that will be sent
                user_prompt_formatted = self.user_prompt_template.format(
                    summary_results=self.summary_results,
                    feedback_instructions=feedback_instructions,
                    input_data=self.input_data,
                    prompt=self.prompt,
                    previous_summary=self.previous_summary
                )
                if settings.AGENTS_DEBUG:
                    logger.info("🎯 CONSOLIDATION SUMMARY AGENT - EXACT PROMPTS BEING SENT TO LLM")
                    logger.info(f"Session Type: {self.session_type}")
                    logger.info(f"System Prompt Length: {len(self.system_prompt)} characters")
                    logger.info(f"User Prompt Length: {len(user_prompt_formatted)} characters")
                    logger.info("SYSTEM PROMPT:")
                    logger.info(self.system_prompt)
                    logger.info("USER PROMPT:")
                    logger.info(user_prompt_formatted)
            except Exception as e:
                logger.error(f"Error formatting debug prompt: {str(e)}")

            # Prepare state and config for the agent
            state = {}

            config = {
                "configurable": {
                    "summary_results": self.summary_results,
                    "input_data": self.input_data,
                    "feedback_instructions": self._get_feedback_instructions(),
                    "prompt": self.prompt,
                    "previous_summary": self.previous_summary
                }
            }

            # Invoke the dynamic ReAct agent with automatic fallback
            result = self.invoke_with_fallback(state, config=config)

            # Extract the agent's output from the last message
            agent_output = result["messages"][-1].content
            logger.info(
                f"ConsolidationSummaryAgent completed summarization: {len(agent_output)} characters"
            )

            # Return as BaseMessage-compatible object
            from langchain_core.messages import HumanMessage

            return HumanMessage(content=agent_output)

        except Exception as e:
            MultiAgentWorkflowException.log_exception(e, "consolidation_generate_summary")
            raise MultiAgentWorkflowException(
                "Error in consolidation_generate_summary node ", sys.exc_info()
            )

    def _get_feedback_instructions(self) -> str:
        """Get feedback instructions based on improvement_feedback."""
        information_prompt = ""
        if self.user_feedback:
            information_prompt += \
                f"""Feedback on Generated Commentary:
Below is a list of feedback for the previously generated commentary. Use this feedback to refine and improve the commentary: \n\n{self.user_feedback}\n\n"""
        if self.unit_check_result:
            information_prompt += f"The following unit checks were performed on the summary. Please ensure your improved summary passes all these checks.\n\n- Unit Check Results: {self.unit_check_result}\n\n"
        if self.data_check_result:
            information_prompt += f"The following data accuracy checks were performed on the summary. Please ensure your improved summary passes all these checks.\n\n- Data Check Results: {self.data_check_result}\n\n"
        if self.final_validation_result:
            information_prompt += f"The following validation checks were performed on the summary. Please ensure your improved summary passes all these checks.\n\n- Validation Results: {self.final_validation_result}\n\n"
        if information_prompt:
            information_prompt += """INSTRUCTIONS FOR IMPROVEMENT:
1. Carefully read the user feedback above, understand the issues and suggestions mentioned.
2. Address EVERY issue mentioned in the feedback
3. Ensure your summary follows all formatting rules, data accuracy requirements, and quality standards
4. Pay special attention to:
   - Numeric formatting and unit consistency
   - Data accuracy and calculation correctness
   - Summary completeness and professional quality
5. Generate an improved summary that will pass all validation checks

Your improved summary should directly address the specific issues mentioned above."""
            return information_prompt
        else:
            return """FIRST ATTEMPT INSTRUCTIONS:
Generate a comprehensive, high-quality summary that follows all formatting rules, maintains data accuracy, and provides clear business value."""