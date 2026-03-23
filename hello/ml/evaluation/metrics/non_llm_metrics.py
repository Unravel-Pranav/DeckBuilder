import asyncio
from typing import Union
from ragas.dataset_schema import SingleTurnSample
from ragas.metrics._string import NonLLMStringSimilarity
from ragas.metrics import BleuScore, RougeScore, ExactMatch, StringPresence
from hello.ml.logger import GLOBAL_LOGGER as logger
from hello.ml.exception.custom_exception import MultiAgentWorkflowException
from hello.services.config import settings

class NonLLMMetricsEvaluator:
    """
    A modular evaluator for non-LLM metrics.
    
    This class provides methods to evaluate various non-LLM metrics like
    string similarity, BLEU score, ROUGE score, exact match, and string presence.
    """
    
    async def _evaluate_metric(self, response: str, reference: str, scorer_class, metric_name: str) -> float:
        """
        Generic method to evaluate any metric using a scorer class.
        
        Args:
            response: The generated response text
            reference: The reference text to compare against
            scorer_class: The scorer class to use
            metric_name: Name of the metric for error logging
            
        Returns:
            Metric score
        """
        sample = SingleTurnSample(response=response, reference=reference)
        scorer = scorer_class()
        result = await scorer.single_turn_ascore(sample)
        return result
    
    async def evaluate_string_similarity(self, response: str, reference: str) -> float:
        """
        Evaluate string similarity using NonLLMStringSimilarity.
        
        Args:
            response: The generated response text
            reference: The reference text to compare against
            
        Returns:
            String similarity score (0-1, higher is better)
        """
        return await self._evaluate_metric(response, reference, NonLLMStringSimilarity, "string similarity")
    
    async def evaluate_bleu_score(self, response: str, reference: str) -> float:
        """
        Evaluate BLEU score for text similarity.
        
        Args:
            response: The generated response text
            reference: The reference text to compare against
            
        Returns:
            BLEU score (0-1, higher is better)
        """
        return await self._evaluate_metric(response, reference, BleuScore, "BLEU score")
    
    async def evaluate_rouge_score(self, response: str, reference: str) -> float:
        """
        Evaluate ROUGE score for text similarity.
        
        Args:
            response: The generated response text
            reference: The reference text to compare against
            
        Returns:
            ROUGE score (0-1, higher is better)
        """
        return await self._evaluate_metric(response, reference, RougeScore, "ROUGE score")
    
    async def evaluate_exact_match(self, response: str, reference: str) -> float:
        """
        Evaluate exact match between response and reference.
        
        Args:
            response: The generated response text
            reference: The reference text to compare against
            
        Returns:
            Exact match score (0 or 1, 1 if exact match, 0 otherwise)
        """
        return await self._evaluate_metric(response, reference, ExactMatch, "exact match")
    
    async def evaluate_string_presence(self, response: str, reference: str) -> float:
        """
        Evaluate string presence - checks if reference text is present in response.
        
        Args:
            response: The generated response text
            reference: The reference text to check for presence
            
        Returns:
            String presence score (0 or 1, 1 if reference is present in response, 0 otherwise)
        """
        return await self._evaluate_metric(response, reference, StringPresence, "string presence")
    
    async def _evaluate_metric_with_error_handling(self, response: str, reference: str, metric_method, metric_name: str) -> float:
        """
        Evaluate a single metric with error handling.
        
        Args:
            response: The generated response text
            reference: The reference text to compare against
            metric_method: The async method to call for evaluation
            metric_name: Name of the metric for error logging
            
        Returns:
            Metric score or None if error occurred
        """
        try:
            return await metric_method(response, reference)
        except Exception as e:
            logger.info(f"Error calculating {metric_name}: {e}")
            return None

    async def evaluate_all(self, response: str, reference: str) -> dict[str, float]:
        """
        Evaluate all available non-LLM metrics.
        
        Args:
            response: The generated response text
            reference: The reference text to compare against
            
        Returns:
            Dictionary with metric names as keys and scores as values
        """
        # Define all metrics to evaluate
        metrics = [
            ("string_similarity", self.evaluate_string_similarity, "string similarity"),
            ("bleu_score", self.evaluate_bleu_score, "BLEU score"),
            ("rouge_score", self.evaluate_rouge_score, "ROUGE score"),
            ("exact_match", self.evaluate_exact_match, "exact match"),
            ("string_presence", self.evaluate_string_presence, "string presence")
        ]
        
        results = {}
        for metric_key, metric_method, metric_name in metrics:
            results[metric_key] = await self._evaluate_metric_with_error_handling(
                response, reference, metric_method, metric_name
            )
        
        return results

    def evaluate_all_sync(self, response: str, reference: str) -> dict[str, float]:
        """
        Synchronous wrapper for evaluate_all that handles event loop properly.
        
        Args:
            response: The generated response text
            reference: The reference text to compare against
            
        Returns:
            Dictionary with metric names as keys and scores as values
        """
        try:
            logger.info("Evaluating all non-LLM metrics...")
            if settings.AGENTS_DEBUG:
                logger.info("--------------------------------")
                logger.info("Evaluating all non-LLM metrics...")
                logger.info("--------------------------------")
            
            async def main():
                return await self.evaluate_all(response, reference)

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
            MultiAgentWorkflowException.log_exception(e, "NonLLMMetricsEvaluator")
            raise MultiAgentWorkflowException(f"Failed to evaluate all non-LLM metrics: {str(e)}")


if __name__ == "__main__":
    evaluator = NonLLMMetricsEvaluator()
    all_results = evaluator.evaluate_all_sync(response="The Eiffel Tower is located in Paris.", reference="The Eiffel Tower is located in Paris. It has a height of 1000ft.")
    logger.info("--------------------------------")
    logger.info(f"All Non-LLM Metrics: {all_results}")
    logger.info("--------------------------------")
    