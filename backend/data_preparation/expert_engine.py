"""
Expert Cleaning Engine: Multi-perspective reasoning system
"""
import pandas as pd
import json
from typing import Dict, Any, List, Tuple
from .decision_logger import DecisionLogger
from .cleaning_engine import CLEANING_OPERATIONS, _apply_operation
from utils.llm_utils import rate_limited_llm_call


# Intent-based objectives
INTENT_OBJECTIVES = {
    "visualization": {
        "name": "Visualization / Dashboards",
        "priority": "Stability, completeness, smooth patterns",
        "avoid": "Variance spikes, missing gaps, extreme outliers"
    },
    "machine_learning": {
        "name": "Machine Learning / Modeling",
        "priority": "No leakage, normalized distributions, clean features",
        "avoid": "High cardinality, future data, target leakage"
    },
    "forecasting": {
        "name": "Time-series Forecasting",
        "priority": "Temporal continuity, seasonality preservation, stationary patterns",
        "avoid": "Time gaps, non-stationary variance, trend breaks"
    },
    "reporting": {
        "name": "Reporting / Compliance",
        "priority": "Completeness, accuracy, audit trail",
        "avoid": "Data loss, imputation uncertainty, transformation opacity"
    },
    "exploration": {
        "name": "Exploration / EDA",
        "priority": "Signal preservation, outlier visibility, distribution integrity",
        "avoid": "Over-cleaning, smoothing, aggressive filtering"
    }
}


def generate_expert_plans(
    profile: Dict[str, Any],
    intent: str,
    df_sample: pd.DataFrame
) -> Dict[str, Any]:
    """
    Generate 3 expert cleaning plans using parallel LLM reasoning.
    
    Args:
        profile: Dataset profile from profiler.py
        intent: User's primary use case
        df_sample: Sample of actual data (first 100 rows) for grounding
    
    Returns:
        {
            "expert_plans": [plan1, plan2, plan3],
            "recommended_plan": "expert_2",
            "intent_context": {...}
        }
    """
    
    # Prepare context
    intent_obj = INTENT_OBJECTIVES.get(intent, INTENT_OBJECTIVES["exploration"])
    
    # Get data sample summary for grounding
    sample_summary = {
        "shape": df_sample.shape,
        "dtypes": df_sample.dtypes.astype(str).to_dict(),
        "missing_per_col": df_sample.isna().sum().to_dict(),
        "sample_rows": df_sample.head(3).to_dict(orient="records")
    }
    
    # Run 3 expert LLM calls in parallel perspectives
    expert_1 = _call_expert_llm(
        expert_name="Signal Preservation Expert",
        role="Minimize information loss while addressing quality issues",
        objectives=[
            "Preserve variance and distribution shape",
            "Avoid row deletion when possible",
            "Keep outliers unless clearly erroneous",
            "Use interpolation over deletion"
        ],
        profile=profile,
        intent_obj=intent_obj,
        sample_summary=sample_summary
    )
    
    expert_2 = _call_expert_llm(
        expert_name="Stability & Interpretability Expert",
        role="Make data safe and readable for stakeholders",
        objectives=[
            "Maximize completeness and consistency",
            "Reduce variance spikes",
            "Prefer robust statistics (median, mode)",
            "Aggressive text cleaning"
        ],
        profile=profile,
        intent_obj=intent_obj,
        sample_summary=sample_summary
    )
    
    expert_3 = _call_expert_llm(
        expert_name="Model-Readiness Expert",
        role="Prepare data for downstream modeling and analysis",
        objectives=[
            "Remove leakage risks",
            "Normalize distributions",
            "Handle high cardinality",
            "Flag temporal issues"
        ],
        profile=profile,
        intent_obj=intent_obj,
        sample_summary=sample_summary
    )
    
    # Master arbiter scores and ranks
    arbiter_result = _call_arbiter_llm(
        expert_plans=[expert_1, expert_2, expert_3],
        intent=intent,
        intent_obj=intent_obj,
        profile=profile
    )
    
    return {
        "expert_plans": [expert_1, expert_2, expert_3],
        "recommended_plan": arbiter_result["recommended"],
        "intent_context": intent_obj,
        "arbiter_reasoning": arbiter_result["reasoning"]
    }


def _call_expert_llm(
    expert_name: str,
    role: str,
    objectives: List[str],
    profile: Dict[str, Any],
    intent_obj: Dict[str, Any],
    sample_summary: Dict[str, Any]
) -> Dict[str, Any]:
    """Call LLM with expert persona to generate cleaning plan."""
    
    # Build available operations list
    operations_desc = "\n".join([
        f"- {op_id}: {meta['name']} ({meta['impact']} impact) - {meta['description']}"
        for op_id, meta in CLEANING_OPERATIONS.items()
    ])
    
    # Build quality issues summary
    issues_summary = "\n".join([
        f"- {issue['message']} (severity: {issue['severity']})"
        for issue in profile.get("quality_issues", [])[:10]
    ])
    
    prompt = f"""
You are the **{expert_name}**.

Your role: {role}

Your objectives:
{chr(10).join(f"- {obj}" for obj in objectives)}

USER'S INTENT: {intent_obj['name']}
Priority: {intent_obj['priority']}
Avoid: {intent_obj['avoid']}

DATASET PROFILE:
- Rows: {profile['row_count']:,}
- Columns: {len(profile['columns'])}
- Structure: {profile['structure']}
- Duplicate rows: {profile['duplicate_rows']}

QUALITY ISSUES DETECTED:
{issues_summary if issues_summary else "- No major issues"}

COLUMN DETAILS (sample):
{json.dumps(list(profile['columns'].items())[:5], indent=2)}

DATA SAMPLE (for grounding):
Shape: {sample_summary['shape']}
Missing counts: {json.dumps(sample_summary['missing_per_col'], indent=2)}

AVAILABLE CLEANING OPERATIONS:
{operations_desc}

TASK:
Design a cleaning plan that aligns with YOUR ROLE and the user's intent.

OUTPUT REQUIREMENTS:
- Return ONLY valid JSON (no markdown, no code blocks, no explanatory text)
- Use double quotes for all strings
- No trailing commas in arrays or objects
- Numbers should be unquoted and WITHOUT + prefix (e.g., use 5.0 not +5.0, use -5.0 for negative)
- For percentages, use plain numbers: 91.0 not +91.0

JSON STRUCTURE:
{{
    "expert_name": "{expert_name}",
    "operations": [
        {{
            "operation_type": "<one of the operation IDs from AVAILABLE CLEANING OPERATIONS above>",
            "column": "column_name or 'all'",
            "reason": "Why this operation given your role and user intent",
            "expected_impact": {{
                "rows_affected": <estimate number>,
                "completeness_change_pct": <estimate number, e.g., 91.0 or -5.0, NO plus sign>,
                "variance_change_pct": <estimate number, e.g., -2.5 or 3.0, NO plus sign>
            }}
        }}
    ],
    "estimated_row_loss": <total rows that might be removed>,
    "estimated_variance_change": <expected % change in data variance>,
    "risk_flags": ["list", "of", "potential", "risks"],
    "confidence_score": <0.0 to 1.0>,
    "pros": ["Benefit 1", "Benefit 2"],
    "cons": ["Tradeoff 1", "Tradeoff 2"],
    "overall_justification": "2-3 sentence summary of your approach"
}}

CRITICAL:
- Use EXACT operation IDs from the AVAILABLE CLEANING OPERATIONS list (e.g., "cap_outliers", "remove_duplicates", "fill_missing_numeric_median")
- Do NOT use generic IDs like "operation_1", "operation_2" - these will not work
- Order operations logically (e.g., dedupe before imputation)
- Be specific about which columns need which operations
- Estimate impacts based on actual profile data
- Stay true to YOUR EXPERT ROLE
"""
    
    try:
        raw_response, _ = rate_limited_llm_call(prompt)
        
        # Clean markdown if present
        if "```json" in raw_response:
            raw_response = raw_response.split("```json")[1].split("```")[0].strip()
        elif "```" in raw_response:
            raw_response = raw_response.split("```")[1].split("```")[0].strip()
        
        # Additional cleanup
        raw_response = raw_response.strip()
        
        # Try to parse
        try:
            plan = json.loads(raw_response)
        except json.JSONDecodeError as json_err:
            print(f"[EXPERT] JSON parse error for {expert_name}: {json_err}")
            print(f"[EXPERT] Raw response preview: {raw_response[:500]}...")
            
            # Try to fix common JSON issues
            import re
            # Fix trailing commas
            raw_response = re.sub(r',(\s*[}\]])', r'\1', raw_response)
            # Fix numbers with + prefix (e.g., +91.0 -> 91.0, +5.0 -> 5.0)
            raw_response = re.sub(r':\s*\+(\d+\.?\d*)', r': \1', raw_response)
            raw_response = re.sub(r':\s*\+\s*(\d+\.?\d*)', r': \1', raw_response)
            # Try parsing again
            plan = json.loads(raw_response)
        
        return plan
    
    except Exception as e:
        print(f"[EXPERT] Error calling {expert_name}: {e}")
        print(f"[EXPERT] Full response (if available): {raw_response[:1000] if 'raw_response' in locals() else 'N/A'}...")
        # Return fallback minimal plan
        return {
            "expert_name": expert_name,
            "operations": [
                {
                    "operation_type": "remove_duplicates",
                    "column": "all",
                    "reason": "Fallback: Basic duplicate removal",
                    "expected_impact": {
                        "rows_affected": profile['duplicate_rows'],
                        "completeness_change_pct": 0,
                        "variance_change_pct": 0
                    }
                }
            ],
            "estimated_row_loss": profile['duplicate_rows'],
            "estimated_variance_change": 0,
            "risk_flags": ["LLM call failed - using fallback"],
            "confidence_score": 0.3,
            "pros": ["Safe fallback"],
            "cons": ["Not optimized"],
            "overall_justification": "Fallback plan due to LLM error"
        }


def _call_arbiter_llm(
    expert_plans: List[Dict[str, Any]],
    intent: str,
    intent_obj: Dict[str, Any],
    profile: Dict[str, Any]
) -> Dict[str, Any]:
    """Master arbiter scores and ranks the 3 expert plans."""
    
    prompt = f"""
You are the **Master Arbiter** for data cleaning strategy.

USER'S INTENT: {intent_obj['name']}
Priority: {intent_obj['priority']}
Avoid: {intent_obj['avoid']}

DATASET CONTEXT:
- Rows: {profile['row_count']:,}
- Structure: {profile['structure']}
- Quality issues: {len(profile.get('quality_issues', []))}

THREE EXPERT PLANS SUBMITTED:

EXPERT 1 - {expert_plans[0]['expert_name']}:
Operations: {len(expert_plans[0]['operations'])}
Estimated row loss: {expert_plans[0]['estimated_row_loss']}
Confidence: {expert_plans[0]['confidence_score']}
Pros: {', '.join(expert_plans[0]['pros'])}
Cons: {', '.join(expert_plans[0]['cons'])}
Justification: {expert_plans[0]['overall_justification']}

EXPERT 2 - {expert_plans[1]['expert_name']}:
Operations: {len(expert_plans[1]['operations'])}
Estimated row loss: {expert_plans[1]['estimated_row_loss']}
Confidence: {expert_plans[1]['confidence_score']}
Pros: {', '.join(expert_plans[1]['pros'])}
Cons: {', '.join(expert_plans[1]['cons'])}
Justification: {expert_plans[1]['overall_justification']}

EXPERT 3 - {expert_plans[2]['expert_name']}:
Operations: {len(expert_plans[2]['operations'])}
Estimated row loss: {expert_plans[2]['estimated_row_loss']}
Confidence: {expert_plans[2]['confidence_score']}
Pros: {', '.join(expert_plans[2]['pros'])}
Cons: {', '.join(expert_plans[2]['cons'])}
Justification: {expert_plans[2]['overall_justification']}

TASK:
Score each plan (0-100) based on alignment with user intent.
Consider:
- Appropriateness for intent
- Risk vs reward balance
- Practical impact
- Expert confidence

OUTPUT VALID JSON ONLY:
{{
    "scores": {{
        "expert_1": <0-100>,
        "expert_2": <0-100>,
        "expert_3": <0-100>
    }},
    "recommended": "expert_1|expert_2|expert_3",
    "reasoning": "2-3 sentences explaining your scoring and recommendation",
    "weight_distribution": {{
        "stability": <0.0-1.0>,
        "completeness": <0.0-1.0>,
        "signal_preservation": <0.0-1.0>,
        "model_safety": <0.0-1.0>
    }}
}}
"""
    
    try:
        raw_response, _ = rate_limited_llm_call(prompt)
        
        if raw_response.startswith("```json"):
            raw_response = raw_response[7:].strip()
        if raw_response.endswith("```"):
            raw_response = raw_response[:-3].strip()
        
        result = json.loads(raw_response)
        
        # Add scores to expert plans
        expert_plans[0]["score"] = result["scores"]["expert_1"]
        expert_plans[1]["score"] = result["scores"]["expert_2"]
        expert_plans[2]["score"] = result["scores"]["expert_3"]
        
        return result
    
    except Exception as e:
        print(f"[ARBITER] Error: {e}")
        # Fallback: score by confidence
        scores = {
            "expert_1": int(expert_plans[0]["confidence_score"] * 100),
            "expert_2": int(expert_plans[1]["confidence_score"] * 100),
            "expert_3": int(expert_plans[2]["confidence_score"] * 100)
        }
        
        recommended = max(scores, key=scores.get)
        
        expert_plans[0]["score"] = scores["expert_1"]
        expert_plans[1]["score"] = scores["expert_2"]
        expert_plans[2]["score"] = scores["expert_3"]
        
        return {
            "scores": scores,
            "recommended": recommended,
            "reasoning": "Fallback scoring based on expert confidence levels",
            "weight_distribution": {"stability": 0.25, "completeness": 0.25, "signal_preservation": 0.25, "model_safety": 0.25}
        }


def apply_expert_plan(
    df: pd.DataFrame,
    expert_plan: Dict[str, Any],
    profile: Dict[str, Any]
) -> Tuple[pd.DataFrame, Dict[str, Any], DecisionLogger]:
    """
    Apply expert's cleaning plan and measure real deltas.
    
    Returns:
        (cleaned_df, actual_stats, decision_log)
    """
    
    logger = DecisionLogger()
    df_cleaned = df.copy()
    
    before_stats = {
        "row_count": len(df),
        "column_count": len(df.columns),
        "missing_cells": int(df.isna().sum().sum()),
        "duplicate_rows": len(df) - len(df.drop_duplicates()),
        "total_variance": float(df.select_dtypes(include=['number']).var().sum()) if len(df.select_dtypes(include=['number']).columns) > 0 else 0
    }
    
    # Apply each operation from expert plan
    for idx, op in enumerate(expert_plan["operations"]):
        # Get operation type - try different field names for backwards compatibility
        op_type = op.get("operation_type") or op.get("id") or op.get("type")
        
        if not op_type:
            print(f"[EXPERT APPLY] Warning: Operation {idx+1} missing operation_type field")
            print(f"[EXPERT APPLY] Operation data: {op}")
            continue
        
        # If it's a generic ID like "operation_1", skip it
        if op_type.startswith("operation_"):
            print(f"[EXPERT APPLY] Warning: Invalid operation type '{op_type}' - should be a valid operation ID from CLEANING_OPERATIONS")
            print(f"[EXPERT APPLY] Available operations: {list(CLEANING_OPERATIONS.keys())}")
            continue
        
        # Check if operation exists
        if op_type not in CLEANING_OPERATIONS:
            print(f"[EXPERT APPLY] Error: Unknown operation type '{op_type}'")
            print(f"[EXPERT APPLY] Available operations: {list(CLEANING_OPERATIONS.keys())}")
            logger.log(
                action=op_type,
                column=op.get("column", "all"),
                reason=f"Unknown operation type",
                before={"status": "attempted"},
                after={"status": "failed"},
                impact="low"
            )
            continue
        
        try:
            # Use existing operation logic from cleaning_engine
            df_cleaned = _apply_operation(df_cleaned, op_type, profile, logger)
        except Exception as e:
            print(f"[EXPERT APPLY] Error applying {op_type}: {e}")
            logger.log(
                action=op_type,
                column=op.get("column", "all"),
                reason=f"Operation failed: {str(e)}",
                before={"status": "attempted"},
                after={"status": "failed"},
                impact="low"
            )
    
    after_stats = {
        "row_count": len(df_cleaned),
        "column_count": len(df_cleaned.columns),
        "missing_cells": int(df_cleaned.isna().sum().sum()),
        "duplicate_rows": len(df_cleaned) - len(df_cleaned.drop_duplicates()),
        "total_variance": float(df_cleaned.select_dtypes(include=['number']).var().sum()) if len(df_cleaned.select_dtypes(include=['number']).columns) > 0 else 0
    }
    
    # Calculate actual deltas
    actual_stats = {
        "before": before_stats,
        "after": after_stats,
        "deltas": {
            "row_loss": before_stats["row_count"] - after_stats["row_count"],
            "row_loss_pct": ((before_stats["row_count"] - after_stats["row_count"]) / before_stats["row_count"] * 100) if before_stats["row_count"] > 0 else 0,
            "missing_reduction": before_stats["missing_cells"] - after_stats["missing_cells"],
            "variance_change_pct": ((after_stats["total_variance"] - before_stats["total_variance"]) / before_stats["total_variance"] * 100) if before_stats["total_variance"] > 0 else 0
        }
    }
    
    return df_cleaned, actual_stats, logger
