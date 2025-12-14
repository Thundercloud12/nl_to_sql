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
        Save DataSource to Neon DB via Next.js API.
        
        Args:
            user_id: User ID from Clerk
            cloudinary_url: URL of uploaded Parquet file on Cloudinary
            raw_metadata: Raw metadata JSON
            schema_graph: Schema graph JSON
        
        Returns:
            Response with data_source_id and status
        
        Raises:
            Exception: If API call fails
        """
        try:
            payload = {
                "userId": user_id,
                "cloudinaryUrl": cloudinary_url,
                "rawMetadata": raw_metadata,
                "schemaGraph": schema_graph
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{NEXT_JS_API_URL}/api/datasources/create",
                    json=payload,
                    timeout=30.0
                )
            
            if response.status_code not in [200, 201]:
                raise Exception(f"API error: {response.status_code} - {response.text}")
            
            data = response.json()
            print(f"[PRISMA] ✓ DataSource created: {data.get('id')}")
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