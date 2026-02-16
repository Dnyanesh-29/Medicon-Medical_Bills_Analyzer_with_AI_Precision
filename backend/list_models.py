
import os
from dotenv import load_dotenv, find_dotenv

# Load env
load_dotenv(find_dotenv(usecwd=True))
api_key = os.getenv("GOOGLE_API_KEY")

try:
    from google.genai import Client
    print(f"Using API Key: {api_key[:5]}...")
    client = Client(api_key=api_key)
    print("Listing models...")
    for model in client.models.list():
        print(f"- {model.name}")
except Exception as e:
    print(f"Error: {e}")
