import os
from supabase import create_client, Client
from dotenv import load_dotenv
from typing import Dict, Any

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "nl-sql-query")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def upload_to_cloudinary(file_path: str) -> str:
    """
    Upload a file to Supabase Storage with validation.
    
    Args:
        file_path: Local path to the file
    
    Returns:
        Public URL of the uploaded file
    
    Raises:
        Exception: If upload fails
    """
    try:
        # Step 1: Validate file exists and is readable
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        if not os.path.isfile(file_path):
            raise ValueError(f"Path is not a file: {file_path}")
        
        # Step 2: Check file size
        file_size = os.path.getsize(file_path)
        max_upload_size = 500 * 1024 * 1024  # 500 MB limit
        
        if file_size == 0:
            raise ValueError(f"File is empty: {file_path}")
        
        if file_size > max_upload_size:
            raise ValueError(f"File too large ({file_size / (1024**2):.2f} MB). Max: {max_upload_size / (1024**2):.2f} MB")
        
        # Step 3: Check read permission
        if not os.access(file_path, os.R_OK):
            raise PermissionError(f"File is not readable: {file_path}")
        
        print(f"[SUPABASE] Validating upload for {os.path.basename(file_path)} ({file_size / (1024**2):.2f} MB)...")

        # Step 4: Upload to Supabase
        file_name = os.path.basename(file_path)
        storage_path = f"nl_sql_query/{file_name}"

        try:
            with open(file_path, "rb") as f:
                response = supabase.storage.from_(SUPABASE_BUCKET).upload(
                    path=storage_path,
                    file=f,
                    file_options={"upsert": "true"}
                )
            
            if not response:
                raise Exception("Upload returned empty response from Supabase")
            
            print(f"[SUPABASE] ✓ File uploaded successfully to {storage_path}")
        except Exception as upload_err:
            print(f"[SUPABASE] ✗ Upload failed: {upload_err}")
            raise

        # Step 5: Get public URL
        try:
            public_url = supabase.storage.from_(SUPABASE_BUCKET).get_public_url(storage_path)
            
            if not public_url:
                raise Exception("Failed to get public URL from Supabase")
            
            print(f"[SUPABASE] ✓ Public URL generated: {public_url}")
            return public_url
        except Exception as url_err:
            print(f"[SUPABASE] ✗ Failed to get public URL: {url_err}")
            
            # Try to rollback the upload
            try:
                print(f"[SUPABASE] Rolling back upload...")
                supabase.storage.from_(SUPABASE_BUCKET).remove([storage_path])
            except:
                print(f"[SUPABASE] ⚠️ Could not rollback upload")
            
            raise

    except Exception as e:
        print(f"[SUPABASE] ✗ Error uploading {file_path}: {str(e)}")
        raise

def deletefromsupabase(data_source) -> Dict[str, str]:
    """
    Delete file from Supabase Storage using the cloudinaryUrl from data_source.
    
    Args:
        data_source: Dict containing 'cloudinaryUrl' field, or None
        
    Returns:
        Dict with status and message
    """
    try:
        # ✅ FIX: Check if data_source is a dict and has the URL
        if not data_source or not isinstance(data_source, dict):
            return {"status": "error", "message": "Invalid data_source format"}
            
        cloudinary_url = data_source.get("cloudinaryUrl")
        if not cloudinary_url:
            return {"status": "error", "message": "No cloudinaryUrl found"}
        
        # Extract file path from URL (e.g., https://.../nl_sql_query/data__Sheet1.parquet)
        # ✅ HOW TO GET THE URL: Split on '/nl_sql_query/' and take the last part
        file_path = cloudinary_url.split("/nl_sql_query/")[-1]
        
        # Delete from Supabase
        supabase.storage.from_(SUPABASE_BUCKET).remove([f"nl_sql_query/{file_path}"])
        
        print(f"[DELETE] ✓ Deleted from Supabase: {file_path}")
        return {"status": "success", "message": f"Deleted {file_path}"}
    
    except Exception as e:
        print(f"[DELETE] ⚠ Supabase deletion failed: {str(e)}")
        return {"status": "error", "message": str(e)}