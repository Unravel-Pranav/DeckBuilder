"""
AWS Bedrock Claude Model Loader (WSO2 Integration)

This module provides LangChain-compatible access to Claude models via AWS Bedrock
through the WSO2 API gateway. It handles OAuth2 authentication and request/response
format conversion for seamless integration with existing agents.

Based on AWS Bedrock Claude API documentation:
- API Reference: https://docs.aws.amazon.com/bedrock/latest/APIReference/API_Operations_Amazon_Bedrock_Runtime.html
- Claude Parameters: https://docs.aws.amazon.com/bedrock/latest/userguide/model-parameters-claude.html
"""

import sys
import json
import uuid
import httpx
from typing import Optional, List, Dict, Any, Iterator, ClassVar, Tuple
import logging
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AIMessage
from langchain_core.messages.ai import UsageMetadata
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import llm

from hello.ml.logger import GLOBAL_LOGGER as logger
from hello.ml.exception.custom_exception import MultiAgentWorkflowException
from hello.services.config import settings
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)


class TransientAWSBedrockAuthError(Exception):
    """Represents a transient error when obtaining AWS Bedrock auth token via WSO2."""


class TransientAWSBedrockRequestError(Exception):
    """Represents a transient error during AWS Bedrock request via WSO2."""


class WSO2BedrockClaudeChatModel(BaseChatModel):
    """
    LangChain-compatible chat model for Claude via AWS Bedrock through WSO2 gateway.
    
    This class implements the BaseChatModel interface and handles:
    - Message format conversion (LangChain -> Bedrock Claude format)
    - HTTP requests to WSO2 gateway
    - Response parsing (Bedrock Claude -> LangChain format)
    - Error handling and retries
    """
    
    # Model configuration
    model_name: str = Field(default="claude-sonnet-4.5")
    deployment_name: str = Field(default="")
    api_endpoint: str = Field(default="")
    auth_token: str = Field(default="")
    max_tokens: int = Field(default=4096)
    temperature: float = Field(default=0.7)
    timeout: int = Field(default=600)
    max_retries: int = Field(default=3)
    # Thinking / reasoning trace configuration
    thinking_enabled: bool = Field(default=True, description="Whether to request Claude thinking traces")
    thinking_budget_tokens: int = Field(default=10000, description="Thinking token budget when enabled")
    
    # Model aliases for easy switching
    MODEL_ALIASES: ClassVar[Dict[str, str]] = {
        "claude-sonnet-4": "global.anthropic.claude-sonnet-4-20250514-v1:0",
        "claude-sonnet-4.5": "global.anthropic.claude-sonnet-4-5-20250929-v1:0", 
        "claude-3.5-haiku": "us.anthropic.claude-3-5-haiku-20241022-v1:0"
    }
    
    class Config:
        arbitrary_types_allowed = True
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._deployment_name = settings.WSO2_BEDROCK_DEPLOYMENT_ID or self.MODEL_ALIASES.get(self.model_name, self.model_name)
        
        # Log initialization (avoid heavy logging during import)
        # Resolve max tokens from settings (fallback to 100000 if not provided)
        self.max_tokens = settings.LLM_MODEL_MAX_TOKENS
        logger.info(f"WSO2BedrockClaudeChatModel initialized - Model: {self.model_name}, Deployment: {self._deployment_name}, MaxTokens: {self.max_tokens}")
    
    @property
    def _llm_type(self) -> str:
        """Return identifier of llm type."""
        return "anthropic"
    
    def _convert_messages_to_bedrock_format(self, messages: List[BaseMessage]) -> Tuple[str, List[Dict[str, str]]]:
        """
        Convert LangChain messages to Bedrock Claude format.
        
        Args:
            messages: List of LangChain BaseMessage objects
            
        Returns:
            List of message dictionaries in Bedrock format
        """
        bedrock_messages = []
        system_message = ""
        for message in messages:
            if isinstance(message, SystemMessage):
                system_message = message.content
            elif isinstance(message, HumanMessage):
                bedrock_messages.append({
                    "role": "user",
                    "content": message.content
                })
            elif isinstance(message, AIMessage):
                bedrock_messages.append({
                    "role": "assistant",
                    "content": message.content
                })
        
        return system_message, bedrock_messages
    
    def _execute_request(self, endpoint_url: str, headers: Dict[str, str],
                        payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the actual HTTP request to AWS Bedrock.
        
        Returns:
            Response dictionary from Claude API
            
        Raises:
            TransientAWSBedrockRequestError: For retryable HTTP errors (5xx, 429)
            Exception: For non-retryable errors
        """
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                endpoint_url,
                json=payload,
                headers=headers
            )
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"Claude request successful - Response length: {len(str(result))}")
                return result
            else:
                error_msg = f"Claude request failed: {response.status_code} - {response.text}"
                logger.error(error_msg)
                
                # Check if error is retryable (5xx server errors or 429 rate limit)
                if response.status_code >= 500 or response.status_code == 429:
                    raise TransientAWSBedrockRequestError(error_msg)
                else:
                    raise Exception(error_msg)

    @retry(
        reraise=True,
        stop=stop_after_attempt(getattr(settings, 'WSO2_LLM_MAX_RETRIES', 5)),  # Retry up to 3 times (total 4 attempts)
        wait=wait_exponential(
            multiplier=getattr(settings, 'WSO2_LLM_BACKOFF_INITIAL', 5),
            max=getattr(settings, 'WSO2_LLM_BACKOFF_MAX', 60),
            exp_base=getattr(settings, 'WSO2_LLM_BACKOFF_EXP_BASE', 2.0),
        ),
        retry=retry_if_exception_type((
            TransientAWSBedrockRequestError,
            httpx.TimeoutException,
            httpx.ConnectError,
            httpx.NetworkError,
            httpx.ReadError,
        )),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    @llm(name="invoke_claude_llm", model_provider="anthropic")
    def _make_request(self, messages: List[BaseMessage], **kwargs) -> Dict[str, Any]:
        """
        Make HTTP request to WSO2 gateway for Claude model.
        
        This method retries up to 3 times on transient network errors before failing.
        
        Args:
            messages: List of LangChain messages
            **kwargs: Additional parameters (temperature, max_tokens, etc.)
            
        Returns:
            Response dictionary from Claude API
            
        Raises:
            Exception: If request fails after retries
        """
        try:
            # Convert messages to Bedrock format
            system_message, bedrock_messages = self._convert_messages_to_bedrock_format(messages)
            
            # Prepare request payload
            # Determine thinking config (allow per-call override)
            thinking_enabled = kwargs.get("thinking_enabled", self.thinking_enabled)
            thinking_budget = kwargs.get("thinking_budget_tokens", self.thinking_budget_tokens)

            effective_max_tokens = kwargs.get("max_tokens", self.max_tokens)
            payload = {
                "anthropic_version": "bedrock-2023-05-31",
                "system": system_message,
                "messages": bedrock_messages,
                "max_tokens": effective_max_tokens,
            }
            if thinking_enabled:
                payload["thinking"] = {"type": "enabled", "budget_tokens": thinking_budget}
            
            # Build endpoint URL
            endpoint_url = f"{self.api_endpoint}/aws/bedrock/model/{self._deployment_name}/invoke"
            
            uuid_str = str(uuid.uuid4())
            logger.info(f"Generated correlation ID for Claude request: {uuid_str}")
            # Prepare headers
            headers = {
                "Authorization": f"Bearer {self.auth_token}",
                "Content-Type": "application/json",
                "X-AI-WSO2-API": "true",
                "X-correlation-id": uuid_str
                 
            }
            
            logger.info(f"Making request to Claude via WSO2 - Endpoint: {endpoint_url}")
            logger.debug(f"Request payload: {json.dumps(payload, indent=2)}")
            
            # Execute request with retry logic
            result = self._execute_request(endpoint_url, headers, payload)
            
            # Process successful response
            model_name = self._deployment_name.split(".anthropic.")[-1]
            usage = result.get("usage", {})
            if usage:
                usage["total_tokens"] = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
            obs_metadata = {
                "temperature": 0,
                "max_tokens": effective_max_tokens,
                "anthropic_version": "bedrock-2023-05-31",
                "model_name": model_name,
            }
            if thinking_enabled:
                obs_metadata["thinking"] = {"type": "enabled", "budget_tokens": thinking_budget}
            LLMObs.annotate(
                span=None,
                input_data=[{"role": "system", "content": system_message}] + bedrock_messages,
                output_data=[{"role": "assistant", "content": result.get("content")[-1].get("text", "")}],
                metadata=obs_metadata,
                metrics=usage,
                tags={"model_provider": "anthropic", "integration": "bedrock"}
            )
            return result
                
        except (TransientAWSBedrockRequestError, httpx.TimeoutException, httpx.ConnectError, 
                httpx.NetworkError, httpx.ReadError):
            # These exceptions are retryable and will be caught by the retry decorator
            raise
        except Exception as e:
            # Non-retryable errors - log and re-raise
            error_msg = f"Unexpected error in Claude request: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)
    
    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """
        Generate response from Claude model.
        
        Args:
            messages: List of input messages
            stop: Optional list of stop sequences
            run_manager: Optional callback manager
            **kwargs: Additional generation parameters
            
        Returns:
            ChatResult with generated response
        """
        try:
            # Make request to Claude
            response = self._make_request(messages, **kwargs)
            # logger.info("--------------******************------------------")
            # logger.info(f"Response: {response}")
            # logger.info("--------------******************------------------")
            content = ""
            # Extract content from response
            text_parts = []
            thinking = None
            if "content" in response and len(response["content"]) > 0:

                for content_block in response["content"]:
                    if content_block.get("type") == "text":  # ✅ Only extracts 'text' type
                        text_parts.append(content_block.get("text", ""))

                message_content = response.get("content", [])
                # Extract thinking content
                thinking_blocks = [
                    block for block in message_content if block.get("type") == "thinking"
                ]
                if thinking_blocks:
                    # Get the first thinking block (there's typically just one)
                    thinking_block = thinking_blocks[0]
                    thinking = {
                        "text": thinking_block.get("thinking", ""),
                        "signature": thinking_block.get("signature", ""),
                    }

            if text_parts:
                content = "\n".join(text_parts)
            else:
                content = "No response content received from Claude"
                logger.warning("Empty response content from Claude")
            
            # logger.info("--------------**********content from claude********------------------")
            # logger.info(f"Content: {content}")
            # logger.info("--------------******************------------------")
            
            # Log usage if available
            if "usage" in response:
                usage = response["usage"]
                logger.info(f"Claude usage - Input tokens: {usage.get('input_tokens', 0)}, Output tokens: {usage.get('output_tokens', 0)}")

            if usage := response.get("usage"):
                input_tokens = usage.get("input_tokens", 0)
                output_tokens = usage.get("output_tokens", 0)
                cache_read_input_tokens = usage.get("cache_read_input_tokens", 0)
                cache_write_input_tokens = usage.get("cache_creation_input_tokens", 0)
                usage_metadata = UsageMetadata(
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    input_token_details={
                        "cache_read": cache_read_input_tokens,
                        "cache_creation": cache_write_input_tokens,
                    },
                    total_tokens=usage.get("total_tokens", input_tokens + output_tokens),
                )
                lc_usage = {
                    "prompt_tokens": input_tokens,
                    "completion_tokens": output_tokens,
                    "total_tokens": usage.get("total_tokens", input_tokens + output_tokens),
                }
            else:
                lc_usage = {}
                usage_metadata = None

            # logger.info("--------------******************------------------")
            # logger.info(f"Usage Metadata: {usage_metadata}")
            # logger.info("--------------******************------------------")

            llm_output = {
                # keys consumed by get_bedrock_anthropic_callback()
                "model_id": response.get("model_id"),
                "model_name": response.get("model_id"),
                "usage": lc_usage,
                # optional observability
                "provider": "aws.bedrock.anthropic",
                "raw_response": response,
                "stop_reason": response.get("stop_reason"),
                "thinking": thinking,
            }

            msg = AIMessage(
                content=content,
                additional_kwargs=response,
                usage_metadata=usage_metadata,
            )
            generation = ChatGeneration(message=msg,)

            # logger.info("--------------******************------------------")
            # logger.info(f"Generation: {generation}")
            # logger.info("--------------******************------------------")

            return ChatResult(generations=[generation], llm_output=llm_output,)
            
        except Exception as e:
            error_msg = f"Error generating Claude response: {str(e)}"
            logger.error(error_msg)
            raise MultiAgentWorkflowException(error_msg, sys.exc_info())
    
    def _stream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> Iterator[ChatGeneration]:
        """
        Stream response from Claude model (not implemented for Bedrock).
        
        Args:
            messages: List of input messages
            stop: Optional list of stop sequences
            run_manager: Optional callback manager
            **kwargs: Additional generation parameters
            
        Yields:
            ChatGeneration objects
            
        Note:
            Streaming is not supported in the current Bedrock implementation.
            This method falls back to regular generation.
        """
        logger.warning("Streaming not supported for Bedrock Claude - falling back to regular generation")
        
        # Fall back to regular generation
        result = self._generate(messages, stop, run_manager, **kwargs)
        for generation in result.generations:
            yield generation


class WS02BedrockModelLoader:
    """
    Model loader for Claude models via AWS Bedrock through WSO2 gateway.

    This class handles:
    - OAuth2 authentication with WSO2
    - Model initialization and configuration
    - Model aliasing for easy switching
    """
    
    def _classify_token_response(self, status_code: int) -> str:
        """Classify token endpoint HTTP status into success/transient/fatal."""
        if status_code == 200:
            return "success"
        if status_code in {429, 500, 502, 503, 504}:
            logger.info(f"Classifying response as transient for status code: {status_code}")
            return "transient"
        return "fatal"

    @retry(
        reraise=True,
        stop=stop_after_attempt(getattr(settings, 'WSO2_TOKEN_MAX_RETRIES', 5)),
        wait=wait_exponential(
            multiplier=getattr(settings, 'WSO2_TOKEN_BACKOFF_INITIAL', 5),
            max=getattr(settings, 'WSO2_TOKEN_BACKOFF_MAX', 60),
            exp_base=getattr(settings, 'WSO2_TOKEN_BACKOFF_EXP_BASE', 2.0),
        ),
        retry=retry_if_exception_type((TransientAWSBedrockAuthError, httpx.TimeoutException, httpx.ConnectError)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def _get_access_token(self, client_id: str, client_secret: str, auth_endpoint: str) -> str:
        """Obtain AWS Bedrock access token via WSO2 with exponential backoff on transient errors."""
        try:
            with httpx.Client(timeout=20) as client:
                response = client.post(
                    auth_endpoint,
                    data={
                        'grant_type': 'client_credentials',
                        'client_id': client_id,
                        'client_secret': client_secret
                    }
                )
            logger.info(f"WSO2 Token Endpoint Response Status: {response.status_code}")
        except httpx.ConnectError as e:
            logger.warning(f"Transient network error during token fetch: {e}")
            raise TransientAWSBedrockAuthError(str(e))
        except httpx.TimeoutException as e:
            logger.warning(f"Transient timeout during token fetch: {e}")
            raise TransientAWSBedrockAuthError("timeout")
        except Exception as e:
            logger.error(f"Unexpected error calling token endpoint: {e}")
            raise

        classification = self._classify_token_response(response.status_code)
        if classification == "success":
            try:
                data = response.json()
                token = data['access_token']
            except Exception as e:
                logger.warning(f"Malformed JSON in token response, treating as transient: {e}")
                raise TransientAWSBedrockAuthError("malformed-json")
            logger.info("Successfully obtained WSO2 access token for AWS Bedrock")
            return token
        elif classification == "transient":
            logger.warning(f"Transient token endpoint response {response.status_code}: {response.text[:300]}")
            raise TransientAWSBedrockAuthError(f"status-{response.status_code}")
        else:
            logger.error(f"Fatal token endpoint response {response.status_code}: {response.text[:300]}")
            raise Exception(
                f'Failed to obtain AWS Bedrock access token (fatal): {response.status_code} - {response.text}'
            )
    
    def load_model(self, model_name: Optional[str] = None, 
                   reasoning_effort: Optional[str] = None, 
                   temperature: Optional[float] = None, 
                   streaming: Optional[bool] = None,
                   max_tokens: Optional[int] = None,
                   timeout: Optional[int] = None,
                   max_retries: Optional[int] = None) -> WSO2BedrockClaudeChatModel:
        """
        Load Claude model via AWS Bedrock through WSO2 gateway.
        
        Args:
            model_name: Optional model name/alias. If None, uses config.
            reasoning_effort: Optional reasoning effort level (not used for Claude).
                            Kept for compatibility with other model loaders.
            
        Returns:
            WSO2BedrockClaudeChatModel: Initialized LangChain-compatible model instance.
            
        Raises:
            Exception: If model loading fails.
        """
        try:
            logger.info("Loading Claude model via AWS Bedrock through WSO2 gateway")
            
            # Get model configuration
            model_name_to_load = model_name or settings.LLM_MODEL_NAME
            temperature_to_use = temperature or settings.LLM_MODEL_TEMPERATURE
            max_tokens_to_use = max_tokens or settings.LLM_MODEL_MAX_TOKENS
            timeout_to_use = timeout or settings.LLM_MODEL_TIMEOUT
            max_retries_to_use = max_retries or settings.LLM_MODEL_MAX_RETRIES

            thinking_enabled = False
            thinking_budget_tokens = 0
            # Log reasoning effort (not applicable to Claude but kept for compatibility)
            if reasoning_effort is not None:
                if reasoning_effort.lower() == "low":
                    thinking_enabled = True
                    thinking_budget_tokens = settings.WSO2_BEDROCK_THINKING_BUDGET_LOW or 2000
                    logger.info(f"Thinking enabled with low budget for Claude model with reasoning effort 'low', tokens: {thinking_budget_tokens}")
                elif reasoning_effort.lower() == "medium":
                    thinking_enabled = True
                    thinking_budget_tokens = settings.WSO2_BEDROCK_THINKING_BUDGET_MEDIUM or 5000
                    logger.info(f"Thinking enabled with medium budget for Claude model with reasoning effort 'medium', tokens: {thinking_budget_tokens}")
                elif reasoning_effort.lower() == "high":
                    thinking_enabled = True
                    thinking_budget_tokens = settings.WSO2_BEDROCK_THINKING_BUDGET_HIGH or 10000
                    logger.info(f"Thinking enabled with high budget for Claude model with reasoning effort 'high', tokens: {thinking_budget_tokens}")
                else:
                    logger.warning(f"Unknown reasoning effort level '{reasoning_effort}' for Claude model - defaulting to no thinking")
            else:
                logger.info("No reasoning effort specified - defaulting to no thinking for Claude model")

            logger.info(f"Max tokens for Claude model set to: {max_tokens_to_use}")


            logger.info(f"AWS Bedrock Claude configuration - Model: {model_name_to_load}")
            
            # Get AWS Bedrock configuration
            api_endpoint = settings.WSO2_BEDROCK_API_ENDPOINT
            auth_endpoint = settings.WSO2_BEDROCK_AUTH_ENDPOINT
            
            if not api_endpoint or not auth_endpoint:
                raise ValueError(
                    "WSO2_BEDROCK_API_ENDPOINT and WSO2_BEDROCK_AUTH_ENDPOINT must be configured"
                )
            
            # Get WSO2 client credentials
            client_id = settings.WSO2_BEDROCK_CLIENT_ID
            client_secret = settings.WSO2_BEDROCK_CLIENT_SECRET
            
            if not client_id or not client_secret:
                raise ValueError(
                    "WSO2_BEDROCK_CLIENT_ID and WSO2_BEDROCK_CLIENT_SECRET must be configured"
                )
            
            logger.info(f"Connecting to WSO2 gateway for AWS Bedrock at: {api_endpoint}")
            logger.info(f"Using client ID: {client_id[:8]}... (masked)")
            

            # Get OAuth2 access token
            access_token = self._get_access_token(client_id, client_secret, auth_endpoint)
            
            # Initialize Claude model
            model = WSO2BedrockClaudeChatModel(
                model_name=model_name_to_load,
                api_endpoint=api_endpoint,
                auth_token=access_token,
                max_tokens=max_tokens_to_use,
                temperature=temperature_to_use,
                timeout=timeout_to_use,
                max_retries=max_retries_to_use,
                thinking_enabled=thinking_enabled,
                thinking_budget_tokens=thinking_budget_tokens
            )
            
            logger.info(f"Successfully loaded Claude model via AWS Bedrock: {model_name_to_load}")
            logger.info(f'Model temperature set to: {temperature_to_use}')
            return model
            
        except Exception as e:
            MultiAgentWorkflowException.log_exception(e, "load_model_aws_bedrock")
            raise MultiAgentWorkflowException("Error in load_model via AWS Bedrock", sys.exc_info())

    def load_model_for_evaluator(self, model_name: Optional[str] = None, 
                                 temperature: Optional[float] = None, 
                                 streaming: Optional[bool] = False,
                                 max_tokens: Optional[int] = None,
                                 timeout: Optional[int] = None,
                                 max_retries: Optional[int] = None,) -> WSO2BedrockClaudeChatModel:
        """Load Claude model specifically for evaluation tasks.

        Uses evaluation-focused settings (EVAL_MODEL_NAME, EVAL_MODEL_TEMPERATURE) allowing
        separation from interactive generation parameters.

        Args:
            model_name: Optional explicit model/alias override. If None, uses settings.EVAL_MODEL_NAME.

        Returns:
            WSO2BedrockClaudeChatModel configured for evaluation.
        """
        try:
            logger.info("Loading Claude evaluator model via AWS Bedrock through WSO2 gateway")

            # Resolve evaluator model name precedence: explicit override then config
            model_name_to_load = model_name or settings.EVAL_MODEL_NAME
            temperature_to_use = temperature or settings.EVAL_MODEL_TEMPERATURE
            max_tokens_to_use = max_tokens or settings.EVAL_MODEL_MAX_TOKENS
            timeout_to_use = timeout or settings.EVAL_MODEL_TIMEOUT
            max_retries_to_use = max_retries or settings.EVAL_MODEL_MAX_RETRIES

            thinking_enabled = False
            thinking_budget_tokens = 0
            if not thinking_enabled:
                logger.info("Evaluator models typically do not use reasoning effort settings - defaulting to no thinking")

            if not model_name_to_load:
                raise ValueError("No evaluator model name configured (EVAL_MODEL_NAME or LLM_MODEL_NAME)")

            logger.info(f"AWS Bedrock Claude configuration - Model: {model_name_to_load}")

            # Fetch endpoints
            api_endpoint = settings.WSO2_BEDROCK_API_ENDPOINT
            auth_endpoint = settings.WSO2_BEDROCK_AUTH_ENDPOINT
            if not api_endpoint or not auth_endpoint:
                raise ValueError("WSO2_BEDROCK_API_ENDPOINT and WSO2_BEDROCK_AUTH_ENDPOINT must be configured for evaluator")

            # Credentials
            client_id = settings.WSO2_BEDROCK_CLIENT_ID
            client_secret = settings.WSO2_BEDROCK_CLIENT_SECRET
            if not client_id or not client_secret:
                raise ValueError("WSO2_BEDROCK_CLIENT_ID and WSO2_BEDROCK_CLIENT_SECRET must be configured for evaluator")

            logger.info(f"Connecting to WSO2 gateway for WSO2 Bedrock evaluator at: {api_endpoint}")
            logger.info(f"Using client ID: {client_id[:8]}... (masked)")

            access_token = self._get_access_token(client_id, client_secret, auth_endpoint)


            # Initialize Claude model
            model = WSO2BedrockClaudeChatModel(
                model_name=model_name_to_load,
                api_endpoint=api_endpoint,
                auth_token=access_token,
                max_tokens=max_tokens_to_use,
                temperature=temperature_to_use,
                timeout=timeout_to_use,
                max_retries=max_retries_to_use,
                thinking_enabled=thinking_enabled,
                thinking_budget_tokens=thinking_budget_tokens
            )

            logger.info(f"Successfully loaded Claude evaluator model via WSO2 Bedrock: {model_name_to_load} (temperature={temperature_to_use})")
            return model

        except Exception as e:
            MultiAgentWorkflowException.log_exception(e, "load_model_for_evaluator_wso2_bedrock")
            raise MultiAgentWorkflowException("Error in load_model_for_evaluator via WSO2 Bedrock", sys.exc_info())


if __name__ == "__main__":
    # Test the model loader
    try:
        loader = WS02BedrockModelLoader()
        model = loader.load_model("claude-sonnet-4.5", reasoning_effort="high")
        if model.thinking_enabled:
            print("Thinking enabled?", model.thinking_enabled)
            print("Thinking budget:", model.thinking_budget_tokens)
        # # Test with a simple message
        response = model.invoke("Hello! Can you tell me a short joke?")
        print(f"Claude Response: {response.content}")
        
    except Exception as e:
        print(f"Error testing AWS Bedrock Claude model loader: {str(e)}")
        import traceback
        traceback.print_exc()
