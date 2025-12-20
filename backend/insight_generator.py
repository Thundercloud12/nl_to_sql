
import google.generativeai as genai





def generate_insight1(user_query: str, execution_result: str) -> str:  # Changed execution_result from dict to str
    """
    Converts numeric/table output into natural-language insights.
    """
    model = genai.GenerativeModel("gemma-3-12b-it")  # Fixed model name

    prompt = f"""
        You are a senior data analyst.

        A user asked:

        {user_query}

        The analytics engine returned the following result (Python-evaluated output):

        {execution_result}

        Your task:
        - Summarize key findings in 4–6 sentences.
        - Explain the key insights in simple language.
        - Mention trends, anomalies, or comparisons.
        - NO CODE, NO MARKDOWN.
        - Make the explanation conversational and clear.
        """

    response = model.generate_content(prompt)
    return response.text.strip()