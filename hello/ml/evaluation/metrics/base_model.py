from hello.ml.logger import GLOBAL_LOGGER as logger
from hello.ml.exception.custom_exception import MultiAgentWorkflowException
from ragas.llms import LangchainLLMWrapper
from hello.ml.utils.model_factory import get_model_loader
from hello.services.config import settings


class ModelForEvaluation:
    """Base class for Evaluation LLM usage.

    Responsibilities:
    - Initialize evaluator LLM using factory abstraction respecting provider.
    - Expose lightweight metadata (provider, model, temperature) for persistence.
    - Wrap underlying LLM with RAGAS Langchain wrapper for metric evaluators.
    """

    def __init__(self, model_name: str = None):
        self.model_name = model_name  # optional override
        # Capture configured provider & defaults prior to load
        self.provider = settings.EVAL_MODEL_PROVIDER
        self.model_name = settings.EVAL_MODEL_NAME
        self.temperature_eval = settings.EVAL_MODEL_TEMPERATURE
        # Initialize model
        self.llm = self._initialize_llm()
        self.evaluator_llm = LangchainLLMWrapper(self.llm)
        # Prepare last_model_details dict for external consumption (e.g., DB storage)
        self._last_model_details = {
            "provider": self.provider,
            "model_name": self._resolved_model_name,
            "temperature": self.temperature_eval,
        }

    def _initialize_llm(self):
        """Initialize the LLM wrapper for evaluation."""
        try:
            # Use model factory to get appropriate loader based on LLM_MODEL_PROVIDER setting
            model_loader = get_model_loader(self.provider)
            llm = model_loader.load_model_for_evaluator(
                model_name=self.model_name,
                temperature=self.temperature_eval
            )
            # Attempt to derive an effective model name (attribute or fallback)
            logger.info("Loaded LLM:", llm)
            resolved = getattr(llm, "model_name", None) or self.model_name or getattr(settings, "EVAL_MODEL_NAME", None)
            self._resolved_model_name = resolved
            logger.info(f"Initialized evaluation LLM with provider: {self.provider}, model: {resolved}")
            return llm
        except Exception as e:
            MultiAgentWorkflowException.log_exception(e, "ModelForEvaluation")
            raise MultiAgentWorkflowException(f"Failed to initialize LLM '{self.model_name}': {str(e)}")

    def get_model_details(self) -> dict:
        """Return metadata about the evaluator LLM for persistence/logging.

        Returns:
            dict: {provider, model_name, temperature}
        """
        return dict(self._last_model_details)
    

if __name__ == "__main__":
    # Simple test instantiation
    obj = ModelForEvaluation()
    obj._initialize_llm()
    logger.info("Model details:", obj.get_model_details())
