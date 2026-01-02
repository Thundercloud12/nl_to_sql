"""
Customer-Hosted Agent Module

This module provides the infrastructure for customer-hosted agents that can
securely connect to the main RELIX service. Agents run on customer infrastructure
and execute database queries locally, sending only results back to the main service.

Components:
- auth: Token-based authentication for agent-service communication
- models: Pydantic models for agent configuration and messages
- service: Agent service that runs on customer infrastructure
"""

from .models import AgentConfig, AgentRegistration, AgentStatus, AgentQueryRequest, AgentQueryResponse
from .auth import AgentAuthenticator, generate_agent_token, validate_agent_token

__all__ = [
    "AgentConfig",
    "AgentRegistration", 
    "AgentStatus",
    "AgentQueryRequest",
    "AgentQueryResponse",
    "AgentAuthenticator",
    "generate_agent_token",
    "validate_agent_token",
]
