"""
Customer-Hosted Agent Service

This is the lightweight agent service that runs on customer infrastructure.
It receives queries from the main RELIX service and executes them against
the local database, returning only the results.

Usage:
    python -m agent.service --config agent_config.json
    
Or programmatically:
    from agent.service import AgentService
    
    service = AgentService(config)
    service.start()
"""

import os
import json
import time
import asyncio
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

import psycopg2
from psycopg2.extras import RealDictCursor

from .models import (
    AgentConfig,
    AgentQueryRequest,
    AgentQueryResponse,
    AgentHeartbeat,
    AgentStatus
)
from .auth import AgentAuthenticator, validate_agent_token

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent.service")


class AgentService:
    """
    Customer-hosted agent service for secure database query execution.
    
    This service:
    1. Connects to the customer's local database
    2. Receives authenticated query requests from RELIX service
    3. Executes queries locally (read-only by default)
    4. Returns results securely to the main service
    5. Sends periodic heartbeats to maintain connection status
    """
    
    VERSION = "1.0.0"
    
    def __init__(
        self,
        agent_id: str,
        agent_secret: str,
        database_url: str,
        allowed_schemas: List[str] = None,
        read_only: bool = True,
        max_rows: int = 10000,
        query_timeout: int = 30
    ):
        """
        Initialize the agent service.
        
        Args:
            agent_id: Unique agent identifier from registration
            agent_secret: Secret key from registration
            database_url: PostgreSQL connection string for local database
            allowed_schemas: List of schemas the agent can query
            read_only: Only allow SELECT queries (default: True)
            max_rows: Maximum rows to return per query (default: 10000)
            query_timeout: Query timeout in seconds (default: 30)
        """
        self.agent_id = agent_id
        self.agent_secret = agent_secret
        self.database_url = database_url
        self.allowed_schemas = allowed_schemas or ["public"]
        self.read_only = read_only
        self.max_rows = max_rows
        self.query_timeout = query_timeout
        
        self.authenticator = AgentAuthenticator(agent_id, agent_secret)
        self._db_connection: Optional[psycopg2.extensions.connection] = None
        self._is_running = False
        self._queries_executed = 0
        self._total_execution_time = 0.0
        self._errors = 0
        self._start_time: Optional[datetime] = None
        
        logger.info(f"Agent service initialized: {agent_id}")
    
    def _get_db_connection(self) -> psycopg2.extensions.connection:
        """Get or create database connection."""
        if self._db_connection is None or self._db_connection.closed:
            self._db_connection = psycopg2.connect(
                self.database_url,
                cursor_factory=RealDictCursor
            )
            if self.read_only:
                self._db_connection.set_session(readonly=True)
            logger.info("Database connection established")
        return self._db_connection
    
    def _validate_query(self, sql: str) -> tuple[bool, Optional[str]]:
        """
        Validate SQL query for safety.
        
        Args:
            sql: SQL query string
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        sql_upper = sql.strip().upper()
        
        # Check for read-only mode
        if self.read_only:
            allowed_prefixes = ("SELECT", "WITH", "EXPLAIN")
            if not any(sql_upper.startswith(prefix) for prefix in allowed_prefixes):
                return False, "Only SELECT queries are allowed in read-only mode"
        
        # Block dangerous operations
        dangerous_keywords = [
            "DROP ", "DELETE ", "TRUNCATE ", "ALTER ", "CREATE ",
            "INSERT ", "UPDATE ", "GRANT ", "REVOKE ", "COPY ",
            "pg_", "information_schema"
        ]
        
        if self.read_only:
            for keyword in dangerous_keywords:
                if keyword in sql_upper:
                    return False, f"Query contains forbidden keyword: {keyword.strip()}"
        
        return True, None
    
    def execute_query(self, request: AgentQueryRequest) -> AgentQueryResponse:
        """
        Execute a query request from the main service.
        
        Args:
            request: Query request with SQL and parameters
            
        Returns:
            Query response with results or error
        """
        start_time = time.time()
        
        try:
            # Validate query
            is_valid, error = self._validate_query(request.sql)
            if not is_valid:
                logger.warning(f"Query validation failed: {error}")
                return AgentQueryResponse(
                    query_id=request.query_id,
                    success=False,
                    error=error
                )
            
            # Get connection
            conn = self._get_db_connection()
            
            # Set schema search path
            if request.schema_name and request.schema_name in self.allowed_schemas:
                with conn.cursor() as cur:
                    cur.execute(f"SET search_path TO {request.schema_name}")
            
            # Execute query with timeout
            with conn.cursor() as cur:
                # Set statement timeout
                timeout_ms = min(request.timeout_seconds, self.query_timeout) * 1000
                cur.execute(f"SET statement_timeout = {timeout_ms}")
                
                # Execute main query
                cur.execute(request.sql, request.parameters)
                
                # Fetch results
                max_rows = min(request.max_rows, self.max_rows)
                rows = cur.fetchmany(max_rows + 1)  # Fetch one extra to detect truncation
                
                truncated = len(rows) > max_rows
                if truncated:
                    rows = rows[:max_rows]
                
                # Get column info
                columns = [desc[0] for desc in cur.description] if cur.description else []
                
                # Build column types
                column_types = {}
                if cur.description:
                    for desc in cur.description:
                        col_name = desc[0]
                        type_code = desc[1]
                        # Map PostgreSQL type codes to names
                        column_types[col_name] = self._get_type_name(type_code)
            
            execution_time = (time.time() - start_time) * 1000
            
            # Update stats
            self._queries_executed += 1
            self._total_execution_time += execution_time
            
            logger.info(f"Query {request.query_id} executed: {len(rows)} rows in {execution_time:.2f}ms")
            
            # Convert rows to dicts and handle non-JSON-serializable types
            result_rows = [self._serialize_row(dict(row)) for row in rows]
            
            return AgentQueryResponse(
                query_id=request.query_id,
                success=True,
                rows=result_rows,
                row_count=len(result_rows),
                columns=columns,
                column_types=column_types,
                execution_time_ms=execution_time,
                truncated=truncated
            )
            
        except psycopg2.Error as e:
            self._errors += 1
            execution_time = (time.time() - start_time) * 1000
            logger.error(f"Database error: {e}")
            
            return AgentQueryResponse(
                query_id=request.query_id,
                success=False,
                error=f"Database error: {str(e)}",
                execution_time_ms=execution_time
            )
            
        except Exception as e:
            self._errors += 1
            execution_time = (time.time() - start_time) * 1000
            logger.error(f"Query execution error: {e}")
            
            return AgentQueryResponse(
                query_id=request.query_id,
                success=False,
                error=f"Execution error: {str(e)}",
                execution_time_ms=execution_time
            )
    
    def _get_type_name(self, type_code: int) -> str:
        """Map PostgreSQL type OID to type name."""
        # Common PostgreSQL type OIDs
        type_map = {
            16: "boolean",
            20: "bigint",
            21: "smallint",
            23: "integer",
            25: "text",
            700: "real",
            701: "double precision",
            1043: "varchar",
            1082: "date",
            1083: "time",
            1114: "timestamp",
            1184: "timestamptz",
            1700: "numeric",
            2950: "uuid",
            3802: "jsonb",
            114: "json",
        }
        return type_map.get(type_code, "unknown")
    
    def _serialize_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """Convert row values to JSON-serializable types."""
        from datetime import date, datetime, timedelta
        from decimal import Decimal
        import uuid as uuid_module
        
        result = {}
        for key, value in row.items():
            if isinstance(value, datetime):
                result[key] = value.isoformat()
            elif isinstance(value, date):
                result[key] = value.isoformat()
            elif isinstance(value, timedelta):
                result[key] = str(value)
            elif isinstance(value, Decimal):
                result[key] = float(value)
            elif isinstance(value, uuid_module.UUID):
                result[key] = str(value)
            elif isinstance(value, bytes):
                result[key] = value.decode('utf-8', errors='replace')
            else:
                result[key] = value
        return result
    
    def verify_request(self, token: str) -> tuple[bool, Optional[str]]:
        """
        Verify an incoming request token.
        
        Args:
            token: Authentication token from request
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        return validate_agent_token(token, self.agent_id, self.agent_secret)
    
    def get_heartbeat(self) -> AgentHeartbeat:
        """Generate heartbeat message."""
        connected_dbs = []
        try:
            conn = self._get_db_connection()
            with conn.cursor() as cur:
                cur.execute("SELECT current_database()")
                result = cur.fetchone()
                if result:
                    connected_dbs.append(result['current_database'])
        except Exception:
            pass
        
        return AgentHeartbeat(
            agent_id=self.agent_id,
            agent_token=self.authenticator.get_token(),
            status="healthy" if connected_dbs else "degraded",
            connected_databases=connected_dbs,
            active_connections=1 if self._db_connection and not self._db_connection.closed else 0
        )
    
    def get_status(self) -> Dict[str, Any]:
        """Get agent status information."""
        uptime = None
        if self._start_time:
            uptime = int((datetime.utcnow() - self._start_time).total_seconds())
        
        avg_time = 0.0
        if self._queries_executed > 0:
            avg_time = self._total_execution_time / self._queries_executed
        
        error_rate = 0.0
        total = self._queries_executed + self._errors
        if total > 0:
            error_rate = self._errors / total
        
        return {
            "agent_id": self.agent_id,
            "version": self.VERSION,
            "status": "running" if self._is_running else "stopped",
            "uptime_seconds": uptime,
            "queries_executed": self._queries_executed,
            "avg_response_time_ms": avg_time,
            "error_rate": error_rate,
            "allowed_schemas": self.allowed_schemas,
            "read_only": self.read_only,
            "max_rows": self.max_rows
        }
    
    def test_database_connection(self) -> tuple[bool, str]:
        """
        Test the database connection.
        
        Returns:
            Tuple of (success, message)
        """
        try:
            conn = self._get_db_connection()
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
            return True, "Database connection successful"
        except Exception as e:
            return False, f"Database connection failed: {str(e)}"
    
    def start(self):
        """Start the agent service."""
        self._is_running = True
        self._start_time = datetime.utcnow()
        logger.info(f"Agent service started: {self.agent_id}")
    
    def stop(self):
        """Stop the agent service and close connections."""
        self._is_running = False
        if self._db_connection:
            self._db_connection.close()
            self._db_connection = None
        logger.info(f"Agent service stopped: {self.agent_id}")


def create_agent_from_config(config_path: str) -> AgentService:
    """
    Create an agent service from a configuration file.
    
    Args:
        config_path: Path to JSON configuration file
        
    Returns:
        Configured AgentService instance
    """
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    return AgentService(
        agent_id=config["agent_id"],
        agent_secret=config["agent_secret"],
        database_url=config["database_url"],
        allowed_schemas=config.get("allowed_schemas", ["public"]),
        read_only=config.get("read_only", True),
        max_rows=config.get("max_rows", 10000),
        query_timeout=config.get("query_timeout", 30)
    )
