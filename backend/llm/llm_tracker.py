import json
import time
import os
from datetime import datetime
from threading import Lock

# Thread-safe lock for file writes
_file_lock = Lock()

TRACKING_FILE = "llm_usage_log.json"

def _load_existing_logs() -> list:
    """Load existing logs from file."""
    if os.path.exists(TRACKING_FILE):
        try:
            with open(TRACKING_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []
    return []

def _save_logs(logs: list):
    """Save logs to file - DISABLED: No longer writing to JSON file."""
    # File writing disabled to reduce I/O overhead
    # with _file_lock:
    #     with open(TRACKING_FILE, "w") as f:
    #         json.dump(logs, f, indent=2)
    pass

def log_llm_call(
    function_name: str,
    model_name: str,
    prompt: str,
    response_text: str,
    start_time: float,
    end_time: float,
    input_tokens: int = None,
    output_tokens: int = None,
    total_tokens: int = None,
    metadata: dict = None
):
    """
    Log an LLM call with timing and token usage.
    
    Args:
        function_name: Name of the function making the call
        model_name: Name of the LLM model used
        prompt: The input prompt
        response_text: The response from the LLM
        start_time: time.time() when call started
        end_time: time.time() when call ended
        input_tokens: Number of input tokens (if available)
        output_tokens: Number of output tokens (if available)
        total_tokens: Total tokens used (if available)
        metadata: Any additional metadata
    """
    duration_seconds = end_time - start_time
    
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "function_name": function_name,
        "model_name": model_name,
        "duration_seconds": round(duration_seconds, 3),
        "duration_ms": round(duration_seconds * 1000, 1),
        "prompt_length_chars": len(prompt),
        "response_length_chars": len(response_text),
        "tokens": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens
        },
        "metadata": metadata or {}
    }
    
    # Load, append, save
    logs = _load_existing_logs()
    logs.append(log_entry)
    _save_logs(logs)
    
    # Also print for debugging
    print(f"[LLM_TRACKER] {function_name} | Model: {model_name} | Duration: {duration_seconds:.3f}s | Tokens: {total_tokens}")
    
    return log_entry

def get_summary() -> dict:
    """Get summary statistics of all LLM calls."""
    logs = _load_existing_logs()
    
    if not logs:
        return {"total_calls": 0}
    
    total_duration = sum(log["duration_seconds"] for log in logs)
    total_tokens = sum(log["tokens"]["total_tokens"] or 0 for log in logs)
    
    # Group by function
    by_function = {}
    for log in logs:
        fn = log["function_name"]
        if fn not in by_function:
            by_function[fn] = {"calls": 0, "total_duration": 0, "total_tokens": 0}
        by_function[fn]["calls"] += 1
        by_function[fn]["total_duration"] += log["duration_seconds"]
        by_function[fn]["total_tokens"] += log["tokens"]["total_tokens"] or 0
    
    return {
        "total_calls": len(logs),
        "total_duration_seconds": round(total_duration, 3),
        "total_tokens": total_tokens,
        "by_function": by_function,
        "logs": logs
    }

def clear_logs():
    """Clear all logs."""
    _save_logs([])