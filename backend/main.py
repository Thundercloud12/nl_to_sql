# main.py
# Remove unused imports
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uuid
from typing import List, Dict, Any
import os
import json
import logging
import shutil
import tempfile
import psycopg2
from psycopg2.extras import RealDictCursor

from data_ingestion.graph_builder import process_schema_build
from llm.plan_generator import build_graph, State
import asyncio
from utils.cloudinary_handler import upload_to_cloudinary, deletefromsupabase
from utils.prisma_handler import PrismaHandler
from utils.datasource_loader import download_from_cloudinary, load_datasource_files

app = FastAPI()
url=os.getenv("NEXT_JS_API_URL")
# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501", "http://127.0.0.1:8501", "http://localhost:3000", url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "uploaded_files"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Add constant for max total size
MAX_TOTAL_SIZE = 100 * 1024 * 1024  # 100 MB

def get_db_connection():
    return psycopg2.connect(os.getenv("DATABASE_URL"))

SESSIONS = {}  # Deprecated - kept for compatibility only

def load_session_from_db(session_id: str) -> dict | None:
    """Load full session data from database."""
    try:
        conn = get_db_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM \"Session\" WHERE id = %s",
                (session_id,)
            )
            session_row = cur.fetchone()
        conn.close()
        return dict(session_row) if session_row else None
    except Exception as e:
        print(f"[SESSION] Error loading from DB: {e}")
        return None

def save_session_to_db(session_id: str, conversation_history: list, last_result: dict = None, last_plan: dict = None):
    """Write session data directly to database."""
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            history_json = json.dumps(conversation_history)
            last_result_json = json.dumps(last_result) if last_result else None
            last_plan_json = json.dumps(last_plan) if last_plan else None
            
            cur.execute(
                """
                UPDATE "Session" 
                SET "conversationHistory" = %s, 
                    "lastResult" = %s, 
                    "lastPlan" = %s,
                    "updatedAt" = NOW()
                WHERE id = %s
                """,
                (history_json, last_result_json, last_plan_json, session_id)
            )
        conn.commit()
        conn.close()
        print(f"[SESSION] ✓ Session {session_id} saved to DB")
    except Exception as e:
        print(f"[SESSION] Error saving to DB: {e}")
        raise

def save_state(session_id: str, state: dict):
    """Save clarification state to database."""
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            clarification_json = json.dumps(state)
            cur.execute(
                "UPDATE \"Session\" SET \"clarificationState\" = %s, \"updatedAt\" = NOW() WHERE id = %s",
                (clarification_json, session_id)
            )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[SESSION] Error saving clarification state: {e}")

def load_state(session_id: str) -> dict | None:
    """Load clarification state from database."""
    session = load_session_from_db(session_id)
    if session:
        clarification_state = session.get("clarificationState")
        if isinstance(clarification_state, str):
            return json.loads(clarification_state)
        return clarification_state
    return None

def create_session(user_id: str, data_source_id: str) -> str:
    """Create new session in database."""
    session_id = str(uuid.uuid4())
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO "Session" (id, "userId", "dataSourceId", "conversationHistory", "updatedAt")
                VALUES (%s, %s, %s, %s, NOW())
                """,
                (session_id, user_id, data_source_id, json.dumps([]))
            )
        conn.commit()
        conn.close()
        print(f"[QUERY] ✓ Created new session: {session_id}")
        return session_id
    except Exception as e:
        print(f"[SESSION] Error creating session: {e}")
        raise

def build_context_prompt(session_id: str, current_question: str) -> str:
    """Build question with conversation context from database."""
    session = load_session_from_db(session_id)
    if not session:
        return current_question
    
    # Load conversation history from DB
    history = session.get("conversationHistory", [])
    if isinstance(history, str):
        history = json.loads(history)
    
    # Get last 4 messages (2 exchanges) for context
    recent_messages = history[-4:]
    
    context_parts = []
    if recent_messages:
        context_parts.append("=== CONVERSATION HISTORY ===")
        for msg in recent_messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if len(content) > 200:
                content = content[:197] + "..."
            context_parts.append(f"{role.capitalize()}: {content}")
    
    context_parts.append(f"\n=== CURRENT QUESTION ===\n{current_question}")
    
    return "\n".join(context_parts)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)





@app.post("/query")
def query(req: dict):
    """Start a new conversation - checks for existing session first."""
    question = req.get("question")
    user_id = req.get("user_id")  # NEW: Add user_id
    data_source_id = req.get("data_source_id")  # NEW: Add data_source_id
    
    if not question:
        raise HTTPException(status_code=400, detail="question is required")
    if not user_id or not data_source_id:
        raise HTTPException(status_code=400, detail="user_id and data_source_id are required")
    
    print(f"[QUERY] Received question: {question}")
    print(f"[QUERY] User: {user_id}, DataSource: {data_source_id}")
    
    # Check for existing session first
    conn = get_db_connection()
    existing_session = None
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT * FROM \"Session\" WHERE \"userId\" = %s AND \"dataSourceId\" = %s ORDER BY \"createdAt\" DESC LIMIT 1",
            (user_id, data_source_id)
        )
        existing_session = cur.fetchone()
    conn.close()
    
    if existing_session:
        print(f"[QUERY] ✓ Found existing session: {existing_session['id']}")
        session_id = existing_session['id']
    else:
        print(f"[QUERY] Creating new session...")
        session_id = create_session(user_id, data_source_id)

    state = State({
        "user_question": question,
        "data_source_id": data_source_id,  # ✅ Add data_source_id
        "schema_info": None,
        "planner_output": None,
        "sql_result": None,
        "clarification_answer": None,
        "metadata_requests": [],
        "insights": None,
        "final_answer": None,
        "status": "running",
        "pending_question": None,
        "appended_data": "",
    })
    graph = build_graph()

    final_state = graph.invoke(state)
    print(f"[DEBUG] Final state: {final_state}")

    # Handle clarification
    if final_state.get("status") == "need_clarification":
        save_state(session_id, dict(final_state))
        
        planner_output = final_state.get("planner_output", {})
        clarification_questions = planner_output.get("clarification_questions", [])
        
        return {
            "status": "need_clarification",
            "session_id": session_id,
            "question": final_state.get("pending_question"),
            "all_questions": clarification_questions
        }

    # Success - save to database and return response
    # Load current conversation history from DB
    current_session = load_session_from_db(session_id)
    current_history = current_session.get("conversationHistory", []) if current_session else []
    if isinstance(current_history, str):
        current_history = json.loads(current_history)
    
    # Append new messages to history
    current_history.append({"role": "user", "content": question})
    current_history.append({"role": "assistant", "content": final_state.get("final_answer", "")[:1000]})
    
    # Save updated session to database
    save_session_to_db(
        session_id,
        current_history,
        final_state.get("sql_result"),
        final_state.get("planner_output")
    )

    return {
        "status": "completed",
        "session_id": session_id,
        "answer": final_state.get("final_answer"),
        "insights": final_state.get("insights")
    }

@app.post("/continue")
def continue_conversation(req: dict):
    """Continue an existing conversation with context."""
    session_id = req.get("session_id")
    question = req.get("question")
    
    if not session_id:
        return {"error": "session_id is required"}
    if not question:
        return {"error": "question is required"}
    
    # Verify session exists - load from DB
    session = load_session_from_db(session_id)
    if not session:
        return {"error": "Invalid or expired session_id. Use /query to start a new conversation."}
    
    history = session.get("conversationHistory", [])
    if isinstance(history, str):
        history = json.loads(history)
    
    print(f"[DEBUG] Continuing session: {session_id}")
    print(f"[DEBUG] History length: {len(history)}")
    
    # Build question with context
    contextualized_question = build_context_prompt(session_id, question)
    print(f"[DEBUG] Contextualized question: {contextualized_question[:200]}...")
    
    # Get data_source_id from session
    data_source_id = session.get("dataSourceId")
    if not data_source_id:
        return {"error": "data_source_id not found in session"}

    state = State({
        "user_question": contextualized_question,
        "data_source_id": data_source_id,  # ✅ Add data_source_id
        "schema_info": None,
        "planner_output": None,
        "sql_result": None,
        "clarification_answer": None,
        "metadata_requests": [],
        "insights": None,
        "final_answer": None,
        "status": "running",
        "pending_question": None,
        "appended_data": "",
    })
    graph = build_graph()

    final_state = graph.invoke(state)
    print(f"[DEBUG] Final state: {final_state}")

    # Handle clarification
    if final_state.get("status") == "need_clarification":
        save_state(session_id, dict(final_state))
        
        planner_output = final_state.get("planner_output", {})
        clarification_questions = planner_output.get("clarification_questions", [])
        
        return {
            "status": "need_clarification",
            "session_id": session_id,
            "question": final_state.get("pending_question"),
            "all_questions": clarification_questions
        }

    # Success - save to database with original question (not contextualized)
    current_session = load_session_from_db(session_id)
    current_history = current_session.get("conversationHistory", []) if current_session else []
    if isinstance(current_history, str):
        current_history = json.loads(current_history)
    
    # Append new messages to history
    current_history.append({"role": "user", "content": question})
    current_history.append({"role": "assistant", "content": final_state.get("final_answer", "")[:1000]})
    
    # Save updated session to database
    save_session_to_db(
        session_id,
        current_history,
        final_state.get("sql_result"),
        final_state.get("planner_output")
    )

    return {
        "status": "completed",
        "session_id": session_id,
        "answer": final_state.get("final_answer"),
        "insights": final_state.get("insights")
    }

@app.post("/clarify")
def clarify(req: dict):
    """Handle clarification response."""
    session_id = req.get("session_id")
    answer = req.get("answer")
    
    if not session_id or not answer:
        return {"error": "session_id and answer are required"}

    # Load clarification state from DB
    session = load_session_from_db(session_id)
    if not session:
        return {"error": "Invalid or expired session_id"}
    
    state_data = session.get("clarificationState")
    if not state_data:
        return {"error": "No pending clarification for this session"}
    
    # Get data_source_id from session
    data_source_id = session.get("dataSourceId")
    if not data_source_id:
        return {"error": "data_source_id not found in session"}

    state = State(state_data)
    state["data_source_id"] = data_source_id  # ✅ Ensure data_source_id is in state

    # Inject answer into question
    pending_q = state.get('pending_question', '')
    state["user_question"] += f" {pending_q} {answer}"
    state["clarification_answer"] = answer

    # Reset clarification flags
    state["pending_question"] = None
    state["status"] = "running"
    
    # Reset planner_output clarification flags
    if state.get("planner_output"):
        state["planner_output"]["needs_clarification"] = False
        state["planner_output"]["clarification_questions"] = []
    
    graph = build_graph()
    final_state = graph.invoke(state)

    # Clarification needed again
    if final_state.get("status") == "need_clarification":
        save_state(session_id, dict(final_state))
        
        planner_output = final_state.get("planner_output", {})
        clarification_questions = planner_output.get("clarification_questions", [])
        
        return {
            "status": "need_clarification",
            "session_id": session_id,
            "question": final_state.get("pending_question"),
            "all_questions": clarification_questions
        }

    # Success - save to database
    current_session = load_session_from_db(session_id)
    current_history = current_session.get("conversationHistory", []) if current_session else []
    if isinstance(current_history, str):
        current_history = json.loads(current_history)
    
    # Append clarification answer to history
    current_history.append({"role": "user", "content": f"Clarification: {answer}"})
    current_history.append({"role": "assistant", "content": final_state.get("final_answer", "")[:1000]})
    
    # Save updated session to database
    save_session_to_db(
        session_id,
        current_history,
        final_state.get("sql_result"),
        final_state.get("planner_output")
    )
    
    # Clear clarification state in DB
    save_state(session_id, None)

    return {
        "status": "completed",
        "session_id": session_id,
        "answer": final_state.get("final_answer"),
        "insights": final_state.get("insights")
    }

@app.post("/save_session")
async def save_session(req: Request):
    try:
        body = await req.body()
        req = json.loads(body.decode("utf-8"))

        session_id = req.get("session_id")
        user_id = req.get("user_id")
        data_source_id = req.get("data_source_id")
        
        if not session_id or not user_id or not data_source_id:
            raise HTTPException(
                status_code=400,
                detail="session_id, user_id, and data_source_id are required"
            )
        
        print(f"[SAVE_SESSION] Cleaning up files for session {session_id}...")
        
        # Verify the session exists (for authorization)
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM \"Session\" WHERE id = %s AND \"userId\" = %s AND \"dataSourceId\" = %s",
                (session_id, user_id, data_source_id)
            )
            session_exists = cur.fetchone()
        
        if not session_exists:
            conn.close()
            raise HTTPException(
                status_code=404,
                detail="Session not found"
            )
        
        conn.close()
        
        # Clean up datasource-specific folder only
        print(f"[SAVE_SESSION] Cleaning up files for datasource: {data_source_id}...")
        
        datasource_folder = os.path.join("uploaded_files", f"datasource_{data_source_id}")
        if os.path.exists(datasource_folder):
            try:
                shutil.rmtree(datasource_folder)
                print(f"[SAVE_SESSION] ✓ Deleted datasource folder: {datasource_folder}")
            except Exception as e:
                print(f"[SAVE_SESSION] ⚠ Failed to delete datasource folder: {e}")
        
        return {
            "status": "success",
            "message": "Files cleaned up successfully",
            "session_id": session_id
        }
    
    except HTTPException as e:
        print(f"[SAVE_SESSION] ✗ Error: {str(e)}", flush=True)
        raise e
    except Exception as e:
        print(f"[SAVE_SESSION] ✗ Error: {str(e)}", flush=True)
        logger.error(f"Error cleaning up session: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))



@app.post("/upload_and_process")
async def upload_and_process(
    files: List[UploadFile] = File(...),
    user_id: str = Form(...)  # Fix: Use Form to extract from multipart data
):
    """
    Unified endpoint: Upload files → Generate metadata → Upload to Cloudinary → Save to DB.
    
    Args:
        files: List of Excel/CSV files
        user_id: Clerk user ID from form data
    
    Returns:
        {status, data_source_id, cloudinary_url, raw_metadata, schema_graph}
    """
    data_source_id = None
    
    try:
        if not user_id:
            raise HTTPException(status_code=400, detail="user_id is required")

        total_size = 0
        for file in files:
            file.file.seek(0, 2)      # move to end
            file_size = file.file.tell()
            file.file.seek(0)         # reset pointer
            total_size += file_size
        
        if total_size > MAX_TOTAL_SIZE:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"Total file size ({total_size / (1024 * 1024):.2f} MB) "
                    f"exceeds the limit of {MAX_TOTAL_SIZE / (1024 * 1024):.2f} MB."
                ),
            )
        
        # Use TemporaryDirectory for automatic cleanup
        import tempfile
        with tempfile.TemporaryDirectory(prefix="nl_sql_upload_") as temp_folder:
            print(f"[UPLOAD] Created temp folder: {temp_folder}")
            
            # Step 2: Save uploaded files to temp folder
            uploaded_files = []
            for file in files:
                if not file.filename.endswith(('.xlsx', '.xls', '.csv')):
                    raise HTTPException(
                        status_code=400, 
                        detail=f"Invalid file type: {file.filename}. Only .xlsx, .xls, .csv allowed."
                    )
                
                file_path = os.path.join(temp_folder, file.filename)
                with open(file_path, "wb") as f:
                    shutil.copyfileobj(file.file, f)
                uploaded_files.append(file_path)
                print(f"[UPLOAD] ✓ Saved {file.filename} to temp folder")
            
            # Step 3: Generate schema graph (Parquet + graph)
            print(f"[UPLOAD] Processing schema and converting to Parquet...")
            result = process_schema_build(temp_folder)  # Returns dict
            initial_schema = result["raw_metadata"]
            schema_graph = result["schema_graph"]
            print(f"[UPLOAD] ✓ Generated schema graph")
            
            # Step 4: Find the Parquet file
            parquet_files = []
            for root, dirs, files_list in os.walk(temp_folder):
                for fname in files_list:
                    if fname.endswith('.parquet'):
                        parquet_files.append(os.path.join(root, fname))
            
            if not parquet_files:
                raise Exception("No Parquet files generated during processing")
            
            # Use the first parquet file
            parquet_path = parquet_files[0]
            print(f"[UPLOAD] Found Parquet: {parquet_path}")
            
            # Step 5: Upload Parquet to Cloudinary
            print(f"[UPLOAD] Uploading to Cloudinary...")
            cloudinary_url = upload_to_cloudinary(parquet_path)
            print(f"[UPLOAD] ✓ Cloudinary URL: {cloudinary_url}")
            
            # Step 6: Save to Neon DB via Prisma
            print(f"[UPLOAD] Saving to database...")
            db_response = await PrismaHandler.save_datasource_to_db(
                user_id=user_id,
                cloudinary_url=cloudinary_url,
                raw_metadata=initial_schema,
                schema_graph=schema_graph
            )
            data_source_id = db_response.get("id")
            print(f"[UPLOAD] ✓ Saved to DB with ID: {data_source_id}")
            
            # Success response
            return {
                "status": "success",
                "data_source_id": data_source_id,
                "cloudinary_url": cloudinary_url,
                "raw_metadata": initial_schema,
                "schema_graph": schema_graph
            }
    
    except Exception as e:
        print(f"[UPLOAD] ✗ Error: {str(e)}", flush=True)
        
        # Rollback: Delete from DB if insertion succeeded but later steps failed
        if data_source_id:
            print(f"[UPLOAD] Rolling back database insertion...")
            await PrismaHandler.delete_datasource(data_source_id)
        
        logger.error(f"Error in upload_and_process: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))



@app.delete("/datasource/{data_source_id}")
async def delete_datasource(data_source_id: str, user_id: str):
    """
    Delete a DataSource and all associated Sessions and Conversations.
    Also cleans up any in-memory sessions.
    
    Args:
        - data_source_id: ID of DataSource to delete
        - user_id: User ID for authorization
    
    Returns:
        {status: "success", message: "DataSource deleted", deleted_sessions: X, deleted_conversations: Y}
    """
    try:
        if not data_source_id or not user_id:
            raise HTTPException(
                status_code=400,
                detail="data_source_id and user_id are required"
            )
        
        print(f"[DELETE] Deleting DataSource: {data_source_id} for user: {user_id}")
        
        conn = get_db_connection()
        
        # Step 1: Verify DataSource exists and belongs to user
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT id FROM \"DataSource\" WHERE id = %s AND \"userId\" = %s",
                (data_source_id, user_id)
            )
            data_source = cur.fetchone()
        
        if not data_source:
            conn.close()
            raise HTTPException(
                status_code=404,
                detail="DataSource not found or unauthorized"
            )
        
        # Step 2: Get all session IDs for this data source (to clean up memory)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT id FROM \"Session\" WHERE \"dataSourceId\" = %s",
                (data_source_id,)
            )
            session_rows = cur.fetchall()
            session_ids = [row['id'] for row in session_rows]
        
        # Step 3: Delete associated Conversations
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM \"Conversation\" WHERE \"dataSourceId\" = %s",
                (data_source_id,)
            )
            conversations_deleted = cur.rowcount
            print(f"[DELETE] ✓ Deleted {conversations_deleted} Conversation(s)")
        
        # Step 4: Delete associated Sessions
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM \"Session\" WHERE \"dataSourceId\" = %s",
                (data_source_id,)
            )
            sessions_deleted = cur.rowcount
            print(f"[DELETE] ✓ Deleted {sessions_deleted} Session(s)")
        
        with conn.cursor(cursor_factory=RealDictCursor) as cur:  # ✅ ADD: RealDictCursor
            cur.execute(
                "SELECT \"cloudinaryUrl\" FROM \"DataSource\" WHERE id = %s AND \"userId\" = %s",
                (data_source_id, user_id)
            )
            data_source = cur.fetchone()

        # In the delete route
        result = deletefromsupabase(data_source)
        if result["status"] == "error":
            print(f"[DELETE] {result['message']}")
        

        # Step 5: Delete the DataSource itself
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM \"DataSource\" WHERE id = %s AND \"userId\" = %s",
                (data_source_id, user_id)
            )
            datasource_deleted = cur.rowcount
        
        conn.commit()
        conn.close()
        
        if datasource_deleted == 0:
            raise HTTPException(
                status_code=500,
                detail="Failed to delete DataSource"
            )
        
        print(f"[DELETE] ✓ Deleted DataSource: {data_source_id}")
        
        return {
            "status": "success",
            "message": "DataSource and all associated data deleted successfully",
            "data_source_id": data_source_id,
            "deleted_sessions": sessions_deleted,
            "deleted_conversations": conversations_deleted
        }
    
    except HTTPException as e:
        print(f"[DELETE] ✗ Error: {str(e)}", flush=True)
        raise e
    except Exception as e:
        print(f"[DELETE] ✗ Error: {str(e)}", flush=True)
        logger.error(f"Error deleting datasource: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))




@app.post("/initialize_chat")
async def initialize_chat(req: dict):
    """
    Initialize chat session with DataSource (backend-only).
    Loads Parquet from Cloudinary, writes metadata/graph JSON files, handles sessions.
    
    Args:
        - data_source_id: ID of DataSource to load
        - user_id: User ID (for DB verification)
    
    Returns:
        {
            status: "success",
            session_id: "new or existing session ID",
            conversation_history: [...],
            last_result: {...},
            last_plan: {...},
            parquet_path: "path to downloaded parquet",
            metadata_loaded: true,
            graph_loaded: true
        }
    """
    try:
        data_source_id = req.get("data_source_id")
        user_id = req.get("user_id")
        
        if not data_source_id or not user_id:
            raise HTTPException(
                status_code=400,
                detail="data_source_id and user_id are required"
            )
        
        print(f"[INIT] Initializing chat for DataSource: {data_source_id}")
        
        # Step 1: Fetch DataSource from DB directly
        conn = get_db_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM \"DataSource\" WHERE id = %s AND \"userId\" = %s",
                (data_source_id, user_id)
            )
            data_source_row = cur.fetchone()
        
        if not data_source_row:
            raise Exception("DataSource not found or unauthorized")
        
        data_source = dict(data_source_row)
        
        # Step 2: Check for existing session (latest for this user + data source)
        existing_session = None
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM \"Session\" WHERE \"userId\" = %s AND \"dataSourceId\" = %s ORDER BY \"createdAt\" DESC LIMIT 1",
                (user_id, data_source_id)
            )
            existing_session = cur.fetchone()
        
        # Step 3: Download Parquet from Cloudinary to datasource-specific folder
        print(f"[INIT] Downloading Parquet from Cloudinary...")
        datasource_dir = os.path.join("uploaded_files", f"datasource_{data_source_id}")
        os.makedirs(datasource_dir, exist_ok=True)
        parquet_path = os.path.join(datasource_dir, "data.parquet")
        await download_from_cloudinary(
            data_source["cloudinaryUrl"],
            parquet_path
        )
        
        # Step 4: Write metadata and schema graph JSON files to datasource-specific folder
        print(f"[INIT] Writing schema files...")
        file_paths = load_datasource_files(
            data_source_id,
            data_source["rawMetadata"],
            data_source["schemaGraph"]
        )
        
        # Step 5: Handle session (resume existing or create new)
        conversation_history = []
        last_result = None
        last_plan = None
        
        if existing_session:
            print(f"[INIT] Resuming existing session: {existing_session['id']}")
            final_session_id = existing_session['id']
            conversation_history = existing_session.get("conversationHistory", [])
            if isinstance(conversation_history, str):
                conversation_history = json.loads(conversation_history)
            last_result = existing_session.get("lastResult")
            last_plan = existing_session.get("lastPlan")
        else:
            print(f"[INIT] Creating new session...")
            final_session_id = create_session(user_id, data_source_id)
            conversation_history = []
            last_result = None
            last_plan = None
        
        conn.close()
        
        return {
            "status": "success",
            "session_id": final_session_id,
            "conversation_history": conversation_history,
            "last_result": last_result,
            "last_plan": last_plan,
            "parquet_path": parquet_path,
            "metadata_loaded": os.path.exists(file_paths["metadata_path"]),
            "graph_loaded": os.path.exists(file_paths["graph_path"]),
            "message": "Chat initialized successfully"
        }
    
    except Exception as e:
        print(f"[INIT] ✗ Error: {str(e)}", flush=True)
        logger.error(f"Error initializing chat: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))



if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)