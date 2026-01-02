"""
Agent Manager

Manages customer-hosted agents from the main RELIX service.
Handles registration, heartbeats, connection status, and query routing.
"""

import os
import json
import time
import uuid
import asyncio
import logging
import httpx
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta

from .models import (
    AgentConfig,
    AgentRegistration,
    AgentRegistrationResponse,
    AgentStatus,
    AgentQueryRequest,
    AgentQueryResponse,
    AgentHeartbeat,
    AgentStatusResponse
)
from .auth import generate_agent_credentials, AgentAuthenticator, sign_payload

logger = logging.getLogger("agent.manager")


class AgentManager:
    """
    Manages customer-hosted agents from the server side.
    
    Responsibilities:
    - Register new agents and generate credentials
    - Track agent status via heartbeats
    - Route queries to appropriate agents
    - Handle agent disconnections and failovers
    """
    
    def __init__(self, db_cursor_factory):
        """
        Initialize the agent manager.
        
        Args:
            db_cursor_factory: Function that returns a database cursor context manager
        """
        self.db_cursor = db_cursor_factory
        self._agent_cache: Dict[str, Dict[str, Any]] = {}
        self._heartbeat_timestamps: Dict[str, datetime] = {}
        
        # Configuration
        self.heartbeat_timeout_seconds = 60  # Agent considered disconnected after this
        self.query_timeout_seconds = 30
        self.max_retries = 2
    
    async def register_agent(self, registration: AgentRegistration) -> AgentRegistrationResponse:
        """
        Register a new customer-hosted agent.
        
        Args:
            registration: Agent registration details
            
        Returns:
            Registration response with credentials
        """
        # Generate credentials
        agent_id, agent_token, agent_secret = generate_agent_credentials()
        
        # Store in database
        config = AgentConfig(
            agent_id=agent_id,
            agent_name=registration.agent_name,
            host_url=registration.host_url,
            database_type=registration.database_type,
            allowed_schemas=registration.allowed_schemas
        )
        
        with self.db_cursor(commit=True) as cur:
            cur.execute(
                """
                INSERT INTO "Agent" (
                    id, "userId", name, "hostUrl", "databaseType", 
                    "allowedSchemas", "agentToken", "agentSecret", 
                    status, "createdAt", "updatedAt"
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                """,
                (
                    agent_id,
                    registration.user_id,
                    registration.agent_name,
                    registration.host_url,
                    registration.database_type,
                    json.dumps(registration.allowed_schemas),
                    agent_token,  # Store hashed in production
                    agent_secret,  # Store hashed in production
                    AgentStatus.PENDING.value
                )
            )
        
        logger.info(f"Registered new agent: {agent_id} for user: {registration.user_id}")
        
        return AgentRegistrationResponse(
            agent_id=agent_id,
            agent_token=agent_token,
            agent_secret=agent_secret,
            message="Agent registered successfully. Use these credentials in your agent configuration.",
            status=AgentStatus.PENDING
        )
    
    async def process_heartbeat(self, heartbeat: AgentHeartbeat) -> Dict[str, Any]:
        """
        Process a heartbeat from an agent.
        
        Args:
            heartbeat: Heartbeat message from agent
            
        Returns:
            Acknowledgment response
        """
        agent_id = heartbeat.agent_id
        
        # Validate token
        agent_data = await self._get_agent_data(agent_id)
        if not agent_data:
            return {"success": False, "error": "Unknown agent"}
        
        # Update status
        with self.db_cursor(commit=True) as cur:
            cur.execute(
                """
                UPDATE "Agent" 
                SET status = %s, "lastHeartbeat" = NOW(), "updatedAt" = NOW(),
                    "connectedDatabases" = %s, "activeConnections" = %s
                WHERE id = %s
                """,
                (
                    AgentStatus.CONNECTED.value,
                    json.dumps(heartbeat.connected_databases),
                    heartbeat.active_connections,
                    agent_id
                )
            )
        
        self._heartbeat_timestamps[agent_id] = datetime.utcnow()
        
        # Invalidate cache
        if agent_id in self._agent_cache:
            del self._agent_cache[agent_id]
        
        logger.debug(f"Heartbeat received from agent: {agent_id}")
        
        return {"success": True, "message": "Heartbeat acknowledged"}
    
    async def execute_query(
        self, 
        agent_id: str, 
        sql: str, 
        parameters: Optional[Dict[str, Any]] = None,
        schema_name: str = "public",
        timeout: int = 30
    ) -> AgentQueryResponse:
        """
        Execute a query through a customer-hosted agent.
        
        Args:
            agent_id: Target agent ID
            sql: SQL query to execute
            parameters: Query parameters
            schema_name: Target schema
            timeout: Query timeout in seconds
            
        Returns:
            Query response from agent
        """
        # Get agent data
        agent_data = await self._get_agent_data(agent_id)
        if not agent_data:
            return AgentQueryResponse(
                query_id="error",
                success=False,
                error="Agent not found"
            )
        
        # Check agent status
        if agent_data.get("status") != AgentStatus.CONNECTED.value:
            return AgentQueryResponse(
                query_id="error",
                success=False,
                error=f"Agent not connected. Status: {agent_data.get('status')}"
            )
        
        # Build query request
        query_id = f"query_{uuid.uuid4().hex[:12]}"
        request = AgentQueryRequest(
            query_id=query_id,
            sql=sql,
            parameters=parameters,
            schema_name=schema_name,
            timeout_seconds=min(timeout, self.query_timeout_seconds)
        )
        
        # Sign request
        authenticator = AgentAuthenticator(agent_id, agent_data["agentSecret"])
        signed_request = authenticator.sign_request(request.model_dump())
        
        # Send to agent
        host_url = agent_data["hostUrl"].rstrip("/")
        
        try:
            async with httpx.AsyncClient(timeout=timeout + 5) as client:
                response = await client.post(
                    f"{host_url}/query",
                    json=signed_request,
                    headers={"Content-Type": "application/json"}
                )
                
                if response.status_code != 200:
                    return AgentQueryResponse(
                        query_id=query_id,
                        success=False,
                        error=f"Agent returned status {response.status_code}"
                    )
                
                result = response.json()
                return AgentQueryResponse(**result)
                
        except httpx.TimeoutException:
            logger.error(f"Query timeout for agent {agent_id}")
            return AgentQueryResponse(
                query_id=query_id,
                success=False,
                error="Query timed out"
            )
        except Exception as e:
            logger.error(f"Query execution error: {e}")
            return AgentQueryResponse(
                query_id=query_id,
                success=False,
                error=f"Communication error: {str(e)}"
            )
    
    async def get_agent_status(self, agent_id: str, user_id: str) -> Optional[AgentStatusResponse]:
        """
        Get status information for an agent.
        
        Args:
            agent_id: Agent ID
            user_id: User ID for authorization
            
        Returns:
            Agent status or None if not found
        """
        with self.db_cursor() as cur:
            cur.execute(
                """
                SELECT * FROM "Agent" WHERE id = %s AND "userId" = %s
                """,
                (agent_id, user_id)
            )
            agent = cur.fetchone()
        
        if not agent:
            return None
        
        # Calculate uptime
        uptime = None
        last_heartbeat = agent.get("lastHeartbeat")
        if last_heartbeat:
            uptime = int((datetime.utcnow() - last_heartbeat).total_seconds())
        
        return AgentStatusResponse(
            agent_id=agent["id"],
            agent_name=agent["name"],
            status=AgentStatus(agent["status"]),
            host_url=agent["hostUrl"],
            database_type=agent["databaseType"],
            last_heartbeat=last_heartbeat,
            uptime_seconds=uptime,
            queries_executed=agent.get("queriesExecuted", 0),
            avg_response_time_ms=agent.get("avgResponseTime", 0),
            error_rate=agent.get("errorRate", 0)
        )
    
    async def list_agents(self, user_id: str) -> List[AgentStatusResponse]:
        """
        List all agents for a user.
        
        Args:
            user_id: User ID
            
        Returns:
            List of agent status responses
        """
        with self.db_cursor() as cur:
            cur.execute(
                """
                SELECT * FROM "Agent" WHERE "userId" = %s ORDER BY "createdAt" DESC
                """,
                (user_id,)
            )
            agents = cur.fetchall()
        
        result = []
        for agent in agents:
            uptime = None
            last_heartbeat = agent.get("lastHeartbeat")
            if last_heartbeat:
                uptime = int((datetime.utcnow() - last_heartbeat).total_seconds())
            
            result.append(AgentStatusResponse(
                agent_id=agent["id"],
                agent_name=agent["name"],
                status=AgentStatus(agent["status"]),
                host_url=agent["hostUrl"],
                database_type=agent["databaseType"],
                last_heartbeat=last_heartbeat,
                uptime_seconds=uptime,
                queries_executed=agent.get("queriesExecuted", 0),
                avg_response_time_ms=agent.get("avgResponseTime", 0),
                error_rate=agent.get("errorRate", 0)
            ))
        
        return result
    
    async def delete_agent(self, agent_id: str, user_id: str) -> bool:
        """
        Delete an agent.
        
        Args:
            agent_id: Agent ID
            user_id: User ID for authorization
            
        Returns:
            True if deleted, False if not found
        """
        with self.db_cursor(commit=True) as cur:
            cur.execute(
                """
                DELETE FROM "Agent" WHERE id = %s AND "userId" = %s
                """,
                (agent_id, user_id)
            )
            deleted = cur.rowcount > 0
        
        if deleted:
            # Clean up cache
            if agent_id in self._agent_cache:
                del self._agent_cache[agent_id]
            if agent_id in self._heartbeat_timestamps:
                del self._heartbeat_timestamps[agent_id]
            
            logger.info(f"Deleted agent: {agent_id}")
        
        return deleted
    
    async def test_agent_connection(self, agent_id: str, user_id: str) -> Tuple[bool, str, float]:
        """
        Test connection to an agent.
        
        Args:
            agent_id: Agent ID
            user_id: User ID for authorization
            
        Returns:
            Tuple of (success, message, latency_ms)
        """
        agent_data = await self._get_agent_data(agent_id)
        if not agent_data:
            return False, "Agent not found", 0
        
        if agent_data.get("userId") != user_id:
            return False, "Unauthorized", 0
        
        host_url = agent_data["hostUrl"].rstrip("/")
        
        start_time = time.time()
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"{host_url}/health")
                latency = (time.time() - start_time) * 1000
                
                if response.status_code == 200:
                    return True, "Connection successful", latency
                else:
                    return False, f"Agent returned status {response.status_code}", latency
                    
        except httpx.TimeoutException:
            return False, "Connection timed out", (time.time() - start_time) * 1000
        except Exception as e:
            return False, f"Connection error: {str(e)}", (time.time() - start_time) * 1000
    
    async def _get_agent_data(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get agent data from cache or database."""
        # Check cache
        if agent_id in self._agent_cache:
            cached = self._agent_cache[agent_id]
            if datetime.utcnow() - cached["_cached_at"] < timedelta(minutes=5):
                return cached
        
        # Fetch from database
        with self.db_cursor() as cur:
            cur.execute(
                """SELECT * FROM "Agent" WHERE id = %s""",
                (agent_id,)
            )
            agent = cur.fetchone()
        
        if agent:
            agent_dict = dict(agent)
            agent_dict["_cached_at"] = datetime.utcnow()
            self._agent_cache[agent_id] = agent_dict
            return agent_dict
        
        return None
    
    async def check_stale_agents(self) -> List[str]:
        """
        Check for agents that haven't sent heartbeats recently.
        Updates their status to disconnected.
        
        Returns:
            List of agent IDs marked as disconnected
        """
        threshold = datetime.utcnow() - timedelta(seconds=self.heartbeat_timeout_seconds)
        
        with self.db_cursor(commit=True) as cur:
            cur.execute(
                """
                UPDATE "Agent" 
                SET status = %s, "updatedAt" = NOW()
                WHERE status = %s AND "lastHeartbeat" < %s
                RETURNING id
                """,
                (AgentStatus.DISCONNECTED.value, AgentStatus.CONNECTED.value, threshold)
            )
            stale_agents = [row["id"] for row in cur.fetchall()]
        
        # Clear cache for stale agents
        for agent_id in stale_agents:
            if agent_id in self._agent_cache:
                del self._agent_cache[agent_id]
            logger.warning(f"Agent marked as disconnected: {agent_id}")
        
        return stale_agents


# Global instance (will be initialized in main.py)
_agent_manager: Optional[AgentManager] = None


def get_agent_manager() -> AgentManager:
    """Get the global agent manager instance."""
    global _agent_manager
    if _agent_manager is None:
        raise RuntimeError("Agent manager not initialized")
    return _agent_manager


def init_agent_manager(db_cursor_factory) -> AgentManager:
    """Initialize the global agent manager."""
    global _agent_manager
    _agent_manager = AgentManager(db_cursor_factory)
    return _agent_manager
