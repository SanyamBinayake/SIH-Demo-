import streamlit as st
import pandas as pd
import re

# Load CSV
@st.cache_data
def load_data():
    df = pd.read_csv("Merged_CSV_3.csv")

    # Clean HTML tags but keep italicized words by converting <em>...</em> → *...*
    def clean_html(text):
        text = str(text)
        # Replace <em>...</em> with *...* (markdown italics)
        text = re.sub(r'<em>(.*?)</em>', r'*\1*', text)
        # Remove any other stray tags
        text = re.sub(r'<[^>]+>', '', text)
        return text

    df['Short_definition'] = df['Short_definition'].apply(clean_html)
    df['Long_definition'] = df['Long_definition'].apply(clean_html)
    df['Term'] = df['Term'].apply(clean_html)
    df['RegionalTerm'] = df['RegionalTerm'].apply(clean_html)

    return df

df = load_data()

st.title("NAMASTE Terminology Search 🔍")

# Search box
query = st.text_input("Search by Code, Term, Regional Term, Short/Long Definition")

if query:
    query_lower = query.lower()
    results = df[
        df.apply(lambda row: query_lower in str(row['Code']).lower()
                 or query_lower in str(row['Term']).lower()
                 or query_lower in str(row['RegionalTerm']).lower()
                 or query_lower in str(row['Short_definition']).lower()
                 or query_lower in str(row['Long_definition']).lower(),
                 axis=1)
    ]
else:
    results = df.head(20)  # show first 20 by default

st.write(f"Showing {len(results)} results")

# Display results in expandable format
for _, row in results.iterrows():
    with st.expander(f"{row['Code']} - {row['Term']}"):
        st.markdown(f"**Regional Term:** {row['RegionalTerm']}")
        st.markdown(f"**Short Definition:** {row['Short_definition']}", unsafe_allow_html=True)
        st.markdown(f"**Long Definition:** {row['Long_definition']}", unsafe_allow_html=True)
