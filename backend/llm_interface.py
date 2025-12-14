# llm_interface.py
import re
from typing import Optional
import google.generativeai as genai
import os
from dotenv import load_dotenv

# Load env vars
load_dotenv()

# Configure Gemini API
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

def extract_code_from_response(resp_text: str) -> str:
    """
    Extract the Python code block from an LLM response.
    """
    m = re.search(r"```(?:python)?\n(.*?)```", resp_text, re.S | re.I)
    if m:
        return m.group(1).strip()
    return resp_text.strip()

def call_llm(user_query: str, schema_text: str) -> str:
    """
    Generates pandas code that operates on the `tables` dictionary.
    """
    system_prompt = f"""
You are a Python pandas expert. You will be given access to a `tables` dictionary mapping string names
to pandas.DataFrame objects representing Excel sheets or unioned sheets.

Rules:
- OUTPUT ONLY Python code (no commentary, no markdown).
- Use only the `tables` object; pandas (`pd`) is available.
- The final answer must be assigned to a variable named `result`.
- Prefer union tables (names start with "__union__") for multi-file queries.
- Convert numerical columns using pd.to_numeric(..., errors="coerce") before computation.
- If a referenced column does not exist, raise an Exception.

User query: {user_query}

Schema summary:
{schema_text}
    """
    model = genai.GenerativeModel("gemini-2.5-flash")
    response = model.generate_content(system_prompt)
    return response.text
