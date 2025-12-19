import io
import requests
import trafilatura
from bs4 import BeautifulSoup
from pypdf import PdfReader
from duckduckgo_search import DDGS
from urllib.parse import urlparse
import google.generativeai as genai

class MedicalCongressAgent:
    def __init__(self):
        # --- 🔑 API KEY CONFIGURATION ---
        # PASTE YOUR KEY INSIDE THE QUOTES BELOW
        self.API_KEY = "PASTE_YOUR_GOOGLE_API_KEY_HERE"
        
        if self.API_KEY == "PASTE_YOUR_GOOGLE_API_KEY_HERE":
            print("⚠️ WARNING: No API Key found. Please paste it in backend.py line 14.")
        else:
            genai.configure(api_key=self.API_KEY)
            
        self.ddgs = DDGS()
        self.excluded_domains = [
            "pubmed.ncbi.nlm.nih.gov", "embase.com", "clinicaltrials.gov",
            "cochranelibrary.com", "sciencedirect.com", "researchgate.net",
            "wiley.com", "springer.com", "nejm.org", "thelancet.com",
            "googleapis.com", "google.com", "wikipedia.org", "youtube.com",
            "github.com", "facebook.com", "twitter.com"
        ]

    def _generate_acronym(self, phrase):
        ignore = {'of', 'and', 'the', 'for', 'in', 'with'}
        words = [w for w in phrase.split() if w.lower() not in ignore]
        if len(words) < 2: return None
        return "".join([w[0].upper() for w in words])

    def search_congresses(self, user_query, max_results=5):
        if not user_query or not user_query.strip(): return []

        acronym = self._generate_acronym(user_query)
        main_term = f'("{user_query}" OR "{acronym}")' if acronym else f'("{user_query}")'

        # STRICT CONTEXT: Medical Conferences Only
        context_terms = '("medical conference" OR "scientific congress" OR "annual meeting" OR "clinical symposium")'
        anti_spam = '-chatgpt -openai -github -python -code'
        
        final_query = f'{main_term} {context_terms} {anti_spam}'
        print(f"Agent Query: {final_query}")
        
        try:
            # Fetch 10x results to filter effectively
            raw_results = list(self.ddgs.text(final_query, max_results=max_results * 10))
            
            clean_results = []
            for res in raw_results:
                link = res['href']
                title = res['title'].lower()
                domain = urlparse(link).netloc.lower()
                
                if any(bad in domain for bad in self.excluded_domains): continue
                if any(x in title for x in ['chatgpt', 'openai', 'github', 'code']): continue
                
                clean_results.append(res)
                if len(clean_results) >= max_results: break
            
            return clean_results
        except Exception as e:
            print(f"Search Error: {e}")
            return []

    def extract_abstract(self, url, user_query):
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            try:
                head = requests.head(url, headers=headers, timeout=5, allow_redirects=True)
                content_type = head.headers.get('Content-Type', '').lower()
            except: content_type = ""

            # 1. Handle PDF
            if 'application/pdf' in content_type or url.lower().endswith('.pdf'):
                raw_text = self._process_pdf_url(url, user_query)
                return self._analyze_with_gemini(raw_text, user_query)

            # 2. Handle HTML
            downloaded = trafilatura.fetch_url(url)
            if not downloaded: return {"error": "Connection Failed"}
            
            page_text = trafilatura.extract(downloaded) or ""
            
            # If text is short, look for PDF links
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
                # Scan first 2 pages + any page with keyword
                if i < 2 or user_query.lower() in text.lower():
                    extracted_text.append(text)
                if len(extracted_text) >= 15: break 
            
            return "\n".join(extracted_text)
        except: return ""

    def _analyze_with_gemini(self, text, user_query):
        """
        Sends text to Google Gemini 1.5 Pro for analysis.
        """
        if not text: return {"content": "No content."}
        
        # Keyword validation to save tokens
        if user_query.lower() not in text.lower():
             return {"error": f"Term '{user_query}' not found in document."}

        # Gemini Pro has a huge context window, so we can send more text (up to 30k chars here)
        input_text = text[:30000] 

        prompt = f"""
        You are a Medical Research Assistant. 
        Your task is to identify if the following document contains a conference abstract related to: "{user_query}".
        
        DOCUMENT TEXT:
        {input_text}
        
        INSTRUCTIONS:
        1. If NO relevant abstract is found, simply output "Not relevant".
        2. If YES, extract the Title of the abstract/talk.
        3. Write a 3-bullet summary of the clinical findings or study design.
        
        FORMAT:
        **Title:** [Insert Title]
        **Summary:**
        - [Point 1]
        - [Point 2]
        - [Point 3]
        """

        try:
            # Initialize Model
            model = genai.GenerativeModel('gemini-1.5-pro')
            response = model.generate_content(prompt)
            return {"content": response.text}

        except Exception as e:
            return {"content": f"Gemini Error: {e}"}