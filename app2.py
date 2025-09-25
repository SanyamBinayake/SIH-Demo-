import re
from flask import Flask, jsonify, request
import requests
import os
from dotenv import load_dotenv
import base64
import pandas as pd
from datetime import datetime
from db_helper import DatabaseHelper
import json
from fuzzywuzzy import fuzz
from difflib import SequenceMatcher
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from nltk.stem import PorterStemmer
import string

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
API_URL = "https://id.who.int/icd/release/11/2024-01/mms"

# Initialize NLTK components (download if needed)
def download_nltk_data():
    """Download NLTK data with proper error handling."""
    try:
        # Try to download required NLTK data
        import ssl
        try:
            _create_unverified_https_context = ssl._create_unverified_context
        except AttributeError:
            pass
        else:
            ssl._create_default_https_context = _create_unverified_https_context
        
        # Download punkt tokenizer
        try:
            nltk.data.find('tokenizers/punkt')
        except LookupError:
            print("📥 Downloading NLTK punkt tokenizer...")
            nltk.download('punkt', quiet=True)
        
        # Download punkt_tab tokenizer (newer NLTK versions)
        try:
            nltk.data.find('tokenizers/punkt_tab')
        except LookupError:
            print("📥 Downloading NLTK punkt_tab tokenizer...")
            nltk.download('punkt_tab', quiet=True)
        
        # Download stopwords
        try:
            nltk.data.find('corpora/stopwords')
        except LookupError:
            print("📥 Downloading NLTK stopwords...")
            nltk.download('stopwords', quiet=True)
            
        return True
    except Exception as e:
        print(f"🟡 WARNING: Could not download NLTK data: {e}")
        return False

# Try to download NLTK data
NLTK_AVAILABLE = download_nltk_data()

# -------------------
# DATA LOADING
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
# Dynamic NLP Processing Functions
# -------------------
class DynamicTermProcessor:
    def __init__(self):
        if NLTK_AVAILABLE:
            try:
                self.stemmer = PorterStemmer()
                self.stop_words = set(stopwords.words('english'))
                self.nltk_ready = True
            except Exception as e:
                print(f"🟡 WARNING: NLTK components not available: {e}")
                self.nltk_ready = False
        else:
            self.nltk_ready = False
            
        # Fallback stop words if NLTK fails
        self.fallback_stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 
            'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'be', 
            'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 
            'would', 'should', 'could', 'can', 'may', 'might', 'must', 'this', 
            'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they'
        }
        
        # Medical term patterns for better extraction
        self.medical_patterns = [
            r'\b(?:disease|disorder|condition|syndrome|symptom|pain|ache)\b',
            r'\b(?:fever|headache|nausea|vomiting|diarrhea|constipation)\b',
            r'\b(?:inflammation|infection|swelling|bleeding|weakness)\b',
            r'\b(?:chronic|acute|severe|mild|persistent|intermittent)\b',
            r'\b(?:cough|cold|flu|asthma|bronchitis|pneumonia)\b',
            r'\b(?:diabetes|hypertension|arthritis|gastritis)\b'
        ]
    
    def simple_tokenize(self, text):
        """Fallback tokenizer if NLTK is not available."""
        # Simple word extraction using regex
        words = re.findall(r'\b[a-zA-Z]{2,}\b', text.lower())
        return words
    
    def extract_medical_terms(self, text):
        """Extract medical terms from text using NLP or fallback methods."""
        if not isinstance(text, str):
            return []
        
        # Clean and normalize text
        text = text.lower().strip()
        
        # Remove content in brackets and parentheses
        text = re.sub(r'[\[\(].*?[\]\)]', '', text)
        
        # Extract sentences and split by common delimiters
        sentences = re.split(r'[.;,/\-]', text)
        
        extracted_terms = []
        
        for sentence in sentences:
            # Clean sentence
            sentence = re.sub(r'[^\w\s]', ' ', sentence)
            
            # Tokenize - use NLTK if available, otherwise fallback
            if self.nltk_ready:
                try:
                    words = word_tokenize(sentence)
                    stop_words = self.stop_words
                except Exception:
                    words = self.simple_tokenize(sentence)
                    stop_words = self.fallback_stop_words
            else:
                words = self.simple_tokenize(sentence)
                stop_words = self.fallback_stop_words
            
            # Remove stopwords and short words
            meaningful_words = [w for w in words if w not in stop_words and len(w) > 2]
            
            # Check for medical patterns
            sentence_clean = ' '.join(meaningful_words)
            for pattern in self.medical_patterns:
                matches = re.findall(pattern, sentence_clean)
                extracted_terms.extend(matches)
            
            # Add meaningful word combinations
            if len(meaningful_words) >= 2:
                # Add 2-word combinations
                for i in range(len(meaningful_words) - 1):
                    combo = ' '.join(meaningful_words[i:i+2])
                    if len(combo) > 5:  # Skip very short combinations
                        extracted_terms.append(combo)
            
            # Add individual meaningful words
            for word in meaningful_words:
                if len(word) > 3:
                    extracted_terms.append(word)
        
        # Remove duplicates and return top terms
        unique_terms = list(set(extracted_terms))
        return unique_terms[:10]  # Return top 10 terms
    
    def generate_search_variants(self, term):
        """Generate search variants for a term."""
        variants = [term]
        
        # Add stemmed version if NLTK is available
        if self.nltk_ready:
            try:
                stemmed = self.stemmer.stem(term)
                if stemmed != term:
                    variants.append(stemmed)
            except Exception:
                pass  # Skip if stemming fails
        
        # Add plural/singular variants
        if term.endswith('s'):
            variants.append(term[:-1])  # Remove 's' for singular
        else:
            variants.append(term + 's')  # Add 's' for plural
        
        # Add common medical suffix variants
        medical_suffixes = ['itis', 'osis', 'emia', 'pathy', 'algia']
        for suffix in medical_suffixes:
            if term.endswith(suffix):
                root = term[:-len(suffix)]
                if len(root) > 2:
                    variants.append(root)
            else:
                if len(term) > 3:  # Only add suffix to reasonable length words
                    variants.append(term + suffix)
        
        return list(set(variants))  # Remove duplicates

# -------------------
# Enhanced Helper Functions
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

def who_api_search(query, chapter_filter=None, limit=10):
    """Enhanced WHO API search with configurable limits."""
    token = get_who_token()
    if not token: 
        return []
    
    headers = {
        "Authorization": f"Bearer {token}", 
        "Accept": "application/json", 
        "API-Version": "v2", 
        "Accept-Language": "en"
    }
    params = {"q": query}
    if chapter_filter:
        params["useFlexisearch"] = "true"
        params["chapterFilter"] = chapter_filter
    
    try:
        r = requests.get(f"{API_URL}/search", headers=headers, params=params, timeout=15)
        if r.status_code == 200:
            results = []
            entities = r.json().get("destinationEntities", [])[:limit]  # Limit results
            
            for ent in entities:
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

def calculate_semantic_similarity(text1, text2):
    """
    Calculate semantic similarity between two medical texts.
    Uses fallback methods if NLTK is not available.
    """
    if not text1 or not text2:
        return 0
    
    # Normalize texts
    text1_clean = re.sub(r'[^\w\s]', ' ', text1.lower())
    text2_clean = re.sub(r'[^\w\s]', ' ', text2.lower())
    
    # Tokenize - with fallback
    if NLTK_AVAILABLE:
        try:
            tokens1 = set(word_tokenize(text1_clean))
            tokens2 = set(word_tokenize(text2_clean))
            stop_words = set(stopwords.words('english'))
        except Exception:
            # Fallback tokenization
            tokens1 = set(re.findall(r'\b[a-zA-Z]{2,}\b', text1_clean))
            tokens2 = set(re.findall(r'\b[a-zA-Z]{2,}\b', text2_clean))
            stop_words = {
                'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 
                'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'be'
            }
    else:
        # Simple tokenization
        tokens1 = set(re.findall(r'\b[a-zA-Z]{2,}\b', text1_clean))
        tokens2 = set(re.findall(r'\b[a-zA-Z]{2,}\b', text2_clean))
        stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 
            'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'be'
        }
    
    # Remove stopwords
    tokens1 = tokens1 - stop_words
    tokens2 = tokens2 - stop_words
    
    # Calculate Jaccard similarity (intersection over union)
    if not tokens1 or not tokens2:
        jaccard_sim = 0
    else:
        intersection = tokens1.intersection(tokens2)
        union = tokens1.union(tokens2)
        jaccard_sim = len(intersection) / len(union)
    
    # Calculate fuzzy similarity
    fuzz_sim = fuzz.ratio(text1.lower(), text2.lower()) / 100
    
    # Calculate sequence similarity
    seq_sim = SequenceMatcher(None, text1.lower(), text2.lower()).ratio()
    
    # Weighted combination
    final_score = (jaccard_sim * 0.4 + fuzz_sim * 0.3 + seq_sim * 0.3)
    
    return final_score

def dynamic_mapping_engine(namaste_code, namaste_term, namaste_definition):
    """
    Core dynamic mapping engine that uses multiple strategies to find ICD-11 matches.
    """
    processor = DynamicTermProcessor()
    all_candidates = []
    
    print(f"🔍 Starting dynamic mapping for {namaste_code}: {namaste_term}")
    
    # Strategy 1: Direct term search with variants
    print("📋 Strategy 1: Direct term search")
    direct_terms = [namaste_term] + processor.generate_search_variants(namaste_term)
    for term in direct_terms[:5]:  # Limit to 5 variants
        if len(term.strip()) > 2:
            results = who_api_search(term.strip(), limit=5)
            for result in results:
                similarity = calculate_semantic_similarity(namaste_term, result["term"])
                all_candidates.append({
                    **result,
                    "confidence": similarity,
                    "method": "direct_term",
                    "search_term": term
                })
    
    # Strategy 2: Medical term extraction from definition
    print("🔬 Strategy 2: Medical term extraction")
    extracted_terms = processor.extract_medical_terms(namaste_definition)
    for term in extracted_terms[:7]:  # Top 7 extracted terms
        if len(term.strip()) > 2:
            # Search in general ICD-11
            results = who_api_search(term.strip(), limit=3)
            for result in results:
                def_similarity = calculate_semantic_similarity(namaste_definition, result["definition"])
                term_similarity = calculate_semantic_similarity(term, result["term"])
                combined_similarity = (def_similarity * 0.7 + term_similarity * 0.3)
                
                all_candidates.append({
                    **result,
                    "confidence": combined_similarity,
                    "method": "definition_extraction",
                    "search_term": term
                })
    
    # Strategy 3: Traditional Medicine Module (TM2) specific search
    print("🌿 Strategy 3: TM2 chapter search")
    tm_search_terms = [namaste_term] + extracted_terms[:5]
    for term in tm_search_terms:
        if len(term.strip()) > 2:
            results = who_api_search(term.strip(), chapter_filter="26", limit=3)
            for result in results:
                similarity = calculate_semantic_similarity(namaste_definition, result["definition"])
                # Boost TM2 results since they're more relevant for traditional medicine
                boosted_similarity = min(similarity * 1.3, 1.0)
                
                all_candidates.append({
                    **result,
                    "confidence": boosted_similarity,
                    "method": "tm2_chapter",
                    "search_term": term
                })
    
    # Strategy 4: Symptom-based search
    print("🩺 Strategy 4: Symptom-based search")
    symptom_keywords = ['pain', 'ache', 'fever', 'nausea', 'weakness', 'inflammation', 'swelling']
    definition_lower = namaste_definition.lower()
    
    for keyword in symptom_keywords:
        if keyword in definition_lower:
            results = who_api_search(keyword, limit=3)
            for result in results:
                similarity = calculate_semantic_similarity(namaste_definition, result["definition"])
                all_candidates.append({
                    **result,
                    "confidence": similarity * 0.8,  # Slightly lower confidence for symptom-based
                    "method": "symptom_based",
                    "search_term": keyword
                })
    
    # Remove duplicates based on ICD code
    seen_codes = set()
    unique_candidates = []
    
    for candidate in all_candidates:
        code = candidate.get("code", "")
        if code not in seen_codes and code != "N/A":
            seen_codes.add(code)
            unique_candidates.append(candidate)
    
    # Sort by confidence score
    unique_candidates.sort(key=lambda x: x.get("confidence", 0), reverse=True)
    
    # Return top 5 matches with detailed scoring
    top_matches = unique_candidates[:5]
    
    print(f"✅ Found {len(top_matches)} unique matches with confidence scores")
    for i, match in enumerate(top_matches):
        print(f"   {i+1}. {match['code']} - {match['term'][:50]}... (confidence: {match['confidence']:.3f})")
    
    return top_matches

# -------------------
# Main API Routes
# -------------------
@app.route("/")
def home(): 
    return "🚀 Dynamic NAMASTE ↔ ICD-11 Mapping Server"

@app.route("/search")
def search_biomedicine():
    q = request.args.get("q", "")
    if not q: 
        return jsonify({"results": []})
    return jsonify({"results": who_api_search(q, chapter_filter="!26")})

@app.route("/search/tm2")
def search_tm2():
    q = request.args.get("q", "")
    if not q: 
        return jsonify({"results": []})
    return jsonify({"results": who_api_search(q, chapter_filter="26")})

@app.route("/map-code", methods=['POST'])
def map_namaste_to_icd():
    """Dynamic mapping endpoint - no static mappings used."""
    payload = request.get_json()
    namaste_code = payload.get("code")
    
    if not namaste_code: 
        return jsonify({"error": "No NAMASTE code provided"}), 400

    # Find the NAMASTE code details
    source_details = None
    for system, data in ALL_NAMASTE_DATA.items():
        found = next((item for item in data if item['code'] == namaste_code), None)
        if found:
            source_details = found
            source_details['system'] = system
            break
            
    if not source_details:
        return jsonify({"error": f"Code '{namaste_code}' not found in any NAMASTE system."}), 404

    try:
        namaste_term = source_details.get('term', '')
        namaste_definition = source_details.get('definition', '')
        
        # Use dynamic mapping engine
        mapped_results = dynamic_mapping_engine(namaste_code, namaste_term, namaste_definition)
        
        # Format results for frontend
        formatted_results = []
        for result in mapped_results:
            formatted_results.append({
                "code": result["code"],
                "term": result["term"],
                "definition": result["definition"][:200] + "..." if len(result["definition"]) > 200 else result["definition"],
                "confidence": f"{result.get('confidence', 0):.3f}",
                "method": result.get('method', 'unknown'),
                "search_term": result.get('search_term', 'N/A')
            })
        
        return jsonify({
            "source_details": source_details, 
            "mapped_details": formatted_results,
            "total_candidates_found": len(mapped_results),
            "mapping_success": len(formatted_results) > 0
        })
        
    except Exception as e:
        print(f"🔴 ERROR in dynamic mapping: {e}")
        return jsonify({
            "source_details": source_details,
            "mapped_details": [],
            "error": f"Dynamic mapping failed: {str(e)}",
            "mapping_success": False
        }), 500

# -------------------
# FHIR-Specific Route
# -------------------
@app.route("/fhir/Bundle", methods=["POST"])
def receive_bundle():
    """Process FHIR Bundle with dynamic mapping."""
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
                try:
                    with app.test_request_context():
                        map_response = app.test_client().post("/map-code", json={"code": namaste_code_obj['code']})
                        if map_response.status_code == 200:
                            map_data = map_response.get_json()
                            mapped_details = map_data.get("mapped_details", [])
                            
                            # Add the best match (highest confidence)
                            if mapped_details:
                                best_match = mapped_details[0]
                                confidence_score = float(best_match.get('confidence', '0'))
                                
                                # Only add ICD coding if confidence is above threshold
                                if confidence_score > 0.1:  # Minimum confidence threshold
                                    icd_coding = {
                                        "system": "http://id.who.int/icd/release/11/mms",
                                        "code": best_match['code'],
                                        "display": best_match['term']
                                    }
                                    codings.append(icd_coding)
                                    
                                    # Add metadata about the mapping
                                    resource["meta"] = {
                                        "tag": [{
                                            "system": "https://demo.sih/fhir/CodeSystem/mapping-metadata",
                                            "code": "dynamic-mapping",
                                            "display": f"Dynamic mapping (confidence: {best_match.get('confidence', '0.000')}, method: {best_match.get('method', 'unknown')})"
                                        }]
                                    }
                except Exception as e:
                    print(f"🔴 ERROR in bundle dynamic mapping: {e}")
            
            processed_conditions.append(resource)

    final_payload = {"status": "accepted", "stored": processed_conditions, "mapping_method": "dynamic"}
    db.save_bundle(final_payload)
    return jsonify(final_payload), 201

# -------------------
# Additional utility endpoints
# -------------------
@app.route("/mapping-health")
def mapping_health():
    """Health check for the dynamic mapping system."""
    return jsonify({
        "system_status": "operational",
        "mapping_method": "fully_dynamic",
        "nlp_components": "loaded" if NLTK_AVAILABLE else "fallback_mode",
        "nltk_status": "available" if NLTK_AVAILABLE else "using_fallback",
        "namaste_systems_loaded": list(ALL_NAMASTE_DATA.keys()),
        "total_namaste_codes": sum(len(data) for data in ALL_NAMASTE_DATA.values()),
        "who_api_status": "connected" if get_who_token() else "disconnected"
    })

# -------------------
# Run
# -------------------
if __name__ == "__main__":
    load_namaste_data_from_github()
    app.run(debug=True, port=5000)
else:
    # This runs when Gunicorn starts the app on Render
    load_namaste_data_from_github()