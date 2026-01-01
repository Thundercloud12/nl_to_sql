
# 🚀 RELIX - Natural Language to SQL

Transform data questions into AI-driven SQL queries through conversational intelligence.

---

## 📋 What It Does

Upload data files (Excel, CSV) → Ask questions in English → Get SQL results + AI insights. No SQL knowledge required.

**Key Features**:
- 🎯 Natural language query interface
- 📁 Auto schema detection & metadata generation
- 🔄 Multi-turn conversations with context awareness
- ❓ Smart clarification for ambiguous queries
- 💬 LLM-powered result summarization
- 🔐 Multi-tenant with Clerk auth
- 🌗 Universal Light/Dark theme toggle (next-themes, Tailwind)
- 🗄️ **NEW:** Direct PostgreSQL database connections (query live databases)

---


## 🖌️ New UI/UX Features

- **Light/Dark Theme Toggle**: All pages now support instant switching between true light and true dark modes. Toggle is available on landing, dashboard, chat, upload, sign-in, and sign-up pages.
- **Theme Persistence**: User preference is saved and restored automatically.
- **Modern Color Palette**: Professional, high-contrast colors for accessibility and aesthetics.
- **Animated Toggle Button**: Sun/Moon icon with smooth transitions.

---

## 🏗️ Architecture at a Glance

```
User Query → FastAPI Backend → LangGraph Workflow → SQL Execution (DuckDB or PostgreSQL) → Gemini Insights → Response
```

### Data Flow
```
1. FILE Mode: File Upload → Convert to Parquet → Generate Schema (DuckDB + LLM)
2. DATABASE Mode: Connect Database → Fetch Schema (PostgreSQL) → Store Metadata
3. User Query → LangGraph State Machine → Intelligent Routing
4. Planner LLM → Generate Execution Plan (tables, filters, aggregations)
5. Execute SQL (DuckDB for files, PostgreSQL for databases) → Generate Insights → Return to User
```

---

## 🌟 LangGraph Workflow (Core Intelligence)

**8 Nodes in Intelligent Sequence**:

| Node | Purpose | Decision |
|------|---------|----------|
| **Input** | Validate query | → Planner |
| **Planner** ⭐ | LLM generates SQL plan | Router decides next step |
| **Router** | Conditional branching | 5 possible routes |
| **Clarify** | Ask user questions | → END |
| **Schema** | Fetch table details | → Planner (loop) |
| **Preprocess** | Data transformations | → SQL Executor |
| **SQL Executor** | Execute on DuckDB | → Output |
| **Output** | Format results + insights | → END |

### Router Logic
```python
if plan.needs_clarification:
    → user_clarification (ask user)
elif plan.metadata_requests:
    → schema_info (fetch + replan)
elif plan.preprocessing_operations:
    → preprocessing (clean data)
elif plan.execution_mode == "sql":
    → sql_executor (execute)
else:
    → output (direct response)
```

### Example Plan (Planner Output)
```json
{
  "tables": ["sales"],
  "filters": ["date >= '2025-10-01'"],
  "operations": ["AVG(amount)"],
  "group_by": ["category"],
  "preprocessing_operations": [
    {"type": "fill_nulls", "column": "amount", "method": "mean"}
  ],
  "execution_mode": "sql"
}
```

---

## 📁 Project Structure

```
backend/                    # FastAPI + LangGraph
├── main.py               # Endpoints, session management
├── data_ingestion/
│   └── graph_builder.py  # Parquet conversion, schema generation
├── llm/
│   ├── plan_generator.py # ⭐ LangGraph workflow (8 nodes)
│   ├── interpretor.py    # SQL execution
│   └── llm_tracker.py    # LLM analytics
└── utils/                # Rate limiting, DB, cloud storage

my-app/                    # Next.js Frontend
├── app/
│   ├── page.tsx          # Landing page
│   ├── chat/             # Query interface
│   ├── upload-file/      # File upload
│   └── api/              # Backend routes
└── components/           # UI components
```

---


## 💻 Tech Stack

**Backend**: FastAPI, LangGraph 1.0, Gemini API, DuckDB, PostgreSQL, Supabase   
**Frontend**: Next.js 16, React 19, TypeScript, Tailwind CSS, Clerk auth, next-themes

---


## 🚀 Quick Start

### Backend
```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# .env
GOOGLE_API_KEY=your_key
DATABASE_URL=postgresql://...
SUPABASE_URL=supabase://...

uvicorn main:app --reload --port 8000
```

### Frontend
```bash
cd my-app
npm install

# .env.local
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=your_key
NEXT_PUBLIC_API_URL=http://localhost:8000

npm run dev  # http://localhost:3000
```

---

## 📊 Query Execution Flow

**User asks**: "Average revenue by region in Q4?"

1. **Planner Node** (LLM) → Understands intent
   - Tables: `[sales]`
   - Filters: `[date BETWEEN '2025-10-01' AND '2025-12-31']`
   - Operations: `[AVG(revenue)]`
   - Group: `[region]`

2. **Router** → `execution_mode = "sql"` → Routes to SQL Executor

3. **SQL Executor**
   ```sql
   SELECT region, AVG(revenue)
   FROM sales
   WHERE date BETWEEN '2025-10-01' AND '2025-12-31'
   GROUP BY region
   ```

4. **Output Node** → Gemini LLM converts results to insights
   - "North leads with $2,450 avg (40% higher than West)..."

5. **Return** → Results + Insights + Save to session history

---

## 🔄 Multi-Turn with Clarification

If query is ambiguous:

1. **Planner** detects ambiguity → `needs_clarification = True`
2. **Router** → Clarification Node
3. **Clarification Node** → Sends question to user
4. **User responds** → Context appended → Planner replans

**Example**:
```
System: "Define 'recent' - last week or month?"
User:   "Last 30 days"
→ Replans with clarification context
```

---

## 🔐 Security & Multi-Tenancy

- Clerk authentication
- All queries filtered by `user_id` + `data_source_id`
- Per-datasource session isolation
- Secure file storage (Supabase )

---

## ⚡ Performance

- **Parquet files** - 10x faster than CSV
- **DuckDB** - In-process SQL (no latency)
- **Row limiting** - Schema on 10K rows max
- **Rate limiting** - ~50 LLM calls/min
- **Connection reuse** - Avoid repeated loads

---

## 📊 Data Ingestion Pipeline

```
1. Upload File (Excel/CSV)
   ↓
2. Convert to Parquet (memory-efficient)
   ↓
3. Build Schema via DuckDB
   - Detect types
   - Normalize columns
   - Sample rows
   ↓
4. Generate Metadata (LLM)
   - Table summaries
   - Relationship detection
   ↓
5. Store
   - Parquet → Supabase 
   - Metadata → PostgreSQL
```

---

## 🛠️ API Endpoints

**Files**: 
- `POST /upload_and_process` - Upload CSV/Excel files
- `POST /connect_database` - Connect PostgreSQL database
- `POST /test_db_connection` - Test database credentials

**Queries**: 
- `POST /query` - Execute natural language query
- `POST /continue_conversation` - Multi-turn conversation
- `POST /clarify` - Answer clarification questions

**Sessions**: 
- `POST /save_session` - Save conversation state
- `POST /initialize_chat` - Start new chat session

**Data Sources**:
- `GET /datasource/{id}` - Get datasource details
- `DELETE /datasource/{id}` - Delete datasource

---

## 📈 Error Handling

- SQL validation before execution
- Type coercion (auto-convert strings to numbers)
- NULL handling via preprocessing
- Missing column detection → requests schema
- Failed queries → retry with corrections
- Ambiguous queries → ask user

---

## 🎯 Future Roadmap

- [ ] Multi-step joins with relationship inference
- [ ] Chart/visualization generation
- [ ] Scheduled queries & alerts
- [ ] Advanced caching
- [ ] Federated queries (multiple datasources)
- [ ] Explainability reports

---

## 📄 Monitoring

**LLM Tracking** (`llm_tracker.py`):
- Calls per query
- Token usage
- Latency
- Cost estimation

---


## 🤝 Contributing

1. Create feature branch: `git checkout -b feature/your-feature`
2. Make changes
3. Submit PR

---

## 📝 Recent Changes

### Database Connection Feature (v2.0)
- **Direct PostgreSQL Support**: Connect your own databases and query them in natural language
- **New Pages**: `/connect-database` with credential testing and validation
- **Dashboard Updates**: Separate icons for FILE (FileSpreadsheet) and DATABASE (Database) sources
- **Navbar Updates**: Added "Upload File" and "Connect Database" buttons
- **Backend Infrastructure**: PostgreSQLConnectionManager with schema extraction
- **API Endpoints**: `/test_db_connection`, `/connect_database`, `/fetch_db_schema`
- **Prisma Schema**: Extended DataSource model with connection fields

### Theme System (v1.5)
- Added universal light/dark theme toggle (next-themes, Tailwind)
- Created ThemeProvider and ThemeToggle components
- Integrated toggle on all pages (landing, dashboard, chat, upload, sign-in, sign-up)
- Updated all hardcoded colors to use theme-aware CSS variables
- Improved accessibility and color contrast

---

**Built with ❤️ using LangGraph, DuckDB, PostgreSQL, Gemini API, and next-themes**
