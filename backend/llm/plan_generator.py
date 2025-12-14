# plan_generator.py (graph_workflow.py)
from typing import Dict, Any, List
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
import uuid
import json
import os
import google.generativeai as genai
from insight_generator import generate_insight1
from .llm_tracker import log_llm_call
import time
from dotenv import load_dotenv
load_dotenv()

# Configure Gemini API
api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    raise ValueError("GOOGLE_API_KEY environment variable is not set. Please set it to your Google Gemini API key.")
genai.configure(api_key=api_key)

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


class State(dict):
    """
    Shared state passed around between LangGraph nodes.
    """
    user_question: str
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


def load_schema_graph(graph_path: str = "schema_graph.json") -> dict:
    """Load the schema graph from Parquet-based workflow."""
    if not os.path.exists(graph_path):
        raise FileNotFoundError(f"Schema graph not found at {graph_path}. Please run schema build first.")
    with open(graph_path, "r") as f:
        return json.load(f)

def load_raw_metadata(metadata_path: str = "raw_metadata.json") -> dict:
    """Load raw metadata from Parquet files."""
    if not os.path.exists(metadata_path):
        raise FileNotFoundError(f"Metadata not found at {metadata_path}. Please run schema build first.")
    with open(metadata_path, "r") as f:
        return json.load(f)

def retrieve_metadata(requests: List[str]) -> str:
    """
    Parse metadata requests (e.g., ["columns for T1"]) and retrieve from raw_metadata.json.
    Return formatted string for prompt.
    """
    metadata = load_raw_metadata()
    response = ""
    for req in requests:
        if "columns for" in req:
            table = req.split("columns for ")[-1].strip()
            if table in metadata["tables"]:
                cols = metadata["tables"][table]["columns"]
                response += f"Columns for {table}: {', '.join(cols)}\n"
        elif "dtypes for" in req:
            table = req.split("dtypes for ")[-1].strip()
            if table in metadata["tables"]:
                dtypes = metadata["tables"][table]["dtypes"]
                response += f"Data types for {table}: {', '.join([f'{k}: {v}' for k, v in dtypes.items()])}\n"
    return response


def input_node(state: State) -> State:
    """The initial node – receives the user question."""
    print("[INPUT NODE] Received user question.")
    print(f"[DEBUG] Initial state: {dict(state)}")
    return state

def planner_node(state: State) -> State:
    """LLM Planner Node with iterative metadata retrieval."""
    print("[PLANNER NODE] Running LLM planner...")
    print(f"[DEBUG] State before planner: user_question={state.get('user_question')}, appended_data={state.get('appended_data', '')[:100]}...")
    
    schema_graph = load_schema_graph()
    raw_metadata = load_raw_metadata()  # ✅ Load raw metadata
    
    schema_text = json.dumps(schema_graph, indent=2)
    
    # ✅ Build comprehensive schema with all columns
    full_schema_text = "SCHEMA GRAPH:\n" + schema_text + "\n\n"
    full_schema_text += "AVAILABLE TABLES & COLUMNS:\n"
    for table_short, table_info in raw_metadata.get("tables", {}).items():
        original_name = table_info.get("original_name", "Unknown")
        columns = table_info.get("columns", [])
        full_schema_text += f"\n{table_short} ({original_name}):\n"
        full_schema_text += f"  Columns: {', '.join(columns)}\n"
        dtypes = table_info.get("dtypes", {})
        if dtypes:
            full_schema_text += f"  Types: {', '.join([f'{k}:{v}' for k, v in dtypes.items()][:10])}\n"
    
    user_question = state["user_question"]
    previous_metadata = state.get("metadata_requests", [])
    
    # Iterative prompting: Start with minimal, append retrieved data
    max_iterations = 3
    iteration = 0
    appended_data = state.get("appended_data", "")
    
    combined_plan = state.get("planner_output")
    print(f"[DEBUG] Starting planner loop: combined_plan={combined_plan}, appended_data length={len(appended_data)}")
    
    while iteration < max_iterations:
        print(f"[DEBUG] Iteration {iteration}: appended_data preview={appended_data[:100]}...")
        prompt = f"""
You are a query planner. Using the schema graph, available columns, and user question, generate a JSON plan.

{full_schema_text}

Question: {user_question}
{appended_data}

OUTPUT: Valid JSON only. Example:
{{
  "tables": ["T1"],
  "filters": [],
  "joins": [{{"left": "", "right": "", "reason": ""}}],
  "operations": ["COUNT(*)"],
  "group_by": [],
  "final_output": "description of answer or result",
  "execution_mode": "sql",
  "needs_clarification": false,
  "clarification_questions": [],
  "metadata_requests": []
}}

Rules:
- "sql" mode for ANY retrieval/filters/joins/aggs/grouping/comparisons/trends/best/worst/data-value usage.
- "model" mode ONLY when answerable from schema/structure info (tables, columns, dtypes).
- For BOTH modes: If you need additional info (specific columns/dtypes for tables), add to "metadata_requests".
  * Example: ["columns for T1", "dtypes for T2"]
  * On next iteration, you'll receive this data and can use it in final_output
- For "model" mode schema questions:
  * FIRST iteration: Request needed metadata
  * SUBSEQUENT iterations: Use retrieved metadata to populate final_output with detailed answer
- Never request full schema (already provided above).
- Output ONLY valid JSON.
- For "sql" mode, operations must describe steps convertible to pandas.
- For complex analysis/comparisons/trends: ALWAYS use "sql".
- Use EXACT column names from the schema above.
- In final_output, provide the actual answer (not placeholders like "T1" or "table").
"""
        
        try:
            model = genai.GenerativeModel(
                "gemma-3-27b-it",
                generation_config=genai.GenerationConfig(
                    temperature=0,
                    top_p=1,
                    top_k=1,
                )
            )
            
            time.sleep(30)  # Rate limiting: 20 second delay between API calls
            start_time = time.time()
            response = model.generate_content(prompt)
            end_time = time.time()
            
            raw = response.text.strip()
            
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
            
            requests = current_plan.get("metadata_requests", [])
            if requests:
                print(f"[DEBUG] Metadata requests found: {requests}")
                appended_data += "\nRetrieved Metadata:\n" + retrieve_metadata(requests)
                current_plan["metadata_requests"] = []
                combined_plan["metadata_requests"] = []
                iteration += 1
                continue
            else:
                print("[DEBUG] No metadata requests, finalizing plan")
                state["planner_output"] = combined_plan
                state["metadata_requests"] = previous_metadata
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
                    "metadata_requests": []
                }
            print(f"[DEBUG] Error fallback plan: {state['planner_output']}")
            return state
    
    print("[DEBUG] Max iterations reached")
    state["planner_output"] = combined_plan if combined_plan else {}
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
    schema_graph = load_schema_graph()
    state["schema_info"] = schema_graph
    print(f"[DEBUG] Schema info loaded: {len(schema_graph)} keys")
    return state

def sql_executor_node(state: State) -> State:
    """Executes SQL query via interpreter."""
    print("[SQL EXECUTOR NODE] Executing SQL query...")
    plan = state.get("planner_output", {})
    print(f"[DEBUG] SQL executor plan: {plan}")
    from .interpretor import interpret_and_execute
    result = interpret_and_execute(plan)
    state["sql_result"] = result
    print(f"[DEBUG] SQL result: {result[:100] if result else 'None'}...")
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
    
    print(f"[DEBUG] insights stored: {insights[:100] if insights else 'None'}...")
    print(f"[DEBUG] final_answer stored: {final_answer[:100] if final_answer else 'None'}...")
    
    return state

def planner_router(state: State) -> str:
    """
    Routes based on planner_output flags.
    """
    plan = state.get("planner_output", {})
    exec_mode = plan.get("execution_mode")
    print(f"[DEBUG] Router: plan={plan}")
    print(f"[DEBUG] execution_mode: {exec_mode}")  

    # ✅ REMOVED: Don't clear metadata_requests based on appended_data
    # This allows model mode to still request metadata

    if plan.get("needs_clarification"):
        state["status"] = "need_clarification"
        print("[DEBUG] Routing to user_clarification")
        return "user_clarification"

    # ✅ CHANGED: Check metadata_requests FIRST, regardless of execution_mode
    if plan.get("metadata_requests"):
        print("[DEBUG] Routing to schema_info for metadata requests") 
        return "schema_info"  

    if exec_mode == "sql":
        print("[DEBUG] Routing to sql_executor")  
        return "sql_executor"

    # ✅ For model mode with no metadata requests, go straight to output
    print("[DEBUG] Routing to output")  
    return "output"


def build_graph():
    workflow = StateGraph(State)

    workflow.add_node("input", input_node)
    workflow.add_node("planner", planner_node)
    workflow.add_node("user_clarification", user_clarification_node)
    workflow.add_node("schema_info", schema_info_node)
    workflow.add_node("sql_executor", sql_executor_node)
    workflow.add_node("output", output_node)

    workflow.set_entry_point("input")

    workflow.add_edge("input", "planner")

    workflow.add_conditional_edges(
        source="planner",
        path=planner_router,  
        path_map={
            "user_clarification": "user_clarification",
            "schema_info": "schema_info",
            "sql_executor": "sql_executor",
            "output": "output",
        }
    )

    workflow.add_edge("user_clarification", END)

    workflow.add_edge("schema_info", "planner")

    workflow.add_edge("sql_executor", "output")

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