import streamlit as st
import pandas as pd
import requests

# Set your backend URL here
BACKEND_URL = "https://sih-demo-4z5c.onrender.com"

# --------------------
# UI Customization Section
# --------------------
st.set_page_config(layout="wide") # Use a wider layout for the mapper

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
/* Custom styles for the mapper cards */
.mapper-card {
    background-color: #262730;
    padding: 20px;
    border-radius: 10px;
    border: 1px solid #3D3D3D;
    height: 100%;
}
.mapper-card h3 {
    margin-top: 0;
    color: #00A9E0;
}
</style>
""", unsafe_allow_html=True)

# Create a custom header with your logo and the new title
LOGO_URL = "https://raw.githubusercontent.com/SanyamBinayake/SIH-Demo-/main/mediunify_logo_1_-removebg-preview.png"
st.markdown(f"""
<div style="display: flex; align-items: center; margin-bottom: 20px;">
    <img src="{LOGO_URL}" alt="Logo" style="height: 50px; margin-right: 15px;">
    <h1 id="unified-namaste-who-icd-search">Unified Terminology Search & Mapper</h1>
</div>
""", unsafe_allow_html=True)

# --------------------
# Helper Functions
# --------------------
@st.cache_data
def load_all_data():
    """
    Loads all terminology CSVs into a dictionary of DataFrames.
    """
    data = {"Ayurveda": None, "Unani": None, "Siddha": None}
    base_url = "https://raw.githubusercontent.com/SanyamBinayake/SIH-Demo-/main/"
    
    for system in data.keys():
        try:
            data[system] = pd.read_csv(base_url + f"{system}_Codes_Terms.csv")
        except Exception:
            data[system] = pd.DataFrame()
    return data

def show_with_load_more(results, section_key, source="namaste", page_size=5):
    """Displays results with a 'Load More' button."""
    if section_key not in st.session_state: st.session_state[section_key] = page_size
    visible_count = st.session_state[section_key]

    for row in results[:visible_count]:
        code = row.get("code") if source.startswith("icd") else row.get("Code", "N/A")
        term = row.get("term") if source.startswith("icd") else row.get("Term", "N/A")
        
        with st.expander(f"`{code}` - {term}"):
            if source.startswith("icd"):
                 st.markdown(f"**Definition:** {row.get('definition', 'N/A')}")
            else: # NAMASTE
                st.markdown(f"**Explanation:** {row.get('Explanation', 'N/A')}")

    if len(results) > visible_count:
        st.write(f"Showing {visible_count} of {len(results)}.")
        if st.button("Load More", key=f"load_more_{section_key}"):
            st.session_state[section_key] += page_size
            st.rerun()
            
def handle_api_request(endpoint, query):
    try:
        response = requests.get(f"{BACKEND_URL}{endpoint}", params={"q": query}, timeout=20)
        response.raise_for_status()
        return response.json().get("results", [])
    except requests.exceptions.RequestException as e:
        st.error(f"API Error: {e}")
        return []

# --------------------
# Main Application Logic
# --------------------
all_data = load_all_data()

for system, df in all_data.items():
    if df.empty:
        st.error(f"Failed to load {system}_Codes_Terms.csv from GitHub. Please check the file path and repository.")

# --- NEW: Reorganized Main Tabs ---
search_tab, map_tab, bundle_tab = st.tabs(["⚕️ Terminology Search", " NAMASTE <-> ICD-11 Mapper", "🧾 Save Bundle"])

with search_tab:
    query = st.text_input("🔍 Search all terminologies", help="Try 'Jwara', 'Fever', or 'Vertigo'")
    
    if 'current_query' not in st.session_state or st.session_state.current_query != query:
        st.session_state.current_query = query
        for key in ["ayurveda", "unani", "siddha", "icd_bio", "icd_tm2"]:
            if key in st.session_state: del st.session_state[key]
    
    if query:
        # --- NEW: Nested Tabs for NAMASTE and ICD ---
        namaste_search_tab, icd_search_tab = st.tabs(["NAMASTE Terminologies", "WHO ICD-11 Terminologies"])

        with namaste_search_tab:
            ayur_tab, unani_tab, siddha_tab = st.tabs(["Ayurveda", "Unani", "Siddha"])
            
            for system, tab in [("Ayurveda", ayur_tab), ("Unani", unani_tab), ("Siddha", siddha_tab)]:
                with tab:
                    df = all_data[system]
                    if not df.empty:
                        mask = df.apply(lambda row: any(query.lower() in str(cell).lower() for cell in row), axis=1)
                        results = df[mask].to_dict("records")
                        st.write(f"Found {len(results)} matches.")
                        if results: show_with_load_more(results, system.lower(), "namaste")
                    else:
                        st.warning(f"{system} data is not available.")
        
        with icd_search_tab:
            bio_tab, tm2_tab = st.tabs(["Biomedicine", "TM2"])

            with bio_tab:
                results = handle_api_request("/search", query)
                st.write(f"Found {len(results)} matches.")
                if results: show_with_load_more(results, "icd_bio", "icd")
            with tm2_tab:
                results = handle_api_request("/search/tm2", query)
                st.write(f"Found {len(results)} matches.")
                if results: show_with_load_more(results, "icd_tm2", "icd")
    else:
        st.info("Type a diagnosis in the search box to begin.")

with map_tab:
    st.subheader("Concept Mapper: Find the best ICD-11 match for a NAMASTE code")
    st.info("Enter a NAMASTE code (e.g., AYU-AAA-1) to find the ICD-11 code with the most similar meaning based on its definition.")
    
    namaste_code_to_map = st.text_input("Enter NAMASTE Code")

    if st.button("Map Code"):
        if not namaste_code_to_map:
            st.warning("Please enter a NAMASTE code to map.")
        else:
            with st.spinner(f"Searching for the best match for `{namaste_code_to_map}`..."):
                try:
                    payload = {"code": namaste_code_to_map}
                    response = requests.post(f"{BACKEND_URL}/map-code", json=payload, timeout=30)
                    response.raise_for_status()
                    map_results = response.json()
                    
                    source = map_results.get("source_details")
                    matches = map_results.get("mapped_details")

                    st.success("Mapping complete!")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown(
                            f"""
                            <div class="mapper-card">
                                <h3>Source: NAMASTE ({source.get('system')})</h3>
                                <p><strong>Code:</strong> <code>{source.get('code')}</code></p>
                                <p><strong>Term:</strong> {source.get('term')}</p>
                                <p><strong>Definition:</strong> {source.get('definition')}</p>
                            </div>
                            """, unsafe_allow_html=True
                        )
                    with col2:
                        st.markdown(
                            f"""
                            <div class="mapper-card">
                                <h3>Best ICD-11 Match</h3>
                                {"<p>No suitable match found in ICD-11.</p>" if not matches else ""}
                            </div>
                            """, unsafe_allow_html=True
                        )
                        if matches:
                            for match in matches:
                                with st.container(border=True):
                                     st.markdown(f"<strong>Code:</strong> <code>{match.get('code')}</code>", unsafe_allow_html=True)
                                     st.markdown(f"<strong>Term:</strong> {match.get('term')}", unsafe_allow_html=True)
                                     st.markdown(f"<strong>Definition:</strong> {match.get('definition')}", unsafe_allow_html=True)

                except requests.exceptions.RequestException as e:
                    st.error(f"Mapping failed. Could not connect to the backend: {e}")

with bundle_tab:
    st.subheader("🧾 Demo: Save Condition to FHIR Bundle")
    namaste_code = st.text_input("Enter NAMASTE code (e.g., AYU-AAA-1)", key="bundle_namaste_code")
    patient_id = st.text_input("Enter Patient ID", "Patient/001", key="bundle_patient_id")
    if st.button("Save Condition Bundle"):
        if not namaste_code: st.warning("Please enter a NAMASTE code.")
        else:
            with st.spinner("Saving bundle..."):
                bundle = {"resourceType": "Bundle", "type": "collection", "entry": [{"resource": {"resourceType": "Condition", "code": {"coding": [{"system": "https://demo.sih/fhir/CodeSystem/namaste", "code": namaste_code, "display": "NAMASTE term"}]}, "subject": {"reference": patient_id}}}]}
                try:
                    resp = requests.post(f"{BACKEND_URL}/fhir/Bundle", json=bundle, timeout=30)
                    if resp.status_code == 201:
                        st.success("✅ Condition stored with dual coding!")
                        st.json(resp.json())
                    else:
                        st.error(f"❌ Failed to save. Server responded with status {resp.status_code}:")
                        st.json(resp.json())
                except requests.exceptions.RequestException as e:
                    st.error(f"❌ Error connecting to the backend: {e}")

