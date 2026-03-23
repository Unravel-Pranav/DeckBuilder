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

class DataCheckAgent(BaseAgent):
    # Use LOW reasoning for data validation (numeric comparison)
    # REASONING_EFFORT = "low"
    # Specify which agent config key to use from settings.agents_config
    AGENT_CONFIG_KEY = "data_check_agent"

    def __init__(self, state: Dict[str, Any]) -> None:
        # Load agent prompts from YAML file
        self.session_type = state.get("session_type", "")
        
        # Load all prompts for this agent
        self.agent_prompts = load_agent_prompts("data_check_agent")
        self.system_prompt = self.agent_prompts.get("system_prompt", "")
        self.user_prompt_template = self.agent_prompts.get("user_prompt", "")
        
        super().__init__(state)

    def _initialize_agent_specific_attributes(self) -> None:
        """Initialize agent-specific attributes from state."""
        list_of_data = self.state.get("input_data", [])
        self.input_data = self._preprocess_input_data(list_of_data)
        self.summary_result = self.state.get("summary_result", "")

    def _get_agent_goal(self) -> str:
        """Default implementation - not used in this agent."""
        return ""

    def _create_agent(self):
        """Create ReAct agent with dynamic prompting for data checking validation."""
        return create_react_agent(
            model=self.model,
            tools=[],  # No tools needed for validation
            prompt=self._dynamic_prompt,
        )

    def _dynamic_prompt(
        self, state: Dict[str, Any], config: Optional[RunnableConfig] = None
    ) -> List[BaseMessage]:
        """Dynamic prompt that combines system and user prompts for data checking validation."""

        # Get configuration from config if available
        cfg = (config or {}).get("configurable", {})

        # Extract data from state/config
        input_data = cfg.get("input_data", self.input_data)
        summary_result = cfg.get("summary_result", self.summary_result)

        # Build user message content from the user prompt template
        user_content = self.user_prompt_template.format(
            input_data=input_data,
            summary_result=summary_result,
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
                # Build the exact user prompt that will be sent
                user_prompt_formatted = self.user_prompt_template.format(
                    input_data=self.input_data,
                    summary_result=self.summary_result
                )

                if settings.AGENTS_DEBUG:
                    logger.info("🎯 DATA CHECK AGENT - EXACT PROMPTS BEING SENT TO LLM")
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
                    "input_data": self.input_data,
                    "summary_result": self.summary_result
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
            MultiAgentWorkflowException.log_exception(e, "data_check_validation")
            raise MultiAgentWorkflowException(
                "Error in data_check validation node ", sys.exc_info()
            )

