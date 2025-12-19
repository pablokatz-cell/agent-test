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
        # --- SECURE API KEY HANDLING ---
        try:
            self.API_KEY = st.secrets["GOOGLE_API_KEY"]
        except:
            self.API_KEY = "PASTE_YOUR_GOOGLE_API_KEY_HERE"
        
        if "PASTE" not in self.API_KEY and self.API_KEY:
            genai.configure(api_key=self.API_KEY)
            
        self.ddgs = DDGS()
        self.excluded_domains = [
            "pubmed.ncbi.nlm.nih.gov", "embase.com", "clinicaltrials.gov",
            "cochranelibrary.com", "sciencedirect.com", "researchgate.net",
            "wiley.com", "springer.com", "nejm.org", "thelancet.com",
            "googleapis.com", "google.com", "wikipedia.org", "youtube.com",
            "github.com", "facebook.com", "twitter.com"
        ]

    def _generate_smart_queries(self, user_query):
        """
        Uses Gemini 3 to brainstorm 3 distinct, high-quality search queries.
        """
        if "PASTE" in self.API_KEY:
            return [f'"{user_query}" medical conference abstract']

        prompt = f"""
        You are an expert Medical Librarian. 
        I need to find conference abstracts, posters, or scientific programs for the topic: "{user_query}".
        
        Generate 3 specific, distinct search queries to find these on the open web.
        - Query 1: Direct phrase match + conference terms.
        - Query 2: Broader therapeutic area or synonyms + "Abstract Book".
        - Query 3: Specific file types (PDF) or acronyms.
        
        Output ONLY the 3 queries, one per line. No numbering, no bullets.
        """
        
        try:
            # UPGRADED TO GEMINI 3 PRO
            # Note: We use the 'preview' tag as it often provides the earliest access to the newest weights
            model = genai.GenerativeModel('gemini-3-pro-preview')
            response = model.generate_content(prompt)
            queries = [q.strip() for q in response.text.split('\n') if q.strip()]
            return queries[:3]
        except Exception as e:
            print(f"Gemini 3 Query Gen Error: {e}")
            # Fallback to older model if 3 isn't available in your region yet
            try:
                model = genai.GenerativeModel('gemini-1.5-pro')
                response = model.generate_content(prompt)
                queries = [q.strip() for q in response.text.split('\n') if q.strip()]
                return queries[:3]
            except:
                return [f'"{user_query}" conference abstract']

    def search_congresses(self, user_query, max_results=10):
        if not user_query or not user_query.strip(): return []

        print(f"🧠 Asking Gemini 3 to brainstorm search queries for: {user_query}")
        smart_queries = self._generate_smart_queries(user_query)
        print(f"🔍 Gemini suggested: {smart_queries}")

        all_results = []
        seen_urls = set()

        # Dynamic limit based on number of queries
        limit_per_query = max(3, int(max_results / len(smart_queries)) + 2)

        for q in smart_queries:
            final_q = f"{q} -chatgpt -openai -github"
            
            try:
                results = list(self.ddgs.text(final_q, max_results=limit_per_query))
                
                for res in results:
                    link = res['href']
                    domain = urlparse(link).netloc.lower()
                    
                    if link in seen_urls: continue
                    if any(bad in domain for bad in self.excluded_domains): continue
                    
                    seen_urls.add(link)
                    all_results.append(res)
                    
            except Exception as e:
                print(f"Search Error on query '{q}': {e}")
                continue
        
        return all_results[:max_results]

    def extract_abstract(self, url, user_query):
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

    def _analyze_with_gemini(self, text, user_query):
        if not text: return {"content": "No content."}
        
        if user_query.lower().split()[0] not in text.lower():
             return {"error": f"Term '{user_query}' not found in document."}

        input_text = text[:35000] # Gemini 3 handles even larger contexts easily

        prompt = f"""
        You are a Medical Research Assistant. 
        Identify if the following document contains a conference abstract related to: "{user_query}".
        
        DOCUMENT TEXT:
        {input_text}
        
        INSTRUCTIONS:
        1. If NO relevant abstract is found, output "Not relevant".
        2. If YES, extract the Title.
        3. Write a 3-bullet summary of the clinical findings or study design.
        
        FORMAT:
        **Title:** [Insert Title]
        **Summary:**
        - [Point 1]
        - [Point 2]
        - [Point 3]
        """

        try:
            # UPGRADED TO GEMINI 3 PRO
            model = genai.GenerativeModel('gemini-3-pro-preview')
            response = model.generate_content(prompt)
            return {"content": response.text}

        except Exception as e:
            # Fallback to 1.5 Pro if 3 fails (e.g., API tier limits)
            try:
                model = genai.GenerativeModel('gemini-1.5-pro')
                response = model.generate_content(prompt)
                return {"content": response.text}
            except Exception as e2:
                return {"content": f"Gemini Error: {e2}"}