import streamlit as st
from backend import MedicalCongressAgent

st.set_page_config(page_title="Gemini 3 Scout", page_icon="⚡", layout="wide")

with st.sidebar:
    st.title("⚡ Gemini 3 Scout")
    st.markdown("### Settings")
    max_results = st.slider("Max Sites to Analyze", 5, 100, 10)

st.header("Medical Conference Abstract Finder (Gemini 3 Pro)")
st.markdown("> **Powered by Google Gemini 3 Pro** | The smartest reasoning model for complex medical analysis.")

search_query = st.text_input("Search Topic", placeholder="e.g. Paroxysmal Nocturnal Hemoglobinuria or PNH")

if st.button("🚀 Find & Analyze"):
    if not search_query:
        st.warning("Please enter a search topic.")
        st.stop()

    agent = MedicalCongressAgent()
    if "PASTE_YOUR" in agent.API_KEY:
        st.error("🚨 Missing API Key! Check backend.py")
        st.stop()
    
    with st.status(f"⚡ Gemini 3 is strategizing for '{search_query}'...", expanded=True) as status:
        
        st.write("🧠 Brainstorming search queries...")
        results = agent.search_congresses(search_query, max_results)
        
        if not results:
            st.error("No relevant conference sites found.")
            status.update(label="Failed", state="error")
            st.stop()
            
        st.write(f"✅ Found {len(results)} sites. analyzing...")
        
        found_abstracts = []
        progress_bar = st.progress(0)
        
        for idx, site in enumerate(results):
            progress_bar.progress((idx + 1) / len(results))
            st.write(f"Reading: {site['title']}...")
            
            data = agent.extract_abstract(site['href'], search_query)
            content = data.get("content", "")
            
            if "Not relevant" not in content and "No content" not in content and not data.get("error"):
                found_abstracts.append({
                    "title": site['title'], 
                    "url": site['href'], 
                    "summary": content
                })
        
        status.update(label="Done!", state="complete", expanded=False)

    st.divider()
    if found_abstracts:
        st.success(f"Gemini 3 found {len(found_abstracts)} relevant abstracts.")
        for item in found_abstracts:
            with st.expander(f"📄 {item['title']}", expanded=True):
                st.caption(f"Source: {item['url']}")
                st.markdown(item['summary'])
    else:
        st.warning("No relevant abstracts found.")