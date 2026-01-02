# RELIX Streamlit Demo Application

A simple demo chat interface for showcasing the NL-to-SQL capability with customer-hosted agent.

## Features

- 📁 Upload CSV/Excel files
- 💬 Ask natural language questions about your data
- 🔒 Secure query execution through customer-hosted agent
- 📊 View query results and insights

## Quick Start

### 1. Install Dependencies

```powershell
cd backend/demo
pip install -r requirements.txt
```

### 2. Set Environment Variables (Optional)

```powershell
$env:SAAS_SERVER_URL = "http://localhost:8000"
$env:AGENT_ID = "your_agent_id"
$env:USER_ID = "your_user_id"
```

### 3. Run the App

```powershell
streamlit run streamlit_app.py
```

The app will open at `http://localhost:8501`

## Usage

1. **Configure Connection**: Enter your SaaS server URL and Agent ID in the sidebar
2. **Upload Data**: Upload a CSV or Excel file in the left panel
3. **Ask Questions**: Type natural language questions in the right panel
4. **View Results**: See SQL queries and results displayed in the chat

## For Hackathon Demo

### Two-Laptop Setup

**Laptop 1 (SaaS Server):**
```powershell
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000
```

**Laptop 2 (Customer Demo):**
```powershell
cd backend/demo
$env:SAAS_SERVER_URL = "http://192.168.x.x:8000"  # SaaS laptop IP
$env:AGENT_ID = "agent_xxxxx"  # From registration
streamlit run streamlit_app.py
```

### Demo Script

1. Show the upload feature - drag and drop a CSV file
2. Point out the schema detection in the sidebar
3. Ask a question like "Show me the top 5 rows"
4. Explain that the query goes through the secure agent, never exposing raw database credentials

## Screenshots

The app has two main panels:
- **Left**: File upload and data preview
- **Right**: Chat interface for questions

## Troubleshooting

- **Connection Error**: Make sure the backend server is running
- **Agent Not Found**: Verify agent_id is correct and agent is registered
- **No Results**: Check that your agent is connected (status: connected)
