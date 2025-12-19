# NL2SQL - Natural Language to SQL Query Engine

A full-stack AI-powered data analysis platform that converts natural language questions into executable SQL queries and delivers insightful results. Built with Next.js, FastAPI, LangGraph, and Google's Gemini API.

## 📋 Project Overview

**NL2SQL** enables users to upload data files and ask questions in plain English to get intelligent, data-driven answers without writing SQL code. The system automatically:

1. **Processes** uploaded Excel/CSV files into optimized Parquet format
2. **Understands** natural language queries about your data
3. **Plans** the required SQL operations (filtering, grouping, aggregations, joins)
4. **Executes** the plan on your datasets using DuckDB
5. **Generates** human-readable insights and visualizations
6. **Maintains** multi-turn conversations with context awareness

### Key Features

✅ **Natural Language Interface** - Ask questions like "How many users are active?" or "What's the average revenue by category?"  
✅ **File Upload & Processing** - Supports Excel, CSV files with automatic schema detection  
✅ **Multi-turn Conversations** - Maintains session history and context  
✅ **Smart Clarifications** - Asks for clarification when queries are ambiguous  
✅ **Metadata-Aware** - Automatically discovers and understands your data schema  
✅ **Self-Healing Execution** - Retries failed operations with corrected logic  
✅ **LLM-Powered Insights** - Converts raw SQL results into natural language explanations  
✅ **Secure Authentication** - User management with Clerk  
✅ **Cloud Storage** - File storage with Supabase  
✅ **Modern Web UI** - Responsive interface built with Next.js and Tailwind CSS  

---

## 🏗️ Architecture

### High-Level Flow

```
User Uploads File → Frontend (Next.js)
    ↓
File Processing → Backend (FastAPI)
    ↓
Schema Generation → DuckDB + LLM
    ↓
User Query → Frontend
    ↓
[LangGraph State Machine]
    ↓
Input Node → Planner Node → Router → SQL Executor → Output Node
    ↑                                                           ↓
    └─── Clarification Loop (if needed) ← Clarification Node ←┘
    
    ↓
Insight Generator (LLM) → Final Answer → Frontend
```

### Directory Structure

```
├── README.md
├── backend/
│   ├── main.py                      # FastAPI application & session management
│   ├── insight_generator.py         # NLP-based insight generation
│   ├── llm_interface.py             # LLM communication utilities
│   ├── raw_metadata.json            # Auto-generated data schema
│   ├── schema_graph.json            # Table relationship graph
│   ├── requirements.txt             # Python dependencies
│   ├── data_ingestion/
│   │   ├── data_ingest.py          # File processing, schema extraction
│   │   └── graph_builder.py         # Table relationship inference
│   ├── llm/
│   │   ├── plan_generator.py       # LangGraph workflow & query planning
│   │   ├── interpretor.py          # SQL generation & execution
│   │   └── llm_tracker.py          # LLM usage logging
│   ├── utils/
│   │   ├── prisma_handler.py       # Database operations
│   │   ├── datasource_loader.py    # Data source management
│   │   └── cloudinary_handler.py   # File storage utilities
│   └── uploaded_files/             # Temporary file storage
├── my-app/                         # Next.js Frontend
│   ├── app/
│   │   ├── page.tsx                # Landing page
│   │   ├── dashboard/              # User dashboard
│   │   ├── chat/                   # Query interface
│   │   ├── upload-file/            # File upload
│   │   └── api/                    # API routes
│   ├── components/                 # Reusable UI components
│   ├── lib/                        # Utilities and configurations
│   ├── prisma/                     # Database schema
│   └── package.json                # Node.js dependencies
└── prisma/                         # Database migrations
    └── schema.prisma               # Prisma schema
```

---

## 🔧 Core Components

### 1. **Frontend** (`my-app/`)

**Next.js Application**
- **Landing Page**: Marketing site with demo animations
- **Authentication**: Clerk integration for user management
- **Dashboard**: View and manage uploaded data sources
- **Chat Interface**: Natural language query interface with session management
- **File Upload**: Drag-and-drop file upload with progress tracking
- **Responsive Design**: Built with Tailwind CSS and shadcn/ui components

**Key Features:**
- Real-time chat with typing indicators
- Session persistence across page reloads
- Clarification handling for ambiguous queries
- Result visualization and insights display

### 2. **Backend API** (`backend/`)

**`main.py`** - FastAPI Application
- Session-based conversation management
- File upload and processing endpoints
- Query processing with LangGraph integration
- Database operations via Prisma
- Cloud storage integration (Supabase)

**Endpoints:**
- `POST /upload_and_process` - Upload and process data files
- `POST /query` - Submit natural language queries
- `POST /clarify` - Handle clarification responses
- `POST /save_session` - Persist conversation sessions
- `GET /sessions` - Retrieve user sessions

### 3. **Data Ingestion** (`data_ingestion/`)

**`data_ingest.py`**
- Processes Excel/CSV files into Parquet format
- Extracts schema and generates metadata
- Uses LLM to create table summaries
- Handles column normalization and type inference

**`graph_builder.py`**
- Infers relationships between tables using LLM
- Creates schema graph for query planning
- Handles complex column names and data types

### 4. **LLM Pipeline** (`llm/`)

**`plan_generator.py`** - Query Planning Engine
- LangGraph state machine for workflow orchestration
- Multi-iteration planning with metadata retrieval
- Clarification handling for ambiguous queries
- Rate-limited LLM calls with retry logic

**`interpretor.py`** - SQL Execution Engine
- Generates DuckDB SQL from structured plans
- Executes queries with error handling
- Self-healing retries on execution failures
- Result formatting and validation

### 5. **Database & Storage**

**Prisma ORM** (`prisma/`)
- User management and authentication data
- Data source metadata and file references
- Session and conversation history
- Deployed on Neon (PostgreSQL)

**Supabase Storage**
- Secure file storage for uploaded datasets
- Automatic cleanup and access control
- Integration with Prisma for metadata linking

### 6. **Insight Generation** (`insight_generator.py`)

- Converts SQL results into natural language explanations
- Identifies trends, correlations, and anomalies
- Provides contextual insights based on data patterns

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
| **Frontend Framework** | Next.js 14, React 18 |
| **UI Library** | Tailwind CSS, shadcn/ui, Lucide Icons |
| **Authentication** | Clerk |
| **Backend Framework** | FastAPI |
| **Database** | Prisma ORM, Neon (PostgreSQL) |
| **File Storage** | Supabase Storage |
| **Workflow Orchestration** | LangGraph, LangChain |
| **LLM** | Google Gemini 2.5 Flash |
| **Data Processing** | DuckDB, Pandas |
| **Data Format** | Parquet, Excel, CSV |
| **Deployment** | Vercel (Frontend), Railway/Fly.io (Backend) |
| **Configuration** | Environment variables (.env) |

---

## ⚙️ Setup & Installation

### Prerequisites
- Node.js 18+
- Python 3.9+
- Google Gemini API key
- Supabase account
- Clerk account
- Neon database

### Backend Setup

```bash
# Navigate to backend directory
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
cp .env.example .env
# Edit .env with your API keys:
# GOOGLE_API_KEY=your_gemini_api_key
# SUPABASE_URL=your_supabase_url
# SUPABASE_ANON_KEY=your_supabase_anon_key
# DATABASE_URL=your_neon_database_url
```

### Frontend Setup

```bash
# Navigate to frontend directory
cd my-app

# Install dependencies
npm install

# Set environment variables
cp .env.example .env.local
# Edit .env.local with your keys:
# NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=your_clerk_publishable_key
# CLERK_SECRET_KEY=your_clerk_secret_key
# NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
# DATABASE_URL=your_neon_database_url
```

### Database Setup

```bash
# Install Prisma CLI globally
npm install -g prisma

# Navigate to frontend directory
cd my-app

# Generate Prisma client and run migrations
npx prisma generate
npx prisma db push

# Seed the database (if needed)
npx prisma db seed
```

### Running the Application

```bash
# Terminal 1: Start Backend
cd backend
python main.py
# Server runs on http://127.0.0.1:8000

# Terminal 2: Start Frontend
cd my-app
npm run dev
# App runs on http://localhost:3000
```

### Environment Variables

Create `.env` files in both `backend/` and `my-app/` directories:

**Backend (.env):**
```env
GOOGLE_API_KEY=your_gemini_api_key
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your_supabase_anon_key
DATABASE_URL=postgresql://user:password@host:port/database
```

**Frontend (.env.local):**
```env
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_...
CLERK_SECRET_KEY=sk_test_...
NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
DATABASE_URL=postgresql://user:password@host:port/database
```

---

## 📊 Usage

### Web Interface

1. **Sign Up/Login**: Use Clerk authentication on the landing page
2. **Upload Data**: Go to Upload File page, drag-and-drop Excel/CSV files
3. **Start Chatting**: Navigate to Chat page, select a data source, and ask questions
4. **View Results**: Get SQL queries, data results, and AI-generated insights

### Example Workflow

**Upload File:**
- User uploads `sales_data.xlsx`
- System processes file → Creates Parquet → Generates schema → Stores in Supabase
- Metadata saved to database for future queries

**Query Example:**
```
User: "What's the total revenue by product category?"

System Processing:
1. Planner generates SQL plan
2. Executor runs: SELECT category, SUM(revenue) FROM sales_data GROUP BY category
3. Insight generator analyzes results
4. Response: "Electronics leads with $500K revenue, followed by Clothing at $300K..."

Response includes:
- Executed SQL query
- Data table/chart
- Natural language insights
- Option to ask follow-up questions
```

### API Usage

**Upload File:**
```bash
curl -X POST "http://localhost:8000/upload_and_process" \
  -F "files=@data.xlsx" \
  -F "user_id=user123"
```

**Query Data:**
```bash
curl -X POST "http://localhost:8000/query" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "How many records are in the dataset?",
    "user_id": "user123",
    "data_source_id": "ds456"
  }'
```

**Response:**
```json
{
  "session_id": "sess789",
  "answer": "The dataset contains 1,250 records.",
  "sql_query": "SELECT COUNT(*) FROM table1",
  "insights": "This represents a substantial dataset for analysis...",
  "data": {"count": 1250}
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

### Backend (requirements.txt)
```txt
annotated-types==0.7.0
anyio==4.12.0
beautifulsoup4==4.14.3
certifi==2025.11.12
click==8.3.1
duckdb==1.4.2
fastapi==0.124.0
fsspec==2025.12.0
google-generativeai==0.8.5
grpcio==1.76.0
httpx==0.28.1
langchain-core==1.1.2
langgraph==1.0.4
numpy==2.3.5
openpyxl==3.1.5
pandas==2.3.3
prisma==0.15.0
pydantic==2.12.5
python-dotenv==1.2.1
supabase==2.25.1
tenacity==9.1.2
uvicorn==0.38.0
```

### Frontend (package.json)
```json
{
  "dependencies": {
    "@clerk/nextjs": "^4.29.9",
    "@prisma/client": "^5.11.0",
    "@radix-ui/react-dialog": "^1.0.5",
    "@radix-ui/react-dropdown-menu": "^2.0.6",
    "@radix-ui/react-select": "^2.0.0",
    "framer-motion": "^11.2.12",
    "lucide-react": "^0.344.0",
    "next": "14.1.0",
    "prisma": "^5.11.0",
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "tailwindcss": "^3.4.1",
    "typescript": "^5.3.3"
  }
}
```

---

## 🔐 Configuration

Create a `.env` file in `/backend`:

```env
GOOGLE_API_KEY=your_gemini_api_key_here
```

---

## 🚀 Deployment

### Frontend (Vercel)
```bash
cd my-app
npm run build
# Deploy to Vercel with environment variables set
```

### Backend (Railway/Fly.io)
```bash
cd backend
# Use Docker or direct deployment
# Set environment variables in hosting platform
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Guidelines
- Follow existing code style and patterns
- Add tests for new features
- Update documentation as needed
- Ensure all environment variables are properly configured

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Built with ❤️ to democratize data analysis
- Powered by Google's Gemini AI
- Thanks to the open-source community for amazing tools
