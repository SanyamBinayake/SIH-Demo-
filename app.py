import streamlit as st
import pandas as pd
import re
import requests

# Set your backend URL here
BACKEND_URL = "https://sih-demo-4z5c.onrender.com"

# --------------------
# Helper Functions
# --------------------
@st.cache_data
def load_data():
    try:
        df = pd.read_csv("Merged_CSV_3.csv")
        def clean_html(text):
            text = str(text)
            text = re.sub(r'<em>(.*?)</em>', r'*\1*', text)
            text = re.sub(r'<[^>]+>', '', text)
            return text
        # Ensure all expected columns exist before cleaning
        for col in ["Short_definition", "Long_definition", "Term", "RegionalTerm"]:
            if col in df.columns:
                df[col] = df[col].apply(clean_html)
        return df
    except FileNotFoundError:
        st.error("FATAL: Merged_CSV_3.csv not found. Make sure it's in your GitHub repository.")
        return pd.DataFrame()

def show_with_load_more(results, section_key, page_size=5, source="namaste"):
    if section_key not in st.session_state:
        st.session_state[section_key] = page_size
    visible_count = st.session_state.get(section_key, page_size)

    for row in results[:visible_count]:
        if source.startswith("icd"): # ICD WHO results
            code = row.get("code", "N/A")
            term = row.get("term", "N/A")
            # --- THIS SECTION IS NOW UPDATED ---
            definition = row.get("definition", "No definition available.")
            with st.expander(f"`{code}` - {term}"):
                st.markdown(f"**Source:** {source.upper()}")
                st.markdown(f"**Definition:** {definition}")
            # --- END OF UPDATE ---

        else: # NAMASTE rows
            with st.expander(f"{row.get('Code', 'N/A')} - {row.get('Term', 'N/A')}"):
                st.markdown(f"**Regional Term:** {row.get('RegionalTerm', 'N/A')}")
                st.markdown(f"**Short Definition:** {row.get('Short_definition', 'N/A')}")
                st.markdown(f"**Long Definition:** {row.get('Long_definition', 'N/A')}")

def handle_api_request(endpoint, query):
    try:
        response = requests.get(f"{BACKEND_URL}{endpoint}", params={"q": query}, timeout=20)
        response.raise_for_status()
        return response.json().get("results", [])
    except requests.exceptions.RequestException as e:
        st.error(f"Failed to connect to the backend API. Please ensure the server is running. Error: {e}")
        return []
    except Exception as e:
        st.error(f"An unexpected error occurred: {e}")
        return []

# --------------------
# Streamlit UI
# --------------------
st.title("🌿 Unified NAMASTE + WHO ICD Search")

df = load_data()
query = st.text_input("🔍 Search for a diagnosis (term, code, or definition)", help="Try searching for 'Jwara', 'Fever', or 'Vertigo'")

if query:
    query_lower = query.lower()
    
    tab1, tab2, tab3, tab4 = st.tabs([
        "📘 NAMASTE",
        "🌍 WHO ICD-11 (Biomedicine)",
        "🌏 WHO ICD-11 (TM2)",
        "⚡ Combined Autocomplete"
    ])

    with tab1:
        with st.spinner("Searching NAMASTE data..."):
            namaste_results = []
            if not df.empty:
                mask = df.apply(lambda row: any(query_lower in str(cell).lower() for cell in row), axis=1)
                namaste_results = df[mask].to_dict("records")
            
            st.write(f"Found {len(namaste_results)} matches.")
            if namaste_results:
                show_with_load_more(namaste_results, section_key="namaste", source="namaste")
            else:
                st.info("No matches found in the local NAMASTE dataset.")

    with tab2:
        with st.spinner("Fetching Biomedicine results..."):
            results = handle_api_request("/search", query)
            st.write(f"Found {len(results)} matches.")
            if results:
                show_with_load_more(results, section_key="icd_bio", source="icd-biomedicine")
            else:
                st.info("No results returned from the WHO ICD-11 Biomedicine API.")

    with tab3:
        with st.spinner("Fetching TM2 results..."):
            results = handle_api_request("/search/tm2", query)
            st.write(f"Found {len(results)} matches.")
            if results:
                show_with_load_more(results, section_key="icd_tm2", source="icd-tm2")
            else:
                st.info("No results returned from the WHO ICD-11 TM2 API.")

    with tab4:
        with st.spinner("Fetching combined results..."):
            try:
                response = requests.get(f"{BACKEND_URL}/autocomplete", params={"q": query}, timeout=20)
                response.raise_for_status()
                data = response.json().get("results", [])
                st.write(f"Found {len(data)} matches.")
                if data:
                    for row in data:
                        with st.expander(f"**{row.get('source', 'N/A')}** | `{row.get('code', 'N/A')}` - {row.get('display', 'N/A')}"):
                            st.markdown(f"**System:** `{row.get('system', 'N/A')}`")
                else:
                    st.info("No results found.")
            except requests.exceptions.RequestException as e:
                st.error(f"Failed to connect to autocomplete API: {e}")

else:
    st.info("Type a diagnosis in the search box above to begin.")

# --------------------
# Bundle Save Section
# --------------------
st.markdown("---")
st.subheader("🧾 Demo: Save Condition to FHIR Bundle")

namaste_code = st.text_input("Enter NAMASTE code (e.g., NAM0001)")
patient_id = st.text_input("Enter Patient ID", "Patient/001")

if st.button("Save Condition Bundle"):
    if not namaste_code:
        st.warning("Please enter a NAMASTE code.")
    else:
        with st.spinner("Saving bundle..."):
            bundle = {
                "resourceType": "Bundle", "type": "collection",
                "entry": [{
                    "resource": {
                        "resourceType": "Condition",
                        "code": { "coding": [{
                            "system": "https://demo.sih/fhir/CodeSystem/namaste",
                            "code": namaste_code,
                            "display": "NAMASTE term (to be translated)"
                        }]},
                        "subject": {"reference": patient_id}
                    }
                }]
            }
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

