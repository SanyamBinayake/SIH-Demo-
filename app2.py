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

@app.route("/search")
def search_icd():
    q = request.args.get("q", "epilepsy")
    token = get_who_token()
    if not token:
        return jsonify({"error": "Failed to get token"}), 500

    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json", "API-Version": "v2", "Accept-Language": "en"}
    search_url = f"{API_URL}/2024-01/mms/search?q={q}"
    try:
        r2 = requests.get(search_url, headers=headers, timeout=15)
        if r2.status_code != 200:
            return jsonify({"error": "WHO ICD search failed"}), 400
        
        data = r2.json()
        entities = data.get("destinationEntities", [])
        results = []
        for ent in entities:
            results.append({"code": ent.get("theCode", ""), "term": ent.get("title", "").replace("<em class='found'>", "").replace("</em>", "")})
        return jsonify({"results": results})
    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"Could not connect to WHO API: {e}"}), 503

@app.route("/autocomplete")
def autocomplete():
    q = request.args.get("q", "").lower()
    results = []
    if not q: return {"total": 0, "results": []}

    for code, data in NAMASTE_CODES.items():
        if (q in data["display"].lower() or q in data["regional_term"].lower() or q in data["definition"].lower()):
            results.append({"system": "https://demo.sih/fhir/CodeSystem/namaste", "code": code, "display": data["display"], "source": "NAMASTE"})

    token = get_who_token()
    if token:
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json", "API-Version": "v2"}
        try:
            r = requests.get(f"{API_URL}/2024-01/mms/search?q={q}", headers=headers, timeout=15)
            if r.status_code == 200:
                for ent in r.json().get("destinationEntities", []):
                    results.append({"system": "http://id.who.int/icd/release/11/mms", "code": ent.get("theCode"), "display": ent.get("title", {}).get("@value", ent.get("title", "")).replace("<em class='found'>", "").replace("</em>", ""), "source": "ICD-11"})
        except requests.exceptions.RequestException:
            pass # Silently fail if WHO is unreachable
    
    return {"total": len(results), "results": results[:20]}

# --- RESTORED FHIR ROUTES ---
@app.route("/fhir/CodeSystem/namaste")
def get_codesystem():
    """Expose NAMASTE CodeSystem"""
    concepts = [{"code": data["code"], "display": data["display"]} for data in NAMASTE_CODES.values()]
    return jsonify({
        "resourceType": "CodeSystem", "id": "namaste", "url": "https://demo.sih/fhir/CodeSystem/namaste",
        "status": "active", "content": "complete", "concept": concepts
    })

@app.route("/fhir/ConceptMap/$translate", methods=["POST"])
def translate():
    """Translate NAMASTE code to ICD-11"""
    payload = request.get_json()
    code = payload.get("code")
    nam_term = NAMASTE_CODES.get(code, {}).get("display")

    if not nam_term:
        return jsonify({"error": "Code not found"}), 404

    token = get_who_token()
    mapped = []
    if token:
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json", "API-Version": "v2"}
        r = requests.get(f"{API_URL}/2024-01/mms/search?q={nam_term}", headers=headers)
        if r.status_code == 200:
            for res in r.json().get("destinationEntities", [])[:1]:
                mapped.append({
                    "system": "http://id.who.int/icd/release/11/mms",
                    "code": res.get("theCode"),
                    "display": res.get("title", {}).get("@value", res.get("title", ""))
                })
    
    return jsonify({
        "resourceType": "Parameters",
        "parameter": [{"name": "result", "valueBoolean": True}, {"name": "match", "part": [{"name": "concept", "valueCoding": mapped[0]}]}] if mapped else [{"name": "result", "valueBoolean": False}]
    })

@app.route("/fhir/Bundle", methods=["POST"])
def receive_bundle():
    """Receive FHIR Bundle with dual coding"""
    bundle = request.get_json()
    if not bundle or bundle.get("resourceType") != "Bundle":
        return jsonify({"error": "Invalid Bundle"}), 400

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