from __future__ import annotations
import os
import pandas as pd
from typing import Dict, Tuple, Any
import google.generativeai as genai
import json
import numpy as np
import time
from tenacity import retry, stop_after_attempt, wait_exponential
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

def load_excel_folder(path: str) -> Tuple[Dict[str, pd.DataFrame], Dict[str, Dict[str, Any]]]:
    """
    Load all Excel files (recursively) from a folder.
    Extract every sheet from each file.
    Return:
        tables: {unique_table_name: DataFrame}
        schema: {unique_table_name: {columns, dtypes, file_path, file_name, sheet, sample_rows}}
    """
    convert_csvs_to_excel(path)
    tables = {}
    schema = {}

    if not os.path.exists(path):
        raise FileNotFoundError(f"Path {path} does not exist.")

    for root, dirs, files in os.walk(path):
        for fname in files:
            # Only Excel files
            if not fname.lower().endswith((".xlsx", ".xls", ".xlsm")):
                continue

            full_path = os.path.join(root, fname)

            try:
                # Load file once → sheets later
                xls = pd.ExcelFile(full_path, engine="openpyxl")

                for sheet in xls.sheet_names:
                    # Load sheet
                    try:
                        df = xls.parse(sheet_name=sheet)
                    except Exception as e:
                        print(f"   ⚠️ Could not parse sheet '{sheet}' in {fname}: {e}")
                        continue

                    # Normalize column names
                    df.rename(columns=lambda c: normalize_col(str(c)), inplace=True)

                    # Light cleaning: remove fully empty rows/columns only
                    df.dropna(axis=1, how="all", inplace=True)
                    df.dropna(axis=0, how="all", inplace=True)

                    # Skip if empty
                    if df.empty or df.shape[1] == 0:
                        continue

                    # Create unique table name
                    base = f"{os.path.splitext(fname)[0]}__{sheet}"
                    name = base
                    idx = 1
                    while name in tables:
                        name = f"{base}_{idx}"
                        idx += 1

                    # Save table
                    tables[name] = df

                    # Save schema info (Step 1.1 metadata)
                    sample_rows = df.head(3).replace({np.nan: None}).to_dict(orient="records")  # 3 sample rows as list of dicts
                    schema[name] = {
                        "columns": list(df.columns),
                        "dtypes": dict(df.dtypes.astype(str)),
                        "file_path": full_path,
                        "file_name": fname,
                        "sheet": sheet,
                        "sample_rows": sample_rows,
                    }

            except Exception as e:
                print(f"⚠️ Failed to load {full_path}: {e}")
                continue

    return tables, schema

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


if __name__ == "__main__":
    tables, schema = load_excel_folder("data/")

    # Build initial schema object (Step 1.2)
    initial_schema = build_initial_schema_object(schema)

    # Write to raw_metadata.json
    with open("raw_metadata.json", "w") as f:
        json.dump(initial_schema, f, indent=4)

    print("Initial Schema Object (Step 1.2) written to raw_metadata.json")

