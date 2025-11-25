#!/usr/bin/env python3
"""
HTML Content Extractor - Surgical Edition V12 (Sibling Targeting)
Updated:
1. Metadata extraction uses strict 'find_next_sibling' from H1.
   - Finds H1 -> Finds next 'span.sub-title' -> Finds next 'p.lead'.
2. No guessing, no scanning unrelated elements.
3. No Backpack (Chunk 0).
"""

import json
import re
from bs4 import BeautifulSoup, Comment, Tag
from typing import Tuple, Optional, List, Set, Dict
from core.google_doc_extractor import extract_google_doc_content
from utils.helpers import safe_log, clean_text

class HTMLContentExtractor:
    
    def __init__(self):
        self.processed_elements: Set[str] = set()
        self.big_chunks = []
        self.chunk_index = 1
    
    def extract_content(self, html_content: str, casino_mode: bool = False) -> Tuple[bool, Optional[str], Optional[str]]:
        try:
            # Pre-clean
            html_content = re.sub(r'\[email&#160;protected\]', 'EMAIL_HIDDEN', html_content)
            soup = BeautifulSoup(html_content, 'html.parser')
            self._preprocess_soup(soup)
            
            self.processed_elements.clear()
            self.big_chunks = []
            self.chunk_index = 1
            
            if casino_mode:
                safe_log("Extractor: Running Surgical Casino Extraction V12")
                
                # 1. Metadata (Sibling Targeting)
                self._extract_metadata_chunk(soup)
                
                # 2. FAQ (Robust Search)
                faq_chunk = self._extract_faq_chunk(soup)
                
                # 3. Remove Noise
                self._remove_casino_widgets(soup)
                
                # 4. Main Body Scan
                main_wrapper = (
                    soup.find(id='review') or 
                    soup.find('section', class_='wrapper') or 
                    soup.find('div', class_='wrapper') or
                    soup.find('main') or 
                    soup.find('article') or
                    soup.find('div', class_='content')
                )
                
                if main_wrapper:
                    self._extract_with_direct_chunking(main_wrapper)
                else:
                    safe_log("Extractor: No main container found, scanning body", "WARNING")
                    body = soup.find('body') or soup
                    self._extract_with_direct_chunking(body)
                
                # 5. Append FAQ (if found)
                if faq_chunk:
                    faq_chunk["big_chunk_index"] = self.chunk_index
                    self.big_chunks.append(faq_chunk)
                    self.chunk_index += 1
                    
            else:
                safe_log("Extractor: Running Generic Extraction")
                body = soup.find('body') or soup
                self._extract_with_direct_chunking(body)
            
            return True, self._create_final_json(), None
            
        except Exception as e:
            return False, None, f"HTML parsing error: {str(e)}"

    def _preprocess_soup(self, soup: BeautifulSoup):
        for tag in soup(['script', 'style', 'nav', 'footer', 'aside', 'header', 'noscript', 'iframe', 'svg', 'button', 'form']):
            tag.decompose()
        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()

    def _remove_casino_widgets(self, soup: BeautifulSoup):
        # Aggressively remove sidebar/widget noise
        noise_patterns = [
            re.compile(r'^blockCasino'),
            re.compile(r'^widget'),
            re.compile(r'^sidebar'),
            re.compile(r'^related'),
            re.compile(r'^templateAuthor'),
            re.compile(r'^templateFooter') 
        ]
        for pattern in noise_patterns:
            for element in soup.find_all(attrs={'data-qa': pattern}):
                element.decompose()
            for element in soup.find_all(class_=pattern):
                element.decompose()

    def _extract_metadata_chunk(self, soup: BeautifulSoup):
        """
        V12 Update: Strict Sibling Targeting relative to H1.
        Structure expected:
        <h1>...</h1>
        <span class="sub-title">...</span>  (Next Sibling)
        <p class="lead">...</p>             (Next Sibling)
        """
        metadata_items = []
        
        # 1. Find H1 (The Anchor)
        # Check specific container first, then fallback to global
        intro_container = soup.find(attrs={'data-qa': re.compile(r'templateIntro', re.I)})
        search_scope = intro_container if intro_container else soup
        
        h1 = search_scope.find('h1')
        
        if h1:
            metadata_items.append(f"H1: {clean_text(h1.get_text())}")
            
            # 2. Find Subtitle (Next SPAN sibling after H1 with class sub-title)
            # We use find_next_sibling to skip whitespace/newlines automatically
            subtitle = h1.find_next_sibling('span', class_=re.compile(r'sub-title', re.I))
            if subtitle:
                metadata_items.append(f"SUBTITLE: {clean_text(subtitle.get_text())}")
                subtitle.decompose()
            
            # 3. Find Lead (Next P sibling after H1 with class lead)
            # Note: find_next_sibling on h1 searches forward. Even if lead is after subtitle, 
            # it is still a sibling of h1.
            lead = h1.find_next_sibling('p', class_=re.compile(r'lead', re.I))
            if lead:
                metadata_items.append(f"LEAD: {clean_text(lead.get_text())}")
                lead.decompose()
            
            # Cleanup H1 last so we don't lose the anchor reference for siblings above
            h1.decompose()

        # 4. Summary Block (Legacy check)
        summary_block = soup.find(attrs={'data-qa': 'blockCasinoSummary'})
        if summary_block:
            text = clean_text(summary_block.get_text())
            if text: metadata_items.append(f"SUMMARY: {text}")
            summary_block.decompose()

        if metadata_items:
            self.big_chunks.append({
                "big_chunk_index": self.chunk_index,
                "content_name": "Page Metadata & Summary",
                "small_chunks": metadata_items
            })
            self.chunk_index += 1

    def _extract_faq_chunk(self, soup: BeautifulSoup) -> Optional[Dict]:
        faq_items = []
        faq_section = None

        # A. Data Attribute
        faq_section = soup.find(attrs={'data-qa': 'templateFAQ'}) or soup.find(class_='faq-section')
        
        # B. Schema.org
        if not faq_section:
            faq_section = soup.find(attrs={'itemtype': re.compile(r'schema\.org/FAQPage')})

        # C. Header Hunt
        if not faq_section:
            for header in soup.find_all(['h2', 'h3']):
                if 'faq' in header.get_text().lower() or 'frequently asked' in header.get_text().lower():
                    faq_section = soup.new_tag('div')
                    curr = header.next_sibling
                    while curr and (not isinstance(curr, Tag) or curr.name not in ['h1', 'h2']):
                        if isinstance(curr, Tag): faq_section.append(curr.extract())
                        curr = curr.next_sibling
                    header.decompose()
                    break

        if not faq_section: return None

        # Extract Questions
        questions = faq_section.find_all(attrs={'itemtype': re.compile(r'schema\.org/Question')})
        if not questions: 
            questions = faq_section.find_all(['h3', 'h4', 'h5', 'strong', 'b'])

        for q in questions:
            q_text = clean_text(q.get_text())
            if not q_text or len(q_text) < 5: continue
            
            a_text = ""
            a_container = q.find(attrs={'itemprop': 'acceptedAnswer'})
            
            if a_container:
                a_text = clean_text(a_container.get_text())
            else:
                curr = q.next_sibling
                while curr and (not isinstance(curr, Tag) or curr.name in ['br', 'span']):
                    curr = curr.next_sibling
                
                if curr and isinstance(curr, Tag) and curr.name in ['p', 'div']:
                    a_text = clean_text(curr.get_text())

            if q_text and a_text:
                faq_items.append(f"FAQ_Q: {q_text} // FAQ_A: {a_text}")
                self._mark_processed(q)
                if 'curr' in locals() and curr: self._mark_processed(curr)

        if faq_section.parent: faq_section.decompose()
        
        if faq_items:
            return {"content_name": "Frequently Asked Questions", "small_chunks": faq_items}
        return None

    def _extract_with_direct_chunking(self, container):
        current_chunk_content = []
        pre_h2_content = []
        current_section_name = "Main Content"
        
        tags = ['h2', 'h3', 'h4', 'p', 'table', 'ul', 'ol', 'dl']
        
        for element in container.find_all(tags):
            if self._is_child_of_processed(element): continue
            
            text = clean_text(element.get_text())
            if not text and element.name != 'table': continue
            
            tag = element.name

            if tag == 'h2':
                if current_chunk_content:
                    self.big_chunks.append({
                        "big_chunk_index": self.chunk_index,
                        "content_name": current_section_name,
                        "small_chunks": current_chunk_content.copy()
                    })
                    self.chunk_index += 1
                elif pre_h2_content:
                    self.big_chunks.append({
                        "big_chunk_index": self.chunk_index,
                        "content_name": "Introduction",
                        "small_chunks": pre_h2_content.copy()
                    })
                    self.chunk_index += 1
                
                current_chunk_content = [f"H2: {text}"]
                current_section_name = text
                self._mark_processed(element)
                continue

            formatted = None
            if 'warning' in str(element.get('class', [])).lower() or '⚠️' in text:
                formatted = f"WARNING: {text}"
            elif tag in ['h3', 'h4']: formatted = f"{tag.upper()}: {text}"
            elif tag == 'p': formatted = f"CONTENT: {text}"
            elif tag in ['ul', 'ol']:
                items = [li.get_text(strip=True) for li in element.find_all('li')]
                if items: formatted = f"LIST: {' // '.join(items)}"
            elif tag == 'dl':
                items = [f"{dt.get_text().strip()}: {dd.get_text().strip()}" for dt, dd in zip(element.find_all('dt'), element.find_all('dd'))]
                if items: formatted = f"DEF_LIST: {' // '.join(items)}"
            elif tag == 'table':
                rows = [" | ".join([c.get_text(strip=True) for c in r.find_all(['td','th'])]) for r in element.find_all('tr')]
                if rows: formatted = f"TABLE: {' // '.join(rows)}"
            
            if formatted:
                self._mark_processed(element)
                if current_section_name == "Main Content": pre_h2_content.append(formatted)
                else: current_chunk_content.append(formatted)

        if current_chunk_content:
            self.big_chunks.append({
                "big_chunk_index": self.chunk_index,
                "content_name": current_section_name,
                "small_chunks": current_chunk_content
            })
            self.chunk_index += 1
        elif pre_h2_content:
            self.big_chunks.append({
                "big_chunk_index": self.chunk_index,
                "content_name": "Introduction",
                "small_chunks": pre_h2_content
            })
            self.chunk_index += 1

    def _is_child_of_processed(self, element) -> bool:
        for parent in element.parents:
            if self._get_element_id(parent) in self.processed_elements: return True
        return False

    def _get_element_id(self, element) -> str:
        return f"{element.name}:{hash(element.get_text()[:50])}"

    def _mark_processed(self, element):
        self.processed_elements.add(self._get_element_id(element))
        for child in element.find_all():
            self.processed_elements.add(self._get_element_id(child))

    def _create_final_json(self) -> str:
        if not self.big_chunks:
            self.big_chunks = [{"big_chunk_index": 1, "content_name": "Empty", "small_chunks": ["No content found"]}]
        return json.dumps({"big_chunks": self.big_chunks}, indent=2, ensure_ascii=False)

def extract_html_content(html: str, casino_mode: bool = False) -> Tuple[bool, Optional[str], Optional[str]]:
    # Smart Switch
    if 'doc-content' in html or 'google.com/url' in html or ('<style type="text/css">' in html and '.c1{' in html):
        safe_log("Extractor: Detected Google Doc format. Using Scavenger Extractor.")
        return extract_google_doc_content(html)
    
    extractor = HTMLContentExtractor()
    return extractor.extract_content(html, casino_mode)
