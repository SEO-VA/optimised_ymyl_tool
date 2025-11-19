#!/usr/bin/env python3
"""
HTML Content Extractor - Surgical Edition V2
Targeted extraction for Casino Reviews.
Focuses on editorial content while aggressively removing widget noise.
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
            soup = BeautifulSoup(html_content, 'html.parser')
            self._preprocess_soup(soup)
            
            # Reset state
            self.processed_elements.clear()
            self.big_chunks = []
            self.chunk_index = 1
            
            if casino_mode:
                # --- CASINO MODE STRATEGY ---
                safe_log("Extractor: Running Casino Mode Extraction")
                
                # 1. Extract High-Value Metadata (Intro & Summary)
                self._extract_metadata_chunk(soup)
                
                # 2. Extract FAQs (and remove them from DOM)
                faq_chunk = self._extract_faq_chunk(soup)
                
                # 3. NOISE REMOVAL (Crucial Step)
                # We remove widgets (Ratings, Slots, Details) so they don't appear in the main scan
                self._remove_casino_widgets(soup)
                
                # 4. Main Content Scan
                # We look for the specific 'wrapper' section that holds the review text
                main_wrapper = soup.find('section', class_='wrapper')
                
                if main_wrapper:
                    self._extract_with_direct_chunking(main_wrapper)
                else:
                    # Fallback: Scan body, but since we removed widgets, it should be cleaner
                    safe_log("Extractor: 'wrapper' section not found, scanning cleaned body", "WARNING")
                    body = soup.find('body') or soup
                    self._extract_with_direct_chunking(body)
                
                # 5. Add FAQ at the end
                if faq_chunk:
                    faq_chunk["big_chunk_index"] = self.chunk_index
                    self.big_chunks.append(faq_chunk)
                    self.chunk_index += 1
                    
            else:
                # --- GENERIC MODE STRATEGY ---
                safe_log("Extractor: Running Generic Extraction")
                body = soup.find('body') or soup
                self._extract_with_direct_chunking(body)
            
            return True, self._create_final_json(), None
            
        except Exception as e:
            return False, None, f"HTML parsing error: {str(e)}"

    def _preprocess_soup(self, soup: BeautifulSoup):
        """Standard cleanup of invisible elements."""
        for tag in soup(['script', 'style', 'nav', 'footer', 'aside', 'header', 'noscript', 'iframe', 'svg']):
            tag.decompose()
        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()

    def _remove_casino_widgets(self, soup: BeautifulSoup):
        """
        Aggressively removes non-editorial widgets based on data-qa attributes.
        This ensures lists of slots, technical details, and ratings don't pollute the output.
        """
        selectors_to_remove = [
            'blockCasinoInfo',          # Top sticky header/info
            'blockCasinoRatingOverall', # The "77/100" Rating Table
            'blockCasinoPopularSlots',  # The "Most Popular Slots" list
            'blockCasinoDetails',       # The "Details" table (Licenses, Launched, etc)
            'templateAuthorCard',       # Author bio (optional, remove if considered noise)
            'blockCasinoInfoSticky'     # Sticky footer/header
        ]
        
        for qa_id in selectors_to_remove:
            # Find elements where data-qa starts with or equals the ID
            for element in soup.find_all(attrs={'data-qa': re.compile(f'^{qa_id}')}):
                element.decompose()

    def _extract_metadata_chunk(self, soup: BeautifulSoup):
        """Extracts H1, Subtitle, Lead, and Summary."""
        metadata_items = []
        
        # Target the Intro container specifically
        intro_container = soup.find(attrs={'data-qa': re.compile('templateIntro')})
        
        # H1
        # Look inside intro container first, then global
        h1 = intro_container.find('h1') if intro_container else soup.find('h1')
        if h1:
            metadata_items.append(f"H1: {clean_text(h1.get_text())}")
            h1.decompose()

        # Subtitle (class="sub-title")
        subtitle = soup.select_one('.sub-title')
        if subtitle:
            metadata_items.append(f"SUBTITLE: {clean_text(subtitle.get_text())}")
            subtitle.decompose()

        # Lead (class="lead")
        lead = soup.select_one('.lead')
        if lead:
            metadata_items.append(f"LEAD: {clean_text(lead.get_text())}")
            lead.decompose()

        # Summary (data-qa="blockCasinoSummary")
        # We need to extract the text from the specific div inside this block
        summary_block = soup.find(attrs={'data-qa': 'blockCasinoSummary'})
        if summary_block:
            # The summary text is usually in the col-lg-8 div, or we just take the whole text
            # Filtering out the "H2 Summary" title to avoid duplication
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
        """Extracts FAQs using robust Schema selectors."""
        faq_section = soup.find(attrs={'data-qa': 'templateFAQ'})
        if not faq_section: return None
            
        faq_items = []
        
        # Use Schema.org Question objects
        questions = faq_section.find_all(attrs={'itemprop': 'mainEntity', 'itemtype': re.compile('Question')})
        
        for q in questions:
            # Question Text
            q_text_el = q.find(attrs={'itemprop': 'name'})
            if not q_text_el: q_text_el = q.find('button')
            
            # Answer Text
            a_container = q.find(attrs={'itemprop': 'acceptedAnswer'})
            a_text_el = None
            if a_container:
                # Look for nested itemprop="text" (Crucial fix from your feedback)
                a_text_el = a_container.find(attrs={'itemprop': 'text'})
                if not a_text_el: a_text_el = a_container # Fallback to container
            
            q_str = clean_text(q_text_el.get_text()) if q_text_el else "Unknown Q"
            a_str = clean_text(a_text_el.get_text()) if a_text_el else "Unknown A"
            
            if q_str and a_str:
                faq_items.append(f"FAQ_Q: {q_str} // FAQ_A: {a_str}")
        
        # Remove from DOM so generic chunker doesn't see it
        faq_section.decompose()
        
        if faq_items:
            return {
                "content_name": "Frequently Asked Questions",
                "small_chunks": faq_items
            }
        return None

    def _extract_with_direct_chunking(self, container):
        """Generic H2-based chunking logic."""
        current_chunk_content = []
        pre_h2_content = []
        current_section_name = "Main Content Intro"
        
        tags = ['h2', 'h3', 'h4', 'p', 'table', 'ul', 'ol']
        
        for element in container.find_all(tags):
            if self._is_child_of_processed(element): continue
            
            text = clean_text(element.get_text())
            if not text and element.name != 'table': continue
            
            tag = element.name
            formatted = None

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
                if current_section_name == "Main Content Intro": pre_h2_content.append(formatted)
                else: current_chunk_content.append(formatted)

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
