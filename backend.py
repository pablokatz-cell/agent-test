import io
import requests
import trafilatura
from bs4 import BeautifulSoup
from pypdf import PdfReader
from duckduckgo_search import DDGS
from urllib.parse import urlparse
import streamlit as st
from openai import OpenAI
import json

class MedicalCongressAgent:
    def __init__(self):
        # --- ROCHE GATEWAY CONFIGURATION ---
        self.PORTKEY_KEY = "H9nb7pQK5OU0SwIZUyPs1QFxOJJ1"
        if "PORTKEY_API_KEY" in st.secrets:
             self.PORTKEY_KEY = st.secrets["PORTKEY_API_KEY"]

        self.client = OpenAI(
            api_key=self.PORTKEY_KEY,
            base_url="https://us.aigw.galileo.roche.com/v1",
            timeout=300.0
        )
        self.MODEL_ID = "@org-gcp-general-us-central1/gemini-2.5-flash-lite"
        self.ddgs = DDGS()

    # --- USER INPUT MAPPING ---
    def get_predefined_congresses(self, disease_area):
        if "alzheimer" in disease_area.lower():
            return [
                {"name": "AAIC (Alzheimer's Association International Conference)"},
                {"name": "AAN (American Academy of Neurology Annual Meeting)"},
                {"name": "CTAD (Clinical Trials on Alzheimer's Disease)"}
            ]
        return [{"name": f"{disease_area} Congress"}]

    # --- MODULE A: THE NAVIGATOR ---
    def module_a_navigator(self, congress_list):
        targeted_results = []
        
        # EXACT URLs PROVIDED BY USER
        known_targets = {
            "AAIC": "https://aaic.alz.org/abstracts/abstracts-archive.asp",
            "AAN": "https://www.neurology.org/toc/wnl/104/7_Supplement_1",
            "CTAD": "https://www.sciencedirect.com/science/article/pii/S2274580724006368?via%3Dihub"
        }

        for item in congress_list:
            congress = item["name"]
            found_url = None
            
            # 1. Check Known Targets first
            for key, url in known_targets.items():
                if key in congress:
                    found_url = {'title': f"{congress} (Official Target)", 'href': url}
                    break
            
            # 2. Fallback search (only if new congresses are added later)
            if not found_url:
                try:
                    queries = [f'{congress} 2024 scientific program abstracts']
                    for q in queries:
                        results = list(self.ddgs.text(q, max_results=1))
                        if results:
                            found_url = results[0]
                            break
                except: pass

            if found_url:
                targeted_results.append({
                    "congress": congress,
                    "title": found_url['title'],
                    "url": found_url['href']
                })
        
        return targeted_results

    # --- MODULE B: THE CODER ---
    def module_b_coder(self, url, congress_name):
        try:
            # 1. FETCH CONTENT (With Robust Headers for ScienceDirect/Neurology.org)
            # These sites are strict, so we mimic a real Chrome browser.
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
            }
            
            content_type = ""
            is_pdf = False
            raw_text = ""

            # Detect PDF via URL extension first
            if url.lower().endswith('.pdf'):
                is_pdf = True
            
            try:
                # First HEAD request to check type
                head = requests.head(url, headers=headers, timeout=5, allow_redirects=True)
                content_type = head.headers.get('Content-Type', '').lower()
                if 'application/pdf' in content_type:
                    is_pdf = True
            except: pass

            try:
                if is_pdf:
                    response = requests.get(url, headers=headers, timeout=15)
                    f = io.BytesIO(response.content)
                    reader = PdfReader(f)
                    raw_text = "\n".join([p.extract_text() for p in reader.pages[:4]])
                else:
                    # For strict HTML sites (ScienceDirect), trafilatura is often safer than requests
                    downloaded = trafilatura.fetch_url(url)
                    if downloaded:
                        raw_text = trafilatura.extract(downloaded) or ""
                    
                    # Fallback: If trafilatura fails, try requests text
                    if not raw_text or len(raw_text) < 100:
                        resp = requests.get(url, headers=headers, timeout=10)
                        if resp.status_code == 200:
                            # We send a chunk of raw HTML so the LLM can see the class names
                            raw_text = resp.text[:15000] 
            except Exception as e:
                return {"error": f"Connection Error: {str(e)}"}

            # STRICT VALIDATION
            if not raw_text or len(raw_text) < 100:
                return {"error": "Access Denied: The website blocked the scraper. (ScienceDirect/Neurology often require Selenium)"}

            # 2. GENERATE SCRIPT
            system_prompt = "You are a Senior Python Developer."
            user_prompt = f"""
            Task: Generate a Python script to parse congress abstracts from this specific page.
            
            INPUT CONTEXT:
            - Congress: {congress_name}
            - URL: {url}
            - Type: {'PDF Document' if is_pdf else 'HTML Page'}
            
            CONTENT PREVIEW (First 10k chars):
            {raw_text[:10000]}
            
            STRICT REQUIREMENTS:
            1. Generate a Python script using 'BeautifulSoup' (HTML) or 'pypdf' (PDF).
            2. The script MUST output a CSV file named 'abstracts.csv'.
            3. The CSV MUST have these columns: congress_name, date, title, authors, body.
            4. Look at the CONTENT PREVIEW. If the page is a Table of Contents (like Neurology.org), write the script to extract the *links* to the abstracts. If it is the abstracts themselves, extract the text.
            
            Return JSON:
            {{
                "sample_abstract": {{ "title": "...", "authors": "...", "body": "..." }},
                "python_parsing_script": "Full python code here..."
            }}
            """

            response = self.client.chat.completions.create(
                model=self.MODEL_ID,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"},
                stream=False
            )
            return json.loads(response.choices[0].message.content)

        except Exception as e:
            return {"error": str(e)}