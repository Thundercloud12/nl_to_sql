"""
Agent Models

Pydantic models for customer-hosted agent configuration, registration,
status tracking, and query message payloads.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class AgentStatus(str, Enum):
    """Agent connection status"""
    PENDING = "pending"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"


class AgentConfig(BaseModel):
    """Configuration for a customer-hosted agent"""
    agent_id: str = Field(..., description="Unique agent identifier")
    agent_name: str = Field(..., description="Human-readable agent name")
    host_url: str = Field(..., description="URL where agent is hosted")
    database_type: str = Field(default="postgres", description="Database type (postgres, mysql, etc.)")
    allowed_schemas: List[str] = Field(default=["public"], description="Schemas agent can access")
    max_rows_per_query: int = Field(default=10000, description="Maximum rows returned per query")
    timeout_seconds: int = Field(default=30, description="Query timeout in seconds")
    read_only: bool = Field(default=True, description="Only allow SELECT queries")
    
    class Config:
        json_schema_extra = {
            "example": {
                "agent_id": "agent_abc123",
                "agent_name": "Production DB Agent",
                "host_url": "https://agent.customer.com:8443",
                "database_type": "postgres",
                "allowed_schemas": ["public", "analytics"],
                "max_rows_per_query": 10000,
                "timeout_seconds": 30,
                "read_only": True
            }
        }


class AgentRegistration(BaseModel):
    """Request payload for registering a new agent"""
    agent_name: str = Field(..., description="Human-readable agent name")
    host_url: str = Field(..., description="URL where agent will be hosted")
    database_type: str = Field(default="postgres", description="Database type")
    allowed_schemas: List[str] = Field(default=["public"], description="Schemas agent can access")
    user_id: str = Field(..., description="Owner user ID")
    
    class Config:
        json_schema_extra = {
            "example": {
                "agent_name": "My Production Agent",
                "host_url": "https://agent.mycompany.com:8443",
                "database_type": "postgres",
                "allowed_schemas": ["public"],
                "user_id": "user_clerk_xxx"
            }
        }


class AgentRegistrationResponse(BaseModel):
    """Response after successful agent registration"""
    agent_id: str
    agent_token: str
    agent_secret: str
    message: str
    status: AgentStatus


class AgentHeartbeat(BaseModel):
    """Heartbeat message from agent to server"""
    agent_id: str
    agent_token: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    status: str = Field(default="healthy")
    connected_databases: List[str] = Field(default=[])
    active_connections: int = Field(default=0)
    
    class Config:
        json_schema_extra = {
            "example": {
                "agent_id": "agent_abc123",
                "agent_token": "tok_xxx",
                "timestamp": "2026-01-02T12:00:00Z",
                "status": "healthy",
                "connected_databases": ["production"],
                "active_connections": 5
            }
        }


class AgentQueryRequest(BaseModel):
    """Query request sent to agent for execution"""
    query_id: str = Field(..., description="Unique query identifier")
    sql: str = Field(..., description="SQL query to execute")
    parameters: Optional[Dict[str, Any]] = Field(default=None, description="Query parameters")
    schema_name: Optional[str] = Field(default="public", description="Target schema")
    timeout_seconds: int = Field(default=30, description="Query timeout")
    max_rows: int = Field(default=10000, description="Maximum rows to return")
    
    class Config:
        json_schema_extra = {
            "example": {
                "query_id": "query_xyz789",
                "sql": "SELECT * FROM users WHERE created_at > $1 LIMIT 100",
                "parameters": {"$1": "2025-01-01"},
                "schema_name": "public",
                "timeout_seconds": 30,
                "max_rows": 100
            }
        }


class AgentQueryResponse(BaseModel):
    """Query response from agent"""
    query_id: str
    success: bool
    rows: Optional[List[Dict[str, Any]]] = None
    row_count: int = 0
    columns: Optional[List[str]] = None
    column_types: Optional[Dict[str, str]] = None
    execution_time_ms: float = 0
    error: Optional[str] = None
    truncated: bool = False
    
    class Config:
        json_schema_extra = {
            "example": {
                "query_id": "query_xyz789",
                "success": True,
                "rows": [{"id": 1, "name": "John"}],
                "row_count": 1,
                "columns": ["id", "name"],
                "column_types": {"id": "integer", "name": "varchar"},
                "execution_time_ms": 45.2,
                "error": None,
                "truncated": False
            }
        }


class AgentStatusResponse(BaseModel):
    """Agent status information"""
    agent_id: str
    agent_name: str
    status: AgentStatus
    host_url: str
    database_type: str
    last_heartbeat: Optional[datetime] = None
    uptime_seconds: Optional[int] = None
    queries_executed: int = 0
    avg_response_time_ms: float = 0
    error_rate: float = 0


class AgentConnectionTest(BaseModel):
    """Request to test agent connection"""
    agent_id: str
    agent_token: str


class AgentConnectionTestResponse(BaseModel):
    """Response from agent connection test"""
    success: bool
    latency_ms: float
    message: str
    agent_version: Optional[str] = None
    database_connected: bool = False
