import streamlit as st
import pandas as pd
import re
import requests
import os
from dotenv import load_dotenv

# --------------------
# Load environment variables
# --------------------
load_dotenv()
CLIENT_ID = os.getenv("WHO_CLIENT_ID")
CLIENT_SECRET = os.getenv("WHO_CLIENT_SECRET")

TOKEN_URL = "https://icdaccessmanagement.who.int/connect/token"
ICD_API_URL = "https://id.who.int/icd/release/11/2024/search"

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


def get_access_token():
    """Fetch OAuth2 access token from WHO API"""
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "scope": "icdapi_access",
        "grant_type": "client_credentials"
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    response = requests.post(TOKEN_URL, data=data, headers=headers)
    response.raise_for_status()
    return response.json()["access_token"]


def search_icd(query, token, chapter=None):
    """Search ICD-11 for query"""
    headers = {"Authorization": f"Bearer {token}"}
    params = {"q": query}
    if chapter:
        params["chapter"] = chapter
    response = requests.get(ICD_API_URL, headers=headers, params=params)
    response.raise_for_status()
    return response.json()


# --------------------
# Streamlit UI
# --------------------
st.title("🌿 NAMASTE + WHO ICD-11 Search")

df = load_data()
query = st.text_input("🔍 Search for a diagnosis (term, code, or definition)")

if query:
    # NAMASTE Search
    query_lower = query.lower()
    namaste_results = df[
        df.apply(lambda row: query_lower in str(row['Code']).lower()
                 or query_lower in str(row['Term']).lower()
                 or query_lower in str(row['RegionalTerm']).lower()
                 or query_lower in str(row['Short_definition']).lower()
                 or query_lower in str(row['Long_definition']).lower(),
                 axis=1)
    ]

    # ICD Search
    try:
        token = get_access_token()
        icd_results = search_icd(query, token)
        icd_entities = icd_results.get("destinationEntities", [])
    except Exception as e:
        st.error(f"WHO ICD API Error: {e}")
        icd_entities = []

    # Display Results
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📘 NAMASTE Terminology")
        st.write(f"Found {len(namaste_results)} matches")
        for _, row in namaste_results.iterrows():
            with st.expander(f"{row['Code']} - {row['Term']}"):
                st.markdown(f"**Regional Term:** {row['RegionalTerm']}")
                st.markdown(f"**Short Definition:** {row['Short_definition']}")
                st.markdown(f"**Long Definition:** {row['Long_definition']}")

    with col2:
        st.subheader("🌍 WHO ICD-11 (TM2 + Biomedicine)")
        st.write(f"Found {len(icd_entities)} matches")
        for entity in icd_entities:
            title = entity.get("title", {}).get("@value", "N/A")
            code = entity.get("theCode", "N/A")
            uri = entity.get("@id", "")
            with st.expander(f"{code} - {title}"):
                st.markdown(f"**Code:** {code}")
                st.markdown(f"**Title:** {title}")
                st.markdown(f"[View in ICD Browser]({uri})")
else:
    st.info("Type a diagnosis in the search box above 👆")
