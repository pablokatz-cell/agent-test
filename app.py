import streamlit as st
from backend import MedicalCongressAgent

st.set_page_config(page_title="Congress Agent 2.0", page_icon="🧬", layout="wide")

agent = MedicalCongressAgent()

# --- SIDEBAR ---
with st.sidebar:
    st.title("🧬 Settings")
    st.info("Agent Mode: Architecture v2 (Strategist/Navigator/Coder)")

# --- MAIN INTERFACE ---
st.header("Congress Abstract Extraction Agent")
st.markdown("Identifies high-impact & specialty congresses, finds their abstract archives, and generates parsing code.")

# Input Zone [cite: 4, 36, 56]
disease_area = st.text_input("Enter Disease Area", placeholder="e.g. Alzheimer's Disease")

if st.button("🚀 Run Agent"):
    if not disease_area:
        st.error("Please enter a disease area.")
        st.stop()
    
    if "PASTE" in agent.PORTKEY_KEY:
        st.error("🚨 Missing Roche Portkey Key.")
        st.stop()

    # --- STEP 1: THE STRATEGIST ---
    st.subheader("1. The Strategist (Identification)")
    with st.spinner("Identifying top 4 congresses..."):
        congresses = agent.module_a_strategist(disease_area)
        
    if not congresses:
        st.error("Could not identify congresses.")
        st.stop()
        
    cols = st.columns(2)
    with cols[0]:
        st.markdown("**Category A: High Impact**")
        for c in congresses:
            if c['type'] == 'High Impact': st.success(f"🏛️ {c['name']}")
    with cols[1]:
        st.markdown("**Category B: Specialty**")
        for c in congresses:
            if c['type'] == 'Specialty': st.info(f"🔬 {c['name']}")

    # --- STEP 2: THE NAVIGATOR ---
    st.divider()
    st.subheader("2. The Navigator (Search & Location)")
    with st.spinner("Locating 2024/2025 Abstract Archives..."):
        targets = agent.module_b_navigator(congresses)
    
    for t in targets:
        st.markdown(f"**{t['congress']}** ({t['type']})")
        st.caption(f"Found Source: {t['url']}")

    # --- STEP 3: THE CODER ---
    st.divider()
    st.subheader("3. The Coder (Extraction & Scripting)")
    st.markdown("*Generates code to parse the identified pages into CSV.*")
    
    progress_bar = st.progress(0)
    
    for idx, target in enumerate(targets):
        progress_bar.progress((idx + 1) / len(targets))
        
        with st.expander(f"📄 Processing: {target['congress']}", expanded=True):
            data = agent.module_c_coder(target['url'], target['congress'])
            
            if "error" in data:
                st.error(f"Failed to process: {data['error']}")
            else:
                # User Zone: Data Preview
                st.markdown("### 📊 Extracted Sample")
                sample = data.get("sample_abstract", {})
                st.write(f"**Title:** {sample.get('title')}")
                st.write(f"**Authors:** {sample.get('authors')}")
                st.text_area("Abstract Body", sample.get('body'), height=100)
                
                # Developer Zone: The Code [cite: 8, 33, 48]
                st.markdown("---")
                st.markdown("### 🛠️ Developer Zone: Generated Parsing Script")
                st.code(data.get("python_parsing_script", "# No script generated"), language="python")