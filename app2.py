from flask import Flask, jsonify, request
import requests
import os
from dotenv import load_dotenv
import base64  # For Basic Auth encoding

# Load secrets from .env
load_dotenv()
CLIENT_ID = os.getenv("WHO_CLIENT_ID")
CLIENT_SECRET = os.getenv("WHO_CLIENT_SECRET")

# Validate credentials loaded
if not CLIENT_ID or not CLIENT_SECRET:
    print("Warning: WHO_CLIENT_ID or WHO_CLIENT_SECRET not found in .env file!")

app = Flask(__name__)

TOKEN_URL = "https://icdaccessmanagement.who.int/connect/token"
API_URL = "https://id.who.int/icd/release/11"

@app.route("/")
def home():
    return "WHO ICD API Debug Server Running 🚀"

@app.route("/token")
def get_token():
    """Fetch access token from WHO API using Basic Auth"""
    if not CLIENT_ID or not CLIENT_SECRET:
        return jsonify({"error": "Missing CLIENT_ID or CLIENT_SECRET"}), 400

    # Basic Auth header: base64(client_id:client_secret)
    credentials = f"{CLIENT_ID}:{CLIENT_SECRET}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()
    headers = {
        "Authorization": f"Basic {encoded_credentials}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {
        "scope": "icdapi_access",
        "grant_type": "client_credentials"
    }

    r = requests.post(TOKEN_URL, data=data, headers=headers)
    return jsonify(r.json())

@app.route("/search")
def search_icd():
    """Search ICD-11 API with query parameter ?q=term"""
    q = request.args.get("q", "epilepsy")

    if not CLIENT_ID or not CLIENT_SECRET:
        return jsonify({"error": "Missing CLIENT_ID or CLIENT_SECRET"}), 400

    # First get token using Basic Auth
    credentials = f"{CLIENT_ID}:{CLIENT_SECRET}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()
    token_headers = {
        "Authorization": f"Basic {encoded_credentials}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    token_data = {
        "scope": "icdapi_access",
        "grant_type": "client_credentials"
    }
    r = requests.post(TOKEN_URL, data=token_data, headers=token_headers)
    token = r.json().get("access_token")

    if not token:
        return jsonify({"error": "Failed to get token", "details": r.json()}), 400

    # Use token to search ICD
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "API-Version": "v2",
        "Accept-Language": "en"
    }
    search_url = f"{API_URL}/2024-01/mms/search?q={q}"
    r2 = requests.get(search_url, headers=headers)

    try:
        if r2.status_code == 200 and "application/json" in r2.headers.get("Content-Type", ""):
            data = r2.json()
        else:
            return jsonify({"error": "Invalid response", "status": r2.status_code, "raw": r2.text})
    except ValueError:
        return jsonify({"error": "Failed to parse JSON", "raw": r2.text})

    # Clean and extract useful info
    entities = data.get("destinationEntities", [])
    results = []
    for ent in entities:
        code = ent.get("theCode", "")
        term = ent.get("title", "").replace("<em class='found'>", "").replace("</em>", "")
        definition = None
        for pv in ent.get("matchingPVs", []):
            if pv.get("propertyId") == "Synonym":
                definition = pv.get("label", "").replace("<em class='found'>", "").replace("</em>", "")
                break

        results.append({
            "code": code,
            "term": term,
            "definition": definition if definition else "No definition available"
        })

    return jsonify({
        "requested_url": search_url,
        "status_code": r2.status_code,
        "results": results
    })

if __name__ == "__main__":
    app.run(debug=True, port=5000)