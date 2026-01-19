import streamlit as st
from backend import MedicalCongressAgent

st.set_page_config(page_title="Congress Abstract Agent", page_icon="🧬", layout="wide")

agent = MedicalCongressAgent()

# --- SIDEBAR ---
with st.sidebar:
    st.title("🧬 Settings")
    st.info("Mode: 2-Module Architecture (Navigator/Coder)")

# --- MAIN INTERFACE ---
st.header("Congress Abstract Extraction Agent")
st.markdown("Automated abstract locator and parser generator.")

# INPUT ZONE
disease_area = st.text_input("Enter Disease Area", placeholder="e.g. Alzheimer's Disease")

if st.button("🚀 Run Agent"):
    if not disease_area:
        st.error("Please enter a disease area.")
        st.stop()
    
    # --- PREDEFINED INPUT HANDLING ---
    # The "Strategist" is replaced by user inputs, mapped here.
    congresses = agent.get_predefined_congresses(disease_area)
    
    st.markdown("### 1. Target Congresses")
    for c in congresses:
        st.success(f"🎯 {c['name']}")

    # --- MODULE A: NAVIGATOR ---
    st.divider()
    st.subheader("Module A: The Navigator")
    with st.spinner("Locating 2024/2025 Archives..."):
        targets = agent.module_a_navigator(congresses)
    
    if not targets:
        st.error("No targets found.")
        st.stop()

    for t in targets:
        st.markdown(f"**{t['congress']}**")
        st.caption(f"🔗 Source: {t['url']}")

    # --- MODULE B: CODER ---
    st.divider()
    st.subheader("Module B: The Coder")
    st.markdown("*Generating CSV extraction script...*")
    
    progress_bar = st.progress(0)
    
    for idx, target in enumerate(targets):
        progress_bar.progress((idx + 1) / len(targets))
        
        with st.expander(f"📄 Processing: {target['congress']}", expanded=True):
            data = agent.module_b_coder(target['url'], target['congress'])
            
            if "error" in data:
                st.error(f"❌ {data['error']}")
            else:
                # RESULTS ZONE
                st.markdown("### 📊 Sample Data")
                sample = data.get("sample_abstract", {})
                st.write(f"**Title:** {sample.get('title')}")
                st.write(f"**Authors:** {sample.get('authors')}")
                st.text_area("Abstract Body", sample.get('body'), height=60)
                
                # DEVELOPER ZONE
                st.markdown("---")
                st.markdown("### 🛠️ Developer Zone: Parsing Script")
                st.code(data.get("python_parsing_script", "# No script"), language="python")