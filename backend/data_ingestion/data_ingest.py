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



def convert_csv_to_parquet(data_folder: str = "data/") -> None:
    """
    Convert CSV files to Parquet in-place using a memory-conscious approach.
    Reads only a limited number of rows, normalizes columns, drops empty columns,
    and writes Parquet with minimal memory overhead.
    """
    base_path = Path(data_folder)

    for csv_path in base_path.rglob("*.csv"):
        print(f"[CONVERT] Processing {csv_path}")

        try:
            encoding = detect_encoding(csv_path)

            # Read only required rows, no index, no dtype inference explosion
            df = pd.read_csv(
                csv_path,
                encoding=encoding,
                nrows=MAX_SCHEMA_ROWS,
                low_memory=True
            )

            if df.empty:
                continue

            # Normalize columns (in-place, no new list retained)
            df.columns = tuple(normalize_col(str(c)) for c in df.columns)

            # Drop fully empty columns
            df.dropna(axis=1, how="all", inplace=True)

            parquet_path = csv_path.with_suffix(".parquet")

            # Write parquet without keeping extra references
            df.to_parquet(
                parquet_path,
                index=False
            )

        except Exception as exc:
            print(f"[CONVERT] ✗ Error {csv_path}: {exc}")

        finally:
            # Explicit cleanup (important for Render / small containers)
            if "df" in locals():
                del df
            gc.collect()

        print(f"[CONVERT] ✓ Converted {csv_path.name}")




