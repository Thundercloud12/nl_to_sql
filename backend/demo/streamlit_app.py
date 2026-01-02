"""
RELIX Demo Application - Streamlit Chat Interface

A simple demo application that allows users to:
1. Upload CSV/Excel files
2. Ask natural language questions about their data
3. Get SQL queries and results through the customer-hosted agent

Usage:
    pip install streamlit pandas openpyxl requests
    streamlit run demo/streamlit_app.py
"""

import streamlit as st
import pandas as pd
import requests
import json
import os

# Configuration
SAAS_SERVER_URL = os.getenv("SAAS_SERVER_URL", "http://localhost:8000")
AGENT_ID = os.getenv("AGENT_ID", "")
USER_ID = os.getenv("USER_ID", "demo_user")

# Page configuration
st.set_page_config(
    page_title="RELIX - NL to SQL Demo",
    page_icon="🔍",
    layout="wide"
)

# Custom CSS
st.markdown("""
<style>
    .stTextArea textarea {
        font-size: 16px;
    }
    .chat-message {
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
    }
    .user-message {
        background-color: #e3f2fd;
    }
    .assistant-message {
        background-color: #f5f5f5;
    }
</style>
""", unsafe_allow_html=True)

# Title
st.title("🔍 RELIX - Natural Language to SQL")
st.markdown("Upload your data and ask questions in plain English!")

# Sidebar for configuration
with st.sidebar:
    st.header("⚙️ Configuration")
    
    server_url = st.text_input(
        "SaaS Server URL",
        value=SAAS_SERVER_URL,
        help="URL of your RELIX SaaS server"
    )
    
    agent_id = st.text_input(
        "Agent ID",
        value=AGENT_ID,
        help="Your registered agent ID"
    )
    
    user_id = st.text_input(
        "User ID",
        value=USER_ID,
        help="Your user ID"
    )
    
    st.divider()
    
    st.header("📊 Agent Status")
    if st.button("Check Agent Status"):
        if agent_id and user_id:
            try:
                response = requests.get(
                    f"{server_url}/agent/status/{agent_id}",
                    params={"user_id": user_id},
                    timeout=5
                )
                if response.status_code == 200:
                    status = response.json()
                    st.success(f"Status: {status.get('status', 'unknown')}")
                else:
                    st.error(f"Error: {response.status_code}")
            except Exception as e:
                st.error(f"Connection error: {str(e)}")
        else:
            st.warning("Please enter Agent ID and User ID")

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []

if "uploaded_data" not in st.session_state:
    st.session_state.uploaded_data = None

if "data_schema" not in st.session_state:
    st.session_state.data_schema = None

# Main content area
col1, col2 = st.columns([1, 1])

with col1:
    st.header("📁 Upload Data")
    
    uploaded_file = st.file_uploader(
        "Choose a CSV or Excel file",
        type=["csv", "xlsx", "xls"],
        help="Upload your data file to analyze"
    )
    
    if uploaded_file is not None:
        try:
            # Read the file
            if uploaded_file.name.endswith('.csv'):
                df = pd.read_csv(uploaded_file)
            else:
                df = pd.read_excel(uploaded_file)
            
            st.session_state.uploaded_data = df
            
            # Generate schema info
            schema_info = []
            for col in df.columns:
                dtype = str(df[col].dtype)
                schema_info.append(f"- {col} ({dtype})")
            st.session_state.data_schema = "\n".join(schema_info)
            
            st.success(f"✅ Loaded {len(df)} rows, {len(df.columns)} columns")
            
            # Show preview
            st.subheader("Data Preview")
            st.dataframe(df.head(10), use_container_width=True)
            
            # Show schema
            with st.expander("📋 Column Schema"):
                st.text(st.session_state.data_schema)
                
        except Exception as e:
            st.error(f"Error reading file: {str(e)}")

with col2:
    st.header("💬 Ask Questions")
    
    # Display chat history
    for message in st.session_state.messages:
        if message["role"] == "user":
            st.markdown(f"""
            <div class="chat-message user-message">
                <strong>You:</strong> {message["content"]}
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class="chat-message assistant-message">
                <strong>Assistant:</strong><br>{message["content"]}
            </div>
            """, unsafe_allow_html=True)
    
    # Question input
    question = st.text_area(
        "Ask a question about your data",
        placeholder="e.g., Show me the top 5 customers by total sales",
        height=100,
        key="question_input"
    )
    
    col_btn1, col_btn2 = st.columns([1, 1])
    
    with col_btn1:
        ask_button = st.button("🚀 Ask", type="primary", use_container_width=True)
    
    with col_btn2:
        if st.button("🗑️ Clear Chat", use_container_width=True):
            st.session_state.messages = []
            st.rerun()
    
    if ask_button and question:
        # Add user message
        st.session_state.messages.append({
            "role": "user",
            "content": question
        })
        
        # Process the question
        with st.spinner("Thinking..."):
            try:
                if agent_id and server_url:
                    # Build context with schema info
                    context = ""
                    if st.session_state.data_schema:
                        context = f"Available columns:\n{st.session_state.data_schema}\n\n"
                    
                    # Call the query endpoint
                    # Note: In a real implementation, this would go through the NL-to-SQL pipeline
                    # For demo purposes, we'll show how to structure the API call
                    
                    payload = {
                        "agent_id": agent_id,
                        "user_id": user_id,
                        "question": question,
                        "context": context
                    }
                    
                    # Try to call the main query endpoint
                    response = requests.post(
                        f"{server_url}/query",
                        json={
                            "question": f"{context}User question: {question}",
                            "user_id": user_id,
                            "data_source_id": agent_id  # Using agent as data source
                        },
                        timeout=30
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        answer = result.get("answer", result.get("final_answer", "No answer received"))
                        
                        # Format the response
                        response_text = f"{answer}"
                        
                        if "insights" in result and result["insights"]:
                            response_text += f"\n\n**Insights:** {result['insights']}"
                        
                    else:
                        # Fallback: Show how to use the agent/query endpoint directly
                        response_text = f"""
**Demo Mode**: To execute queries through your agent, use:

```
POST {server_url}/agent/query
{{
    "agent_id": "{agent_id}",
    "user_id": "{user_id}",
    "sql": "SELECT ... FROM your_table"
}}
```

Your question: "{question}"

With the uploaded data schema:
{st.session_state.data_schema or "No data uploaded"}
"""
                else:
                    response_text = "⚠️ Please configure Agent ID and Server URL in the sidebar."
                
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": response_text
                })
                
            except requests.exceptions.ConnectionError:
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": f"❌ Could not connect to server at {server_url}. Make sure the backend is running."
                })
            except Exception as e:
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": f"❌ Error: {str(e)}"
                })
        
        st.rerun()

# Footer
st.divider()
st.markdown("""
<div style="text-align: center; color: #666;">
    <p>🔒 Your data stays secure with the customer-hosted agent architecture</p>
    <p>Built with ❤️ using RELIX NL-to-SQL</p>
</div>
""", unsafe_allow_html=True)
