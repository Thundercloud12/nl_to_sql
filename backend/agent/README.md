# Customer-Hosted Agent Setup Guide

This guide explains how to deploy and configure the RELIX customer-hosted agent on your infrastructure.

## Overview

The customer-hosted agent allows you to securely connect your private databases to RELIX without exposing your database credentials or data to the cloud. The agent runs on your infrastructure and:

- Receives authenticated query requests from the RELIX service
- Executes SQL queries locally against your database
- Returns only the query results (not raw credentials or full database access)
- Operates in read-only mode by default for safety

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Your Infrastructure                           │
│                                                                      │
│  ┌──────────────────┐      ┌──────────────────┐                     │
│  │   Customer       │      │    Your          │                     │
│  │   Agent          │─────▶│    Database      │                     │
│  │   (Port 8443)    │      │    (PostgreSQL)  │                     │
│  └──────────────────┘      └──────────────────┘                     │
│           │                                                          │
│           │ HTTPS (TLS)                                             │
└───────────┼─────────────────────────────────────────────────────────┘
            │
            ▼
┌───────────────────────────────────────────────────────────────────┐
│                       RELIX Cloud                                  │
│  ┌──────────────────┐                                             │
│  │   RELIX API      │◀──── Secure Token Authentication            │
│  │   Server         │                                              │
│  └──────────────────┘                                             │
└───────────────────────────────────────────────────────────────────┘
```

## Prerequisites

- Python 3.9+
- Access to your PostgreSQL database
- Network access from the agent to your database
- (Optional) SSL certificate for HTTPS

## Quick Start

### 1. Register Your Agent

First, register a new agent through the RELIX API or dashboard:

```bash
curl -X POST https://api.relix.com/agent/register \
  -H "Content-Type: application/json" \
  -d '{
    "agent_name": "Production DB Agent",
    "host_url": "https://your-agent-host:8443",
    "database_type": "postgres",
    "allowed_schemas": ["public"],
    "user_id": "your_user_id"
  }'
```

Response:
```json
{
  "agent_id": "agent_abc123xyz",
  "agent_token": "tok_xxxxxxxxxxxx",
  "agent_secret": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "message": "Agent registered successfully",
  "status": "pending"
}
```

**Important:** Save the `agent_id` and `agent_secret` securely. The secret is only shown once.

### 2. Configure the Agent

Create a configuration file `agent_config.json`:

```json
{
  "agent_id": "agent_abc123xyz",
  "agent_secret": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "database_url": "postgresql://user:password@localhost:5432/mydb",
  "relix_server_url": "https://api.relix.com",
  "allowed_schemas": ["public", "analytics"],
  "read_only": true,
  "max_rows": 10000,
  "query_timeout": 30,
  "heartbeat_interval": 30,
  "port": 8443
}
```

Or use environment variables:

```bash
export AGENT_ID="agent_abc123xyz"
export AGENT_SECRET="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
export DATABASE_URL="postgresql://user:password@localhost:5432/mydb"
export RELIX_SERVER_URL="https://api.relix.com"
export AGENT_PORT=8443
export AGENT_ALLOWED_SCHEMAS="public,analytics"
export AGENT_READ_ONLY=true
```

### 3. Install Dependencies

```bash
pip install fastapi uvicorn psycopg2-binary httpx pydantic
```

### 4. Run the Agent

```bash
python -m agent.run_agent --config agent_config.json
```

Or with environment variables:

```bash
python -m agent.run_agent
```

### 5. Verify Connection

Check agent health:

```bash
curl http://localhost:8443/health
```

Expected response:
```json
{
  "status": "healthy",
  "agent_id": "agent_abc123xyz",
  "version": "1.0.0",
  "database_connected": true,
  "timestamp": "2026-01-02T12:00:00Z"
}
```

## Configuration Options

| Option | Description | Default |
|--------|-------------|---------|
| `agent_id` | Unique agent ID from registration | Required |
| `agent_secret` | Secret key from registration | Required |
| `database_url` | PostgreSQL connection string | Required |
| `relix_server_url` | RELIX API server URL | Required |
| `allowed_schemas` | Schemas the agent can query | `["public"]` |
| `read_only` | Only allow SELECT queries | `true` |
| `max_rows` | Maximum rows per query | `10000` |
| `query_timeout` | Query timeout in seconds | `30` |
| `heartbeat_interval` | Heartbeat interval in seconds | `30` |
| `port` | Port to listen on | `8443` |
| `ssl_cert` | Path to SSL certificate | `null` |
| `ssl_key` | Path to SSL private key | `null` |

## Security Best Practices

### 1. Use Read-Only Database User

Create a dedicated read-only database user for the agent:

```sql
CREATE USER relix_agent WITH PASSWORD 'secure_password';
GRANT CONNECT ON DATABASE mydb TO relix_agent;
GRANT USAGE ON SCHEMA public TO relix_agent;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO relix_agent;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO relix_agent;
```

### 2. Enable SSL/TLS

For production, always use SSL:

```json
{
  "ssl_cert": "/path/to/fullchain.pem",
  "ssl_key": "/path/to/privkey.pem"
}
```

### 3. Network Security

- Run the agent on a private network when possible
- Use a firewall to restrict incoming connections
- Only allow connections from RELIX IP addresses

### 4. Keep Secrets Secure

- Never commit `agent_config.json` with real credentials
- Use environment variables or secret management systems
- Rotate the agent secret periodically

## Deployment Options

### Docker

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agent/ ./agent/

EXPOSE 8443

CMD ["python", "-m", "agent.run_agent"]
```

```bash
docker build -t relix-agent .
docker run -d \
  -p 8443:8443 \
  -e AGENT_ID=your_agent_id \
  -e AGENT_SECRET=your_secret \
  -e DATABASE_URL=postgresql://... \
  -e RELIX_SERVER_URL=https://api.relix.com \
  relix-agent
```

### Kubernetes

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: relix-agent
spec:
  replicas: 1
  selector:
    matchLabels:
      app: relix-agent
  template:
    metadata:
      labels:
        app: relix-agent
    spec:
      containers:
      - name: agent
        image: relix-agent:latest
        ports:
        - containerPort: 8443
        envFrom:
        - secretRef:
            name: relix-agent-secrets
---
apiVersion: v1
kind: Secret
metadata:
  name: relix-agent-secrets
type: Opaque
stringData:
  AGENT_ID: "agent_xxx"
  AGENT_SECRET: "xxx"
  DATABASE_URL: "postgresql://..."
  RELIX_SERVER_URL: "https://api.relix.com"
```

### systemd Service

```ini
[Unit]
Description=RELIX Customer Agent
After=network.target postgresql.service

[Service]
Type=simple
User=relix
WorkingDirectory=/opt/relix-agent
EnvironmentFile=/etc/relix-agent/env
ExecStart=/opt/relix-agent/venv/bin/python -m agent.run_agent
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

## Troubleshooting

### Agent not connecting

1. Check network connectivity to RELIX server
2. Verify agent credentials are correct
3. Check firewall rules
4. Review agent logs for errors

### Database connection failed

1. Verify `database_url` is correct
2. Check database user permissions
3. Ensure database is accessible from agent host

### Queries timing out

1. Increase `query_timeout` setting
2. Optimize slow queries
3. Check database performance

### Authentication errors

1. Verify `agent_id` and `agent_secret` match registration
2. Check if agent token has expired
3. Re-register the agent if needed

## API Endpoints

### Health Check

```
GET /health
```

Returns agent health status and database connectivity.

### Status

```
GET /status
```

Returns detailed agent status including query statistics.

### Query Execution

```
POST /query
```

Executes a query (called by RELIX server, not directly).

## Support

For issues or questions:

1. Check the troubleshooting guide above
2. Review agent logs
3. Contact RELIX support
