from flask import Flask, jsonify, request
import requests
import os
from dotenv import load_dotenv
import base64
import pandas as pd
from datetime import datetime
from db_helper import DatabaseHelper
import json

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

# --- Initialize Database Helper ---
# This is done here so it's globally accessible to the app
db = DatabaseHelper()

TOKEN_URL = "https://icdaccessmanagement.who.int/connect/token"
API_URL = "https://id.who.int/icd/release/11"

# -------------------
# DATA LOADING (from GitHub)
# -------------------
ALL_NAMASTE_DATA = {}

def load_namaste_data_from_github():
    """Loads Ayurveda and Unani data directly from GitHub at startup."""
    global ALL_NAMASTE_DATA
    base_url = "https://raw.githubusercontent.com/SanyamBinayake/SIH-Demo-/main/"
    terminologies = {
        "Ayurveda": base_url + "Ayurveda_Codes_Terms.csv",
        "Unani": base_url + "Unani_Codes_Terms.csv"
    }
    
    for term_system, url in terminologies.items():
        try:
            df = pd.read_csv(url)
            # Standardize column names for easier processing
            df.rename(columns={"Explanation": "definition", "Term": "term", "Code": "code"}, inplace=True)
            ALL_NAMASTE_DATA[term_system] = df.to_dict('records')
            print(f"✅ [INFO] Loaded {len(ALL_NAMASTE_DATA[term_system])} codes from {term_system}.")
        except Exception as e:
            print(f"🔴 ERROR: Failed to load {term_system} data from GitHub: {e}")
            ALL_NAMASTE_DATA[term_system] = []

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
    if not token: return []

    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json", "API-Version": "v2", "Accept-Language": "en"}
    params = {"q": query}
    if chapter_filter:
        params["useFlexisearch"] = "true" # Required for chapter filtering
        params["chapterFilter"] = chapter_filter
    
    try:
        r = requests.get(f"{API_URL}/mms/search", headers=headers, params=params, timeout=15)
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
            print(f"🟡 WARNING: WHO API returned status {r.status_code} for query '{query}': {r.text}")
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
    q = request.args.get("q", "")
    if not q: return jsonify({"results": []})
    results = who_api_search(q, chapter_filter="!26") # Exclude TM2
    return jsonify({"results": results})

@app.route("/search/tm2")
def search_tm2():
    q = request.args.get("q", "")
    if not q: return jsonify({"results": []})
    results = who_api_search(q, chapter_filter="26") # ONLY TM2
    return jsonify({"results": results})

@app.route("/translate", methods=['POST'])
def translate_terminology():
    payload = request.get_json()
    source = payload.get("source")
    target = payload.get("target")
    query = payload.get("query")

    if not all([source, target, query]):
        return jsonify({"error": "Missing source, target, or query"}), 400

    search_term = query
    # If source is NAMASTE, find the English term to search in ICD-11
    if source.startswith("NAMASTE"):
        system = source.split('-')[1] # Ayurveda or Unani
        # Find the term associated with the code
        found_entry = next((item for item in ALL_NAMASTE_DATA.get(system, []) if item['code'] == query), None)
        if found_entry:
            search_term = found_entry['term']

    matches = []
    # If target is ICD-11, search the WHO API
    if target.startswith("ICD-11"):
        chapter = "26" if "TM2" in target else "!26"
        matches = who_api_search(search_term, chapter_filter=chapter)
    
    # If target is NAMASTE, search the loaded data
    elif target.startswith("NAMASTE"):
        system = target.split('-')[1] # Ayurveda or Unani
        query_lower = search_term.lower()
        for item in ALL_NAMASTE_DATA.get(system, []):
            if query_lower in str(item['term']).lower() or query_lower in str(item['definition']).lower():
                matches.append({"code": item['code'], "term": item['term'], "explanation": item['definition']})

    return jsonify({"match_count": len(matches), "matches": matches})

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
                # Use the internal translate function by calling the endpoint
                with app.test_request_context():
                    translate_response = app.test_client().post(
                        "/translate",
                        json={
                            "source": "NAMASTE-Ayurveda", # Assuming Ayurveda for now, can be enhanced
                            "target": "ICD-11-Biomedicine",
                            "query": nam_code_obj['code']
                        }
                    )
                    if translate_response.status_code == 200:
                        translate_data = translate_response.get_json()
                        if translate_data.get("matches"):
                            best_match = translate_data["matches"][0]
                            icd_coding = {
                                "system": "http://id.who.int/icd/release/11/mms",
                                "code": best_match['code'],
                                "display": best_match['term']
                            }
                            codings.append(icd_coding)
            
            processed_conditions.append(resource)

    final_payload = {"status": "accepted", "stored": processed_conditions}
    
    # Save the final bundle to the database
    db.save_bundle(final_payload)
    
    return jsonify(final_payload), 201

# -------------------
# Run
# -------------------
if __name__ == "__main__":
    load_namaste_data_from_github()
    app.run(debug=True, port=5000)
else:
    # This runs when Gunicorn starts the app on Render
    load_namaste_data_from_github()
