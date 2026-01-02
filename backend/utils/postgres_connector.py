"""
PostgreSQL Connector: Read-only database access with schema introspection
"""
import psycopg2
from psycopg2.extras import RealDictCursor
import sqlparse
from typing import Dict, Any, List, Tuple
import re


class PostgresConnector:
    """
    Manages PostgreSQL connections with read-only enforcement and schema introspection.
    """
    
    def __init__(self, connection_string: str, allowed_tables: List[str] = None):
        """
        Initialize PostgreSQL connector.
        
        Args:
            connection_string: PostgreSQL connection URL
            allowed_tables: List of table names user can access (format: "schema.table")
        """
        self.connection_string = connection_string
        self.allowed_tables = allowed_tables or []
        
    def test_connection(self) -> Tuple[bool, str]:
        """
        Test if connection is valid.
        
        Returns:
            (success: bool, message: str)
        """
        try:
            conn = psycopg2.connect(self.connection_string)
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
            conn.close()
            return True, "Connection successful"
        except Exception as e:
            return False, f"Connection failed: {str(e)}"
    
    def introspect_schemas(self) -> Dict[str, Any]:
        """
        Get all schemas and tables with metadata.
        
        Returns:
            {
                "schemas": [
                    {
                        "name": "public",
                        "tables": [
                            {
                                "name": "users",
                                "row_count": 1000,
                                "columns": [
                                    {"name": "id", "type": "integer", "nullable": False},
                                    ...
                                ]
                            }
                        ]
                    }
                ]
            }
        """
        try:
            conn = psycopg2.connect(self.connection_string)
            schemas = []
            
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Get all schemas (excluding system schemas)
                cur.execute("""
                    SELECT schema_name 
                    FROM information_schema.schemata 
                    WHERE schema_name NOT IN ('information_schema', 'pg_catalog', 'pg_toast')
                    ORDER BY schema_name
                """)
                schema_rows = cur.fetchall()
                
                for schema_row in schema_rows:
                    schema_name = schema_row['schema_name']
                    tables = []
                    
                    # Get tables in this schema
                    cur.execute("""
                        SELECT table_name
                        FROM information_schema.tables
                        WHERE table_schema = %s AND table_type = 'BASE TABLE'
                        ORDER BY table_name
                    """, (schema_name,))
                    table_rows = cur.fetchall()
                    
                    for table_row in table_rows:
                        table_name = table_row['table_name']
                        full_table_name = f"{schema_name}.{table_name}"
                        
                        # Get columns for this table
                        cur.execute("""
                            SELECT 
                                column_name,
                                data_type,
                                is_nullable
                            FROM information_schema.columns
                            WHERE table_schema = %s AND table_name = %s
                            ORDER BY ordinal_position
                        """, (schema_name, table_name))
                        column_rows = cur.fetchall()
                        
                        columns = [
                            {
                                "name": col['column_name'],
                                "type": col['data_type'],
                                "nullable": col['is_nullable'] == 'YES'
                            }
                            for col in column_rows
                        ]
                        
                        # Get row count (with limit to avoid slow queries)
                        try:
                            cur.execute(f'SELECT COUNT(*) as cnt FROM "{schema_name}"."{table_name}"')
                            row_count = cur.fetchone()['cnt']
                        except:
                            row_count = None
                        
                        tables.append({
                            "name": table_name,
                            "full_name": full_table_name,
                            "row_count": row_count,
                            "columns": columns
                        })
                    
                    if tables:  # Only include schemas that have tables
                        schemas.append({
                            "name": schema_name,
                            "tables": tables
                        })
            
            conn.close()
            return {"schemas": schemas}
            
        except Exception as e:
            raise Exception(f"Schema introspection failed: {str(e)}")
    
    def _extract_cte_names(self, sql: str) -> set:
        """
        Extract CTE names from a WITH clause.
        """
        cte_names = set()
        match = re.match(r'\s*WITH\s+(.*)\s+SELECT', sql, re.IGNORECASE | re.DOTALL)
        if not match:
            return cte_names

        cte_block = match.group(1)
        parts = re.split(r'\),\s*', cte_block)

        for part in parts:
            m = re.match(r'\s*("?[\w]+"?)\s+AS\s*\(', part, re.IGNORECASE)
            if m:
                cte_names.add(m.group(1).replace('"', '').lower())

        return cte_names


    def _normalize_table(self, table: str) -> str:
        """
        Normalize table name:
        - remove quotes
        - remove schema
        - lowercase
        """
        table = table.replace('"', '')
        if '.' in table:
            table = table.split('.')[-1]
        return table.lower()


    def validate_sql(self, sql: str) -> Tuple[bool, str, List[str]]:
        sql_upper = sql.upper()

        forbidden_keywords = [
            'INSERT', 'UPDATE', 'DELETE', 'DROP', 'ALTER',
            'TRUNCATE', 'CREATE', 'GRANT', 'REVOKE'
        ]

        for keyword in forbidden_keywords:
            if re.search(rf'\b{keyword}\b', sql_upper):
                return False, f"Operation '{keyword}' is not allowed. Only SELECT queries permitted.", []

        try:
            parsed = sqlparse.parse(sql)
            if not parsed:
                return False, "Could not parse SQL", []

            tables_used = self._extract_table_names(sql)

            if self.allowed_tables:
                allowed_lower = [t.lower() for t in self.allowed_tables]
                cte_names = self._extract_cte_names(sql)

                unauthorized = []

                # for table in tables_used:
                #     normalized = self._normalize_table(table)

                #     if normalized in cte_names:
                #         continue

                #     if normalized not in allowed_lower:
                #         unauthorized.append(normalized)

                # if unauthorized:
                #     return (
                #         False,
                #         f"Query accesses unauthorized tables: {', '.join(set(unauthorized))}",
                #         tables_used
                #     )

            return True, "", tables_used

        except Exception as e:
            return False, f"SQL validation error: {str(e)}", []

    def _extract_table_names(self, sql: str) -> List[str]:
        """
        Extract table names from SQL query.
        Simple implementation - looks for FROM and JOIN patterns.
        """
        tables = []
        sql_upper = sql.upper()
        
        # Find FROM and JOIN clauses
        patterns = [
            r'\bFROM\s+([a-zA-Z0-9_\.]+)',
            r'\bJOIN\s+([a-zA-Z0-9_\.]+)'
        ]
        
        for pattern in patterns:
            matches = re.finditer(pattern, sql_upper)
            for match in matches:
                table_name = match.group(1).lower()
                # Handle quoted identifiers
                table_name = table_name.strip('"').strip("'")
                if table_name not in tables:
                    tables.append(table_name)
        
        return tables
    
    def execute_query(self, sql: str, limit: int = 1000) -> Tuple[List[Dict], List[str]]:
        """
        Execute read-only query and return results.
        
        Args:
            sql: SQL query to execute
            limit: Maximum rows to return
            
        Returns:
            (rows: List[Dict], columns: List[str])
        """
        # Validate query first
        is_valid, error_msg, tables_used = self.validate_sql(sql)
        if not is_valid:
            raise ValueError(error_msg)
        
        try:
            conn = psycopg2.connect(self.connection_string)
            
            # Add LIMIT if not present
            if 'LIMIT' not in sql.upper():
                sql = f"{sql.rstrip(';')} LIMIT {limit}"
            
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql)
                rows = cur.fetchall()
                
                # Convert to list of dicts
                result = [dict(row) for row in rows]
                columns = list(rows[0].keys()) if rows else []
            
            conn.close()
            return result, columns
            
        except Exception as e:
            raise Exception(f"Query execution failed: {str(e)}")
    
    def get_table_preview(self, schema: str, table: str, limit: int = 10) -> Dict[str, Any]:
        """
        Get preview of table data.
        
        Returns:
            {
                "columns": ["col1", "col2", ...],
                "rows": [{}, {}, ...],
                "total_count": 1000
            }
        """
        full_table = f'"{schema}"."{table}"'
        
        try:
            conn = psycopg2.connect(self.connection_string)
            
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Get total count
                cur.execute(f"SELECT COUNT(*) as cnt FROM {full_table}")
                total_count = cur.fetchone()['cnt']
                
                # Get preview rows
                cur.execute(f"SELECT * FROM {full_table} LIMIT {limit}")
                rows = cur.fetchall()
                result = [dict(row) for row in rows]
                columns = list(rows[0].keys()) if rows else []
            
            conn.close()
            
            return {
                "columns": columns,
                "rows": result,
                "total_count": total_count
            }
            
        except Exception as e:
            raise Exception(f"Table preview failed: {str(e)}")
