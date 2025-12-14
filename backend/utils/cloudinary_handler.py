import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "nl-sql-query")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def upload_to_cloudinary(file_path: str) -> str:
    """
    Upload a file to Supabase Storage and return the public URL.

    Args:
        file_path: Local path to the file

    Returns:
        Public URL of the uploaded file

    Raises:
        Exception: If upload fails
    """
    try:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        file_name = os.path.basename(file_path)
        storage_path = f"nl_sql_query/{file_name}"

        with open(file_path, "rb") as f:
            response = supabase.storage.from_(SUPABASE_BUCKET).upload(
                path=storage_path,
                file=f,
                file_options={"upsert": "true"}
            )

        public_url = supabase.storage.from_(SUPABASE_BUCKET).get_public_url(storage_path)

        if not public_url:
            raise Exception("Failed to get public URL from Supabase")

        print(f"[SUPABASE] ✓ Uploaded {file_path} → {public_url}")
        return public_url

    except Exception as e:
        print(f"[SUPABASE] ✗ Error uploading {file_path}: {str(e)}")
        raise
