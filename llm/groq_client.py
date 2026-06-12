import os
from groq import Groq


def get_groq_response(
    system_prompt: str,
    user_prompt:   str,
    api_key:       str,
    model:         str = "llama-3.3-70b-versatile",
    history:       list[dict] | None = None,
) -> str:
    """
    Sends a prompt to Groq and returns the generated reply.

    Parameters
    ----------
    system_prompt : System instruction string.
    user_prompt   : The current user turn prompt (RAG-assembled).
    api_key       : Groq API key.
    model         : Groq model identifier.
    history       : Optional list of prior {"role", "content"} dicts
                    (from memory_store.get_recent_turns). These are
                    injected between the system prompt and the current
                    user message so the LLM has conversation context.
    """
    client = Groq(api_key=api_key)

    messages = [{"role": "system", "content": system_prompt}]

    # Inject conversation history before the latest user turn
    if history:
        messages.extend(history)

    messages.append({"role": "user", "content": user_prompt})

    chat_completion = client.chat.completions.create(
        messages=messages,
        model=model,
        temperature=0.2,
        max_tokens=1024,
    )

    return chat_completion.choices[0].message.content.strip()

# if __name__ == "__main__":
#     # Simple test
#     import sys
#     key = os.environ.get("GROQ_API_KEY")
#     if not key:
#         print("Please set GROQ_API_KEY environment variable to test.")
#         sys.exit(1)
        
#     sys_p = "You are a helpful assistant."
#     usr_p = "Explain Groq in 10 words."
#     try:
#         res = get_groq_response(sys_p, usr_p, key)
#         print(f"Response: {res}")
#     except Exception as e:
#         print(f"Error: {e}")
