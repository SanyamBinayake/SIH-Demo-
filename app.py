import streamlit as st
import pandas as pd
import requests
import re

# Set your backend URL here
BACKEND_URL = "https://sih-demo-4z5c.onrender.com"

# --------------------
# UI Customization Section
# --------------------
st.set_page_config(layout="wide")

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
    background-color: #F0F2F6;
    color: #31333F;
    padding: 20px;
    border-radius: 10px;
    border: 1px solid #D3D3D3;
    height: 100%;
    overflow-y: auto;
    max-height: 600px;
}
.mapper-card h3 {
    margin-top: 0;
    color: #00A9E0;
}
.mapper-card code {
    background-color: #E6E6E6;
    color: #31333F;
    padding: 2px 4px;
    border-radius: 3px;
}
.match-container {
    background-color: #FFFFFF;
    border: 1px solid #D3D3D3;
    border-radius: 8px;
    padding: 15px;
    margin-bottom: 10px;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}
.confidence-badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 12px;
    font-size: 12px;
    font-weight: bold;
}
.confidence-high { background-color: #d4edda; color: #155724; }
.confidence-medium { background-color: #fff3cd; color: #856404; }
.confidence-low { background-color: #f8d7da; color: #721c24; }
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
    data = {"Ayurveda": None, "Unani": None, "Siddha": None}
    base_url = "https://raw.githubusercontent.com/SanyamBinayake/SIH-Demo-/main/"
    for system in data.keys():
        try:
            data[system] = pd.read_csv(base_url + f"{system}_Codes_Terms.csv")
        except Exception:
            data[system] = pd.DataFrame()
    return data

def show_with_load_more(results, section_key, source="namaste", page_size=5):
    if section_key not in st.session_state: st.session_state[section_key] = page_size
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

def get_confidence_class(confidence_str):
    """Determine CSS class based on confidence score."""
    try:
        confidence = float(confidence_str)
        if confidence >= 0.7:
            return "confidence-high"
        elif confidence >= 0.4:
            return "confidence-medium"
        else:
            return "confidence-low"
    except (ValueError, TypeError):
        return "confidence-low"

def format_confidence_label(confidence_str):
    """Format confidence score for display."""
    try:
        confidence = float(confidence_str)
        return f"{confidence:.1%}"
    except (ValueError, TypeError):
        return "Unknown"

# --------------------
# Main Application Logic
# --------------------
all_data = load_all_data()

for system, df in all_data.items():
    if df.empty:
        st.error(f"Failed to load {system}_Codes_Terms.csv from GitHub.")

search_tab, map_tab, bundle_tab = st.tabs([
    "⚕️ Terminology Search", 
    "🔗 NAMASTE <-> ICD-11 Mapper", 
    "🧾 Save Bundle"
])

with search_tab:
    query = st.text_input("🔍 Search all terminologies", help="Try 'Jwara', 'Fever', 'Vertigo'")
    
    if 'current_query' not in st.session_state or st.session_state.current_query != query:
        st.session_state.current_query = query
        for key in ["ayurveda", "unani", "siddha", "icd_bio", "icd_tm2"]:
            if key in st.session_state: del st.session_state[key]
    
    if query:
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
    st.subheader("🔗 Dynamic Concept Mapper")
    st.info("Enter a NAMASTE code to find dynamically matched ICD-11 codes with confidence scores and mapping methods.")
    
    namaste_code_to_map = st.text_input("Enter NAMASTE Code", placeholder="e.g., DBC1.3, AYU-AAA-1, etc.")

    if st.button("🚀 Map Code", type="primary"):
        if not namaste_code_to_map:
            st.warning("Please enter a NAMASTE code to map.")
        else:
            with st.spinner(f"🧠 Performing dynamic mapping for `{namaste_code_to_map}`..."):
                try:
                    payload = {"code": namaste_code_to_map}
                    response = requests.post(f"{BACKEND_URL}/map-code", json=payload, timeout=30)
                    response.raise_for_status()
                    map_results = response.json()
                    
                    source = map_results.get("source_details")
                    matches = map_results.get("mapped_details", [])
                    mapping_success = map_results.get("mapping_success", False)

                    if mapping_success:
                        st.success(f"✅ Dynamic mapping completed! Found {len(matches)} potential matches.")
                    else:
                        st.warning("⚠️ Mapping completed but no high-confidence matches found.")
                    
                    # Display mapping statistics
                    col_stats1, col_stats2, col_stats3 = st.columns(3)
                    with col_stats1:
                        st.metric("Total Candidates", map_results.get("total_candidates_found", 0))
                    with col_stats2:
                        st.metric("High Confidence", len([m for m in matches if float(m.get('confidence', '0')) > 0.5]))
                    with col_stats3:
                        strategies_used = map_results.get("mapping_strategies_used", 1)
                        st.metric("Strategies Used", strategies_used)
                    
                    # Main mapping results display
                    col1, col2 = st.columns([1, 1])
                    
                    # Source NAMASTE details
                    with col1:
                        st.markdown("### 📋 Source: NAMASTE")
                        
                        source_container = st.container()
                        with source_container:
                            st.markdown(f"""
                            <div style="background-color: #E8F4F8; padding: 20px; border-radius: 10px; border-left: 4px solid #00A9E0;">
                                <h4 style="color: #00A9E0; margin-top: 0;">NAMASTE ({source.get('system', 'Unknown')})</h4>
                                <p><strong>Code:</strong> <code style="background-color: #D1E7DD; padding: 2px 6px; border-radius: 3px;">{source.get('code', 'N/A')}</code></p>
                                <p><strong>Term:</strong> {source.get('term', 'N/A')}</p>
                                <p><strong>Definition:</strong></p>
                                <div style="background-color: white; padding: 10px; border-radius: 5px; margin-top: 5px; font-style: italic;">
                                    {source.get('definition', 'No definition available.')[:300]}{'...' if len(source.get('definition', '')) > 300 else ''}
                                </div>
                            </div>
                            """, unsafe_allow_html=True)
                    
                    # ICD-11 matches
                    with col2:
                        st.markdown("### 🎯 ICD-11 Matches")
                        
                        if not matches:
                            st.markdown("""
                            <div style="background-color: #FFF3CD; padding: 20px; border-radius: 10px; border-left: 4px solid #856404;">
                                <h4 style="color: #856404; margin-top: 0;">No Matches Found</h4>
                                <p>The dynamic mapping system could not find suitable ICD-11 matches for this NAMASTE code.</p>
                                <p><strong>Suggestions:</strong></p>
                                <ul>
                                    <li>Try searching manually in the Search tab</li>
                                    <li>Check if the NAMASTE code is correct</li>
                                    <li>The term might be too specific for current ICD-11 coverage</li>
                                </ul>
                            </div>
                            """, unsafe_allow_html=True)
                        else:
                            # Display each match in a clean format
                            for i, match in enumerate(matches, 1):
                                confidence_str = match.get('confidence', '0.000')
                                confidence_class = get_confidence_class(confidence_str)
                                confidence_label = format_confidence_label(confidence_str)
                                method = match.get('method', 'unknown').replace('_', ' ').title()
                                search_term = match.get('search_term', 'N/A')
                                
                                # Use Streamlit container for better layout control
                                with st.container():
                                    st.markdown(f"""
                                    <div style="background-color: white; padding: 15px; border-radius: 8px; border: 1px solid #dee2e6; margin-bottom: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                                            <h5 style="margin: 0; color: #495057;">Match #{i}</h5>
                                            <span class="{confidence_class}" style="padding: 2px 8px; border-radius: 12px; font-size: 12px; font-weight: bold;">{confidence_label}</span>
                                        </div>
                                        
                                        <p><strong>ICD-11 Code:</strong> <code style="background-color: #F8F9FA; padding: 2px 6px; border-radius: 3px; color: #495057;">{match.get('code', 'N/A')}</code></p>
                                        
                                        <p><strong>Term:</strong> {match.get('term', 'N/A')}</p>
                                        
                                        <p><strong>Definition:</strong></p>
                                        <div style="background-color: #F8F9FA; padding: 8px; border-radius: 4px; font-size: 14px; color: #6C757D;">
                                            {match.get('definition', 'No definition available.')[:200]}{'...' if len(match.get('definition', '')) > 200 else ''}
                                        </div>
                                        
                                        <div style="margin-top: 10px; font-size: 12px; color: #6C757D;">
                                            <strong>Method:</strong> {method} | <strong>Search Term:</strong> "{search_term}"
                                        </div>
                                    </div>
                                    """, unsafe_allow_html=True)

                except requests.exceptions.RequestException as e:
                    st.error(f"🔴 Mapping failed. Could not connect to the backend: {e}")
                    st.info("💡 Please check if the backend server is running and accessible.")
                except KeyError as e:
                    st.error(f"🔴 Unexpected response format from server: Missing key {e}")
                except Exception as e:
                    st.error(f"🔴 An unexpected error occurred: {e}")
                    st.info("💡 Please try again or contact support if the issue persists.")

with bundle_tab:
    st.subheader("🧾 FHIR Bundle Demo")
    st.info("Save a condition with dual coding (NAMASTE + ICD-11) to demonstrate FHIR Bundle creation.")
    
    namaste_code = st.text_input("Enter NAMASTE code", placeholder="e.g., DBC1.3", key="bundle_namaste_code")
    patient_id = st.text_input("Enter Patient ID", "Patient/001", key="bundle_patient_id")
    
    if st.button("💾 Save Condition Bundle", type="primary"):
        if not namaste_code: 
            st.warning("Please enter a NAMASTE code.")
        else:
            with st.spinner("Creating FHIR Bundle with dual coding..."):
                bundle = {
                    "resourceType": "Bundle", 
                    "type": "collection", 
                    "entry": [{
                        "resource": {
                            "resourceType": "Condition", 
                            "code": {
                                "coding": [{
                                    "system": "https://demo.sih/fhir/CodeSystem/namaste", 
                                    "code": namaste_code, 
                                    "display": "NAMASTE term"
                                }]
                            }, 
                            "subject": {"reference": patient_id}
                        }
                    }]
                }
                try:
                    resp = requests.post(f"{BACKEND_URL}/fhir/Bundle", json=bundle, timeout=30)
                    if resp.status_code == 201:
                        st.success("✅ FHIR Bundle created successfully with dual coding!")
                        
                        # Display the enhanced bundle
                        result = resp.json()
                        
                        # Show summary
                        col1, col2 = st.columns(2)
                        with col1:
                            st.metric("Bundle Status", result.get("status", "unknown").title())
                        with col2:
                            st.metric("Conditions Processed", len(result.get("stored", [])))
                        
                        # Show detailed bundle
                        with st.expander("📄 View Complete FHIR Bundle", expanded=False):
                            st.json(result, expanded=False)
                        
                        # Show dual coding information if available
                        stored_conditions = result.get("stored", [])
                        if stored_conditions:
                            condition = stored_conditions[0]
                            codings = condition.get("code", {}).get("coding", [])
                            
                            if len(codings) > 1:
                                st.success("🎯 Dual coding successfully applied!")
                                st.markdown("**Applied Codings:**")
                                for i, coding in enumerate(codings, 1):
                                    system_name = "NAMASTE" if "namaste" in coding.get("system", "") else "ICD-11"
                                    st.markdown(f"- **{system_name}:** `{coding.get('code', 'N/A')}` - {coding.get('display', 'N/A')}")
                    else:
                        st.error(f"❌ Failed to save bundle. Server responded with status {resp.status_code}:")
                        st.json(resp.json())
                        
                except requests.exceptions.RequestException as e:
                    st.error(f"❌ Error connecting to the backend: {e}")
                except Exception as e:
                    st.error(f"❌ Unexpected error: {e}")