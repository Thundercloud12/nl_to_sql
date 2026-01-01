"""
Cleaning Engine: Apply cleaning modes with toggleable operations
"""
import pandas as pd
import duckdb
import numpy as np
from typing import Dict, Any, List
from .decision_logger import DecisionLogger


# Define cleaning operations with metadata
CLEANING_OPERATIONS = {
    "remove_duplicates": {
        "name": "Remove Duplicate Rows",
        "description": "Delete exact duplicate rows to reduce redundancy",
        "impact": "medium",
        "applies_to": "all"
    },
    "fill_missing_numeric_mean": {
        "name": "Fill Missing (Mean)",
        "description": "Replace missing numeric values with column mean",
        "impact": "high",
        "applies_to": "numeric"
    },
    "fill_missing_numeric_median": {
        "name": "Fill Missing (Median)",
        "description": "Replace missing numeric values with column median (robust to outliers)",
        "impact": "high",
        "applies_to": "numeric"
    },
    "fill_missing_categorical_mode": {
        "name": "Fill Missing (Mode)",
        "description": "Replace missing categorical values with most frequent value",
        "impact": "high",
        "applies_to": "categorical"
    },
    "drop_missing_rows": {
        "name": "Drop Rows with Missing Values",
        "description": "Remove rows containing any missing values",
        "impact": "high",
        "applies_to": "all"
    },
    "remove_outliers_iqr": {
        "name": "Remove Outliers (IQR Method)",
        "description": "Remove values outside 1.5×IQR from Q1/Q3",
        "impact": "high",
        "applies_to": "numeric"
    },
    "cap_outliers": {
        "name": "Cap Outliers (Winsorization)",
        "description": "Cap extreme values at 5th and 95th percentiles",
        "impact": "medium",
        "applies_to": "numeric"
    },
    "interpolate_time_series": {
        "name": "Interpolate Time Series",
        "description": "Fill gaps in time series with linear interpolation",
        "impact": "medium",
        "applies_to": "time_series"
    },
    "normalize_whitespace": {
        "name": "Normalize Whitespace",
        "description": "Trim extra spaces and standardize text",
        "impact": "low",
        "applies_to": "text"
    },
    "standardize_case": {
        "name": "Standardize Text Case",
        "description": "Convert text columns to consistent case (lowercase/titlecase)",
        "impact": "low",
        "applies_to": "text"
    }
}


# Predefined cleaning modes
CLEANING_MODES = {
    "minimal": {
        "name": "Minimal Intervention",
        "description": "Only fix obvious errors without changing data distribution",
        "default_operations": [
            "remove_duplicates",
            "normalize_whitespace"
        ],
        "optional_operations": [
            "drop_missing_rows"
        ]
    },
    "visualization": {
        "name": "Visualization-Safe",
        "description": "Preserve outliers and patterns, fill gaps for smooth charts",
        "default_operations": [
            "remove_duplicates",
            "fill_missing_numeric_median",
            "fill_missing_categorical_mode",
            "interpolate_time_series",
            "normalize_whitespace"
        ],
        "optional_operations": [
            "cap_outliers"
        ]
    },
    "aggressive": {
        "name": "Aggressive Cleanup",
        "description": "Remove anomalies and standardize data (may lose signal)",
        "default_operations": [
            "remove_duplicates",
            "drop_missing_rows",
            "remove_outliers_iqr",
            "normalize_whitespace",
            "standardize_case"
        ],
        "optional_operations": [
            "fill_missing_numeric_mean",
            "fill_missing_categorical_mode"
        ]
    }
}


def apply_cleaning(
    df: pd.DataFrame,
    mode: str,
    deselected_operations: List[str],
    profile: Dict[str, Any],
    logger: DecisionLogger
) -> pd.DataFrame:
    """
    Apply cleaning operations based on mode and user selections.
    
    Args:
        df: Input DataFrame
        mode: "minimal" | "visualization" | "aggressive"
        deselected_operations: List of operation IDs user wants to skip
        profile: Output from profiler.profile_dataset()
        logger: DecisionLogger instance
    
    Returns:
        Cleaned DataFrame
    """
    
    if mode not in CLEANING_MODES:
        raise ValueError(f"Invalid mode: {mode}")
    
    mode_config = CLEANING_MODES[mode]
    operations_to_run = [
        op for op in mode_config["default_operations"]
        if op not in deselected_operations
    ]
    
    print(f"[CLEANING] Running {len(operations_to_run)} operations in '{mode}' mode")
    
    # Track original stats
    original_shape = df.shape
    
    # Run operations in order
    for op_id in operations_to_run:
        try:
            df = _apply_operation(df, op_id, profile, logger)
        except Exception as e:
            print(f"[CLEANING] ⚠️ Operation {op_id} failed: {e}")
            logger.log(
                action=op_id,
                column="all",
                reason=f"Operation failed: {str(e)}",
                before={"status": "attempted"},
                after={"status": "failed"},
                impact="low"
            )
    
    # Final summary
    final_shape = df.shape
    print(f"[CLEANING] ✓ Complete: {original_shape[0]} → {final_shape[0]} rows, "
          f"{original_shape[1]} → {final_shape[1]} columns")
    
    return df


def _apply_operation(
    df: pd.DataFrame,
    op_id: str,
    profile: Dict[str, Any],
    logger: DecisionLogger
) -> pd.DataFrame:
    """Apply single cleaning operation."""
    
    op_meta = CLEANING_OPERATIONS[op_id]
    print(f"[CLEANING] Applying: {op_meta['name']}")
    
    # OPERATION: Remove duplicates
    if op_id == "remove_duplicates":
        before_count = len(df)
        df = df.drop_duplicates()
        after_count = len(df)
        removed = before_count - after_count
        
        if removed > 0:
            logger.log(
                action="remove_duplicates",
                column="all",
                reason="Exact duplicate rows detected and removed",
                before={"row_count": before_count},
                after={"row_count": after_count, "removed": removed},
                impact="medium"
            )
    
    # OPERATION: Fill missing numeric (mean)
    elif op_id == "fill_missing_numeric_mean":
        numeric_cols = [col for col, meta in profile["columns"].items()
                       if meta["dtype"] == "numeric" and meta["missing_count"] > 0]
        
        for col in numeric_cols:
            before_missing = df[col].isna().sum()
            mean_val = df[col].mean()
            df[col] = df[col].fillna(mean_val)
            
            logger.log(
                action="fill_missing_mean",
                column=col,
                reason=f"Filled {before_missing} missing values with mean ({mean_val:.2f})",
                before={"missing_count": before_missing},
                after={"missing_count": 0, "fill_value": mean_val},
                impact="high"
            )
    
    # OPERATION: Fill missing numeric (median)
    elif op_id == "fill_missing_numeric_median":
        numeric_cols = [col for col, meta in profile["columns"].items()
                       if meta["dtype"] == "numeric" and meta["missing_count"] > 0]
        
        for col in numeric_cols:
            before_missing = df[col].isna().sum()
            if before_missing > 0:
                median_val = df[col].median()
                df[col] = df[col].fillna(median_val)
                
                logger.log(
                    action="fill_missing_median",
                    column=col,
                    reason=f"Filled {before_missing} missing values with median ({median_val:.2f})",
                    before={"missing_count": before_missing},
                    after={"missing_count": 0, "fill_value": median_val},
                    impact="high"
                )
    
    # OPERATION: Fill missing categorical (mode)
    elif op_id == "fill_missing_categorical_mode":
        categorical_cols = [col for col, meta in profile["columns"].items()
                           if meta["dtype"] in ["text", "categorical"] and meta["missing_count"] > 0]
        
        for col in categorical_cols:
            before_missing = df[col].isna().sum()
            if before_missing > 0:
                mode_val = df[col].mode()[0] if len(df[col].mode()) > 0 else "UNKNOWN"
                df[col] = df[col].fillna(mode_val)
                
                logger.log(
                    action="fill_missing_mode",
                    column=col,
                    reason=f"Filled {before_missing} missing values with most frequent value ('{mode_val}')",
                    before={"missing_count": before_missing},
                    after={"missing_count": 0, "fill_value": str(mode_val)},
                    impact="high"
                )
    
    # OPERATION: Drop rows with any missing
    elif op_id == "drop_missing_rows":
        before_count = len(df)
        df = df.dropna()
        after_count = len(df)
        removed = before_count - after_count
        
        if removed > 0:
            logger.log(
                action="drop_missing_rows",
                column="all",
                reason=f"Removed {removed} rows containing missing values",
                before={"row_count": before_count},
                after={"row_count": after_count, "removed": removed},
                impact="high"
            )
    
    # OPERATION: Remove outliers (IQR)
    elif op_id == "remove_outliers_iqr":
        numeric_cols = [col for col, meta in profile["columns"].items()
                       if meta["dtype"] == "numeric" and meta.get("has_outliers", False)]
        
        for col in numeric_cols:
            before_count = len(df)
            Q1 = df[col].quantile(0.25)
            Q3 = df[col].quantile(0.75)
            IQR = Q3 - Q1
            lower_bound = Q1 - 1.5 * IQR
            upper_bound = Q3 + 1.5 * IQR
            
            df = df[(df[col] >= lower_bound) & (df[col] <= upper_bound)]
            after_count = len(df)
            removed = before_count - after_count
            
            if removed > 0:
                logger.log(
                    action="remove_outliers_iqr",
                    column=col,
                    reason=f"Removed {removed} outliers outside [{lower_bound:.2f}, {upper_bound:.2f}]",
                    before={"row_count": before_count, "outliers": removed},
                    after={"row_count": after_count, "outliers": 0},
                    impact="high"
                )
    
    # OPERATION: Cap outliers (Winsorization)
    elif op_id == "cap_outliers":
        numeric_cols = [col for col, meta in profile["columns"].items()
                       if meta["dtype"] == "numeric" and meta.get("has_outliers", False)]
        
        for col in numeric_cols:
            p5 = df[col].quantile(0.05)
            p95 = df[col].quantile(0.95)
            capped_count = ((df[col] < p5) | (df[col] > p95)).sum()
            
            if capped_count > 0:
                df[col] = df[col].clip(lower=p5, upper=p95)
                
                logger.log(
                    action="cap_outliers",
                    column=col,
                    reason=f"Capped {capped_count} extreme values at 5th/95th percentiles [{p5:.2f}, {p95:.2f}]",
                    before={"outliers": capped_count},
                    after={"outliers": 0, "bounds": [p5, p95]},
                    impact="medium"
                )
    
    # OPERATION: Interpolate time series
    elif op_id == "interpolate_time_series":
        # Find temporal column
        temporal_cols = [col for col, meta in profile["columns"].items()
                        if meta["role"] == "temporal"]
        
        if temporal_cols and profile["structure"] == "time_series":
            time_col = temporal_cols[0]
            # Sort by time
            df = df.sort_values(by=time_col)
            
            # Interpolate numeric columns
            numeric_cols = [col for col, meta in profile["columns"].items()
                           if meta["dtype"] == "numeric" and meta["missing_count"] > 0]
            
            for col in numeric_cols:
                before_missing = df[col].isna().sum()
                if before_missing > 0:
                    df[col] = df[col].interpolate(method='linear', limit_direction='both')
                    after_missing = df[col].isna().sum()
                    
                    logger.log(
                        action="interpolate_time_series",
                        column=col,
                        reason=f"Interpolated {before_missing - after_missing} missing values in time series",
                        before={"missing_count": before_missing},
                        after={"missing_count": after_missing},
                        impact="medium"
                    )
    
    # OPERATION: Normalize whitespace
    elif op_id == "normalize_whitespace":
        text_cols = [col for col, meta in profile["columns"].items()
                    if meta["dtype"] == "text"]
        
        for col in text_cols:
            df[col] = df[col].astype(str).str.strip().str.replace(r'\s+', ' ', regex=True)
        
        if text_cols:
            logger.log(
                action="normalize_whitespace",
                column=", ".join(text_cols),
                reason="Trimmed whitespace and normalized spacing in text columns",
                before={"columns_affected": len(text_cols)},
                after={"status": "cleaned"},
                impact="low"
            )
    
    # OPERATION: Standardize case
    elif op_id == "standardize_case":
        text_cols = [col for col, meta in profile["columns"].items()
                    if meta["dtype"] == "text"]
        
        for col in text_cols:
            df[col] = df[col].astype(str).str.lower()
        
        if text_cols:
            logger.log(
                action="standardize_case",
                column=", ".join(text_cols),
                reason="Converted text columns to lowercase for consistency",
                before={"columns_affected": len(text_cols)},
                after={"status": "standardized"},
                impact="low"
            )
    
    return df
