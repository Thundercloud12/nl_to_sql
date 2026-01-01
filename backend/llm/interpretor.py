# interpreter.py
import json
import pandas as pd
import os
import duckdb
import google.generativeai as genai
from .llm_tracker import log_llm_call
from typing import Dict,List
import time
from tenacity import retry, stop_after_attempt, wait_exponential
from dotenv import load_dotenv
load_dotenv()

# Configure Gemini API
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

# Global list to track request timestamps for rate limiting
request_timestamps = []

@retry(
    retry=lambda exc: isinstance(exc, Exception),  # Retry on any exception (rate limit, etc.)
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=60)  # Start at 4s, double up to 60s
)
def rate_limited_llm_call(prompt: str, model_name: str = "gemma-3-27b-it"):
    """
    Make a rate-limited LLM call with exponential backoff on failures.
    Limits to ~50 requests per minute.
    Returns (response_text, response_object)
    """
    global request_timestamps
    
    # Rate limiting: sliding window of 60 seconds, max 50 requests
    now = time.time()
    request_timestamps[:] = [t for t in request_timestamps if now - t < 60]  # Keep last 60s
    if len(request_timestamps) >= 50:
        sleep_time = 60 - (now - request_timestamps[0])
        print(f"[RATE LIMIT] Sleeping {sleep_time:.1f}s to avoid limit")
        time.sleep(sleep_time)
    
    request_timestamps.append(now)
    
    model = genai.GenerativeModel(
        model_name,
        generation_config=genai.GenerationConfig(
            temperature=0,
            top_p=1,
            top_k=1,
        )
    )
    
    response = model.generate_content(prompt)
    return response.text.strip(), response


def load_tables(short_names: list, data_source_id: str) -> duckdb.DuckDBPyConnection:
    """
    Load Parquet tables into DuckDB connection from datasource-specific folder.
    Tables are loaded from normalized Parquet files created by graph_builder.
    
    Args:
        short_names: List of short table names (e.g., ['T1', 'T2'])
        data_source_id: DataSource ID for folder isolation
    """
    print("[LOAD_TABLES] Loading tables into DuckDB...")
    con = duckdb.connect()
    
    datasource_dir = os.path.join("uploaded_files", f"datasource_{data_source_id}")
    metadata_path = os.path.join(datasource_dir, "raw_metadata.json")
    
    if not os.path.exists(metadata_path):
        raise FileNotFoundError(f"raw_metadata.json not found at {metadata_path}. Please run schema build first.")
    
    with open(metadata_path, "r") as f:
        metadata = json.load(f)
    
    for short in short_names:
        if short in metadata["tables"]:
            # Use the specific parquet file in the datasource folder
            parquet_path = os.path.join(datasource_dir, "data.parquet")
            
            if os.path.exists(parquet_path):
                try:
                    con.execute(f"CREATE TABLE {short} AS SELECT * FROM read_parquet('{parquet_path}')")
                    print(f"[LOAD_TABLES] ✓ Loaded {short} from {parquet_path}")
                except Exception as e:
                    print(f"[LOAD_TABLES] ✗ Error loading {short}: {e}")
                    con.execute(f"CREATE TABLE {short} AS SELECT * FROM (SELECT NULL) WHERE 1=0")
            else:
                print(f"[LOAD_TABLES] ⚠ Parquet file not found at {parquet_path}, creating empty table")
                con.execute(f"CREATE TABLE {short} AS SELECT * FROM (SELECT NULL) WHERE 1=0")
        else:
            print(f"[LOAD_TABLES] ⚠ No mapping found for {short} in metadata")
    
    return con


def get_actual_schema_from_duckdb(con: duckdb.DuckDBPyConnection, table_names: list) -> dict:
    """
    Query DuckDB to get the ACTUAL schema of loaded tables.
    This is more reliable than metadata files.
    """
    actual_schema = {}
    for table in table_names:
        try:
            # Get columns and types directly from DuckDB
            result = con.execute(f"PRAGMA table_info({table})").fetchall()
            columns = {row[1]: row[2] for row in result}  # {column_name: data_type}
            actual_schema[table] = {
                "columns": columns,
                "column_names": list(columns.keys())
            }
        except Exception as e:
            print(f"[WARNING] Could not get schema for {table}: {e}")
            actual_schema[table] = {"columns": {}, "column_names": []}
    
    return actual_schema


def generate_code(plan: dict, con: duckdb.DuckDBPyConnection, data_source_id: str, error_context: str = "") -> str:
    """
    Generate DuckDB SQL code from plan.
    Uses actual schema from DuckDB to ensure column names match.
    """
    datasource_dir = os.path.join("uploaded_files", f"datasource_{data_source_id}")
    metadata_path = os.path.join(datasource_dir, "raw_metadata.json")
    
    with open(metadata_path, "r") as f:
        metadata = json.load(f)
    
    # Build error feedback section if we have previous errors
    error_section = ""
    if error_context:
        error_section = f"""
⚠️ PREVIOUS ATTEMPT FAILED WITH ERROR:
{error_context}

Please fix the SQL to avoid this error. Common fixes:
- Column not found: Check column names exist in metadata
- Type mismatch: Check data types
- Syntax error: Check SQL syntax for DuckDB
- Use EXACT column names from the schema below.
"""
    
    # Get ACTUAL schema from DuckDB instead of relying on metadata file
    loaded_tables = plan.get("tables", [])
    actual_schema = get_actual_schema_from_duckdb(con, loaded_tables)
    
    # List available tables and their actual columns explicitly
    available_tables_str = ", ".join(loaded_tables)
    
    # Build schema info showing actual columns
    schema_info = "ACTUAL TABLE SCHEMAS IN DuckDB (from normalized Parquet files):\n"
    for table, schema in actual_schema.items():
        columns = schema.get("column_names", [])
        schema_info += f"\n{table}:\n  Columns: {', '.join(columns)}\n"
    
    prompt = f"""
You are a STRICT DuckDB SQL generator.

Your ONLY job: produce SAFE, EXECUTABLE DuckDB SQL that implements the PLAN using the provided SCHEMA.

=========================
GLOBAL HARD RULES
=========================

1. OUTPUT FORMAT (MANDATORY)
- Output ONLY a single DuckDB SQL query.
- No markdown. No comments. No explanations. No surrounding text.

2. SCHEMA SAFETY
- Use ONLY table and column names that exist EXACTLY (case-sensitive) in the SCHEMA.
- NEVER guess a column name.
- If the PLAN references missing columns or impossible logic:
    RETURN EXACTLY:
    SELECT * FROM (SELECT 1) WHERE 1=0 LIMIT 0;

3. JOINS
- Only join tables if the PLAN requires it.
- Use explicit JOIN … ON … syntax.
- NEVER invent join keys not present in schema.

4. AGGREGATIONS
- All non-aggregated columns MUST appear in GROUP BY.
- Allowed aggregates: COUNT, SUM, AVG, MIN, MAX, LIST, ARRAY_AGG.
- DO NOT use window functions unless explicitly required by PLAN.

5. STRING MATCHING (CRITICAL FOR DuckDB)
- CASE-INSENSITIVE pattern matching: Use (column_name ILIKE '%pattern%') with ILIKE OPERATOR (not function).
  ✓ CORRECT: WHERE genre ILIKE '%comedy%'
  ✗ WRONG: WHERE ILIKE(genre, '%comedy%')
- String concatenation uses ||.
- Regex uses REGEXP_MATCHES(col, pattern).
- For EXACT case-insensitive comparison (no wildcards): LOWER(column) = LOWER('value')
  Example: WHERE LOWER(genre) LIKE '%comedy%'

6. DATE & TIME RULES (STRICT)
Allowed ONLY:
- date_diff('day', col, CURRENT_DATE)
- col + INTERVAL 7 DAY
- col - INTERVAL 30 DAY
- CAST(col AS DATE)
- EXTRACT(YEAR FROM col)
- strptime(string_col, '%Y-%m-%d')
- strftime(date_col, '%Y-%m-%d')

FORBIDDEN (NEVER USE):
- Wrong strftime order
- Implicit VARCHAR→DATE casts
- Unsupported date formats
- Any unlisted date arithmetic

If PLAN requires forbidden date behavior, rewrite using allowed functions.

7. ERROR SELF-HEALING (MANDATORY)
If {error_section} contains a DuckDB error:
- Identify EXACTLY the failing function, column, or syntax.
- Rewrite the SQL using DIFFERENT valid DuckDB functions.
- NEVER repeat the same broken SQL structure.
- ALWAYS output a fresh rewritten query.

8. EXECUTION GUARANTEE
- The final SQL MUST be valid DuckDB syntax.

=========================
INPUTS
=========================
SCHEMA (authoritative):
{json.dumps(metadata["tables"], indent=2)}

PLAN (what to compute):
{json.dumps(plan, indent=2)}

ERROR SECTION:
{error_section}

=========================
FINAL OUTPUT RULE
=========================
Single DuckDB SQL query only.
"""
    
    # Track timing and tokens
    start_time = time.time()
    try:
        raw, response = rate_limited_llm_call(prompt)
        end_time = time.time()
        
    except ValueError as e:
        print(f"[ERROR] ValueError in LLM response: {e}")
        end_time = time.time()
        return ""
    except Exception as e:
        print(f"[ERROR] Exception in LLM call: {type(e).__name__}: {e}")
        end_time = time.time()
        return ""
    
    # Extract token usage from response
    input_tokens = None
    output_tokens = None
    total_tokens = None
    
    if hasattr(response, 'usage_metadata'):
        usage = response.usage_metadata
        input_tokens = getattr(usage, 'prompt_token_count', None)
        output_tokens = getattr(usage, 'candidates_token_count', None)
        total_tokens = getattr(usage, 'total_token_count', None)
    
    # Log the LLM call
    log_llm_call(
        function_name="generate_code",
        model_name="gemma-3-27b-it",
        prompt=prompt,
        response_text=raw,
        start_time=start_time,
        end_time=end_time,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        metadata={"error_context_provided": bool(error_context), "loaded_tables": loaded_tables}
    )
    
    print(f"[DEBUG] LLM raw output: {raw[:500]}...")
    
    # Clean markdown formatting
    if raw.startswith("```sql"):
        raw = raw[6:].strip()
    elif raw.startswith("```"):
        raw = raw[3:].strip()
    if raw.endswith("```"):
        raw = raw[:-3].strip()
    
    return raw.strip()


def execute_generated_code(sql: str, con: duckdb.DuckDBPyConnection) -> tuple:
    """Execute SQL on DuckDB and return result DataFrame."""
    try:
        result = con.execute(sql).fetchdf()
        return result, None
    except Exception as e:
        error_msg = f"ExecutionError: {type(e).__name__}: {e}"
        print(f"[ERROR] {error_msg}")
        return None, error_msg


def execute_with_self_healing(plan: dict, con: duckdb.DuckDBPyConnection, data_source_id: str, max_retries: int = 5) -> pd.DataFrame:
    """
    Execute SQL with self-healing loop.
    
    Args:
        plan: Execution plan
        con: DuckDB connection
        data_source_id: DataSource ID for folder isolation
        max_retries: Max retry attempts
    """
    error_context = ""
    previous_codes = []
    
    for attempt in range(max_retries):
        print(f"[SELF-HEAL] Attempt {attempt + 1}/{max_retries}")
        
        sql = generate_code(plan, con, data_source_id, error_context)
        
        if sql in previous_codes:
            print(f"[SELF-HEAL] LLM generated same SQL again, trying with stronger hint...")
            error_context += "\n\nIMPORTANT: You generated the EXACT same SQL that failed before. Please try a DIFFERENT approach!"
            continue
        
        previous_codes.append(sql)
        
        result_df, error_msg = execute_generated_code(sql, con)
        
        if error_msg is None:
            print(f"[SELF-HEAL] Success on attempt {attempt + 1}")
            return result_df
        
        print(f"[SELF-HEAL] Attempt {attempt + 1} failed: {error_msg}")
        
        error_context = f"""
ERROR FROM ATTEMPT {attempt + 1}:
SQL that failed:
```
{sql}
```

Error message:
{error_msg}

Please analyze the error and generate FIXED SQL.
"""
    
    print(f"[SELF-HEAL] All {max_retries} attempts failed")
    return pd.DataFrame({
        "error": [f"Failed after {max_retries} attempts"],
        "last_error": [error_context[:500]]
    })

def apply_preprocessing(con: duckdb.DuckDBPyConnection, operations: List[Dict]) -> None:
    """
    Apply preprocessing operations to DuckDB tables.
    """
    print(f"[PREPROCESSING] Applying {len(operations)} operations...")
    
    for op in operations:
        op_type = op.get("type")
        table = op.get("table")
        
        try:
            if op_type == "encode":
                column = op.get("column")
                method = op.get("method", "label")
                
                if method == "label":
                    # Label encoding: Assign integer to each unique value
                    sql = f"""
                    CREATE OR REPLACE TABLE {table} AS 
                    SELECT *, 
                        DENSE_RANK() OVER (ORDER BY {column}) - 1 AS {column}_encoded
                    FROM {table}
                    """
                    con.execute(sql)
                    print(f"[PREPROCESSING] ✓ Label encoded {table}.{column}")
                
                elif method == "onehot":
                    # One-hot encoding: Create binary column for each category
                    unique_vals = con.execute(f"SELECT DISTINCT {column} FROM {table}").fetchall()
                    for val in unique_vals[:10]:  # Limit to 10 categories
                        val_str = str(val[0]).replace("'", "''")
                        col_name = f"{column}_{val_str}".replace(" ", "_")[:63]  # DuckDB name limit
                        sql = f"""
                        ALTER TABLE {table} 
                        ADD COLUMN {col_name} INTEGER DEFAULT 0;
                        UPDATE {table} SET {col_name} = 1 WHERE {column} = '{val_str}';
                        """
                        con.execute(sql)
                    print(f"[PREPROCESSING] ✓ One-hot encoded {table}.{column}")
                
                elif method == "binary":
                    # Binary encoding: 0/1 for 2 categories
                    sql = f"""
                    CREATE OR REPLACE TABLE {table} AS 
                    SELECT *, 
                        CASE WHEN {column} = (SELECT MIN({column}) FROM {table}) THEN 0 ELSE 1 END AS {column}_binary
                    FROM {table}
                    """
                    con.execute(sql)
                    print(f"[PREPROCESSING] ✓ Binary encoded {table}.{column}")
            
            elif op_type == "fill_missing":
                column = op.get("column")
                method = op.get("method", "mean")
                
                if method == "mean":
                    sql = f"""
                    UPDATE {table} 
                    SET {column} = (SELECT AVG({column}) FROM {table} WHERE {column} IS NOT NULL)
                    WHERE {column} IS NULL
                    """
                elif method == "median":
                    sql = f"""
                    UPDATE {table} 
                    SET {column} = (SELECT MEDIAN({column}) FROM {table} WHERE {column} IS NOT NULL)
                    WHERE {column} IS NULL
                    """
                elif method == "mode":
                    sql = f"""
                    UPDATE {table} 
                    SET {column} = (SELECT {column} FROM {table} WHERE {column} IS NOT NULL 
                                   GROUP BY {column} ORDER BY COUNT(*) DESC LIMIT 1)
                    WHERE {column} IS NULL
                    """
                elif method == "drop":
                    sql = f"DELETE FROM {table} WHERE {column} IS NULL"
                
                con.execute(sql)
                print(f"[PREPROCESSING] ✓ Filled missing in {table}.{column} using {method}")
            
            elif op_type == "normalize":
                columns = op.get("columns", [])
                method = op.get("method", "standard")
                
                for column in columns:
                    if method == "standard":
                        # Z-score normalization
                        sql = f"""
                        CREATE OR REPLACE TABLE {table} AS 
                        SELECT *, 
                            ({column} - (SELECT AVG({column}) FROM {table})) / 
                            (SELECT STDDEV({column}) FROM {table}) AS {column}_normalized
                        FROM {table}
                        """
                    elif method == "minmax":
                        # Min-max normalization
                        sql = f"""
                        CREATE OR REPLACE TABLE {table} AS 
                        SELECT *, 
                            ({column} - (SELECT MIN({column}) FROM {table})) / 
                            ((SELECT MAX({column}) FROM {table}) - (SELECT MIN({column}) FROM {table})) 
                            AS {column}_normalized
                        FROM {table}
                        """
                    
                    con.execute(sql)
                    print(f"[PREPROCESSING] ✓ Normalized {table}.{column} using {method}")
            
            elif op_type == "drop_duplicates":
                sql = f"""
                CREATE OR REPLACE TABLE {table} AS 
                SELECT DISTINCT * FROM {table}
                """
                con.execute(sql)
                print(f"[PREPROCESSING] ✓ Dropped duplicates from {table}")
            
            elif op_type == "cast":
                column = op.get("column")
                target_type = op.get("target_type", "VARCHAR")
                sql = f"""
                CREATE OR REPLACE TABLE {table} AS 
                SELECT *, CAST({column} AS {target_type}) AS {column}_casted
                FROM {table}
                """
                con.execute(sql)
                print(f"[PREPROCESSING] ✓ Casted {table}.{column} to {target_type}")
        
        except Exception as e:
            print(f"[PREPROCESSING] ✗ Error applying {op_type} on {table}: {e}")


def interpret_and_execute(plan: dict, data_source_id: str, existing_connection=None) -> str:
    """
    Main entry point: load tables → generate SQL → execute → return result.
    
    Args:
        plan: Execution plan from planner
        data_source_id: DataSource ID for folder isolation
        existing_connection: Pre-loaded DuckDB connection (from preprocessing)
    """
    if not plan.get("tables"):
        return "No tables specified in plan."
    
    # ✅ Use existing connection if provided (preprocessing already applied)
    if existing_connection:
        print("[INTERPRETER] Using existing DuckDB connection (preprocessed)")
        con = existing_connection
    else:
        print("[INTERPRETER] Loading fresh data")
        con = load_tables(plan["tables"], data_source_id)
    
    # Execute with self-healing
    result_df = execute_with_self_healing(plan, con, data_source_id, max_retries=5)
    
    # ✅ Only close if we created a new connection
    if not existing_connection:
        con.close()
    
    print(f"[DEBUG] Final result:\n{result_df}")
    
    # ✅ NEW: Advanced analysis for large results
    if isinstance(result_df, pd.DataFrame) and len(result_df) > 1000:
        print(f"[ANALYSIS] Result too large ({len(result_df)} rows), invoking advanced analysis...")
        
        # Load metadata for schema context from datasource-specific folder
        datasource_dir = os.path.join("uploaded_files", f"datasource_{data_source_id}")
        metadata_path = os.path.join(datasource_dir, "raw_metadata.json")
        
        with open(metadata_path, "r") as f:
            metadata = json.load(f)
        
        # Prepare context for LLM
        user_question = plan.get("user_question", "Unknown question")
        partial_result_preview = result_df.head(10).to_string(index=False)  # First 10 rows for context
        schema_preview = json.dumps(metadata["tables"], indent=2)[:2000]  # Truncate schema if too long
        
        analysis_prompt = f"""
You are a STRICT DuckDB SQL generator for ADVANCED ANALYSIS.
The initial query produced a large result ({len(result_df)} rows), which is too much to display.
Your job: Generate SAFE, EXECUTABLE DuckDB SQL to ANALYZE and SUMMARIZE the result into a concise DataFrame.

HARD RULES:
- OUTPUT ONLY DuckDB SQL (no markdown, no comments, no text).
- Input: The result is already in a temporary table called `temp_result`.
- Use: SELECT ... FROM temp_result
- Final query should return a summarized DataFrame with <100 rows.
- Examples: GROUP BY categories, TOP N with LIMIT, aggregate stats (COUNT, SUM, AVG).
- Use ONLY standard SQL: SELECT, FROM, WHERE, GROUP BY, ORDER BY, LIMIT, etc.
- Ensure the query is valid DuckDB SQL.

CONTEXT:
User Question: {user_question}
Partial Result Preview (first 10 rows):
{partial_result_preview}
Schema (truncated):
{schema_preview}

Example output:
SELECT category, COUNT(*) as count FROM temp_result GROUP BY category ORDER BY count DESC LIMIT 10
"""
        
        try:
            # Track timing and tokens for analysis
            start_time = time.time()
            analysis_sql, response = rate_limited_llm_call(analysis_prompt)
            end_time = time.time()
            
            # Extract token usage
            input_tokens = None
            output_tokens = None
            total_tokens = None
            
            if hasattr(response, 'usage_metadata'):
                usage = response.usage_metadata
                input_tokens = getattr(usage, 'prompt_token_count', None)
                output_tokens = getattr(usage, 'candidates_token_count', None)
                total_tokens = getattr(usage, 'total_token_count', None)
            
            # Log the LLM call
            log_llm_call(
                function_name="interpret_and_execute_analysis",
                model_name="gemma-3-27b-it",
                prompt=analysis_prompt,
                response_text=analysis_sql,
                start_time=start_time,
                end_time=end_time,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                metadata={"result_rows": len(result_df)}
            )
            
            # Clean SQL (similar to generate_code)
            if analysis_sql.startswith("```sql"):
                analysis_sql = analysis_sql[6:].strip()
            elif analysis_sql.startswith("```"):
                analysis_sql = analysis_sql[3:].strip()
            if analysis_sql.endswith("```"):
                analysis_sql = analysis_sql[:-3].strip()
            
            print(f"[ANALYSIS] Generated SQL: {analysis_sql[:200]}...")
            
            # Execute analysis SQL on result_df
            con = duckdb.connect()
            con.execute("CREATE TEMP TABLE temp_result AS SELECT * FROM result_df")
            analyzed_df = con.execute(analysis_sql).fetchdf()
            con.close()
            
            if analyzed_df is not None and isinstance(analyzed_df, pd.DataFrame):
                result_df = analyzed_df
                print(f"[ANALYSIS] Advanced analysis complete, new result has {len(result_df)} rows.")
            else:
                print("[ANALYSIS] Analysis failed, df not a DataFrame or None.")
        except Exception as e:
            print(f"[ANALYSIS] Error in advanced analysis: {e}, using original result.")
    
    # Convert to string with full content (no truncation)
    if isinstance(result_df, pd.DataFrame):

        if len(result_df) > 100:
            print(f"[WARNING] Result has {len(result_df)} rows, limiting to 100 rows")
            result_df = result_df.head(100)
        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', None)
        pd.set_option('display.max_colwidth', None)
        
        result_str = result_df.to_string(index=False)
        
        pd.reset_option('display.max_columns')
        pd.reset_option('display.width')
        pd.reset_option('display.max_colwidth')
        
        return result_str
    else:
        return str(result_df)