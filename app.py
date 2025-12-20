import streamlit as st
from backend import MedicalCongressAgent

st.set_page_config(page_title="Gemini 3 Scout", page_icon="⚡", layout="wide")

agent = MedicalCongressAgent()

# --- SIDEBAR ---
with st.sidebar:
    st.title("⚡ Settings")
    
    st.markdown("### 🤖 Target Strategy")
    st.info(
        "**AI Auto-Discovery Active**\n\n"
        "Instead of a fixed list, Gemini 3 now identifies the top 5 specialist societies "
        "for your specific topic (e.g., 'Glaucoma' → AAO, ARVO, EGS) automatically."
    )

    st.divider()

    # Date Filter
    st.markdown("### 📅 Date Filter")
    time_filter = st.radio(
        "Publish Date:",
        ["Any Time", "Past Year", "Past Month"],
        index=0
    )
    time_map = {"Any Time": None, "Past Year": "y", "Past Month": "m"}
    selected_time = time_map[time_filter]

    st.divider()
    max_results = st.slider("Max Sites", 5, 50, 10)

# --- MAIN INTERFACE ---
st.header("Medical Conference Abstract Finder (Gemini 3)")
st.markdown("> **Advanced Mode:** AI automatically targets the most relevant specialist societies for your topic.")

search_query = st.text_input("Search Topic", placeholder="e.g. Multiple Sclerosis")

if st.button("🚀 Find & Analyze"):
    if not search_query:
        st.warning("Please enter a topic.")
        st.stop()
    
    if "PASTE_YOUR" in agent.API_KEY:
        st.error("🚨 Missing API Key in backend.py")
        st.stop()

    with st.status(f"⚡ Scouting for '{search_query}'...", expanded=True) as status:
        
        # SEARCH STEP
        st.write("🧠 Generative AI is identifying top specialist societies...")
        
        # We removed 'selected_societies' because AI handles it internally now
        results = agent.search_congresses(
            search_query, 
            max_results=max_results,
            time_limit=selected_time
        )
        
        if not results:
            st.error("No results found. Try removing date filters.")
            status.update(label="Failed", state="error")
            st.stop()
            
        st.write(f"✅ Found {len(results)} matches. Analyzing content...")
        
        # ANALYSIS STEP
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
    
    # RESULTS DISPLAY
    if found_abstracts:
        st.success(f"Gemini identified {len(found_abstracts)} highly relevant abstracts.")
        for item in found_abstracts:
            with st.expander(f"📄 {item['title']}", expanded=True):
                st.caption(f"Source: {item['url']}")
                st.markdown(item['summary'])
    else:
        st.warning("Gemini read the sites but found no matching abstracts.")