import asyncio
import os
from typing import Dict, Union, Optional, List
from dotenv import load_dotenv
from ragas.dataset_schema import SingleTurnSample
from ragas.metrics import RubricsScore
from hello.ml.utils.model_loader import ModelLoader
from hello.ml.logger import GLOBAL_LOGGER as logger
from hello.ml.exception.custom_exception import MultiAgentWorkflowException
from hello.ml.evaluation.metrics.base_model import ModelForEvaluation
from hello.services.config import settings

class RubricsScoreEvaluator(ModelForEvaluation):
    """
    Modular Rubrics Score Evaluator for RAGAS metrics.
    
    This class provides a flexible interface for evaluating responses against 
    custom rubrics on a 1-5 scale.
    """
    
    def __init__(self, model_name: str = "gpt-4o-mini", rubrics: Optional[Dict[str, str]] = None):
        """
        Initialize the Rubrics Score Evaluator.
        
        Args:
            model_name (str): Name of the LLM model to use for evaluation
            rubrics (Dict[str, str]): Custom rubrics dictionary. If None, uses default rubrics.
        """
        super().__init__(model_name)
        self.rubrics = rubrics or self._get_default_rubrics()

    def _get_default_rubrics(self) -> Dict[str, str]:
        """Get default 5-point rubrics for evaluation."""
        return {
            "score1_description": "The response is entirely incorrect and fails to address any aspect of the reference.",
            "score2_description": "The response contains partial accuracy but includes major errors or significant omissions that affect its relevance to the reference.",
            "score3_description": "The response is mostly accurate but lacks clarity, thoroughness, or minor details needed to fully address the reference.",
            "score4_description": "The response is accurate and clear, with only minor omissions or slight inaccuracies in addressing the reference.",
            "score5_description": "The response is completely accurate, clear, and thoroughly addresses the reference without any errors or omissions.",
        }
    
    async def evaluate_single(
        self, 
        response: str, 
        reference: str
    ) -> float:
        """
        Evaluate rubrics score for a single sample.
        
        Args:
            response (str): The response text to evaluate
            reference (str): The reference text for comparison
            
        Returns:
            float: Rubrics score (1-5 scale)
        """
        try:
            # Create sample
            sample = SingleTurnSample(response=response, reference=reference)
            
            # Initialize scorer with custom rubrics
            scorer = RubricsScore(rubrics=self.rubrics, llm=self.evaluator_llm)
            
            # Calculate score
            result = await scorer.single_turn_ascore(sample)
            return float(result)
            
        except Exception as e:
            raise RuntimeError(f"Failed to evaluate rubrics score: {str(e)}")
    
    def get_rubrics_info(self) -> Dict[str, str]:
        """
        Get information about the rubrics being used.
        
        Returns:
            Dict[str, str]: Current rubrics configuration
        """
        return self.rubrics.copy()

    def evaluate_rubrics_score(self, response: str, reference: str) -> float:
        """
        Evaluate rubrics score for a single sample.
        
        Args:
            response (str): The response text to evaluate
            reference (str): The reference text for comparison
            
        Returns:
            float: Rubrics score (1-5 scale)
        """
        try:
            logger.info("Evaluating rubrics score...")
            if settings.AGENTS_DEBUG:
                logger.info("--------------------------------")
                logger.info("Evaluating rubrics score...")
                logger.info("--------------------------------")
            
            # Show current rubrics
            logger.info("Current Rubrics:")
            for score, description in self.get_rubrics_info().items():
                logger.info(f"\n{score}: {description}")
            
            if settings.AGENTS_DEBUG:
                logger.info("--------------------------------")
                logger.info("Current Rubrics:")
                for score, description in self.get_rubrics_info().items():
                    logger.info(f"\n{score}: {description}")
                logger.info("--------------------------------")
            
            async def main():
                # Single evaluation
                logger.info(f"\nEvaluating: '{response}' vs '{reference}'")
                score = await self.evaluate_single(response, reference)
                logger.info(f"Rubrics Score: {score}")
                return score

            # Check if we're already in an event loop
            try:
                loop = asyncio.get_running_loop()
                # If we're in a loop, we need to use a different approach
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, main())
                    return future.result()
            except RuntimeError:
                # No running loop, safe to use asyncio.run
                return asyncio.run(main())
        
        except Exception as e:
            MultiAgentWorkflowException.log_exception(e, "RubricsScoreEvaluator")
            raise MultiAgentWorkflowException(f"Failed to evaluate rubrics score: {str(e)}")
        
if __name__ == "__main__":
    evaluator = RubricsScoreEvaluator(model_name="gpt-4o-mini")
    score = evaluator.evaluate_rubrics_score(response="The Eiffel Tower is located in Paris.", reference="The Eiffel Tower is located in Paris. It has a height of 1000ft.")
    logger.info(f"Rubrics Score: {score}")
