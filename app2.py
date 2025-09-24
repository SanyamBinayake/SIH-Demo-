from flask import Flask, jsonify, request
import requests
import os
from dotenv import load_dotenv
import base64
import pandas as pd
from datetime import datetime
from db_helper import DatabaseHelper 

# --- Initialization ---
load_dotenv()
app = Flask(__name__)
db = DatabaseHelper() # Initialize the database helper

# --- Constants and Globals ---
CLIENT_ID = os.getenv("WHO_CLIENT_ID")
CLIENT_SECRET = os.getenv("WHO_CLIENT_SECRET")
TOKEN_URL = "https://icdaccessmanagement.who.int/connect/token"
API_URL = "https://id.who.int/icd/release/11"
NAMASTE_CODES = {}

# -------------------
# Startup Functions
# -------------------
def ingest_namaste_csv(path="Merged_CSV_3.csv"):
    global NAMASTE_CODES
    if not os.path.exists(path):
        print(f"🔴 FATAL: The CSV file was not found at path: {path}")
        return
    try:
        df = pd.read_csv(path)
        for _, row in df.iterrows():
            code = str(row.get("Code", "")).strip()
            if code:
                NAMASTE_CODES[code] = {
                    "code": code, "display": str(row.get("Term", "")).strip(),
                    "regional_term": str(row.get("RegionalTerm", "")).strip(),
                    "definition": str(row.get("Short_definition", "")).strip()
                }
        print(f"✅ [INFO] Loaded {len(NAMASTE_CODES)} NAMASTE codes successfully.")
    except Exception as e:
        print(f"🔴 ERROR: Failed to load NAMASTE CSV: {e}")

# -------------------
# Helper Functions
# -------------------
def get_who_token():
    # (Implementation is correct and remains the same)
    if not CLIENT_ID or not CLIENT_SECRET: return None
    credentials = f"{CLIENT_ID}:{CLIENT_SECRET}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()
    headers = {"Authorization": f"Basic {encoded_credentials}", "Content-Type": "application/x-www-form-urlencoded"}
    data = {"scope": "icdapi_access", "grant_type": "client_credentials"}
    try:
        r = requests.post(TOKEN_URL, data=data, headers=headers, timeout=10)
        r.raise_for_status()
        return r.json().get("access_token")
    except requests.exceptions.RequestException as e:
        print(f"🔴 ERROR: Could not get WHO token: {e}")
        return None

def who_api_search(query, chapter_filter=None):
    # (Implementation is correct and remains the same)
    token = get_who_token()
    if not token: return []
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json", "API-Version": "v2", "Accept-Language": "en"}
    params = {"q": query}
    if chapter_filter: params["chapterFilter"] = chapter_filter
    try:
        r = requests.get(f"{API_URL}/2024-01/mms/search", headers=headers, params=params, timeout=15)
        if r.status_code == 200:
            results = []
            for ent in r.json().get("destinationEntities", []):
                results.append({
                    "code": ent.get("theCode", "N/A"), "term": ent.get("title", "").replace("<em class='found'>", "").replace("</em>", ""),
                    "definition": ent.get("definition", {}).get("@value", "No definition available.")
                })
            return results
        return []
    except requests.exceptions.RequestException:
        return []

# -------------------
# Main API Routes
# -------------------
@app.route("/")
def home(): return "WHO ICD + NAMASTE Demo Server 🚀"

@app.route("/search")
def search_biomedicine():
    q = request.args.get("q", "")
    if not q: return jsonify({"results": []})
    results = who_api_search(q, chapter_filter="!26")
    return jsonify({"results": results})

@app.route("/search/tm2")
def search_tm2():
    q = request.args.get("q", "")
    if not q: return jsonify({"results": []})
    results = who_api_search(q, chapter_filter="26")
    return jsonify({"results": results})

@app.route("/autocomplete")
def autocomplete():
    q = request.args.get("q", "").lower()
    print(f"\n🔍 [Autocomplete] Received request for: '{q}'")
    if not q: return jsonify({"total": 0, "results": []})
    
    results = []
    
    # --- Stage 1: Search NAMASTE ---
    print("-> [Autocomplete] Searching local NAMASTE data...")
    namaste_count = 0
    for code, data in NAMASTE_CODES.items():
        if (q in data["display"].lower() or q in data["regional_term"].lower() or q in data["definition"].lower()):
            results.append({"system": "https://demo.sih/fhir/CodeSystem/namaste", "code": code, "display": data["display"], "source": "NAMASTE"})
            namaste_count += 1
    print(f"   [Autocomplete] Found {namaste_count} match(es) in NAMASTE.")
    
    # --- Stage 2: Search Biomedicine ---
    print("-> [Autocomplete] Searching WHO Biomedicine API...")
    bio_results = who_api_search(q, chapter_filter="!26")[:5]
    for item in bio_results:
        results.append({"system": "http://id.who.int/icd/release/11/mms", "code": item["code"], "display": item["term"], "source": "ICD-11"})
    print(f"   [Autocomplete] Found {len(bio_results)} match(es) in Biomedicine.")
        
    # --- Stage 3: Search TM2 ---
    print("-> [Autocomplete] Searching WHO TM2 API...")
    tm2_results = who_api_search(q, chapter_filter="26")[:5]
    for item in tm2_results:
        results.append({"system": "http://id.who.int/icd/release/11/mms/tm", "code": item["code"], "display": item["term"], "source": "ICD-11 (TM2)"})
    print(f"   [Autocomplete] Found {len(tm2_results)} match(es) in TM2.")

    print(f"✅ [Autocomplete] Returning {len(results)} total combined results.")
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
                translate_response = app.test_client().post(
                    "/fhir/ConceptMap/$translate", json={"code": nam_code_obj['code']}
                )
                if translate_response.status_code == 200:
                    translate_data = translate_response.get_json()
                    if translate_data.get("parameter") and translate_data["parameter"][0].get("valueBoolean"):
                        icd_coding = translate_data["parameter"][1]["part"][0]["valueCoding"]
                        codings.append(icd_coding)
            
            processed_conditions.append(resource)
    
    final_payload = {"status": "accepted", "stored": processed_conditions}
    db.save_bundle(final_payload) # Save to database
    return jsonify(final_payload), 201

# (Other FHIR routes like $translate are omitted for brevity but should be included from your correct file)
@app.route("/fhir/ConceptMap/$translate", methods=["POST"])
def translate():
    payload = request.get_json()
    code_to_translate = payload.get("code")
    nam_term = NAMASTE_CODES.get(code_to_translate, {}).get("display")
    if not nam_term: return jsonify({"error": "Code not found"}), 404
    search_results = who_api_search(nam_term)
    if not search_results: return jsonify({"resourceType": "Parameters", "parameter": [{"name": "result", "valueBoolean": False}]})
    best_match = search_results[0]
    mapped_coding = {"system": "http://id.who.int/icd/release/11/mms", "code": best_match["code"], "display": best_match["term"]}
    return jsonify({"resourceType": "Parameters", "parameter": [{"name": "result", "valueBoolean": True}, {"name": "match", "part": [{"name": "concept", "valueCoding": mapped_coding}]}]})

# -------------------
# Run
# -------------------
if __name__ == "__main__":
    ingest_namaste_csv()
    app.run(debug=True, port=5000)
else:
    # Ensure CSV is loaded when run by Gunicorn on Render
    ingest_namaste_csv()

