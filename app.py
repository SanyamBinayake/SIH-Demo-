import streamlit as st
import pandas as pd
import re
import requests

# Set your backend URL here
BACKEND_URL = "https://sih-demo-4z5c.onrender.com"

# --------------------
# UI Customization Section
# --------------------
# 1. Inject custom CSS with st.markdown
st.markdown("""
<style>
/* Target the title header */
h1#unified-namaste-who-icd-search {
    font-size: 26px; font-weight: 600; line-height: 1.2;
}
/* Target the input box label */
div[data-testid="stTextInput"] label {
    font-size: 18px !important; font-weight: 500;
}
</style>
""", unsafe_allow_html=True)

# 2. Create a custom header with your logo and the new title
LOGO_URL = "https://raw.githubusercontent.com/SanyamBinayake/SIH-Demo-/3c131c7e8b87c00be561ae349a84bf7654acd7ad/mediunify_logo_1_-removebg-preview.png"

st.markdown(f"""
<div style="display: flex; align-items: center; margin-bottom: 20px;">
    <img src="{LOGO_URL}" alt="Logo" style="height: 50px; margin-right: 15px;">
    <h1 id="unified-namaste-who-icd-search">Unified NAMASTE + WHO ICD Search</h1>
</div>
""", unsafe_allow_html=True)

# --------------------
# Helper Functions
# --------------------
@st.cache_data
def load_all_data():
    """Loads all terminology CSVs into a dictionary of DataFrames."""
    data = {"ayurveda": None, "unani": None, "siddha": None}
    base_url = "https://raw.githubusercontent.com/SanyamBinayake/SIH-Demo-/main/"
    
    try:
        data["ayurveda"] = pd.read_csv(base_url + "Ayurveda_Codes_Terms.csv")
        st.success("Ayurveda data loaded successfully.")
    except Exception as e:
        st.error(f"Failed to load Ayurveda_Codes_Terms.csv from GitHub: {e}")
        data["ayurveda"] = pd.DataFrame()

    try:
        data["unani"] = pd.read_csv(base_url + "Unani_Codes_Terms.csv")
        st.success("Unani data loaded successfully.")
    except Exception as e:
        st.error(f"Failed to load Unani_Codes_Terms.csv from GitHub: {e}")
        data["unani"] = pd.DataFrame()
        
    # Placeholder for Siddha data
    data["siddha"] = pd.DataFrame()
    st.info("Siddha data is not yet available and has been loaded as an empty set.")

    return data

def show_with_load_more(results, section_key, source="namaste", page_size=15):
    """Displays a list of results with a "Load More" button for pagination."""
    if section_key not in st.session_state:
        st.session_state[section_key] = page_size
    visible_count = st.session_state[section_key]

    for row in results[:visible_count]:
        code = row.get("code") if source.startswith("icd") else row.get("Code", "N/A")
        term = row.get("term") if source.startswith("icd") else row.get("Term", "N/A")
        
        with st.expander(f"`{code}` - {term}"):
            if source.startswith("icd"):
                 st.markdown(f"**Definition:** {row.get('definition', 'N/A')}")
            else:
                st.markdown(f"**Explanation:** {row.get('Explanation', 'N/A')}")

    if len(results) > visible_count:
        st.write(f"Showing {visible_count} of {len(results)} results.")
        if st.button("Load More", key=f"load_more_{section_key}"):
            st.session_state[section_key] += page_size
            st.rerun()
            
def handle_api_request(endpoint, query):
    try:
        response = requests.get(f"{BACKEND_URL}{endpoint}", params={"q": query}, timeout=20)
        response.raise_for_status()
        return response.json().get("results", [])
    except requests.exceptions.RequestException as e:
        st.error(f"Failed to connect to the backend API. Error: {e}")
        return []

# --------------------
# Main Application Logic
# --------------------
all_data = load_all_data()

# Create main tabs
search_tab, translate_tab, bundle_tab = st.tabs(["⚕️ Terminology Search", "↔️ Translation", "🧾 Save Bundle"])

with search_tab:
    query = st.text_input("🔍 Search for a diagnosis (term, code, or explanation)", help="Try 'Jwara', 'Fever', or 'Vertigo'")
    
    if 'current_query' not in st.session_state or st.session_state.current_query != query:
        st.session_state.current_query = query
        for key in ["ayurveda", "unani", "siddha", "icd_bio", "icd_tm2"]:
            if key in st.session_state:
                del st.session_state[key]
    
    if query:
        query_lower = query.lower()
        
        st.subheader("NAMASTE Terminologies")
        namaste_ayur, namaste_unani, namaste_siddha = st.tabs(["Ayurveda", "Unani", "Siddha"])
        
        with namaste_ayur:
            df = all_data["ayurveda"]
            if not df.empty:
                mask = df.apply(lambda row: any(query_lower in str(cell).lower() for cell in row), axis=1)
                results = df[mask].to_dict("records")
                st.write(f"Found {len(results)} total matches.")
                if results: show_with_load_more(results, "ayurveda", "namaste")

        with namaste_unani:
            df = all_data["unani"]
            if not df.empty:
                mask = df.apply(lambda row: any(query_lower in str(cell).lower() for cell in row), axis=1)
                results = df[mask].to_dict("records")
                st.write(f"Found {len(results)} total matches.")
                if results: show_with_load_more(results, "unani", "namaste")

        with namaste_siddha:
            st.warning("Siddha terminology data is not yet available.")

        st.subheader("WHO ICD-11 Terminologies")
        icd_bio, icd_tm2 = st.tabs(["Biomedicine", "TM2"])

        with icd_bio:
            results = handle_api_request("/search", query)
            st.write(f"Found {len(results)} total matches.")
            if results: show_with_load_more(results, "icd_bio", "icd")
            
        with icd_tm2:
            results = handle_api_request("/search/tm2", query)
            st.write(f"Found {len(results)} total matches.")
            if results: show_with_load_more(results, "icd_tm2", "icd")
    else:
        st.info("Type a diagnosis in the search box above to begin.")

with translate_tab:
    st.subheader("Translate Between Terminologies")
    st.info("Enter a code or term from a source system to find its equivalent in a target system.")
    
    col1, col2 = st.columns(2)
    with col1:
        source_system = st.selectbox("Source System", ["NAMASTE-Ayurveda", "NAMASTE-Unani", "ICD-11-Biomedicine", "ICD-11-TM2"])
    with col2:
        target_system = st.selectbox("Target System", ["ICD-11-Biomedicine", "ICD-11-TM2", "NAMASTE-Ayurveda", "NAMASTE-Unani"])
        
    term_to_translate = st.text_input("Enter code or term to translate")

    if st.button("Translate"):
        if not term_to_translate:
            st.warning("Please enter a term or code to translate.")
        else:
            with st.spinner("Translating..."):
                try:
                    payload = {"source": source_system, "target": target_system, "query": term_to_translate}
                    response = requests.post(f"{BACKEND_URL}/translate", json=payload, timeout=30)
                    response.raise_for_status()
                    translation_results = response.json()
                    
                    st.success("Translation complete!")
                    st.write(f"Found **{translation_results.get('match_count', 0)}** potential matches:")
                    
                    for match in translation_results.get("matches", []):
                        with st.container(border=True):
                            st.markdown(f"**Code:** `{match.get('code')}`")
                            st.markdown(f"**Term:** {match.get('term')}")
                            if "definition" in match and pd.notna(match['definition']):
                                st.markdown(f"**Definition:** {match.get('definition')}")
                            if "explanation" in match and pd.notna(match['explanation']):
                                st.markdown(f"**Explanation:** {match.get('explanation')}")

                except requests.exceptions.RequestException as e:
                    st.error(f"Translation failed. Could not connect to the backend: {e}")

with bundle_tab:
    st.subheader("🧾 Demo: Save Condition to FHIR Bundle")
    namaste_code = st.text_input("Enter NAMASTE code (e.g., AYU-AAA-1)", key="bundle_namaste_code")
    patient_id = st.text_input("Enter Patient ID", "Patient/001", key="bundle_patient_id")
    if st.button("Save Condition Bundle"):
        if not namaste_code:
            st.warning("Please enter a NAMASTE code.")
        else:
            with st.spinner("Saving bundle..."):
                bundle = {"resourceType": "Bundle", "type": "collection", "entry": [{"resource": {"resourceType": "Condition", "code": {"coding": [{"system": "https://demo.sih/fhir/CodeSystem/namaste", "code": namaste_code, "display": "NAMASTE term"}]}, "subject": {"reference": patient_id}}}]}
                try:
                    resp = requests.post(f"{BACKEND_URL}/fhir/Bundle", json=bundle, timeout=30)
                    if resp.status_code == 201:
                        st.success("✅ Condition stored with dual coding!")
                        st.json(resp.json())
                    else:
                        st.error(f"❌ Failed to save bundle. Server responded with status {resp.status_code}:")
                        st.json(resp.json())
                except requests.exceptions.RequestException as e:
                    st.error(f"❌ Error connecting to the backend: {e}")

