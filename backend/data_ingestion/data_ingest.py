# data_ingest.py
import os
import pandas as pd
from typing import Dict, Tuple, Any
import google.generativeai as genai
import json
import numpy as np


# Configure Gemini API
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

def convert_csvs_to_excel(path: str) -> None:
    """
    Recursively scan the folder for CSV files, convert each to Excel (.xlsx),
    save in the same location, and delete the original CSV.
    Handles multiple encodings robustly.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Path {path} does not exist.")

    # Common encodings to try in order
    encodings = [
        'utf-8',
        'latin-1',      # ISO-8859-1
        'iso-8859-1',
        'windows-1252', # Western European
        'cp1252',       # Windows Western
        'utf-16',
        'utf-32',
        'ascii',
        'cp850',        # Western European (DOS)
        'mac_roman',    # Mac OS Roman
    ]

    for root, dirs, files in os.walk(path):
        for fname in files:
            if fname.lower().endswith(".csv"):
                csv_path = os.path.join(root, fname)
                excel_path = os.path.splitext(csv_path)[0] + ".xlsx"
                
                df = None
                successful_encoding = None
                
                # Try each encoding until one works
                for encoding in encodings:
                    try:
                        df = pd.read_csv(csv_path, encoding=encoding)
                        successful_encoding = encoding
                        break
                    except (UnicodeDecodeError, UnicodeError):
                        continue
                    except Exception as e:
                        # Other errors (like file not found, permission issues)
                        print(f"Failed to convert {csv_path}: {e}")
                        break
                
                # If all encodings failed, try with error handling
                if df is None:
                    try:
                        # Try UTF-8 with error replacement as last resort
                        df = pd.read_csv(csv_path, encoding='utf-8', encoding_errors='replace')
                        successful_encoding = 'utf-8 (with replacements)'
                    except Exception as e:
                        print(f"Failed to convert {csv_path} with all encodings: {e}")
                        continue
                
                # Write to Excel if we successfully read the CSV
                if df is not None:
                    try:
                        df.to_excel(excel_path, index=False, engine="openpyxl")
                        os.remove(csv_path)
                        print(f"Converted {csv_path} to {excel_path} using {successful_encoding} encoding and deleted original CSV.")
                    except Exception as e:
                        print(f"Failed to write Excel file {excel_path}: {e}")

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
        model = genai.GenerativeModel("gemma-3-27b-it")
        response = model.generate_content(prompt)
        return response.text.strip()
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

if __name__ == "__main__":
    tables, schema = load_excel_folder("data/")

    # Build initial schema object (Step 1.2)
    initial_schema = build_initial_schema_object(schema)

    # Write to raw_metadata.json
    with open("raw_metadata.json", "w") as f:
        json.dump(initial_schema, f, indent=4)

    print("Initial Schema Object (Step 1.2) written to raw_metadata.json")

