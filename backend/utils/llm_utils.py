import time
import google.generativeai as genai
from tenacity import retry, stop_after_attempt, wait_exponential
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()
api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    raise ValueError("GOOGLE_API_KEY not found in environment variables")
genai.configure(api_key=api_key)

# Global list to track request timestamps for rate limiting
request_timestamps = []

@retry(
    retry=lambda exc: isinstance(exc, Exception),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=60)
)
def rate_limited_llm_call(prompt: str, model_name: str = "gemma-3-27b-it"):
    """
    Make a rate-limited LLM call with exponential backoff on failures.
    Limits to ~50 requests per minute.
    Returns (response_text, response_object)
    """
    global request_timestamps
    
    # Rate limiting: sliding window of 60 seconds, max 50 requests
    now = time.time()
    request_timestamps[:] = [t for t in request_timestamps if now - t < 60]  # Keep last 60s
    if len(request_timestamps) >= 50:
        sleep_time = 60 - (now - request_timestamps[0])
        print(f"[RATE LIMIT] Sleeping {sleep_time:.1f}s to avoid limit")
        time.sleep(sleep_time)
    
    request_timestamps.append(now)
    
    model = genai.GenerativeModel(
        model_name,
        generation_config=genai.GenerationConfig(
            temperature=0,
            top_p=1,
            top_k=1,
        )
    )
    
    response = model.generate_content(prompt)
    
    # Check for empty or blocked responses
    if not response.text or not response.text.strip():
        print(f"[LLM ERROR] Empty response from {model_name}. Response: {response}")
        print(f"[LLM ERROR] Response finish_reason: {response.candidates[0].finish_reason if response.candidates else 'No candidates'}")
        raise ValueError(f"LLM returned empty response: {response}")
    
    return response.text.strip(), response