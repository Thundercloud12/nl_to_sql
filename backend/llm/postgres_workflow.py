# postgres_workflow.py - PostgreSQL-specific LangGraph workflow
from typing import Dict, Any, List
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
import uuid
import json
import os
from insight_generator import generate_insight1
from .llm_tracker import log_llm_call
import time
from utils.llm_utils import rate_limited_llm_call
from utils.postgres_connector import PostgresConnector
from utils.database_utilities import db_cursor
from dotenv import load_dotenv
load_dotenv()

def quote_identifier(ident: str) -> str:
    parts = ident.split(".")
    return ".".join(f'"{p}"' for p in parts)


# Import the SAME schema loading functions used by file workflow
def load_schema_graph(data_source_id: str) -> dict:
    """Load schema graph from datasource-specific folder (same as file workflow)."""
    graph_path = os.path.join("uploaded_files", f"datasource_{data_source_id}", "schema_graph.json")
    if not os.path.exists(graph_path):
        raise FileNotFoundError(f"Schema graph not found at {graph_path}. Please run schema build first.")
    with open(graph_path, "r") as f:
        return json.load(f)


def load_raw_metadata(data_source_id: str) -> dict:
    """Load raw metadata from datasource-specific folder (same as file workflow)."""
    metadata_path = os.path.join("uploaded_files", f"datasource_{data_source_id}", "raw_metadata.json")
    if not os.path.exists(metadata_path):
        raise FileNotFoundError(f"Metadata not found at {metadata_path}. Please run schema build first.")
    with open(metadata_path, "r") as f:
        return json.load(f)

def merge_plans(old, new):
    """Merge two plans, accumulating lists and preferring new values for scalars."""
    if old is None:
        return new.copy() if new else {}
    if new is None:
        return old.copy() if old else {}

    merged = {}

    old_tables = old.get("tables", [])
    new_tables = new.get("tables", [])
    merged["tables"] = list(dict.fromkeys(old_tables + new_tables)) 

    old_filters = old.get("filters", [])
    new_filters = new.get("filters", [])
    merged["filters"] = old_filters + [f for f in new_filters if f not in old_filters]

    old_joins = old.get("joins", [])
    new_joins = new.get("joins", [])
    existing_join_keys = {(j.get("left"), j.get("right")) for j in old_joins}
    merged["joins"] = old_joins + [
        j for j in new_joins 
        if (j.get("left"), j.get("right")) not in existing_join_keys
    ]

    old_ops = old.get("operations", [])
    new_ops = new.get("operations", [])
    merged["operations"] = old_ops + [op for op in new_ops if op not in old_ops]

    old_group = old.get("group_by", [])
    new_group = new.get("group_by", [])
    merged["group_by"] = list(dict.fromkeys(old_group + new_group))

    merged["final_output"] = new.get("final_output") or old.get("final_output", "table")
    merged["execution_mode"] = new.get("execution_mode") or old.get("execution_mode", "sql")
    merged["needs_clarification"] = old.get("needs_clarification", False) or new.get("needs_clarification", False)
    
    old_qs = old.get("clarification_questions", [])
    new_qs = new.get("clarification_questions", [])
    merged["clarification_questions"] = old_qs + [q for q in new_qs if q not in old_qs]

    old_meta = old.get("metadata_requests", [])
    new_meta = new.get("metadata_requests", [])
    merged["metadata_requests"] = old_meta + new_meta

    return merged


class PostgresState(dict):
    """
    State for PostgreSQL workflow.
    """
    user_question: str
    data_source_id: str
    schema_info: Dict[str, Any] | None
    planner_output: Dict[str, Any] | None
    sql_result: Any | None
    clarification_answer: str | None
    metadata_requests: List[str] | None
    insights: str | None
    final_answer: str | None
    status: str | None
    pending_question: str | None
    postgres_connector: PostgresConnector | None
    chart_data: Dict[str, Any] | None


def input_node(state: PostgresState) -> PostgresState:
    """Entry point - validates and initializes state."""
    print("[POSTGRES INPUT NODE] Processing user question...")
    
    if not state.get("user_question"):
        raise ValueError("user_question is required")
    
    if not state.get("data_source_id"):
        raise ValueError("data_source_id is required")
    
    return state


def build_intelligent_schema(raw_metadata):
    """Build schema with intelligent pattern analysis (same as file workflow)."""
    schema_text = "AVAILABLE TABLES & COLUMNS:\n"
    
    for table_short, table_info in raw_metadata.get("tables", {}).items():
        original_name = table_info.get("original_name", "Unknown")
        columns = table_info.get("columns", [])
        canonical_types = table_info.get("canonical_types", {})
        sample_values = table_info.get("sample_values", table_info.get("samples", {}))
        
        schema_text += f"\n{table_short} ({original_name}):\n"
        
        # Show columns with their data types
        if canonical_types:
            schema_text += "  Columns & Types:\n"
            for col in columns:
                col_type = canonical_types.get(col, "UNKNOWN")
                schema_text += f"    - {col}: {col_type}\n"
        else:
            schema_text += f"  Columns: {', '.join(columns)}\n"
        
        if table_info.get("summary"):
            schema_text += f"  Summary: {table_info['summary']}\n"
        
        # Show sample values
        if sample_values:
            schema_text += f"  Sample Data:\n"
            if isinstance(sample_values, list):
                for i, sample in enumerate(sample_values[:2]):
                    schema_text += f"    Row {i+1}: {json.dumps(sample)}\n"
            elif isinstance(sample_values, dict):
                for col, vals in list(sample_values.items())[:5]:
                    schema_text += f"    {col}: {vals[:3] if isinstance(vals, list) else vals}\n"
    
    return schema_text


def planner_node(state: PostgresState) -> PostgresState:
    print("[POSTGRES PLANNER NODE] Generating query plan...")

    data_source_id = state["data_source_id"]
    user_question = state["user_question"]

    schema_graph = load_schema_graph(data_source_id)
    raw_metadata = load_raw_metadata(data_source_id)

    # Build detailed schema with column names and data types
    schema_text = build_intelligent_schema(raw_metadata)

    prompt = f"""
You are a PostgreSQL query planner.

DATABASE SCHEMA:
{schema_text}

RELATIONSHIP GRAPH:
{json.dumps(schema_graph, indent=2)}

User Question:
{user_question}

CRITICAL INSTRUCTIONS (POSTGRESQL-SPECIFIC):

1. Use ONLY table short names (T1, T2, T3, etc.) in SQL.
2. SELECT-only queries (read-only).
3. Use valid PostgreSQL syntax.

🚨 POSTGRESQL WINDOW FUNCTION RULES (MANDATORY):
- Window functions (OVER, LAG, LEAD, ROW_NUMBER, RANK, AVG(...) OVER, etc.)
  MUST NOT appear in:
  - WHERE
  - JOIN conditions
  - HAVING
- Window functions MUST NOT be nested.
- Aliases created by window functions CANNOT be referenced in the same SELECT.
- If window functions are required:
  YOU MUST use a CTE.

✅ REQUIRED PATTERN:
WITH base AS (
  SELECT ..., <window functions>
  FROM ...
)
SELECT *
FROM base
WHERE <conditions>;

If the question requires analytics (moving averages, EMA, comparisons to prior rows),
ALWAYS use the CTE pattern above.

Respond ONLY with valid JSON:

{{
  "execution_mode": "sql" | "model",
  "tables": ["T1", "T2"],
  "sql_query": "SELECT ...",
  "final_output": "table|chart|description",
  "chart_type": "line|bar|pie|scatter|null",
  "needs_clarification": false,
  "clarification_questions": []
}}
"""

    print(f"[POSTGRES PLANNER] Calling LLM with prompt length: {len(prompt)}")
    response_text, _ = rate_limited_llm_call(prompt)
    
    print(f"[POSTGRES PLANNER] LLM Response: {response_text[:500] if response_text else 'EMPTY RESPONSE'}")

    if not response_text or not response_text.strip():
        print("[POSTGRES PLANNER] ERROR: Empty LLM response!")
        raise ValueError("LLM returned empty response")

    response = response_text.strip()
    
    # Strip markdown code blocks with proper handling of language identifier
    if response.startswith("```"):
        # Split by ``` to get [before, content_with_lang, content, after]
        parts = response.split("```")
        if len(parts) >= 3:
            # Get the second part (after first ```) and skip language identifier if present
            content = parts[1].strip()
            # If it starts with 'json\n', skip the 'json\n' part
            if content.startswith("json"):
                content = content[4:].lstrip('\n')
            response = content.strip()
            # Also strip closing ``` if present
            if response.endswith("```"):
                response = response[:-3].strip()

    print(f"[POSTGRES PLANNER] Parsed response: {response[:200]}")
    plan = json.loads(response)
    state["planner_output"] = plan

    log_llm_call(
        function_name="planner_node",
        model_name="gemma-3-27b-it",
        prompt=prompt,
        response_text=response,
        start_time=time.time(),
        end_time=time.time(),
        total_tokens=len(response) // 4,
        metadata={"user_question": user_question[:100]},
    )

    print("[POSTGRES PLANNER] ✓ Plan generated")
    return state


# =========================
# SQL executor (FIXED)
# =========================

WINDOW_ERROR_HINTS = [
    "window functions are not allowed",
    "window function lag requires an over clause",
    "cannot nest window functions",
]

def user_clarification_node(state: PostgresState) -> PostgresState:
    """
    Pauses workflow to request user clarification.
    """
    print("[POSTGRES CLARIFICATION NODE] Requesting user input...")
    
    planner_output = state.get("planner_output", {})
    questions = planner_output.get("clarification_questions", [])
    
    if questions:
        state["pending_question"] = questions[0]
        state["status"] = "need_clarification"
    
    return state


def sql_executor_node(state: PostgresState) -> PostgresState:
    """
    Executes SQL query against PostgreSQL using PostgresConnector.
    Creates connector on-demand from database if not in state.
    Translates short table names (T1, T2, T3, T4) to actual table names.
    Includes self-healing retry loop for robustness.
    """
    print("[POSTGRES SQL EXECUTOR NODE] Executing query with self-healing...")
    
    planner_output = state.get("planner_output", {})
    original_sql = planner_output.get("sql_query")
    
    if not original_sql:
        print("[POSTGRES SQL EXECUTOR] ✗ No SQL query in plan")
        state["sql_result"] = {"error": "No SQL query generated"}
        return state
    
    # Get or create PostgresConnector
    connector = state.get("postgres_connector")
    data_source_id = state.get("data_source_id")
    raw_metadata = None
    
    if not connector:
        print("[POSTGRES SQL EXECUTOR] Creating PostgresConnector...")
        
        # Fetch datasource from database to get connection string
        with db_cursor() as cur:
            cur.execute("SELECT * FROM \"DataSource\" WHERE id = %s", (data_source_id,))
            data_source = cur.fetchone()
        
        if not data_source:
            state["sql_result"] = {"error": f"DataSource {data_source_id} not found"}
            return state
        
        connection_string = data_source["cloudinaryUrl"]
        raw_metadata = data_source.get("rawMetadata", {})
        
        # Parse if stored as string
        if isinstance(raw_metadata, str):
            raw_metadata = json.loads(raw_metadata) if raw_metadata else {}
        
        allowed_tables = raw_metadata.get("allowed_tables", [])
        connector = PostgresConnector(connection_string, allowed_tables)
        state["postgres_connector"] = connector
        print(f"[POSTGRES SQL EXECUTOR] ✓ Created connector for {len(allowed_tables)} tables")
    else:
        # Load metadata for table name mapping
        if not raw_metadata:
            raw_metadata = load_raw_metadata(data_source_id)
    
    # === SELF-HEALING LOOP ===
    max_retries = 5
    error_context = ""
    previous_sqls = []
    
    for attempt in range(max_retries):
        print(f"\n[POSTGRES SQL EXECUTOR] Self-heal attempt {attempt + 1}/{max_retries}")
        
        # Generate SQL (use error context if we're retrying)
        if attempt == 0:
            sql_to_execute = original_sql
        else:
            # Ask LLM to fix the SQL based on previous error
            schema_graph = load_schema_graph(data_source_id)
            fix_prompt = f"""You are a PostgreSQL expert. Fix the following SQL query that failed with an error.

CRITICAL RULES:
- Return ONLY SQL
- No markdown
- SELECT only
- Use CTEs if window functions are required
- Window functions MUST NOT be in WHERE / JOIN / HAVING


Failed SQL:
{previous_sqls[-1]}

Error message:
{error_context}

Database schema (tables available):
{json.dumps(schema_graph, indent=2)[:1000]}

Return ONLY the corrected SQL query with no markdown formatting."""
            
            sql_to_execute, _ = rate_limited_llm_call(fix_prompt)
            
            # === SANITIZE LLM OUTPUT ===
            # Remove markdown code blocks if present
            sql_to_execute = sql_to_execute.strip()
            if sql_to_execute.startswith("```"):
                # Extract SQL from markdown block
                lines = sql_to_execute.split('\n')
                # Remove opening marker (e.g., ```sql or ```)
                if lines[0].strip().startswith("```"):
                    lines = lines[1:]
                # Remove closing marker
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                sql_to_execute = '\n'.join(lines).strip()
            
            print(f"[POSTGRES SQL EXECUTOR] Sanitized SQL: {sql_to_execute[:80]}...")
        
        # === TRANSLATE SHORT TABLE NAMES TO ACTUAL TABLE NAMES ===
        # Build mapping: T1 → public.Conversation, T2 → public.DataSource, etc.
        table_mapping = {}
        for short_name, table_info in raw_metadata.get("tables", {}).items():
            actual_name = quote_identifier(table_info.get("original_name"))
            if actual_name:
                table_mapping[short_name] = actual_name
        
        # Replace short names with actual names in SQL query
        translated_sql = sql_to_execute
        for short, actual in table_mapping.items():
            # Replace "FROM T1" with "FROM public.User", etc.
            import re
            translated_sql = re.sub(rf'\bFROM\s+{short}\b', f'FROM {actual}', translated_sql, flags=re.IGNORECASE)
            translated_sql = re.sub(rf'\bJOIN\s+{short}\b', f'JOIN {actual}', translated_sql, flags=re.IGNORECASE)
            translated_sql = re.sub(rf'\bLEFT\s+JOIN\s+{short}\b', f'LEFT JOIN {actual}', translated_sql, flags=re.IGNORECASE)
            translated_sql = re.sub(rf'\bINNER\s+JOIN\s+{short}\b', f'INNER JOIN {actual}', translated_sql, flags=re.IGNORECASE)
        
        # Check if we've generated this exact SQL before
        if translated_sql in previous_sqls:
            print(f"[POSTGRES SQL EXECUTOR] ⚠️ LLM generated same SQL again, adding stronger hint...")
            error_context += "\n\nIMPORTANT: You generated the EXACT same SQL that failed. Please try a completely DIFFERENT approach!"
            continue
        
        previous_sqls.append(translated_sql)
        
        print(f"[POSTGRES SQL EXECUTOR] Translated SQL: {translated_sql[:100]}...")
        
        # Validate SQL before execution
        is_valid, validation_error, tables_used = connector.validate_sql(translated_sql)
        
        if not is_valid:
            print(f"[POSTGRES SQL EXECUTOR] ⚠️ Validation failed: {validation_error}")
            error_context = validation_error
            continue
        
        print(f"[POSTGRES SQL EXECUTOR] Tables used: {tables_used}")
        
        try:
            # Execute query (with auto-LIMIT for safety)
            rows, columns = connector.execute_query(translated_sql, limit=1000)
            
            result = {
                "rows": rows,
                "columns": columns,
                "row_count": len(rows),
                "sql_query": translated_sql,
                "attempts": attempt + 1
            }
            
            print(f"[POSTGRES SQL EXECUTOR] ✓ Success on attempt {attempt + 1}: {len(rows)} rows returned")
            state["sql_result"] = result
            return state
            
        except Exception as e:
            print(f"[POSTGRES SQL EXECUTOR] ⚠️ Execution error: {str(e)}")
            error_context = str(e)
    
    # All retries exhausted
    print(f"[POSTGRES SQL EXECUTOR] ✗ Failed after {max_retries} attempts")
    state["sql_result"] = {
        "error": f"Query failed after {max_retries} self-healing attempts. Last error: {error_context}",
        "sql_query": original_sql,
        "attempts": max_retries
    }
    
    return state


def chart_generator_node(state: PostgresState) -> PostgresState:
    """
    Generates chart data in Plotly format if requested by planner.
    """
    print("[POSTGRES CHART GENERATOR NODE] Checking if chart needed...")
    
    planner_output = state.get("planner_output", {})
    sql_result = state.get("sql_result", {})
    
    if planner_output.get("final_output") != "chart":
        print("[POSTGRES CHART GENERATOR] No chart requested, skipping...")
        return state
    
    if "error" in sql_result:
        print("[POSTGRES CHART GENERATOR] SQL error, skipping chart...")
        return state
    
    rows = sql_result.get("rows", [])
    columns = sql_result.get("columns", [])
    
    if not rows or not columns:
        print("[POSTGRES CHART GENERATOR] No data for chart")
        return state
    
    chart_type = planner_output.get("chart_type", "scatter")
    
    # Convert rows to lists for Plotly
    x_data = []
    y_data = []
    
    for row in rows[:50]:  # Limit to 50 points for performance
        x_val = row.get(columns[0])
        y_val = row.get(columns[1]) if len(columns) > 1 else 0
        
        # Convert to float for numeric types
        if y_val is not None:
            try:
                from decimal import Decimal
                if isinstance(y_val, Decimal):
                    y_val = float(y_val)
                elif not isinstance(y_val, (int, float)):
                    y_val = float(y_val)
            except:
                pass
        
        x_data.append(str(x_val))
        y_data.append(y_val)
    
    # Build Plotly-format chart data
    chart_data = {
        "data": [
            {
                "x": x_data,
                "y": y_data,
                "name": columns[1] if len(columns) > 1 else "Value",
                "type": "scatter" if chart_type == "line" else chart_type,
                "mode": "lines+markers" if chart_type == "line" else "markers",
                "line": {
                    "color": "#00e599",
                    "width": 2
                } if chart_type == "line" else None,
                "marker": {
                    "color": "#00e599",
                    "size": 6
                }
            }
        ],
        "layout": {
            "title": f"{chart_type.capitalize()} Chart",
            "xaxis": {
                "title": columns[0],
            },
            "yaxis": {
                "title": columns[1] if len(columns) > 1 else "Value",
            },
            "hovermode": "closest"
        }
    }
    
    print(f"[POSTGRES CHART GENERATOR] ✓ Generated {chart_type} chart with {len(rows)} points (Plotly format)")
    state["chart_data"] = chart_data
    
    return state


def output_node(state: PostgresState) -> PostgresState:
    """
    Generates final natural language answer using LLM.
    Handles both SQL mode (with query results) and model mode (descriptive answers).
    """
    print("[POSTGRES OUTPUT NODE] Generating final answer...")
    
    user_question = state.get("user_question")
    planner_output = state.get("planner_output", {})
    execution_mode = planner_output.get("execution_mode", "sql")
    
    # Handle model mode (descriptive answer) - answer already in planner output
    if execution_mode == "model":
        final_answer = planner_output.get("final_output", "")
        state["final_answer"] = final_answer
        state["status"] = "completed"
        print("[POSTGRES OUTPUT] ✓ Model mode answer generated")
        return state
    
    # Handle SQL mode - use query results to generate answer
    sql_result = state.get("sql_result", {})
    
    if not sql_result or "error" in sql_result:
        error_msg = sql_result.get("error", "Unknown error") if sql_result else "No query result"
        state["final_answer"] = f"I encountered an error while querying the database: {error_msg}"
        state["status"] = "error"
        return state
    
    rows = sql_result.get("rows", [])
    columns = sql_result.get("columns", [])
    
    # Build data summary for LLM
    data_summary = f"Query returned {len(rows)} rows with columns: {', '.join(columns)}\n\n"
    if rows:
        data_summary += "Sample results:\n"
        for i, row in enumerate(rows[:5]):
            # Convert all non-JSON-serializable objects to strings
            from datetime import datetime, date, timedelta
            from decimal import Decimal
            
            row_dict = {}
            for key, val in row.items():
                if isinstance(val, datetime):
                    row_dict[key] = val.isoformat()
                elif isinstance(val, date):
                    row_dict[key] = val.isoformat()
                elif isinstance(val, timedelta):
                    row_dict[key] = str(val)
                elif isinstance(val, Decimal):
                    row_dict[key] = float(val)
                elif val is None:
                    row_dict[key] = None
                else:
                    row_dict[key] = val
            data_summary += f"Row {i+1}: {json.dumps(row_dict)}\n"
    
    prompt = f"""You are a data analyst. Answer the user's question based on the query results.

User Question: {user_question}

SQL Query: {sql_result.get('sql_query', 'N/A')}

{data_summary}

Provide a clear, concise answer in natural language. Include specific numbers and insights."""

    response_text, _ = rate_limited_llm_call(prompt)
    
    state["final_answer"] = response_text
    state["status"] = "completed"
    
    # Generate insights
    try:
        insights = generate_insight1(user_question, str(rows[:10]))
        state["insights"] = insights
    except Exception as e:
        print(f"[POSTGRES OUTPUT] ⚠️ Insight generation failed: {e}")
        state["insights"] = None
    
    print("[POSTGRES OUTPUT] ✓ Answer generated")
    
    return state


def planner_router(state: PostgresState) -> str:
    """
    Routes to appropriate node based on planner output.
    NOTE: schema_info_node is removed - planner loads schema from local JSON files directly.
    """
    planner_output = state.get("planner_output", {})
    execution_mode = planner_output.get("execution_mode", "sql")
    
    # Check for clarification need
    if planner_output.get("needs_clarification"):
        print("[POSTGRES ROUTER] Routing to user_clarification")
        return "user_clarification"
    
    # Check for error
    if execution_mode == "error":
        print("[POSTGRES ROUTER] Error in planner, routing to output")
        return "output"
    
    # Execute SQL
    if execution_mode == "sql":
        print("[POSTGRES ROUTER] Routing to sql_executor")
        return "sql_executor"
    
    # Model mode (descriptive answers) - go directly to output
    if execution_mode == "model":
        print("[POSTGRES ROUTER] Model mode, routing to output")
        return "output"
    
    # Default to output
    print("[POSTGRES ROUTER] Routing to output")
    return "output"


def build_postgres_graph():
    """
    Builds the PostgreSQL-specific LangGraph workflow.
    NOTE: No schema_info_node - planner loads from local JSON files (same as file workflow).
    """
    workflow = StateGraph(PostgresState)

    # Add nodes (NO schema_info_node - planner loads schema directly)
    workflow.add_node("input", input_node)
    workflow.add_node("planner", planner_node)
    workflow.add_node("user_clarification", user_clarification_node)
    workflow.add_node("sql_executor", sql_executor_node)
    workflow.add_node("chart_generator", chart_generator_node)
    workflow.add_node("output", output_node)

    # Set entry point
    workflow.set_entry_point("input")

    # Define edges
    workflow.add_edge("input", "planner")

    workflow.add_conditional_edges(
        source="planner",
        path=planner_router,
        path_map={
            "user_clarification": "user_clarification",
            "sql_executor": "sql_executor",
            "output": "output",
        }
    )

    workflow.add_edge("user_clarification", END)
    # NOTE: Removed schema_info → planner edge (schema loaded directly by planner)
    workflow.add_edge("sql_executor", "chart_generator")
    workflow.add_edge("chart_generator", "output")
    workflow.add_edge("output", END)

    return workflow.compile()
