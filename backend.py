import io
import requests
import trafilatura
from bs4 import BeautifulSoup
from pypdf import PdfReader
from duckduckgo_search import DDGS
from urllib.parse import urlparse
import streamlit as st
from openai import OpenAI  # We use the OpenAI client to connect to the Gateway

class MedicalCongressAgent:
    def __init__(self):
        # --- ROCHE GATEWAY CONFIGURATION ---
        try:
            self.PORTKEY_KEY = st.secrets["PORTKEY_API_KEY"]
        except:
            self.PORTKEY_KEY = "PASTE_YOUR_ROCHE_KEY_HERE"

        # Initialize Client pointing to Roche's Internal Gateway
        if "PASTE" not in self.PORTKEY_KEY:
            self.client = OpenAI(
                api_key=self.PORTKEY_KEY,
                base_url="https://eu.aigw.galileo.roche.com/v1" 
            )
        else:
            self.client = None

        self.ddgs = DDGS()
        self.excluded_domains = [
            "pubmed.ncbi.nlm.nih.gov", "embase.com", "clinicaltrials.gov",
            "cochranelibrary.com", "sciencedirect.com", "researchgate.net",
            "wiley.com", "springer.com", "nejm.org", "thelancet.com",
            "googleapis.com", "google.com", "wikipedia.org", "youtube.com",
            "github.com", "facebook.com", "twitter.com"
        ]

    def _get_dynamic_societies(self, user_query):
        """Asks AI to identify top 5 medical societies."""
        if not self.client: return []

        prompt = f"Identify the 5 most important medical societies for: '{user_query}'. Return ONLY domain names."
        try:
            # Using the specific Roche Model Name
            response = self.client.chat.completions.create(
                model="gemini-2.5-pro", 
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                stream=False # We disable streaming for the agent logic
            )
            text = response.choices[0].message.content
            return [d.strip() for d in text.split('\n') if '.' in d][:5]
        except Exception as e:
            print(f"Gateway Error: {e}")
            return []

    # ... (Keep existing _generate_smart_queries) ...
    def _generate_smart_queries(self, user_query, dynamic_sites):
        site_operator = ""
        if dynamic_sites:
            site_operator = " (" + " OR ".join([f"site:{d}" for d in dynamic_sites]) + ")"
        return [
            f'"{user_query}" conference abstract{site_operator}',
            f'"{user_query}" scientific program{site_operator}',
            f'"{user_query}" annual meeting abstract{site_operator}'
        ]

    # ... (Keep existing search_congresses) ...
    def search_congresses(self, user_query, max_results=10, time_limit=None):
        if not user_query: return []
        
        # 1. Dynamic Discovery
        print(f"🧠 Gateway identifying societies for '{user_query}'...")
        dynamic_sites = self._get_dynamic_societies(user_query)

        # 2. Generate Queries
        smart_queries = self._generate_smart_queries(user_query, dynamic_sites)

        all_results = []
        seen_urls = set()
        limit_per_query = max(3, int(max_results / len(smart_queries)) + 2)

        for q in smart_queries:
            final_q = f"{q} -chatgpt -github"
            try:
                results = list(self.ddgs.text(final_q, max_results=limit_per_query, timelimit=time_limit))
                for res in results:
                    link = res['href']
                    domain = urlparse(link).netloc.lower()
                    if link in seen_urls: continue
                    if any(bad in domain for bad in self.excluded_domains): continue
                    
                    seen_urls.add(link)
                    all_results.append(res)
            except: continue
        return all_results[:max_results]

    # ... (Keep existing extract_abstract, _hunt_for_pdf_links, _process_pdf_url) ...
    def extract_abstract(self, url, user_query):
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            try:
                head = requests.head(url, headers=headers, timeout=5, allow_redirects=True)
                content_type = head.headers.get('Content-Type', '').lower()
            except: content_type = ""

            if 'application/pdf' in content_type or url.lower().endswith('.pdf'):
                raw_text = self._process_pdf_url(url, user_query)
                return self._analyze_with_gateway(raw_text, user_query)

            downloaded = trafilatura.fetch_url(url)
            if not downloaded: return {"error": "Connection Failed"}
            
            page_text = trafilatura.extract(downloaded) or ""
            if len(page_text) < 1000:
                pdf_text = self._hunt_for_pdf_links(downloaded, url, user_query)
                if pdf_text: page_text += "\n\n" + pdf_text

            if not page_text.strip(): return {"error": "No text found."}

            return self._analyze_with_gateway(page_text, user_query)
        except Exception as e:
            return {"error": str(e)}

    def _hunt_for_pdf_links(self, html_content, base_url, user_query):
        if not html_content: return ""
        soup = BeautifulSoup(html_content, 'html.parser')
        for link in soup.find_all('a', href=True):
            href = link['href'].lower()
            if href.endswith('.pdf'):
                if href.startswith('/'): full = f"{'/'.join(base_url.split('/')[:3])}{href}"
                elif not href.startswith('http'): full = f"{base_url.rstrip('/')}/{href}"
                else: full = link['href']
                return self._process_pdf_url(full, user_query)
        return ""

    def _process_pdf_url(self, pdf_url, user_query):
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(pdf_url, headers=headers, timeout=15)
            f = io.BytesIO(response.content)
            reader = PdfReader(f)
            extracted_text = []
            for i, page in enumerate(reader.pages):
                text = page.extract_text() or ""
                if i < 3 or user_query.lower().split()[0] in text.lower():
                    extracted_text.append(text)
                if len(extracted_text) >= 15: break 
            return "\n".join(extracted_text)
        except: return ""

    def _analyze_with_gateway(self, text, user_query):
        if not text: return {"content": "No content."}
        if user_query.lower().split()[0] not in text.lower():
             return {"error": f"Term '{user_query}' not found."}
        
        input_text = text[:30000]
        
        system_prompt = "You are a Medical Research Assistant. Extract conference abstracts."
        user_prompt = f"""
        Identify if this document contains a conference abstract related to: "{user_query}".
        DOCUMENT TEXT: {input_text}
        INSTRUCTIONS:
        1. If NO relevant abstract is found, output "Not relevant".
        2. If YES, extract Title and 3-bullet summary.
        FORMAT: **Title:** [Title]\n**Summary:**\n- [Point 1]
        """

        try:
            # CONNECTING TO ROCHE GATEWAY
            response = self.client.chat.completions.create(
                model="gemini-2.5-pro", # Use the internal model name
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                stream=False
            )
            return {"content": response.choices[0].message.content}
        except Exception as e:
            return {"content": f"Gateway Error: {e}"}