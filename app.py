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


# --------------------
# Pagination (Load More style)
# --------------------
def show_with_load_more(results, section_key, page_size=5, source="namaste"):
    """Display results with Load More button"""
    if section_key not in st.session_state:
        st.session_state[section_key] = page_size

    visible_count = st.session_state[section_key]
    total = len(results)

    for row in results[:visible_count]:
        if source == "icd":  # ICD WHO results from Flask
            code = row.get("code", "N/A")
            term = row.get("term", "N/A")
            definition = row.get("definition", "No definition available")

            with st.expander(f"{code} - {term}"):
                st.markdown(f"**Code:** {code}")
                st.markdown(f"**Term:** {term}")
                st.markdown(f"**Definition:** {definition}")

        else:  # NAMASTE dataframe rows
            with st.expander(f"{row['Code']} - {row['Term']}"):
                st.markdown(f"**Regional Term:** {row['RegionalTerm']}")
                st.markdown(f"**Short Definition:** {row['Short_definition']}")
                st.markdown(f"**Long Definition:** {row['Long_definition']}")

    if visible_count < total:
        if st.button("Load More", key=f"loadmore_{section_key}"):
            st.session_state[section_key] += page_size
            st.rerun()  # ✅ Streamlit 1.25+


# --------------------
# Streamlit UI
# --------------------
st.title("🌿 Unified NAMASTE + WHO ICD Search")

df = load_data()
query = st.text_input("🔍 Search for a diagnosis (term, code, or definition)")

if query:
    query_lower = query.lower()

    # Tabs for NAMASTE and ICD
    tab1, tab2 = st.tabs(["📘 NAMASTE Terminology", "🌍 WHO ICD-11 Terminology"])

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
            show_with_load_more(
                namaste_results.to_dict("records"),
                section_key="namaste",
                source="namaste"
            )
        else:
            st.warning("No matches found in NAMASTE dataset.")

    # --------------------
    # WHO ICD Tab
    # --------------------
    with tab2:
        with st.spinner("Fetching ICD results..."):
            try:
                r = requests.get(f"http://127.0.0.1:5000/search?q={query}")
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
                st.error(f"❌ Failed to connect to WHO API backend: {e}")

else:
    st.info("Type a diagnosis in the search box above 👆")
