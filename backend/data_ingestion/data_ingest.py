from __future__ import annotations
import os
import pandas as pd
from typing import Dict, Tuple, Any
import json
import numpy as np
import time
import pyarrow as pa
import pyarrow.parquet as pq
import gc
from pathlib import Path
import pandas as pd


MAX_SCHEMA_ROWS = 10_000
import chardet

def detect_encoding(path, bytes=100_000):
    with open(path, "rb") as f:
        raw = f.read(bytes)
    return chardet.detect(raw)["encoding"] or "utf-8"



def normalize_col(c: str) -> str:
    """Normalize column names: strip, lowercase, replace spaces with underscores."""
    return c.strip().lower().replace(" ", "_")

def generate_table_summary(table_name: str, columns: list, samples: list) -> str:
    """
    Use Gemini to generate a lightweight summary of the table.
    """
    prompt = f"""
        You are a data analyst. Given a table name, its columns, and sample rows, provide a very short (1-2 sentence) summary of what this table represents.I dont want number of columns n all. A suggestion of what this sheet might contain or model. Be concise.

        Table Name: {table_name}
        Columns: {', '.join(columns)}
        Sample Rows: {samples[:3]}  # First 3 samples

        Summary:
    """
    try:
        response_text, response = rate_limited_llm_call(prompt)
        return response_text
    except Exception as e:
        return f"Table containing {len(columns)} columns with data like {columns[:3]}."


def build_initial_schema_object(schema: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    Build the initial schema object as per Step 1.2 with improvements.
    - Short table names (T1, T2, ...)
    - Include original_name, columns, dtypes, samples (limited to 3), summary
    """
    initial_schema = {"tables": {}}
    table_counter = 1

    for original_name, metadata in schema.items():
        short_name = f"T{table_counter}"
        table_counter += 1

        # Limit samples to 3
        samples = metadata["sample_rows"][:3]

        # Generate summary using Gemini
        summary = generate_table_summary(original_name, metadata["columns"], samples)

        initial_schema["tables"][short_name] = {
            "original_name": original_name,
            "columns": metadata["columns"],
            "dtypes": metadata["dtypes"],
            "samples": samples,
            "summary": summary,
        }

    return initial_schema



def convert_csv_to_parquet(data_folder: str = "data/") -> dict:
    """
    Convert CSV files to Parquet with detailed error tracking.
    
    Returns:
        {
            "success": bool,
            "converted_files": [list of parquet paths],
            "failed_files": [list of {file, error}],
            "total": int
        }
    """
    base_path = Path(data_folder)
    converted_files = []
    failed_files = []
    csv_files = list(base_path.rglob("*.csv"))
    
    print(f"[CONVERT-CSV] Found {len(csv_files)} CSV file(s)")
    
    if not csv_files:
        return {
            "success": False,
            "converted_files": [],
            "failed_files": [],
            "total": 0,
            "error": "No CSV files found"
        }

    for csv_path in csv_files:
        print(f"[CONVERT-CSV] Processing {csv_path.name}...")

        try:
            # Detect encoding with fallback
            encoding = detect_encoding(csv_path)
            if not encoding:
                print(f"[CONVERT-CSV] ⚠️ Encoding detection failed for {csv_path}, using utf-8 fallback")
                encoding = "utf-8"

            # Try to read CSV
            try:
                df = pd.read_csv(
                    csv_path,
                    encoding=encoding,
                    nrows=MAX_SCHEMA_ROWS,
                    low_memory=True
                )
            except UnicodeDecodeError as ue:
                print(f"[CONVERT-CSV] ⚠️ Encoding {encoding} failed, trying utf-8 with errors='replace'")
                df = pd.read_csv(
                    csv_path,
                    encoding="utf-8",
                    errors="replace",
                    nrows=MAX_SCHEMA_ROWS,
                    low_memory=True
                )

            if df.empty:
                print(f"[CONVERT-CSV] ⚠️ CSV is empty: {csv_path.name}")
                failed_files.append({
                    "file": str(csv_path),
                    "error": "Empty CSV file"
                })
                continue

            # Normalize and clean
            df.columns = tuple(normalize_col(str(c)) for c in df.columns)
            df.dropna(axis=1, how="all", inplace=True)

            # Check if any columns left
            if len(df.columns) == 0:
                print(f"[CONVERT-CSV] ✗ All columns are empty: {csv_path.name}")
                failed_files.append({
                    "file": str(csv_path),
                    "error": "All columns are empty"
                })
                continue

            # Write parquet
            parquet_path = csv_path.with_suffix(".parquet")
            try:
                df.to_parquet(parquet_path, index=False)
                converted_files.append(str(parquet_path))
                print(f"[CONVERT-CSV] ✓ Converted {csv_path.name} → {parquet_path.name}")
            except Exception as pq_err:
                print(f"[CONVERT-CSV] ✗ Failed to write Parquet for {csv_path.name}: {pq_err}")
                failed_files.append({
                    "file": str(csv_path),
                    "error": f"Parquet write failed: {str(pq_err)}"
                })

        except Exception as exc:
            print(f"[CONVERT-CSV] ✗ Error processing {csv_path}: {exc}")
            failed_files.append({
                "file": str(csv_path),
                "error": str(exc)
            })

        finally:
            if "df" in locals():
                del df
            gc.collect()

    # Summary
    success = len(failed_files) == 0
    print(f"[CONVERT-CSV] Summary: {len(converted_files)}/{len(csv_files)} files converted successfully")
    
    if failed_files:
        print(f"[CONVERT-CSV] Failed files:")
        for item in failed_files:
            print(f"  - {item['file']}: {item['error']}")
    
    return {
        "success": success,
        "converted_files": converted_files,
        "failed_files": failed_files,
        "total": len(csv_files)
    }




