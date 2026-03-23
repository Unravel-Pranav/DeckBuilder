"""
Model Factory for Multi-Provider LLM Support

This module provides a factory pattern to dynamically select and load LLM models
from different providers with different routing mechanisms.

Supported Providers:
- WSO2_OPENAI: GPT models (OpenAI API) via WSO2 Gateway with streaming support
- WSO2_BEDROCK: Claude models (AWS Bedrock) via WSO2 Gateway
- WSO2_GEMINI: Gemini models (Google Gemini API) via WSO2 Gateway with streaming support
- OPENAI: GPT models via Direct OpenAI API (no gateway)

Architecture:
    WSO2_OPENAI Provider:
        Application → WSO2 Gateway → OpenAI API → GPT-4o/GPT-5 (with streaming)

    WSO2_BEDROCK Provider:
        Application → WSO2 Gateway → AWS Bedrock → Claude Sonnet

    WSO2_GEMINI Provider:
        Application → WSO2 Gateway → Google Gemini API → Gemini 2.5 Flash (with streaming)

    OPENAI Provider:
        Application → OpenAI API → GPT-4o/o1/etc (Direct, no streaming)

Usage:
    from hello.ml.utils.model_factory import get_model_loader, load_model

    # Get model loader instance (uses LLM_MODEL_PROVIDER from settings)
    loader = get_model_loader()

    # Load model with optional parameters
    model = load_model(model_name="gpt-4o", reasoning_effort="high")

    # Override provider
    model = load_model(provider="WSO2_CLAUDE")  # Use Claude via WSO2
"""

import sys
from typing import Optional, Union
from hello.ml.logger import GLOBAL_LOGGER as logger
from hello.ml.exception.custom_exception import MultiAgentWorkflowException
from hello.services.config import settings


def get_model_loader(provider: Optional[str] = None):
    """
    Factory function to get the appropriate model loader based on configuration.

    Args:
        provider: Optional provider override. If None, uses settings.LLM_MODEL_PROVIDER.
                 Options: "WSO2_OPENAI", "WSO2_BEDROCK", "WSO2_GEMINI", "OPENAI"
                 Legacy options also supported: "WSO2_GPT", "WSO2_CLAUDE", "GPT"

    Returns:
        Model loader instance:
        - WSO2OpenAIModelLoader: GPT models via WSO2 Gateway (OpenAI API) with streaming
        - WS02BedrockModelLoader: Claude models via WSO2 Gateway (AWS Bedrock)
        - WSO2GeminiModelLoader: Gemini models via WSO2 Gateway (Google Gemini API) with streaming
        - ModelLoader: GPT models via Direct OpenAI API (no streaming)

    Raises:
        ValueError: If invalid provider is specified
        MultiAgentWorkflowException: If model loader initialization fails

    Examples:
        # Use default provider from settings
        loader = get_model_loader()

        # Use GPT via WSO2 Gateway with streaming
        loader = get_model_loader(provider="WSO2_OPENAI")

        # Use Claude via WSO2 Gateway
        loader = get_model_loader(provider="WSO2_BEDROCK")

        # Use Gemini via WSO2 Gateway with streaming
        loader = get_model_loader(provider="WSO2_GEMINI")

        # Use direct OpenAI API
        loader = get_model_loader(provider="OPENAI")
    """
    try:
        # Determine provider
        provider_to_use = (provider or settings.LLM_MODEL_PROVIDER).upper()
        logger.info(f"Initializing model loader with provider: {provider_to_use}")

        # Import and return appropriate loader
        if provider_to_use == "WSO2_OPENAI":
            from hello.ml.utils.wso2_openai_model_loader import WSO2OpenAIModelLoader
            logger.info("Using WSO2OpenAIModelLoader: GPT models via WSO2 Gateway (OpenAI API) with streaming")
            return WSO2OpenAIModelLoader()

        elif provider_to_use == "WSO2_BEDROCK":
            from hello.ml.utils.wso2_bedrock_model_loader import WS02BedrockModelLoader
            logger.info("Using WS02BedrockModelLoader: Claude models via WSO2 Gateway (AWS Bedrock)")
            return WS02BedrockModelLoader()

        elif provider_to_use == "WSO2_GEMINI":
            from hello.ml.utils.wso2_gemini_model_loader import WSO2GeminiModelLoader
            logger.info("Using WSO2GeminiModelLoader: Gemini models via WSO2 Gateway (Google Gemini API) with streaming")
            return WSO2GeminiModelLoader()

        elif provider_to_use == "OPENAI":
            from hello.ml.utils.model_loader import ModelLoader
            logger.info("Using ModelLoader: GPT models via Direct OpenAI API (no streaming)")
            return ModelLoader()

        else:
            raise ValueError(
                f"Invalid LLM provider: {provider_to_use}. "
                f"Valid options are: WSO2_OPENAI, WSO2_BEDROCK, WSO2_GEMINI, OPENAI"
            )

    except ValueError as e:
        logger.error(f"Invalid provider configuration: {str(e)}")
        raise
    except Exception as e:
        error_msg = f"Error initializing model loader: {str(e)}"
        logger.error(error_msg)
        raise MultiAgentWorkflowException(error_msg, sys.exc_info())


def load_model(
    model_name: Optional[str] = None,
    reasoning_effort: Optional[str] = None,
    provider: Optional[str] = None,
    streaming: Optional[bool] = True,
    temperature: Optional[float] = None
) -> Union[object, None]:
    """
    Convenience function to load a model in one step.

    Args:
        model_name: Optional model name to override config. If None, uses config.
        reasoning_effort: Optional reasoning effort level ('low', 'medium', 'high').
                        If None, uses config value. If "none", loads without reasoning.
                        Note: Only applicable to OPENAI provider with o1 models and WSO2_BEDROCK.
        provider: Optional provider override. If None, uses settings.LLM_MODEL_PROVIDER.
                 Options: "WSO2_OPENAI", "WSO2_BEDROCK", "WSO2_GEMINI", "OPENAI"
        streaming: Optional streaming mode. Default: True for WSO2_OPENAI and WSO2_GEMINI, False for others.
                  Only applicable to WSO2_OPENAI and WSO2_GEMINI providers.
        temperature: Optional temperature override. If None, uses config value.

    Returns:
        Initialized language model instance

    Raises:
        MultiAgentWorkflowException: If model loading fails

    Examples:
        # Load default model from default provider with streaming enabled (default)
        model = load_model()

        # Load Claude via WSO2 Gateway
        model = load_model(model_name="claude-sonnet-4.5", provider="WSO2_BEDROCK")

        # Load GPT via WSO2 Gateway with streaming
        model = load_model(model_name="gpt-5", provider="WSO2_OPENAI", streaming=True)

        # Load Gemini via WSO2 Gateway with streaming
        model = load_model(model_name="gemini-2.5-flash", provider="WSO2_GEMINI", streaming=True)

        # Load GPT via WSO2 Gateway without streaming
        model = load_model(model_name="gpt-5", provider="WSO2_OPENAI", streaming=False)

        # Load GPT directly with reasoning (o1 models)
        model = load_model(model_name="o1", reasoning_effort="high", provider="OPENAI")
    """
    try:
        # Get appropriate loader
        loader = get_model_loader(provider)

        # Load and return model
        logger.info(f"Loading model: {model_name or settings.LLM_MODEL_NAME} with reasoning: {reasoning_effort or settings.LLM_MODEL_REASONING_EFFECT}, streaming: {streaming or settings.LLM_MODEL_STREAMING}")

        # Check if loader supports streaming parameter (WSO2OpenAIModelLoader)
        if hasattr(loader, 'load_model') and 'streaming' in loader.load_model.__code__.co_varnames:
            return loader.load_model(
                model_name=model_name,
                reasoning_effort=reasoning_effort,
                streaming=streaming,
                temperature=temperature
            )
        else:
            # For loaders that don't support streaming (WS02BedrockModelLoader, ModelLoader)
            return loader.load_model(
                model_name=model_name,
                reasoning_effort=reasoning_effort,
                temperature=temperature
            )

    except Exception as e:
        error_msg = f"Error loading model: {str(e)}"
        logger.error(error_msg)
        raise MultiAgentWorkflowException(error_msg, sys.exc_info())


def load_model_for_evaluator(
    model_name: Optional[str] = None,
    temperature: Optional[float] = None,
    provider: Optional[str] = None,
    streaming: Optional[bool] = False
) -> Union[object, None]:
    """
    Load model specifically configured for evaluation tasks.

    Args:
        model_name: Optional model name. If None, uses settings.EVAL_MODEL_NAME.
        temperature: Optional temperature. If None, uses settings.EVAL_MODEL_TEMPERATURE.
        provider: Optional provider override. If None, uses settings.LLM_MODEL_PROVIDER.
        streaming: Optional streaming mode. Default: False for evaluators (not needed).

    Returns:
        Initialized evaluator model instance

    Raises:
        MultiAgentWorkflowException: If model loading fails

    Examples:
        # Load evaluator model with defaults (no streaming)
        eval_model = load_model_for_evaluator()

        # Load specific evaluator model
        eval_model = load_model_for_evaluator(model_name="gpt-4o-mini", provider="WSO2_OPENAI")
    """
    try:
        # Get appropriate loader
        loader = get_model_loader(provider)

        # Load evaluator model
        logger.info(f"Loading evaluator model: {model_name or settings.EVAL_MODEL_NAME}, streaming: {streaming or settings.EVAL_MODEL_STREAMING}")

        # Check if loader supports streaming parameter (WSO2OpenAIModelLoader)
        if hasattr(loader, 'load_model_for_evaluator') and 'streaming' in loader.load_model_for_evaluator.__code__.co_varnames:
            return loader.load_model_for_evaluator(
                model_name=model_name,
                temperature=temperature,
                streaming=streaming
            )
        else:
            # For loaders that don't support streaming in evaluator
            return loader.load_model_for_evaluator(
                model_name=model_name,
                temperature=temperature
            )

    except Exception as e:
        error_msg = f"Error loading evaluator model: {str(e)}"
        logger.error(error_msg)
        raise MultiAgentWorkflowException(error_msg, sys.exc_info())


def get_provider_info() -> dict:
    """
    Get information about the currently configured provider.

    Returns:
        Dictionary containing provider information including:
        - provider: Provider name
        - description: What this provider does
        - model_class: Loader class used
        - gateway: Routing mechanism
        - models: Available models
        - features: Key capabilities

    Example:
        info = get_provider_info()
        logger.info(f"Provider: {info['provider']}")
        logger.info(f"Description: {info['description']}")
        logger.info(f"Gateway: {info['gateway']}")
    """
    provider = settings.LLM_MODEL_PROVIDER.upper()

    # Support legacy naming
    provider_mapping = {
        "WSO2": "WSO2_OPENAI",
        "WSO2_GPT": "WSO2_OPENAI",  # Legacy name
        "AWS": "WSO2_BEDROCK",
        "WSO2_CLAUDE": "WSO2_BEDROCK",  # Legacy name
        "GEMINI": "WSO2_GEMINI",  # Legacy name
        "GPT": "OPENAI"
    }
    provider = provider_mapping.get(provider, provider)

    provider_info = {
        "WSO2_OPENAI": {
            "provider": "WSO2_OPENAI",
            "description": "GPT models (OpenAI API) via WSO2 Gateway with streaming support",
            "model_class": "WSO2OpenAIModelLoader",
            "gateway": "WSO2 Gateway → OpenAI API",
            "models": ["gpt-5", "gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "o1", "o1-mini"],
            "features": [
                "OAuth2 authentication via WSO2",
                "Enterprise gateway routing",
                "OpenAI GPT models (GPT-5, GPT-4o, o1)",
                "Real-time streaming support",
                "Reasoning effort control (o1 models)",
                "Production-ready CBRE environment",
                "Request correlation tracking"
            ]
        },
        "WSO2_BEDROCK": {
            "provider": "WSO2_BEDROCK",
            "description": "Claude models (AWS Bedrock) via WSO2 Gateway",
            "model_class": "WS02BedrockModelLoader",
            "gateway": "WSO2 Gateway → AWS Bedrock",
            "models": ["claude-sonnet-4.5", "claude-sonnet-4", "claude-3.5-haiku"],
            "features": [
                "OAuth2 authentication via WSO2",
                "Enterprise gateway routing",
                "Claude Sonnet models from AWS Bedrock",
                "Extended thinking capabilities",
                "200K token context window",
                "Request correlation tracking"
            ]
        },
        "WSO2_GEMINI": {
            "provider": "WSO2_GEMINI",
            "description": "Gemini models (Google Gemini API) via WSO2 Gateway with streaming support",
            "model_class": "WSO2GeminiModelLoader",
            "gateway": "WSO2 Gateway → Google Gemini API",
            "models": ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"],
            "features": [
                "OAuth2 authentication via WSO2",
                "Enterprise gateway routing",
                "Google Gemini models (2.5 Flash, 2.0 Flash, 1.5 Pro)",
                "Real-time streaming support",
                "Advanced safety filters",
                "Production-ready CBRE environment",
                "Request correlation tracking",
                "Multimodal capabilities"
            ]
        },
        "OPENAI": {
            "provider": "OPENAI",
            "description": "GPT models via Direct OpenAI API",
            "model_class": "ModelLoader",
            "gateway": "Direct → OpenAI API (no gateway)",
            "models": ["gpt-4o", "gpt-4o-mini", "o1", "o1-mini"],
            "features": [
                "Direct OpenAI API connection",
                "API key authentication",
                "GPT-4o and o1 models",
                "Reasoning effort control (o1)",
                "Fastest response times",
                "No streaming support"
            ]
        }
    }

    return provider_info.get(provider, {
        "provider": provider,
        "description": "Unknown provider",
        "model_class": "Unknown",
        "gateway": "Unknown",
        "models": [],
        "features": []
    })


if __name__ == "__main__":
    # Test the factory
    logger.info("Testing Model Factory...")
    logger.info(f"Current provider from settings: {settings.LLM_MODEL_PROVIDER}")
    logger.info()

    # Get provider info
    info = get_provider_info()
    logger.info(f"Provider Info:")
    logger.info(f"  Name: {info['provider']}")
    logger.info(f"  Description: {info['description']}")
    logger.info(f"  Model Class: {info['model_class']}")
    logger.info(f"  Features: {', '.join(info['features'])}")
    logger.info()

    # Test loading model (uncomment to test)
    # try:
    #     model = load_model()
    #     logger.info(f"Successfully loaded model: {type(model)}")
    #     response = model.invoke("Hello! How are you?")
    #     logger.info(f"Model response: {response.content}")
    # except Exception as e:
    #     logger.info(f"Error testing model: {str(e)}")
