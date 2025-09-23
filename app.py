import streamlit as st
import pandas as pd
import re
import requests

# --------------------
# Helper Functions
# --------------------
@st.cache_data
def load_data():
    df = pd.read_csv("Merged_CSV_3.csv")

    def clean_html(text):
        text = str(text)
        text = re.sub(r'<em>(.*?)</em>', r'*\1*', text)  # italic text
        text = re.sub(r'<[^>]+>', '', text)  # remove other HTML tags
        return text

    for col in ["Short_definition", "Long_definition", "Term", "RegionalTerm"]:
        df[col] = df[col].apply(clean_html)

    return df


def show_with_load_more(results, section_key, page_size=5, source="namaste"):
    """Display results with Load More button"""
    if section_key not in st.session_state:
        st.session_state[section_key] = page_size

    visible_count = st.session_state[section_key]
    total = len(results)

    for row in results[:visible_count]:
        if source == "icd":  # ICD WHO results
            code = row.get("code", "N/A")
            term = row.get("term", "N/A")
            definition = row.get("definition", "No definition available")

            with st.expander(f"{code} - {term}"):
                st.markdown(f"**Code:** {code}")
                st.markdown(f"**Term:** {term}")
                st.markdown(f"**Definition:** {definition}")

        else:  # NAMASTE rows
            with st.expander(f"{row['Code']} - {row['Term']}"):
                st.markdown(f"**Regional Term:** {row['RegionalTerm']}")
                st.markdown(f"**Short Definition:** {row['Short_definition']}")
                st.markdown(f"**Long Definition:** {row['Long_definition']}")

                # 🔹 New: Translate NAMASTE → ICD
                if st.button(f"Translate {row['Code']} to ICD", key=row["Code"]):
                    try:
                        r = requests.post(
                            "https://sih-demo-4z5c.onrender.com/fhir/ConceptMap/$translate",
                            json={"code": row["Code"]}
                        )
                        if r.status_code == 200:
                            st.json(r.json())
                        else:
                            st.error("❌ Translation failed")
                    except Exception as e:
                        st.error(f"Error: {e}")

    if visible_count < total:
        if st.button("Load More", key=f"loadmore_{section_key}"):
            st.session_state[section_key] += page_size
            st.rerun()


# --------------------
# Streamlit UI
# --------------------
st.title("🌿 Unified NAMASTE + WHO ICD Search")

df = load_data()
query = st.text_input("🔍 Search for a diagnosis (term, code, or definition)")

if query:
    query_lower = query.lower()
    tab1, tab2, tab3 = st.tabs(["📘 NAMASTE Terminology", "🌍 WHO ICD-11", "⚡ Combined Autocomplete"])

    # --------------------
    # NAMASTE Tab
    # --------------------
    with tab1:
        namaste_results = df[
            df.apply(lambda row: query_lower in str(row['Code']).lower()
                     or query_lower in str(row['Term']).lower()
                     or query_lower in str(row['RegionalTerm']).lower()
                     or query_lower in str(row['Short_definition']).lower()
                     or query_lower in str(row['Long_definition']).lower(),
                     axis=1)
        ]
        st.write(f"Found {len(namaste_results)} matches")
        if len(namaste_results) > 0:
            show_with_load_more(namaste_results.to_dict("records"), section_key="namaste", source="namaste")
        else:
            st.warning("No matches found in NAMASTE dataset.")

    # --------------------
    # WHO ICD Tab
    # --------------------
    with tab2:
        with st.spinner("Fetching ICD results..."):
            try:
                r = requests.get(f"https://sih-demo-4z5c.onrender.com/search?q={query}")
                if r.status_code == 200:
                    data = r.json()
                    icd_results = data.get("results", [])
                    st.write(f"Found {len(icd_results)} results from WHO ICD API")

                    if len(icd_results) > 0:
                        show_with_load_more(icd_results, section_key="icd", source="icd")
                    else:
                        st.warning("No results returned from WHO ICD API.")
                else:
                    st.error(f"Error from WHO API: {r.text}")
            except Exception as e:
                st.error(f"❌ Failed to connect WHO API: {e}")

    # --------------------
    # Combined Autocomplete Tab
    # --------------------
    with tab3:
        with st.spinner("Fetching combined autocomplete..."):
            try:
                r = requests.get(f"https://sih-demo-4z5c.onrender.com/autocomplete?q={query}")
                if r.status_code == 200:
                    data = r.json()
                    results = data.get("results", [])
                    st.write(f"Found {len(results)} results (NAMASTE + ICD)")
                    for row in results:
                        with st.expander(f"{row['source']} | {row['code']} - {row['display']}"):
                            st.markdown(f"**System:** {row['system']}")
                            st.markdown(f"**Code:** {row['code']}")
                            st.markdown(f"**Term:** {row['display']}")
                            st.markdown(f"**Source:** {row['source']}")
                else:
                    st.error(f"Error: {r.text}")
            except Exception as e:
                st.error(f"❌ Failed to connect autocomplete: {e}")

else:
    st.info("Type a diagnosis in the search box above 👆")

# --------------------
# Bundle Save Section
# --------------------
st.markdown("---")
st.subheader("🧾 Demo: Save Condition to FHIR Bundle")

namaste_code = st.text_input("Enter NAMASTE code (e.g., NAM0001)")
patient_id = st.text_input("Enter Patient ID", "Patient/001")

if st.button("Save Condition Bundle"):
    bundle = {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [
            {
                "resource": {
                    "resourceType": "Condition",
                    "id": "cond-demo",
                    "code": {
                        "coding": [
                            {
                                "system": "https://demo.sih/fhir/CodeSystem/namaste",
                                "code": namaste_code,
                                "display": f"NAMASTE term for {namaste_code}"
                            }
                        ]
                    },
                    "subject": {"reference": patient_id}
                }
            }
        ]
    }

    try:
        resp = requests.post("https://sih-demo-4z5c.onrender.com/fhir/Bundle", json=bundle)
        if resp.status_code == 201:
            st.success("✅ Condition stored with dual coding")
            st.json(resp.json())
        else:
            st.error(f"❌ Failed: {resp.text}")
    except Exception as e:
        st.error(f"❌ Error: {e}")
