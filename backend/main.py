from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uuid
from typing import List, Dict, Any
import os
import tempfile
import json
import logging
import shutil
import tempfile
import psycopg2
from psycopg2.extras import RealDictCursor
from pathlib import Path
from data_ingestion.graph_builder import process_schema_build
from llm.plan_generator import build_graph, State

from utils.cloudinary_handler import upload_to_cloudinary, deletefromsupabase
from utils.prisma_handler import PrismaHandler
from utils.datasource_loader import download_from_cloudinary, load_datasource_files, load_chat, ensure_datasource_files
from utils.database_utilities import get_db_connection, db_connection, db_cursor, PostgreSQLConnectionManager

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

MAX_TOTAL_SIZE = 100 * 1024 * 1024  

SESSIONS = {}  

def load_session_from_db(session_id: str) -> dict | None:
    """Load full session data from database."""
    try:
        with db_cursor() as cur:
            cur.execute(
                "SELECT * FROM \"Session\" WHERE id = %s",
                (session_id,)
            )
            session_row = cur.fetchone()
        return dict(session_row) if session_row else None
    except Exception as e:
        print(f"[SESSION] Error loading from DB: {e}")
        return None

def save_session_to_db(session_id: str, conversation_history: list, last_result: dict = None, last_plan: dict = None):
    """Write session data directly to database."""
    try:
        with db_cursor(commit=True) as cur:
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
        print(f"[SESSION] ✓ Session {session_id} saved to DB")
    except Exception as e:
        print(f"[SESSION] Error saving to DB: {e}")
        raise

def save_state(session_id: str, state: dict):
    """Save clarification state to database."""
    try:
        with db_cursor(commit=True) as cur:
            clarification_json = json.dumps(state)
            cur.execute(
                "UPDATE \"Session\" SET \"clarificationState\" = %s, \"updatedAt\" = NOW() WHERE id = %s",
                (clarification_json, session_id)
            )
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
        with db_cursor(commit=True) as cur:
            cur.execute(
                """
                INSERT INTO "Session" (id, "userId", "dataSourceId", "conversationHistory", "updatedAt")
                VALUES (%s, %s, %s, %s, NOW())
                """,
                (session_id, user_id, data_source_id, json.dumps([]))
            )
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
    
    history = session.get("conversationHistory", [])
    if isinstance(history, str):
        history = json.loads(history)

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


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============ HEALTH CHECK ENDPOINT ============


# ============================================


@app.post("/query")
def query(req: dict):
    """Start a new conversation - checks for existing session first."""
    question = req.get("question")
    user_id = req.get("user_id")  
    data_source_id = req.get("data_source_id")  
    
    if not question:
        raise HTTPException(status_code=400, detail="question is required")
    if not user_id or not data_source_id:
        raise HTTPException(status_code=400, detail="user_id and data_source_id are required")
    
    print(f"[QUERY] Received question: {question}")
    print(f"[QUERY] User: {user_id}, DataSource: {data_source_id}")
    existing_session = None
    with db_cursor() as cur:
        cur.execute(
            "SELECT * FROM \"Session\" WHERE \"userId\" = %s AND \"dataSourceId\" = %s ORDER BY \"createdAt\" DESC LIMIT 1",
            (user_id, data_source_id)
        )
        existing_session = cur.fetchone()
    
    if existing_session:
        print(f"[QUERY] ✓ Found existing session: {existing_session['id']}")
        session_id = existing_session['id']
    else:
        print(f"[QUERY] Creating new session...")
        session_id = create_session(user_id, data_source_id)

    with db_cursor() as cur:
        cur.execute("SELECT * FROM \"DataSource\" WHERE id = %s", (data_source_id,))
        data_source = cur.fetchone()
    
    if not data_source:
        raise HTTPException(status_code=404, detail="DataSource not found")
    
    connection_type = data_source.get("connectionType", "FILE")
    print(f"[QUERY] Connection type: {connection_type}")
    
    # For FILE datasources, ensure files are present
    if connection_type == "FILE":
        ensure_datasource_files(data_source)
    
    # For DATABASE datasources, prepare db_config
    db_config = None
    if connection_type == "DATABASE":
        db_config = {
            "host": data_source.get("dbHost"),
            "port": data_source.get("dbPort"),
            "database": data_source.get("dbName"),
            "username": data_source.get("dbUsername"),
            "password": data_source.get("dbPassword"),
        }
        print(f"[QUERY] Using database: {db_config['host']}/{db_config['database']}")

    state = State({
        "user_question": question,
        "data_source_id": data_source_id,  
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
        "connection_type": connection_type,
        "db_config": db_config,
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


    current_session = load_session_from_db(session_id)
    current_history = current_session.get("conversationHistory", []) if current_session else []
    if isinstance(current_history, str):
        current_history = json.loads(current_history)

    current_history.append({"role": "user", "content": question})
    current_history.append({"role": "assistant", "content": final_state.get("final_answer", "")[:1000]})
    
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


@app.get("/health")
def health():
    """
    Lightweight health check endpoint.
    Used for:
    - Cold start detection
    - Server warm-up before uploads
    - Monitoring uptime
    
    Returns immediately with minimal overhead.
    """
    return {"status": "awake"}

@app.post("/continue")
def continue_conversation(req: dict):
    """Continue an existing conversation with context."""
    session_id = req.get("session_id")
    question = req.get("question")
    
    if not session_id:
        return {"error": "session_id is required"}
    if not question:
        return {"error": "question is required"}

    session = load_session_from_db(session_id)
    if not session:
        return {"error": "Invalid or expired session_id. Use /query to start a new conversation."}
    
    history = session.get("conversationHistory", [])
    if isinstance(history, str):
        history = json.loads(history)
    
    print(f"[DEBUG] Continuing session: {session_id}")
    print(f"[DEBUG] History length: {len(history)}")

    contextualized_question = build_context_prompt(session_id, question)
    print(f"[DEBUG] Contextualized question: {contextualized_question[:200]}...")

    data_source_id = session.get("dataSourceId")
    if not data_source_id:
        return {"error": "data_source_id not found in session"}
    
    with db_cursor() as cur:
        cur.execute("SELECT * FROM \"DataSource\" WHERE id = %s", (data_source_id,))
        data_source = cur.fetchone()
    
    if not data_source:
        return {"error": "DataSource not found"}
    ensure_datasource_files(data_source)
    
    state = State({
        "user_question": contextualized_question,
        "data_source_id": data_source_id,  
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

    current_session = load_session_from_db(session_id)
    current_history = current_session.get("conversationHistory", []) if current_session else []
    if isinstance(current_history, str):
        current_history = json.loads(current_history)

    current_history.append({"role": "user", "content": question})
    current_history.append({"role": "assistant", "content": final_state.get("final_answer", "")[:1000]})

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
    state["data_source_id"] = data_source_id 

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


    current_session = load_session_from_db(session_id)
    current_history = current_session.get("conversationHistory", []) if current_session else []
    if isinstance(current_history, str):
        current_history = json.loads(current_history)

    current_history.append({"role": "user", "content": f"Clarification: {answer}"})
    current_history.append({"role": "assistant", "content": final_state.get("final_answer", "")[:1000]})

    save_session_to_db(
        session_id,
        current_history,
        final_state.get("sql_result"),
        final_state.get("planner_output")
    )

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
        req_data = json.loads(body.decode("utf-8"))

        session_id = req_data.get("session_id")
        user_id = req_data.get("user_id")
        data_source_id = req_data.get("data_source_id")
        conversation_history = req_data.get("conversation_history", [])
        
        if not session_id or not user_id or not data_source_id:
            raise HTTPException(
                status_code=400,
                detail="session_id, user_id, and data_source_id are required"
            )
        
        print(f"[SAVE_SESSION] Saving conversation for session {session_id}...")

        history_json = json.dumps(conversation_history)

        with db_cursor(commit=True) as cur:
            cur.execute(
                """
                SELECT id FROM "Conversation" 
                WHERE "userId" = %s AND "dataSourceId" = %s
                ORDER BY "createdAt" DESC LIMIT 1
                """,
                (user_id, data_source_id)
            )
            existing_conversation = cur.fetchone()
            
            if existing_conversation:
                print(f"[SAVE_SESSION] Updating existing Conversation record...")
                cur.execute(
                    """
                    UPDATE "Conversation" 
                    SET messages = %s, "updatedAt" = NOW()
                    WHERE "userId" = %s AND "dataSourceId" = %s
                    """,
                    (history_json, user_id, data_source_id)
                )
                conversation_rows_affected = cur.rowcount
            else:
                # Create new conversation record
                print(f"[SAVE_SESSION] Creating new Conversation record...")
                conversation_id = str(uuid.uuid4())
                cur.execute(
                    """
                    INSERT INTO "Conversation" (id, "userId", "dataSourceId", messages, "updatedAt")
                    VALUES (%s, %s, %s, %s, NOW())
                    """,
                    (conversation_id, user_id, data_source_id, history_json)
                )
                conversation_rows_affected = cur.rowcount
        
        print(f"[SAVE_SESSION] ✓ Conversation saved/updated ({conversation_rows_affected} row(s) affected)")
        
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
            "message": "Conversation saved and files cleaned up successfully",
            "session_id": session_id
        }
    
    except HTTPException as e:
        print(f"[SAVE_SESSION] ✗ Error: {str(e)}", flush=True)
        raise e
    except Exception as e:
        print(f"[SAVE_SESSION] ✗ Error: {str(e)}", flush=True)
        logger.error(f"Error saving session: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))



@app.post("/upload_and_process")
async def upload_and_process(
    files: List[UploadFile] = File(...),
    user_id: str = Form(...)  
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
            file.file.seek(0, 2)      
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
        
        with tempfile.TemporaryDirectory(prefix="nl_sql_upload_") as temp_folder:
            print(f"[UPLOAD] Created temp folder: {temp_folder}")
            

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
                
                # Rename file to include user_id before processing
                
                original_stem = Path(file.filename).stem
                suffix = Path(file.filename).suffix
                new_filename = f"{original_stem}_{user_id}{suffix}"
                new_file_path = os.path.join(temp_folder, new_filename)
                os.rename(file_path, new_file_path)
                
                uploaded_files.append(new_file_path)
                print(f"[UPLOAD] ✓ Saved and renamed {file.filename} to {new_filename}")
            
  
            print(f"[UPLOAD] Processing schema and converting to Parquet...")
            result = process_schema_build(temp_folder)  # Returns dict
            initial_schema = result["raw_metadata"]
            schema_graph = result["schema_graph"]
            print(f"[UPLOAD] ✓ Generated schema graph")
            
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
        
        # Perform all delete operations in a single transaction
        with db_cursor(commit=True) as cur:

            cur.execute(
                "SELECT id, \"cloudinaryUrl\" FROM \"DataSource\" WHERE id = %s AND \"userId\" = %s",
                (data_source_id, user_id)
            )
            data_source = cur.fetchone()
            
            if not data_source:
                raise HTTPException(
                    status_code=404,
                    detail="DataSource not found or unauthorized"
                )
            
            cloudinary_url = data_source['cloudinaryUrl']

            cur.execute(
                "SELECT id FROM \"Session\" WHERE \"dataSourceId\" = %s",
                (data_source_id,)
            )
            session_rows = cur.fetchall()

            cur.execute(
                "DELETE FROM \"Conversation\" WHERE \"dataSourceId\" = %s",
                (data_source_id,)
            )
            conversations_deleted = cur.rowcount
            print(f"[DELETE] ✓ Deleted {conversations_deleted} Conversation(s)")

            cur.execute(
                "DELETE FROM \"Session\" WHERE \"dataSourceId\" = %s",
                (data_source_id,)
            )
            sessions_deleted = cur.rowcount
            print(f"[DELETE] ✓ Deleted {sessions_deleted} Session(s)")

            cur.execute(
                "DELETE FROM \"DataSource\" WHERE id = %s AND \"userId\" = %s",
                (data_source_id, user_id)
            )
            datasource_deleted = cur.rowcount
            
            if datasource_deleted == 0:
                raise HTTPException(
                    status_code=500,
                    detail="Failed to delete DataSource"
                )
        
        result = deletefromsupabase({"cloudinaryUrl": cloudinary_url})
        if result["status"] == "error":
            print(f"[DELETE] {result['message']}")
        
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

        result = await load_chat(data_source_id, user_id)
        data_source = result["data_source"]
        existing_session = result["existing_session"]
        existing_conversation = result["existing_conversation"]
        parquet_path = result["parquet_path"]
        file_paths = result["file_paths"]

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

        if existing_conversation:
            messages_field = existing_conversation.get('messages', [])
            if isinstance(messages_field, str):
                conversation_history = json.loads(messages_field)
            else:
                conversation_history = messages_field
        
        print(f"[INIT] Conversation history loaded: {len(conversation_history)} messages")
        
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



# ============================================================================
# DATABASE CONNECTION ENDPOINTS
# ============================================================================

class DatabaseConnectionRequest(BaseModel):
    host: str
    port: int
    database: str
    username: str
    password: str
    user_id: str
    display_name: str = None

@app.post("/test_db_connection")
async def test_db_connection(req: DatabaseConnectionRequest):
    """
    Test PostgreSQL database connection credentials.
    
    Args:
        - host: Database host
        - port: Database port
        - database: Database name
        - username: Database username
        - password: Database password
    
    Returns:
        {success: true/false, message: "Connection status"}
    """
    try:
        result = PostgreSQLConnectionManager.test_connection(
            host=req.host,
            port=req.port,
            database=req.database,
            username=req.username,
            password=req.password
        )
        return result
    except Exception as e:
        logger.error(f"Error testing database connection: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/connect_database")
async def connect_database(req: DatabaseConnectionRequest):
    """
    Connect to a PostgreSQL database and save as a datasource.
    
    Args:
        - host, port, database, username, password: DB credentials
        - user_id: User ID for ownership
        - display_name: Optional friendly name
    
    Returns:
        {success: true, data_source_id: "...", schema: {...}}
    """
    try:
        # Test connection first
        test_result = PostgreSQLConnectionManager.test_connection(
            host=req.host,
            port=req.port,
            database=req.database,
            username=req.username,
            password=req.password
        )
        
        if not test_result.get("success"):
            raise HTTPException(status_code=400, detail=test_result.get("message"))
        
        # Fetch schema
        schema_result = PostgreSQLConnectionManager.fetch_database_schema(
            host=req.host,
            port=req.port,
            database=req.database,
            username=req.username,
            password=req.password
        )
        
        if not schema_result.get("success"):
            raise HTTPException(status_code=400, detail=schema_result.get("message"))
        
        schema = schema_result.get("schema")
        
        # Save to database
        with db_cursor(commit=True) as cur:
            data_source_id = str(uuid.uuid4())
            display_name = req.display_name or f"{req.database}@{req.host}"
            
            cur.execute(
                """
                INSERT INTO "DataSource" 
                (id, "userId", "connectionType", "dbType", "dbHost", "dbPort", "dbName", 
                 "dbUsername", "dbPassword", "displayName", "rawMetadata", "schemaGraph", "createdAt")
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                RETURNING id
                """,
                (
                    data_source_id,
                    req.user_id,
                    "DATABASE",
                    "postgresql",
                    req.host,
                    req.port,
                    req.database,
                    req.username,
                    req.password,  # TODO: Encrypt in production
                    display_name,
                    json.dumps(schema),
                    json.dumps(schema)
                )
            )
        
        print(f"[DB_CONNECT] Created DataSource: {data_source_id} for user: {req.user_id}")
        
        return {
            "success": True,
            "data_source_id": data_source_id,
            "display_name": display_name,
            "schema": schema,
            "message": "Database connected successfully"
        }
    
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error connecting database: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/fetch_db_schema/{data_source_id}")
async def fetch_db_schema(data_source_id: str, user_id: str):
    """
    Fetch schema for an existing database datasource.
    
    Args:
        - data_source_id: DataSource ID
        - user_id: User ID for authorization
    
    Returns:
        {success: true, schema: {...}}
    """
    try:
        with db_cursor() as cur:
            cur.execute(
                """
                SELECT "dbHost", "dbPort", "dbName", "dbUsername", "dbPassword", "rawMetadata"
                FROM "DataSource"
                WHERE id = %s AND "userId" = %s AND "connectionType" = 'DATABASE'
                """,
                (data_source_id, user_id)
            )
            datasource = cur.fetchone()
        
        if not datasource:
            raise HTTPException(status_code=404, detail="Database datasource not found")
        
        # Return cached schema or fetch fresh
        schema = datasource.get("rawMetadata")
        if isinstance(schema, str):
            schema = json.loads(schema)
        
        return {"success": True, "schema": schema}
    
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error fetching schema: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)