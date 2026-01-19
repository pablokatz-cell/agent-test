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
        try:
            self.PORTKEY_KEY = st.secrets["PORTKEY_API_KEY"]
        except:
            self.PORTKEY_KEY = "PASTE_YOUR_ROCHE_KEY_HERE"

        if "PASTE" not in self.PORTKEY_KEY:
            self.client = OpenAI(
                api_key=self.PORTKEY_KEY,
                base_url="https://eu.aigw.galileo.roche.com/v1",
                timeout=300.0
            )
        else:
            self.client = None

        self.ddgs = DDGS()

    # --- MODULE A: THE STRATEGIST ---
    # Identifies exactly 4 key congresses (2 High Impact, 2 Specialty) [cite: 6, 10, 11]
    def module_a_strategist(self, disease_area):
        if not self.client: return []
        
        system_prompt = "You are a Senior Medical Researcher. Return ONLY valid JSON."
        user_prompt = f"""
        For the disease area '{disease_area}', identify exactly 4 congresses.
        
        1. Category A (High-Impact): The 2 largest, most influential general societies (e.g. longstanding, >5000 attendees).
        2. Category B (Specialty): The 2 most relevant niche conferences focusing on trials or specific pathology.
        
        Return a JSON object with this exact structure:
        {{
            "high_impact": ["Congress Name 1 (Acronym)", "Congress Name 2 (Acronym)"],
            "specialty": ["Congress Name 3 (Acronym)", "Congress Name 4 (Acronym)"]
        }}
        """
        
        try:
            response = self.client.chat.completions.create(
                model="gemini-2.5-pro",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"},
                stream=False
            )
            data = json.loads(response.choices[0].message.content)
            # Flatten the list for the navigator
            return [
                {"name": name, "type": "High Impact"} for name in data.get("high_impact", [])
            ] + [
                {"name": name, "type": "Specialty"} for name in data.get("specialty", [])
            ]
        except Exception as e:
            print(f"Strategist Error: {e}")
            return []

    # --- MODULE B: THE NAVIGATOR ---
    # Finds specific 'Abstracts' or 'Scientific Program' URLs for the past year [cite: 18, 19, 42]
    def module_b_navigator(self, congress_list):
        targeted_results = []
        
        for item in congress_list:
            congress = item["name"]
            # Queries specifically looking for data sources (journals, archives, programs) [cite: 43-46]
            queries = [
                f'{congress} 2024 scientific program abstracts',
                f'{congress} 2024 journal supplement',
                f'{congress} annual meeting abstract archive'
            ]
            
            found_url = None
            for q in queries:
                try:
                    results = list(self.ddgs.text(q, max_results=3))
                    for res in results:
                        u = res['href'].lower()
                        t = res['title'].lower()
                        
                        # "Green Flags" that indicate this is a data source
                        if any(x in u or x in t for x in ['abstract', 'program', 'supplement', 'schedule', 'agenda', 'pdf']):
                            found_url = res
                            break
                    if found_url: break
                except: continue
            
            if found_url:
                targeted_results.append({
                    "congress": congress,
                    "type": item["type"],
                    "title": found_url['title'],
                    "url": found_url['href']
                })
        
        return targeted_results

    # --- MODULE C: THE CODER ---
    # Scrapes the structure and writes a Python script [cite: 28, 29, 31-33]
    def module_c_coder(self, url, congress_name):
        try:
            # 1. FETCH CONTENT
            headers = {'User-Agent': 'Mozilla/5.0'}
            content_type = ""
            try:
                head = requests.head(url, headers=headers, timeout=5, allow_redirects=True)
                content_type = head.headers.get('Content-Type', '').lower()
            except: pass

            raw_text = ""
            is_pdf = False
            
            if 'application/pdf' in content_type or url.lower().endswith('.pdf'):
                is_pdf = True
                response = requests.get(url, headers=headers, timeout=15)
                f = io.BytesIO(response.content)
                reader = PdfReader(f)
                # Read first few pages to understand structure
                raw_text = "\n".join([p.extract_text() for p in reader.pages[:4]])
            else:
                downloaded = trafilatura.fetch_url(url)
                if downloaded:
                    raw_text = trafilatura.extract(downloaded) or ""

            if not raw_text: return {"error": "Could not read content"}

            # 2. GENERATE SCRIPT
            system_prompt = "You are a Senior Python Developer."
            user_prompt = f"""
            Task: Generate a Python script to scrape abstract data from this specific format.
            
            CONTEXT:
            - Congress: {congress_name}
            - URL: {url}
            - Format: {'PDF' if is_pdf else 'HTML'}
            
            CONTENT PREVIEW:
            {raw_text[:10000]}
            
            REQUIREMENTS:
            1. Write a Python script using 'BeautifulSoup' (if HTML) or 'pypdf' (if PDF).
            2. The script must extract: Congress Name, Date, Title, Authors, Body.
            3. Also extract 1 sample abstract from the content preview provided above to prove it works.
            
            Return JSON:
            {{
                "sample_abstract": {{ "title": "...", "authors": "...", "body": "..." }},
                "python_parsing_script": "Full python code here..."
            }}
            """

            response = self.client.chat.completions.create(
                model="gemini-2.5-pro",
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