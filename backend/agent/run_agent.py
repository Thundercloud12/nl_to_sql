#!/usr/bin/env python3
"""
Customer-Hosted Agent Runner

This script runs the customer-hosted agent as a standalone service.
Deploy this on your infrastructure to securely connect your databases
to the RELIX NL-to-SQL service.

Usage:
    python run_agent.py --config agent_config.json
    
    Or set environment variables:
    AGENT_ID=agent_xxx
    AGENT_SECRET=xxx
    DATABASE_URL=postgresql://...
    RELIX_SERVER_URL=https://api.relix.com
    
    python run_agent.py
    
Configuration file format (agent_config.json):
    {
        "agent_id": "agent_xxx",
        "agent_secret": "your_agent_secret",
        "database_url": "postgresql://user:pass@localhost:5432/mydb",
        "relix_server_url": "https://api.relix.com",
        "allowed_schemas": ["public", "analytics"],
        "read_only": true,
        "max_rows": 10000,
        "query_timeout": 30,
        "heartbeat_interval": 30,
        "port": 8443,
        "ssl_cert": "/path/to/cert.pem",
        "ssl_key": "/path/to/key.pem"
    }
"""

import os
import sys
import json
import argparse
import asyncio
import logging
import signal
from datetime import datetime
from typing import Optional

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import httpx

from agent.service import AgentService
from agent.models import AgentQueryRequest, AgentQueryResponse
from agent.auth import validate_agent_token

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("agent.runner")

# Global agent service instance
agent_service: Optional[AgentService] = None
config: dict = {}


def create_app() -> FastAPI:
    """Create the FastAPI application for the agent."""
    app = FastAPI(
        title="RELIX Customer Agent",
        description="Customer-hosted agent for secure database access",
        version="1.0.0"
    )
    
    # Configure CORS - only allow RELIX server
    relix_url = config.get("relix_server_url", "")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[relix_url] if relix_url else ["*"],
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    
    @app.get("/health")
    async def health():
        """Health check endpoint."""
        if agent_service is None:
            return {"status": "not_initialized"}
        
        db_ok, db_msg = agent_service.test_database_connection()
        
        return {
            "status": "healthy" if db_ok else "degraded",
            "agent_id": agent_service.agent_id,
            "version": AgentService.VERSION,
            "database_connected": db_ok,
            "database_message": db_msg,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    @app.get("/status")
    async def status():
        """Get detailed agent status."""
        if agent_service is None:
            raise HTTPException(status_code=503, detail="Agent not initialized")
        
        return agent_service.get_status()
    
    @app.post("/query")
    async def execute_query(request: Request):
        """
        Execute a query from the RELIX server.
        
        Request body is a signed payload from the server.
        """
        if agent_service is None:
            raise HTTPException(status_code=503, detail="Agent not initialized")
        
        try:
            body = await request.json()
            
            # Extract and verify token
            token = body.get("token")
            if not token:
                raise HTTPException(status_code=401, detail="Missing authentication token")
            
            is_valid, error = agent_service.verify_request(token)
            if not is_valid:
                logger.warning(f"Invalid request token: {error}")
                raise HTTPException(status_code=401, detail=f"Authentication failed: {error}")
            
            # Extract payload
            payload = body.get("payload", {})
            
            # Build query request
            query_request = AgentQueryRequest(
                query_id=payload.get("query_id", "unknown"),
                sql=payload.get("sql", ""),
                parameters=payload.get("parameters"),
                schema_name=payload.get("schema_name", "public"),
                timeout_seconds=payload.get("timeout_seconds", 30),
                max_rows=payload.get("max_rows", 10000)
            )
            
            # Execute query
            result = agent_service.execute_query(query_request)
            
            return result.model_dump()
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Query execution error: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    return app


async def send_heartbeat():
    """Send periodic heartbeats to the RELIX server."""
    global agent_service, config
    
    relix_url = config.get("relix_server_url", "").rstrip("/")
    interval = config.get("heartbeat_interval", 30)
    
    if not relix_url:
        logger.warning("No RELIX server URL configured, heartbeats disabled")
        return
    
    logger.info(f"Starting heartbeat sender (interval: {interval}s)")
    
    while True:
        try:
            if agent_service:
                heartbeat = agent_service.get_heartbeat()
                
                async with httpx.AsyncClient(timeout=10) as client:
                    response = await client.post(
                        f"{relix_url}/agent/heartbeat",
                        json=heartbeat.model_dump(),
                        headers={"Content-Type": "application/json"}
                    )
                    
                    if response.status_code == 200:
                        logger.debug("Heartbeat sent successfully")
                    else:
                        logger.warning(f"Heartbeat failed: {response.status_code}")
            
            await asyncio.sleep(interval)
            
        except asyncio.CancelledError:
            logger.info("Heartbeat sender stopped")
            break
        except Exception as e:
            logger.error(f"Heartbeat error: {e}")
            await asyncio.sleep(interval)


def load_config(config_path: Optional[str] = None) -> dict:
    """Load configuration from file or environment variables."""
    config = {}
    
    # Try loading from file
    if config_path and os.path.exists(config_path):
        with open(config_path, 'r') as f:
            config = json.load(f)
        logger.info(f"Loaded configuration from {config_path}")
    
    # Override with environment variables
    env_mapping = {
        "AGENT_ID": "agent_id",
        "AGENT_SECRET": "agent_secret",
        "DATABASE_URL": "database_url",
        "RELIX_SERVER_URL": "relix_server_url",
        "AGENT_PORT": "port",
        "AGENT_ALLOWED_SCHEMAS": "allowed_schemas",
        "AGENT_READ_ONLY": "read_only",
        "AGENT_MAX_ROWS": "max_rows",
        "AGENT_QUERY_TIMEOUT": "query_timeout",
        "AGENT_HEARTBEAT_INTERVAL": "heartbeat_interval",
        "AGENT_SSL_CERT": "ssl_cert",
        "AGENT_SSL_KEY": "ssl_key",
    }
    
    for env_var, config_key in env_mapping.items():
        value = os.getenv(env_var)
        if value is not None:
            # Type conversion
            if config_key in ["port", "max_rows", "query_timeout", "heartbeat_interval"]:
                value = int(value)
            elif config_key == "read_only":
                value = value.lower() in ("true", "1", "yes")
            elif config_key == "allowed_schemas":
                value = [s.strip() for s in value.split(",")]
            
            config[config_key] = value
    
    return config


def validate_config(config: dict) -> bool:
    """Validate required configuration."""
    required = ["agent_id", "agent_secret", "database_url"]
    missing = [key for key in required if not config.get(key)]
    
    if missing:
        logger.error(f"Missing required configuration: {', '.join(missing)}")
        return False
    
    return True


def main():
    """Main entry point."""
    global agent_service, config
    
    parser = argparse.ArgumentParser(description="Run RELIX Customer Agent")
    parser.add_argument(
        "--config", "-c",
        help="Path to configuration file",
        default="agent_config.json"
    )
    parser.add_argument(
        "--port", "-p",
        type=int,
        help="Port to listen on (default: 8443)",
        default=None
    )
    parser.add_argument(
        "--host",
        help="Host to bind to (default: 0.0.0.0)",
        default="0.0.0.0"
    )
    
    args = parser.parse_args()
    
    # Load configuration
    config = load_config(args.config)
    
    # Override port from command line
    if args.port:
        config["port"] = args.port
    
    # Validate configuration
    if not validate_config(config):
        sys.exit(1)
    
    # Initialize agent service
    agent_service = AgentService(
        agent_id=config["agent_id"],
        agent_secret=config["agent_secret"],
        database_url=config["database_url"],
        allowed_schemas=config.get("allowed_schemas", ["public"]),
        read_only=config.get("read_only", True),
        max_rows=config.get("max_rows", 10000),
        query_timeout=config.get("query_timeout", 30)
    )
    
    # Test database connection
    db_ok, db_msg = agent_service.test_database_connection()
    if not db_ok:
        logger.error(f"Database connection failed: {db_msg}")
        sys.exit(1)
    
    logger.info(f"Database connection successful")
    
    # Start agent
    agent_service.start()
    
    # Create FastAPI app
    app = create_app()
    
    # Get SSL configuration
    ssl_cert = config.get("ssl_cert")
    ssl_key = config.get("ssl_key")
    
    ssl_kwargs = {}
    if ssl_cert and ssl_key:
        if os.path.exists(ssl_cert) and os.path.exists(ssl_key):
            ssl_kwargs = {
                "ssl_certfile": ssl_cert,
                "ssl_keyfile": ssl_key
            }
            logger.info("SSL enabled")
        else:
            logger.warning("SSL certificate/key files not found, running without SSL")
    
    port = config.get("port", 8443)
    
    logger.info(f"Starting agent server on {args.host}:{port}")
    logger.info(f"Agent ID: {config['agent_id']}")
    
    # Start heartbeat task
    async def startup():
        asyncio.create_task(send_heartbeat())
    
    app.add_event_handler("startup", startup)
    
    # Handle shutdown
    def shutdown_handler(signum, frame):
        logger.info("Shutting down...")
        if agent_service:
            agent_service.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)
    
    # Run server
    uvicorn.run(
        app,
        host=args.host,
        port=port,
        **ssl_kwargs
    )


if __name__ == "__main__":
    main()
