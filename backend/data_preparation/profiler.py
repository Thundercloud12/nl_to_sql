"""
Dataset Profiler: Semantic detection of data patterns for cleaning
Optimized for memory efficiency with large files
"""
import pandas as pd
import duckdb
import numpy as np
from pathlib import Path
from typing import Dict, Any, List
import gc

def count_duplicates(con: duckdb.DuckDBPyConnection, table: str = "data") -> int:
    """
    Count duplicate rows in a table using DuckDB-safe SQL.

    Args:
        con: DuckDB connection
        table: table name (default: "data")

    Returns:
        Number of duplicate rows
    """
    result = con.execute(f"""
        SELECT
            (SELECT COUNT(*) FROM {table}) -
            (SELECT COUNT(*) FROM (SELECT DISTINCT * FROM {table}))
    """).fetchone()

    return result[0] if result else 0



def profile_dataset(file_path: str) -> Dict[str, Any]:
    """
    Profile dataset to detect semantic patterns for intelligent cleaning.
    MEMORY OPTIMIZED: Uses DuckDB's native streaming and column selection.
    
    Returns:
        {
            "structure": "time_series" | "transactional" | "tabular",
            "columns": {...},
            "quality_issues": [...],
            "recommended_mode": "visualization" | "minimal" | "aggressive",
            "row_count": int,
            "duplicate_rows": int
        }
    """
    
    # Load data into DuckDB with memory-efficient streaming
    con = duckdb.connect(":memory:")
    
    # === MEMORY OPTIMIZATION 1: Set aggressive memory settings ===
    con.execute("SET memory_limit='2GB'")
    con.execute("SET threads=4")
    
    file_path_obj = Path(file_path)
    suffix = file_path_obj.suffix.lower()
    
    df_temp = None
    
    if suffix == ".csv":
        # Memory optimization: Let DuckDB handle streaming directly without pandas
        try:
            import chardet
            with open(file_path, 'rb') as f:
                raw_data = f.read(100000)
                result = chardet.detect(raw_data)
                detected_encoding = result['encoding'] or 'utf-8'
            print(f"[PROFILER] Detected encoding: {detected_encoding}")
        except:
            detected_encoding = 'utf-8'
        
        # === MEMORY OPTIMIZATION 2: Use DuckDB's native CSV reader ===
        # DuckDB streams data and doesn't load entire file into memory
        data_loaded = False
        try:
            con.execute(f"""
                CREATE TABLE data AS 
                SELECT * FROM read_csv(
                    '{file_path}',
                    encoding='{detected_encoding}',
                    ignore_errors=true,
                    buffer_size=8388608
                )
            """)
            data_loaded = True
            print(f"[PROFILER] Loaded CSV with streaming (encoding: {detected_encoding})")
        except Exception as e1:
            print(f"[PROFILER] DuckDB CSV failed: {e1}, trying latin1...")
            try:
                con.execute(f"""
                    CREATE TABLE data AS 
                    SELECT * FROM read_csv(
                        '{file_path}',
                        encoding='latin1',
                        ignore_errors=true,
                        buffer_size=8388608
                    )
                """)
                data_loaded = True
            except Exception as e2:
                print(f"[PROFILER] Fallback to pandas (limited memory mode)...")
                # Last resort: pandas with chunked read
                try:
                    # Read only first 100K rows with pandas to estimate, then use DuckDB
                    chunks = []
                    chunk_size = 50000
                    for chunk in pd.read_csv(file_path, encoding=detected_encoding, 
                                            chunksize=chunk_size, on_bad_lines='skip'):
                        chunks.append(chunk)
                        # Only keep first chunk for analysis to save memory
                        break
                    
                    if chunks:
                        df_temp = chunks[0]
                        print(f"[PROFILER] Loaded first {len(df_temp)} rows with pandas")
                except:
                    try:
                        chunks = []
                        for chunk in pd.read_csv(file_path, encoding='latin1', 
                                                chunksize=50000, on_bad_lines='skip'):
                            chunks.append(chunk)
                            break
                        if chunks:
                            df_temp = chunks[0]
                    except Exception as e3:
                        raise ValueError(f"Could not load CSV: {e3}")
        
        # If pandas was used, create table from sample dataframe
        if not data_loaded and df_temp is not None:
            rel = con.from_df(df_temp)
            con.execute("CREATE TABLE data AS SELECT * FROM rel")
            # Clean up pandas dataframe from memory
            del df_temp
            del chunks
            gc.collect()
    
    elif suffix == ".parquet":
        # Parquet is already columnar/efficient
        con.execute(f"CREATE TABLE data AS SELECT * FROM read_parquet('{file_path}')")
        print(f"[PROFILER] Loaded Parquet file (columnar format)")
    
    elif suffix in [".xlsx", ".xls"]:
        # Excel: read with minimal memory footprint
        print(f"[PROFILER] Loading Excel (may use more memory)...")
        df_temp = pd.read_excel(file_path)
        rel = con.from_df(df_temp)
        con.execute("CREATE TABLE data AS SELECT * FROM rel")
        del df_temp
        gc.collect()
    
    else:
        raise ValueError(f"Unsupported file type: {suffix}")
    
    # === MEMORY OPTIMIZATION 3: Analyze schema without loading full data ===
    cols = con.execute("DESCRIBE data").fetchall()
    col_names = [c[0] for c in cols]
    col_types = {c[0]: c[1] for c in cols]
    
    # Get row count (doesn't load data)
    row_count = con.execute("SELECT COUNT(*) FROM data").fetchone()[0]
    print(f"[PROFILER] Processing {row_count} rows, {len(col_names)} columns")
    
    # === MEMORY OPTIMIZATION 4: Detect duplicates efficiently ===
    # Use GROUP BY instead of window functions to save memory
    try:
        duplicate_count_result = con.execute("""
            SELECT SUM(row_counts) - COUNT(*) as duplicates
            FROM (
                SELECT COUNT(*) as row_counts FROM data
                GROUP BY *
            )
        """).fetchone()
        duplicate_count = duplicate_count_result[0] if duplicate_count_result[0] is not None else 0
    except:
        print(f"[PROFILER] Duplicate detection skipped (large dataset)")
        duplicate_count = 0
    
    profile = {
        "structure": "tabular",
        "columns": {},
        "quality_issues": [],
        "recommended_mode": "minimal",
        "row_count": row_count,
        "duplicate_rows": duplicate_count
    }
    
    if duplicate_count > 0:
        profile["quality_issues"].append({
            "type": "duplicate_rows",
            "severity": "medium",
            "count": duplicate_count,
            "message": f"{duplicate_count} duplicate rows detected"
        })
    
    # === MEMORY OPTIMIZATION 5: Profile columns efficiently ===
    temporal_cols = []
    
    for col in col_names:
        col_profile = _profile_column(con, col, col_types[col], row_count)
        profile["columns"][col] = col_profile
        
        if col_profile["role"] == "temporal":
            temporal_cols.append(col)
        
        if col_profile["missing_pct"] > 20:
            profile["quality_issues"].append({
                "type": "high_missing_rate",
                "severity": "high" if col_profile["missing_pct"] > 50 else "medium",
                "column": col,
                "missing_pct": col_profile["missing_pct"],
                "message": f"{col}: {col_profile['missing_pct']:.1f}% missing values"
            })
        
        if col_profile["has_outliers"]:
            profile["quality_issues"].append({
                "type": "outliers_detected",
                "severity": "low",
                "column": col,
                "outlier_count": col_profile["outlier_count"],
                "message": f"{col}: {col_profile['outlier_count']} potential outliers"
            })
    
    # Detect structure type
    if len(temporal_cols) > 0:
        time_col = temporal_cols[0]
        try:
            gaps = con.execute(f"""
                SELECT COUNT(*) as gaps
                FROM (
                    SELECT 
                        "{time_col}",
                        LAG("{time_col}") OVER (ORDER BY "{time_col}") as prev_time
                    FROM data
                )
                WHERE prev_time IS NOT NULL
                AND "{time_col}" - prev_time > INTERVAL '2 days'
            """).fetchone()[0]
            
            if gaps < row_count * 0.1:  # Less than 10% gaps
                profile["structure"] = "time_series"
        except:
            pass
    
    # Check for transactional patterns (high cardinality IDs + timestamps)
    high_card_cols = [col for col, meta in profile["columns"].items() 
                      if meta["cardinality"] == "high"]
    if len(high_card_cols) >= 2 and len(temporal_cols) > 0:
        profile["structure"] = "transactional"
    
    # Recommend cleaning mode
    severe_issues = sum(1 for issue in profile["quality_issues"] 
                       if issue["severity"] == "high")
    total_issues = len(profile["quality_issues"])
    
    if severe_issues >= 3 or total_issues >= 5:
        profile["recommended_mode"] = "aggressive"
    elif profile["structure"] == "time_series":
        profile["recommended_mode"] = "visualization"
    else:
        profile["recommended_mode"] = "minimal"
    
    con.close()
    return profile


def _profile_column(con: duckdb.DuckDBPyConnection, col: str, dtype: str, 
                   total_rows: int) -> Dict[str, Any]:
    """
    Profile a single column efficiently.
    OPTIMIZED: Combines multiple queries into single pass where possible.
    """
    
    # === MEMORY OPTIMIZATION: Single query for basic stats ===
    try:
        stats_result = con.execute(f"""
            SELECT 
                COUNT(*) FILTER (WHERE "{col}" IS NULL) as missing_count,
                COUNT(DISTINCT "{col}") as unique_count
            FROM data
        """).fetchone()
        
        missing_count = stats_result[0]
        unique_count = stats_result[1]
    except:
        missing_count = 0
        unique_count = 0
    
    # Sample values
    try:
        samples = con.execute(f"""
            SELECT "{col}"
            FROM data
            WHERE "{col}" IS NOT NULL 
            LIMIT 3
        """).fetchall()
        sample_values = [str(s[0])[:100] for s in samples]
    except:
        sample_values = []
    
    col_info = {
        "role": "categorical",
        "dtype": _normalize_dtype(dtype),
        "missing_count": missing_count,
        "missing_pct": (missing_count / total_rows * 100) if total_rows > 0 else 0,
        "unique_count": unique_count,
        "cardinality": _classify_cardinality(unique_count, total_rows),
        "has_outliers": False,
        "outlier_count": 0,
        "sample_values": sample_values,
        "stats": {}
    }
    
    # Detect role
    col_lower = col.lower()
    if "date" in col_lower or "time" in col_lower or "timestamp" in col_lower:
        col_info["role"] = "temporal"
    elif dtype.upper().startswith("TIMESTAMP") or dtype.upper().startswith("DATE"):
        col_info["role"] = "temporal"
    elif col_info["cardinality"] == "high":
        if "id" in col_lower or "key" in col_lower or "code" in col_lower:
            col_info["role"] = "identifier"
        elif col_info["dtype"] == "text":
            col_info["role"] = "identifier"
    elif col_info["dtype"] == "numeric":
        measure_keywords = ["sales", "revenue", "profit", "amount", "quantity", 
                           "count", "total", "price", "cost", "value"]
        if any(kw in col_lower for kw in measure_keywords) or col_info["cardinality"] in ["medium", "high"]:
            col_info["role"] = "measure"
    
    # === MEMORY OPTIMIZATION: Numeric stats in single query ===
    if col_info["dtype"] == "numeric":
        try:
            # Combine all numeric statistics in one query
            stats = con.execute(f"""
                SELECT 
                    MIN("{col}") as min_val,
                    MAX("{col}") as max_val,
                    AVG("{col}") as mean,
                    MEDIAN("{col}") as median,
                    STDDEV("{col}") as std,
                    PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY "{col}") as q1,
                    PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY "{col}") as q3
                FROM data
                WHERE "{col}" IS NOT NULL
            """).fetchone()
            
            if stats and stats[0] is not None:
                col_info["stats"] = {
                    "min": float(stats[0]),
                    "max": float(stats[1]),
                    "mean": float(stats[2]) if stats[2] is not None else None,
                    "median": float(stats[3]) if stats[3] is not None else None,
                    "std": float(stats[4]) if stats[4] is not None else None
                }
                
                # Detect outliers using IQR
                if stats[5] is not None and stats[6] is not None:
                    q1, q3 = float(stats[5]), float(stats[6])
                    iqr = q3 - q1
                    
                    if iqr > 0:
                        lower_bound = q1 - 1.5 * iqr
                        upper_bound = q3 + 1.5 * iqr
                        
                        outlier_count = con.execute(f"""
                            SELECT COUNT(*) FROM data
                            WHERE "{col}" IS NOT NULL
                            AND ("{col}" < {lower_bound} OR "{col}" > {upper_bound})
                        """).fetchone()[0]
                        
                        if outlier_count > 0:
                            col_info["has_outliers"] = True
                            col_info["outlier_count"] = outlier_count
                            col_info["stats"]["outlier_bounds"] = {
                                "lower": float(lower_bound),
                                "upper": float(upper_bound)
                            }
        except Exception as e:
            print(f"[PROFILER] Warning: Stats for {col}: {e}")
    
    return col_info
    samples = con.execute(f"""
        SELECT DISTINCT "{col}" FROM data 
        WHERE "{col}" IS NOT NULL 
        LIMIT 3
    """).fetchall()
    sample_values = [str(s[0])[:100] for s in samples]  # Truncate long strings at 100 chars
    
    col_info = {
        "role": "categorical",  # Default
        "dtype": _normalize_dtype(dtype),
        "missing_count": missing_count,
        "missing_pct": (missing_count / total_rows * 100) if total_rows > 0 else 0,
        "unique_count": unique_count,
        "cardinality": _classify_cardinality(unique_count, total_rows),
        "has_outliers": False,
        "outlier_count": 0,
        "sample_values": sample_values,
        "stats": {}
    }
    
    # Detect role based on semantics
    col_lower = col.lower()
    
    # Temporal detection
    if "date" in col_lower or "time" in col_lower or "timestamp" in col_lower:
        col_info["role"] = "temporal"
    elif dtype.upper().startswith("TIMESTAMP") or dtype.upper().startswith("DATE"):
        col_info["role"] = "temporal"
    
    # Identifier detection (high cardinality + not numeric aggregate)
    elif col_info["cardinality"] == "high":
        if "id" in col_lower or "key" in col_lower or "code" in col_lower:
            col_info["role"] = "identifier"
        elif col_info["dtype"] == "text":
            col_info["role"] = "identifier"
    
    # Measure detection (numeric + low cardinality relative to rows)
    elif col_info["dtype"] == "numeric":
        # Check for common measure keywords
        measure_keywords = ["sales", "revenue", "profit", "amount", "quantity", 
                           "count", "total", "price", "cost", "value"]
        if any(kw in col_lower for kw in measure_keywords):
            col_info["role"] = "measure"
        # Or if numeric with reasonable cardinality
        elif col_info["cardinality"] in ["medium", "high"]:
            col_info["role"] = "measure"
    
    # Numeric statistics and outliers
    if col_info["dtype"] == "numeric":
        try:
            stats = con.execute(f"""
                SELECT 
                    MIN("{col}") as min_val,
                    MAX("{col}") as max_val,
                    AVG("{col}") as mean,
                    MEDIAN("{col}") as median,
                    STDDEV("{col}") as std
                FROM data
                WHERE "{col}" IS NOT NULL
            """).fetchone()
            
            if stats:
                col_info["stats"] = {
                    "min": float(stats[0]) if stats[0] is not None else None,
                    "max": float(stats[1]) if stats[1] is not None else None,
                    "mean": float(stats[2]) if stats[2] is not None else None,
                    "median": float(stats[3]) if stats[3] is not None else None,
                    "std": float(stats[4]) if stats[4] is not None else None
                }
                
                # Detect outliers using IQR method
                if stats[3] is not None and stats[4] is not None:
                    q1 = con.execute(f"""
                        SELECT PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY "{col}")
                        FROM data WHERE "{col}" IS NOT NULL
                    """).fetchone()[0]
                    
                    q3 = con.execute(f"""
                        SELECT PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY "{col}")
                        FROM data WHERE "{col}" IS NOT NULL
                    """).fetchone()[0]
                    
                    if q1 is not None and q3 is not None:
                        iqr = q3 - q1
                        lower_bound = q1 - 1.5 * iqr
                        upper_bound = q3 + 1.5 * iqr
                        
                        outlier_count = con.execute(f"""
                            SELECT COUNT(*) FROM data
                            WHERE "{col}" IS NOT NULL
                            AND ("{col}" < {lower_bound} OR "{col}" > {upper_bound})
                        """).fetchone()[0]
                        
                        if outlier_count > 0:
                            col_info["has_outliers"] = True
                            col_info["outlier_count"] = outlier_count
                            col_info["stats"]["outlier_bounds"] = {
                                "lower": float(lower_bound),
                                "upper": float(upper_bound)
                            }
        except Exception as e:
            print(f"[PROFILER] Warning: Could not compute stats for {col}: {e}")
    
    return col_info


def _normalize_dtype(dtype: str) -> str:
    """Normalize DuckDB types to simple categories."""
    dtype_upper = dtype.upper()
    
    if any(t in dtype_upper for t in ["INT", "BIGINT", "FLOAT", "DOUBLE", "DECIMAL", "NUMERIC"]):
        return "numeric"
    elif any(t in dtype_upper for t in ["VARCHAR", "TEXT", "STRING"]):
        return "text"
    elif any(t in dtype_upper for t in ["DATE", "TIMESTAMP", "TIME"]):
        return "date"
    elif "BOOL" in dtype_upper:
        return "boolean"
    else:
        return "text"  # Default


def _classify_cardinality(unique_count: int, total_rows: int) -> str:
    """Classify cardinality as low/medium/high."""
    if total_rows == 0:
        return "low"
    
    ratio = unique_count / total_rows
    
    if ratio > 0.9:
        return "high"
    elif ratio > 0.1:
        return "medium"
    else:
        return "low"
