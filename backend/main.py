# main.py
from fastapi import FastAPI, HTTPException, UploadFile, File, Form  # Add Form import
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uuid
from typing import List, Dict, Any
import os
import json
import logging
import shutil
import httpx
import psycopg2
from psycopg2.extras import RealDictCursor  # Add this import
import pandas as pd
from data_ingestion.data_ingest import load_excel_folder, build_initial_schema_object
from data_ingestion.graph_builder import process_schema_build
from llm.plan_generator import build_graph, State
import asyncio
from utils.cloudinary_handler import upload_to_cloudinary
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

# Upload directory
UPLOAD_DIR = "uploaded_files"
os.makedirs(UPLOAD_DIR, exist_ok=True)

def get_db_connection():
    return psycopg2.connect(os.getenv("DATABASE_URL"))
# Session store with conversation history
SESSIONS = {}  # {session_id: {"conversation_history": [...], "last_result": ..., "clarification_state": ...}}

def save_state(session_id: str, state: dict):
    """Save state for clarification flow."""
    if session_id not in SESSIONS:
        SESSIONS[session_id] = {"conversation_history": [], "last_result": None, "clarification_state": None}
    SESSIONS[session_id]["clarification_state"] = state

def load_state(session_id: str) -> dict | None:
    """Load clarification state."""
    session = SESSIONS.get(session_id)
    if session:
        return session.get("clarification_state")
    return None

def get_session(session_id: str) -> dict | None:
    """Get full session data."""
    return SESSIONS.get(session_id)

def create_session() -> str:
    """Create new session with empty history."""
    session_id = str(uuid.uuid4())
    SESSIONS[session_id] = {
        "conversation_history": [],  # [{"role": "user"/"assistant", "content": "..."}]
        "last_result": None,         # Last SQL result for context
        "last_plan": None,           # Last plan for context
        "clarification_state": None  # State during clarification
    }
    return session_id

def update_session_history(session_id: str, user_msg: str, assistant_msg: str, sql_result: str = None, plan: dict = None):
    """Update session with new conversation turn."""
    if session_id not in SESSIONS:
        SESSIONS[session_id] = {"conversation_history": [], "last_result": None, "clarification_state": None}
    
    SESSIONS[session_id]["conversation_history"].append({"role": "user", "content": user_msg})
    SESSIONS[session_id]["conversation_history"].append({"role": "assistant", "content": assistant_msg[:1000]})  # Truncate long responses
    
    if sql_result:
        SESSIONS[session_id]["last_result"] = sql_result
    if plan:
        SESSIONS[session_id]["last_plan"] = plan

def build_context_prompt(session_id: str, current_question: str) -> str:
    """Build question with conversation context."""
    session = get_session(session_id)
    if not session:
        return current_question
    
    history = session.get("conversation_history", [])
    
    # ✅ CHANGED: Get last 4 messages (2 exchanges) instead of 6
    recent_messages = history[-4:]
    
    context_parts = []
    if recent_messages:
        context_parts.append("=== CONVERSATION HISTORY ===")
        for msg in recent_messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            # ✅ CHANGED: Truncate to 200 chars instead of 300
            if len(content) > 200:
                content = content[:197] + "..."
            context_parts.append(f"{role.capitalize()}: {content}")
    
    # ✅ REMOVED: Previous query result section entirely
    
    context_parts.append(f"\n=== CURRENT QUESTION ===\n{current_question}")
    
    return "\n".join(context_parts)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DataIngestRequest(BaseModel):
    folder_path: str

class BuildSchemaRequest(BaseModel):
    session_id: str
    user_explanation: str
    previous_answers: List[Dict[str, Any]] = []

@app.post("/data_ingest")
def data_ingest(request: DataIngestRequest):
    try:
        logger.info(f"Starting data ingestion for folder: {request.folder_path}")
        if not os.path.exists("raw_metadata.json"):
            logger.info("raw_metadata.json does not exist, proceeding with ingestion")
            tables, schema = load_excel_folder(request.folder_path)
            logger.info(f"Loaded schema: {schema}")
            initial_schema = build_initial_schema_object(schema)
            logger.info(f"Built initial schema: {initial_schema}")
            with open("raw_metadata.json", "w") as f:
                json.dump(initial_schema, f, indent=4)
            logger.info("raw_metadata.json written successfully")
            return {"status": "success", "message": "Data ingested successfully", "initial_schema": initial_schema}
        else:
            logger.info("raw_metadata.json already exists")
            return {"status": "success", "message": "Data already ingested"}
    except Exception as e:
        logger.error(f"Error during data ingestion: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

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
        # Load existing session into memory
        SESSIONS[session_id] = {
            "conversation_history": existing_session.get("conversationHistory", []),
            "last_result": existing_session.get("lastResult"),
            "last_plan": existing_session.get("lastPlan"),
            "clarification_state": None
        }
    else:
        print(f"[QUERY] Creating new session...")
        session_id = create_session()
        print(f"[QUERY] ✓ Created new session: {session_id}")

    state = State({
        "user_question": question,
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

    # Success - update history
    update_session_history(
        session_id, 
        question, 
        final_state.get("final_answer", ""),
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
    
    # Verify session exists
    session = get_session(session_id)
    if not session:
        return {"error": "Invalid or expired session_id. Use /query to start a new conversation."}
    
    print(f"[DEBUG] Continuing session: {session_id}")
    print(f"[DEBUG] History length: {len(session.get('conversation_history', []))}")
    
    # Build question with context
    contextualized_question = build_context_prompt(session_id, question)
    print(f"[DEBUG] Contextualized question: {contextualized_question[:200]}...")

    state = State({
        "user_question": contextualized_question,
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

    # Success - update history with original question (not contextualized)
    update_session_history(
        session_id, 
        question,  # Store original question, not contextualized
        final_state.get("final_answer", ""),
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

    state_data = load_state(session_id)
    if not state_data:
        return {"error": "Invalid or expired session_id, or no pending clarification"}

    state = State(state_data)

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

    # Success - update history
    # Extract original question (before clarification was appended)
    original_question = state_data.get("user_question", "").split("===")[0].strip()
    update_session_history(
        session_id, 
        f"{original_question} (clarified: {answer})",
        final_state.get("final_answer", ""),
        final_state.get("sql_result"),
        final_state.get("planner_output")
    )
    
    # Clear clarification state
    if session_id in SESSIONS:
        SESSIONS[session_id]["clarification_state"] = None

    return {
        "status": "completed",
        "session_id": session_id,
        "answer": final_state.get("final_answer"),
        "insights": final_state.get("insights")
    }

@app.post("/session/history")
def get_history(req: dict):
    """Get conversation history for a session."""
    session_id = req.get("session_id")
    if not session_id:
        return {"error": "session_id is required"}
    
    session = get_session(session_id)
    if not session:
        return {"error": "Invalid or expired session_id"}
    
    return {
        "session_id": session_id,
        "history": session.get("conversation_history", []),
        "message_count": len(session.get("conversation_history", []))
    }

@app.post("/session/clear")
def clear_session(req: dict):
    """Clear a session's history."""
    session_id = req.get("session_id")
    if session_id and session_id in SESSIONS:
        del SESSIONS[session_id]
        return {"status": "cleared", "session_id": session_id}
    return {"status": "not_found"}

@app.get("/sessions")
def list_sessions():
    """List all active sessions (for debugging)."""
    return {
        "active_sessions": len(SESSIONS),
        "session_ids": list(SESSIONS.keys())
    }

@app.post("/build_schema")
def build_schema(request: BuildSchemaRequest):
    try:
        response = process_schema_build(request.session_id, request.user_explanation, request.previous_answers)
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/save_session")
async def save_session(req: dict):
    """
    Save session state to Neon DB.
    Called when user closes chat.
    Saves to both Session and Conversation tables.
    Cleans up uploaded files and JSON metadata files after saving.
    
    Args:
        - session_id: Session ID to save
        - user_id: User ID for verification
        - data_source_id: DataSource ID for verification
        - conversation_history: Array of messages
        - last_result: Last SQL result (optional)
        - last_plan: Last plan (optional)
    
    Returns:
        {status: "success", message: "Session saved"}
    """
    try:
        session_id = req.get("session_id")
        user_id = req.get("user_id")
        data_source_id = req.get("data_source_id")
        conversation_history = req.get("conversation_history", [])
        last_result = req.get("last_result")
        last_plan = req.get("last_plan")
        
        if not session_id or not user_id or not data_source_id:
            raise HTTPException(
                status_code=400,
                detail="session_id, user_id, and data_source_id are required"
            )
        
        print(f"[SAVE_SESSION] Persisting session {session_id} to database...")
        print(f"[SAVE_SESSION] Conversation history: {len(conversation_history)} messages")
        
        # Convert to proper JSON format
        history_json = json.dumps(conversation_history) if conversation_history else json.dumps([])
        last_result_json = json.dumps(last_result) if last_result else None
        last_plan_json = json.dumps(last_plan) if last_plan else None
        
        # Update session in database
        conn = get_db_connection()
        with conn.cursor() as cur:
            # Step 1: Verify the session exists
            cur.execute(
                "SELECT id FROM \"Session\" WHERE id = %s AND \"userId\" = %s AND \"dataSourceId\" = %s",
                (session_id, user_id, data_source_id)
            )
            session_exists = cur.fetchone()
            
            if not session_exists:
                print(f"[SAVE_SESSION] ⚠ Session not found: {session_id}")
                conn.close()
                raise HTTPException(
                    status_code=404,
                    detail="Session not found"
                )
            
            # Step 2: Update the Session table
            cur.execute(
                """
                UPDATE "Session" 
                SET "conversationHistory" = %s, 
                    "lastResult" = %s, 
                    "lastPlan" = %s, 
                    "updatedAt" = NOW()
                WHERE id = %s AND "userId" = %s AND "dataSourceId" = %s
                """,
                (
                    history_json,
                    last_result_json,
                    last_plan_json,
                    session_id,
                    user_id,
                    data_source_id
                )
            )
            
            session_rows_affected = cur.rowcount
            
            # Step 3: Check if conversation record exists
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
                # Update existing conversation
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
        
        conn.commit()
        conn.close()
        
        print(f"[SAVE_SESSION] ✓ Session saved: {session_id} (rows updated: {session_rows_affected})")
        print(f"[SAVE_SESSION] ✓ Conversation saved (rows affected: {conversation_rows_affected})")
        
        # Step 4: Clean up files
        print(f"[SAVE_SESSION] Cleaning up files...")
        
        # Delete uploaded_files folder
        if os.path.exists(UPLOAD_DIR):
            try:
                shutil.rmtree(UPLOAD_DIR)
                print(f"[SAVE_SESSION] ✓ Deleted uploaded_files folder")
            except Exception as e:
                print(f"[SAVE_SESSION] ⚠ Failed to delete uploaded_files: {e}")
        
        # Delete raw_metadata.json
        if os.path.exists("raw_metadata.json"):
            try:
                os.remove("raw_metadata.json")
                print(f"[SAVE_SESSION] ✓ Deleted raw_metadata.json")
            except Exception as e:
                print(f"[SAVE_SESSION] ⚠ Failed to delete raw_metadata.json: {e}")
        
        # Delete final_graph.json
        if os.path.exists("final_graph.json"):
            try:
                os.remove("final_graph.json")
                print(f"[SAVE_SESSION] ✓ Deleted final_graph.json")
            except Exception as e:
                print(f"[SAVE_SESSION] ⚠ Failed to delete final_graph.json: {e}")
        
        # Recreate empty uploaded_files folder for next session
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        
        return {
            "status": "success",
            "message": "Session and Conversation saved, files cleaned up successfully",
            "session_id": session_id,
            "messages_saved": len(conversation_history)
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
    temp_folder = None
    parquet_path = None
    data_source_id = None
    
    try:
        if not user_id:
            raise HTTPException(status_code=400, detail="user_id is required")
        
        # Step 1: Create temporary folder for this upload
        import tempfile
        temp_folder = tempfile.mkdtemp(prefix="nl_sql_upload_")
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
        
        # Step 3: Generate schema graph (Parquet + graph) - Fix unpacking
        print(f"[UPLOAD] Processing schema and converting to Parquet...")
        result = process_schema_build(temp_folder)  # Returns dict, not tuple
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
        
        # Use the first parquet file (or combine if multiple)
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
        
        # Step 7: Delete Parquet file after successful upload
        if os.path.exists(parquet_path):
            os.remove(parquet_path)
            print(f"[UPLOAD] ✓ Deleted Parquet: {parquet_path}")
        
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
        
        # Clean up temp folder
        if temp_folder and os.path.exists(temp_folder):
            shutil.rmtree(temp_folder)
            print(f"[UPLOAD] ✓ Cleaned up temp folder")
        
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
        
        # Step 6: Clean up in-memory sessions
        for session_id in session_ids:
            if session_id in SESSIONS:
                del SESSIONS[session_id]
                print(f"[DELETE] ✓ Cleaned up in-memory session: {session_id}")
        
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
        
        # Step 3: Download Parquet from Cloudinary
        print(f"[INIT] Downloading Parquet from Cloudinary...")
        parquet_path = os.path.join("uploaded_files", f"datasource_{data_source_id}.parquet")
        await download_from_cloudinary(
            data_source["cloudinaryUrl"],
            parquet_path
        )
        
        # Step 4: Write metadata and schema graph JSON files
        print(f"[INIT] Writing schema files...")
        file_paths = load_datasource_files(
            data_source["rawMetadata"],
            data_source["schemaGraph"]
        )
        
        # Step 5: Handle session (resume existing or create new)
        conversation_history = []
        last_result = None
        last_plan = None
        
        if existing_session:
            print(f"[INIT] Resuming existing session: {existing_session['id']}")
            session_data = dict(existing_session)
            conversation_history = session_data.get("conversationHistory", [])
            last_result = session_data.get("lastResult")
            last_plan = session_data.get("lastPlan")
            final_session_id = existing_session['id']
            
            # ✅ NEW: Load session into memory
            SESSIONS[final_session_id] = {
                "conversation_history": conversation_history,
                "last_result": last_result,
                "last_plan": last_plan,
                "clarification_state": None
            }
            print(f"[INIT] Loaded session into memory")
        else:
            print(f"[INIT] Creating new session...")
            new_session_id = str(uuid.uuid4())
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO "Session" (id, "userId", "dataSourceId", "conversationHistory", "updatedAt")
                    VALUES (%s, %s, %s, %s, NOW())
                    """,
                    (new_session_id, user_id, data_source_id, json.dumps([]))
                )
            conn.commit()
            final_session_id = new_session_id
            print(f"[INIT] Created new session: {final_session_id}")
        
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

# Keep old endpoints for backward compatibility (mark as deprecated)
# @app.post("/upload")
# async def upload_files(files: List[UploadFile] = File(...)):
#     """[DEPRECATED] Use /upload_and_process instead."""
#     try:
#         uploaded_info = []
        
#         for file in files:
#             if not file.filename.endswith(('.xlsx', '.xls', '.csv')):
#                 return {"error": f"Invalid file type: {file.filename}. Only .xlsx, .xls, .csv allowed."}
            
#             file_path = os.path.join(UPLOAD_DIR, file.filename)
#             with open(file_path, "wb") as f:
#                 shutil.copyfileobj(file.file, f)
            
#             if file.filename.endswith('.csv'):
#                 df = pd.read_csv(file_path)
#             else:
#                 df = pd.read_excel(file_path)
            
#             uploaded_info.append({
#                 "filename": file.filename,
#                 "shape": df.shape,
#                 "columns": list(df.columns),
#                 "preview": df.head(5).to_dict(orient="records")
#             })
            
#             logger.info(f"Uploaded file: {file.filename} (shape: {df.shape})")
        
#         return {
#             "status": "success",
#             "message": f"Uploaded {len(files)} file(s)",
#             "files": uploaded_info
#         }
#     except Exception as e:
#         logger.error(f"Error uploading files: {str(e)}")
#         raise HTTPException(status_code=500, detail=str(e))

# @app.post("/ingest_uploaded")
# def ingest_uploaded_files():
#     """Process uploaded files and create schema + normalize to Parquet."""
#     try:
#         print("[INGEST] Starting ingestion of uploaded files...", flush=True)
#         logger.info("Starting ingestion of uploaded files...")
        
#         if not os.path.exists("raw_metadata.json"):
#             # Load Excel/CSV files
#             print("[INGEST] Loading Excel/CSV files from uploaded_files...", flush=True)
#             logger.info("Loading Excel/CSV files from uploaded_files...")
#             tables, schema = load_excel_folder(UPLOAD_DIR)
#             print(f"[INGEST] ✓ Loaded {len(tables)} tables", flush=True)
#             logger.info(f"Loaded schema from uploaded files: {schema}")
            
#             logger.info(f"Built initial schema")
            
#             process_schema_build(UPLOAD_DIR)
#             print("[INGEST] ✓ Schema processed and Parquet files created", flush=True)
#             logger.info("raw_metadata.json created and schema processed successfully")
            
#             return {
#                 "status": "success",
#                 "message": "Files ingested and normalized successfully",
#             }
#         else:
#             print("[INGEST] ⚠️ raw_metadata.json already exists", flush=True)
#             logger.info("raw_metadata.json already exists")
#             return {
#                 "status": "success",
#                 "message": "Metadata already exists. Clear and re-upload to update.",
#                 "action": "existing_schema"
#             }
#     except Exception as e:
#         print(f"[INGEST] ❌ Error: {str(e)}", flush=True)
#         logger.error(f"Error ingesting uploaded files: {str(e)}")
#         raise HTTPException(status_code=500, detail=str(e))

@app.post("/clear_uploaded")
def clear_uploaded_files():
    """Clear uploaded files and metadata."""
    try:
        # Clear upload directory
        for file in os.listdir(UPLOAD_DIR):
            file_path = os.path.join(UPLOAD_DIR, file)
            if os.path.isfile(file_path):
                os.remove(file_path)
        
        # Clear metadata
        if os.path.exists("raw_metadata.json"):
            os.remove("raw_metadata.json")
        
        logger.info("Cleared uploaded files and metadata")
        
        return {"status": "success", "message": "Files and metadata cleared"}
    except Exception as e:
        logger.error(f"Error clearing files: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)