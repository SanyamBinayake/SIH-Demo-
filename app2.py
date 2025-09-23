from flask import Flask, jsonify, request
import requests
import os
from dotenv import load_dotenv
import base64  # For Basic Auth encoding
import pandas as pd
from datetime import datetime

# -------------------
# Load secrets
# -------------------
load_dotenv()
CLIENT_ID = os.getenv("WHO_CLIENT_ID")
CLIENT_SECRET = os.getenv("WHO_CLIENT_SECRET")

if not CLIENT_ID or not CLIENT_SECRET:
    print("Warning: WHO_CLIENT_ID or WHO_CLIENT_SECRET not found in .env file!")

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
        df = pd.read_csv(path)
        for _, row in df.iterrows():
            code = str(row.get("Code", "")).strip()
            term = str(row.get("Term", "")).strip()
            definition = str(row.get("Short_definition", "")).strip()
            if code:
                NAMASTE_CODES[code] = {
                    "code": code,
                    "display": term,
                    "definition": definition
                }
        print(f"[INFO] Loaded {len(NAMASTE_CODES)} NAMASTE codes")
    except Exception as e:
        print(f"[ERROR] Failed to load NAMASTE CSV: {e}")

# -------------------
# Helpers
# -------------------
def get_who_token():
    """Fetch WHO ICD token using Basic Auth"""
    if not CLIENT_ID or not CLIENT_SECRET:
        return None
    credentials = f"{CLIENT_ID}:{CLIENT_SECRET}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()
    headers = {
        "Authorization": f"Basic {encoded_credentials}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {"scope": "icdapi_access", "grant_type": "client_credentials"}
    r = requests.post(TOKEN_URL, data=data, headers=headers)
    return r.json().get("access_token")

# -------------------
# Routes
# -------------------
@app.route("/")
def home():
    return "WHO ICD + NAMASTE Demo Server 🚀"

@app.route("/token")
def get_token():
    token = get_who_token()
    if not token:
        return jsonify({"error": "Failed to get token"}), 400
    return jsonify({"access_token": token})

@app.route("/search")
def search_icd():
    """Search ICD-11 API with query parameter ?q=term"""
    q = request.args.get("q", "epilepsy")
    token = get_who_token()
    if not token:
        return jsonify({"error": "Failed to get token"}), 400

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "API-Version": "v2",
        "Accept-Language": "en"
    }
    search_url = f"{API_URL}/2024-01/mms/search?q={q}"
    r2 = requests.get(search_url, headers=headers)

    if r2.status_code != 200:
        return jsonify({"error": "WHO ICD search failed", "status": r2.status_code}), 400

    data = r2.json()
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

    return jsonify({"requested_url": search_url, "results": results})

# -------------------
# New Features for SIH Demo
# -------------------

@app.route("/fhir/CodeSystem/namaste")
def get_codesystem():
    """Expose NAMASTE CodeSystem"""
    return {
        "resourceType": "CodeSystem",
        "id": "namaste",
        "url": "https://demo.sih/fhir/CodeSystem/namaste",
        "version": "1.0.0",
        "status": "active",
        "content": "complete",
        "concept": list(NAMASTE_CODES.values()),
        "meta": {
            "versionId": "1",
            "lastUpdated": datetime.utcnow().isoformat()
        }
    }

@app.route("/autocomplete")
def autocomplete():
    """Autocomplete NAMASTE + ICD terms"""
    q = request.args.get("q", "").lower()
    results = []

    # Search NAMASTE
    for code, data in NAMASTE_CODES.items():
        if q in data["display"].lower():
            results.append({
                "system": "https://demo.sih/fhir/CodeSystem/namaste",
                "code": code,
                "display": data["display"],
                "source": "NAMASTE"
            })

    # Search WHO ICD
    token = get_who_token()
    if token:
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "API-Version": "v2"
        }
        r = requests.get(f"{API_URL}/2024-01/mms/search?q={q}", headers=headers)
        if r.status_code == 200:
            for ent in r.json().get("destinationEntities", []):
                results.append({
                    "system": "http://id.who.int/icd/release/11/mms",
                    "code": ent.get("theCode"),
                    "display": ent.get("title", {}).get("@value", ent.get("title", "")),
                    "source": "ICD-11"
                })

    return {"total": len(results), "results": results[:10]}

@app.route("/fhir/ConceptMap/$translate", methods=["POST"])
def translate():
    """Translate NAMASTE code to ICD-11"""
    payload = request.get_json()
    code = payload.get("code")
    nam_term = NAMASTE_CODES.get(code, {}).get("display")

    if not nam_term:
        return {"error": "Code not found"}, 404

    token = get_who_token()
    mapped = []
    if token:
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "API-Version": "v2"
        }
        r = requests.get(f"{API_URL}/2024-01/mms/search?q={nam_term}", headers=headers)
        if r.status_code == 200:
            for res in r.json().get("destinationEntities", [])[:1]:  # just top hit
                mapped.append({
                    "system": "http://id.who.int/icd/release/11/mms",
                    "code": res.get("theCode"),
                    "display": res.get("title", {}).get("@value", res.get("title", ""))
                })

    return {
        "resourceType": "Parameters",
        "parameter": [
            {"name": "result", "valueBoolean": True},
            {"name": "match", "valueCoding": mapped[0]} if mapped else {}
        ]
    }

@app.route("/fhir/Bundle", methods=["POST"])
def receive_bundle():
    """Receive FHIR Bundle with dual coding"""
    bundle = request.get_json()
    if bundle.get("resourceType") != "Bundle":
        return {"error": "Invalid Bundle"}, 400

    stored_conditions = []
    for entry in bundle.get("entry", []):
        res = entry.get("resource", {})
        if res.get("resourceType") == "Condition":
            codings = res.get("code", {}).get("coding", [])
            has_nam = any("namaste" in c.get("system", "") for c in codings)
            has_icd = any("icd" in c.get("system", "") for c in codings)

            if has_nam and not has_icd:
                nam_code = next(c for c in codings if "namaste" in c["system"])["code"]
                # Call translate inline
                trans = app.test_client().post("/fhir/ConceptMap/$translate", json={"code": nam_code})
                if trans.status_code == 200:
                    icd_coding = trans.get_json()["parameter"][1]["valueCoding"]
                    codings.append(icd_coding)

            stored_conditions.append(res)

    return {"status": "accepted", "stored": stored_conditions}, 201

# -------------------
# Run
# -------------------
if __name__ == "__main__":
    ingest_namaste_csv()  # load NAMASTE CSV at startup
    app.run(debug=True, port=5000)
