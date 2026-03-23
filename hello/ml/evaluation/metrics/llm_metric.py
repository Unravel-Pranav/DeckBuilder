import json
import re
from typing import Dict, Union, Optional, List, Tuple
from hello.ml.utils.model_loader import ModelLoader
from hello.ml.logger import GLOBAL_LOGGER as logger
from hello.ml.exception.custom_exception import MultiAgentWorkflowException
from hello.ml.evaluation.metrics.base_model import ModelForEvaluation
from hello.services.config import settings

class LLMMetricEvaluator(ModelForEvaluation):
    """
    LLM-based metric evaluator for comparing generated summaries with reference summaries.
    
    This class provides comprehensive evaluation using LLM to assess various aspects
    of summary quality including accuracy, completeness, coherence, and relevance.
    """
    
    def __init__(self, model_name: str = None):
        """
        Initialize the LLM Metric Evaluator.
        
        Args:
            model_name (str): Name of the LLM model to use for evaluation
        """
        # Initialize base model (sets self.model_name and self.llm)
        super().__init__(model_name)
    
    def _create_evaluation_prompt(self, generated_summary: str, reference_summary: str) -> str:
        """
        Create a comprehensive evaluation prompt for LLM assessment.
        
        Args:
            generated_summary (str): The generated summary to evaluate
            reference_summary (str): The reference summary for comparison
            
        Returns:
            str: Formatted evaluation prompt
        """
        prompt = f"""
You are an expert evaluator tasked with comparing a generated summary against a reference summary. 
Please evaluate the following aspects and provide scores on a scale of 0-1 (where 1 is perfect):

**Generated Summary:**
{generated_summary}

**Reference Summary:**
{reference_summary}

**Evaluation Criteria:**

1. **Accuracy (0-1)**: How factually correct is the generated summary compared to the reference?
   - Are the key facts, numbers, and claims accurate?
   - Are there any factual errors or misrepresentations?

2. **Completeness (0-1)**: How well does the generated summary cover the important information from the reference?
   - Are all major points and key details included?
   - Is important information missing or significantly abbreviated?

3. **Coherence (0-1)**: How well-structured and logically organized is the generated summary?
   - Does it flow logically from one point to the next?
   - Is the information presented in a clear, understandable way?

4. **Relevance (0-1)**: How relevant and focused is the generated summary?
   - Does it stay on topic and avoid irrelevant information?
   - Is the level of detail appropriate for a summary?

5. **Clarity (0-1)**: How clear and concise is the language used?
   - Is the language clear and easy to understand?
   - Is the summary appropriately concise without losing important information?

6. **Overall Quality (0-1)**: Overall assessment of the generated summary's quality.

**Instructions:**
- Provide scores for each criterion as decimal numbers between 0 and 1
- Include a brief explanation for each score
- Be objective and fair in your assessment
- Consider the context and purpose of the summary

**Response Format (JSON):**
{{
    "accuracy": {{
        "score": 0.85,
        "explanation": "Brief explanation of the score"
    }},
    "completeness": {{
        "score": 0.90,
        "explanation": "Brief explanation of the score"
    }},
    "coherence": {{
        "score": 0.88,
        "explanation": "Brief explanation of the score"
    }},
    "relevance": {{
        "score": 0.92,
        "explanation": "Brief explanation of the score"
    }},
    "clarity": {{
        "score": 0.87,
        "explanation": "Brief explanation of the score"
    }},
    "overall_quality": {{
        "score": 0.88,
        "explanation": "Brief explanation of the overall assessment"
    }},
    "summary": "Overall assessment summary"
}}
"""
        return prompt
    
    def _parse_llm_response(self, response: str) -> Dict[str, Union[float, Dict]]:
        """
        Parse the LLM response and extract scores.
        
        Args:
            response (str): Raw LLM response
            
        Returns:
            Dict: Parsed evaluation results
        """
        try:
            # Try to extract JSON from the response
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group()
                parsed_response = json.loads(json_str)
                
                # Extract scores and create structured result
                result = {}
                for criterion in ["accuracy", "completeness", "coherence", "relevance", "clarity", "overall_quality"]:
                    if criterion in parsed_response:
                        if isinstance(parsed_response[criterion], dict):
                            result[criterion] = {
                                "score": float(parsed_response[criterion].get("score", 0.0)),
                                "explanation": parsed_response[criterion].get("explanation", "")
                            }
                        else:
                            result[criterion] = {
                                "score": float(parsed_response[criterion]),
                                "explanation": ""
                            }
                
                # Add summary if available
                if "summary" in parsed_response:
                    result["summary"] = parsed_response["summary"]
                
                return result
            else:
                # Fallback: try to extract scores using regex
                logger.warning("Could not parse JSON from LLM response, using fallback parsing")
                return self._fallback_parse(response)
                
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parsing failed: {e}, using fallback parsing")
            return self._fallback_parse(response)
        except Exception as e:
            logger.error(f"Error parsing LLM response: {e}")
            return self._create_default_result()
    
    def _fallback_parse(self, response: str) -> Dict[str, Union[float, Dict]]:
        """
        Fallback parsing method using regex to extract scores.
        
        Args:
            response (str): Raw LLM response
            
        Returns:
            Dict: Parsed evaluation results
        """
        result = {}
        criteria = ["accuracy", "completeness", "coherence", "relevance", "clarity", "overall_quality"]
        
        for criterion in criteria:
            # Look for patterns like "accuracy: 0.85" or "accuracy score: 0.85"
            pattern = rf"{criterion}.*?(\d+\.?\d*)"
            match = re.search(pattern, response, re.IGNORECASE)
            if match:
                try:
                    score = float(match.group(1))
                    # Ensure score is between 0 and 1
                    if score > 1:
                        score = score / 10 if score <= 10 else score / 100
                    result[criterion] = {
                        "score": score,
                        "explanation": f"Extracted from {criterion} evaluation"
                    }
                except ValueError:
                    result[criterion] = {
                        "score": 0.5,
                        "explanation": f"Could not parse {criterion} score"
                    }
            else:
                result[criterion] = {
                    "score": 0.5,
                    "explanation": f"No {criterion} score found"
                }
        
        return result
    
    def _create_default_result(self) -> Dict[str, Union[float, Dict]]:
        """Create a default result when parsing fails."""
        return {
            "accuracy": {"score": 0.5, "explanation": "Parsing failed, using default score"},
            "completeness": {"score": 0.5, "explanation": "Parsing failed, using default score"},
            "coherence": {"score": 0.5, "explanation": "Parsing failed, using default score"},
            "relevance": {"score": 0.5, "explanation": "Parsing failed, using default score"},
            "clarity": {"score": 0.5, "explanation": "Parsing failed, using default score"},
            "overall_quality": {"score": 0.5, "explanation": "Parsing failed, using default score"},
            "summary": "Evaluation parsing failed"
        }
    
    def evaluate(self, generated_summary: str, reference_summary: str) -> Dict[str, Union[float, Dict]]:
        """
        Evaluate the generated summary against the reference.
        
        Args:
            generated_summary (str): The generated summary to evaluate
            reference_summary (str): The reference summary for comparison
            
        Returns:
            Dict: Evaluation results with scores and explanations
        """
        try:
            # Input validation
            if not generated_summary or not generated_summary.strip():
                raise ValueError("Generated summary cannot be empty or None")
            if not reference_summary or not reference_summary.strip():
                raise ValueError("Reference summary cannot be empty or None")
            
            logger.info("Evaluating summaries with LLM...")
            if settings.AGENTS_DEBUG:
                logger.info("--------------------------------")
                logger.info("Evaluating summaries with LLM...")
                logger.info("--------------------------------")
            
            # Create evaluation prompt
            prompt = self._create_evaluation_prompt(generated_summary, reference_summary)
            
            # Get LLM response
            logger.info("Sending evaluation request to LLM...")
            response = self.llm.invoke(prompt)
            
            # Parse the response
            if hasattr(response, 'content'):
                response_text = response.content
            else:
                response_text = str(response)
            
            logger.info("Parsing LLM evaluation response...")
            result = self._parse_llm_response(response_text)
            
            return result
            
        except Exception as e:
            MultiAgentWorkflowException.log_exception(e, "LLMMetricEvaluator.evaluate")
            raise MultiAgentWorkflowException(f"Failed to evaluate summaries: {str(e)}")
    
    def get_overall_score(self, evaluation_result: Dict[str, Union[float, Dict]]) -> float:
        """
        Calculate overall score from evaluation results.
        
        Args:
            evaluation_result (Dict): Results from evaluate() method
            
        Returns:
            float: Overall weighted score
        """
        try:
            # Extract scores
            scores = []
            weights = {
                "accuracy": 0.25,
                "completeness": 0.20,
                "coherence": 0.15,
                "relevance": 0.15,
                "clarity": 0.15,
                "overall_quality": 0.10
            }
            
            weighted_sum = 0.0
            total_weight = 0.0
            
            for criterion, weight in weights.items():
                if criterion in evaluation_result:
                    if isinstance(evaluation_result[criterion], dict):
                        score = evaluation_result[criterion]["score"]
                    else:
                        score = float(evaluation_result[criterion])
                    
                    weighted_sum += score * weight
                    total_weight += weight
            
            return weighted_sum / total_weight if total_weight > 0 else 0.0
            
        except Exception as e:
            logger.error(f"Error calculating overall score: {e}")
            return 0.0
    
    def get_detailed_report(self, evaluation_result: Dict[str, Union[float, Dict]]) -> str:
        """
        Generate a detailed text report from evaluation results.
        
        Args:
            evaluation_result (Dict): Results from evaluate() method
            
        Returns:
            str: Formatted detailed report
        """
        try:
            report = "LLM Evaluation Report\n"
            report += "=" * 50 + "\n\n"
            
            # Individual scores
            for criterion in ["accuracy", "completeness", "coherence", "relevance", "clarity", "overall_quality"]:
                if criterion in evaluation_result:
                    if isinstance(evaluation_result[criterion], dict):
                        score = evaluation_result[criterion]["score"]
                        explanation = evaluation_result[criterion]["explanation"]
                    else:
                        score = float(evaluation_result[criterion])
                        explanation = "No explanation provided"
                    
                    report += f"{criterion.replace('_', ' ').title()}: {score:.3f}\n"
                    report += f"  Explanation: {explanation}\n\n"
            
            # Overall score
            overall_score = self.get_overall_score(evaluation_result)
            report += f"Overall Score: {overall_score:.3f}\n\n"
            
            # Summary
            if "summary" in evaluation_result:
                report += f"Summary: {evaluation_result['summary']}\n"
            
            return report
            
        except Exception as e:
            logger.error(f"Error generating detailed report: {e}")
            return "Error generating detailed report"


if __name__ == "__main__":
    """Example usage of the LLM metric evaluator."""
    # Example data
    generated_summary = "The Eiffel Tower is located in Paris, France. It was built in 1889 and stands 330 meters tall. The tower is one of the most famous landmarks in the world."
    reference_summary = "The Eiffel Tower is located in Paris, France. It was constructed in 1889 for the World's Fair and stands 330 meters (1,083 feet) tall. The tower is made of iron and is one of the most recognizable landmarks globally."
    
    try:
        evaluator = LLMMetricEvaluator(model_name="gpt-4o-mini")
        results = evaluator.evaluate(generated_summary, reference_summary)
        
        logger.info("Evaluation Results:")
        logger.info(json.dumps(results, indent=2))
        
        overall_score = evaluator.get_overall_score(results)
        logger.info(f"\nOverall Score: {overall_score:.3f}")
        
        detailed_report = evaluator.get_detailed_report(results)
        logger.info(f"\nDetailed Report:\n{detailed_report}")
        
    except Exception as e:
        logger.info(f"Error during evaluation: {e}")
