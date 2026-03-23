"""
Script to fetch GroundTruthCommentary data from the database, evaluate commentary,
and save results to CommentaryEvaluation table.

Workflow:
1. Fetch ground truth commentary from ground_truth_commentaries table
2. Evaluate generated commentary against ground truth
3. Save evaluation results to commentary_evaluations table
"""
import sys
from sqlalchemy import select, and_, or_, cast
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime
from typing import Optional, List, Dict, Any

from hello.models import CommentaryEvaluation, GroundTruthCommentary
from hello.services.database import async_session  
from hello.ml.logger import GLOBAL_LOGGER as logger
from hello.ml.exception.custom_exception import MultiAgentWorkflowException

class CommentaryEvaluationService:
    """
    Service class for fetching and evaluating commentary evaluations.
    Provides a modular interface for database operations and evaluation metrics.
    """
    
    def __init__(self):
        """Initialize the CommentaryEvaluationService.

        Note: Engine/session management is delegated to the shared infrastructure
        in `hello.services.database`. This service now simply acquires sessions
        from the imported `async_session` factory.
        """
        # No local engine/session; reuse global async_session
        pass
    
    async def fetch_evaluations(
        self,
        section_name: Optional[str] = None,
        property_type: Optional[str] = None,
        property_sub_type: Optional[str] = None,
        division: Optional[str] = None,
        publishing_group: Optional[str] = None,
        automation_mode: Optional[str] = None,
        quarter: Optional[str] = None,
        history_range: Optional[str] = None,
        defined_markets: Optional[List[str]] = None,
        absorption_calculation: Optional[str] = None,
        total_vs_direct_absorption: Optional[str] = None,
        asking_rate_frequency: Optional[str] = None,
        asking_rate_type: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch ground truth commentaries based on filters.
        
        Args:
            section_name: Filter by section name (partial match)
            property_type: Filter by property type (partial match)
            property_sub_type: Filter by property sub type (partial match)
            division: Filter by division (partial match)
            publishing_group: Filter by publishing group (partial match)
            automation_mode: Filter by automation mode (partial match)
            quarter: Filter by quarter (partial match)
            history_range: Filter by history range (partial match)
            defined_markets: Filter by defined markets (exact match)
            limit: Limit the number of results returned
        
        Returns:
            List of dictionaries containing the ground truth commentary data
        """
        try:
            async with async_session() as session:
                # Build the query - using GroundTruthCommentary table
                stmt = select(GroundTruthCommentary)
                
                # Apply filters
                conditions = []
                if section_name:
                    conditions.append(GroundTruthCommentary.section_name.ilike(f"%{section_name}%"))
                if property_type:
                    conditions.append(GroundTruthCommentary.property_type.ilike(f"%{property_type}%"))
                if property_sub_type:
                    conditions.append(GroundTruthCommentary.property_sub_type.ilike(f"%{property_sub_type}%"))
                if division:
                    conditions.append(GroundTruthCommentary.division.ilike(f"%{division}%"))
                if publishing_group:
                    conditions.append(GroundTruthCommentary.publishing_group.ilike(f"%{publishing_group}%"))
                if automation_mode:
                    conditions.append(GroundTruthCommentary.automation_mode.ilike(f"%{automation_mode}%"))
                if quarter:
                    conditions.append(GroundTruthCommentary.quarter.ilike(f"%{quarter}%"))
                if history_range:
                    conditions.append(GroundTruthCommentary.history_range.ilike(f"%{history_range}%"))
                if absorption_calculation:
                    conditions.append(GroundTruthCommentary.absorption_calculation.ilike(f"%{absorption_calculation}%"))
                if total_vs_direct_absorption:
                    conditions.append(GroundTruthCommentary.total_vs_direct_absorption.ilike(f"%{total_vs_direct_absorption}%"))
                if asking_rate_frequency:
                    conditions.append(GroundTruthCommentary.asking_rate_frequency.ilike(f"%{asking_rate_frequency}%"))
                if asking_rate_type:
                    conditions.append(GroundTruthCommentary.asking_rate_type.ilike(f"%{asking_rate_type}%"))
                if defined_markets:
                    # Normalize and filter empty strings
                    cleaned_markets = [str(m).strip() for m in defined_markets if str(m).strip()]
                    if cleaned_markets:
                        # ANY-overlap semantics: at least one of the provided markets must be present.
                        # Use PostgreSQL JSONB containment operator @> via SQLAlchemy .op('@>') for reliable matching.
                        # Convert each single-element list to JSONB for containment check.
                        overlap_conditions = [
                            GroundTruthCommentary.defined_markets.cast(JSONB).op('@>')(cast([m], JSONB))
                            for m in cleaned_markets
                        ]
                        conditions.append(or_(*overlap_conditions))
                
                if conditions:
                    stmt = stmt.where(and_(*conditions))
                
                # Order by created_at descending
                stmt = stmt.order_by(GroundTruthCommentary.created_at.desc())
                
                # Apply limit if specified
                if limit:
                    stmt = stmt.limit(limit)
                
                # Execute query
                result = await session.execute(stmt)
                evaluations = list(result.scalars().all())
                
                # Convert to dictionaries
                evaluations_dict = []
                for eval_record in evaluations:
                    eval_dict = {
                        "id": eval_record.id,
                        "section_name": eval_record.section_name,
                        "property_type": eval_record.property_type,
                        "property_sub_type": eval_record.property_sub_type,
                        "division": eval_record.division,
                        "publishing_group": eval_record.publishing_group,
                        "automation_mode": eval_record.automation_mode,
                        "quarter": eval_record.quarter,
                        "history_range": eval_record.history_range,
                        "defined_markets": eval_record.defined_markets,
                        "absorption_calculation": eval_record.absorption_calculation,
                        "total_vs_direct_absorption": eval_record.total_vs_direct_absorption,
                        "asking_rate_frequency": eval_record.asking_rate_frequency,
                        "asking_rate_type": eval_record.asking_rate_type,
                        "ground_truth_commentary": eval_record.ground_truth_commentary,
                        "created_at": eval_record.created_at.isoformat() if eval_record.created_at else None,
                    }
                    evaluations_dict.append(eval_dict)
                
                return evaluations_dict
        except Exception as e:
            MultiAgentWorkflowException.log_exception(e, "fetch_evaluations")
            raise MultiAgentWorkflowException("Error in fetch_evaluations", sys.exc_info())
    
    async def evaluate_commentary(
        self,
        generated_commentary: str,
        ground_truth_commentary: str,
        evaluation_types: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Evaluate generated commentary against ground truth.
        
        Args:
            generated_commentary: The generated commentary to evaluate
            ground_truth_commentary: The reference commentary
            evaluation_types: List of evaluation types (e.g., ['factual_correctness', 'relevance'])
        
        Returns:
            Dictionary containing evaluation results
        """
        evaluation_results = {}
        
        # Set default evaluation types if not provided
        if evaluation_types is None:
            evaluation_types = ['factual_correctness']
        
        # Try to perform factual correctness evaluation
        model_details: Dict[str, Any] = {}
        if 'factual_correctness' in evaluation_types:
            try:
                from hello.ml.evaluation.metrics.factual_correctness import FactualCorrectnessEvaluator
                evaluator = FactualCorrectnessEvaluator()
                evaluation_result = evaluator.evaluate_factual_correctness(
                    generated_commentary,
                    ground_truth_commentary
                )
                evaluation_results['factual_correctness'] = evaluation_result
                # Extract model details from base evaluator
                try:
                    model_details = evaluator.get_model_details()
                except Exception as _md_err:
                    MultiAgentWorkflowException.log_exception(_md_err, "evaluate_commentary_get_model_details")
                    raise MultiAgentWorkflowException("Error in evaluate_commentary get_model_details", sys.exc_info())
            except Exception as e:
                MultiAgentWorkflowException.log_exception(e, "evaluate_commentary_factual_correctness")
                raise MultiAgentWorkflowException("Error in evaluate_commentary factual_correctness", sys.exc_info())
        # Attach model_details to top-level results for persistence usage
        evaluation_results['__model_details__'] = model_details
        
        return evaluation_results
    
    async def fetch_and_evaluate(
        self,
        filters: Dict[str, Any],
        generated_commentary: str,
        evaluation_types: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Fetch evaluations and perform scoring on the generated commentary.
        
        Args:
            filters: Dictionary of filters to apply (section_name, property_type, etc.)
            generated_commentary: The generated commentary to evaluate
            evaluation_types: List of evaluation types to perform
        
        Returns:
            Dictionary containing fetched evaluations and their scores
        """
        try:
            # Fetch evaluations based on filters
            evaluations = await self.fetch_evaluations(**filters)
            
            if not evaluations:
                return {
                    "evaluations": [],
                    "scores": {},
                    "message": "No evaluations found matching the criteria"
                }
            
            # Perform evaluation on the first match
            result = {
                "evaluations": evaluations,
                "scores": {}
            }
            
            if evaluations:
                ground_truth = evaluations[0].get("ground_truth_commentary", "")
                if ground_truth:
                    scores = await self.evaluate_commentary(
                        generated_commentary,
                        ground_truth,
                        evaluation_types
                    )
                    result["scores"] = scores
            
            return result
        except Exception as e:
            MultiAgentWorkflowException.log_exception(e, "fetch_and_evaluate")
            raise MultiAgentWorkflowException("Error in fetch_and_evaluate", sys.exc_info())
    
    async def update_evaluation_result(
        self,
        evaluation_id: int,
        evaluation_result: Dict[str, Any]
    ) -> bool:
        """
        Update the evaluation_result field for an existing evaluation record.
        
        Args:
            evaluation_id: The ID of the evaluation record to update
            evaluation_result: Dictionary containing the evaluation results
        
        Returns:
            True if successful, False otherwise
        """
        try:
            async with async_session() as session:
                # Find the evaluation record
                stmt = select(CommentaryEvaluation).where(
                    CommentaryEvaluation.id == evaluation_id
                )
                result = await session.execute(stmt)
                eval_record = result.scalar_one_or_none()
                
                if eval_record:
                    # Update the evaluation_result field
                    eval_record.evaluation_result = evaluation_result
                    await session.commit()
                    return True
                else:
                    logger.error(f"No evaluation found with ID: {evaluation_id}")
                    return False
        except Exception as e:
            MultiAgentWorkflowException.log_exception(e, "update_evaluation_result")
            raise MultiAgentWorkflowException("Error in update_evaluation_result", sys.exc_info())
    
    async def insert_evaluation_record(
        self,
        section_name: str,
        property_type: str,
        generated_commentary: str,
        ground_truth_commentary: str,
        evaluation_result: Dict[str, Any],
        model_details: Optional[Dict[str, Any]] = None,
        property_sub_type: Optional[str] = None,
        division: Optional[str] = None,
        publishing_group: Optional[str] = None,
        automation_mode: Optional[str] = None,
        quarter: Optional[str] = None,
        history_range: Optional[str] = None,
        defined_markets: Optional[List[str]] = None,
        absorption_calculation: Optional[str] = None,
        total_vs_direct_absorption: Optional[str] = None,
        asking_rate_frequency: Optional[str] = None,
        asking_rate_type: Optional[str] = None,
        report_id: Optional[int] = None,
        run_id: Optional[int] = None,
    ) -> Optional[int]:
        """
        Insert a new evaluation record with evaluation results.
        
        Args:
            section_name: Name of the section
            property_type: Property type
            generated_commentary: The generated commentary
            ground_truth_commentary: The reference commentary
            evaluation_result: Dictionary containing the evaluation results
            property_sub_type: Optional property sub type
            division: Optional division
            publishing_group: Optional publishing group
            automation_mode: Optional automation mode
            quarter: Optional quarter
            history_range: Optional history range
            defined_markets: Optional list of defined markets
            absorption_calculation: Optional absorption calculation method
            total_vs_direct_absorption: Optional total vs direct absorption
            asking_rate_frequency: Optional asking rate frequency
            asking_rate_type: Optional asking rate type
            report_id: Optional report ID to link the evaluation
            run_id: Optional report run ID to link the evaluation to a specific execution
        
        Returns:
            The ID of the newly created record, or None if failed
        """
        try:
            async with async_session() as session:
                # Create new evaluation record
                new_eval = CommentaryEvaluation(
                    report_id=report_id,
                    run_id=run_id,
                    section_name=section_name,
                    property_type=property_type,
                    property_sub_type=property_sub_type,
                    division=division,
                    publishing_group=publishing_group,
                    automation_mode=automation_mode,
                    quarter=quarter,
                    history_range=history_range,
                    defined_markets=defined_markets if defined_markets else [],
                    absorption_calculation=absorption_calculation,
                    total_vs_direct_absorption=total_vs_direct_absorption,
                    asking_rate_frequency=asking_rate_frequency,
                    asking_rate_type=asking_rate_type,
                    generated_commentary=generated_commentary,
                    ground_truth_commentary=ground_truth_commentary,
                    evaluation_result=evaluation_result,
                    model_details=model_details or {}
                )
                
                session.add(new_eval)
                await session.commit()
                await session.refresh(new_eval)
                
                return new_eval.id
        except Exception as e:
            MultiAgentWorkflowException.log_exception(e, "insert_evaluation_record")
            raise MultiAgentWorkflowException("Error in insert_evaluation_record", sys.exc_info())
    
    async def evaluate_and_save(
        self,
        filters: Dict[str, Any],
        generated_commentary: str,
        evaluation_types: Optional[List[str]] = None,
        report_id: Optional[int] = None,
        run_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Fetch evaluations, perform scoring, and save the results to the database.
        
        Args:
            filters: Dictionary of filters to apply (section_name, property_type, etc.)
            generated_commentary: The generated commentary to evaluate
            evaluation_types: List of evaluation types to perform
            report_id: Optional report identifier for associating the evaluation
            run_id: Optional run identifier for associating the evaluation with a concrete execution
        
        Returns:
            Dictionary containing fetched evaluations, scores, and save status
        """
        try:
            if run_id is not None and (not isinstance(run_id, int) or run_id <= 0):
                raise ValueError("run_id must be a positive integer if provided")
            # Fetch evaluations based on filters
            evaluations = await self.fetch_evaluations(**filters)
            
            if not evaluations:
                return {
                    "evaluations": [],
                    "scores": {},
                    "saved": False,
                    "message": "No evaluations found matching the criteria"
                }
            
            # Get the first matching evaluation
            first_eval = evaluations[0]
            ground_truth = first_eval.get("ground_truth_commentary", "")
            
            if not ground_truth:
                return {
                    "evaluations": evaluations,
                    "scores": {},
                    "saved": False,
                    "message": "No ground truth commentary found"
                }
            
            # Perform evaluation
            scores = await self.evaluate_commentary(
                generated_commentary,
                ground_truth,
                evaluation_types
            )
            # Extract model details for persistence
            model_details = scores.pop("__model_details__", {}) if isinstance(scores, dict) else {}
            
            # Upsert logic: attempt to update existing evaluation (by report_id + section_name), else insert
            saved = False
            saved_id = None
            updated_id = None
            if report_id is not None:
                try:
                    async with async_session() as session:
                        # Attempt to locate an existing evaluation for this report & section
                        stmt = select(CommentaryEvaluation.id).where(
                            CommentaryEvaluation.report_id == report_id,
                            CommentaryEvaluation.section_name == first_eval.get("section_name", ""),
                        ).limit(1)
                        existing_id = (await session.execute(stmt)).scalar_one_or_none()
                        if existing_id:
                            # Update existing record fields
                            upd_stmt = (
                                select(CommentaryEvaluation).where(CommentaryEvaluation.id == existing_id)
                            )
                            rec = (await session.execute(upd_stmt)).scalar_one_or_none()
                            if rec:
                                rec.generated_commentary = generated_commentary
                                rec.ground_truth_commentary = ground_truth
                                rec.evaluation_result = scores
                                # Overwrite model_details each evaluation (keeps latest provenance)
                                rec.model_details = model_details or {}
                                if run_id is not None:
                                    rec.run_id = run_id
                                rec.created_at = datetime.utcnow()
                                await session.commit()
                                updated_id = existing_id
                                saved = True
                                saved_id = None
                            else:
                                logger.warning("evaluate_and_save: expected existing evaluation id %s not found; will insert new", existing_id)
                        else:
                            # No existing record; proceed to insert
                            pass
                except Exception as _upd_err:
                    MultiAgentWorkflowException.log_exception(_upd_err, "evaluate_and_save_update_existing")
                    raise MultiAgentWorkflowException("Error in evaluate_and_save update existing", sys.exc_info())
            # Insert path if no update happened
            if not updated_id:
                saved_id = await self.insert_evaluation_record(
                    section_name=first_eval.get("section_name", ""),
                    property_type=first_eval.get("property_type", ""),
                    generated_commentary=generated_commentary,
                    ground_truth_commentary=ground_truth,
                    evaluation_result=scores,
                    model_details=model_details,
                    property_sub_type=first_eval.get("property_sub_type"),
                    division=first_eval.get("division"),
                    publishing_group=first_eval.get("publishing_group"),
                    automation_mode=first_eval.get("automation_mode"),
                    quarter=first_eval.get("quarter"),
                    history_range=first_eval.get("history_range"),
                    defined_markets=first_eval.get("defined_markets"),
                    absorption_calculation=first_eval.get("absorption_calculation"),
                    total_vs_direct_absorption=first_eval.get("total_vs_direct_absorption"),
                    asking_rate_frequency=first_eval.get("asking_rate_frequency"),
                    asking_rate_type=first_eval.get("asking_rate_type"),
                    report_id=report_id,
                    run_id=run_id,
                )
                saved = saved_id is not None
            
            return {
                "evaluations": evaluations,
                "scores": scores,
                "saved": saved,
                "saved_id": saved_id,
                "updated_id": updated_id,
                "message": f"Evaluation {'saved' if saved else 'failed to save'} to commentary_evaluations table"
            }
        except Exception as e:
            MultiAgentWorkflowException.log_exception(e, "evaluate_and_save")
            raise MultiAgentWorkflowException("Error in evaluate_and_save", sys.exc_info())


# Example usage - for testing purposes
async def main():
    """Example function to test CommentaryEvaluationService."""
    service = CommentaryEvaluationService()
    
    # Example 1: Just fetch evaluations
    logger.info("--- Example 1: Fetch evaluations ---")
    evaluations = await service.fetch_evaluations(
        section_name="Net Absorption",
        property_type="Industrial",
        property_sub_type="Figures",
        division="Midwest",
        publishing_group="Published National",
        automation_mode="tier1",
        quarter="2025 Q2",
        history_range="3-Year",
        limit=10
    )
    
    logger.info("Found %s evaluation(s)", len(evaluations))
    for eval in evaluations:
        logger.info("ID: %s, Section: %s", eval["id"], eval["section_name"])
    
    # Example 2: Fetch, evaluate and save to database
    if evaluations:
        generated_text = evaluations[0].get("generated_commentary", "")
        
        if generated_text:
            logger.info("\n--- Example 2: Fetch, evaluate and save ---")
            result = await service.evaluate_and_save(
                filters={
                    "section_name": "Construction Activity",
                    "property_type": "Industrial"
                },
                generated_commentary=generated_text,
                evaluation_types=['factual_correctness'],
            )
            logger.info("Evaluation scores: %s", result.get("scores", {}))
            logger.info("Saved to database: %s", result.get("saved", False))
            if result.get('updated_id'):
                logger.info("Updated record ID: %s", result.get("updated_id"))
            if result.get('saved_id'):
                logger.info("New record ID: %s", result.get("saved_id"))
