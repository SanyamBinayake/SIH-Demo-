from flask import Flask, jsonify, request
import requests
import os
from dotenv import load_dotenv
import base64
import pandas as pd
from datetime import datetime

# -------------------
# Load secrets
# -------------------
load_dotenv()
CLIENT_ID = os.getenv("WHO_CLIENT_ID")
CLIENT_SECRET = os.getenv("WHO_CLIENT_SECRET")

# Check if credentials are loaded
if not CLIENT_ID or not CLIENT_SECRET:
    print("🔴 FATAL: WHO_CLIENT_ID or WHO_CLIENT_SECRET not found!")
    print("🔴 On Render, set these in the 'Environment' tab. Locally, use a .env file.")

app = Flask(__name__)

TOKEN_URL = "https://icdaccessmanagement.who.int/connect/token"
API_URL = "https://id.who.int/icd/release/11"

# -------------------
# NAMASTE CSV ingestion
# -------------------
NAMASTE_CODES = {}

def ingest_namaste_csv(path="Merged_CSV_3.csv"):
    global NAMASTE_CODES
    try:
        if not os.path.exists(path):
            print(f"🔴 FATAL: The CSV file was not found at path: {path}")
            print("🔴 Make sure the file is in the same directory and pushed to your Git repository.")
            return

        df = pd.read_csv(path)
        for _, row in df.iterrows():
            code = str(row.get("Code", "")).strip()
            if code:
                NAMASTE_CODES[code] = {
                    "code": code,
                    "display": str(row.get("Term", "")).strip(),
                    "regional_term": str(row.get("RegionalTerm", "")).strip(),
                    "definition": str(row.get("Short_definition", "")).strip()
                }
        
        if not NAMASTE_CODES:
             print("🟡 WARNING: CSV loaded, but no codes were ingested. Check the CSV file's content.")
        else:
            print(f"✅ [INFO] Loaded {len(NAMASTE_CODES)} NAMASTE codes successfully.")

    except Exception as e:
        print(f"🔴 ERROR: Failed to load or process NAMASTE CSV: {e}")

# -------------------
# Helpers
# -------------------
def get_who_token():
    if not CLIENT_ID or not CLIENT_SECRET:
        return None
    credentials = f"{CLIENT_ID}:{CLIENT_SECRET}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()
    headers = {"Authorization": f"Basic {encoded_credentials}", "Content-Type": "application/x-www-form-urlencoded"}
    data = {"scope": "icdapi_access", "grant_type": "client_credentials"}
    try:
        r = requests.post(TOKEN_URL, data=data, headers=headers, timeout=10)
        r.raise_for_status()
        return r.json().get("access_token")
    except requests.exceptions.RequestException as e:
        print(f"🔴 ERROR: Could not get WHO token. Reason: {e}")
        return None

# -------------------
# Routes
# -------------------
@app.route("/")
def home():
    return "WHO ICD + NAMASTE Demo Server 🚀"

@app.route("/search")
def search_icd():
    q = request.args.get("q", "epilepsy")
    print(f"\n🔍 Received ICD search request for: '{q}'")
    token = get_who_token()
    if not token:
        return jsonify({"error": "Failed to get token due to configuration issue"}), 500

    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json", "API-Version": "v2", "Accept-Language": "en"}
    search_url = f"{API_URL}/2024-01/mms/search?q={q}"
    
    try:
        r2 = requests.get(search_url, headers=headers, timeout=15)
        print(f"   WHO API returned status: {r2.status_code}")
        if r2.status_code != 200:
            return jsonify({"error": "WHO ICD search failed", "details": r2.text}), r2.status_code

        data = r2.json()
        entities = data.get("destinationEntities", [])
        results = []
        for ent in entities:
            code = ent.get("theCode", "")
            term = ent.get("title", "").replace("<em class='found'>", "").replace("</em>", "")
            definition = term # Fallback definition
            for pv in ent.get("matchingPVs", []):
                if pv.get("propertyId") == "Synonym":
                    definition = pv.get("label", "").replace("<em class='found'>", "").replace("</em>", "")
                    break
            results.append({"code": code, "term": term, "definition": definition})
        return jsonify({"results": results})
    except requests.exceptions.RequestException as e:
        print(f"🔴 ERROR: Could not connect to WHO Search API. Reason: {e}")
        return jsonify({"error": "Could not connect to downstream WHO API"}), 503

@app.route("/autocomplete")
def autocomplete():
    q = request.args.get("q", "").lower()
    print(f"\n🔍 Received autocomplete request for: '{q}'")
    results = []
    if not q:
        return {"total": 0, "results": []}

    print("-> Searching local NAMASTE data...")
    for code, data in NAMASTE_CODES.items():
        if (q in data["display"].lower() or q in data["regional_term"].lower() or q in data["definition"].lower()):
            results.append({"system": "https://demo.sih/fhir/CodeSystem/namaste", "code": code, "display": data["display"], "source": "NAMASTE"})
    print(f"   Found {len(results)} match(es) in NAMASTE.")

    print("-> Searching WHO ICD API...")
    token = get_who_token()
    if token:
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json", "API-Version": "v2"}
        try:
            r = requests.get(f"{API_URL}/2024-01/mms/search?q={q}", headers=headers, timeout=15)
            print(f"   WHO API returned status: {r.status_code}")
            if r.status_code == 200:
                icd_results_count = 0
                for ent in r.json().get("destinationEntities", []):
                    icd_results_count += 1
                    results.append({"system": "http://id.who.int/icd/release/11/mms", "code": ent.get("theCode"), "display": ent.get("title", {}).get("@value", ent.get("title", "")).replace("<em class='found'>", "").replace("</em>", ""), "source": "ICD-11"})
                print(f"   Found {icd_results_count} match(es) from WHO ICD API.")
        except requests.exceptions.RequestException as e:
            print(f"🔴 ERROR: Could not connect to WHO Search API. Reason: {e}")
    else:
        print("   Skipping WHO search; no token was available.")
    
    print(f"✅ Returning {len(results)} total results.")
    return {"total": len(results), "results": results[:20]}

# Add your other FHIR-specific routes (/fhir/CodeSystem/namaste, /fhir/ConceptMap/$translate, /fhir/Bundle) here from your original file.
# They are omitted for brevity but should be included in your final file.

# -------------------
# Run
# -------------------
if __name__ == "__main__":
    ingest_namaste_csv()
    app.run(debug=True, port=5000)