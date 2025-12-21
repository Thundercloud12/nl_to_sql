import httpx
import os
import json
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

# Use your Next.js backend URL for Prisma calls
NEXT_JS_API_URL = os.getenv("NEXT_JS_API_URL", "http://localhost:3000")

class PrismaHandler:
    """Handle database operations via Next.js Prisma API"""
    
    @staticmethod
    async def save_datasource_to_db(
        user_id: str,
        cloudinary_url: str,
        raw_metadata: dict,
        schema_graph: dict
    ) -> dict:
        """
        Save DataSource to Neon DB via Next.js API with validation.
        """
        try:
            # Step 1: Validate inputs
            print("[PRISMA] Step 1: Validating inputs...")
            
            if not user_id or not isinstance(user_id, str):
                raise ValueError("user_id must be a non-empty string")
            
            if not cloudinary_url or not isinstance(cloudinary_url, str):
                raise ValueError("cloudinary_url must be a non-empty string")
            
            if not cloudinary_url.startswith("http"):
                raise ValueError(f"cloudinary_url is not a valid URL: {cloudinary_url}")
            
            if not isinstance(raw_metadata, dict):
                raise ValueError("raw_metadata must be a dict")
            
            if not isinstance(schema_graph, dict):
                raise ValueError("schema_graph must be a dict")
            
            if not raw_metadata.get("tables"):
                print("[PRISMA] ⚠️ raw_metadata has no tables, but proceeding...")
            
            print("[PRISMA] ✓ Input validation passed")
            
            # Step 2: Prepare payload
            print("[PRISMA] Step 2: Preparing payload...")
            
            payload = {
                "userId": user_id,
                "cloudinaryUrl": cloudinary_url,
                "rawMetadata": raw_metadata,
                "schemaGraph": schema_graph
            }
            
            # Step 3: Send to API
            print(f"[PRISMA] Step 3: Sending request to {NEXT_JS_API_URL}/api/datasources/create")
            
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{NEXT_JS_API_URL}/api/datasources/create",
                        json=payload,
                        timeout=30.0
                    )
            except httpx.TimeoutException:
                raise Exception("Request timed out after 30 seconds. Database may be slow.")
            except httpx.ConnectError:
                raise Exception(f"Could not connect to {NEXT_JS_API_URL}. Is the Next.js server running?")
            except Exception as req_err:
                raise Exception(f"HTTP request failed: {str(req_err)}")
            
            # Step 4: Validate response
            print(f"[PRISMA] Step 4: Validating response (status: {response.status_code})...")
            
            if response.status_code not in [200, 201]:
                print(f"[PRISMA] ✗ API returned {response.status_code}")
                print(f"[PRISMA] Response body: {response.text[:500]}")
                raise Exception(f"API error {response.status_code}: {response.text}")
            
            try:
                data = response.json()
            except Exception as json_err:
                print(f"[PRISMA] ✗ Could not parse JSON response: {json_err}")
                raise Exception(f"Invalid JSON response: {response.text[:200]}")
            
            # Step 5: Validate response data
            if not data.get("id"):
                print(f"[PRISMA] ✗ No 'id' in response: {data}")
                raise Exception("API did not return a data_source_id")
            
            datasource_id = data.get("id")
            print(f"[PRISMA] ✓ DataSource created with ID: {datasource_id}")
            
            return data

        except Exception as e:
            print(f"[PRISMA] ✗ Error saving DataSource: {str(e)}")
            raise

    @staticmethod
    async def delete_datasource(data_source_id: str) -> bool:
        """
        Delete a DataSource (for rollback on failure).
        
        Args:
            data_source_id: ID of DataSource to delete
        
        Returns:
            True if successful, False otherwise
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.delete(
                    f"{NEXT_JS_API_URL}/api/datasources/{data_source_id}",
                    timeout=30.0
                )
            
            if response.status_code == 200:
                print(f"[PRISMA] ✓ DataSource deleted (rollback): {data_source_id}")
                return True
            else:
                print(f"[PRISMA] ⚠️ Failed to delete DataSource: {response.status_code}")
                return False
        
        except Exception as e:
            print(f"[PRISMA] ✗ Error deleting DataSource: {str(e)}")
            return False