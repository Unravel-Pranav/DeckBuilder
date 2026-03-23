"""
WSO2 Gemini Model Loader (Google Gemini Integration)

This module provides LangChain-compatible access to Google Gemini models
through the WSO2 API gateway. It handles OAuth2 authentication, streaming support,
and request/response format conversion for seamless integration with existing agents.

Based on Google Gemini API:
- API Reference: https://ai.google.dev/api/rest/v1beta/models/generateContent
- Streaming: https://ai.google.dev/api/rest/v1beta/models/streamGenerateContent
"""

import sys
import json
import uuid
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


class TransientWSO2GeminiAuthError(Exception):
    """Represents a transient error when obtaining Gemini auth token via WSO2."""


class TransientWSO2GeminiStreamingError(Exception):
    """Represents a transient error during Gemini streaming request via WSO2."""


class ContentFilterException(Exception):
    """
    Represents a content filter violation from Google Gemini.

    This exception is NOT retryable - it indicates the prompt triggered
    Gemini's safety settings and should be returned to the user
    as a readable error message.
    """

    def __init__(self, user_message: str, raw_error: dict = None):
        self.user_message = user_message
        self.raw_error = raw_error or {}
        super().__init__(user_message)

    @classmethod
    def from_response(cls, response_data: dict) -> Optional["ContentFilterException"]:
        """
        Parse response and create ContentFilterException if it's a content filter error.

        Args:
            response_data: Response dictionary from the API

        Returns:
            ContentFilterException if content filter error detected, None otherwise
        """
        try:
            # Check for promptFeedback with blockReason
            prompt_feedback = response_data.get("promptFeedback", {})
            block_reason = prompt_feedback.get("blockReason")

            if block_reason:
                user_message = cls._format_user_message(block_reason, prompt_feedback)
                return cls(user_message, response_data)

            # Check for candidates with blocked finishReason
            candidates = response_data.get("candidates", [])
            for candidate in candidates:
                finish_reason = candidate.get("finishReason")
                if finish_reason in ["SAFETY", "BLOCKED_SAFETY", "RECITATION"]:
                    safety_ratings = candidate.get("safetyRatings", [])
                    user_message = cls._format_user_message(finish_reason, {"safetyRatings": safety_ratings})
                    return cls(user_message, response_data)

            return None
        except (KeyError, TypeError):
            return None

    @staticmethod
    def _format_user_message(block_reason: str, feedback: dict) -> str:
        """Format the error into a user-readable message."""
        base_message = (
            "⚠️ **Content Policy Notice**\n\n"
            "Your request could not be processed because it triggered the content safety filter. "
        )

        if block_reason:
            base_message += f"Reason: **{block_reason}**.\n\n"

        # Extract safety ratings if available
        safety_ratings = feedback.get("safetyRatings", [])
        if safety_ratings:
            blocked_categories = [
                rating.get("category")
                for rating in safety_ratings
                if rating.get("probability") in ["HIGH", "MEDIUM"]
            ]
            if blocked_categories:
                categories = ", ".join(blocked_categories)
                base_message += f"Flagged categories: **{categories}**.\n\n"

        base_message += (
            "**What you can do:**\n"
            "- Review and modify your prompt to ensure it complies with content guidelines\n"
            "- Rephrase your request using different wording\n"
            "- Remove any content that might be interpreted as inappropriate\n\n"
            "If you believe this is a mistake, please contact support."
        )

        return base_message


class WSO2GeminiChatModel(BaseChatModel):
    """
    LangChain-compatible chat model for Google Gemini via WSO2 gateway.

    This class implements the BaseChatModel interface and handles:
    - Message format conversion (LangChain -> Gemini format)
    - HTTP requests to WSO2 gateway
    - Response parsing (Gemini -> LangChain format)
    - Streaming support for real-time responses
    - Error handling and retries
    """

    # Model configuration
    model_name: str = Field(default="gemini-2.5-flash")
    api_endpoint: str = Field(default="")
    auth_token: str = Field(default="")
    max_tokens: int = Field(default=8192)
    temperature: float = Field(default=0.7)
    timeout: int = Field(default=600)
    max_retries: int = Field(default=3)
    streaming: bool = Field(default=False, description="Whether to enable streaming responses")

    # Model aliases for easy switching
    MODEL_ALIASES: ClassVar[Dict[str, str]] = {
        "gemini-2.5-flash": "gemini-2.5-flash",
        "gemini-2.0-flash": "gemini-2.0-flash",
        "gemini-1.5-pro": "gemini-1.5-pro",
        "gemini-1.5-flash": "gemini-1.5-flash",
    }

    class Config:
        arbitrary_types_allowed = True

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Resolve model name from alias if needed
        self._model_name = self.MODEL_ALIASES.get(self.model_name, self.model_name)

        # Log initialization
        try:
            logger.info(f"WSO2GeminiChatModel initialized - Model: {self.model_name}, MaxTokens: {self.max_tokens}, Streaming: {self.streaming}")
        except:
            # Fallback if logger is not ready
            logger.info(f"WSO2GeminiChatModel initialized - Model: {self.model_name}, MaxTokens: {self.max_tokens}, Streaming: {self.streaming}")

    @property
    def _llm_type(self) -> str:
        """Return identifier of llm type."""
        return "gemini"

    def _convert_messages_to_gemini_format(self, messages: List[BaseMessage]) -> Dict[str, Any]:
        """
        Convert LangChain messages to Gemini format.

        Args:
            messages: List of LangChain BaseMessage objects

        Returns:
            Dictionary with Gemini API format including contents and systemInstruction
        """
        system_instruction = None
        contents = []

        for message in messages:
            if isinstance(message, SystemMessage):
                # Gemini uses systemInstruction for system messages
                system_instruction = {"parts": [{"text": message.content}]}
            elif isinstance(message, HumanMessage):
                contents.append({
                    "role": "user",
                    "parts": [{"text": message.content}]
                })
            elif isinstance(message, AIMessage):
                contents.append({
                    "role": "model",
                    "parts": [{"text": message.content}]
                })

        result = {"contents": contents}
        if system_instruction:
            result["systemInstruction"] = system_instruction

        return result

    @retry(
        reraise=True,
        stop=stop_after_attempt(getattr(settings, 'WSO2_LLM_MAX_RETRIES', 5)),
        wait=wait_exponential(
            multiplier=getattr(settings, 'WSO2_LLM_BACKOFF_INITIAL', 5),
            max=getattr(settings, 'WSO2_LLM_BACKOFF_MAX', 60),
            exp_base=getattr(settings, 'WSO2_LLM_BACKOFF_EXP_BASE', 2.0),
        ),
        retry=retry_if_exception_type((
            TransientWSO2GeminiStreamingError,
            httpx.TimeoutException,
            httpx.ConnectError,
            httpx.NetworkError,
            httpx.ReadError,
        )),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    @llm(name="invoke_gemini_llm", model_provider="google")
    def _make_request(self, messages: List[BaseMessage], stream: bool = True, **kwargs) -> Dict[str, Any]:
        """
        Make HTTP request to WSO2 gateway for Gemini model.

        Args:
            messages: List of LangChain messages
            stream: Whether to enable streaming
            **kwargs: Additional parameters (temperature, max_tokens, etc.)

        Returns:
            Response dictionary from Gemini API (or full content if streaming)

        Raises:
            Exception: If request fails
        """
        try:
            # Convert messages to Gemini format
            stream = self.streaming
            logger.info(f"Streaming set to: {stream}")
            gemini_payload = self._convert_messages_to_gemini_format(messages)

            # Prepare generation config
            effective_max_tokens = kwargs.get("max_tokens", self.max_tokens)
            generation_config = {
                "temperature": kwargs.get("temperature", self.temperature),
                "maxOutputTokens": effective_max_tokens,
            }

            # Add generation config to payload
            gemini_payload["generationConfig"] = generation_config

            # Build endpoint URL dynamically using selected model name
            endpoint_url = (
                f"{self.api_endpoint}/gc/publishers/google/models/{self._model_name}:generateContent"
            )

            # Prepare observability metadata
            obs_metadata = {
                "temperature": generation_config["temperature"],
                "max_tokens": effective_max_tokens,
                "model_name": self._model_name,
            }

            uuid_str = str(uuid.uuid4())
            logger.info(f"Generated correlation ID for Gemini request: {uuid_str}")

            # Prepare headers
            headers = {
                "Authorization": f"Bearer {self.auth_token}",
                "Content-Type": "application/json",
                "X-AI-WSO2-API": "true",
                "X-correlation-id": uuid_str
            }

            logger.info(f"Making request to Gemini via WSO2 - Endpoint: {endpoint_url}, Streaming: {stream}")
            logger.debug(f"Request payload: {json.dumps(gemini_payload, indent=2)}")

            if stream:
                # Handle streaming response
                response = self._handle_streaming_request(endpoint_url=endpoint_url, headers=headers, payload=gemini_payload)
            else:
                # Handle regular response
                response = self._handle_regular_request(endpoint_url=endpoint_url, headers=headers, payload=gemini_payload)

            # Log usage for observability
            usage = response.get("usageMetadata", {})
            # Extract response content
            content = ""
            if "candidates" in response and len(response["candidates"]) > 0:
                candidate = response["candidates"][0]
                if "content" in candidate and "parts" in candidate["content"]:
                    parts = candidate["content"]["parts"]
                    content = "".join([part.get("text", "") for part in parts])

            # Convert LangChain messages to Datadog-friendly format
            input_messages = []
            for msg in messages:
                if isinstance(msg, SystemMessage):
                    input_messages.append({"role": "system", "content": msg.content})
                elif isinstance(msg, HumanMessage):
                    input_messages.append({"role": "user", "content": msg.content})
                elif isinstance(msg, AIMessage):
                    input_messages.append({"role": "assistant", "content": msg.content})

            datadog_usage_obj = {
                "input_tokens": usage.get("promptTokenCount", 0),
                "output_tokens": usage.get("candidatesTokenCount", 0),
                "total_tokens": usage.get("totalTokenCount", usage.get("promptTokenCount", 0) + usage.get("candidatesTokenCount", 0))
            }

            if usage.get("cachedContentTokenCount"):
                datadog_usage_obj["cache_read_input_tokens"] = usage.get("cachedContentTokenCount", 0)

            # Annotate metrics to Datadog
            LLMObs.annotate(
                span=None,
                input_data=input_messages,
                output_data=[{"role": "assistant", "content": content}],
                metadata=obs_metadata,
                metrics=datadog_usage_obj,
                tags={"model_provider": "google", "integration": "gemini"}
            )
            return response

        except ContentFilterException:
            # Let ContentFilterException pass through without wrapping
            raise
        except httpx.TimeoutException:
            error_msg = f"Gemini request timeout after {self.timeout} seconds"
            logger.error(error_msg)
            raise Exception(error_msg)
        except httpx.RequestError as e:
            error_msg = f"Gemini request error: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)
        except Exception as e:
            error_msg = f"Unexpected error in Gemini request: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)

    def _execute_regular_request(self, endpoint_url: str, headers: Dict[str, str],
                                 payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the actual non-streaming HTTP request.

        Returns:
            Response dictionary from Gemini API

        Raises:
            TransientWSO2GeminiStreamingError: For retryable HTTP errors (5xx, 429)
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
                logger.info(f"Gemini request successful - Response length: {len(str(result))}")

                # Check for content filter in response
                content_filter_error = ContentFilterException.from_response(result)
                if content_filter_error:
                    logger.warning(f"Content filter triggered: {content_filter_error.user_message[:100]}...")
                    raise content_filter_error

                return result
            else:
                error_msg = f"Gemini request failed: {response.status_code} - {response.text}"
                logger.error(error_msg)

                # Check for content filter error (400 status)
                if response.status_code == 400:
                    try:
                        error_data = response.json()
                        content_filter_error = ContentFilterException.from_response(error_data)
                        if content_filter_error:
                            logger.warning(f"Content filter triggered: {content_filter_error.user_message[:100]}...")
                            raise content_filter_error
                    except json.JSONDecodeError:
                        pass
                    raise Exception(error_msg)

                # Todo:  Need to verify for which status codes we need to raise TransientWSO2GeminiAuthError
                raise TransientWSO2GeminiAuthError(error_msg)

    def _handle_regular_request(self, endpoint_url: str, headers: Dict[str, str],
                               payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle non-streaming HTTP request and return response.

        This method retries up to 3 times on transient network errors before failing.
        """
        result = self._execute_regular_request(endpoint_url, headers, payload)
        return result

    def _execute_streaming_request(self, endpoint_url: str, headers: Dict[str, str],
                                   payload: Dict[str, Any]) -> tuple[str, int, dict, Optional[str]]:
        """
        Execute the actual streaming HTTP request.

        Returns:
            Tuple of (full_content, chunk_count, usage, finish_reason)

        Raises:
            TransientWSO2GeminiStreamingError: For retryable HTTP errors (5xx, 429)
            Exception: For non-retryable errors
        """
        full_content = ""
        chunk_count = 0
        usage = {}
        finish_reason = None

        # For streaming, append "?alt=sse" to the endpoint
        if "?" in endpoint_url:
            stream_url = f"{endpoint_url}&alt=sse"
        else:
            stream_url = f"{endpoint_url}?alt=sse"

        with httpx.Client(timeout=self.timeout) as client:
            with client.stream("POST", stream_url, json=payload, headers=headers) as response:
                if response.status_code != 200:
                    # Read the full error response body
                    try:
                        response.read()
                        error_body = ""
                        for chunk in response.iter_bytes():
                            error_body += chunk.decode('utf-8')
                        error_msg = f"Gemini streaming request failed: {response.status_code} error_text- {response.text} - error_body- {error_body}"
                    except Exception:
                        error_body = response.text
                        error_msg = f"Gemini streaming request failed: {response.status_code} - {response.text}"
                    logger.error(error_msg)

                    # Check for content filter error (400 status)
                    if response.status_code == 400:
                        try:
                            error_data = json.loads(error_body)
                            content_filter_error = ContentFilterException.from_response(error_data)
                            if content_filter_error:
                                logger.warning(f"Content filter triggered: {content_filter_error.user_message[:100]}...")
                                raise content_filter_error
                        except json.JSONDecodeError:
                            pass
                        raise Exception(error_msg)

                    # Todo:  Need to verify for which status codes we need to raise TransientWSO2GeminiAuthError
                    raise TransientWSO2GeminiAuthError(error_msg)

                logger.info(f"Response Status Code: {response.status_code}")
                logger.info("=" * 60)
                logger.info("STREAMING CONTENT:")
                logger.info("=" * 60)

                try:
                    for line in response.iter_lines():
                        if line:
                            chunk_count += 1
                            line_str = line.strip()

                            # Gemini SSE format: "data: {...}"
                            if line_str.startswith('data: '):
                                data_str = line_str[6:]  # Remove 'data: ' prefix

                                try:
                                    chunk_data = json.loads(data_str)

                                    # Extract content from candidates
                                    if 'candidates' in chunk_data and len(chunk_data['candidates']) > 0:
                                        candidate = chunk_data['candidates'][0]

                                        # Extract content parts
                                        if 'content' in candidate and 'parts' in candidate['content']:
                                            parts = candidate['content']['parts']
                                            for part in parts:
                                                if 'text' in part:
                                                    content_chunk = part['text']
                                                    # print(content_chunk, end='', flush=True)
                                                    full_content += content_chunk

                                        # Extract finish reason
                                        if 'finishReason' in candidate:
                                            finish_reason = candidate['finishReason']

                                    # Extract usage information (usually in the last chunk)
                                    if 'usageMetadata' in chunk_data:
                                        usage = chunk_data['usageMetadata']

                                    # Check for content filter
                                    content_filter_error = ContentFilterException.from_response(chunk_data)
                                    if content_filter_error:
                                        logger.warning(f"Content filter triggered during streaming")
                                        raise content_filter_error

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

        # Construct Gemini-style response from streamed content
        return {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": full_content}],
                        "role": "model"
                    },
                    "finishReason": finish_reason or "STOP"
                }
            ],
            "usageMetadata": usage
        }

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """
        Generate response from Gemini model.

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

            # Make request to Gemini
            response = self._make_request(messages, stream=stream, **kwargs)

            # Extract content from response
            content = ""
            if "candidates" in response and len(response["candidates"]) > 0:
                candidate = response["candidates"][0]
                if "content" in candidate and "parts" in candidate["content"]:
                    parts = candidate["content"]["parts"]
                    content = "".join([part.get("text", "") for part in parts])

            if not content:
                content = "No response content received from Gemini"
                logger.warning("Empty response content from Gemini")

            # Log usage if available
            if "usageMetadata" in response:
                usage = response["usageMetadata"]
                logger.info(f"Gemini usage - Prompt tokens: {usage.get('promptTokenCount', 0)}, "
                          f"Candidate tokens: {usage.get('candidatesTokenCount', 0)}, "
                          f"Total tokens: {usage.get('totalTokenCount', 0)}")

            # Create usage metadata
            if usage := response.get("usageMetadata"):
                prompt_tokens = usage.get("promptTokenCount", 0)
                completion_tokens = usage.get("candidatesTokenCount", 0)
                total_tokens = usage.get("totalTokenCount", prompt_tokens + completion_tokens)

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
                "model_name": self._model_name,
                "usage": lc_usage,
                "provider": "wso2.gemini",
                "raw_response": response,
                "finish_reason": response.get("candidates", [{}])[0].get("finishReason"),
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
                "provider": "wso2.gemini",
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
            error_msg = f"Error generating Gemini response: {str(e)}"
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
        Stream response from Gemini model.

        Args:
            messages: List of input messages
            stop: Optional list of stop sequences
            run_manager: Optional callback manager
            **kwargs: Additional generation parameters

        Yields:
            ChatGenerationChunk objects
        """
        try:
            # Convert messages to Gemini format
            gemini_payload = self._convert_messages_to_gemini_format(messages)

            # Prepare generation config
            effective_max_tokens = kwargs.get("max_tokens", self.max_tokens)
            generation_config = {
                "temperature": kwargs.get("temperature", self.temperature),
                "maxOutputTokens": effective_max_tokens,
            }

            gemini_payload["generationConfig"] = generation_config

            # Build endpoint URL dynamically using selected model name
            endpoint_url = (
                f"{self.api_endpoint}/gc/publishers/google/models/{self._model_name}:generateContent"
            )

            if "?" in endpoint_url:
                stream_url = f"{endpoint_url}&alt=sse"
            else:
                stream_url = f"{endpoint_url}?alt=sse"

            uuid_str = str(uuid.uuid4())
            headers = {
                "Authorization": f"Bearer {self.auth_token}",
                "Content-Type": "application/json",
                "X-AI-WSO2-API": "true",
                "X-correlation-id": uuid_str
            }

            logger.info(f"Starting streaming request to Gemini via WSO2")

            with httpx.Client(timeout=self.timeout) as client:
                with client.stream("POST", stream_url, json=gemini_payload, headers=headers) as response:
                    if response.status_code != 200:
                        # Read the full error response
                        try:
                            response.read()
                            error_body = ""
                            for chunk in response.iter_bytes():
                                error_body += chunk.decode('utf-8')
                        except Exception:
                            error_body = response.text

                        error_msg = f"Gemini streaming request failed: {response.status_code} - {error_body}"
                        logger.error(error_msg)

                        # Check for content filter error (400 status)
                        if response.status_code == 400:
                            try:
                                error_data = json.loads(error_body)
                                content_filter_error = ContentFilterException.from_response(error_data)
                                if content_filter_error:
                                    logger.warning(f"Content filter triggered in _stream")
                                    raise content_filter_error
                            except json.JSONDecodeError:
                                pass

                        raise Exception(error_msg)

                    for line in response.iter_lines():
                        if line:
                            line_str = line.strip()

                            if line_str.startswith('data: '):
                                data_str = line_str[6:]

                                try:
                                    chunk_data = json.loads(data_str)

                                    if 'candidates' in chunk_data and len(chunk_data['candidates']) > 0:
                                        candidate = chunk_data['candidates'][0]

                                        if 'content' in candidate and 'parts' in candidate['content']:
                                            parts = candidate['content']['parts']
                                            for part in parts:
                                                if 'text' in part:
                                                    content_chunk = part['text']

                                                    chunk_msg = AIMessage(content=content_chunk)
                                                    chunk = ChatGenerationChunk(message=chunk_msg)

                                                    if run_manager:
                                                        run_manager.on_llm_new_token(content_chunk, chunk=chunk)

                                                    yield chunk

                                    # Check for content filter
                                    content_filter_error = ContentFilterException.from_response(chunk_data)
                                    if content_filter_error:
                                        raise content_filter_error

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
            error_msg = f"Error streaming Gemini response: {str(e)}"
            logger.error(error_msg)
            raise MultiAgentWorkflowException(error_msg, sys.exc_info())


class WSO2GeminiModelLoader:
    """
    Model loader for Google Gemini models via WSO2 gateway.

    This class handles:
    - OAuth2 authentication with WSO2
    - Model initialization and configuration
    - Model aliasing for easy switching
    - Streaming support
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
        retry=retry_if_exception_type((TransientWSO2GeminiAuthError, httpx.TimeoutException, httpx.ConnectError)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def _get_access_token(self, client_id: str, client_secret: str, auth_endpoint: str) -> str:
        """Obtain Gemini access token via WSO2 with exponential backoff on transient errors."""
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
            raise TransientWSO2GeminiAuthError(str(e))
        except httpx.TimeoutException as e:
            logger.warning(f"Transient timeout during token fetch: {e}")
            raise TransientWSO2GeminiAuthError("timeout")
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
                raise TransientWSO2GeminiAuthError("malformed-json")
            logger.info("Successfully obtained WSO2 access token for Gemini")
            return token
        elif classification == "transient":
            logger.warning(f"Transient token endpoint response {response.status_code}: {response.text[:300]}")
            raise TransientWSO2GeminiAuthError(f"status-{response.status_code}")
        else:
            logger.error(f"Fatal token endpoint response {response.status_code}: {response.text[:300]}")
            raise Exception(
                f'Failed to obtain Gemini access token (fatal): {response.status_code} - {response.text}'
            )

    def load_model(self, model_name: Optional[str] = None,
                   temperature: Optional[float] = None,
                   streaming: Optional[bool] = None,
                   max_tokens: Optional[int] = None,
                   timeout: Optional[int] = None,
                   max_retries: Optional[int] = None) -> WSO2GeminiChatModel:
        """
        Load Gemini model via WSO2 gateway.

        Args:
            model_name: Optional model name/alias. If None, uses config.
            temperature: Optional temperature override.
            streaming: Optional streaming mode override.

        Returns:
            WSO2GeminiChatModel: Initialized LangChain-compatible model instance.

        Raises:
            Exception: If model loading fails.
        """
        try:
            logger.info("Loading Gemini model via WSO2 gateway")

            # Get model configuration
            model_name_to_load = model_name or settings.LLM_MODEL_NAME
            temperature_to_use = temperature or settings.LLM_MODEL_TEMPERATURE
            streaming_to_use = streaming or settings.LLM_MODEL_STREAMING
            max_tokens_to_use = max_tokens or settings.LLM_MODEL_MAX_TOKENS
            timeout_to_use = timeout or settings.LLM_MODEL_TIMEOUT
            max_retries_to_use = max_retries or settings.LLM_MODEL_MAX_RETRIES

            logger.info(f"WSO2 Gemini configuration - Model: {model_name_to_load}, Temperature: {temperature_to_use}, Streaming: {streaming_to_use}")

            # Get WSO2 configuration
            api_endpoint = settings.WSO2_GEMINI_API_ENDPOINT
            auth_endpoint = settings.WSO2_GEMINI_AUTH_ENDPOINT

            if not api_endpoint or not auth_endpoint:
                raise ValueError(
                    "WSO2_GEMINI_API_ENDPOINT and WSO2_GEMINI_AUTH_ENDPOINT must be configured"
                )

            # Get WSO2 client credentials
            client_id = settings.WSO2_GEMINI_CLIENT_ID
            client_secret = settings.WSO2_GEMINI_CLIENT_SECRET

            if not client_id or not client_secret:
                raise ValueError(
                    "WSO2_GEMINI_CLIENT_ID and WSO2_GEMINI_CLIENT_SECRET must be configured"
                )

            logger.info(f"Connecting to WSO2 gateway for Gemini at: {api_endpoint}")
            logger.info(f"Using client ID: {client_id[:8]}... (masked)")

            # Get OAuth2 access token
            access_token = self._get_access_token(client_id, client_secret, auth_endpoint)

            # Initialize Gemini model
            model = WSO2GeminiChatModel(
                model_name=model_name_to_load,
                api_endpoint=api_endpoint,
                auth_token=access_token,
                max_tokens=max_tokens_to_use,
                temperature=temperature_to_use,
                timeout=timeout_to_use,
                max_retries=max_retries_to_use,
                streaming=streaming_to_use,
            )

            logger.info(f"Successfully loaded Gemini model via WSO2: {model_name_to_load}")
            logger.info(f'Model temperature set to: {temperature_to_use}')
            logger.info(f'Streaming enabled: {streaming_to_use}')
            logger.info(f"Model loaded details: {model}")
            return model

        except Exception as e:
            MultiAgentWorkflowException.log_exception(e, "load_model_wso2_gemini")
            raise MultiAgentWorkflowException("Error in load_model via WSO2 Gemini", sys.exc_info())

    def load_model_for_evaluator(self, model_name: Optional[str] = None,
                                 temperature: Optional[float] = None,
                                 streaming: Optional[bool] = False,
                                 max_tokens: Optional[int] = None,
                                 timeout: Optional[int] = None,
                                 max_retries: Optional[int] = None) -> WSO2GeminiChatModel:
        """Load Gemini model specifically for evaluation tasks.

        Uses evaluation-focused settings allowing separation from interactive generation parameters.

        Args:
            model_name: Optional explicit model/alias override. If None, uses settings.
            temperature: Optional temperature override.
            streaming: Optional streaming mode (default: False for evaluators).

        Returns:
            WSO2GeminiChatModel configured for evaluation.
        """
        try:
            logger.info("Loading Gemini evaluator model via WSO2 gateway")

            # Resolve evaluator model name precedence: explicit override then config
            model_name_to_load = model_name or settings.EVAL_MODEL_NAME
            temperature_to_use = temperature or settings.EVAL_MODEL_TEMPERATURE
            max_tokens_to_use = max_tokens or settings.EVAL_MODEL_MAX_TOKENS
            timeout_to_use = timeout or settings.EVAL_MODEL_TIMEOUT
            max_retries_to_use = max_retries or settings.EVAL_MODEL_MAX_RETRIES

            logger.info(f"WSO2 Gemini configuration - Model: {model_name_to_load}")

            # Fetch endpoints
            api_endpoint = settings.WSO2_GEMINI_API_ENDPOINT
            auth_endpoint = settings.WSO2_GEMINI_AUTH_ENDPOINT
            if not api_endpoint or not auth_endpoint:
                raise ValueError("WSO2_GEMINI_API_ENDPOINT and WSO2_GEMINI_AUTH_ENDPOINT must be configured for evaluator")

            # Credentials
            client_id = settings.WSO2_GEMINI_CLIENT_ID
            client_secret = settings.WSO2_GEMINI_CLIENT_SECRET
            if not client_id or not client_secret:
                raise ValueError("WSO2_GEMINI_CLIENT_ID and WSO2_GEMINI_CLIENT_SECRET must be configured for evaluator")

            logger.info(f"Connecting to WSO2 gateway for Gemini evaluator at: {api_endpoint}")
            logger.info(f"Using client ID: {client_id[:8]}... (masked)")

            access_token = self._get_access_token(client_id, client_secret, auth_endpoint)

            # Initialize Gemini model
            model = WSO2GeminiChatModel(
                model_name=model_name_to_load,
                api_endpoint=api_endpoint,
                auth_token=access_token,
                max_tokens=max_tokens_to_use,
                temperature=temperature_to_use,
                timeout=timeout_to_use,
                max_retries=max_retries_to_use,
                streaming=streaming,
            )

            logger.info(f"Successfully loaded Gemini evaluator model via WSO2: {model_name_to_load} (temperature={temperature_to_use})")
            return model

        except Exception as e:
            MultiAgentWorkflowException.log_exception(e, "load_model_for_evaluator_wso2_gemini")
            raise MultiAgentWorkflowException("Error in load_model_for_evaluator via WSO2 Gemini", sys.exc_info())


if __name__ == "__main__":
    # Test the model loader
    try:
        loader = WSO2GeminiModelLoader()

        # Test without streaming
        print("\n=== Testing without streaming ===")
        model = loader.load_model("gemini-2.5-flash", streaming=False)
        response = model.invoke("Hello! Can you tell me a short joke?")
        print(f"Gemini Response: {response.content}")

        # Test with streaming
        print("\n=== Testing with streaming ===")
        model_stream = loader.load_model("gemini-2.5-flash", streaming=True)
        response_stream = model_stream.invoke("Hello! Can you tell me a short joke?")
        print(f"\nFinal Response: {response_stream.content}")

    except Exception as e:
        print(f"Error testing WSO2 Gemini model loader: {str(e)}")
        import traceback
        traceback.print_exc()
