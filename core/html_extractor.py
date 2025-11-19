#!/usr/bin/env python3
"""
HTML Content Extractor - Surgical Edition V3 (Final Fix)
Robust noise removal and precise targeting for Casino Review structure.
"""

import json
import re
from bs4 import BeautifulSoup, Comment
from typing import Tuple, Optional, List, Set, Dict
from utils.helpers import safe_log, clean_text

class HTMLContentExtractor:
    
    def __init__(self):
        self.processed_elements: Set[str] = set()
        self.big_chunks = []
        self.chunk_index = 1
    
    def extract_content(self, html_content: str, casino_mode: bool = False) -> Tuple[bool, Optional[str], Optional[str]]:
        try:
            # Clean up messy HTML before parsing (remove Cloudflare email protection)
            html_content = re.sub(r'\[email&#160;protected\]', 'EMAIL_HIDDEN', html_content)
            
            soup = BeautifulSoup(html_content, 'html.parser')
            self._preprocess_soup(soup)
            
            # Reset state
            self.processed_elements.clear()
            self.big_chunks = []
            self.chunk_index = 1
            
            if casino_mode:
                safe_log("Extractor: Running Surgical Casino Extraction")
                
                # 1. Extract Intro/Metadata (H1, Subtitle, Lead)
                # Targeted before noise removal to ensure we get the H1
                self._extract_metadata_chunk(soup)
                
                # 2. Extract FAQ (and remove from DOM)
                faq_chunk = self._extract_faq_chunk(soup)
                
                # 3. AGGRESSIVE NOISE REMOVAL
                # We specifically remove the widgets that polluted your previous output
                self._remove_casino_widgets(soup)
                
                # 4. Main Content Scan (The "wrapper" section)
                main_wrapper = soup.find('section', class_='wrapper')
                if main_wrapper:
                    self._extract_with_direct_chunking(main_wrapper)
                else:
                    safe_log("Extractor: Wrapper missing, scanning cleaned body", "WARNING")
                    body = soup.find('body') or soup
                    self._extract_with_direct_chunking(body)
                
                # 5. Append FAQ at the end
                if faq_chunk:
                    faq_chunk["big_chunk_index"] = self.chunk_index
                    self.big_chunks.append(faq_chunk)
                    self.chunk_index += 1
            
            else:
                # Generic Mode
                safe_log("Extractor: Running Generic Extraction")
                body = soup.find('body') or soup
                self._extract_with_direct_chunking(body)
            
            return True, self._create_final_json(), None
            
        except Exception as e:
            return False, None, f"HTML parsing error: {str(e)}"

    def _preprocess_soup(self, soup: BeautifulSoup):
        """Remove invisible elements."""
        for tag in soup(['script', 'style', 'nav', 'footer', 'aside', 'header', 'noscript', 'iframe', 'svg', 'button']):
            tag.decompose()
        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()

    def _remove_casino_widgets(self, soup: BeautifulSoup):
        """
        Removes specific widgets based on your provided JSON noise.
        """
        # Regex to match data-qa starting with specific strings
        noise_patterns = [
            re.compile(r'^blockCasinoInfo'),        # Top sticky header
            re.compile(r'^blockCasinoRating'),      # The "247bet Rating" widget
            re.compile(r'^blockCasinoPopularSlots'),# The "Most popular slots" widget
            re.compile(r'^blockCasinoDetails'),     # The "Details" table
            re.compile(r'^templateAuthor'),         # Author bio (optional)
            re.compile(r'^blockCasinoInfoSticky')   # Bottom sticky footer
        ]
        
        for pattern in noise_patterns:
            for element in soup.find_all(attrs={'data-qa': pattern}):
                element.decompose()

    def _extract_metadata_chunk(self, soup: BeautifulSoup):
        """Extracts H1, Subtitle, Lead, and Summary."""
        metadata_items = []
        
        # INTRO SECTION (H1, Subtitle, Lead)
        # Search for container with 'templateIntro' in data-qa
        intro_container = soup.find(attrs={'data-qa': re.compile(r'templateIntro', re.I)})
        
        search_area = intro_container if intro_container else soup
        
        # H1
        h1 = search_area.find('h1')
        if h1:
            metadata_items.append(f"H1: {clean_text(h1.get_text())}")
            h1.decompose() # Prevent re-reading

        # Subtitle (span class="sub-title")
        subtitle = search_area.select_one('.sub-title')
        if subtitle:
            metadata_items.append(f"SUBTITLE: {clean_text(subtitle.get_text())}")
            subtitle.decompose()

        # Lead (p class="lead")
        lead = search_area.select_one('.lead')
        if lead:
            metadata_items.append(f"LEAD: {clean_text(lead.get_text())}")
            lead.decompose()

        # SUMMARY SECTION (data-qa="blockCasinoSummary")
        # We look for the specific text div inside
        summary_block = soup.find(attrs={'data-qa': 'blockCasinoSummary'})
        if summary_block:
            # The summary text is usually in a div with col-lg-8, but text extraction is safer
            # We exclude the H2 "Summary" title
            h2 = summary_block.find('h2')
            if h2: h2.decompose()
            
            text = clean_text(summary_block.get_text())
            if text:
                metadata_items.append(f"SUMMARY: {text}")
            summary_block.decompose()

        if metadata_items:
            self.big_chunks.append({
                "big_chunk_index": self.chunk_index,
                "content_name": "Page Metadata & Summary",
                "small_chunks": metadata_items
            })
            self.chunk_index += 1

    def _extract_faq_chunk(self, soup: BeautifulSoup) -> Optional[Dict]:
        """Extracts FAQs using Schema.org Question/Answer objects."""
        faq_section = soup.find(attrs={'data-qa': 'templateFAQ'})
        if not faq_section: return None
            
        faq_items = []
        
        # Look for Schema Question objects
        questions = faq_section.find_all(attrs={'itemtype': re.compile(r'schema\.org/Question')})
        
        # Fallback: Look for cards if schema missing
        if not questions:
            questions = faq_section.find_all(class_='card')

        for q in questions:
            # Find Question Text
            # Priority: itemprop="name" -> button text -> any h3
            q_text = ""
            q_el = q.find(attrs={'itemprop': 'name'})
            if not q_el: q_el = q.find('button')
            if q_el: q_text = clean_text(q_el.get_text())
            
            # Find Answer Text
            # Priority: itemprop="text" inside Answer -> itemprop="acceptedAnswer"
            a_text = ""
            a_container = q.find(attrs={'itemtype': re.compile(r'schema\.org/Answer')})
            if a_container:
                a_el = a_container.find(attrs={'itemprop': 'text'})
                if not a_el: a_el = a_container
                a_text = clean_text(a_el.get_text())
            else:
                # Fallback for non-schema (look for collapse div)
                collapse = q.find(class_='collapse')
                if collapse: a_text = clean_text(collapse.get_text())

            if q_text and a_text:
                faq_items.append(f"FAQ_Q: {q_text} // FAQ_A: {a_text}")
        
        # Decompose to prevent generic scanner finding it
        faq_section.decompose()
        
        if faq_items:
            return {
                "content_name": "Frequently Asked Questions",
                "small_chunks": faq_items
            }
        return None

    def _extract_with_direct_chunking(self, container):
        """Generic H2-based chunking."""
        current_chunk_content = []
        pre_h2_content = []
        current_section_name = "Main Content"
        
        tags = ['h2', 'h3', 'h4', 'p', 'table', 'ul', 'ol']
        
        for element in container.find_all(tags):
            if self._is_child_of_processed(element): continue
            
            text = clean_text(element.get_text())
            if not text and element.name != 'table': continue
            
            tag = element.name
            formatted = None

            if tag == 'h2':
                # Save current chunk
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

            # Formatting
            if 'warning' in str(element.get('class', [])).lower() or '⚠️' in text:
                formatted = f"WARNING: {text}"
            elif tag in ['h3', 'h4']: formatted = f"{tag.upper()}: {text}"
            elif tag == 'p': formatted = f"CONTENT: {text}"
            elif tag in ['ul', 'ol']:
                items = [li.get_text(strip=True) for li in element.find_all('li')]
                if items: formatted = f"LIST: {' // '.join(items)}"
            elif tag == 'table':
                rows = [" | ".join([c.get_text(strip=True) for c in r.find_all(['td','th'])]) for r in element.find_all('tr')]
                if rows: formatted = f"TABLE: {' // '.join(rows)}"
            
            if formatted:
                self._mark_processed(element)
                if current_section_name == "Main Content":
                    pre_h2_content.append(formatted)
                else:
                    current_chunk_content.append(formatted)

        # Final Flush
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
    extractor = HTMLContentExtractor()
    return extractor.extract_content(html, casino_mode)
