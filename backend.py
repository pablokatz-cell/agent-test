import io
import requests
import trafilatura
from bs4 import BeautifulSoup
from pypdf import PdfReader
from duckduckgo_search import DDGS
import google.generativeai as genai

class MedicalCongressAgent:
    def __init__(self, api_key):
        genai.configure(api_key=api_key)
        self.ddgs = DDGS()
        
        # --- SMART MODEL SELECTION ---
        # We attempt to load Gemini 3. If unavailable, we fallback to 1.5 Pro.
        target_model = 'gemini-3.0-pro' 
        fallback_model = 'gemini-1.5-pro'
        
        try:
            # Test if we can initialize the specific model
            self.model = genai.GenerativeModel(target_model)
            print(f"✅ Successfully initialized {target_model}")
            self.model_name = target_model
        except:
            print(f"⚠️ {target_model} not found/accessible. Falling back to {fallback_model}.")
            self.model = genai.GenerativeModel(fallback_model)
            self.model_name = fallback_model

        # Database Blacklist (Unchanged)
        self.excluded_sites = [
            "pubmed.ncbi.nlm.nih.gov", "embase.com", "clinicaltrials.gov",
            "cochranelibrary.com", "sciencedirect.com", "researchgate.net",
            "wiley.com", "springer.com", "nejm.org", "thelancet.com"
        ]

    def search_congresses(self, area, disease, keywords, max_results=5):
        exclusions = " ".join([f"-site:{site}" for site in self.excluded_sites])
        event_terms = '(conference OR congress OR "annual meeting" OR symposium)'
        doc_terms = '("book of abstracts" OR "scientific program" OR "poster session" OR "abstract book")'
        
        final_query = f'"{area}" "{disease}" {keywords} {event_terms} {doc_terms} {exclusions}'
        print(f"Agent Query: {final_query}")
        
        try:
            return list(self.ddgs.text(final_query, max_results=max_results))
        except Exception as e:
            print(f"Search Error: {e}")
            return []

    def extract_abstract(self, url, disease, area):
        try:
            # 1. Headers Check
            try:
                head = requests.head(url, timeout=5, allow_redirects=True)
                content_type = head.headers.get('Content-Type', '').lower()
            except:
                content_type = ""

            # 2. PDF Check
            if 'application/pdf' in content_type or url.lower().endswith('.pdf'):
                return self._process_pdf_url(url, disease, area)

            # 3. Webpage Extraction
            downloaded = trafilatura.fetch_url(url)
            if not downloaded:
                return {"error": "Connection Failed"}
            
            page_text = trafilatura.extract(downloaded)
            
            # 4. Hidden PDF Hunt
            pdf_text = self._hunt_for_pdf_links(downloaded, url, disease)
            
            full_context = f"WEBPAGE CONTENT:\n{page_text or ''}\n\nLINKED PDF CONTENT:\n{pdf_text or ''}"
            
            if len(full_context) < 100:
                return {"error": "No content found"}

            return self._analyze_with_gemini(full_context, disease, area, url)

        except Exception as e:
            return {"error": str(e)}

    def _hunt_for_pdf_links(self, html_content, base_url, keyword):
        if not html_content: return ""
        soup = BeautifulSoup(html_content, 'html.parser')
        pdf_links = []
        
        for link in soup.find_all('a', href=True):
            href = link['href'].lower()
            if href.endswith('.pdf') and any(x in href or x in link.get_text().lower() for x in ['abstract', 'program']):
                if href.startswith('/'):
                    full = f"{'/'.join(base_url.split('/')[:3])}{href}"
                elif not href.startswith('http'):
                    full = f"{base_url.rstrip('/')}/{href}"
                else:
                    full = link['href']
                pdf_links.append(full)
        
        if pdf_links:
            return self._process_pdf_url(pdf_links[0], keyword, "")['content']
        return ""

    def _process_pdf_url(self, pdf_url, keyword, area):
        try:
            response = requests.get(pdf_url, timeout=10)
            f = io.BytesIO(response.content)
            reader = PdfReader(f)
            extracted_text = []
            
            for page in reader.pages:
                text = page.extract_text()
                if text and (keyword.lower() in text.lower() or area.lower() in text.lower()):
                    extracted_text.append(text)
                if len(extracted_text) >= 20: break
            
            if not extracted_text:
                return {"content": "PDF downloaded, but no relevant text found."}
            return {"content": "\n".join(extracted_text)}
        except Exception as e:
            return {"content": f"Error reading PDF: {e}"}

    def _analyze_with_gemini(self, text, disease, area, url):
        # Optimized prompt for the stronger model
        prompt = f"""
        Act as a Senior Medical Researcher.
        
        METADATA:
        - URL: {url}
        - Target: {disease} ({area})
        
        TASK:
        1. Verify source is a Conference/Congress/Symposium.
        2. Extract the CLINICAL ABSTRACT matching the target disease.
        3. If multiple abstracts exist, summarize the most significant one (e.g. Phase 3 results).
        
        INPUT TEXT:
        {text[:40000]} 
        
        OUTPUT FORMAT:
        - If Invalid: "INVALID SOURCE"
        - If Valid: Return **Title**, **Authors**, and **Structured Abstract**.
        """
        try:
            response = self.model.generate_content(prompt)
            return {"content": response.text}
        except Exception as e:
            return {"error": f"Gemini Error: {e}"}