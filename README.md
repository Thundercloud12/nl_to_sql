# NL SQL Query - Natural Language to Data Analysis Engine

A sophisticated AI-powered data analysis system that converts natural language questions into executable queries and delivers insightful results. Built with FastAPI, LangGraph, and Google's Gemini API.

## 📋 Project Overview

**NL SQL Query** enables users to ask data questions in plain English and get intelligent, data-driven answers without writing SQL or Python code. The system automatically:

1. **Understands** natural language queries about your data
2. **Plans** the required data operations (filtering, grouping, aggregations, joins)
3. **Executes** the plan on your datasets (Excel files)
4. **Generates** human-readable insights and answers
5. **Maintains** multi-turn conversations with context awareness

### Key Features

✅ **Natural Language Interface** - Ask questions like "Does the data show bias?" or "What's the average age by outcome?"  
✅ **Multi-turn Conversations** - Maintains session history and context  
✅ **Smart Clarifications** - Asks for clarification when needed  
✅ **Metadata-Aware** - Automatically discovers and understands your data schema  
✅ **Self-Healing Execution** - Retries failed operations with corrected logic  
✅ **LLM-Powered Insights** - Converts raw data results into natural language explanations  

---

## 🏗️ Architecture

### High-Level Flow

```
User Query 
    ↓
[LangGraph State Machine]
    ↓
Input Node → Planner Node → Router → SQL/Pandas Executor → Output Node
    ↑                                                           ↓
    └─── Clarification Loop (if needed) ← Clarification Node ←┘
    
    ↓
Insight Generator (LLM) → Final Answer to User
```

### Directory Structure

```
backend/
├── main.py                      # FastAPI application & session management
├── insight_generator.py         # NLP-based insight generation
├── llm_interface.py             # LLM communication utilities
├── raw_metadata.json            # Auto-generated data schema
├── schema_graph_string.json     # Table relationship graph
│
├── data_ingestion/
│   ├── data_ingest.py          # Excel loader, schema extraction
│   └── graph_builder.py         # Table relationship inference
│
├── llm/
│   ├── plan_generator.py       # LangGraph workflow & query planning
│   └── interpretor.py          # Code generation & execution (pandas/SQL)
│
└── data/                        # Input datasets (Excel files)
    ├── DEEPAKNTR/
    ├── DMART/
    └── ELECON/
```

---

## 🔧 Core Components

### 1. **Data Ingestion** (`data_ingestion/`)

**`data_ingest.py`**
- Recursively loads Excel files from `data/` folder
- Extracts every sheet and creates unique table names
- Normalizes column names (lowercase, underscores)
- Uses Gemini LLM to generate table summaries
- Outputs `raw_metadata.json` with schema info

**`graph_builder.py`**
- Infers relationships between tables using LLM
- Creates table dependency graph
- Handles multi-turn clarification for relationship discovery

### 2. **LLM Pipeline** (`llm/`)

**`plan_generator.py`** - Query Planning Engine
- **Input Node**: Accepts user question
- **Planner Node**: Calls Gemini to generate a structured query plan:
  ```json
  {
    "tables": ["T1", "T2"],
    "filters": ["outcome > 0"],
    "joins": [{"left": "T1", "right": "T2"}],
    "operations": ["COUNT(*)", "AVG(glucose)"],
    "group_by": ["outcome"],
    "execution_mode": "sql" | "pandas"
  }
  ```
- **Router Node**: Routes to SQL or Pandas executor based on plan
- **Clarification Node**: Requests user input if plan is ambiguous
- **Output Node**: Formats final answer with insights

**`interpretor.py`** - Code Execution Engine
- Generates Python/Pandas code from structured plans
- Executes code safely in isolated environment
- **Self-Healing**: On error, provides error context to LLM and retries
- Validates that generated code matches the plan requirements
- Max 3 retry attempts with progressive error feedback

### 3. **Insight Generation** (`insight_generator.py`)

- Converts raw query results into natural language explanations
- Identifies trends, anomalies, and comparisons
- Provides 4-6 sentence summaries with business-friendly language

### 4. **API Layer** (`main.py`)

- **FastAPI** backend with session-based conversation management
- Session storage for multi-turn conversations
- Endpoints:
  - `POST /query` - Submit a question (returns session_id)
  - `POST /clarify` - Provide clarification answers
  - Conversation history tracking per session

---

## 🚀 How It Works

### Example: "Does the data show some bias?"

1. **User Query** → "Does the data show some bias?"

2. **Planning Phase** (LLM generates):
   ```json
   {
     "tables": ["T1"],
     "operations": ["COUNT(*)", "AVG(age)", "AVG(glucose)", ...],
     "group_by": ["outcome"],
     "needs_clarification": false
   }
   ```

3. **Execution Phase** (Pandas):
   ```python
   df = tables['T1'].copy()
   result = df.groupby('outcome').agg({
     'count': 'size',
     'age': 'mean',
     'glucose': 'mean',
     ...
   }).reset_index()
   ```

4. **Insight Phase** (LLM analyzes result):
   - "The data shows 500 non-diabetic vs 268 diabetic individuals"
   - "Class imbalance of 65% vs 35% is a key bias concern"
   - "Diabetic group has higher glucose (141 vs 110) and age (37 vs 31)"

5. **Response** → Natural language answer with data table + insights

---

## 🛠️ Tech Stack

| Component | Technology |
|-----------|------------|
| **API Framework** | FastAPI |
| **Workflow Orchestration** | LangGraph |
| **LLM** | Google Gemini 2.5 Flash |
| **Data Processing** | Pandas |
| **Data Input** | Excel/Openpyxl |
| **Configuration** | Environment variables (.env) |

---

## ⚙️ Setup & Installation

### Prerequisites
- Python 3.9+
- Google Gemini API key

### Installation

```bash
# Clone and navigate
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install fastapi pandas openpyxl google-generativeai langgraph uvicorn

# Set API key
export GOOGLE_API_KEY="your-gemini-api-key"

# Place your data
# Data should be in: backend/data/<folder_name>/*.xlsx
```

### Running the Server

```bash
python main.py
```

Server runs on `http://127.0.0.1:8000`

---

## 📊 Example Usage

### Query: "What's the average age by diabetes outcome?"

**Request:**
```json
{
  "question": "What's the average age by diabetes outcome?"
}
```

**Internal Processing:**
1. Planner generates: `group_by: ['outcome'], operations: ['AVG(age)', 'COUNT(*)']`
2. Executor creates pandas code with groupby
3. LLM generates insight from result

**Response:**
```json
{
  "result": {
    "outcome": [0, 1],
    "avg_age": [31.19, 37.07],
    "count": [500, 268]
  },
  "insight": "People with diabetes are on average 6 years older (37 vs 31). The diabetic group is significantly smaller (268 vs 500), showing class imbalance in the dataset."
}
```

---

## 🐛 Known Issues & Recent Fixes

### Fixed: `needs_clarification` Flag Not Preserved
**Issue**: Plan merging overwrote `needs_clarification: true` with `false` from subsequent LLM calls  
**Solution**: Modified `merge_plans()` to use OR logic: if ANY iteration needs clarification, preserve it

### Fixed: Groupby Operations Not Executed
**Issue**: Plan said `group_by: ['outcome']` but generated code ignored it  
**Solution**: Added validation in `interpretor.py` to ensure groupby operations are reflected in generated code

---

## 🔍 Debugging

The system outputs detailed debug logs:

```
[INPUT NODE] Received user question.
[PLANNER NODE] Running LLM planner...
[DEBUG] Current plan from LLM: {...}
[SQL EXECUTOR NODE] Executing SQL query...
[SELF-HEAL] Attempt 1/3
[OUTPUT NODE] Returning final answer to user.
```

Check these for understanding what the planner decided to do.

---

## 📝 Project Workflow

1. **Data Discovery** → Loads Excel files, generates metadata
2. **Schema Understanding** → LLM infers table relationships
3. **Query Planning** → Convert natural language → structured plan
4. **Execution** → Run pandas/SQL operations on data
5. **Insight Generation** → Convert results → human-readable answers
6. **Session Management** → Track multi-turn conversations

---

## 🎯 Use Cases

- **Data Exploration**: "Show me the distribution of ages"
- **Bias Detection**: "Does the data show bias towards any group?"
- **Statistical Analysis**: "Compare average glucose levels by outcome"
- **Data Quality**: "Are there missing values in the dataset?"
- **Trend Analysis**: "Which variables correlate with diabetes?"

---

## 📚 Dependencies

```txt
fastapi>=0.104.0
pandas>=2.0.0
openpyxl>=3.10.0
google-generativeai>=0.3.0
langgraph>=0.0.0
uvicorn>=0.24.0
python-multipart>=0.0.6
```

---

## 🔐 Configuration

Create a `.env` file in `/backend`:

```env
GOOGLE_API_KEY=your_gemini_api_key_here
```

---

## 📄 License

This project is created for data analysis and exploration purposes.

---

## 👨‍💻 Architecture Insights

### Why LangGraph?
- **State Management**: Maintains conversation state across multiple steps
- **Conditonal Routing**: Routes to different executors (SQL vs Pandas) based on plan
- **Clarity Handling**: Supports multi-turn clarification flows naturally
- **Modularity**: Each node is independent and testable

### Why Pandas + LLM Code Generation?
- **Flexibility**: Can handle complex operations beyond SQL
- **Data Transformations**: Easy reshaping, pivoting, conditional logic
- **Self-Healing**: LLM can fix its own mistakes with error context
- **Safety**: Isolated execution environment

### Design Philosophy
**"Let the LLM think, validate, and retry"**
- LLM plans what to do (not how)
- Structured schema prevents hallucinations
- Self-healing retries improve reliability
- Human-readable insights bridge data and business

---

## 🚦 Future Enhancements

- [ ] Support for SQL databases (PostgreSQL, MySQL)
- [ ] Advanced ML model integration (predictions, clustering)
- [ ] Real-time data source connections
- [ ] Dashboard with visualization
- [ ] Multi-language support
- [ ] API rate limiting & authentication
- [ ] Result caching for repeated queries

---

**Built with ❤️ to make data exploration accessible to everyone.**
