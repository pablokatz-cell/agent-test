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

    # --- MODULE A: THE STRATEGIST ---
    def module_a_strategist(self, disease_area):
        return [
            {"name": "AAIC (Alzheimer's Association International Conference)", "type": "High Impact"},
            {"name": "AAN (American Academy of Neurology)", "type": "High Impact"},
            {"name": "AD/PD (Intl Conf on Alzheimer's & Parkinson's)", "type": "Specialty"},
            {"name": "CTAD (Clinical Trials on Alzheimer's)", "type": "Specialty"}
        ]

    # --- MODULE B: THE NAVIGATOR ---
    def module_b_navigator(self, congress_list):
        targeted_results = []
        
        # DEMO BACKUPS: Real URLs to use if search fails
        demo_urls = {
            "AAIC": "https://alz.org/aaic/scientific-program.asp", # Likely to block, but we try
            "CTAD": "https://www.ctad-alzheimer.com/files/files/CTAD2024_Abstracts.pdf", # Works great (PDF)
            "AAN": "https://www.aan.com/events/annual-meeting", 
            "AD/PD": "https://adpd.kenes.com/"
        }

        for item in congress_list:
            congress = item["name"]
            found_url = None
            
            # 1. Try Real Search (Prioritize PDFs as they are rarely blocked)
            try:
                queries = [
                    f'{congress} 2024 scientific program abstracts filetype:pdf',
                    f'{congress} 2024 journal supplement',
                    f'{congress} 2025 abstract archive'
                ]
                for q in queries:
                    results = list(self.ddgs.text(q, max_results=2))
                    for res in results:
                        u = res['href'].lower()
                        if any(x in u for x in ['pdf', 'program', 'abstract', 'supplement']):
                            found_url = res
                            break
                    if found_url: break
            except: pass

            # 2. Use Demo Backup if search failed
            if not found_url:
                for key, url in demo_urls.items():
                    if key in congress:
                        found_url = {'title': f"{congress} (Demo Source)", 'href': url}
                        break
            
            if found_url:
                targeted_results.append({
                    "congress": congress,
                    "type": item["type"],
                    "title": found_url['title'],
                    "url": found_url['href']
                })
        return targeted_results

    # --- MODULE C: THE CODER (CLEAN - NO FAKE DATA) ---
    def module_c_coder(self, url, congress_name):
        try:
            # 1. FETCH CONTENT
            headers = {'User-Agent': 'Mozilla/5.0'}
            content_type = ""
            raw_text = ""
            is_pdf = False
            
            try:
                head = requests.head(url, headers=headers, timeout=5, allow_redirects=True)
                content_type = head.headers.get('Content-Type', '').lower()
            except: pass

            # Attempt to download PDF or HTML
            if 'application/pdf' in content_type or url.lower().endswith('.pdf'):
                is_pdf = True
                try:
                    response = requests.get(url, headers=headers, timeout=15)
                    f = io.BytesIO(response.content)
                    reader = PdfReader(f)
                    # Read first 3 pages
                    raw_text = "\n".join([p.extract_text() for p in reader.pages[:3]])
                except: pass
            else:
                downloaded = trafilatura.fetch_url(url)
                if downloaded:
                    raw_text = trafilatura.extract(downloaded) or ""

            # IF CONTENT IS EMPTY -> RETURN ERROR (Do not fake it)
            if not raw_text or len(raw_text) < 50:
                return {"error": "Access Denied: The website blocked the automated scraper."}

            # 2. GENERATE SCRIPT (Only if we have real text)
            system_prompt = "You are a Senior Python Developer."
            user_prompt = f"""
            Task: Generate a Python script to scrape abstract data.
            
            CONTEXT:
            - Congress: {congress_name}
            - URL: {url}
            - Format: {'PDF' if is_pdf else 'HTML'}
            
            CONTENT PREVIEW:
            {raw_text[:8000]}
            
            REQUIREMENTS:
            1. Write a Python script using 'BeautifulSoup' (if HTML) or 'pypdf' (if PDF).
            2. The script must extract: Congress Name, Date, Title, Authors, Body.
            3. Also extract 1 sample abstract from the content preview provided above.
            
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