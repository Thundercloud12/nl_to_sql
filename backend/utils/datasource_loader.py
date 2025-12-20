# datasource_loader.py
import os
import json
from typing import Dict, Any
import urllib.request
import requests
from contextlib import contextmanager
import psycopg2
from psycopg2.extras import RealDictCursor
import asyncio
from utils.database_utilities import get_db_connection, db_connection, db_cursor

def get_db_connection():
    return psycopg2.connect(os.getenv("DATABASE_URL"))

@contextmanager
def db_connection():
    """Context manager for database connections."""
    conn = None
    try:
        conn = get_db_connection()
        yield conn
    finally:
        if conn:
            conn.close()

@contextmanager
def db_cursor(commit=False):
    """Context manager for database cursors with optional commit."""
    with db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            try:
                yield cur
                if commit:
                    conn.commit()
            except Exception:
                conn.rollback()
                raise

async def download_from_cloudinary(url: str, output_path: str) -> str:
    """
    Download file from Supabase Storage public URL.

    Args:
        url: Supabase public URL of the file
        output_path: Local path to save the file

    Returns:
        Path to downloaded file

    Raises:
        Exception: If download fails
    """
    try:

        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        r = requests.get(url, timeout=30)
        r.raise_for_status()

        with open(output_path, "wb") as f:
            f.write(r.content)

        print(f"[DATASOURCE] ✓ Downloaded → {output_path}")
        return output_path

    except Exception as e:
        print(f"[DATASOURCE] ✗ Error downloading from Supabase: {str(e)}")
        raise


def load_datasource_files(data_source_id: str, raw_metadata: Dict[str, Any], schema_graph: Dict[str, Any]) -> Dict[str, str]:
    """
    Write raw metadata and schema graph to JSON files in per-datasource folder.
    
    Args:
        data_source_id: ID of the datasource (for folder isolation)
        raw_metadata: Raw metadata dict from DataSource
        schema_graph: Schema graph dict from DataSource
    
    Returns:
        Dict with paths to created files
    """
    try:
        # Write to datasource-specific folder
        datasource_dir = os.path.join("uploaded_files", f"datasource_{data_source_id}")
        os.makedirs(datasource_dir, exist_ok=True)
        
        # Write raw metadata
        metadata_path = os.path.join(datasource_dir, "raw_metadata.json")
        with open(metadata_path, "w") as f:
            json.dump(raw_metadata, f, indent=4)
        print(f"[DATASOURCE] ✓ Wrote raw_metadata.json to {metadata_path}")
        
        # Write schema graph
        graph_path = os.path.join(datasource_dir, "schema_graph.json")
        with open(graph_path, "w") as f:
            json.dump(schema_graph, f, indent=4)
        print(f"[DATASOURCE] ✓ Wrote schema_graph.json to {graph_path}")
        
        return {
            "metadata_path": metadata_path,
            "graph_path": graph_path
        }
    
    except Exception as e:
        print(f"[DATASOURCE] ✗ Error writing files: {str(e)}")
        raise


def ensure_datasource_files(data_source):
    """
    Ensure datasource files exist, rehydrate if missing.
    Returns the parquet path for use in queries.
    """
    datasource_dir = f"uploaded_files/datasource_{data_source['id']}"
    parquet_path = os.path.join(datasource_dir, "data.parquet")
    metadata_path = os.path.join(datasource_dir, "raw_metadata.json")
    graph_path = os.path.join(datasource_dir, "schema_graph.json")

    if not all(map(os.path.exists, [parquet_path, metadata_path, graph_path])):
        print("[CACHE MISS] Rehydrating datasource files...")
        os.makedirs(datasource_dir, exist_ok=True)

        # Re-download parquet
        asyncio.run(download_from_cloudinary(
            data_source["cloudinaryUrl"],
            parquet_path
        ))

        # Re-write metadata & graph
        load_datasource_files(
            data_source["id"],
            data_source["rawMetadata"],
            data_source["schemaGraph"]
        )

    return parquet_path


async def load_chat(data_source_id: str, user_id: str) -> Dict[str, Any]:
    try:
        data_source = None
        with db_cursor() as cur:
            cur.execute(
                "SELECT * FROM \"DataSource\" WHERE id = %s AND \"userId\" = %s",
                (data_source_id, user_id)
            )
            data_source_row = cur.fetchone()
        
        if not data_source_row:
            raise Exception("DataSource not found or unauthorized")
        
        data_source = dict(data_source_row)
        
        # Step 2: Check for existing session (latest for this user + data source)
        existing_session = None
        with db_cursor() as cur:
            cur.execute(
                "SELECT * FROM \"Session\" WHERE \"userId\" = %s AND \"dataSourceId\" = %s ORDER BY \"createdAt\" DESC LIMIT 1",
                (user_id, data_source_id)
            )
            existing_session = cur.fetchone()

        # Step 3: Check for existing conversation
        existing_conversation = None
        with db_cursor() as cur:
            cur.execute(
                "SELECT * FROM \"Conversation\" WHERE \"userId\" = %s AND \"dataSourceId\" = %s ORDER BY \"createdAt\" DESC LIMIT 1",
                (user_id, data_source_id)
            )
            existing_conversation = cur.fetchone()
        
        # Step 4: Download Parquet from Cloudinary to datasource-specific folder
        datasource_dir = os.path.join("uploaded_files", f"datasource_{data_source_id}")
        os.makedirs(datasource_dir, exist_ok=True)
        parquet_path = os.path.join(datasource_dir, "data.parquet")
        await download_from_cloudinary(
            data_source["cloudinaryUrl"],
            parquet_path
        )
        
        # Step 5: Write metadata and schema graph JSON files to datasource-specific folder
        file_paths = load_datasource_files(
            data_source_id,
            data_source["rawMetadata"],
            data_source["schemaGraph"]
        )
        
        return {
            "data_source": data_source,
            "existing_session": existing_session,
            "existing_conversation": existing_conversation,
            "parquet_path": parquet_path,
            "file_paths": file_paths
        }
    
    except Exception as e:
        print(f"[LOAD_CHAT] ✗ Error: {str(e)}")
        raise
