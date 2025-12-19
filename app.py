import streamlit as st
from backend import MedicalCongressAgent

st.set_page_config(page_title="Gemini Congress Scout", page_icon="✨", layout="wide")

with st.sidebar:
    st.title("✨ Gemini Scout")
    st.markdown("### Settings")
    max_results = st.slider("Max Sites to Analyze", 5, 50, 10)

st.header("Medical Conference Abstract Finder (Gemini Pro)")
st.markdown("> **Powered by Google Gemini 1.5 Pro** | Now using AI for **Search Strategy** & **Analysis**.")

search_query = st.text_input("Search Topic", placeholder="e.g. Paroxysmal Nocturnal Hemoglobinuria or PNH")

if st.button("🚀 Find & Analyze"):
    if not search_query:
        st.warning("Please enter a search topic.")
        st.stop()

    agent = MedicalCongressAgent()
    if "PASTE_YOUR" in agent.API_KEY:
        st.error("🚨 Missing API Key in backend.py!")
        st.stop()
    
    with st.status(f"✨ Brainstorming search strategy for '{search_query}'...", expanded=True) as status:
        
        # 1. Search (Now powered by Gemini)
        st.write("🧠 Asking Gemini to generate expert search queries...")
        results = agent.search_congresses(search_query, max_results)
        
        if not results:
            st.error("No relevant conference sites found.")
            status.update(label="Failed", state="error")
            st.stop()
            
        st.write(f"✅ Found {len(results)} potential sites. Analyzing content...")
        
        # 2. Analyze
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
        st.success(f"Gemini found {len(found_abstracts)} relevant abstracts.")
        for item in found_abstracts:
            with st.expander(f"📄 {item['title']}", expanded=True):
                st.caption(f"Source: {item['url']}")
                st.markdown(item['summary'])
    else:
        st.warning("Gemini read the sites but didn't find relevant abstracts.")