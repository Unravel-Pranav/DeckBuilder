"""
WSO2 GPT Model Loader (OpenAI Integration)

This module provides LangChain-compatible access to GPT models via OpenAI API
through the WSO2 API gateway. It handles OAuth2 authentication, streaming support,
and request/response format conversion for seamless integration with existing agents.

Based on OpenAI Chat Completion API:
- API Reference: https://platform.openai.com/docs/api-reference/chat
- Streaming: https://platform.openai.com/docs/api-reference/streaming
"""

import sys
import json
import uuid
import time
import httpx
from typing import Optional, List, Dict, Any, Iterator, ClassVar
import logging
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AIMessage
from langchain_core.messages.ai import UsageMetadata
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.outputs import ChatGeneration, ChatResult, ChatGenerationChunk
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

# https://platform.openai.com/docs/guides/prompt-caching#prompt-cache-retention
prompt_retention_supported_models = ["gpt-5.1", "gpt-5.1-codex", "gpt-5.1-codex-mini", "gpt-5.1-chat-latest", "gpt-5",
                                     "gpt-5-codex", "gpt-4.1"]

class TransientWSO2GPTAuthError(Exception):
    """Represents a transient error when obtaining GPT auth token via WSO2."""


class TransientWSO2GPTStreamingError(Exception):
    """Represents a transient error during GPT streaming request via WSO2."""


class ContentFilterException(Exception):
    """
    Represents a content filter violation from Azure OpenAI.

    This exception is NOT retryable - it indicates the prompt triggered
    Azure's content management policy and should be returned to the user
    as a readable error message.
    """

    def __init__(self, user_message: str, raw_error: dict = None):
        self.user_message = user_message
        self.raw_error = raw_error or {}
        super().__init__(user_message)

    @classmethod
    def from_response(cls, response_text: str) -> Optional["ContentFilterException"]:
        """
        Parse response text and create ContentFilterException if it's a content filter error.

        Args:
            response_text: Raw response text from the API

        Returns:
            ContentFilterException if content filter error detected, None otherwise
        """
        try:
            error_data = json.loads(response_text)
            error = error_data.get("error", {})

            # Check if this is a content filter error
            if error.get("code") == "content_filter" or (
                error.get("innererror", {}).get("code") == "ResponsibleAIPolicyViolation"
            ):
                # Build user-friendly message
                user_message = cls._format_user_message(error)
                return cls(user_message, error_data)

            return None
        except (json.JSONDecodeError, KeyError, TypeError):
            return None

    @staticmethod
    def _format_user_message(error: dict) -> str:
        """Format the error into a user-readable message."""
        innererror = error.get("innererror", {})
        content_filter_result = innererror.get("content_filter_result", {})

        # Find which filters were triggered
        triggered_filters = []
        for filter_name, filter_data in content_filter_result.items():
            if isinstance(filter_data, dict):
                if filter_data.get("filtered") or filter_data.get("detected"):
                    triggered_filters.append(filter_name)

        # Build the user message
        base_message = (
            "⚠️ **Content Policy Notice**\n\n"
            "Your request could not be processed because it triggered the content safety filter. "
        )

        if triggered_filters:
            filter_names = ", ".join(triggered_filters)
            base_message += f"The following content categories were flagged: **{filter_names}**.\n\n"
        else:
            base_message += "\n\n"

        base_message += (
            "**What you can do:**\n"
            "- Review and modify your prompt to ensure it complies with content guidelines\n"
            "- Rephrase your request using different wording\n"
            "- Remove any content that might be interpreted as inappropriate\n\n"
            "If you believe this is a mistake, please contact support."
        )

        return base_message


class WSO2OpenAIChatModel(BaseChatModel):
    """
    LangChain-compatible chat model for GPT via OpenAI API through WSO2 gateway.

    This class implements the BaseChatModel interface and handles:
    - Message format conversion (LangChain -> OpenAI format)
    - HTTP requests to WSO2 gateway
    - Response parsing (OpenAI -> LangChain format)
    - Streaming support for real-time responses
    - Error handling and retries
    """

    # Model configuration
    model_name: str = Field(default="gpt-5.1")
    api_endpoint: str = Field(default="")
    auth_token: str = Field(default="")
    max_tokens: int = Field(default=4096)
    temperature: float = Field(default=0.7)
    timeout: int = Field(default=600)
    max_retries: int = Field(default=3)
    streaming: bool = Field(default=False, description="Whether to enable streaming responses")
    api_version: str = Field(default="2025-01-01-preview", description="API version for OpenAI deployment endpoint")

    # Reasoning effort configuration (for o1 models)
    reasoning_effort: Optional[str] = Field(default=None, description="Reasoning effort level: 'low', 'medium', 'high'")

    # Model aliases for easy switching
    MODEL_ALIASES: ClassVar[Dict[str, str]] = {
        "gpt-4": "gpt-4",
        "gpt-4.1": "gpt-4.1",
        "gpt-4-turbo": "gpt-4-turbo-preview",
        "gpt-4o": "gpt-4o",
        "gpt-4o-mini": "gpt-4o-mini",
        "gpt-5": "gpt-5",
        "gpt-5.1": "gpt-5.1",
        "o1": "o1",
        "o1-mini": "o1-mini",
        "o1-preview": "o1-preview"
    }

    class Config:
        arbitrary_types_allowed = True

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Resolve model name from alias if needed
        self._model_name = self.MODEL_ALIASES.get(self.model_name, self.model_name)

        # Log initialization
        try:
            logger.info(f"WSO2OpenAIChatModel initialized - Model: {self.model_name}, MaxTokens: {self.max_tokens}, Streaming: {self.streaming}")
        except:
            # Fallback if logger is not ready
            print(f"WSO2OpenAIChatModel initialized - Model: {self.model_name}, MaxTokens: {self.max_tokens}, Streaming: {self.streaming}")

    @property
    def _llm_type(self) -> str:
        """Return identifier of llm type."""
        return "openai"

    def _convert_messages_to_openai_format(self, messages: List[BaseMessage]) -> List[Dict[str, str]]:
        """
        Convert LangChain messages to OpenAI format.

        Args:
            messages: List of LangChain BaseMessage objects

        Returns:
            List of message dictionaries in OpenAI format
        """
        openai_messages = []
        for message in messages:
            if isinstance(message, SystemMessage):
                openai_messages.append({
                    "role": "system",
                    "content": message.content
                })
            elif isinstance(message, HumanMessage):
                openai_messages.append({
                    "role": "user",
                    "content": message.content
                })
            elif isinstance(message, AIMessage):
                openai_messages.append({
                    "role": "assistant",
                    "content": message.content
                })

        return openai_messages

    @retry(
        reraise=True,
        stop=stop_after_attempt(getattr(settings, 'WSO2_LLM_MAX_RETRIES', 5)),  # Retry up to 3 times (total 4 attempts)
        wait=wait_exponential(
            multiplier=getattr(settings, 'WSO2_LLM_BACKOFF_INITIAL', 5),
            max=getattr(settings, 'WSO2_LLM_BACKOFF_MAX', 60),
            exp_base=getattr(settings, 'WSO2_LLM_BACKOFF_EXP_BASE', 2.0),
        ),
        retry=retry_if_exception_type((
            TransientWSO2GPTStreamingError,
            httpx.TimeoutException,
            httpx.ConnectError,
            httpx.NetworkError,
            httpx.ReadError,
        )),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    @llm(name="invoke_gpt_llm", model_provider="openai")
    def _make_request(self, messages: List[BaseMessage], stream: bool = True, **kwargs) -> Dict[str, Any]:
        """
        Make HTTP request to WSO2 gateway for GPT model.

        Args:
            messages: List of LangChain messages
            stream: Whether to enable streaming
            **kwargs: Additional parameters (temperature, max_tokens, etc.)

        Returns:
            Response dictionary from OpenAI API (or full content if streaming)

        Raises:
            Exception: If request fails
        """
        try:
            # Convert messages to OpenAI format
            stream = self.streaming
            logger.info(f"Streaming set to: {stream}")
            openai_messages = self._convert_messages_to_openai_format(messages)

            # Prepare request payload
            effective_max_tokens = kwargs.get("max_tokens", self.max_tokens)
            payload = {
                "model": self._model_name,
                "messages": openai_messages,
            }

            # Structured outputs (OpenAI Chat Completions)
            # If provided via LangChain .bind(response_format=...), pass through to the gateway.
            response_format = kwargs.get("response_format")
            if response_format is not None:
                payload["response_format"] = response_format

            # Add reasoning effort if specified (for o1 models)
            if self.reasoning_effort:
                payload["reasoning_effort"] = self.reasoning_effort

            if self.temperature:
                payload["temperature"] = self.temperature

            # Build endpoint URL dynamically using selected model name and configured API version
            endpoint_url = (
                f"{self.api_endpoint}/openai/deployments/{self._model_name}/chat/completions?api-version={self.api_version}"
            )

            # Prepare observability metadata
            obs_metadata = {
                "temperature": payload.get("temperature", self.temperature),
                "max_tokens": effective_max_tokens,
                "model_name": self._model_name,
            }
            if self.reasoning_effort:
                obs_metadata["reasoning_effort"] = self.reasoning_effort

            uuid_str = str(uuid.uuid4())
            logger.info(f"Generated correlation ID for GPT request: {uuid_str}")

            # Prepare headers
            headers = {
                "Authorization": f"Bearer {self.auth_token}",
                "Content-Type": "application/json",
                "X-AI-WSO2-API": "true",
                "X-correlation-id": uuid_str
            }

            # if self.model_name in prompt_retention_supported_models:
            #     payload["prompt_cache_retention"] = "24h"

            payload["prompt_cache_key"] = "research_report_summary_cbre"

            logger.info(f"Making request to GPT via WSO2 - Endpoint: {endpoint_url}, Streaming: {stream}")
            logger.debug(f"Request payload: {json.dumps(payload, indent=2)}")
            if stream:
                payload["stream"] = True
                payload["stream_options"] = {"include_usage": True}
                # Handle streaming response
                response = self._handle_streaming_request(endpoint_url=endpoint_url, headers=headers, payload=payload)
            else:
                # Handle regular response
                response = self._handle_regular_request(endpoint_url=endpoint_url, headers=headers, payload=payload)

            # Log usage for observability
            usage = response.get("usage", {})
            # Extract response content
            content = ""
            if "choices" in response and len(response["choices"]) > 0:
                content = response["choices"][0].get("message", {}).get("content", "")

            datadog_usage_obj = {"input_tokens": usage.get("prompt_tokens", 0), "output_tokens": usage.get("completion_tokens", 0),
                         "total_tokens": usage.get('total_tokens', usage.get("prompt_tokens", 0)+ usage.get("completion_tokens", 0))}

            if usage.get("prompt_tokens_details"):
                datadog_usage_obj["cache_read_input_tokens"] = usage["prompt_tokens_details"].get("cached_tokens", 0)

            # Annotate metrics to Datadog
            LLMObs.annotate(
                span=None,
                input_data=openai_messages,
                output_data=[{"role": "assistant", "content": content}],
                metadata=obs_metadata,
                metrics=datadog_usage_obj,
                tags={"model_provider": "openai", "integration": "openai"}
            )
            return response

        except ContentFilterException:
            # Let ContentFilterException pass through without wrapping
            # This will be handled by _generate to return user-friendly message
            raise
        except TransientWSO2GPTStreamingError:
            # Let TransientWSO2GPTStreamingError pass through for retry logic
            raise
        except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError, httpx.ReadError):
            # Let httpx transient errors pass through for retry logic
            raise
        except httpx.RequestError as e:
            error_msg = f"GPT request error: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)
        except Exception as e:
            error_msg = f"Unexpected error in GPT request: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)

    def _execute_regular_request(self, endpoint_url: str, headers: Dict[str, str],
                                 payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the actual non-streaming HTTP request.

        Returns:
            Response dictionary from OpenAI API

        Raises:
            TransientWSO2GPTStreamingError: For all non-200/non-400 status codes (retryable).
            ContentFilterException: For 400 with content filter violation (not retryable).
            Exception: For 400 without content filter (not retryable).
        """
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                endpoint_url,
                json=payload,
                headers=headers
            )
            if response.status_code == 200:
                result = response.json()
                logger.info(f"GPT request successful - Response length: {len(str(result))}")
                return result
            else:
                error_msg = f"GPT request failed: {response.status_code} - {response.text}"
                logger.error(error_msg)

                # Check for content filter error (400 status) - not retryable
                if response.status_code == 400:
                    content_filter_error = ContentFilterException.from_response(response.text)
                    if content_filter_error:
                        logger.warning(f"Content filter triggered: {content_filter_error.user_message[:100]}...")
                        raise content_filter_error
                    # Non-content-filter 400 errors are not retryable (client error)
                    raise Exception(error_msg)

                # Todo:  Need to verify for which status codes we need to raise TransientWSO2GPTStreamingError

                raise TransientWSO2GPTStreamingError(error_msg)

    def _handle_regular_request(self, endpoint_url: str, headers: Dict[str, str],
                               payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle non-streaming HTTP request and return response.

        This method retries up to 3 times on transient network errors before failing.
        """
        # Execute regular request with retry logic
        result = self._execute_regular_request(endpoint_url, headers, payload)
        return result

    def _execute_streaming_request(self, endpoint_url: str, headers: Dict[str, str],
                                   payload: Dict[str, Any]) -> tuple[str, int, dict, Optional[str]]:
        """
        Execute the actual streaming HTTP request.

        Returns:
            Tuple of (full_content, chunk_count, usage, finish_reason)

        Raises:
            TransientWSO2GPTStreamingError: For all non-200/non-400 status codes (retryable).
            ContentFilterException: For 400 with content filter violation (not retryable).
            Exception: For 400 without content filter (not retryable).
        """
        full_content = ""
        chunk_count = 0
        usage = {}
        finish_reason = None

        with httpx.Client(timeout=self.timeout) as client:
            with client.stream("POST", endpoint_url, json=payload, headers=headers) as response:
                if response.status_code != 200:
                    # Read the full error response body
                    try:
                        response.read()
                        error_body = ""
                        for chunk in response.iter_bytes():
                            error_body += chunk.decode('utf-8')
                        error_msg = f"GPT streaming request failed: {response.status_code} error_text- {response.text} - error_body- {error_body}"
                    except Exception:
                        error_body = response.text
                        error_msg = f"GPT streaming request failed: {response.status_code} - {response.text}"
                    logger.error(error_msg)

                    # Check for content filter error (400 status) - not retryable
                    if response.status_code == 400:
                        content_filter_error = ContentFilterException.from_response(error_body)
                        if content_filter_error:
                            logger.warning(f"Content filter triggered: {content_filter_error.user_message[:100]}...")
                            raise content_filter_error
                        # Non-content-filter 400 errors are not retryable (client error)
                        raise Exception(error_msg)

                    # Todo:  Need to verify for which status codes we need to raise TransientWSO2GPTStreamingError

                    raise TransientWSO2GPTStreamingError(error_msg)

                logger.info(f"Response Status Code: {response.status_code}")
                logger.info("=" * 60)
                logger.info("STREAMING CONTENT:")
                logger.info("=" * 60)

                try:
                    for line in response.iter_lines():
                        if line:
                            chunk_count += 1
                            line_str = line.strip()

                            if line_str.startswith('data: '):
                                data_str = line_str[6:]  # Remove 'data: ' prefix

                                if data_str.strip() == '[DONE]':
                                    logger.info("\n[STREAMING COMPLETED]")
                                    break

                                try:
                                    chunk_data = json.loads(data_str)

                                    if 'choices' in chunk_data and len(chunk_data['choices']) > 0:
                                        choice = chunk_data['choices'][0]

                                        # Extract content delta
                                        if 'delta' in choice and 'content' in choice['delta']:
                                            content_chunk = choice['delta']['content']
                                            full_content += content_chunk

                                        # Extract finish reason
                                        if 'finish_reason' in choice and choice['finish_reason']:
                                            finish_reason = choice['finish_reason']

                                    # Extract usage information (usually in the last chunk)
                                    if 'usage' in chunk_data:
                                        usage = chunk_data['usage']

                                except json.JSONDecodeError:
                                    continue  # Skip malformed JSON chunks

                except (httpx.ReadError, httpx.NetworkError, httpx.TimeoutException) as e:
                    # Retryable network errors during streaming
                    logger.error(f"Retryable streaming error: {e}")
                    raise
                except Exception as e:
                    # Non-retryable errors - log and re-raise
                    logger.error(f"Non-retryable streaming error: {e}")
                    raise

        return full_content, chunk_count, usage, finish_reason

    def _handle_streaming_request(self, endpoint_url: str, headers: Dict[str, str],
                                  payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle streaming HTTP request and return final response.

        This method retries up to 3 times on transient network errors before failing.
        """
        logger.info(f"Starting streaming request with timeout: {self.timeout}...")

        # Execute streaming request with retry logic
        full_content, chunk_count, usage, finish_reason = self._execute_streaming_request(
            endpoint_url, headers, payload
        )

        logger.info("\n" + "=" * 60)
        logger.info("STREAMING STATISTICS:")
        logger.info("=" * 60)
        logger.info(f"Full content length: {len(full_content)} characters")
        logger.info(f"Total chunks received: {chunk_count}")
        logger.info(f"Finish reason: {finish_reason}")

        # Construct OpenAI-style response from streamed content
        return {
            "id": str(uuid.uuid4()),
            "object": "chat.completion",
            "created": int(time.time()),
            "model": self._model_name,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": full_content
                    },
                    "finish_reason": finish_reason or "stop"
                }
            ],
            "usage": usage
        }

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """
        Generate response from GPT model.

        Args:
            messages: List of input messages
            stop: Optional list of stop sequences
            run_manager: Optional callback manager
            **kwargs: Additional generation parameters

        Returns:
            ChatResult with generated response
        """
        try:
            # Determine if streaming is enabled
            stream = kwargs.get("streaming", self.streaming)

            # Make request to GPT
            response = self._make_request(messages, stream=stream, **kwargs)

            # Extract content from response
            content = ""
            if "choices" in response and len(response["choices"]) > 0:
                content = response["choices"][0].get("message", {}).get("content", "")

            if not content:
                content = "No response content received from GPT"
                logger.warning("Empty response content from GPT")

            # Log usage if available
            if "usage" in response:
                usage = response["usage"]
                logger.info(f"GPT usage - Prompt tokens: {usage.get('prompt_tokens', 0)}, "
                          f"Completion tokens: {usage.get('completion_tokens', 0)}, "
                          f"Total tokens: {usage.get('total_tokens', 0)}")

            # Create usage metadata
            if usage := response.get("usage"):
                prompt_tokens = usage.get("prompt_tokens", 0)
                completion_tokens = usage.get("completion_tokens", 0)
                total_tokens = usage.get("total_tokens", usage.get('total_tokens', prompt_tokens + completion_tokens))

                usage_metadata = UsageMetadata(
                    input_tokens=prompt_tokens,
                    output_tokens=completion_tokens,
                    total_tokens=total_tokens,
                )
                lc_usage = {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                }
            else:
                lc_usage = {}
                usage_metadata = None

            llm_output = {
                "model_name": response.get("model", self._model_name),
                "usage": lc_usage,
                "provider": "wso2.openai",
                "raw_response": response,
                "finish_reason": response.get("choices", [{}])[0].get("finish_reason"),
            }

            msg = AIMessage(
                content=content,
                additional_kwargs=response,
                usage_metadata=usage_metadata,
            )
            generation = ChatGeneration(message=msg)

            return ChatResult(generations=[generation], llm_output=llm_output)

        except ContentFilterException as cfe:
            # Handle content filter error - return user-friendly message as response
            logger.warning(f"Content filter error caught in _generate: returning user message")

            # Create a response with the user-friendly error message
            llm_output = {
                "model_name": self._model_name,
                "usage": {},
                "provider": "wso2.openai",
                "finish_reason": "content_filter",
                "content_filter_error": True,
                "raw_error": cfe.raw_error,
            }

            msg = AIMessage(
                content=cfe.user_message,
                additional_kwargs={"content_filter_error": True, "raw_error": cfe.raw_error},
            )
            generation = ChatGeneration(message=msg)

            return ChatResult(generations=[generation], llm_output=llm_output)

        except Exception as e:
            error_msg = f"Error generating GPT response: {str(e)}"
            logger.error(error_msg)
            raise MultiAgentWorkflowException(error_msg, sys.exc_info())

    def _stream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        """
        Stream response from GPT model.

        Args:
            messages: List of input messages
            stop: Optional list of stop sequences
            run_manager: Optional callback manager
            **kwargs: Additional generation parameters

        Yields:
            ChatGenerationChunk objects
        """
        try:
            # Convert messages to OpenAI format
            openai_messages = self._convert_messages_to_openai_format(messages)

            # Prepare request payload
            effective_max_tokens = kwargs.get("max_tokens", self.max_tokens)
            payload = {
                "model": self._model_name,
                "messages": openai_messages,
                "temperature": kwargs.get("temperature", self.temperature),
                "max_tokens": effective_max_tokens,
                "stream": True
            }

            # Structured outputs passthrough for streaming mode as well
            response_format = kwargs.get("response_format")
            if response_format is not None:
                payload["response_format"] = response_format

            if self.reasoning_effort:
                payload["reasoning_effort"] = self.reasoning_effort

            # Determine API version for streaming endpoint
            api_version = getattr(settings, 'WSO2_OPENAI_API_VERSION', self.api_version)
            endpoint_url = (
                f"{self.api_endpoint}/openai/deployments/{self._model_name}/chat/completions?api-version={api_version}"
            )

            uuid_str = str(uuid.uuid4())
            headers = {
                "Authorization": f"Bearer {self.auth_token}",
                "Content-Type": "application/json",
                "X-AI-WSO2-API": "true",
                "X-correlation-id": uuid_str
            }

            logger.info(f"Starting streaming request to GPT via WSO2")

            with httpx.Client(timeout=self.timeout) as client:
                with client.stream("POST", endpoint_url, json=payload, headers=headers) as response:
                    if response.status_code != 200:
                        # Read the full error response
                        try:
                            response.read()
                            error_body = ""
                            for chunk in response.iter_bytes():
                                error_body += chunk.decode('utf-8')
                        except Exception:
                            error_body = response.text

                        error_msg = f"GPT streaming request failed: {response.status_code} - {error_body}"
                        logger.error(error_msg)

                        # Check for content filter error (400 status)
                        if response.status_code == 400:
                            content_filter_error = ContentFilterException.from_response(error_body)
                            if content_filter_error:
                                logger.warning(f"Content filter triggered in _stream")
                                raise content_filter_error

                        raise Exception(error_msg)

                    for line in response.iter_lines():
                        if line:
                            line_str = line.strip()

                            if line_str.startswith('data: '):
                                data_str = line_str[6:]

                                if data_str.strip() == '[DONE]':
                                    break

                                try:
                                    chunk_data = json.loads(data_str)

                                    if 'choices' in chunk_data and len(chunk_data['choices']) > 0:
                                        choice = chunk_data['choices'][0]

                                        if 'delta' in choice and 'content' in choice['delta']:
                                            content_chunk = choice['delta']['content']

                                            chunk_msg = AIMessage(content=content_chunk)
                                            chunk = ChatGenerationChunk(message=chunk_msg)

                                            if run_manager:
                                                run_manager.on_llm_new_token(content_chunk, chunk=chunk)

                                            yield chunk

                                except json.JSONDecodeError:
                                    continue

        except ContentFilterException as cfe:
            # Handle content filter error - yield user-friendly message as a chunk
            logger.warning(f"Content filter error caught in _stream: yielding user message")
            chunk_msg = AIMessage(
                content=cfe.user_message,
                additional_kwargs={"content_filter_error": True, "raw_error": cfe.raw_error}
            )
            yield ChatGenerationChunk(message=chunk_msg)

        except Exception as e:
            error_msg = f"Error streaming GPT response: {str(e)}"
            logger.error(error_msg)
            raise MultiAgentWorkflowException(error_msg, sys.exc_info())


class WSO2OpenAIModelLoader:
    """
    Model loader for GPT models via OpenAI API through WSO2 gateway.

    This class handles:
    - OAuth2 authentication with WSO2
    - Model initialization and configuration
    - Model aliasing for easy switching
    - Streaming support
    """

    def _classify_token_response(self, status_code: int) -> str:
        """Classify token endpoint HTTP status into success/transient."""
        if status_code == 200:
            return "success"

        logger.info(f"Classifying response as transient for status code: {status_code}")
        return "transient"

    @retry(
        reraise=True,
        stop=stop_after_attempt(getattr(settings, 'WSO2_TOKEN_MAX_RETRIES', 5)),
        wait=wait_exponential(
            multiplier=getattr(settings, 'WSO2_TOKEN_BACKOFF_INITIAL', 5),
            max=getattr(settings, 'WSO2_TOKEN_BACKOFF_MAX', 60),
            exp_base=getattr(settings, 'WSO2_TOKEN_BACKOFF_EXP_BASE', 2.0),
        ),
        retry=retry_if_exception_type((TransientWSO2GPTAuthError, httpx.TimeoutException, httpx.ConnectError)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def _get_access_token(self, client_id: str, client_secret: str, auth_endpoint: str) -> str:
        """Obtain GPT access token via WSO2 with exponential backoff on transient errors."""
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
            raise TransientWSO2GPTAuthError(str(e))
        except httpx.TimeoutException as e:
            logger.warning(f"Transient timeout during token fetch: {e}")
            raise TransientWSO2GPTAuthError("timeout")
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
                raise TransientWSO2GPTAuthError("malformed-json")
            logger.info("Successfully obtained WSO2 access token for GPT")
            return token
        else:
            # All non-200 responses are transient/retryable
            logger.warning(f"Transient token endpoint response {response.status_code}: {response.text[:300]}")
            raise TransientWSO2GPTAuthError(f"status-{response.status_code}")

    def load_model(self, model_name: Optional[str] = None,
                   reasoning_effort: Optional[str] = None,
                   temperature: Optional[float] = None,
                   streaming: Optional[bool] = False,
                   max_tokens: Optional[int] = None,
                   timeout: Optional[int] = None,
                   max_retries: Optional[int] = None,
                   api_version: Optional[str] = None) -> WSO2OpenAIChatModel:
        """
        Load GPT model via OpenAI API through WSO2 gateway.

        Args:
            model_name: Optional model name/alias. If None, uses config.
            reasoning_effort: Optional reasoning effort level ('low', 'medium', 'high').
            temperature: Optional temperature override.
            streaming: Optional streaming mode override.

        Returns:
            WSO2OpenAIChatModel: Initialized LangChain-compatible model instance.

        Raises:
            Exception: If model loading fails.
        """
        try:
            logger.info("Loading GPT model via OpenAI API through WSO2 gateway")

            # Get model configuration
            max_tokens_to_use = max_tokens or settings.LLM_MODEL_MAX_TOKENS
            timeout_to_use = timeout or settings.LLM_MODEL_TIMEOUT
            max_retries_to_use = max_retries or settings.LLM_MODEL_MAX_RETRIES
            api_version_to_use = api_version or settings.LLM_MODEL_API_VERSION

            logger.info(f"WSO2 GPT configuration - Model: {model_name}, Temperature: {temperature}, Streaming: {streaming}")

            # Get WSO2 configuration
            api_endpoint = settings.WSO2_OPENAI_API_ENDPOINT
            auth_endpoint = settings.WSO2_OPENAI_AUTH_ENDPOINT

            if not api_endpoint or not auth_endpoint:
                raise ValueError(
                    "WSO2_OPENAI_API_ENDPOINT and WSO2_OPENAI_AUTH_ENDPOINT must be configured"
                )

            # Get WSO2 client credentials
            client_id = settings.WSO2_OPENAI_CLIENT_ID
            client_secret = settings.WSO2_OPENAI_CLIENT_SECRET

            if not client_id or not client_secret:
                raise ValueError(
                    "WSO2_OPENAI_CLIENT_ID and WSO2_OPENAI_CLIENT_SECRET must be configured"
                )

            logger.info(f"Connecting to WSO2 gateway for GPT at: {api_endpoint}")
            logger.info(f"Using client ID: {client_id[:8]}... (masked)")

            # Get OAuth2 access token
            access_token = self._get_access_token(client_id, client_secret, auth_endpoint)

            # Initialize GPT model
            model = WSO2OpenAIChatModel(
                model_name=model_name,
                api_endpoint=api_endpoint,
                auth_token=access_token,
                max_tokens=max_tokens_to_use,
                temperature=temperature,
                timeout=timeout_to_use,
                max_retries=max_retries_to_use,
                streaming=streaming,
                reasoning_effort=reasoning_effort,
                api_version=api_version_to_use
            )

            logger.info(f"Successfully loaded GPT model via WSO2: {model_name}")
            logger.info(f'Model temperature set to: {temperature}')
            logger.info(f"Reasoning effort set to: {reasoning_effort}")
            logger.info(f'Streaming enabled: {streaming}')
            logger.info(f"Model loaded details: {model}")
            return model

        except Exception as e:
            MultiAgentWorkflowException.log_exception(e, "load_model_wso2_gpt")
            raise MultiAgentWorkflowException("Error in load_model via WSO2 GPT", sys.exc_info())

    def load_model_for_evaluator(self, model_name: Optional[str] = None,
                                 temperature: Optional[float] = None,
                                 streaming: Optional[bool] = False,
                                 max_tokens: Optional[int] = None,
                                 timeout: Optional[int] = None,
                                 max_retries: Optional[int] = None,
                                 api_version: Optional[str] = None) -> WSO2OpenAIChatModel:
        """Load GPT model specifically for evaluation tasks.

        Uses evaluation-focused settings (EVAL_MODEL_NAME, EVAL_MODEL_TEMPERATURE) allowing
        separation from interactive generation parameters.

        Args:
            model_name: Optional explicit model/alias override. If None, uses settings.EVAL_MODEL_NAME.
            temperature: Optional temperature override.
            streaming: Optional streaming mode (default: False for evaluators).

        Returns:
            WSO2OpenAIChatModel configured for evaluation.
        """
        try:
            logger.info("Loading GPT evaluator model via WSO2 gateway")

            # Resolve evaluator model name precedence: explicit override then config
            model_name_to_load = model_name or settings.EVAL_MODEL_NAME
            temperature_to_use = temperature or settings.EVAL_MODEL_TEMPERATURE
            max_tokens_to_use = max_tokens or settings.EVAL_MODEL_MAX_TOKENS
            timeout_to_use = timeout or settings.EVAL_MODEL_TIMEOUT
            max_retries_to_use = max_retries or settings.EVAL_MODEL_MAX_RETRIES
            api_version_to_use = api_version or settings.EVAL_MODEL_API_VERSION

            if not model_name_to_load:
                raise ValueError("No evaluator model name configured (EVAL_MODEL_NAME or LLM_MODEL_NAME)")

            logger.info(f"WSO2 GPT configuration - Model: {model_name_to_load}")

            # Fetch endpoints
            api_endpoint = settings.WSO2_OPENAI_API_ENDPOINT
            auth_endpoint = settings.WSO2_OPENAI_AUTH_ENDPOINT
            if not api_endpoint or not auth_endpoint:
                raise ValueError("WS02_LLM_API_ENDPOINT and WS02_LLM_AUTH_ENDPOINT must be configured for evaluator")

            # Credentials
            client_id = settings.WSO2_OPENAI_CLIENT_ID
            client_secret = settings.WSO2_OPENAI_CLIENT_SECRET
            if not client_id or not client_secret:
                raise ValueError("WS02_LLM_CLIENT_ID and WS02_LLM_CLIENT_SECRET must be configured for evaluator")

            logger.info(f"Connecting to WSO2 gateway for GPT evaluator at: {api_endpoint}")
            logger.info(f"Using client ID: {client_id[:8]}... (masked)")

            access_token = self._get_access_token(client_id, client_secret, auth_endpoint)

            # Initialize GPT model
            model = WSO2OpenAIChatModel(
                model_name=model_name_to_load,
                api_endpoint=api_endpoint,
                auth_token=access_token,
                max_tokens=max_tokens_to_use,
                temperature=temperature_to_use,
                timeout=timeout_to_use,
                max_retries=max_retries_to_use,
                streaming=streaming,
                api_version=api_version_to_use
            )

            logger.info(f"Successfully loaded GPT evaluator model via WSO2: {model_name_to_load} (temperature={temperature_to_use})")
            return model

        except Exception as e:
            MultiAgentWorkflowException.log_exception(e, "load_model_for_evaluator_wso2_gpt")
            raise MultiAgentWorkflowException("Error in load_model_for_evaluator via WSO2 GPT", sys.exc_info())


if __name__ == "__main__":
    # Test the model loader
    try:
        loader = WSO2OpenAIModelLoader()

        # Test without streaming
        print("\n=== Testing without streaming ===")
        model = loader.load_model("gpt-5.1", streaming=False)
        response = model.invoke("Hello! Can you tell me a short joke?")
        print(f"GPT Response: {response.content}")

        # Test with streaming
        print("\n=== Testing with streaming ===")
        model_stream = loader.load_model("gpt-5.1", streaming=True)
        response_stream = model_stream.invoke("Hello! Can you tell me a short joke?")
        print(f"\nFinal Response: {response_stream.content}")

    except Exception as e:
        print(f"Error testing WSO2 GPT model loader: {str(e)}")
        import traceback
        traceback.print_exc()
