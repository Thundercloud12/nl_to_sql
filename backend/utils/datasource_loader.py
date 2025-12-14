# datasource_loader.py
import os
import json
from typing import Dict, Any
import urllib.request


async def download_from_cloudinary(url: str, output_path: str) -> str:
    """
    Download file from Supabase Storage public URL.

    Args:
        url: Supabase public URL of the file
        output_path: Local path to save the file

    Returns:
        Path to downloaded file

    Raises:
        Exception: If download fails
    """
    try:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Supabase public URLs are normal HTTPS URLs
        urllib.request.urlretrieve(url, output_path)

        if not os.path.exists(output_path):
            raise Exception("File was not saved")

        file_size = os.path.getsize(output_path)
        print(f"[DATASOURCE] ✓ Downloaded file ({file_size} bytes) → {output_path}")

        return output_path

    except Exception as e:
        print(f"[DATASOURCE] ✗ Error downloading from Supabase: {str(e)}")
        raise


def load_datasource_files(raw_metadata: Dict[str, Any], schema_graph: Dict[str, Any]) -> Dict[str, str]:
    """
    Write raw metadata and schema graph to JSON files at the project root.
    
    Args:
        raw_metadata: Raw metadata dict from DataSource
        schema_graph: Schema graph dict from DataSource
    
    Returns:
        Dict with paths to created files
    """
    try:
        # Write to project root (current directory)
        root_dir = "."  # Project root
        
        # Write raw metadata
        metadata_path = os.path.join(root_dir, "raw_metadata.json")
        with open(metadata_path, "w") as f:
            json.dump(raw_metadata, f, indent=4)
        print(f"[DATASOURCE] ✓ Wrote raw_metadata.json to {metadata_path}")
        
        # Write schema graph
        graph_path = os.path.join(root_dir, "schema_graph.json")
        with open(graph_path, "w") as f:
            json.dump(schema_graph, f, indent=4)
        print(f"[DATASOURCE] ✓ Wrote schema_graph.json to {graph_path}")
        
        return {
            "metadata_path": metadata_path,
            "graph_path": graph_path
        }
    
    except Exception as e:
        print(f"[DATASOURCE] ✗ Error writing files: {str(e)}")
        raise