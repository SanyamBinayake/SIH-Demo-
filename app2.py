from flask import Flask, jsonify, request
import requests
import os
from dotenv import load_dotenv
import base64
import pandas as pd
from datetime import datetime
import json
from db_helper import DatabaseHelper # Make sure you have this import

# -------------------
# Load secrets
# -------------------
load_dotenv()
CLIENT_ID = os.getenv("WHO_CLIENT_ID")
CLIENT_SECRET = os.getenv("WHO_CLIENT_SECRET")

if not CLIENT_ID or not CLIENT_SECRET:
    print("🔴 FATAL: WHO_CLIENT_ID or WHO_CLIENT_SECRET not found!")
    print("🔴 On Render, set these in the 'Environment' tab. Locally, use a .env file.")

app = Flask(__name__)

TOKEN_URL = "https://icdaccessmanagement.who.int/connect/token"
API_URL = "https://id.who.int/icd/release/11"

# -------------------
# Initialize Database Helper
# -------------------
# This is the key change: Initialize db in the global scope
db = DatabaseHelper()

# -------------------
# NAMASTE CSV ingestion
# -------------------
NAMASTE_CODES = {}

def ingest_namaste_csv(path="Merged_CSV_3.csv"):
    global NAMASTE_CODES
    try:
        if not os.path.exists(path):
            print(f"🔴 FATAL: The CSV file was not found at path: {path}")
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
             print("🟡 WARNING: CSV loaded, but no codes were ingested.")
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

def who_api_search(query, chapter_filter=None):
    token = get_who_token()
    if not token: return []
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json", "API-Version": "v2", "Accept-Language": "en"}
    params = {"q": query}
    if chapter_filter:
        params["chapterFilter"] = chapter_filter
    try:
        r = requests.get(f"{API_URL}/2024-01/mms/search", headers=headers, params=params, timeout=15)
        if r.status_code == 200:
            return r.json().get("destinationEntities", [])
        return []
    except requests.exceptions.RequestException:
        return []

# -------------------
# Main API Routes
# -------------------
@app.route("/")
def home():
    return "WHO ICD + NAMASTE Demo Server 🚀"

# ... (other routes like /search, /search/tm2, /autocomplete remain the same)
@app.route("/search")
def search_biomedicine():
    q = request.args.get("q", "")
    if not q: return jsonify({"results": []})
    entities = who_api_search(q, chapter_filter="!26")
    results = [{"code": ent.get("theCode", ""), "term": ent.get("title", "").replace("<em class='found'>", "").replace("</em>", "")} for ent in entities]
    return jsonify({"results": results})

@app.route("/search/tm2")
def search_tm2():
    q = request.args.get("q", "")
    if not q: return jsonify({"results": []})
    entities = who_api_search(q, chapter_filter="26")
    results = [{"code": ent.get("theCode", ""), "term": ent.get("title", "").replace("<em class='found'>", "").replace("</em>", "")} for ent in entities]
    return jsonify({"results": results})

@app.route("/autocomplete")
def autocomplete():
    q = request.args.get("q", "").lower()
    if not q: return jsonify({"total": 0, "results": []})
    results = []
    for code, data in NAMASTE_CODES.items():
        if any(q in str(val).lower() for val in data.values()):
            results.append({"system": "https://demo.sih/fhir/CodeSystem/namaste", "code": code, "display": data["display"], "source": "NAMASTE"})
    entities = who_api_search(q)
    for ent in entities[:10]:
        source = "ICD-11 (TM2)" if ent.get('chapter') == '26' else "ICD-11"
        results.append({"system": "http://id.who.int/icd/release/11/mms", "code": ent.get("theCode"), "display": ent.get("title", "").replace("<em class='found'>", "").replace("</em>", ""), "source": source})
    return jsonify({"total": len(results), "results": results})


# -------------------
# FHIR-Specific Routes
# -------------------
@app.route("/fhir/Bundle", methods=["POST"])
def receive_bundle():
    bundle = request.get_json()
    if not bundle or bundle.get("resourceType") != "Bundle":
        return jsonify({"error": "Invalid Bundle"}), 400

    processed_conditions = []
    for entry in bundle.get("entry", []):
        resource = entry.get("resource", {})
        if resource.get("resourceType") == "Condition":
            codings = resource.get("code", {}).get("coding", [])
            nam_code_obj = next((c for c in codings if "namaste" in c.get("system", "")), None)
            
            if nam_code_obj:
                nam_term = NAMASTE_CODES.get(nam_code_obj['code'], {}).get('display')
                if nam_term:
                    who_results = who_api_search(nam_term)
                    if who_results:
                        best_match = who_results[0]
                        icd_coding = {
                            "system": "http://id.who.int/icd/release/11/mms",
                            "code": best_match.get("theCode"),
                            "display": best_match.get("title", "").replace("<em class='found'>", "").replace("</em>", "")
                        }
                        codings.append(icd_coding)
            
            processed_conditions.append(resource)

    final_payload = {"status": "accepted", "stored": processed_conditions}
    
    # Now 'db' is defined in the global scope and can be accessed here
    db.save_bundle(final_payload)
    
    return jsonify(final_payload), 201

# -------------------
# Run
# -------------------
if __name__ == "__main__":
    ingest_namaste_csv()
    # The 'db' object is already created above, so we just run the app
    app.run(debug=True, port=5000)

