import streamlit as st
import concurrent.futures
from backend import MedicalCongressAgent

st.set_page_config(page_title="Gemini 3 Scout", page_icon="⚡", layout="wide")

agent = MedicalCongressAgent()

# --- SIDEBAR ---
with st.sidebar:
    st.title("⚡ Settings")
    
    st.markdown("### 📅 Date Filter")
    time_filter = st.radio(
        "Publish Date:",
        ["Any Time", "Past Year", "Past Month"],
        index=0
    )
    time_map = {"Any Time": None, "Past Year": "y", "Past Month": "m"}
    selected_time = time_map[time_filter]

    st.divider()
    
    # Defaults to 10, but 5 is faster
    max_results = st.slider("Max Sites to Analyze", 3, 20, 8)

# --- MAIN INTERFACE ---
st.header("Medical Conference Abstract Finder (Roche Gateway)")
st.markdown("> **Advanced Mode:** Parallel processing active (5x Speed).")

search_query = st.text_input("Search Topic", placeholder="e.g. Paroxysmal Nocturnal Hemoglobinuria")

if st.button("🚀 Find & Analyze"):
    if not search_query:
        st.warning("Please enter a topic.")
        st.stop()
    
    # Check for Key (Updated to look for PORTKEY_KEY)
    if "PASTE" in agent.PORTKEY_KEY:
        st.error("🚨 Missing Roche Portkey Key in backend.py or Secrets.")
        st.stop()

    with st.status(f"⚡ Scouting for '{search_query}'...", expanded=True) as status:
        
        # 1. SEARCH STEP (Fast)
        st.write("🧠 Generative AI is identifying specialist societies...")
        
        search_results = agent.search_congresses(
            search_query, 
            max_results=max_results,
            time_limit=selected_time
        )
        
        if not search_results:
            st.error("No results found. Try removing date filters.")
            status.update(label="Failed", state="error")
            st.stop()
            
        st.write(f"✅ Found {len(search_results)} candidates. Starting Parallel Analysis...")
        
        # 2. ANALYSIS STEP (Parallel)
        found_abstracts = []
        progress_bar = st.progress(0)
        completed_count = 0
        
        # This function helps us run the analysis in a separate thread
        def analyze_site(site):
            try:
                data = agent.extract_abstract(site['href'], search_query)
                return site, data
            except Exception as e:
                return site, {"error": str(e)}

        # Run 5 workers at once
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            # Submit all tasks
            future_to_site = {executor.submit(analyze_site, site): site for site in search_results}
            
            # As they finish, update the UI
            for future in concurrent.futures.as_completed(future_to_site):
                site, data = future.result()
                content = data.get("content", "")
                
                # Update Progress
                completed_count += 1
                progress_bar.progress(completed_count / len(search_results))
                
                # Filter results
                if "Not relevant" not in content and "No content" not in content and not data.get("error"):
                    st.write(f"📄 Match found: {site['title']}")
                    found_abstracts.append({
                        "title": site['title'], 
                        "url": site['href'], 
                        "summary": content
                    })
        
        status.update(label="Done!", state="complete", expanded=False)

    st.divider()
    
    # RESULTS DISPLAY
    if found_abstracts:
        st.success(f"Gemini identified {len(found_abstracts)} relevant abstracts.")
        for item in found_abstracts:
            with st.expander(f"📄 {item['title']}", expanded=True):
                st.caption(f"Source: {item['url']}")
                st.markdown(item['summary'])
    else:
        st.warning("Analysis complete. No relevant abstracts found in these results.")