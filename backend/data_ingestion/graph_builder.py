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



def convert_excel_to_parquet(data_folder: str = "data/") -> dict:
    """
    Convert Excel files to Parquet with detailed tracking and type inference.
    """
    converted_files = []
    failed_files = []
    excel_files = list(Path(data_folder).rglob("*.xlsx")) + \
                  list(Path(data_folder).rglob("*.xls")) + \
                  list(Path(data_folder).rglob("*.xlsm"))
    
    print(f"[CONVERT-EXCEL] Found {len(excel_files)} Excel file(s)")
    
    if not excel_files:
        return {
            "success": False,
            "converted_files": [],
            "failed_files": [],
            "total_files": 0,
            "error": "No Excel files found"
        }

    for excel_path in excel_files:
        print(f"[CONVERT-EXCEL] Processing {excel_path.name}...")

        try:
            # Determine engine based on file extension
            if excel_path.suffix.lower() == '.xls':
                engine = "xlrd"
            else:  # .xlsx or .xlsm
                engine = "openpyxl"

            # Check if engine is installed
            try:
                xls = pd.ExcelFile(excel_path, engine=engine)
            except ImportError as ie:
                print(f"[CONVERT-EXCEL] ✗ Engine '{engine}' not installed: {ie}")
                failed_files.append({
                    "file": str(excel_path),
                    "sheet": "N/A",
                    "error": f"Missing {engine} engine. Install: pip install {engine}"
                })
                continue
            except Exception as e:
                print(f"[CONVERT-EXCEL] ✗ Failed to open {excel_path.name}: {e}")
                failed_files.append({
                    "file": str(excel_path),
                    "sheet": "N/A",
                    "error": f"Failed to open Excel: {str(e)}"
                })
                continue

            # Process each sheet
            for sheet in xls.sheet_names:
                try:
                    print(f"[CONVERT-EXCEL] Processing sheet: {sheet}")

                    df = pd.read_excel(
                        excel_path,
                        sheet_name=sheet,
                        nrows=MAX_SCHEMA_ROWS,
                        engine=engine
                    )

                    if df.empty:
                        print(f"[CONVERT-EXCEL] ⚠️ Sheet '{sheet}' is empty, skipping")
                        failed_files.append({
                            "file": str(excel_path),
                            "sheet": sheet,
                            "error": "Empty sheet"
                        })
                        continue

                    # Normalize columns
                    try:
                        df.columns = [normalize_col(str(c)) for c in df.columns]
                    except Exception as col_err:
                        print(f"[CONVERT-EXCEL] ✗ Failed to normalize columns for {sheet}: {col_err}")
                        failed_files.append({
                            "file": str(excel_path),
                            "sheet": sheet,
                            "error": f"Column normalization failed: {str(col_err)}"
                        })
                        continue

                    # Drop empty columns
                    df.dropna(axis=1, how="all", inplace=True)

                    if len(df.columns) == 0:
                        print(f"[CONVERT-EXCEL] ✗ All columns empty for sheet {sheet}")
                        failed_files.append({
                            "file": str(excel_path),
                            "sheet": sheet,
                            "error": "All columns are empty"
                        })
                        continue

                    # 🔧 NEW: Infer and clean column types before Parquet write
                    print(f"[CONVERT-EXCEL] Inferring column types for {sheet}...")
                    df = _infer_and_clean_types(df, sheet)

                    # Write Parquet
                    parquet_filename = f"{excel_path.stem}__{sheet}.parquet"
                    parquet_path = excel_path.parent / parquet_filename

                    try:
                        df.to_parquet(parquet_path, index=False)
                        converted_files.append(str(parquet_path))
                        print(f"[CONVERT-EXCEL] ✓ {excel_path.name}/{sheet} → {parquet_filename}")
                    except Exception as pq_err:
                        print(f"[CONVERT-EXCEL] ✗ Parquet write failed for {sheet}: {pq_err}")
                        failed_files.append({
                            "file": str(excel_path),
                            "sheet": sheet,
                            "error": f"Parquet write failed: {str(pq_err)}"
                        })

                except Exception as sheet_err:
                    print(f"[CONVERT-EXCEL] ✗ Error processing sheet '{sheet}': {sheet_err}")
                    failed_files.append({
                        "file": str(excel_path),
                        "sheet": sheet,
                        "error": str(sheet_err)
                    })

                finally:
                    if "df" in locals():
                        del df
                    gc.collect()

        except Exception as file_err:
            print(f"[CONVERT-EXCEL] ✗ Error processing {excel_path}: {file_err}")
            failed_files.append({
                "file": str(excel_path),
                "sheet": "N/A",
                "error": str(file_err)
            })

    # Summary
    success = len(failed_files) == 0
    print(f"[CONVERT-EXCEL] Summary: {len(converted_files)}/{len(excel_files)} file(s) converted successfully")
    
    if failed_files:
        print(f"[CONVERT-EXCEL] Failed conversions:")
        for item in failed_files:
            print(f"  - {item['file']} (sheet: {item['sheet']}): {item['error']}")
    
    return {
        "success": success,
        "converted_files": converted_files,
        "failed_files": failed_files,
        "total_files": len(excel_files)
    }


def _infer_and_clean_types(df: pd.DataFrame, sheet_name: str) -> pd.DataFrame:
    """
    Infer and clean column types to ensure Parquet serializability.
    Handles date strings, numeric strings, and mixed types.
    """
    date_formats = [
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%d/%m/%Y",
        "%Y-%m-%d %H:%M:%S",
        "%m/%d/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
    ]
    
    for col in df.columns:
        original_dtype = df[col].dtype
        
        # Skip if already a proper type
        if original_dtype in [np.int64, np.float64, 'datetime64[ns]']:
            continue
        
        # Try to infer date columns
        if 'date' in col.lower() or 'time' in col.lower():
            print(f"[CONVERT-EXCEL] Attempting to parse {col} as datetime...")
            try:
                # Try pandas infer (fastest)
                df[col] = pd.to_datetime(df[col], errors='coerce')
                non_null_count = df[col].notna().sum()
                if non_null_count > len(df) * 0.5:  # If >50% parsed successfully
                    print(f"[CONVERT-EXCEL] ✓ {col} → datetime")
                    continue
                else:
                    print(f"[CONVERT-EXCEL] ⚠️ Only {non_null_count}/{len(df)} rows parsed as date, reverting to string")
                    df[col] = df[col].astype(str)
            except Exception as e:
                print(f"[CONVERT-EXCEL] ⚠️ Could not parse {col} as datetime: {e}, using string")
                df[col] = df[col].astype(str)
            continue
        
        # Try to infer numeric columns
        if df[col].dtype == 'object':
            try:
                # Try converting to numeric (handles string numbers like "123")
                numeric_col = pd.to_numeric(df[col], errors='coerce')
                non_null_count = numeric_col.notna().sum()
                if non_null_count > len(df) * 0.7:  # If >70% numeric
                    df[col] = numeric_col
                    print(f"[CONVERT-EXCEL] ✓ {col} → numeric")
                    continue
            except Exception as e:
                print(f"[CONVERT-EXCEL] ⚠️ Could not parse {col} as numeric: {e}")
        
        # Default: convert object to string for safe serialization
        if df[col].dtype == 'object':
            try:
                df[col] = df[col].astype(str)
                print(f"[CONVERT-EXCEL] ✓ {col} → string")
            except Exception as e:
                print(f"[CONVERT-EXCEL] ✗ Could not convert {col} to string: {e}")
    
    return df
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

    con = duckdb.connect(database=":memory:")

    try:
        for parquet_path in Path(data_folder).rglob("*.parquet"):
            short_name = f"T{table_counter}"
            table_counter += 1
            parquet_str = parquet_path.as_posix().replace("'", "''")
            try:
                # Load parquet lazily into DuckDB
                con.execute(f"""
                    CREATE OR REPLACE VIEW raw AS
                    SELECT * FROM read_parquet('{parquet_str}')
                """)

                cols = con.execute("DESCRIBE raw").fetchall()
                col_names = [c[0] for c in cols]
                raw_types = {c[0]: c[1].upper() for c in cols}

                select_exprs: list[str] = []
                final_types: dict[str, str] = {}

                for col in col_names:
                    chosen_type = "VARCHAR"

                    try:
                        distinct_count = con.execute("""
                            SELECT COUNT(DISTINCT "{col}")
                            FROM raw
                            WHERE "{col}" IS NOT NULL
                        """.format(col=col)).fetchone()[0]
                    except Exception as e:
                        print(f"[METADATA] Warning: Could not count distinct for {col}: {e}")
                        distinct_count = 0

                    for duck_type, _ in canonical_types:
                        if duck_type == "BOOLEAN" and distinct_count > 2:
                            continue

                        if duck_type == "TIMESTAMP" and raw_types[col] not in ("VARCHAR", "TEXT"):
                            continue

                        try:
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
                        except Exception as e:
                            print(f"[METADATA] Skipping type {duck_type} for {col}: {e}")
                            continue

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
                    print(f"[METADATA] Column {col}: inferred as {chosen_type}")

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

                # Load minimal data into pandas
                df = pd.read_parquet(
                    parquet_path,
                    columns=col_names
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
                # Hard cleanup per file
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
    """Main orchestration: Parquet first, then metadata, then relationships"""
    print("[PIPELINE] Starting schema build...")
    
    try:
        # Step 1: Convert files
        print("[PIPELINE] Step 1: Converting files to Parquet...")
        
        csv_result = None
        excel_result = None
        
        has_csv = any(f.endswith('.csv') for f in os.listdir(input_folder) if os.path.isfile(os.path.join(input_folder, f)))
        has_excel = any(f.endswith(('.xlsx', '.xls', '.xlsm')) for f in os.listdir(input_folder) if os.path.isfile(os.path.join(input_folder, f)))
        
        if has_csv:
            print("[PIPELINE] CSV files detected...")
            csv_result = convert_csv_to_parquet(input_folder)
            if not csv_result.get("success"):
                print(f"[PIPELINE] ⚠️ CSV conversion had issues: {len(csv_result.get('failed_files', []))} files failed")
        
        if has_excel:
            print("[PIPELINE] Excel files detected...")
            excel_result = convert_excel_to_parquet(input_folder)
            if not excel_result.get("success"):
                print(f"[PIPELINE] ⚠️ Excel conversion had issues: {len(excel_result.get('failed_files', []))} files failed")
        
        if not has_csv and not has_excel:
            print("[PIPELINE] ✗ No supported files found (CSV or Excel)")
            return {
                "raw_metadata": {"tables": {}},
                "schema_graph": {},
                "error": "No CSV or Excel files found"
            }
        
        # Step 2: Verify Parquet files were created
        print("[PIPELINE] Step 2: Verifying Parquet files...")
        parquet_files = list(Path(input_folder).rglob("*.parquet"))
        
        if not parquet_files:
            print("[PIPELINE] ✗ No Parquet files were generated")
            errors = []
            if csv_result:
                errors.extend([f['error'] for f in csv_result.get('failed_files', [])])
            if excel_result:
                errors.extend([f['error'] for f in excel_result.get('failed_files', [])])
            
            return {
                "raw_metadata": {"tables": {}},
                "schema_graph": {},
                "error": "No Parquet files generated",
                "details": errors
            }
        
        print(f"[PIPELINE] ✓ Generated {len(parquet_files)} Parquet file(s)")
        
        # Step 3: Build metadata
        print("[PIPELINE] Step 3: Building metadata from Parquet files...")
        try:
            initial_schema = build_metadata_from_parquet(input_folder)
            if not initial_schema.get("tables"):
                print("[PIPELINE] ⚠️ No tables found in metadata")
            else:
                print(f"[PIPELINE] ✓ Generated metadata for {len(initial_schema['tables'])} table(s)")
        except Exception as meta_err:
            print(f"[PIPELINE] ✗ Metadata generation failed: {meta_err}")
            return {
                "raw_metadata": {"tables": {}},
                "schema_graph": {},
                "error": f"Metadata generation failed: {str(meta_err)}"
            }
        
        # Step 4: Extract tiny metadata
        print("[PIPELINE] Step 4: Extracting tiny metadata...")
        try:
            tiny_metadata = extract_tiny_metadata(initial_schema)
            print(f"[PIPELINE] ✓ Extracted metadata for {len(tiny_metadata)} table(s)")
        except Exception as tiny_err:
            print(f"[PIPELINE] ⚠️ Tiny metadata extraction failed: {tiny_err}")
            tiny_metadata = {}
        
        # Step 5: Call LLM for relationships
        print("[PIPELINE] Step 5: Inferring table relationships...")
        try:
            user_explanation = "Just a single table"
            llm_response = call_llm_for_relationships(tiny_metadata, user_explanation)
            final_graph = llm_response.get("final_graph", {})
            print(f"[PIPELINE] ✓ Generated schema graph")
        except Exception as llm_err:
            print(f"[PIPELINE] ⚠️ LLM relationship inference failed: {llm_err}")
            final_graph = {}
        
        # Return with all components
        return {
            "raw_metadata": initial_schema,
            "schema_graph": final_graph,
            "conversion_summary": {
                "csv": csv_result,
                "excel": excel_result,
                "parquet_count": len(parquet_files)
            }
        }
    
    except Exception as e:
        print(f"[PIPELINE] ✗ Unexpected error in process_schema_build: {e}")
        return {
            "raw_metadata": {"tables": {}},
            "schema_graph": {},
            "error": f"Pipeline failed: {str(e)}"
        }
