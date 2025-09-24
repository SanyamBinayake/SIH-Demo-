import streamlit as st
import pandas as pd
import re
import requests

# Set your backend URL here
BACKEND_URL = "https://sih-demo-4z5c.onrender.com"

# --------------------
# UI Customization Section
# --------------------
# 1. Inject custom CSS with st.markdown to change font sizes
st.markdown("""
<style>
/* Target the title header */
h1#unified-namaste-who-icd-search {
    font-size: 26px; /* Make the title font smaller */
    font-weight: 600;
    line-height: 1.2;
}
/* Target the input box label */
div[data-testid="stTextInput"] label {
    font-size: 18px !important; /* Make the input label larger */
    font-weight: 500;
}
</style>
""", unsafe_allow_html=True)

# 2. Create a custom header with your logo and the new title
# --- This now contains the correct, permanent "raw" URL for your logo ---
LOGO_URL = "https://raw.githubusercontent.com/SanyamBinayake/SIH-Demo-/3c131c7e8b87c00be561ae349a84bf7654acd7ad/mediunify_logo_1_-removebg-preview.png"

st.markdown(f"""
<div style="display: flex; align-items: center; margin-bottom: 20px;">
    <img src="{LOGO_URL}" alt="Logo" style="height: 50px; margin-right: 15px;">
    <h1 id="unified-namaste-who-icd-search">Unified NAMASTE + WHO ICD Search</h1>
</div>
""", unsafe_allow_html=True)

# The original st.title() is now removed and replaced by the custom header above.

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

def show_with_load_more(results, section_key, source="namaste", page_size=15):
    """
    Displays a list of results with a "Load More" button for pagination.
    """
    if section_key not in st.session_state:
        st.session_state[section_key] = page_size

    visible_count = st.session_state[section_key]

    for row in results[:visible_count]:
        if source.startswith("icd"): # ICD WHO results
            code = row.get("code", "N/A")
            term = row.get("term", "N/A")
            definition = row.get("definition", "No definition available.")
            with st.expander(f"`{code}` - {term}"):
                st.markdown(f"**Source:** {source.upper()}")
                st.markdown(f"**Definition:** {definition}")
        else: # NAMASTE rows
            with st.expander(f"{row.get('Code', 'N/A')} - {row.get('Term', 'N/A')}"):
                st.markdown(f"**Regional Term:** {row.get('RegionalTerm', 'N/A')}")
                st.markdown(f"**Short Definition:** {row.get('Short_definition', 'N/A')}")
                st.markdown(f"**Long Definition:** {row.get('Long_definition', 'N/A')}")

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
df = load_data()
query = st.text_input("Search for a diagnosis (term, code, or definition)", help="Try 'Jwara', 'Fever', or 'Vertigo'")

# Reset pagination if the search query changes
if 'current_query' not in st.session_state or st.session_state.current_query != query:
    st.session_state.current_query = query
    for key in ["namaste", "icd_bio", "icd_tm2"]:
        if key in st.session_state:
            del st.session_state[key]

if query:
    query_lower = query.lower()
    
    tab1, tab2, tab3, tab4 = st.tabs([
        "📘 NAMASTE", "🌍 WHO ICD-11 (Biomedicine)", "🌏 WHO ICD-11 (TM2)", "⚡ Combined Autocomplete"
    ])

    with tab1:
        with st.spinner("Searching NAMASTE data..."):
            namaste_results = []
            if not df.empty:
                mask = df.apply(lambda row: any(query_lower in str(cell).lower() for cell in row), axis=1)
                namaste_results = df[mask].to_dict("records")
            st.write(f"Found {len(namaste_results)} total matches.")
            if namaste_results: 
                show_with_load_more(namaste_results, section_key="namaste", source="namaste")

    with tab2:
        with st.spinner("Fetching Biomedicine results..."):
            results = handle_api_request("/search", query)
            st.write(f"Found {len(results)} total matches.")
            if results: 
                show_with_load_more(results, section_key="icd_bio", source="icd-biomedicine")

    with tab3:
        with st.spinner("Fetching TM2 results..."):
            results = handle_api_request("/search/tm2", query)
            st.write(f"Found {len(results)} total matches.")
            if results: 
                show_with_load_more(results, section_key="icd_tm2", source="icd-tm2")

    with tab4:
        with st.spinner("Fetching combined results..."):
            try:
                response = requests.get(f"{BACKEND_URL}/autocomplete", params={"q": query}, timeout=20)
                response.raise_for_status()
                all_results = response.json().get("results", [])
                st.info("This tab shows a combined list of results from all available sources. Use the filter to narrow your view.")
                filter_option = st.selectbox("Filter results by source:", ("All", "NAMASTE", "ICD-11", "ICD-11 (TM2)"))
                if all_results:
                    filtered_data = []
                    if filter_option == "All":
                        filtered_data = all_results
                    else:
                        for row in all_results:
                            if row.get('source') == filter_option:
                                filtered_data.append(row)
                    st.write(f"Displaying {len(filtered_data)} of {len(all_results)} total matches.")
                    if not filtered_data:
                        st.warning(f"No results found for the source '{filter_option}' in this search.")
                    else:
                        for row in filtered_data:
                            with st.expander(f"**{row.get('source', 'N/A')}** | `{row.get('code', 'N/A')}` - {row.get('display', 'N/A')}"):
                                st.markdown(f"**System:** `{row.get('system', 'N/A')}`")
                else:
                    st.info("No results found for this query.")
            except requests.exceptions.RequestException as e:
                st.error(f"Failed to connect to autocomplete API: {e}")
else:
    st.info("Type a diagnosis in the search box to begin.")

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

