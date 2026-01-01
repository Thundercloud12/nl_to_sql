"""
Decision Logger: Track all cleaning transformations with reasoning
"""
from typing import List, Dict, Any
from datetime import datetime
import numpy as np


def _convert_to_json_serializable(obj):
    """Convert numpy types to native Python types for JSON serialization."""
    if isinstance(obj, (np.integer, np.int64, np.int32)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float64, np.float32)):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, dict):
        return {k: _convert_to_json_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_convert_to_json_serializable(item) for item in obj]
    return obj


class DecisionLogger:
    """Log cleaning decisions with before/after context."""
    
    def __init__(self):
        self.decisions: List[Dict[str, Any]] = []
        self.start_time = datetime.now()
    
    def log(self, action: str, column: str, reason: str, 
            before: Dict[str, Any], after: Dict[str, Any], 
            impact: str = "low"):
        """
        Log a cleaning decision.
        
        Args:
            action: e.g., "fill_missing", "remove_outliers", "drop_duplicates"
            column: Column name affected (or "all" for row operations)
            reason: Human-readable explanation
            before: Stats before transformation
            after: Stats after transformation
            impact: "low" | "medium" | "high"
        """
        decision = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "column": column,
            "reason": reason,
            "before": _convert_to_json_serializable(before),
            "after": _convert_to_json_serializable(after),
            "impact": impact
        }
        self.decisions.append(decision)
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary of all decisions."""
        end_time = datetime.now()
        duration = (end_time - self.start_time).total_seconds()
        
        # Count by impact level
        impact_counts = {"low": 0, "medium": 0, "high": 0}
        for d in self.decisions:
            impact_counts[d["impact"]] += 1
        
        # Count by action type
        action_counts = {}
        for d in self.decisions:
            action = d["action"]
            action_counts[action] = action_counts.get(action, 0) + 1
        
        return {
            "total_decisions": len(self.decisions),
            "duration_seconds": duration,
            "impact_breakdown": impact_counts,
            "action_breakdown": action_counts,
            "decisions": self.decisions
        }
    
    def get_human_readable_log(self) -> List[str]:
        """Get human-readable timeline of decisions."""
        log_lines = []
        
        for i, d in enumerate(self.decisions, 1):
            impact_emoji = {"low": "✓", "medium": "⚠️", "high": "🔴"}[d["impact"]]
            
            line = f"{impact_emoji} {i}. {d['action'].replace('_', ' ').title()}"
            if d["column"] != "all":
                line += f" on column '{d['column']}'"
            line += f"\n   Reason: {d['reason']}"
            
            # Add before/after details
            if "rows_affected" in d["before"]:
                line += f"\n   Rows affected: {d['before']['rows_affected']} → {d['after']['rows_affected']}"
            if "missing_count" in d["before"]:
                line += f"\n   Missing: {d['before']['missing_count']} → {d['after']['missing_count']}"
            if "outliers" in d["before"]:
                line += f"\n   Outliers: {d['before']['outliers']} → {d['after']['outliers']}"
            
            log_lines.append(line)
        
        return log_lines
