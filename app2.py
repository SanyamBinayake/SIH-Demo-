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

def who_api_search(query, chapter_filter=None):
    """A generic helper to search the WHO API, with an optional chapter filter."""
    token = get_who_token()
    if not token:
        return []

    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json", "API-Version": "v2", "Accept-Language": "en"}
    params = {"q": query}
    if chapter_filter:
        params["chapterFilter"] = chapter_filter
    
    try:
        r = requests.get(f"{API_URL}/2024-01/mms/search", headers=headers, params=params, timeout=15)
        if r.status_code == 200:
            results = []
            for ent in r.json().get("destinationEntities", []):
                results.append({
                    "code": ent.get("theCode", "N/A"),
                    "term": ent.get("title", "").replace("<em class='found'>", "").replace("</em>", ""),
                    "definition": ent.get("definition", {}).get("@value", "No definition available.")
                })
            return results
        else:
            print(f"🟡 WARNING: WHO API returned status {r.status_code} for query '{query}'")
            return []
    except requests.exceptions.RequestException as e:
        print(f"🔴 ERROR: Could not connect to WHO Search API. Reason: {e}")
        return []

# -------------------
# Main API Routes
# -------------------
@app.route("/")
def home():
    return "WHO ICD + NAMASTE Demo Server 🚀"

@app.route("/search")
def search_biomedicine():
    """Search for BIOMEDICINE terms (Chapters 01-25, 27)"""
    q = request.args.get("q", "")
    if not q: return jsonify({"results": []})
    # Exclude TM2 chapter
    results = who_api_search(q, chapter_filter="!26")
    return jsonify({"results": results})

@app.route("/search/tm2")
def search_tm2():
    """Search for TRADITIONAL MEDICINE terms (Chapter 26)"""
    q = request.args.get("q", "")
    if not q: return jsonify({"results": []})
    # ONLY search TM2 chapter
    results = who_api_search(q, chapter_filter="26")
    return jsonify({"results": results})

@app.route("/autocomplete")
def autocomplete():
    q = request.args.get("q", "").lower()
    if not q: return jsonify({"total": 0, "results": []})
    
    results = []
    # 1. Search NAMASTE
    for code, data in NAMASTE_CODES.items():
        if (q in data["display"].lower() or q in data["regional_term"].lower() or q in data["definition"].lower()):
            results.append({"system": "https://demo.sih/fhir/CodeSystem/namaste", "code": code, "display": data["display"], "source": "NAMASTE"})
    
    # 2. Search Biomedicine
    for item in who_api_search(q, chapter_filter="!26")[:5]: # Limit results
        results.append({"system": "http://id.who.int/icd/release/11/mms", "code": item["code"], "display": item["term"], "source": "ICD-11"})
        
    # 3. Search TM2
    for item in who_api_search(q, chapter_filter="26")[:5]: # Limit results
        results.append({"system": "http://id.who.int/icd/release/11/mms/tm", "code": item["code"], "display": item["term"], "source": "ICD-11 (TM2)"})

    return jsonify({"total": len(results), "results": results})

# -------------------
# FHIR-Specific Routes
# -------------------
@app.route("/fhir/CodeSystem/namaste")
def get_codesystem():
    concepts = [{"code": data["code"], "display": data["display"]} for data in NAMASTE_CODES.values()]
    return jsonify({"resourceType": "CodeSystem", "status": "active", "content": "complete", "concept": concepts})

@app.route("/fhir/ConceptMap/$translate", methods=["POST"])
def translate():
    payload = request.get_json()
    code_to_translate = payload.get("code")
    nam_term = NAMASTE_CODES.get(code_to_translate, {}).get("display")

    if not nam_term:
        return jsonify({"error": "Code not found in NAMASTE"}), 404
    
    # Search for the term in both Biomedicine and TM2, return the first match
    search_results = who_api_search(nam_term)
    if not search_results:
        return jsonify({"resourceType": "Parameters", "parameter": [{"name": "result", "valueBoolean": False}]})

    best_match = search_results[0]
    mapped_coding = {
        "system": "http://id.who.int/icd/release/11/mms",
        "code": best_match["code"],
        "display": best_match["term"]
    }
    
    return jsonify({
        "resourceType": "Parameters",
        "parameter": [
            {"name": "result", "valueBoolean": True},
            {"name": "match", "part": [{"name": "concept", "valueCoding": mapped_coding}]}
        ]
    })

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
                # Use internal translate function
                with app.test_request_context():
                    translate_response = translate(nam_code_obj['code'])
                    if translate_response.status_code == 200:
                        translate_data = translate_response.get_json()
                        if translate_data["parameter"][0].get("valueBoolean"):
                            icd_coding = translate_data["parameter"][1]["part"][0]["valueCoding"]
                            codings.append(icd_coding)
            
            processed_conditions.append(resource)

    return jsonify({"status": "accepted", "stored": processed_conditions}), 201

# -------------------
# Run
# -------------------
if __name__ == "__main__":
    ingest_namaste_csv()
    app.run(debug=True, port=5000)

