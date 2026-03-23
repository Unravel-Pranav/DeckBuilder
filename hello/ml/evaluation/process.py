import asyncio
from typing import Dict, Any, Optional
from hello.ml.evaluation.metrics.factual_correctness import FactualCorrectnessEvaluator
from hello.ml.evaluation.metrics.rubrics_scoring import RubricsScoreEvaluator
from hello.ml.evaluation.metrics.non_llm_metrics import NonLLMMetricsEvaluator
from hello.ml.evaluation.metrics.llm_metric import LLMMetricEvaluator
from hello.ml.evaluation.metrics.hallucination import LLMHallucinationEvaluator
from hello.ml.evaluation.metrics.toxicity import LLMToxicityEvaluator
from hello.ml.logger import GLOBAL_LOGGER as logger
from hello.ml.exception.custom_exception import MultiAgentWorkflowException


class ProcessEvaluation:
    
    def __init__(self):
        self.factual_correctness = FactualCorrectnessEvaluator()
        self.rubrics_score = RubricsScoreEvaluator()
        self.non_llm_metrics = NonLLMMetricsEvaluator()
        self.llm_metric = LLMMetricEvaluator()
        # New modular evaluators
        self.hallucination_metric = LLMHallucinationEvaluator()
        self.toxicity_metric = LLMToxicityEvaluator()
        self.results = {}

    async def evaluate_async(self, response: str, reference: str) -> Dict[str, Any]:
        """
        Evaluate response against reference using all enabled metrics concurrently.

        Args:
            response (str): The response text to evaluate
            reference (str): The reference text for comparison
            
        Returns:
            Dict[str, Any]: Dictionary containing results from all metrics
        """
        logger.info("Starting concurrent evaluation process...")
        self.results = {}

        try:
            # Create tasks for all metrics to run concurrently
            tasks = [
                self._evaluate_factual_correctness_async(response, reference),
                self._evaluate_rubrics_score_async(response, reference),
                self._evaluate_non_llm_metrics_async(response, reference),
                self._evaluate_llm_metric_async(response, reference),
                self._evaluate_hallucination_async(response, reference),
                self._evaluate_toxicity_async(response, reference),
            ]
            
            # Run all tasks concurrently
            logger.info("Running all metrics concurrently...")
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results and handle any exceptions
            metric_names = [
                'factual_correctness',
                'rubrics_score',
                'non_llm_metrics',
                'llm_metric',
                'hallucination',
                'toxicity'
            ]
            
            for i, result in enumerate(results):
                metric_name = metric_names[i]
                if isinstance(result, Exception):
                    logger.error(f"Error in {metric_name}: {result}")
                    self.results[metric_name] = {"error": str(result)}
                else:
                    self.results[metric_name] = result
            
            # Add a small delay to allow HTTP clients to clean up properly
            await asyncio.sleep(0.2)
            
            logger.info("Concurrent evaluation completed successfully")
            return self.results
            
        except Exception as e:
            MultiAgentWorkflowException.log_exception(e, "ProcessEvaluation")
            raise MultiAgentWorkflowException(f"Failed to run concurrent evaluation: {str(e)}")

    async def _evaluate_factual_correctness_async(self, response: str, reference: str) -> Dict[str, float]:
        """Evaluate factual correctness asynchronously."""
        try:
            # Run the synchronous evaluate_factual_correctness method in a thread pool
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, self.factual_correctness.evaluate_factual_correctness, response, reference)
        except Exception as e:
            logger.error(f"Error in factual correctness evaluation: {e}")
            return {"error": str(e)}


    async def _evaluate_rubrics_score_async(self, response: str, reference: str) -> float:
        """Evaluate rubrics score asynchronously."""
        try:
            # Run the synchronous evaluate_rubrics_score method in a thread pool
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, self.rubrics_score.evaluate_rubrics_score, response, reference)
        except Exception as e:
            logger.error(f"Error in rubrics score evaluation: {e}")
            return {"error": str(e)}

    async def _evaluate_non_llm_metrics_async(self, response: str, reference: str) -> Dict[str, float]:
        """Evaluate non-LLM metrics asynchronously."""
        try:
            # Run the synchronous evaluate_all_sync method in a thread pool
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, self.non_llm_metrics.evaluate_all_sync, response, reference)
        except Exception as e:
            logger.error(f"Error in non-LLM metrics evaluation: {e}")
            return {"error": str(e)}

    async def _evaluate_llm_metric_async(self, response: str, reference: str) -> Dict[str, Any]:
        """Evaluate LLM metric asynchronously."""
        try:
            # Run the synchronous evaluate method in a thread pool
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, self.llm_metric.evaluate, response, reference)
        except Exception as e:
            logger.error(f"Error in LLM metric evaluation: {e}")
            return {"error": str(e)}

    async def _evaluate_hallucination_async(self, response: str, reference: str) -> Dict[str, Any]:
        """Evaluate hallucination between generated response and reference.

        Uses LLMHallucinationEvaluator; ground_truth=reference, generated=response.
        """
        try:
            # Use true async method; evaluate() is sync and should not be awaited
            return await self.hallucination_metric.aevaluate(reference, response)
        except Exception as e:
            logger.error(f"Error in hallucination evaluation: {e}")
            return {"error": str(e)}

    async def _evaluate_toxicity_async(self, response: str, reference: str) -> Dict[str, Any]:  # reference unused, kept for signature consistency
        """Evaluate toxicity of the generated response text only."""
        try:
            # Use true async method; evaluate() is sync and should not be awaited
            return await self.toxicity_metric.aevaluate(response)
        except Exception as e:
            logger.error(f"Error in toxicity evaluation: {e}")
            return {"error": str(e)}


    def evaluate(self, response: str, reference: str, context: Optional[str] = None) -> Dict[str, Any]:
        """
        Evaluate response against reference using all enabled metrics (synchronous wrapper).

        Args:
            response (str): The response text to evaluate
            reference (str): The reference text for comparison
            
        Returns:
            Dict[str, Any]: Dictionary containing results from all metrics
        """
        try:
            # Check if we're already in an event loop
            try:
                loop = asyncio.get_running_loop()
                # If we're in a loop, we need to use a different approach
                import concurrent.futures
                import threading

                def run_in_thread():
                    # Create a new event loop in the thread
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        return loop.run_until_complete(self.evaluate_async(response, reference))
                    finally:
                        # Properly close the loop and cleanup
                        try:
                            # Add a small delay to allow HTTP clients to clean up
                            loop.run_until_complete(asyncio.sleep(0.5))
                            
                            # Cancel any remaining tasks
                            pending = asyncio.all_tasks(loop)
                            for task in pending:
                                task.cancel()
                            
                            # Wait for tasks to complete cancellation
                            if pending:
                                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                            
                            # Close the loop
                            loop.close()
                        except Exception:
                            pass  # Ignore cleanup errors

                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(run_in_thread)
                    return future.result()
            except RuntimeError:
                # No running loop, safe to use asyncio.run
                return asyncio.run(self.evaluate_async(response, reference))
        except Exception as e:
            MultiAgentWorkflowException.log_exception(e, "ProcessEvaluation")
            raise MultiAgentWorkflowException(f"Failed to evaluate metrics: {str(e)}")


if __name__ == "__main__":
    import time
    import warnings
    import logging
    
    # Suppress specific asyncio warnings about unretrieved task exceptions
    warnings.filterwarnings("ignore", message=".*Task exception was never retrieved.*")
    logging.getLogger("asyncio").setLevel(logging.CRITICAL)
    
    response = """
    Net absorption was positive 528,351 sq. ft in Q2 2025, a decrease from positive 1.5 million sq. ft in the previous quarter. Over the last four quarters net absorption totaled positive 4.3 million sq. ft. Over the last 3 years cumulative net absorption was positive 18.0 million sq. ft.
    """
    reference = """Net absorption was positive 528,351 sq. ft in Q2 2025, a decrease from positive 1.5 million sq. ft in the previous quarter. Over the last four quarters net absorption totaled positive 4.3 million sq. ft. Over the last 3 years cumulative net absorption was positive 18.0 million sq. ft."""

    # context removed (unused)
    
    process_evaluation = ProcessEvaluation()
    
    # Test concurrent execution (metrics run in parallel)
    logger.info("Testing concurrent execution...")
    start_time = time.time()
    results = process_evaluation.evaluate(response, reference)
    execution_time = time.time() - start_time
    
    logger.info("--------------------------------")
    logger.info(f"Evaluation Results: {results}")
    logger.info(f"Execution time: {execution_time:.2f} seconds")
    logger.info("--------------------------------")