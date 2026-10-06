import os
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

if api_key:
    print("SUCCESS: Gemini API key loaded.")
else:
    print("ERROR: Gemini API key not found.")