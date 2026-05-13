import os
from groq import Groq

def get_groq_response(system_prompt: str, user_prompt: str, api_key: str) -> str:
    """
    Sends a prompt to Groq (Llama 3) and returns the generated reply.
    """
    client = Groq(api_key=api_key)
    
    chat_completion = client.chat.completions.create(
        messages=[
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": user_prompt,
            }
        ],
        model="llama-3.3-70b-versatile",
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
