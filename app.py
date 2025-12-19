import streamlit as st
from backend import MedicalCongressAgent

st.set_page_config(page_title="Gemini 3 Research Scout", page_icon="🛸", layout="wide")
st.markdown("""<style>.reportview-container { margin-top: -2em; } #MainMenu {visibility: hidden;} footer {visibility: hidden;}</style>""", unsafe_allow_html=True)

with st.sidebar:
    st.title("🛸 Gemini 3 Scout")
    st.info("Attempting to use next-gen Gemini models. Auto-fallback enabled.")
    api_key = st.text_input("Google API Key", type="password")
    max_results = st.slider("Max Sites", 2, 10, 4)

st.header("Medical Conference Abstract Finder")
col1, col2 = st.columns(2)
with col1: ther_area = st.text_input("Therapeutic Area", value="Oncology")
with col2: disease = st.text_input("Disease / Indication", value="NSCLC")
keywords = st.text_input("Specific Keywords", placeholder="e.g. 'Phase 3' OR 'Overall Survival'")

if st.button("🚀 Find Conference Abstracts"):
    if not api_key:
        st.error("Google API Key required.")
        st.stop()
        
    agent = MedicalCongressAgent(api_key)
    
    # Display which model is actually being used
    st.toast(f"Brain active: {agent.model_name}", icon="🧠")
    
    with st.status(f"🔍 Searching events with {agent.model_name}...", expanded=True) as status:
        results = agent.search_congresses(ther_area, disease, keywords, max_results)
        
        if not results:
            st.error("No sites found.")
            st.stop()
            
        st.write(f"Found {len(results)} sites. Analyzing...")
        found_abstracts = []
        
        for site in results:
            st.write(f"Reading: {site['title']}")
            data = agent.extract_abstract(site['href'], disease, ther_area)
            content = data.get("content", "")
            
            if "INVALID SOURCE" in content:
                st.warning(f"Skipped {site['title']}: Not a conference.")
            elif data.get("error"):
                st.write(f"⚠️ Error: {data['error']}")
            else:
                found_abstracts.append({"title": site['title'], "url": site['href'], "text": content})
        
        status.update(label="Done!", state="complete", expanded=False)

    st.divider()
    if found_abstracts:
        for item in found_abstracts:
            with st.expander(f"📄 {item['title']}", expanded=True):
                st.caption(f"Source: {item['url']}")
                st.markdown(item['text'])
    else:
        st.warning("No relevant abstracts found.")