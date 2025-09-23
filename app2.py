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

# --- NEW: URI for the Traditional Medicine Module 2 (TM2) Chapter ---
TM2_CHAPTER_URI = "http://id.who.int/icd/release/11/mms/26"

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

# -------------------
# Routes
# -------------------
@app.route("/")
def home():
    return "WHO ICD + NAMASTE Demo Server 🚀"

def _perform_who_search(query, subtree_filter=None):
    """Helper function to perform a search against the WHO ICD API."""
    token = get_who_token()
    if not token:
        return None, "Failed to get token"

    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json", "API-Version": "v2", "Accept-Language": "en"}
    params = {'q': query}
    if subtree_filter:
        params['subtreesFilter'] = subtree_filter
    
    try:
        r = requests.get(f"{API_URL}/2024-01/mms/search", params=params, headers=headers, timeout=15)
        if r.status_code != 200:
            return None, r.text
        
        entities = r.json().get("destinationEntities", [])
        results = []
        for ent in entities:
            results.append({
                "code": ent.get("theCode", ""), 
                "term": ent.get("title", "").replace("<em class='found'>", "").replace("</em>", ""),
                "definition": ent.get("definition", {}).get("value", "No definition available.")
            })
        return results, None
    except requests.exceptions.RequestException as e:
        return None, str(e)

@app.route("/search")
def search_icd():
    """Search the entire WHO ICD-11 (Biomedicine)."""
    q = request.args.get("q")
    results, error = _perform_who_search(q)
    if error:
        return jsonify({"error": "WHO ICD search failed", "details": error}), 500
    return jsonify({"results": results})

# --- NEW: Endpoint specifically for TM2 search ---
@app.route("/search/tm2")
def search_icd_tm2():
    """Search only within the WHO ICD-11 TM2 Chapter."""
    q = request.args.get("q")
    results, error = _perform_who_search(q, subtree_filter=TM2_CHAPTER_URI)
    if error:
        return jsonify({"error": "WHO ICD-11 TM2 search failed", "details": error}), 500
    return jsonify({"results": results})

@app.route("/autocomplete")
def autocomplete():
    q = request.args.get("q", "").lower()
    results = []
    if not q: return {"total": 0, "results": []}

    # 1. Search NAMASTE
    for code, data in NAMASTE_CODES.items():
        if (q in data["display"].lower() or q in data["regional_term"].lower() or q in data["definition"].lower()):
            results.append({"system": "https://demo.sih/fhir/CodeSystem/namaste", "code": code, "display": data["display"], "source": "NAMASTE"})

    # 2. Search WHO ICD-11 (Biomedicine + TM2)
    token = get_who_token()
    if token:
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json", "API-Version": "v2"}
        try:
            r = requests.get(f"{API_URL}/2024-01/mms/search?q={q}", headers=headers, timeout=15)
            if r.status_code == 200:
                for ent in r.json().get("destinationEntities", []):
                    # --- UPDATED: Determine if result is TM2 or Biomedicine ---
                    is_tm2 = TM2_CHAPTER_URI in ent.get('foundationReference', '')
                    source = "ICD-11 TM2" if is_tm2 else "ICD-11"
                    results.append({
                        "system": "http://id.who.int/icd/release/11/mms", 
                        "code": ent.get("theCode"), 
                        "display": ent.get("title", "").replace("<em class='found'>", "").replace("</em>", ""), 
                        "source": source
                    })
        except requests.exceptions.RequestException:
            pass
    
    return {"total": len(results), "results": results[:20]}

# --- FHIR Routes (Unchanged) ---
@app.route("/fhir/CodeSystem/namaste")
def get_codesystem():
    concepts = [{"code": data["code"], "display": data["display"]} for data in NAMASTE_CODES.values()]
    return jsonify({"resourceType": "CodeSystem", "id": "namaste", "url": "https://demo.sih/fhir/CodeSystem/namaste", "status": "active", "content": "complete", "concept": concepts})

@app.route("/fhir/ConceptMap/$translate", methods=["POST"])
def translate():
    payload = request.get_json()
    code = payload.get("code")
    nam_term = NAMASTE_CODES.get(code, {}).get("display")
    if not nam_term: return jsonify({"error": "Code not found"}), 404
    
    results, _ = _perform_who_search(nam_term) # Use helper
    mapped = []
    if results:
        mapped.append({"system": "http://id.who.int/icd/release/11/mms", "code": results[0]['code'], "display": results[0]['term']})

    return jsonify({"resourceType": "Parameters", "parameter": [{"name": "result", "valueBoolean": True}, {"name": "match", "part": [{"name": "concept", "valueCoding": mapped[0]}]}] if mapped else [{"name": "result", "valueBoolean": False}]})

@app.route("/fhir/Bundle", methods=["POST"])
def receive_bundle():
    bundle = request.get_json()
    if not bundle or bundle.get("resourceType") != "Bundle": return jsonify({"error": "Invalid Bundle"}), 400
    
    stored_conditions = []
    for entry in bundle.get("entry", []):
        res = entry.get("resource", {})
        if res.get("resourceType") == "Condition":
            codings = res.get("code", {}).get("coding", [])
            has_nam = any("namaste" in c.get("system", "") for c in codings)
            if has_nam:
                nam_code = next((c["code"] for c in codings if "namaste" in c["system"]), None)
                if nam_code:
                    trans_resp = app.test_client().post("/fhir/ConceptMap/$translate", json={"code": nam_code})
                    if trans_resp.status_code == 200:
                        trans_data = trans_resp.get_json()
                        if trans_data["parameter"][0].get("valueBoolean"):
                            icd_coding = trans_data["parameter"][1]["part"][0]["valueCoding"]
                            codings.append(icd_coding)
            stored_conditions.append(res)
    return jsonify({"status": "accepted", "stored": stored_conditions}), 201

# -------------------
# Run
# -------------------
if __name__ == "__main__":
    ingest_namaste_csv()
    app.run(debug=True, port=5000)
