import io
import requests
import trafilatura
from bs4 import BeautifulSoup
from pypdf import PdfReader
from duckduckgo_search import DDGS
from urllib.parse import urlparse
import streamlit as st
from openai import OpenAI

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
        
        # 1. THE "NUCLEAR" BLACKLIST (Generic Consumer Sites)
        self.banned_domains = [
            # Consumer Health
            "mayoclinic.org", "webmd.com", "clevelandclinic.org", "healthline.com",
            "medicalnewstoday.com", "drugs.com", "medscape.com", "verywellhealth.com",
            "hopkinsmedicine.org", "nhs.uk", "cdc.gov", "who.int", "everydayhealth.com",
            "medlineplus.gov", "patient.info", "upmc.com", "uclahealth.org",
            # General Science/News (often too generic)
            "sciencedaily.com", "wikipedia.org", "nytimes.com", "forbes.com",
            "statnews.com", "nature.com", "sciencemag.org", "frontiersin.org",
            # Social / Tech
            "youtube.com", "facebook.com", "linkedin.com", "twitter.com", 
            "reddit.com", "quora.com", "github.com", "pinterest.com"
        ]

    def _get_dynamic_societies(self, user_query):
        if not self.client: return []
        # Prompt tweaked to ask for CONGRESS sites specifically
        prompt = f"Identify the 5 most important medical societies that hold annual congresses for: '{user_query}'. Return ONLY domain names."
        try:
            response = self.client.chat.completions.create(
                model="gemini-2.5-pro", 
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                stream=False
            )
            text = response.choices[0].message.content
            return [d.strip() for d in text.split('\n') if '.' in d][:5]
        except: return []

    def _generate_smart_queries(self, user_query, dynamic_sites):
        # 2. STRICTER QUERIES
        # We explicitly ask for "abstracts" and "posters"
        base_terms = [
            f'"{user_query}" conference abstract',
            f'"{user_query}" poster session pdf',
            f'"{user_query}" annual meeting proceedings',
            f'"{user_query}" scientific session'
        ]
        
        final_queries = []
        # If we have targeted societies, search ONLY inside them first
        if dynamic_sites:
            site_str = " OR ".join([f"site:{d}" for d in dynamic_sites])
            final_queries.append(f'"{user_query}" ({site_str}) abstract')
            final_queries.append(f'"{user_query}" ({site_str}) meeting')
        
        # Add the general queries as backup
        final_queries.extend(base_terms)
        return final_queries

    def _is_scientific_source(self, url):
        """
        The Gatekeeper: Returns True if the URL looks like a conference/paper.
        Returns False if it looks like a generic blog or health page.
        """
        u = url.lower()
        
        # A. Block explicit blacklisted domains
        domain = urlparse(u).netloc
        if any(ban in domain for ban in self.banned_domains):
            return False

        # B. Green Flags (Strong signs of a paper/abstract)
        green_flags = [
            ".pdf", "/abstract", "/poster", "/meeting", "/congress", 
            "/2023", "/2024", "/2025", "/proceedings", "/files/", 
            "/downloads/", "doi.org"
        ]
        if any(flag in u for flag in green_flags):
            return True

        # C. Red Flags (Strong signs of generic content)
        red_flags = [
            "/health-library/", "/diseases-conditions/", "/symptoms-causes/", 
            "/blog/", "/news/", "/press-release/", "/patient-care/",
            "/about-us/", "/contact/"
        ]
        if any(flag in u for flag in red_flags):
            return False

        # Default: If unsure, let it pass but it might be filtered later by content analysis
        return True

    def search_congresses(self, user_query, max_results=10, time_limit=None):
        if not user_query: return []
        
        print(f"🧠 Identifying societies for '{user_query}'...")
        dynamic_sites = self._get_dynamic_societies(user_query)
        smart_queries = self._generate_smart_queries(user_query, dynamic_sites)

        all_results = []
        seen_urls = set()
        
        # We search a bit more to allow for heavy filtering
        limit_per_query = max(3, int(max_results / len(smart_queries)) + 3)

        for q in smart_queries:
            # Force DuckDuckGo to remove generic sites at search level too
            final_q = f"{q} -mayoclinic -webmd -wikipedia"
            try:
                results = list(self.ddgs.text(final_q, max_results=limit_per_query, timelimit=time_limit))
                for res in results:
                    link = res['href']
                    
                    if link in seen_urls: continue
                    seen_urls.add(link)

                    # 3. APPLY THE GATEKEEPER CHECK
                    if self._is_scientific_source(link):
                        all_results.append(res)
                    else:
                        print(f"Skipped generic/consumer link: {link}")
                        
            except: continue
            
        return all_results[:max_results]

    def extract_abstract(self, url, user_query):
        # ... (Same extraction code as before) ...
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
        # ... (Same helper) ...
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
        # ... (Same helper) ...
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
        # ... (Same helper with Timeout) ...
        if not text: return {"content": "No content."}
        if user_query.lower().split()[0] not in text.lower():
             return {"error": f"Term '{user_query}' not found."}
        
        input_text = text[:30000]
        
        system_prompt = "You are a Medical Research Assistant. Extract conference abstracts."
        user_prompt = f"""
        Identify if this document contains a conference abstract or poster related to: "{user_query}".
        
        DOCUMENT TEXT:
        {input_text}
        
        INSTRUCTIONS:
        1. If NO relevant abstract is found, output "Not relevant".
        2. If YES, extract Title and 3-bullet summary.
        
        FORMAT:
        **Title:** [Title]
        **Summary:**
        - [Point 1]
        """

        try:
            response = self.client.chat.completions.create(
                model="gemini-2.5-pro",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                stream=False,
                timeout=300.0
            )
            return {"content": response.choices[0].message.content}
        except Exception as e:
            return {"content": f"Gateway Error: {e}"}