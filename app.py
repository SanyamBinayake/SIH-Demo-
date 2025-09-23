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
    df = pd.read_csv("Merged_CSV_3.csv")
    def clean_html(text):
        text = str(text)
        text = re.sub(r'<em>(.*?)</em>', r'*\1*', text)
        text = re.sub(r'<[^>]+>', '', text)
        return text
    for col in ["Short_definition", "Long_definition", "Term", "RegionalTerm"]:
        df[col] = df[col].apply(clean_html)
    return df

def show_with_load_more(results, section_key, page_size=5, source="namaste"):
    if section_key not in st.session_state:
        st.session_state[section_key] = page_size
    visible_count = st.session_state[section_key]

    for row in results[:visible_count]:
        if source.startswith("icd"):
            code = row.get("code", "N/A")
            term = row.get("term", "N/A")
            with st.expander(f"{code} - {term}"):
                st.markdown(f"**Code:** `{code}`")
                st.markdown(f"**Term:** {term}")
        else:
            with st.expander(f"{row['Code']} - {row['Term']}"):
                st.markdown(f"**Regional Term:** {row['RegionalTerm']}")

    if visible_count < len(results):
        if st.button("Load More", key=f"loadmore_{section_key}"):
            st.session_state[section_key] += page_size
            st.rerun()
            
# --------------------
# Streamlit UI
# --------------------
st.title("🌿 Unified NAMASTE + WHO ICD Search")
df = load_data()
query = st.text_input("🔍 Search for a diagnosis (e.g., Jwara, Fever)")

if query:
    query_lower = query.lower()
    tab_namaste, tab_icd_bio, tab_icd_tm2, tab_combined = st.tabs([
        "📘 NAMASTE", "🌍 WHO ICD-11 (Biomedicine)", "🌏 WHO ICD-11 (TM2)", "⚡ Combined Autocomplete"
    ])

    with tab_namaste:
        results = df[df.apply(lambda row: any(query_lower in str(cell).lower() for cell in row), axis=1)].to_dict("records")
        st.write(f"Found {len(results)} matches.")
        if results: show_with_load_more(results, "namaste", source="namaste")

    with tab_icd_bio:
        try:
            r = requests.get(f"{BACKEND_URL}/search", params={"q": query})
            results = r.json().get("results", [])
            st.write(f"Found {len(results)} matches.")
            if results: show_with_load_more(results, "icd-bio", source="icd")
        except Exception as e: st.error(f"API Error: {e}")

    with tab_icd_tm2:
        try:
            r = requests.get(f"{BACKEND_URL}/search/tm2", params={"q": query})
            results = r.json().get("results", [])
            st.write(f"Found {len(results)} matches.")
            if results: show_with_load_more(results, "icd-tm2", source="icd-tm2")
        except Exception as e: st.error(f"API Error: {e}")

    with tab_combined:
        try:
            r = requests.get(f"{BACKEND_URL}/autocomplete", params={"q": query})
            results = r.json().get("results", [])
            st.write(f"Found {len(results)} matches.")
            for row in results:
                st.markdown(f"**{row['source']}**: `{row['code']}` - {row['display']}")
        except Exception as e: st.error(f"API Error: {e}")

st.markdown("---")
st.subheader("🧾 Demo: Save Condition to FHIR Bundle")
namaste_code = st.text_input("Enter NAMASTE code (e.g., NAM0001)")
patient_id = st.text_input("Enter Patient ID", "Patient/001")

if st.button("Save Condition Bundle"):
    bundle = {"resourceType": "Bundle", "type": "collection", "entry": [{"resource": {"resourceType": "Condition", "code": {"coding": [{"system": "https://demo.sih/fhir/CodeSystem/namaste", "code": namaste_code}]}, "subject": {"reference": patient_id}}}]}
    try:
        resp = requests.post(f"{BACKEND_URL}/fhir/Bundle", json=bundle)
        if resp.status_code == 201:
            st.success("✅ Condition stored!")
            st.json(resp.json())
        else:
            st.error(f"❌ Failed: {resp.text}")
    except Exception as e:
        st.error(f"❌ Error: {e}")

