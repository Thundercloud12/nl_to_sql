# graph_builder.py
import json
import os
import google.generativeai as genai
from .data_ingest import normalize_col, generate_table_summary, convert_csvs_to_excel
import pandas as pd
import numpy as np
from dotenv import load_dotenv
import duckdb
import time
from tenacity import retry, stop_after_attempt, wait_exponential

load_dotenv()
api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    raise ValueError("GOOGLE_API_KEY not set")
genai.configure(api_key=api_key)

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

def convert_excel_to_parquet(data_folder: str = "data/") -> None:
    """Step 1: Convert Excel to Parquet with normalized columns"""
    convert_csvs_to_excel(data_folder)  # CSV → Excel first
    
    for root, dirs, files in os.walk(data_folder):
        for filename in files:
            if filename.endswith(('.xlsx', '.xls', '.xlsm')):
                excel_path = os.path.join(root, filename)
                
                try:
                    xls = pd.ExcelFile(excel_path, engine="openpyxl")
                    for sheet in xls.sheet_names:
                        df = xls.parse(sheet_name=sheet)
                        df.columns = [normalize_col(str(c)) for c in df.columns]
                        df.dropna(axis=1, how="all", inplace=True)
                        df.dropna(axis=0, how="all", inplace=True)
                        
                        if df.empty:
                            continue
                        
                        # Create parquet filename
                        base_name = f"{os.path.splitext(filename)[0]}__{sheet}"
                        parquet_filename = f"{base_name}.parquet"
                        
                        relative_path = os.path.relpath(root, data_folder)
                        if relative_path == ".":
                            parquet_path = os.path.join(data_folder, parquet_filename)
                        else:
                            parquet_dir = os.path.join(data_folder, relative_path)
                            os.makedirs(parquet_dir, exist_ok=True)
                            parquet_path = os.path.join(parquet_dir, parquet_filename)
                        
                        df.to_parquet(parquet_path)
                        print(f"[CONVERT] ✓ {excel_path}::{sheet} → {parquet_path}")
                except Exception as e:
                    print(f"[CONVERT] ✗ Error: {excel_path}: {e}")

def json_sanitize(obj):
    if isinstance(obj, dict):
        return {k: json_sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [json_sanitize(v) for v in obj]
    if isinstance(obj, (pd.Timestamp, np.datetime64)):
        return obj.isoformat()
    if isinstance(obj, float):
        if np.isnan(obj) or np.isinf(obj):
            return None
    return obj



def build_metadata_from_parquet(
    data_folder: str,
    threshold: float = 0.70
) -> dict:
    """
    Normalize Parquet files by resolving ambiguous column types using
    DuckDB try_cast / try_strptime, overwrite files with cleaned schema,
    and build metadata.
    """

    # Precedence: most informative → least informative
    canonical_types = [
        ("TIMESTAMP", "TIMESTAMP"),
        ("BIGINT", "INTEGER"),
        ("DOUBLE", "FLOAT"),
        ("BOOLEAN", "BOOLEAN"),
        ("VARCHAR", "STRING"),
    ]

    timestamp_formats = [
        "%m/%d/%Y %H:%M",
        "%m/%d/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
    ]

    initial_schema = {"tables": {}}
    table_counter = 1
    con = duckdb.connect()

    for root, _, files in os.walk(data_folder):
        for filename in files:
            if not filename.endswith(".parquet"):
                continue

            parquet_path = os.path.join(root, filename)
            short_name = f"T{table_counter}"
            table_counter += 1

            try:
                # Load raw parquet
                con.execute(
                    f"CREATE OR REPLACE TABLE raw AS SELECT * FROM read_parquet('{parquet_path}')"
                )

                cols = con.execute("DESCRIBE raw").fetchall()
                col_names = [c[0] for c in cols]
                raw_types = {c[0]: c[1].upper() for c in cols}

                select_exprs = []
                final_types = {}

                for col in col_names:
                    chosen_type = "VARCHAR"
                    print("i AM HERE")
                    # Distinct count for BOOLEAN guard
                    distinct_count = con.execute(f"""
                        SELECT COUNT(DISTINCT "{col}")
                        FROM raw
                        WHERE "{col}" IS NOT NULL
                    """).fetchone()[0]

                    for duck_type, _ in canonical_types:
                        # Guard: BOOLEAN only if ≤ 2 distinct non-null values
                        if duck_type == "BOOLEAN" and distinct_count > 2:
                            continue

                        # Guard: TIMESTAMP only for string columns
                        if duck_type == "TIMESTAMP" and raw_types[col] not in ("VARCHAR", "TEXT"):
                            continue

                        if duck_type == "TIMESTAMP":
                            success_ratio = con.execute(f"""
                                SELECT
                                    COUNT(
                                        COALESCE(
                                            {", ".join(
                                                f"try_strptime(\"{col}\", '{fmt}')"
                                                for fmt in timestamp_formats
                                            )}
                                        )
                                    )::DOUBLE
                                    / NULLIF(COUNT(*), 0)
                                FROM raw
                            """).fetchone()[0]
                        else:
                            success_ratio = con.execute(f"""
                                SELECT
                                    COUNT(try_cast("{col}" AS {duck_type}))::DOUBLE
                                    / NULLIF(COUNT(*), 0)
                                FROM raw
                            """).fetchone()[0]

                        if success_ratio is not None and success_ratio >= threshold:
                            chosen_type = duck_type
                            break

                    if chosen_type == "TIMESTAMP":
                        select_exprs.append(f"""
                            COALESCE(
                                {", ".join(
                                    f"try_strptime(\"{col}\", '{fmt}')"
                                    for fmt in timestamp_formats
                                )}
                            ) AS "{col}"
                        """)
                    else:
                        select_exprs.append(
                            f"try_cast(\"{col}\" AS {chosen_type}) AS \"{col}\""
                        )

                    final_types[col] = chosen_type

                # Create normalized table
                con.execute(f"""
                    CREATE OR REPLACE TABLE normalized AS
                    SELECT {", ".join(select_exprs)}
                    FROM raw
                """)

                # Overwrite parquet with cleaned schema
                con.execute(f"""
                    COPY normalized TO '{parquet_path}'
                    (FORMAT PARQUET, OVERWRITE_OR_IGNORE TRUE)
                """)

                # Read cleaned parquet into pandas
                df = pd.read_parquet(parquet_path)

                def json_safe(value):
                    # Handle timestamps
                    if isinstance(value, (pd.Timestamp, np.datetime64)):
                        return value.isoformat()

                    # Handle NaN / inf / -inf
                    if isinstance(value, float):
                        if np.isnan(value) or np.isinf(value):
                            return None

                    return value

                samples = (
                    df.head(3)
                    .map(json_safe)   # <-- replaces applymap (future-proof)
                    .to_dict(orient="records")
                )




                summary = generate_table_summary(
                    filename,
                    list(df.columns),
                    samples
                )

                initial_schema["tables"][short_name] = json_sanitize({
                    "original_name": filename.replace(".parquet", ""),
                    "columns": list(df.columns),
                    "canonical_types": final_types,
                    "samples": samples,
                    "summary": summary,
                })


                print(
                    f"[METADATA] ✓ {short_name}: {filename} "
                    f"({len(df.columns)} cols, normalized)"
                )

            except Exception as e:
                print(f"[METADATA] ✗ Error processing {parquet_path}: {e}")

    con.close()
    return initial_schema

def extract_tiny_metadata(initial_schema: dict) -> dict:
    """Step 3: Extract simplified metadata from dict (not file)"""
    tiny_metadata = {}
    for short_name, table_info in initial_schema["tables"].items():
        tiny_metadata[short_name] = {
            "table_name": table_info["original_name"],
            "number_of_columns": len(table_info["columns"]),
            "column_names": table_info["columns"],
            "inferred_entity_summary": table_info["summary"]
        }
    return tiny_metadata

def call_llm_for_relationships(tiny_metadata: dict, user_explanation: str) -> dict:
    """Step 4: Infer relationships via LLM"""
    metadata_text = "Tiny Metadata:\n"
    for short_name, info in tiny_metadata.items():
        metadata_text += f"- {short_name}: {info['table_name']} ({info['number_of_columns']} columns: {', '.join(info['column_names'])})\n  Summary: {info['inferred_entity_summary']}\n"
    
    prompt = f"""
You are analyzing a dataset based on user explanation and tiny metadata.

User Explanation:
{user_explanation}

Tiny Metadata:
{metadata_text}

Your job:
1. Use the user explanation as the highest authority.
2. Infer meaningful relationships: entities, versions, mergeability, join keys, and cluster groups.
3. Output a FINAL GRAPH in this EXACT JSON structure:

{{
  "tables": {{
    "T1": {{
      "entity_group": "string",
      "versions": ["T2", "T3"],
      "merge_possible": true/false,
      "join_keys": ["col1", "col2"],
      "similarity_score": 0.8,
      "reason": "string explanation"
    }}
  }},
  "clusters": {{
    "ClusterName": ["T1", "T2"]
  }}
}}

Respond with ONLY this JSON:
{{
  "final_graph": {{ ... }}
}}
"""
    
    try:
        response_text, response = rate_limited_llm_call(prompt)
        if response_text.startswith("```json"):
            response_text = response_text[7:].strip()
        if response_text.endswith("```"):
            response_text = response_text[:-3].strip()
        return json.loads(response_text)
    except Exception as e:
        print(f"[LLM] ✗ Error: {e}")
        return {"final_graph": {}}

def process_schema_build(input_folder: str) -> dict:
    """Main orchestration: Parquet first, then metadata, then relationships - return data directly"""
    print("[PIPELINE] Starting schema build...")
    
    # Step 1: Convert Excel → Parquet (normalized)
    convert_excel_to_parquet(input_folder)
    
    # Step 2: Build metadata from Parquet
    initial_schema = build_metadata_from_parquet(input_folder)
    print("[PIPELINE] ✓ Generated raw metadata")
    
    # Step 3: Extract tiny metadata
    tiny_metadata = extract_tiny_metadata(initial_schema)
    user_explanation = "Just a single table"  # You can make this configurable
    
    # Step 4: Infer relationships
    llm_response = call_llm_for_relationships(tiny_metadata, user_explanation)
    final_graph = llm_response.get("final_graph", {})
    
    print("[PIPELINE] ✓ Generated schema graph")
    
    # Return data directly for DB compatibility
    return {
        "raw_metadata": initial_schema,
        "schema_graph": final_graph
    }

if __name__ == "__main__":
    user_explanation = "Consumer data about Brazil consumers"
    result = process_schema_build(user_explanation)
    print(json.dumps(result, indent=4))
