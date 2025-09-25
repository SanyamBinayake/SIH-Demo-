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
# Load secrets & Initialize App
# -------------------
load_dotenv()
CLIENT_ID = os.getenv("WHO_CLIENT_ID")
CLIENT_SECRET = os.getenv("WHO_CLIENT_SECRET")

if not CLIENT_ID or not CLIENT_SECRET:
    print("🔴 FATAL: WHO_CLIENT_ID or WHO_CLIENT_SECRET not found!")

app = Flask(__name__)
db = DatabaseHelper()

TOKEN_URL = "https://icdaccessmanagement.who.int/connect/token"
API_URL = "https://id.who.int/icd/release/11"

# -------------------
# DATA LOADING (from GitHub, now including Siddha)
# -------------------
ALL_NAMASTE_DATA = {}

def load_namaste_data_from_github():
    """Loads Ayurveda, Unani, and Siddha data directly from GitHub at startup."""
    global ALL_NAMASTE_DATA
    base_url = "https://raw.githubusercontent.com/SanyamBinayake/SIH-Demo-/main/"
    terminologies = {
        "Ayurveda": base_url + "Ayurveda_Codes_Terms.csv",
        "Unani": base_url + "Unani_Codes_Terms.csv",
        "Siddha": base_url + "Siddha_Codes_Terms.csv"
    }
    
    for term_system, url in terminologies.items():
        try:
            df = pd.read_csv(url)
            df.rename(columns={"Explanation": "definition", "Term": "term", "Code": "code"}, inplace=True)
            ALL_NAMASTE_DATA[term_system] = df.to_dict('records')
            print(f"✅ [INFO] Loaded {len(ALL_NAMASTE_DATA[term_system])} codes from {term_system}.")
        except Exception as e:
            print(f"🔴 ERROR: Failed to load {term_system} data from GitHub: {e}")
            ALL_NAMASTE_DATA[term_system] = []

# -------------------
# Helper Functions
# -------------------
def get_who_token():
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
        print(f"🔴 ERROR: Could not get WHO token. Reason: {e}")
        return None

def who_api_search(query, chapter_filter=None):
    token = get_who_token()
    if not token: return []
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json", "API-Version": "v2", "Accept-Language": "en"}
    params = {"q": query}
    if chapter_filter:
        params["useFlexisearch"] = "true"
        params["chapterFilter"] = chapter_filter
    try:
        search_url = f"{API_URL}/2024-01/mms/search"
        r = requests.get(search_url, headers=headers, params=params, timeout=15)
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
def home(): return "WHO ICD + NAMASTE Demo Server 🚀"

@app.route("/search")
def search_biomedicine():
    q = request.args.get("q", "")
    if not q: return jsonify({"results": []})
    return jsonify({"results": who_api_search(q, chapter_filter="!26")})

@app.route("/search/tm2")
def search_tm2():
    q = request.args.get("q", "")
    if not q: return jsonify({"results": []})
    return jsonify({"results": who_api_search(q, chapter_filter="26")})

# --- NEW: Semantic Mapping Endpoint ---
@app.route("/map-code", methods=['POST'])
def map_namaste_to_icd():
    """
    Takes a NAMASTE code, finds its definition, and performs a semantic
    search against ICD-11 to find the best conceptual match.
    """
    payload = request.get_json()
    namaste_code = payload.get("code")

    if not namaste_code:
        return jsonify({"error": "No NAMASTE code provided"}), 400

    # Find the NAMASTE entry across all loaded systems
    source_details = None
    for system in ["Ayurveda", "Unani", "Siddha"]:
        found = next((item for item in ALL_NAMASTE_DATA.get(system, []) if item['code'] == namaste_code), None)
        if found:
            source_details = found
            source_details['system'] = system # Add which system it came from
            break
            
    if not source_details:
        return jsonify({"error": f"Code '{namaste_code}' not found in any NAMASTE system."}), 404

    # Use the full definition for a high-quality search query
    search_query = source_details.get('definition', source_details.get('term', ''))
    
    # Search both Biomedicine and TM2 for the best possible matches
    icd_matches = who_api_search(search_query)

    return jsonify({
        "source_details": source_details,
        "mapped_details": icd_matches[:5] # Return top 5 matches
    })

# -------------------
# FHIR-Specific Route (remains for dual-coding)
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
            namaste_code_obj = next((c for c in codings if "namaste" in c.get("system", "")), None)
            
            if namaste_code_obj:
                with app.test_request_context():
                    map_response = app.test_client().post("/map-code", json={"code": namaste_code_obj['code']})
                    if map_response.status_code == 200:
                        map_data = map_response.get_json()
                        if map_data.get("mapped_details"):
                            best_match = map_data["mapped_details"][0]
                            icd_coding = {
                                "system": "http://id.who.int/icd/release/11/mms",
                                "code": best_match['code'], "display": best_match['term']
                            }
                            codings.append(icd_coding)
            
            processed_conditions.append(resource)

    final_payload = {"status": "accepted", "stored": processed_conditions}
    db.save_bundle(final_payload)
    return jsonify(final_payload), 201

# -------------------
# Run
# -------------------
if __name__ == "__main__":
    load_namaste_data_from_github()
    app.run(debug=True, port=5000)
else:
    load_namaste_data_from_github()

