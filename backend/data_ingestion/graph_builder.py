from __future__ import annotations
import json
import os
from .data_ingest import normalize_col, generate_table_summary,convert_csv_to_parquet
import pandas as pd
import numpy as np
from dotenv import load_dotenv
import duckdb
import time
import gc
from utils.llm_utils import rate_limited_llm_call


from pathlib import Path
import duckdb
import pandas as pd
import numpy as np
import gc




MAX_SCHEMA_ROWS = 10_000



def convert_excel_to_parquet(data_folder: str = "data/") -> None:
    for root, _, files in os.walk(data_folder):
        for filename in files:
            if not filename.endswith(('.xlsx', '.xls', '.xlsm')):
                continue

            excel_path = os.path.join(root, filename)
            print(f"[CONVERT] Processing {excel_path}")

            try:
                xls = pd.ExcelFile(excel_path, engine="openpyxl")

                for sheet in xls.sheet_names:
                    print(f"[CONVERT] Sheet: {sheet}")

                    # 🔥 LIMIT ROWS
                    df = pd.read_excel(
                        excel_path,
                        sheet_name=sheet,
                        nrows=MAX_SCHEMA_ROWS,
                        engine="openpyxl"
                    )

                    if df.empty:
                        del df
                        continue

                    df.columns = [normalize_col(str(c)) for c in df.columns]

                    # Drop empty cols only (rows are sampled anyway)
                    df.dropna(axis=1, how="all", inplace=True)

                    parquet_filename = f"{os.path.splitext(filename)[0]}__{sheet}.parquet"
                    parquet_path = os.path.join(root, parquet_filename)

                    df.to_parquet(parquet_path)

                    # 🚨 CRITICAL
                    del df
                    gc.collect()

            except Exception as e:
                print(f"[CONVERT] ✗ Error {excel_path}: {e}")


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

    canonical_types = [
        ("TIMESTAMP", "TIMESTAMP"),
        ("BIGINT", "INTEGER"),
        ("DOUBLE", "FLOAT"),
        ("BOOLEAN", "BOOLEAN"),
        ("VARCHAR", "STRING"),
    ]

    timestamp_formats = (
        "%m/%d/%Y %H:%M",
        "%m/%d/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
    )

    initial_schema: dict = {"tables": {}}
    table_counter = 1

    # Single lightweight DuckDB connection (no pandas binding)
    con = duckdb.connect(database=":memory:")

    try:
        for parquet_path in Path(data_folder).rglob("*.parquet"):
            short_name = f"T{table_counter}"
            table_counter += 1
            parquet_str = parquet_path.as_posix().replace("'", "''")
            try:
                # Load parquet lazily into DuckDB (no pandas yet)
                con.execute(f"""
                    CREATE OR REPLACE VIEW raw AS
                    SELECT * FROM read_parquet('{parquet_str}')
                """)


                cols = con.execute("DESCRIBE raw").fetchall()
                # FIX: Change tuple to list for pandas compatibility
                col_names = [c[0] for c in cols]  # Was: tuple(c[0] for c in cols)
                raw_types = {c[0]: c[1].upper() for c in cols}

                select_exprs: list[str] = []
                final_types: dict[str, str] = {}

                for col in col_names:
                    chosen_type = "VARCHAR"

                    distinct_count = con.execute("""
                        SELECT COUNT(DISTINCT "{col}")
                        FROM raw
                        WHERE "{col}" IS NOT NULL
                    """.format(col=col)).fetchone()[0]

                    for duck_type, _ in canonical_types:
                        if duck_type == "BOOLEAN" and distinct_count > 2:
                            continue

                        if duck_type == "TIMESTAMP" and raw_types[col] not in ("VARCHAR", "TEXT"):
                            continue

                        if duck_type == "TIMESTAMP":
                            success_ratio = con.execute(f"""
                                SELECT
                                    COUNT(
                                        COALESCE(
                                            {", ".join(
                                                f'''try_strptime("{col}", '{fmt}')'''
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
                                    f'''try_strptime("{col}", '{fmt}')'''
                                    for fmt in timestamp_formats
                                )}
                            ) AS "{col}"
                        """)
                    else:
                        select_exprs.append(
                            f'try_cast("{col}" AS {chosen_type}) AS "{col}"'
                        )

                    final_types[col] = chosen_type

                # Normalize without materializing intermediate pandas frames
                con.execute(f"""
                    CREATE OR REPLACE TABLE normalized AS
                    SELECT {", ".join(select_exprs)}
                    FROM raw
                """)

                con.execute(f"""
                    COPY normalized TO '{parquet_str}'
                    (FORMAT PARQUET, OVERWRITE_OR_IGNORE TRUE)
                """)


                # 🔴 Only now load minimal data into pandas
                df = pd.read_parquet(
                    parquet_path,
                    columns=col_names  # Now a list, as required by pandas
                )

                def json_safe(value):
                    if isinstance(value, (pd.Timestamp, np.datetime64)):
                        return value.isoformat()
                    if isinstance(value, float):
                        if np.isnan(value) or np.isinf(value):
                            return None
                    return value

                samples = (
                    df.head(3)
                    .map(json_safe)
                    .to_dict(orient="records")
                )

                summary = generate_table_summary(
                    parquet_path.name,
                    list(df.columns),
                    samples
                )

                initial_schema["tables"][short_name] = json_sanitize({
                    "original_name": parquet_path.stem,
                    "columns": list(df.columns),
                    "canonical_types": final_types,
                    "samples": samples,
                    "summary": summary,
                })

                print(
                    f"[METADATA] ✓ {short_name}: {parquet_path.name} "
                    f"({len(df.columns)} cols, normalized)"
                )

            except Exception as exc:
                print(f"[METADATA] ✗ Error processing {parquet_path}: {exc}")

            finally:
                # Hard cleanup per file (critical on Render)
                if "df" in locals():
                    del df
                con.execute("DROP TABLE IF EXISTS normalized")
                con.execute("DROP VIEW IF EXISTS raw")
                gc.collect()

    finally:
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
    
    has_csv = any(f.endswith('.csv') for f in os.listdir(input_folder) if os.path.isfile(os.path.join(input_folder, f)))
    has_excel = any(f.endswith(('.xlsx', '.xls', '.xlsm')) for f in os.listdir(input_folder) if os.path.isfile(os.path.join(input_folder, f)))
    
    if has_csv:
        print("[PIPELINE] CSV files detected, converting to Parquet...")
        convert_csv_to_parquet(input_folder)
    elif has_excel:
        print("[PIPELINE] Excel files detected, converting to Parquet...")
        convert_excel_to_parquet(input_folder)
    else:
        print("[PIPELINE] No supported files found (CSV or Excel)")
        return {"raw_metadata": {"tables": {}}, "schema_graph": {}}
    
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
