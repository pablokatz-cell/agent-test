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

    # --- USER INPUT STEP (Predefined Congresses) ---
    def get_predefined_congresses(self, disease_area):
        """
        Maps the user input to the 3 predefined congresses requested in the spec.
        Includes specific search hints for the Navigator.
        """
        if "alzheimer" in disease_area.lower():
            return [
                {
                    "name": "AAIC (Alzheimer's Association International Conference)", 
                    "hint": "Alzheimer’s & Dementia Supplementary Issues Podium abstracts"
                },
                {
                    "name": "AAN (American Academy of Neurology Annual Meeting)", 
                    "hint": "Neurology Supplement Issues"
                },
                {
                    "name": "CTAD (Clinical Trials on Alzheimer's Disease)", 
                    "hint": "Journal of Prevention of Alzheimer’s Disease"
                }
            ]
        # Fallback for other queries
        return [{"name": f"{disease_area} Congress", "hint": "Scientific Program"}]

    # --- MODULE A: THE NAVIGATOR (Search & Location) ---
    def module_a_navigator(self, congress_list):
        targeted_results = []
        
        # TARGET URLs (From Validation Workflow Spec)
        # We prioritize these URLs. If not found, we search.
        known_targets = {
            "AAIC": "https://alz.org/aaic/scientific-program.asp",
            "CTAD": "https://www.ctad-alzheimer.com/files/files/CTAD2024_Abstracts.pdf", # PDF Detection Test
            "AAN": "https://www.aan.com/events/annual-meeting"
        }

        for item in congress_list:
            congress = item["name"]
            hint = item.get("hint", "")
            found_url = None
            
            # 1. Check Known Targets first
            for key, url in known_targets.items():
                if key in congress:
                    found_url = {'title': f"{congress} (Official Target)", 'href': url}
                    break
            
            # 2. If no known target, Search using hints
            if not found_url:
                try:
                    # Queries based on "Locating the Archive" instructions
                    queries = [
                        f'{congress} 2024 {hint}',
                        f'{congress} 2024 scientific sessions abstracts',
                        f'{congress} 2024 journal supplement'
                    ]
                    for q in queries:
                        results = list(self.ddgs.text(q, max_results=2))
                        for res in results:
                            u = res['href'].lower()
                            # Look for keywords: abstract, program, supplement, pdf
                            if any(x in u for x in ['pdf', 'program', 'abstract', 'supplement', 'journal']):
                                found_url = res
                                break
                        if found_url: break
                except: pass

            if found_url:
                targeted_results.append({
                    "congress": congress,
                    "title": found_url['title'],
                    "url": found_url['href']
                })
        
        return targeted_results

    # --- MODULE B: THE CODER (Script Generation) ---
    def module_b_coder(self, url, congress_name):
        try:
            # 1. DETECT PDF VS HTML
            headers = {'User-Agent': 'Mozilla/5.0'}
            content_type = ""
            is_pdf = False
            
            if url.lower().endswith('.pdf'):
                is_pdf = True
            else:
                try:
                    head = requests.head(url, headers=headers, timeout=5, allow_redirects=True)
                    content_type = head.headers.get('Content-Type', '').lower()
                    if 'application/pdf' in content_type:
                        is_pdf = True
                except: pass

            # 2. FETCH CONTENT (DOM or TEXT)
            raw_text = ""
            try:
                if is_pdf:
                    response = requests.get(url, headers=headers, timeout=15)
                    f = io.BytesIO(response.content)
                    reader = PdfReader(f)
                    # Read first 3 pages for structure analysis
                    raw_text = "\n".join([p.extract_text() for p in reader.pages[:3]])
                else:
                    # For HTML, we need the DOM structure, but trafilatura gives text.
                    # We will try to fetch raw HTML for the prompt context if possible,
                    # otherwise fallback to text. 
                    downloaded = trafilatura.fetch_url(url)
                    if downloaded:
                        raw_text = trafilatura.extract(downloaded) or ""
            except Exception as e:
                return {"error": f"Connection Error: {str(e)}"}

            # VALIDATION: If blocked
            if not raw_text or len(raw_text) < 100:
                return {"error": "Access Denied: Website blocked the scraper or is empty."}

            # 3. GENERATE SCRIPT (With Strict CSV Schema)
            system_prompt = "You are a Senior Python Developer."
            user_prompt = f"""
            Task: Generate a Python script to parse congress abstracts.
            
            INPUT CONTEXT:
            - Congress: {congress_name}
            - URL: {url}
            - Type: {'PDF Document' if is_pdf else 'HTML Page'}
            
            CONTENT PREVIEW (To identify structure/tags):
            {raw_text[:5000]}
            
            STRICT REQUIREMENTS:
            1. Generate a Python script using 'BeautifulSoup' (if HTML) or 'pypdf' (if PDF).
            2. The script MUST output a CSV file named 'abstracts.csv'.
            3. The CSV MUST have exactly these headers (Data Dictionary):
               - congress_name
               - date
               - title
               - authors
               - body
            
            4. Based on the CONTENT PREVIEW, write the specific logic to find the title/authors/body.
            
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