
import os
import requests
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

api_key = os.getenv("HUBSPOT_SERVICE_KEY")

if not api_key:
    raise ValueError("HUBSPOT_SERVICE_KEY not found in .env")

url = "https://api.hubapi.com/crm/objects/2026-03/contacts"

try:
    response = requests.get(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json"
        },
        params={"limit": 10},
        timeout=30
    )

    print("HTTP Status:", response.status_code)

    if response.status_code == 200:
        data = response.json()
        print("HubSpot connection: SUCCESS")
        print("Contacts returned:", len(data.get("results", [])))

    elif response.status_code == 401:
        print("Authentication failed. Check your Service Key.")

    elif response.status_code == 403:
        print("Access denied. Check Service Key permissions.")

    else:
        print("HubSpot returned an unexpected response.")

except requests.RequestException as error:
    print("Connection error:", type(error).__name__)
