# utils/database_utilities.py
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
from typing import Dict, List, Optional, Any
import json

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


# ============================================================================
# PostgreSQL Connection Manager for User Databases
# ============================================================================

class PostgreSQLConnectionManager:
    """Manages connections to user-provided PostgreSQL databases."""
    
    @staticmethod
    def test_connection(host: str, port: int, database: str, username: str, password: str) -> Dict[str, Any]:
        """Test if database credentials are valid."""
        try:
            conn = psycopg2.connect(
                host=host,
                port=port,
                database=database,
                user=username,
                password=password,
                connect_timeout=10
            )
            conn.close()
            return {"success": True, "message": "Connection successful"}
        except psycopg2.OperationalError as e:
            return {"success": False, "message": f"Connection failed: {str(e)}"}
        except Exception as e:
            return {"success": False, "message": f"Error: {str(e)}"}
    
    @staticmethod
    @contextmanager
    def get_user_db_connection(host: str, port: int, database: str, username: str, password: str):
        """Context manager for user database connections."""
        conn = None
        try:
            conn = psycopg2.connect(
                host=host,
                port=port,
                database=database,
                user=username,
                password=password,
                connect_timeout=30
            )
            yield conn
        finally:
            if conn:
                conn.close()
    
    @staticmethod
    def fetch_database_schema(host: str, port: int, database: str, username: str, password: str) -> Dict[str, Any]:
        """Fetch schema information from user's PostgreSQL database."""
        try:
            with PostgreSQLConnectionManager.get_user_db_connection(host, port, database, username, password) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    # Get all tables and their columns
                    cur.execute("""
                        SELECT 
                            t.table_name,
                            array_agg(
                                json_build_object(
                                    'column_name', c.column_name,
                                    'data_type', c.data_type,
                                    'is_nullable', c.is_nullable,
                                    'column_default', c.column_default
                                ) ORDER BY c.ordinal_position
                            ) as columns
                        FROM information_schema.tables t
                        JOIN information_schema.columns c 
                            ON t.table_name = c.table_name 
                            AND t.table_schema = c.table_schema
                        WHERE t.table_schema = 'public' 
                            AND t.table_type = 'BASE TABLE'
                        GROUP BY t.table_name
                        ORDER BY t.table_name;
                    """)
                    
                    tables = cur.fetchall()
                    
                    # Get foreign key relationships
                    cur.execute("""
                        SELECT
                            tc.table_name,
                            kcu.column_name,
                            ccu.table_name AS foreign_table_name,
                            ccu.column_name AS foreign_column_name
                        FROM information_schema.table_constraints AS tc
                        JOIN information_schema.key_column_usage AS kcu
                            ON tc.constraint_name = kcu.constraint_name
                            AND tc.table_schema = kcu.table_schema
                        JOIN information_schema.constraint_column_usage AS ccu
                            ON ccu.constraint_name = tc.constraint_name
                            AND ccu.table_schema = tc.table_schema
                        WHERE tc.constraint_type = 'FOREIGN KEY'
                            AND tc.table_schema = 'public';
                    """)
                    
                    relationships = cur.fetchall()
                    
                    # Get row counts for each table
                    table_stats = {}
                    for table in tables:
                        table_name = table['table_name']
                        try:
                            cur.execute(f"SELECT COUNT(*) as count FROM {table_name};")
                            count_result = cur.fetchone()
                            table_stats[table_name] = count_result['count']
                        except:
                            table_stats[table_name] = 0
                    
                    schema_data = {
                        "database_name": database,
                        "tables": {
                            table['table_name']: {
                                "columns": table['columns'],
                                "row_count": table_stats.get(table['table_name'], 0)
                            }
                            for table in tables
                        },
                        "relationships": [dict(row) for row in relationships]
                    }
                    
                    return {"success": True, "schema": schema_data}
                    
        except Exception as e:
            return {"success": False, "message": f"Schema fetch failed: {str(e)}"}
    
    @staticmethod
    def execute_query(host: str, port: int, database: str, username: str, password: str, query: str) -> Dict[str, Any]:
        """Execute a query on user's PostgreSQL database."""
        try:
            with PostgreSQLConnectionManager.get_user_db_connection(host, port, database, username, password) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(query)
                    
                    # Check if query returns results
                    if cur.description:
                        columns = [desc[0] for desc in cur.description]
                        rows = cur.fetchall()
                        results = [dict(row) for row in rows]
                        
                        return {
                            "success": True,
                            "columns": columns,
                            "rows": results,
                            "row_count": len(results)
                        }
                    else:
                        # For non-SELECT queries (INSERT, UPDATE, DELETE)
                        conn.commit()
                        return {
                            "success": True,
                            "message": "Query executed successfully",
                            "rows_affected": cur.rowcount
                        }
                        
        except psycopg2.Error as e:
            return {"success": False, "message": f"Query execution failed: {str(e)}"}
        except Exception as e:
            return {"success": False, "message": f"Error: {str(e)}"}