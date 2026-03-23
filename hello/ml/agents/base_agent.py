import os
import json
from abc import ABC, abstractmethod
from typing import Any, Dict, List

from langchain_core.messages import BaseMessage

from hello.ml.logger import GLOBAL_LOGGER as logger
from hello.ml.utils.config_loader import load_agent_goal
from hello.ml.utils.model_factory import get_model_loader
from hello.services.config import settings


class BaseAgent(ABC):
    """Base class for all agents in the multi-agent workflow."""

    # Class-level attribute for reasoning effort (can be overridden by subclasses)
    REASONING_EFFORT = None  # None means use config default
    
    # Class-level attribute for agent config key (e.g., "summary_agent", "consolidation_agent")
    # Subclasses should override this to specify which config key to use
    AGENT_CONFIG_KEY = None  # None means use global settings

    def __init__(self, state: Dict[str, Any]):
        """Initialize base agent with standardized state."""
        try:
            # Load agent-specific configuration if AGENT_CONFIG_KEY is set
            self.agent_config = self._get_agent_config()

            logger.info(f"Initializing {self.__class__.__name__} with config: {self.agent_config}")
            
            # Get provider from agent config or use default
            provider = self._get_provider_from_config()
            
            # Use model factory to get appropriate loader based on agent config or default
            self.model_loader = get_model_loader(provider=provider)

            # Get model name and reasoning effort from agent config or defaults
            model_name = self._get_model_name_from_config()
            reasoning_effort = self._get_reasoning_effort_from_config()
            temperature = self._get_temperature_from_config()
            streaming_enabled = self._get_streaming_enabled_from_config()

            # Load model with provider-specific parameters
            # Different providers support different parameters:
            # - WSO2_OPENAI: supports both streaming and reasoning_effort
            # - WSO2_BEDROCK: supports reasoning_effort but NOT streaming
            # - WSO2_GEMINI: supports streaming but NOT reasoning_effort
            # - OPENAI: supports reasoning_effort but NOT streaming
            self.model = self._load_model_with_provider_params(
                provider=provider,
                model_name=model_name,
                reasoning_effort=reasoning_effort,
                temperature=temperature,
                streaming_enabled=streaming_enabled
            )
            

            logger.info(
                f"{self.__class__.__name__} initialized with provider: {provider}, "
                f"model: {model_name}, reasoning effort: {reasoning_effort}, "
                f"temperature: {temperature}, "
                f"streaming enabled: {streaming_enabled}"
            )

            self.state = state

            # Initialize agent-specific attributes
            self._initialize_agent_specific_attributes()

            # Create the agent (implementation-specific)
            self.agent_executor = self._create_agent()

        except Exception as e:
            logger.error(f"Error in {self.__class__.__name__}: {e}")
            raise e
    
    def _preprocess_input_data(self, list_of_data: List[Dict[str, Any]]) -> str:
        """Preprocess input data to be used by the agent."""
        dataset_json = ""
        for num, item in enumerate(list_of_data):
            dataset_json += f"Input data {num + 1}:\n{item}\n"
        return dataset_json

    def _preprocess_summary_results(self, list_of_summaries: List[str]) -> str:
        """Preprocess summary results to be used by the agent."""
        summaries_text = ""
        for num, summary in enumerate(list_of_summaries):
            summaries_text += f"Summary {num + 1}:\n{summary}\n"
        return summaries_text

    def _get_agent_config(self) -> Dict[str, Any]:
        """Get agent-specific configuration from settings.
        
        Returns:
            Dictionary with agent config if AGENT_CONFIG_KEY is set, else empty dict.
        """
        if not self.AGENT_CONFIG_KEY:
            return {}
        
        try:
            agents_config = settings.agents_config
            agent_config = agents_config.get(self.AGENT_CONFIG_KEY, {})
            
            # Check if agent is enabled
            if not agent_config.get("enabled", True):
                logger.warning(f"{self.__class__.__name__} is disabled in configuration")
            
            return agent_config
        except Exception as e:
            logger.warning(f"Failed to load agent config for {self.AGENT_CONFIG_KEY}, using defaults: {str(e)}")
            return {}
    
    def _load_model_with_provider_params(
        self,
        provider: str,
        model_name: str,
        reasoning_effort: str | None,
        temperature: float,
        streaming_enabled: bool
    ):
        """Load model with provider-specific parameters.

        Different providers support different parameters:
        - WSO2_OPENAI: supports both streaming and reasoning_effort
        - WSO2_BEDROCK: supports reasoning_effort but NOT streaming
        - WSO2_GEMINI: supports streaming but NOT reasoning_effort
        - OPENAI: supports reasoning_effort but NOT streaming

        Args:
            provider: Provider name (e.g., "WSO2_OPENAI", "WSO2_BEDROCK", "WSO2_GEMINI")
            model_name: Model name to load
            reasoning_effort: Reasoning effort level (for providers that support it)
            temperature: Temperature setting
            streaming_enabled: Whether to enable streaming (for providers that support it)

        Returns:
            Loaded model instance
        """
        # Normalize provider name to uppercase
        provider_upper = provider.upper()

        # Build kwargs based on provider capabilities
        load_kwargs = {
            "model_name": model_name,
            "temperature": temperature,
        }

        # WSO2_OPENAI supports both streaming and reasoning_effort
        if provider_upper == "WSO2_OPENAI":
            load_kwargs["streaming"] = streaming_enabled
            if reasoning_effort:
                load_kwargs["reasoning_effort"] = reasoning_effort
            logger.info(
                f"Loading WSO2_OPENAI model with streaming={streaming_enabled}, "
                f"reasoning_effort={reasoning_effort}"
            )

        # WSO2_BEDROCK supports reasoning_effort but NOT streaming
        elif provider_upper == "WSO2_BEDROCK":
            if reasoning_effort:
                load_kwargs["reasoning_effort"] = reasoning_effort
            logger.info(
                f"Loading WSO2_BEDROCK model with reasoning_effort={reasoning_effort} "
                f"(streaming not supported)"
            )

        # WSO2_GEMINI supports streaming but NOT reasoning_effort
        elif provider_upper == "WSO2_GEMINI":
            load_kwargs["streaming"] = streaming_enabled
            logger.info(
                f"Loading WSO2_GEMINI model with streaming={streaming_enabled} "
                f"(reasoning_effort not supported)"
            )

        # OPENAI supports reasoning_effort but NOT streaming
        elif provider_upper == "OPENAI":
            if reasoning_effort:
                load_kwargs["reasoning_effort"] = reasoning_effort
            logger.info(
                f"Loading OPENAI model with reasoning_effort={reasoning_effort} "
                f"(streaming not supported)"
            )

        # Unknown provider - pass all parameters and let the loader handle it
        else:
            load_kwargs["streaming"] = streaming_enabled
            if reasoning_effort:
                load_kwargs["reasoning_effort"] = reasoning_effort
            logger.warning(
                f"Unknown provider '{provider}', passing all parameters - "
                f"loader may raise error if unsupported"
            )

        # Load the model with the appropriate parameters
        return self.model_loader.load_model(**load_kwargs)

    def _get_provider_from_config(self) -> str:
        """Return provider string directly from config/settings.
        """
        provider = self.agent_config.get("provider", settings.LLM_MODEL_PROVIDER) if self.agent_config else settings.LLM_MODEL_PROVIDER
        # Optional lightweight validation (can be removed if unnecessary)
        allowed = {"WSO2_OPENAI", "WSO2_BEDROCK", "WSO2_GEMINI", "OPENAI"}
        if provider not in allowed:
            logger.warning(f"Provider '{provider}' not in allowed set {allowed}; passing through unmodified - may cause factory error.")
        return provider
    
    def _get_model_name_from_config(self) -> str:
        """Get model name from agent config or use default."""
        if self.agent_config:
            return self.agent_config.get("model", settings.LLM_MODEL_NAME)
        return settings.LLM_MODEL_NAME
    
    def _get_reasoning_effort_from_config(self) -> str | None:
        """Get reasoning effort from agent config.
        
        Returns:
            Reasoning effort level if thinking_enabled is True, else None.
            Falls back to class REASONING_EFFORT if config not available.
        """
        if self.agent_config and self.agent_config.get("thinking_enabled", False):
            thinking_level = self.agent_config.get("thinking_level", "high")
            if thinking_level and thinking_level != "none":
                return thinking_level
        return None


    def _get_temperature_from_config(self) -> float | None:
        """Get temperature from agent config or use default."""
        if self.agent_config and "temperature" in self.agent_config:
            return float(self.agent_config["temperature"])
        return settings.LLM_MODEL_TEMPERATURE


    def _get_streaming_enabled_from_config(self) -> bool:        
        """Get streaming_enabled from agent config or use default."""
        if self.agent_config and "streaming_enabled" in self.agent_config:
            return bool(self.agent_config["streaming_enabled"])
        return settings.LLM_MODEL_STREAMING

    @abstractmethod
    def _initialize_agent_specific_attributes(self) -> None:
        """Initialize agent-specific attributes from state."""
        pass

    def _get_agent_goal(self) -> str:
        """Return the agent-specific goal/rules loaded from YAML configuration."""
        # Get session type from state
        session_type = self.state.get("session_type", "")

        # Get agent type - to be set by subclasses
        agent_type = getattr(self, "agent_type", "")

        if session_type and agent_type:
            goal = load_agent_goal(session_type, agent_type)
            if goal:
                return goal

        # Fallback to empty string if YAML loading fails
        logger.warning(f"Using empty agent goal for {self.__class__.__name__}")
        return ""

    @abstractmethod
    def _create_agent(self):
        """Create the agent implementation (ReAct agent, executor, etc.)."""
        pass

    def _validate_json_response(self, response: str) -> str:
        """Validate and ensure proper JSON response format."""
        try:
            # Try to parse as JSON
            parsed = json.loads(response)

            # Ensure required fields exist
            if "status" not in parsed:
                parsed["status"] = "FAIL"
            if "reason" not in parsed:
                parsed["reason"] = "Invalid response format"

            # Normalize status
            parsed["status"] = str(parsed["status"]).upper()
            if parsed["status"] not in ["PASS", "FAIL"]:
                parsed["status"] = "FAIL"
                parsed["reason"] = f"Invalid status value: {parsed['status']}"

            return json.dumps(parsed)

        except json.JSONDecodeError:
            # Create valid JSON from text response
            fallback_response = {
                "status": "PASS" if "PASS" in response.upper() else "FAIL",
                "reason": response,
            }
            return json.dumps(fallback_response)

    def _create_result_message(self, content: str) -> BaseMessage:
        """Create standardized result message."""

        class ValidationResult(BaseMessage):
            def __init__(self, content: str):
                super().__init__(content=content, type="validation_result")

        return ValidationResult(content)

    def check_validation_status(self, validation_content: str) -> bool:
        """Standardized validation status check."""
        try:
            validation_json = json.loads(validation_content)
            status = str(validation_json.get("status", "")).upper()
            return status == "PASS"
        except json.JSONDecodeError:
            return "PASS" in validation_content.upper()
    
    def _get_fallback_provider(self, current_provider: str) -> str:
        """Get fallback provider based on current provider.
        
        Uses LLM_MODEL_PROVIDERS from settings to determine available providers.
        Falls back to the other provider in the list.
        
        Args:
            current_provider: Current provider name (in agent config format)
            
        Returns:
            Fallback provider name (in agent config format)
        """
        # Get available providers from settings
        available_providers = [p.strip() for p in settings.LLM_MODEL_PROVIDERS.split(",") if p.strip()]
        
        # Find current provider in the list and return the other one
        if current_provider in available_providers:
            # Return the other provider in the list
            for provider in available_providers:
                if provider != current_provider:
                    return provider
        return settings.LLM_MODEL_PROVIDER
    
    def _get_current_provider_from_config(self) -> str:
        """Get current provider name in agent config format (not mapped)."""
        if self.agent_config:
            return self.agent_config.get("provider", settings.LLM_MODEL_PROVIDER)
        return settings.LLM_MODEL_PROVIDER
    
    def invoke_with_fallback(self, state: Dict[str, Any], config: Dict[str, Any] = None) -> Dict[str, Any]:
        """Invoke agent executor with automatic fallback to alternate provider.
        
        If the initial provider fails or returns empty result, automatically
        falls back to the alternate provider from [WSO2_OPENAI, WSO2_BEDROCK].

        Args:
            state: State dictionary for agent invocation
            config: Optional config dictionary for agent invocation
            
        Returns:
            Result dictionary from agent executor
            
        Raises:
            Exception: If both initial and fallback providers fail
        """
        config = config or {}
        
        try:
            # Try initial provider
            logger.info(f"Invoking {self.__class__.__name__} with initial provider")
            result = self.agent_executor.invoke(state, config=config)
            
            # Check if result is empty or invalid
            agent_output = result.get("messages", [])[-1].content if result.get("messages") else None
            if not agent_output or not agent_output.strip():
                logger.warning(f"{self.__class__.__name__} returned empty result, attempting fallback")
                raise ValueError("Empty result from initial provider")
            
            return result
            
        except Exception as initial_error:
            # Fallback to alternate provider
            logger.warning(
                f"{self.__class__.__name__} initial invocation failed: {str(initial_error)}, "
                f"attempting fallback to alternate provider"
            )
            
            try:
                # Get current provider in agent config format
                current_provider = self._get_current_provider_from_config()
                logger.info(f"Current model provider: {current_provider}")

                # Get fallback provider
                fallback_provider = self._get_fallback_provider(current_provider)
                logger.info(f"Fallback model provider: {fallback_provider}")

                # todo: Get fallback model name from settings
                models_attr_name = f"{fallback_provider}_MODELS"
                fallback_model_name = getattr(settings, models_attr_name, None)
                if fallback_model_name:
                    logger.info(f"Using fallback model from {models_attr_name}: {fallback_model_name}")
                    logger.info(f"Fallback model name: {fallback_model_name}")

                    # Get configuration
                    reasoning_effort = self._get_reasoning_effort_from_config()
                    temperature = self._get_temperature_from_config()
                    streaming_enabled = self._get_streaming_enabled_from_config()

                    # Create fallback model loader
                    fallback_model_loader = get_model_loader(provider=fallback_provider)

                    # Build kwargs based on fallback provider capabilities
                    fallback_provider_upper = fallback_provider.upper()
                    load_kwargs = {
                        "model_name": fallback_model_name,
                        "temperature": temperature,
                    }

                    # Add provider-specific parameters
                    if fallback_provider_upper == "WSO2_OPENAI":
                        load_kwargs["streaming"] = streaming_enabled
                        if reasoning_effort:
                            load_kwargs["reasoning_effort"] = reasoning_effort
                    elif fallback_provider_upper == "WSO2_BEDROCK":
                        if reasoning_effort:
                            load_kwargs["reasoning_effort"] = reasoning_effort
                    elif fallback_provider_upper == "WSO2_GEMINI":
                        load_kwargs["streaming"] = streaming_enabled
                    elif fallback_provider_upper == "OPENAI":
                        if reasoning_effort:
                            load_kwargs["reasoning_effort"] = reasoning_effort

                    # Load fallback model with appropriate parameters
                    fallback_model = fallback_model_loader.load_model(**load_kwargs)
                    
                    logger.info(
                        f"{self.__class__.__name__} using fallback provider: {fallback_provider}, "
                        f"model: {fallback_model_name}"
                    )
                    
                    fallback_agent_executor = self._create_agent_with_model(fallback_model)
                    
                    # Retry with fallback model
                    result = fallback_agent_executor.invoke(state, config=config)
                    agent_output = result.get("messages", [])[-1].content if result.get("messages") else None
                    
                    if not agent_output or not agent_output.strip():
                        raise ValueError("Empty result from fallback provider")
                    
                    logger.info(
                        f"{self.__class__.__name__} completed successfully with fallback provider"
                    )
                    
                    return result
                    
            except Exception as fallback_error:
                logger.error(
                    f"{self.__class__.__name__} fallback also failed: {str(fallback_error)}"
                )
                # Re-raise the original error if fallback also fails
                raise initial_error
    
    def _create_agent_with_model(self, model) -> Any:
        """Create agent executor with a specific model.
        
        Args:
            model: The model to use for the agent executor
            
        Returns:
            Agent executor instance
        """
        from langgraph.prebuilt import create_react_agent
        
        # Check if agent has _dynamic_prompt method
        if hasattr(self, '_dynamic_prompt'):
            return create_react_agent(
                model=model,
                tools=[],
                prompt=self._dynamic_prompt,
            )
        else:
            # Fallback: create basic agent
            return create_react_agent(
                model=model,
                tools=[],
            )
