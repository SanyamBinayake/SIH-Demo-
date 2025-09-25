import re
from flask import Flask, jsonify, request
import requests
import os
from dotenv import load_dotenv
import base64
import pandas as pd
from datetime import datetime, timedelta
# Assuming db_helper.py is in the same directory, adjusted import if needed
from .db_helper import DatabaseHelper 
import json

# -------------------
# Load secrets & Initialize App
# -------------------
# Load .env file from the root directory
load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')) 

CLIENT_ID = os.getenv("WHO_CLIENT_ID")
CLIENT_SECRET = os.getenv("WHO_CLIENT_SECRET")

if not CLIENT_ID or not CLIENT_SECRET:
    # Changed FATAL to a WARNING since app can still run without ICD features
    print("🔴 WARNING: WHO_CLIENT_ID or WHO_CLIENT_SECRET not found! ICD-11 calls will fail.")

app = Flask(__name__)
# Assuming DatabaseHelper is correctly defined in db_helper.py
db = DatabaseHelper()

TOKEN_URL = "https://icdaccessmanagement.who.int/connect/token"
API_URL = "https://id.who.int/icd/release/11/2024-01" # Using a stable, versioned base URL

# -------------------
# Global State and Data Loading
# -------------------
ALL_NAMASTE_DATA = {}
WHO_TOKEN = None
TOKEN_EXPIRY = datetime.now()

# -------------------
# Core Improvement 1: Data Cleaning Function
# -------------------
def extract_explicit_icd(explanation):
    """
    Uses regex to extract the explicit ICD-11 TM2 term/code 
    that is often embedded at the end of the Explanation field in the format:
    ",Aggravation of vata pattern (TM2)"
    """
    if isinstance(explanation, str):
        # Regex looks for: (a comma or space), then any characters (the term), 
        # followed by (TM2) at the end of the string.
        match = re.search(r'([A-Za-z0-9\s#\(\)-]+)\s*\(TM2\)$', explanation.strip())
        if match:
            # Clean up the extracted term
            return match.group(1).strip().strip(',')
    return None

def get_icd_token():
    """Fetches a new ICD-11 API token and caches it."""
    global WHO_TOKEN, TOKEN_EXPIRY
    
    # Check cache expiry (buffer of 5 minutes)
    if WHO_TOKEN and TOKEN_EXPIRY > datetime.now() + timedelta(seconds=300):
        return WHO_TOKEN

    if not CLIENT_ID or not CLIENT_SECRET:
         return None # Cannot fetch token without credentials

    print("🔑 Fetching new ICD-11 token...")
    try:
        client_auth = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Authorization': f'Basic {client_auth}'
        }
        data = {'grant_type': 'client_credentials', 'scope': API_URL}
        
        response = requests.post(TOKEN_URL, headers=headers, data=data, timeout=15)
        response.raise_for_status()
        token_data = response.json()
        
        WHO_TOKEN = token_data['access_token']
        TOKEN_EXPIRY = datetime.now() + timedelta(seconds=token_data['expires_in'] - 300) 
        
        print("✅ Token fetched and cached successfully.")
        return WHO_TOKEN
    
    except requests.exceptions.RequestException as e:
        print(f"🔴 ERROR: Failed to get ICD-11 token: {e}")
        return None
    except KeyError:
        print(f"🔴 ERROR: Invalid response from token server: {response.text}")
        return None

# -------------------
# Core Improvement 2: Data Loading with Cleaning
# -------------------
def load_namaste_data_from_github():
    """Loads Ayurveda, Unani, and Siddha data, extracting the explicit TM2 term."""
    global ALL_NAMASTE_DATA
    base_url = "https://raw.githubusercontent.com/SanyamBinayake/SIH-Demo-/main/"
    terminologies = {
        "Ayurveda": base_url + "Ayurveda Codes & Terms.csv",
        "Unani": base_url + "Unani Codes & Terms.csv",
        "Siddha": base_url + "Siddha_Codes_Terms.csv"
    }

    print("🔄 Loading NAMASTE data from GitHub...")
    for system, url in terminologies.items():
        try:
            df = pd.read_csv(url, encoding='utf-8')
            # NEW: Clean the Explanation field and store the result
            df['Explicit_ICD11_Term'] = df['Explanation'].apply(extract_explicit_icd) 
            
            # Use 'Code' as the key for fast lookup
            ALL_NAMASTE_DATA.update({row['Code']: row.to_dict() for _, row in df.iterrows()})
            print(f"✅ Loaded {len(df)} {system} terms.")
        except Exception as e:
            print(f"🔴 ERROR: Failed to load {system} data from {url}: {e}")

# Load data on app startup
load_namaste_data_from_github()

# -------------------
# Helper functions for ICD-11
# -------------------

def search_icd_api(query, filter_type=None, limit=10):
    """Performs a search against the WHO ICD-11 API."""
    token = get_icd_token()
    if not token:
        return {"error": "Authentication failed or token expired."}

    headers = {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/json',
        'Accept-Language': 'en',
        'API-Version': 'v2'
    }
    
    # IMPORTANT: The ICD-11 search endpoint is /search relative to the API_URL
    search_url = f"{API_URL}/search"
    
    params = {
        'q': query,
        'limit': limit,
        'linearization': 'mms' # Main Mortality and Morbidity list
    }
    
    if filter_type == 'Traditional Medicine 2':
        # TM2 is Chapter 26 (Codes: SR, SM, SU)
        params['filter'] = 'chapter=26' 
    elif filter_type == 'Biomedicine':
        # Exclude the TM2 chapter
        params['filter'] = 'chapter!=26'

    try:
        response = requests.get(search_url, headers=headers, params=params, timeout=15)
        response.raise_for_status() 
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"🔴 ERROR: ICD-11 API search failed: {e}")
        return {"error": f"ICD-11 API search failed: {e}"}

# -------------------
# Flask API Endpoints
# -------------------

# (omitted: /search-namaste - remains unchanged)

# (omitted: /search-icd - remains unchanged)

@app.route("/map-code", methods=["POST"])
def map_code():
    """
    CORE MAPPING LOGIC: Prioritizes the clean, extracted term for ICD-11 search.
    """
    data = request.get_json()
    namaste_code = data.get('code')

    if not namaste_code:
        return jsonify({"error": "Missing 'code' in request body"}), 400

    # 1. Look up NAMASTE code details
    namaste_info = ALL_NAMASTE_DATA.get(namaste_code)
    if not namaste_info:
        return jsonify({"error": f"NAMASTE code {namaste_code} not found."}), 404

    # ----------------------------------------------------
    # CRITICAL CHANGE: Use the extracted clean term for accuracy
    # ----------------------------------------------------
    search_query = namaste_info.get('Explicit_ICD11_Term')
    
    # Fallback 1: If the explicit term is missing, try the main 'Term'
    if not search_query:
        search_query = namaste_info.get('Term')

    # Fallback 2 (Original, less accurate): Use the full Explanation, but truncate it
    if not search_query:
        # Take the first 50 characters to avoid huge keyword phrases
        search_query = namaste_info.get('Explanation', '')[:50] 

    if not search_query:
        return jsonify({"error": "NAMASTE term has no usable search query."}), 404
        
    # 2. Perform the ICD-11 search using the CLEANED query
    # TM2 filter is key to finding the right codes (SR, SM, SU)
    icd_response = search_icd_api(search_query, filter_type='Traditional Medicine 2', limit=5)

    if icd_response.get("error"):
        return jsonify({"error": "ICD-11 API search failed during mapping."}), 500

    mapped_details = [
        {"code": entity.get("code"), "term": entity.get("title"), "uri": entity.get("id")} 
        for entity in icd_response.get("destinationEntities", [])
    ]
    
    return jsonify({
        "namaste_info": namaste_info,
        "mapped_details": mapped_details
    })

# (omitted: /fhir/Bundle - remains unchanged)

if __name__ == "__main__":
    app.run(debug=True, port=5000)
