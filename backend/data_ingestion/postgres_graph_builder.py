"""
PostgreSQL-specific graph builder - uses actual database foreign key relationships.
Generates metadata and schema graph for PostgreSQL databases.
"""
from __future__ import annotations
import json
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Dict, Any, List, Tuple
from utils.llm_utils import rate_limited_llm_call
from utils.postgres_connector import PostgresConnector


def generate_table_summary(table_name: str, columns: list, samples: list) -> str:
    """
    Use LLM to generate a lightweight summary of the table.
    Identical to file-based version.
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


def extract_foreign_keys(connection_string: str, allowed_tables: List[str]) -> List[Dict[str, Any]]:
    """
    Extract actual foreign key relationships from PostgreSQL database.
    
    Returns:
        [
            {
                "source_table": "public.orders",
                "source_column": "user_id",
                "target_table": "public.users",
                "target_column": "id",
                "constraint_name": "fk_orders_users"
            },
            ...
        ]
    """
    try:
        conn = psycopg2.connect(connection_string)
        foreign_keys = []
        
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Query to get all foreign key constraints
            cur.execute("""
                SELECT
                    tc.table_schema || '.' || tc.table_name AS source_table,
                    kcu.column_name AS source_column,
                    ccu.table_schema || '.' || ccu.table_name AS target_table,
                    ccu.column_name AS target_column,
                    tc.constraint_name
                FROM information_schema.table_constraints AS tc
                JOIN information_schema.key_column_usage AS kcu
                    ON tc.constraint_name = kcu.constraint_name
                    AND tc.table_schema = kcu.table_schema
                JOIN information_schema.constraint_column_usage AS ccu
                    ON ccu.constraint_name = tc.constraint_name
                    AND ccu.table_schema = tc.table_schema
                WHERE tc.constraint_type = 'FOREIGN KEY'
                ORDER BY tc.table_schema, tc.table_name
            """)
            
            rows = cur.fetchall()
            allowed_set = set(allowed_tables)
            
            for row in rows:
                source = row['source_table']
                target = row['target_table']
                
                # Only include relationships where both tables are in allowed list
                if source in allowed_set and target in allowed_set:
                    foreign_keys.append({
                        "source_table": source,
                        "source_column": row['source_column'],
                        "target_table": target,
                        "target_column": row['target_column'],
                        "constraint_name": row['constraint_name']
                    })
        
        conn.close()
        print(f"[POSTGRES-GRAPH] ✓ Extracted {len(foreign_keys)} foreign key relationships")
        return foreign_keys
        
    except Exception as e:
        print(f"[POSTGRES-GRAPH] ⚠️ Could not extract foreign keys: {e}")
        return []


def json_sanitize(obj):
    """Sanitize objects for JSON serialization"""
    import datetime
    from decimal import Decimal
    import uuid
    
    if isinstance(obj, dict):
        return {k: json_sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [json_sanitize(v) for v in obj]
    if isinstance(obj, datetime.timedelta):
        return str(obj)  # Convert timedelta to string (e.g., "1 day, 2:30:00")
    if isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)  # Convert Decimal to float
    if isinstance(obj, uuid.UUID):
        return str(obj)  # Convert UUID to string
    if isinstance(obj, bytes):
        return obj.decode('utf-8', errors='replace')  # Convert bytes to string
    if isinstance(obj, float):
        import math
        if math.isnan(obj) or math.isinf(obj):
            return None
    return obj


def build_metadata_from_postgres(
    connector: PostgresConnector,
    allowed_tables: List[str]
) -> dict:
    """
    Build metadata from PostgreSQL database.
    
    Args:
        connector: PostgresConnector instance
        allowed_tables: List of allowed table names in "schema.table" format
    
    Returns:
        {
            "tables": {
                "T1": {
                    "original_name": "schema.table",
                    "columns": ["col1", "col2", ...],
                    "canonical_types": {"col1": "VARCHAR", "col2": "INTEGER", ...},
                    "samples": [{row1}, {row2}, {row3}],
                    "summary": "Generated table summary"
                },
                ...
            }
        }
    """
    initial_schema: dict = {"tables": {}}
    table_counter = 1
    
    # Introspect all schemas
    introspection_result = connector.introspect_schemas()
    schemas_info = introspection_result.get("schemas", [])
    
    # Build allowed tables set for quick lookup
    allowed_set = set(allowed_tables)
    
    for schema_info in schemas_info:
        schema_name = schema_info["name"]
        
        for table_info in schema_info["tables"]:
            full_table_name = table_info["full_name"]
            
            # Skip if not in allowed list
            if full_table_name not in allowed_set:
                continue
            
            short_name = f"T{table_counter}"
            table_counter += 1
            
            # Get column info
            columns = [col["name"] for col in table_info["columns"]]
            
            # Map PostgreSQL types to canonical types (similar to DuckDB mapping)
            type_mapping = {
                "character varying": "VARCHAR",
                "varchar": "VARCHAR",
                "text": "VARCHAR",
                "character": "VARCHAR",
                "integer": "INTEGER",
                "bigint": "INTEGER",
                "smallint": "INTEGER",
                "numeric": "FLOAT",
                "decimal": "FLOAT",
                "real": "FLOAT",
                "double precision": "FLOAT",
                "boolean": "BOOLEAN",
                "timestamp": "TIMESTAMP",
                "timestamp without time zone": "TIMESTAMP",
                "timestamp with time zone": "TIMESTAMP",
                "date": "TIMESTAMP",
            }
            
            canonical_types = {}
            for col in table_info["columns"]:
                pg_type = col["type"].lower()
                canonical_types[col["name"]] = type_mapping.get(pg_type, "VARCHAR")
            
            # Get sample data (limit 3 rows)
            try:
                samples, _ = connector.execute_query(
                    f'SELECT * FROM "{schema_name}"."{table_info["name"]}" LIMIT 3',
                    limit=3
                )
            except Exception as e:
                print(f"[POSTGRES-GRAPH] ⚠️ Could not fetch samples for {full_table_name}: {e}")
                samples = []
            
            # Generate summary
            summary = generate_table_summary(full_table_name, columns, samples)
            
            initial_schema["tables"][short_name] = json_sanitize({
                "original_name": full_table_name,
                "columns": columns,
                "canonical_types": canonical_types,
                "samples": samples[:3],  # Ensure max 3 samples
                "summary": summary,
            })
            
            print(f"[POSTGRES-GRAPH] ✓ {short_name}: {full_table_name} ({len(columns)} cols)")
    
    return initial_schema


def extract_tiny_metadata(initial_schema: dict) -> dict:
    """
    Extract simplified metadata from initial schema.
    Identical to file-based version.
    """
    tiny_metadata = {}
    for short_name, table_info in initial_schema["tables"].items():
        tiny_metadata[short_name] = {
            "table_name": table_info["original_name"],
            "number_of_columns": len(table_info["columns"]),
            "column_names": table_info["columns"],
            "inferred_entity_summary": table_info["summary"]
        }
    return tiny_metadata


def call_llm_for_relationships(
    tiny_metadata: dict, 
    user_explanation: str,
    foreign_keys: List[Dict[str, Any]],
    table_name_mapping: Dict[str, str]
) -> dict:
    """
    Infer relationships via LLM with ACTUAL foreign keys as ultimate truth.
    
    Args:
        tiny_metadata: Simplified table metadata
        user_explanation: User's data explanation
        foreign_keys: Extracted FK relationships from database
        table_name_mapping: Map of full_name -> short_name (e.g., "public.users" -> "T1")
    """
    metadata_text = "Tiny Metadata:\n"
    for short_name, info in tiny_metadata.items():
        metadata_text += f"- {short_name}: {info['table_name']} ({info['number_of_columns']} columns: {', '.join(info['column_names'])})\n  Summary: {info['inferred_entity_summary']}\n"
    
    # Build FK relationships text with short names
    fk_text = "\n🔒 ULTIMATE TRUTH - Database Foreign Key Relationships (MUST BE INCLUDED):\n"
    if foreign_keys:
        for fk in foreign_keys:
            source_short = table_name_mapping.get(fk['source_table'], fk['source_table'])
            target_short = table_name_mapping.get(fk['target_table'], fk['target_table'])
            fk_text += f"- {source_short}.{fk['source_column']} → {target_short}.{fk['target_column']} (FK: {fk['constraint_name']})\n"
    else:
        fk_text += "- No foreign key constraints found in database\n"
    
    prompt = f"""
You are analyzing a PostgreSQL database with ACTUAL foreign key constraints.

⚠️ CRITICAL INSTRUCTION:
The foreign key relationships listed below are the ULTIMATE TRUTH extracted directly from the database schema.
You MUST include ALL these relationships in your output. They are NOT suggestions - they are facts.

{fk_text}

User Explanation:
{user_explanation}

Tiny Metadata:
{metadata_text}

Your job:
1. START with the foreign key relationships above - these are MANDATORY and FACTUAL.
2. Use the user explanation as high authority for additional context.
3. Add any additional inferred relationships beyond the FK constraints.
4. Output a FINAL GRAPH in this EXACT JSON structure:

{{
  "tables": {{
    "T1": {{
      "entity_group": "string",
      "related_tables": ["T2", "T3"],  // Tables connected via FK or inference
      "foreign_keys": [  // Direct FK relationships (MUST include all from ULTIMATE TRUTH)
        {{"column": "user_id", "references_table": "T2", "references_column": "id"}}
      ],
      "inferred_relationships": [  // Additional non-FK relationships
        {{"table": "T3", "reason": "similar columns suggest relationship"}}
      ],
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
        print(f"[POSTGRES-GRAPH] ✗ LLM Error: {e}")
        return {"final_graph": {}}


def process_postgres_schema_build(
    connector: PostgresConnector,
    allowed_tables: List[str],
    user_explanation: str = "please infer yourself"
) -> dict:
    """
    Main orchestration for PostgreSQL schema building with FK extraction.
    
    Args:
        connector: PostgresConnector instance
        allowed_tables: List of allowed table names
        user_explanation: User's explanation of the data (default: "please infer yourself")
    
    Returns:
        {
            "raw_metadata": { ... },
            "schema_graph": { ... },
            "foreign_keys": [ ... ]  // Extracted FK relationships
        }
    """
    print("[POSTGRES-GRAPH] Starting PostgreSQL schema build...")
    
    try:
        # Step 1: Build metadata from PostgreSQL
        print("[POSTGRES-GRAPH] Step 1: Building metadata from PostgreSQL...")
        try:
            initial_schema = build_metadata_from_postgres(connector, allowed_tables)
            if not initial_schema.get("tables"):
                print("[POSTGRES-GRAPH] ⚠️ No tables found in metadata")
                return {
                    "raw_metadata": {"tables": {}},
                    "schema_graph": {},
                    "foreign_keys": [],
                    "error": "No tables found"
                }
            else:
                print(f"[POSTGRES-GRAPH] ✓ Generated metadata for {len(initial_schema['tables'])} table(s)")
        except Exception as meta_err:
            print(f"[POSTGRES-GRAPH] ✗ Metadata generation failed: {meta_err}")
            return {
                "raw_metadata": {"tables": {}},
                "schema_graph": {},
                "foreign_keys": [],
                "error": f"Metadata generation failed: {str(meta_err)}"
            }
        
        # Step 2: Extract foreign key relationships (ULTIMATE TRUTH)
        print("[POSTGRES-GRAPH] Step 2: Extracting foreign key relationships...")
        try:
            foreign_keys = extract_foreign_keys(connector.connection_string, allowed_tables)
        except Exception as fk_err:
            print(f"[POSTGRES-GRAPH] ⚠️ FK extraction failed: {fk_err}")
            foreign_keys = []
        
        # Step 3: Build table name mapping (full_name -> short_name)
        table_name_mapping = {}
        for short_name, table_info in initial_schema["tables"].items():
            table_name_mapping[table_info["original_name"]] = short_name
        
        # Step 4: Extract tiny metadata
        print("[POSTGRES-GRAPH] Step 3: Extracting tiny metadata...")
        try:
            tiny_metadata = extract_tiny_metadata(initial_schema)
            print(f"[POSTGRES-GRAPH] ✓ Extracted metadata for {len(tiny_metadata)} table(s)")
        except Exception as tiny_err:
            print(f"[POSTGRES-GRAPH] ⚠️ Tiny metadata extraction failed: {tiny_err}")
            tiny_metadata = {}
        
        # Step 5: Call LLM with FK relationships as ULTIMATE TRUTH
        print("[POSTGRES-GRAPH] Step 4: Inferring table relationships with FK constraints...")
        try:
            llm_response = call_llm_for_relationships(
                tiny_metadata, 
                user_explanation,
                foreign_keys,
                table_name_mapping
            )
            final_graph = llm_response.get("final_graph", {})
            print(f"[POSTGRES-GRAPH] ✓ Generated schema graph with {len(foreign_keys)} FK relationships")
        except Exception as llm_err:
            print(f"[POSTGRES-GRAPH] ⚠️ LLM relationship inference failed: {llm_err}")
            final_graph = {}
        
        # Return with all components including FK relationships
        return {
            "raw_metadata": initial_schema,
            "schema_graph": final_graph,
            "foreign_keys": foreign_keys  # Include for reference
        }
    
    except Exception as e:
        print(f"[POSTGRES-GRAPH] ✗ Unexpected error: {e}")
        return {
            "raw_metadata": {"tables": {}},
            "schema_graph": {},
            "foreign_keys": [],
            "error": f"Pipeline failed: {str(e)}"
        }
