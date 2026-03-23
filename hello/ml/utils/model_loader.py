import sys
from typing import Optional
from langchain_openai import ChatOpenAI

from hello.ml.logger import GLOBAL_LOGGER as logger
from hello.ml.exception.custom_exception import MultiAgentWorkflowException
from hello.services.config import settings


class ModelLoader:

    def load_model(self, model_name: Optional[str] = None,
                   reasoning_effort: Optional[str] = None,
                   temperature: Optional[float] = None) -> ChatOpenAI:
        """
        Loads the model based on the configuration.

        Args:
            model_name: Optional model name to override config. If None, uses config.
            reasoning_effort: Optional reasoning effort level ('low', 'medium', 'high').
                            If None, uses config value. If "none", loads without reasoning.

        Returns:
            ChatOpenAI: Initialized language model instance.

        Raises:
            Exception: If model loading fails.
        """
        try:
            # Get the model config
            model_name_to_load = model_name or settings.LLM_MODEL_NAME
            model_temperature = temperature or settings.LLM_MODEL_TEMPERATURE

            # Determine reasoning effort to use
            if reasoning_effort is not None:
                reasoning_to_use = None if reasoning_effort == "none" else reasoning_effort
            else:
                reasoning_to_use = settings.LLM_MODEL_REASONING_EFFECT

            logger.info(f"Loading model: {model_name_to_load} with temperature: {model_temperature}, reasoning: {reasoning_to_use}")

            model_api_key = settings.OPENAI_API_KEY

            if reasoning_to_use is None:
                logger.info("Loading model without reasoning effort")
                llm = ChatOpenAI(
                    model=model_name_to_load,
                    temperature=model_temperature,
                    api_key=model_api_key
                )
            else:
                # Load the model with specified reasoning effort
                logger.info(f"Loading model with reasoning effort: {reasoning_to_use}")
                llm = ChatOpenAI(
                    model=model_name_to_load,
                    temperature=model_temperature,
                    reasoning_effort=reasoning_to_use,
                    api_key=model_api_key
                )
            logger.info(f"Model loaded: {llm}")
            # Return the model
            return llm
        except Exception as e:
            MultiAgentWorkflowException.log_exception(e, "load_model")
            raise MultiAgentWorkflowException("Error in load_model", sys.exc_info())

    def load_model_for_evaluator(self, model_name: Optional[str] = None, 
    temperature: Optional[float] = None) -> ChatOpenAI:
        """
        Loads the model for evaluator.
        """
        try:
            # Get the model config
            model_name_to_load = model_name or settings.EVAL_MODEL_NAME
            model_temperature = temperature or settings.EVAL_MODEL_TEMPERATURE
            model_api_key = settings.OPENAI_API_KEY
            llm = ChatOpenAI(
                model=model_name_to_load,
                temperature= model_temperature,
                api_key=model_api_key
            )
            return llm
        except Exception as e:
            MultiAgentWorkflowException.log_exception(e, "load_model_for_evaluator")
            raise MultiAgentWorkflowException("Error in load_model_for_evaluator", sys.exc_info())

if __name__ == "__main__":
    model_loader = ModelLoader()
    # model = model_loader.load_model()
    model_evaluator = model_loader.load_model("gpt-5.1")
    # logger.info(model.invoke("How is the weather in Hyderabad?"))
    logger.info(model_evaluator.invoke("How is the weather in Hyderabad?"))