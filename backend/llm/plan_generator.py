# plan_generator.py (graph_workflow.py)
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
from dotenv import load_dotenv
load_dotenv()

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

    # ✅ ADD: Merge preprocessing operations
    old_prep = old.get("preprocessing_operations", [])
    new_prep = new.get("preprocessing_operations", [])
    # Deduplicate based on type+table+column
    existing_keys = {(op.get("type"), op.get("table"), op.get("column")) for op in old_prep}
    merged["preprocessing_operations"] = old_prep + [
        op for op in new_prep 
        if (op.get("type"), op.get("table"), op.get("column")) not in existing_keys
    ]

    return merged


class State(dict):
    """
    Shared state passed around between LangGraph nodes.
    """
    user_question: str
    data_source_id: str  # ✅ Add data_source_id for per-datasource isolation
    schema_info: Dict[str, Any] | None
    planner_output: Dict[str, Any] | None
    sql_result: Any | None
    clarification_answer: str | None
    metadata_requests: List[str] | None
    insights: str |None
    final_answer: str| None
    status: str |None
    pending_question: str |None
    appended_data: str | None 
    preprocessing_operations: List[Dict] | None
    preprocessing_applied: bool | None  # ✅ NEW: Track if preprocessing done
    duckdb_connection: Any | None
    chart_data: Dict[str, Any] | None  # ✅ NEW: Chart JSON for visualization 

def preprocessing_node(state: State) -> State:
    """
    Preprocessing node: Loads data and applies preprocessing operations.
    Does NOT execute SQL - only prepares data.
    """
    print("[PREPROCESSING NODE] Applying data transformations...")
    
    plan = state.get("planner_output", {})
    preprocessing_ops = plan.get("preprocessing_operations", [])
    tables = plan.get("tables", [])
    
    if not preprocessing_ops:
        print("[PREPROCESSING NODE] No operations to apply")
        state["preprocessing_applied"] = True
        return state
    
    if not tables:
        print("[PREPROCESSING NODE] No tables specified")
        state["preprocessing_applied"] = True
        return state
    
    print(f"[PREPROCESSING NODE] Loading {len(tables)} table(s) for preprocessing...")
    
    data_source_id = state.get("data_source_id")
    if not data_source_id:
        raise ValueError("data_source_id not found in state")
    
    try:
        # Load tables into DuckDB
        from .interpretor import load_tables, apply_preprocessing
        
        con = load_tables(tables, data_source_id)
        print(f"[PREPROCESSING NODE] Tables loaded: {tables}")
        
        # Apply preprocessing operations
        print(f"[PREPROCESSING NODE] Applying {len(preprocessing_ops)} operations...")
        apply_preprocessing(con, preprocessing_ops)
        
        # ✅ IMPORTANT: Store the connection in state for SQL executor to use
        state["duckdb_connection"] = con
        state["preprocessing_applied"] = True
        
        print(f"[PREPROCESSING NODE] ✓ Preprocessing complete")
        
    except Exception as e:
        print(f"[PREPROCESSING NODE] ✗ Error: {e}")
        state["preprocessing_applied"] = False
        # Don't fail completely - let SQL executor try anyway
    
    return state

def sql_executor_node(state: State) -> State:
    """Executes SQL query via interpreter."""
    print("[SQL EXECUTOR NODE] Executing SQL query...")
    plan = state.get("planner_output", {})
    print(f"[DEBUG] SQL executor plan: {plan}")
    
    data_source_id = state.get("data_source_id")
    if not data_source_id:
        raise ValueError("data_source_id not found in state")
    
    from .interpretor import interpret_and_execute
    
    # ✅ Pass preprocessed connection if available
    preprocessed_con = state.get("duckdb_connection")
    
    if preprocessed_con:
        print("[SQL EXECUTOR NODE] Using preprocessed DuckDB connection")
        result = interpret_and_execute(plan, data_source_id, existing_connection=preprocessed_con)
    else:
        print("[SQL EXECUTOR NODE] Loading fresh data (no preprocessing)")
        result = interpret_and_execute(plan, data_source_id)
    
    state["sql_result"] = result
    print(f"[DEBUG] SQL result: {result[:100] if result else 'None'}...")
    
    # ✅ Clean up connection after execution
    if preprocessed_con:
        try:
            preprocessed_con.close()
            print("[SQL EXECUTOR NODE] Closed DuckDB connection")
        except:
            pass
    
    return state

def chart_generator_node(state: State) -> State:
    """
    Chart Generator Node: Creates visualization if requested.
    Converts SQL result to Plotly chart JSON.
    """
    print("[CHART GENERATOR NODE] Checking if chart generation needed...")
    
    plan = state.get("planner_output", {})
    needs_chart = plan.get("needs_chart", False)
    
    if not needs_chart:
        print("[CHART GENERATOR NODE] No chart requested, skipping")
        state["chart_data"] = None
        return state
    
    sql_result = state.get("sql_result", "")
    
    if not sql_result or sql_result == "No tables specified in plan.":
        print("[CHART GENERATOR NODE] No SQL result to visualize")
        state["chart_data"] = None
        return state
    
    try:
        from .chart_generator import generate_chart
        
        user_question = state.get("user_question", "")
        chart_json = generate_chart(sql_result, plan, user_question)
        
        if chart_json:
            state["chart_data"] = chart_json
            print(f"[CHART GENERATOR NODE] ✓ Chart generated successfully")
        else:
            state["chart_data"] = None
            print(f"[CHART GENERATOR NODE] Chart generation returned None")
    
    except Exception as e:
        print(f"[CHART GENERATOR NODE] ✗ Error generating chart: {e}")
        state["chart_data"] = None
    
    return state

def load_schema_graph(data_source_id: str) -> dict:
    """Load schema graph from datasource-specific folder."""
    graph_path = os.path.join("uploaded_files", f"datasource_{data_source_id}", "schema_graph.json")
    if not os.path.exists(graph_path):
        raise FileNotFoundError(f"Schema graph not found at {graph_path}. Please run schema build first.")
    with open(graph_path, "r") as f:
        return json.load(f)

def load_raw_metadata(data_source_id: str) -> dict:
    """Load raw metadata from datasource-specific folder."""
    metadata_path = os.path.join("uploaded_files", f"datasource_{data_source_id}", "raw_metadata.json")
    if not os.path.exists(metadata_path):
        raise FileNotFoundError(f"Metadata not found at {metadata_path}. Please run schema build first.")
    with open(metadata_path, "r") as f:
        return json.load(f)

def retrieve_metadata(requests: List[str], data_source_id: str) -> str:
    """
    Parse metadata requests and retrieve from datasource-specific raw_metadata.json.
    """
    try:
        metadata = load_raw_metadata(data_source_id)
    except Exception as e:
        print(f"[METADATA] Error loading metadata: {e}")
        return "Metadata unavailable."
    
    response = ""
    for req in requests:
        try:
            if "columns for" in req:
                table = req.split("columns for ")[-1].strip()
                if table in metadata.get("tables", {}):
                    cols = metadata["tables"][table].get("columns", [])
                    response += f"Columns for {table}: {', '.join(cols)}\n"
                else:
                    response += f"Table {table} not found.\n"
                    
            elif "dtypes for" in req:
                table = req.split("dtypes for ")[-1].strip()
                if table in metadata.get("tables", {}):
                    # ✅ FIX: Use "canonical_types" instead of "dtypes"
                    table_info = metadata["tables"][table]
                    dtypes = table_info.get("canonical_types", {})  # ← Changed from "dtypes"
                    
                    if dtypes:
                        response += f"Data types for {table}:\n"
                        for col, dtype in dtypes.items():
                            response += f"  - {col}: {dtype}\n"
                    else:
                        response += f"Data types for {table}: Not available\n"
                else:
                    response += f"Table {table} not found.\n"
                    
        except Exception as e:
            print(f"[METADATA] Error processing request '{req}': {e}")
            response += f"Error retrieving metadata for: {req}\n"
    
    return response if response else "No metadata found for the requested tables."


def input_node(state: State) -> State:
    """The initial node – receives the user question."""
    print("[INPUT NODE] Received user question.")
    print(f"[DEBUG] Initial state: {dict(state)}")
    return state

def analyze_column_patterns(sample_values):
    """Analyze sample values to detect data patterns automatically."""
    if not sample_values:
        return {}
    
    patterns = {}
    for col, vals in sample_values.items():
        if not vals:
            continue
            
        # Filter out None/NaN values
        valid_vals = [str(v) for v in vals if v is not None and str(v) != 'nan']
        if not valid_vals:
            continue
        
        col_patterns = []
        
        # Check for delimiters
        delimiters = [',', '|', ';', '/', '-']
        for delim in delimiters:
            if any(delim in v for v in valid_vals):
                col_patterns.append(f"Contains '{delim}' delimiter - values may have multiple items")
        
        # Check for list/array structures
        if any(v.startswith('[') and v.endswith(']') for v in valid_vals):
            col_patterns.append("Array/list format detected")
        
        # Check for JSON
        if any((v.startswith('{') and v.endswith('}')) for v in valid_vals):
            col_patterns.append("JSON object format detected")
        
        # Check for numeric ranges (e.g., "100-200")
        if any('-' in v and v.replace('-','').replace('.','').isdigit() for v in valid_vals):
            col_patterns.append("May contain numeric ranges")
        
        # Check cardinality vs sample size
        unique_count = len(set(valid_vals))
        if unique_count == 1:
            col_patterns.append(f"Low cardinality - only 1 unique value in sample")
        elif unique_count < len(valid_vals) * 0.5:
            col_patterns.append(f"Low cardinality - {unique_count} unique values in {len(valid_vals)} samples")
        
        if col_patterns:
            patterns[col] = {
                "samples": valid_vals[:5],
                "patterns": col_patterns
            }
    
    return patterns


def build_intelligent_schema(raw_metadata):
    """Build schema with intelligent pattern analysis."""
    schema_text = "AVAILABLE TABLES & COLUMNS:\n"
    
    for table_short, table_info in raw_metadata.get("tables", {}).items():
        original_name = table_info.get("original_name", "Unknown")
        columns = table_info.get("columns", [])
        canonical_types = table_info.get("canonical_types", {})
        sample_values = table_info.get("sample_values", {})
        
        schema_text += f"\n{table_short} ({original_name}):\n"
        schema_text += f"  Columns: {', '.join(columns)}\n"
        
        if canonical_types:
            types_str = ', '.join([f'{k}:{v}' for k, v in list(canonical_types.items())[:15]])
            schema_text += f"  Types: {types_str}\n"
        
        # Analyze patterns
        patterns = analyze_column_patterns(sample_values)
        
        if patterns:
            schema_text += f"  Column Samples & Patterns:\n"
            for col, info in patterns.items():
                schema_text += f"    {col}:\n"
                schema_text += f"      Examples: {info['samples']}\n"
                for pattern in info['patterns']:
                    schema_text += f"      Note: {pattern}\n"
    
    return schema_text


def planner_node(state: State) -> State:
    """LLM Planner Node with intelligent pattern detection."""
    print("[PLANNER NODE] Running LLM planner...")
    print(f"[DEBUG] State before planner: user_question={state.get('user_question')}, appended_data={state.get('appended_data', '')[:100]}...")
    
    data_source_id = state.get("data_source_id")
    if not data_source_id:
        raise ValueError("data_source_id not found in state")
    
    schema_graph = load_schema_graph(data_source_id)
    raw_metadata = load_raw_metadata(data_source_id)
    
    schema_text = json.dumps(schema_graph, indent=2)
    
    # Build intelligent schema description
    full_schema_text = "SCHEMA GRAPH:\n" + schema_text + "\n\n"
    full_schema_text += build_intelligent_schema(raw_metadata)
    
    user_question = state["user_question"]
    previous_metadata = state.get("metadata_requests", [])
    
    max_iterations = 3
    iteration = 0
    appended_data = state.get("appended_data", "")
    
    combined_plan = state.get("planner_output")
    print(f"[DEBUG] Starting planner loop: combined_plan={combined_plan}, appended_data length={len(appended_data)}")
    
    while iteration < max_iterations:
        print(f"[DEBUG] Iteration {iteration}: appended_data preview={appended_data[:100]}...")
        prompt = f"""
You are an intelligent query planner. Analyze the schema carefully, paying special attention to the sample values and patterns noted for each column.

{full_schema_text}

Question: {user_question}
{appended_data}

IMPORTANT PRINCIPLES:
1. EXAMINE THE SAMPLE VALUES: Look at the actual data examples provided. They tell you how the data is structured.
2. INFER THE RIGHT APPROACH: If samples show multiple values in one cell (delimited, arrays, etc.), you need partial matching or special handling.
3. THINK LIKE AN ANALYST: What would a data analyst do with this specific data format?
4. BE ADAPTIVE: Different columns may need different approaches based on their actual content.

OUTPUT: Valid JSON only. Structure:
{{
  "tables": ["T1"],
  "filters": [
    {{
      "column": "column_name",
      "operator": "contains|==|>|<|>=|<=|in|between",
      "value": "search_value",
      "reason": "Why this approach is correct given the sample data"
    }}
  ],
  "joins": [{{"left": "", "right": "", "reason": ""}}],
  "operations": ["COUNT(*)", "SUM(col)", "AVG(col)", etc.],
  "group_by": ["col1"],
  "final_output": "Clear description of what the answer represents",
  "execution_mode": "sql|model",
  "needs_clarification": false,
  "clarification_questions": [],
  "metadata_requests": [],
  "needs_chart": false,
  "chart_type": "bar|line|pie|scatter|auto|null",
  "preprocessing_operations": [
    {{
      "type": "encode|normalize|split|extract",
      "table": "T1",
      "column": "col_name",
      "method": "specific_method",
      "reason": "Why this preprocessing is needed"
    }}
  ]
}}

EXECUTION MODE:
- "sql": For queries requiring data retrieval, filtering, aggregation, joins, comparisons
- "model": ONLY for questions about schema structure itself (what tables exist, what columns, data types)

FILTER OPERATORS - Choose based on actual data structure:
- "==": Exact match (use when samples show single discrete values)
- "contains": Partial text match (use when samples show delimited lists, concatenated values, or when searching within text)
- ">", "<", ">=", "<=": Numeric/date comparisons
- "in": Value is one of several options
- "between": Numeric range

CRITICAL: Always explain your reasoning based on the observed sample values. If samples show "Action, Comedy", explain why you chose "contains" over "==".

CHART GENERATION:
- Set "needs_chart": true if user explicitly asks for visualization, chart, graph, or plot
- Set "chart_type" to: "bar" (categorical comparison), "line" (time series), "pie" (part-to-whole), "scatter" (correlation), or "auto" (let system decide)
- If no visualization requested, set "needs_chart": false and "chart_type": null

CRITICAL CHART DATA RULES:
1. SCATTER PLOTS (correlation/relationship between two variables):
   - For "plot X vs Y" or "relationship between X and Y" → operations: [], group_by: [] (raw data)
   - For "discount vs profit" or "between X and Y" → Select raw columns WITHOUT aggregation
   - Each row becomes a point on the scatter plot showing correlation
   
2. BAR/PIE/LINE CHARTS (aggregated comparisons):
   - For "average sales by region" → operations: ["AVG(sales)"], group_by: ["region"]
   - For "top 10 products" → operations: ["SUM(revenue)"], group_by: ["product"], mention ORDER BY + LIMIT 10
   - For "monthly trends" → operations: ["SUM(sales)"], group_by: ["month"]
   - Always use GROUP BY with aggregations (COUNT, SUM, AVG, etc.)

3. KEYWORD DETECTION:
   - "between", "vs", "relationship", "correlation" → Scatter plot with RAW data (operations: [], group_by: [])
   - "by category", "per region", "breakdown", "distribution" → Bar/Pie with GROUP BY
   - "over time", "trend", "monthly" → Line chart with GROUP BY date

Rules:
- Output ONLY valid JSON (no markdown, no explanations outside JSON)
- Use EXACT column names from schema
- If question is unclear or missing information: set needs_clarification=true
- In final_output, describe the actual answer (not table names or placeholders)
- Include reasoning for your filter/operator choices
"""
        
        try:
            start_time = time.time()
            raw, response = rate_limited_llm_call(prompt)
            end_time = time.time()
            
            input_tokens = None
            output_tokens = None
            total_tokens = None
            
            if hasattr(response, 'usage_metadata'):
                usage = response.usage_metadata
                input_tokens = getattr(usage, 'prompt_token_count', None)
                output_tokens = getattr(usage, 'candidates_token_count', None)
                total_tokens = getattr(usage, 'total_token_count', None)
            
            log_llm_call(
                function_name="planner_node",
                model_name="gemma-3-27b-it",
                prompt=prompt,
                response_text=raw,
                start_time=start_time,
                end_time=end_time,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                metadata={
                    "iteration": iteration,
                    "user_question": user_question[:100],
                    "has_appended_data": bool(appended_data)
                }
            )
            
            if raw.startswith("```json"):
                raw = raw[7:].strip()
            if raw.endswith("```"):
                raw = raw[:-3].strip()
            
            current_plan = json.loads(raw)
            print(f"[DEBUG] Current plan from LLM: {current_plan}")
            
            combined_plan = merge_plans(combined_plan, current_plan)
            print(f"[DEBUG] Merged plan: {combined_plan}")
            
            # Log preprocessing operations
            preprocessing_ops = current_plan.get("preprocessing_operations", [])
            if preprocessing_ops:
                print(f"[PLANNER NODE] Detected {len(preprocessing_ops)} preprocessing operations:")
                for op in preprocessing_ops:
                    print(f"  - {op.get('type')} on {op.get('table')}.{op.get('column', op.get('columns', 'N/A'))}: {op.get('reason')}")
            
            # Log filter operations with reasoning
            filters = current_plan.get("filters", [])
            if filters:
                print(f"[PLANNER NODE] Detected {len(filters)} filter operations:")
                for f in filters:
                    print(f"  - {f.get('column')} {f.get('operator')} '{f.get('value')}' - Reason: {f.get('reason', 'N/A')}")
            
            requests = current_plan.get("metadata_requests", [])
            if requests:
                print(f"[DEBUG] Metadata requests found: {requests}")
                appended_data += "\nRetrieved Metadata:\n" + retrieve_metadata(requests, data_source_id)
                current_plan["metadata_requests"] = []
                combined_plan["metadata_requests"] = []
                iteration += 1
                continue
            else:
                print("[DEBUG] No metadata requests, finalizing plan")
                state["planner_output"] = combined_plan
                state["metadata_requests"] = previous_metadata
                state["preprocessing_operations"] = combined_plan.get("preprocessing_operations", [])
                
                print(f"[DEBUG] Final state from planner: planner_output={combined_plan}")
                return state
                
        except Exception as e:
            print(f"[DEBUG] Planner error: {e}")
            if combined_plan:
                state["planner_output"] = combined_plan
            else:
                state["planner_output"] = {
                    "tables": [],
                    "filters": [],
                    "joins": [],
                    "operations": [],
                    "group_by": [],
                    "final_output": "table",
                    "execution_mode": "sql",
                    "needs_clarification": False,
                    "clarification_questions": [],
                    "metadata_requests": [],
                    "preprocessing_operations": []
                }
            print(f"[DEBUG] Error fallback plan: {state['planner_output']}")
            return state
    
    print("[DEBUG] Max iterations reached")
    state["planner_output"] = combined_plan if combined_plan else {}
    state["preprocessing_operations"] = combined_plan.get("preprocessing_operations", []) if combined_plan else []
    print(f"[DEBUG] Max iter state: planner_output={state['planner_output']}")
    return state

def user_clarification_node(state: State) -> State:
    plan = state.get("planner_output", {})
    questions = plan.get("clarification_questions", [])
    print(f"[DEBUG] User clarification node: questions={questions}")
    state["status"] = "need_clarification"
    state["pending_question"] = questions[0] if questions else None
    print(f"[DEBUG] Pending question: {state['pending_question']}")
    return state


def schema_info_node(state: State) -> State:
    """Provides schema details (if needed)."""
    print("[SCHEMA INFO NODE] Fetching schema details...")
    print(f"[DEBUG] Schema info state before: schema_info={state.get('schema_info')}")
    
    data_source_id = state.get("data_source_id")
    if not data_source_id:
        raise ValueError("data_source_id not found in state")
    
    schema_graph = load_schema_graph(data_source_id)
    state["schema_info"] = schema_graph
    print(f"[DEBUG] Schema info loaded: {len(schema_graph)} keys")
    return state

def sql_executor_node(state: State) -> State:
    """Executes SQL query via interpreter."""
    print("[SQL EXECUTOR NODE] Executing SQL query...")
    plan = state.get("planner_output", {})
    print(f"[DEBUG] SQL executor plan: {plan}")
    
    data_source_id = state.get("data_source_id")
    if not data_source_id:
        raise ValueError("data_source_id not found in state")
    
    from .interpretor import interpret_and_execute
    
    # ✅ Pass preprocessed connection if available
    preprocessed_con = state.get("duckdb_connection")
    
    if preprocessed_con:
        print("[SQL EXECUTOR NODE] Using preprocessed DuckDB connection")
        result = interpret_and_execute(plan, data_source_id, existing_connection=preprocessed_con)
    else:
        print("[SQL EXECUTOR NODE] Loading fresh data (no preprocessing)")
        result = interpret_and_execute(plan, data_source_id)
    
    state["sql_result"] = result
    print(f"[DEBUG] SQL result: {result[:100] if result else 'None'}...")
    
    # ✅ Clean up connection after execution
    if preprocessed_con:
        try:
            preprocessed_con.close()
            print("[SQL EXECUTOR NODE] Closed DuckDB connection")
        except:
            pass
    
    return state

def output_node(state: State) -> State:
    """Final node – prints or returns the answer."""
    print("[OUTPUT NODE] Returning final answer to user.")
    plan = state.get("planner_output", {})
    print(f"[DEBUG] Output node plan: {plan}")
    
    insights = ""
    final_answer = ""
    
    if plan.get("execution_mode") == "model":
        raw_output = plan.get("final_output", "")
        operations = plan.get("operations", [])
        
        placeholder_values = ["model_generated_description", "table", "", None]
        
        if raw_output in placeholder_values or (isinstance(raw_output, str) and raw_output.startswith("model_")):
            if operations and isinstance(operations, list) and len(operations) > 0:
                first_op = operations[0] if operations else ""
                sql_keywords = ("SELECT", "COUNT", "SUM", "AVG", "MAX", "MIN", "GROUP BY", "WHERE")
                if isinstance(first_op, str) and not first_op.upper().startswith(sql_keywords):
                    final_answer = "\n".join(operations)
                else:
                    final_answer = raw_output or "No answer available."
            else:
                final_answer = raw_output or "No answer available."
        else:
            final_answer = raw_output
        
        insights = ""
        print(f"[DEBUG] Model mode: final_answer={final_answer[:100] if final_answer else 'None'}...")
    elif plan.get("execution_mode") == "sql":
        sql_result = state.get("sql_result", "No SQL result.")
        print(f"[DEBUG] SQL mode: sql_result preview={sql_result[:100]}...")
        try:
            insights = generate_insight1(state["user_question"], sql_result)
            print(f"[DEBUG] Generated insights: {insights[:100]}...")
            final_answer = f"{sql_result}\n\nInsights:\n{insights}"
        except Exception as e:
            print(f"[ERROR] Insight generation failed: {e}")
            insights = f"Error generating insights: {e}"
            final_answer = sql_result
    else:
        final_answer = state.get("sql_result", "No SQL result.")
        insights = ""
        print(f"[DEBUG] Default mode: final_answer={final_answer}")
    
    state["insights"] = insights
    state["final_answer"] = final_answer
    
    # ✅ Add chart data to response if available
    chart_data = state.get("chart_data")
    if chart_data:
        print(f"[DEBUG] Chart data included in response")
    
    print(f"[DEBUG] insights stored: {insights[:100] if insights else 'None'}...")
    print(f"[DEBUG] final_answer stored: {final_answer[:100] if final_answer else 'None'}...")
    
    return state

def planner_router(state: State) -> str:
    """
    Routes based on planner_output flags.
    Priority: clarification → metadata → preprocessing → execution
    """
    plan = state.get("planner_output", {})
    exec_mode = plan.get("execution_mode")
    print(f"[DEBUG] Router: plan={plan}")
    print(f"[DEBUG] execution_mode: {exec_mode}")

    # Priority 1: Clarification needed
    if plan.get("needs_clarification"):
        state["status"] = "need_clarification"
        print("[DEBUG] Routing to user_clarification")
        return "user_clarification"

    # Priority 2: Metadata requests (schema info needed)
    if plan.get("metadata_requests"):
        print("[DEBUG] Routing to schema_info for metadata requests")
        return "schema_info"

    # Priority 3: Preprocessing needed (only for SQL mode)
    if exec_mode == "sql":
        preprocessing_ops = plan.get("preprocessing_operations", [])
        
        # ✅ Check if preprocessing is needed AND not yet applied
        if preprocessing_ops and not state.get("preprocessing_applied", False):
            print(f"[DEBUG] Routing to preprocessing ({len(preprocessing_ops)} operations)")
            return "preprocessing"
        
        # Preprocessing done or not needed, go to SQL executor
        print("[DEBUG] Routing to sql_executor")
        return "sql_executor"

    # Priority 4: Model mode (no SQL, no preprocessing)
    print("[DEBUG] Routing to output")
    return "output"


def build_graph():
    workflow = StateGraph(State)

    workflow.add_node("input", input_node)
    workflow.add_node("planner", planner_node)
    workflow.add_node("user_clarification", user_clarification_node)
    workflow.add_node("schema_info", schema_info_node)
    workflow.add_node("preprocessing", preprocessing_node)  # ✅ NEW
    workflow.add_node("sql_executor", sql_executor_node)
    workflow.add_node("chart_generator", chart_generator_node)  # ✅ NEW: Chart generation
    workflow.add_node("output", output_node)

    workflow.set_entry_point("input")

    workflow.add_edge("input", "planner")

    workflow.add_conditional_edges(
        source="planner",
        path=planner_router,
        path_map={
            "user_clarification": "user_clarification",
            "schema_info": "schema_info",
            "preprocessing": "preprocessing",  # ✅ NEW
            "sql_executor": "sql_executor",
            "output": "output",
        }
    )

    workflow.add_edge("user_clarification", END)
    workflow.add_edge("schema_info", "planner")
    workflow.add_edge("preprocessing", "sql_executor")  # ✅ NEW: Preprocessing → SQL Executor
    workflow.add_edge("sql_executor", "chart_generator")  # ✅ MODIFIED: SQL → Chart
    workflow.add_edge("chart_generator", "output")  # ✅ NEW: Chart → Output
    workflow.add_edge("output", END)

    return workflow.compile()


def main():
    graph = build_graph()

    print("\n--- Query System Started ---\n")
    
    while True:
        user_question = input("Enter your query (or 'exit'): ").strip()
        if user_question.lower() == "exit":
            break

        state = State({
            "user_question": user_question,
            "schema_info": None,
            "planner_output": None,
            "sql_result": None,
            "clarification_answer": None,
            "metadata_requests": [],
            "insights": None,
            "final_answer": None,
            "appended_data": "",
        })
        print(f"[DEBUG] Main: Initial state for query '{user_question}': {dict(state)}")

        final_state = graph.invoke(state)
        print(f"[DEBUG] Main: Final state: {dict(final_state)}")
        planner_output = final_state.get("planner_output", {})
        exec_mode = planner_output.get("execution_mode", "")
        
        print("\n--- FINAL ANSWER ---\n")
        
        if final_state.get("insights"):
            print(final_state["insights"])
        elif final_state.get("final_answer"):
            final_answer = final_state["final_answer"]
            if exec_mode == "sql" and "Insights:" in final_answer:
                parts = final_answer.split("Insights:", 1)
                print(parts[1].strip())
            else:
                print(final_answer)
        elif planner_output:
            if isinstance(planner_output, dict):
                print(planner_output.get("final_output", "No answer generated."))
            else:
                print(planner_output)
        else:
            print("No answer generated.")

if __name__ == "__main__":
    main()