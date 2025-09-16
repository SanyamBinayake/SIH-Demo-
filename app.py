import streamlit as st
import pandas as pd

# Load CSV
@st.cache_data
def load_data():
    df = pd.read_csv("Merged_CSV_3.csv")
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
        st.markdown(f"**Short Definition:** {row['Short_definition']}")
        st.markdown(f"**Long Definition:** {row['Long_definition']}")
