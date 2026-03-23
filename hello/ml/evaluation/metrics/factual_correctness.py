import asyncio
import os
from typing import Dict, Union, Optional, List
from dotenv import load_dotenv
from ragas.dataset_schema import SingleTurnSample
from ragas.metrics._factual_correctness import FactualCorrectness

from hello.ml.logger import GLOBAL_LOGGER as logger
from hello.ml.exception.custom_exception import MultiAgentWorkflowException
from hello.ml.evaluation.metrics.base_model import ModelForEvaluation
from hello.services.config import settings

class FactualCorrectnessEvaluator(ModelForEvaluation):
    """
    Modular Factual Correctness Evaluator for RAGAS metrics.
    
    This class provides a flexible interface for evaluating factual correctness
    of responses against reference text using different modes (default, precision, recall).
    """

    def __init__(self, model_name: str = "gpt-4o-mini"):
        """Initialize the Factual Correctness Evaluator.

        Args:
            model_name (str): Name of the LLM model to use for evaluation
        """
        # Initialize base model (sets self.model_name and self.llm)
        super().__init__(model_name)

    async def evaluate_single(
        self, 
        response: str, 
        reference: str, 
        mode: str = "default"
    ) -> float:
        """
        Evaluate factual correctness for a single sample.
        
        Args:
            response (str): The response text to evaluate
            reference (str): The reference text for comparison
            mode (str): Evaluation mode - "default", "precision", or "recall"
            
        Returns:
            float: Factual correctness score
        
        Raises:
            ValueError: If response or reference is empty or None
            MultiAgentWorkflowException: If evaluation fails
        """
        # Input validation
        if not response or not response.strip():
            raise ValueError("Response cannot be empty or None")
        if not reference or not reference.strip():
            raise ValueError("Reference cannot be empty or None")
        if mode not in ["default", "precision", "recall"]:
            raise ValueError(f"Invalid mode '{mode}'. Must be one of: default, precision, recall")
            
        try:
            # Create sample
            sample = SingleTurnSample(response=response, reference=reference)
            
            # Initialize scorer based on mode
            if mode == "precision":
                scorer = FactualCorrectness(llm=self.evaluator_llm, mode="precision")
            elif mode == "recall":
                scorer = FactualCorrectness(llm=self.evaluator_llm, mode="recall")
            else:  # default mode
                scorer = FactualCorrectness(llm=self.evaluator_llm)
            
            # Calculate score
            result = await scorer.single_turn_ascore(sample)
            return float(result)
            
        except Exception as e:
            MultiAgentWorkflowException.log_exception(e, "FactualCorrectnessEvaluator")
            raise MultiAgentWorkflowException(f"Failed to evaluate factual correctness: {str(e)}")
      
    async def evaluate_all_modes(
        self, 
        response: str, 
        reference: str
    ) -> Dict[str, float]:
        """
        Evaluate factual correctness using all three modes concurrently.
        
        Args:
            response (str): The response text to evaluate
            reference (str): The reference text for comparison
            
        Returns:
            Dict[str, float]: Dictionary with scores for each mode
        """
        try:
            modes = ["default", "precision", "recall"]
            
            logger.info(f"Evaluating all modes concurrently: {modes}")
            
            # Run all modes concurrently using asyncio.gather
            tasks = [
                self.evaluate_single(response, reference, mode) 
                for mode in modes
            ]
            
            scores = await asyncio.gather(*tasks)
            
            # Create results dictionary mapping mode names to scores
            results = dict(zip(modes, scores))
            
            logger.info(f"Completed evaluation of all modes: {results}")
            return results
            
        except Exception as e:
            MultiAgentWorkflowException.log_exception(e, "FactualCorrectnessEvaluator")
            raise MultiAgentWorkflowException(f"Failed to evaluate all modes: {str(e)}")


    def evaluate_factual_correctness(self, response: str, reference: str, mode: str = None) -> Dict[str, float]:   
        """
        Evaluate factual correctness using all three modes (synchronous wrapper).
        
        Args:
            response (str): The response text to evaluate
            reference (str): The reference text for comparison
            
        Returns:
            Dict[str, float]: Dictionary with scores for each mode
        
        Raises:
            ValueError: If response or reference is invalid
            MultiAgentWorkflowException: If evaluation fails
        """
        try:
            # Evaluate using different modes
            logger.info("Evaluating factual correctness...")
            if settings.AGENTS_DEBUG:
                logger.info("--------------------------------")
                logger.info("Evaluating factual correctness...")
                logger.info(f"response: {response}")
                logger.info(f"reference: {reference}")
                logger.info("--------------------------------")
            
            async def main():
                all_scores = None
                if mode:
                    logger.info(f"Evaluating only {mode} mode...")
                    all_scores = await self.evaluate_single(response, reference, mode)
                    logger.info(f"All scores: {all_scores}")    
                else:
                    # Evaluate all modes at once using self
                    logger.info("Evaluating all modes...")
                    all_scores = await self.evaluate_all_modes(response, reference)
                    logger.info(f"All scores: {all_scores}") 
                    if settings.AGENTS_DEBUG:
                        logger.info("--------------------------------")
                        logger.info(f"All scores: {all_scores}")
                        logger.info("--------------------------------")
                return all_scores
            
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
            MultiAgentWorkflowException.log_exception(e, "FactualCorrectnessEvaluator")
            raise MultiAgentWorkflowException(f"Failed to evaluate factual correctness: {str(e)}")

if __name__ == "__main__":
    """Example usage of the modular factual correctness evaluator."""
    # Example data
    sample_response = """In Q2 2025 the market reported a total availability rate of 6.2%, up 50 bps quarter-over-quarter and up 60 bps year-over-year, with a 220 bps increase over the past 3 years. Direct availability was 5.4% in Q2 2025, up 40 bps quarter-over-quarter and up 30 bps year-over-year, with a 170 bps increase over the past 3 years. Available sublease space stood at 0.8% in Q2 2025, up 10 bps quarter-over-quarter and an increase 30 bps year-over-year. Sublease availability is above the 3-years quarterly average."""
    sample_reference = """In Q2 2025 the Minneapolis/St. Paul Industrial market reported a total availability rate of 6.2%, up 50 bps quarter-over-quarter and up 60 bps year-over-year, with a 220 bps increase over the past 3 years. Direct availability was 5.4% in Q2 2025, up 40 bps quarter-over-quarter and up 30 bps year-over-year, with a 170 bps increase over the past 3 years. Available sublease space stood at 0.8% in Q2 2025, an increase of 10 bps quarter-over-quarter and an increase 30 bps year-over-year. Sublease availability is above the 3-years quarterly average."""
    
    try:
        evaluator = FactualCorrectnessEvaluator(model_name="gpt-4o-mini")
        all_scores = evaluator.evaluate_factual_correctness(sample_response, sample_reference)
        logger.info(f"All scores: {all_scores}")
    except Exception as e:
        logger.info(f"Error during evaluation: {e}") 