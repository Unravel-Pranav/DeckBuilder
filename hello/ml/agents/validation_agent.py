import sys
from typing import Any, Dict, List, Optional

from langchain_core.messages import BaseMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.prebuilt import create_react_agent

from hello.ml.agents.base_agent import BaseAgent
from hello.ml.exception.custom_exception import MultiAgentWorkflowException
from hello.ml.logger import GLOBAL_LOGGER as logger
from hello.ml.utils.config_loader import load_agent_prompts
from hello.services.config import settings

class ValidationAgent(BaseAgent):
    """Validation agent that performs comprehensive quality critique and assessment (replaces CritiqueCheckAgent)."""
    # Use LOW reasoning for unit validation (simple pattern matching)
    # REASONING_EFFORT = "low"
    # Specify which agent config key to use from settings.agents_config
    AGENT_CONFIG_KEY = "validation_agent"

    def __init__(self, state: Dict[str, Any]) -> None:
        # Load agent prompts from YAML file
        self.session_type = state.get("session_type", "")
        self.prompt = state.get("prompt", "")  # User's section template/prompt
        
        # Load all prompts for this agent
        self.agent_prompts = load_agent_prompts("validation_agent")
        self.system_prompt = self.agent_prompts.get("system_prompt", "")
        self.user_prompt_template = self.agent_prompts.get("user_prompt", "")
        
        super().__init__(state)

    def _initialize_agent_specific_attributes(self) -> None:
        """Initialize agent-specific attributes from state."""
        list_of_data = self.state.get("input_data", [])
        self.input_data = self._preprocess_input_data(list_of_data)
        self.summary_result = self.state.get("summary_result", "")
        self.data_check_result = self.state.get("data_check_result", "")
        self.unit_check_result = self.state.get("unit_check_result", "")
        self.user_feedback = self.state.get("user_feedback", "")

    def _get_agent_goal(self) -> str:
        """Default implementation - not used in this agent."""
        return ""

    def _create_agent(self):
        """Create ReAct agent with dynamic prompting for comprehensive validation."""
        return create_react_agent(
            model=self.model,
            tools=[],  # No tools needed for validation
            prompt=self._dynamic_prompt,
        )

    def _dynamic_prompt(
        self, state: Dict[str, Any], config: Optional[RunnableConfig] = None
    ) -> List[BaseMessage]:
        """Dynamic prompt that combines system and user prompts for validation and critique."""

        # Get configuration from config if available
        cfg = (config or {}).get("configurable", {})

        # Extract data from state/config
        input_data = cfg.get("input_data", self.input_data)
        summary_result = cfg.get("summary_result", self.summary_result)
        feedback_instructions = cfg.get(
            "feedback_instructions", self._get_feedback_instructions()
        )
        prompt = cfg.get("prompt", self.prompt)

        # Build user message content from the user prompt template
        user_content = self.user_prompt_template.format(
            prompt=prompt,
            input_data=input_data,
            summary_result=summary_result,
            feedback_instructions=feedback_instructions
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

    def validate(self) -> BaseMessage:
        """Validate using dynamic ReAct agent."""
        try:
            logger.info(f"Starting {self.__class__.__name__} validation process")

            # DEBUG: Print the exact final prompts being sent to the LLM
            try:
                feedback_instructions = self._get_feedback_instructions()
                
                # Build the exact user prompt that will be sent
                user_prompt_formatted = self.user_prompt_template.format(
                    prompt=self.prompt,
                    input_data=self.input_data,
                    summary_result=self.summary_result,
                    feedback_instructions=feedback_instructions
                )

                if settings.AGENTS_DEBUG:
                    logger.info("🎯 VALIDATION AGENT - EXACT PROMPTS BEING SENT TO LLM")
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
                   # "prompt": self.prompt,  # Don't format here - will be formatted in _dynamic_prompt
                    "input_data": self.input_data,
                    "summary_result": self.summary_result,
                    #"feedback_instructions": self._get_feedback_instructions(),
                }
            }
            

            # Invoke the dynamic ReAct agent with automatic fallback
            result = self.invoke_with_fallback(state, config=config)

            # Extract the agent's output from the last message
            agent_output = result["messages"][-1].content

            # Validate JSON format
            validated_output = self._validate_json_response(agent_output)

            logger.info(f"{self.__class__.__name__} completed validation")

            # Return as BaseMessage-compatible object
            return self._create_result_message(validated_output)

        except Exception as e:
            MultiAgentWorkflowException.log_exception(e, "validation_check_validation")
            raise MultiAgentWorkflowException(
                "Error in validation_check validation node ", sys.exc_info()
            )

    def _get_feedback_instructions(self) -> str:
        """Get feedback instructions based on improvement_feedback."""
        information_prompt = ""
        if self.user_feedback:
            information_prompt += \
                f"""Feedback on Generated Commentary:
Below is the user feedback on the previously generated commentary. Verify that each feedback item is addressed in the generated commentary:\n\n{self.user_feedback}\n\n"""
        # if self.unit_check_result:
        #     information_prompt += f"The following unit checks were performed on the summary. Please ensure your improved summary passes all these checks.\n\n- Unit Check Results: {self.unit_check_result}\n\n"
        # if self.data_check_result:
        #     information_prompt += f"The following data accuracy checks were performed on the summary. Please ensure your improved summary passes all these checks.\n\n- Data Check Results: {self.data_check_result}\n\n"
        if information_prompt:
            information_prompt += """INSTRUCTIONS: Review all user feedback and prior check results above. Verify all user feedback items and prior check failures are fully addressed."""
            return information_prompt
        else:
            return """FIRST ATTEMPT INSTRUCTIONS:
            Generate a comprehensive, high-quality summary that follows all formatting rules, maintains data accuracy, and provides clear business value."""
