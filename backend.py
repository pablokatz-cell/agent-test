import io
import time
import requests
import trafilatura
from bs4 import BeautifulSoup
from pypdf import PdfReader
from duckduckgo_search import DDGS
from urllib.parse import urlparse
import google.generativeai as genai
import streamlit as st

class MedicalCongressAgent:
    def __init__(self):
        try:
            self.API_KEY = st.secrets["GOOGLE_API_KEY"]
        except:
            self.API_KEY = "PASTE_YOUR_GOOGLE_API_KEY_HERE"
        
        if "PASTE" not in self.API_KEY and self.API_KEY:
            genai.configure(api_key=self.API_KEY)
            
        self.ddgs = DDGS()
        
        # We keep the blacklist to avoid spam
        self.excluded_domains = [
            "pubmed.ncbi.nlm.nih.gov", "embase.com", "clinicaltrials.gov",
            "cochranelibrary.com", "sciencedirect.com", "researchgate.net",
            "wiley.com", "springer.com", "nejm.org", "thelancet.com",
            "googleapis.com", "google.com", "wikipedia.org", "youtube.com",
            "github.com", "facebook.com", "twitter.com"
        ]

    def _get_dynamic_societies(self, user_query):
        """
        Asks Gemini to identify the top 5 relevant medical societies 
        for the specific disease/topic provided.
        """
        if "PASTE" in self.API_KEY: return []

        prompt = f"""
        You are a Medical Librarian. The user is researching: "{user_query}".
        Identify the 5 most important medical societies or congresses for this SPECIFIC topic.
        
        Return ONLY their official domain names (e.g., 'hematology.org', 'asco.org').
        Output format: just the domains, one per line. No bullets.
        """
        try:
            # Using Gemini 3 Pro (or 1.5 Pro) to find the best sites
            model = genai.GenerativeModel('gemini-3-pro-preview')
            response = model.generate_content(prompt)
            domains = [d.strip() for d in response.text.split('\n') if '.' in d]
            return domains[:5] # Limit to top 5 to keep search fast
        except:
            return []

    def _generate_smart_queries(self, user_query, dynamic_sites):
        """
        Generates search queries that include the AI-discovered sites.
        """
        site_operator = ""
        if dynamic_sites:
            # Create a string like: (site:aao.org OR site:arvo.org)
            site_operator = " (" + " OR ".join([f"site:{d}" for d in dynamic_sites]) + ")"
        
        queries = [
            f'"{user_query}" conference abstract{site_operator}',
            f'"{user_query}" scientific program{site_operator}',
            f'"{user_query}" annual meeting abstract{site_operator}'
        ]
        return queries

    def search_congresses(self, user_query, max_results=10, selected_societies=None, time_limit=None):
        if not user_query: return []

        # 1. AI DYNAMIC DISCOVERY
        # If the user didn't pick manual societies, let AI find the best ones.
        dynamic_sites = []
        if not selected_societies:
            print(f"🧠 AI is identifying specialist societies for '{user_query}'...")
            dynamic_sites = self._get_dynamic_societies(user_query)
            print(f"🎯 AI Targeted: {dynamic_sites}")
        else:
            # Use the manual selection from the sidebar
            # (You'd need to map these names to URLs if using the manual list)
            pass 

        # 2. Generate Queries
        smart_queries = self._generate_smart_queries(user_query, dynamic_sites)

        all_results = []
        seen_urls = set()
        limit_per_query = max(3, int(max_results / len(smart_queries)) + 2)

        for q in smart_queries:
            # Add Anti-Spam
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
            except Exception as e:
                print(f"Search Error: {e}")
                continue
        
        return all_results[:max_results]

    def extract_abstract(self, url, user_query):
        # ... (Keep your existing extraction code unchanged) ...
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            try:
                head = requests.head(url, headers=headers, timeout=5, allow_redirects=True)
                content_type = head.headers.get('Content-Type', '').lower()
            except: content_type = ""

            if 'application/pdf' in content_type or url.lower().endswith('.pdf'):
                raw_text = self._process_pdf_url(url, user_query)
                return self._analyze_with_gemini(raw_text, user_query)

            downloaded = trafilatura.fetch_url(url)
            if not downloaded: return {"error": "Connection Failed"}
            
            page_text = trafilatura.extract(downloaded) or ""
            if len(page_text) < 1000:
                pdf_text = self._hunt_for_pdf_links(downloaded, url, user_query)
                if pdf_text: page_text += "\n\n" + pdf_text

            if not page_text.strip(): return {"error": "No text found."}

            return self._analyze_with_gemini(page_text, user_query)
        except Exception as e:
            return {"error": str(e)}

    def _hunt_for_pdf_links(self, html_content, base_url, user_query):
        # ... (Keep existing helper) ...
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
        # ... (Keep existing helper) ...
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

    def _analyze_with_gemini(self, text, user_query):
        # ... (Keep existing helper) ...
        if not text: return {"content": "No content."}
        if user_query.lower().split()[0] not in text.lower():
             return {"error": f"Term '{user_query}' not found."}
        input_text = text[:35000]
        prompt = f"""
        Identify if this document contains a conference abstract related to: "{user_query}".
        DOCUMENT TEXT: {input_text}
        INSTRUCTIONS:
        1. If NO relevant abstract is found, output "Not relevant".
        2. If YES, extract Title and 3-bullet summary.
        FORMAT: **Title:** [Title]\n**Summary:**\n- [Point 1]...
        """
        try:
            model = genai.GenerativeModel('gemini-3-pro-preview')
            response = model.generate_content(prompt)
            return {"content": response.text}
        except:
             try:
                model = genai.GenerativeModel('gemini-1.5-pro')
                response = model.generate_content(prompt)
                return {"content": response.text}
             except Exception as e: return {"content": str(e)}