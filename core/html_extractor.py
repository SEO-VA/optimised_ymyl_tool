#!/usr/bin/env python3
"""
HTML Content Extractor - Surgical Edition
Targeted extraction for Casino Reviews using 'data-qa' selectors.
Robust across languages and layout changes.
"""

import json
import re
from bs4 import BeautifulSoup, Comment
# --- FIX: Added 'Dict' to the imports below ---
from typing import Tuple, Optional, List, Set, Dict
from utils.helpers import safe_log, clean_text

class HTMLContentExtractor:
    """Extracts structured content using surgical selectors then generic chunking."""
    
    def __init__(self):
        self.processed_elements: Set[str] = set()
        self.big_chunks = []
        self.chunk_index = 1
    
    def extract_content(self, html_content: str) -> Tuple[bool, Optional[str], Optional[str]]:
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            self._preprocess_soup(soup)
            
            # Reset state
            self.processed_elements.clear()
            self.big_chunks = []
            self.chunk_index = 1
            
            # 1. SURGICAL EXTRACTION: Metadata (Chunk 1)
            self._extract_metadata_chunk(soup)
            
            # 2. SURGICAL EXTRACTION: FAQs (Saved for end, but extracted now to remove from tree)
            faq_chunk = self._extract_faq_chunk(soup)
            
            # 3. MAIN CONTENT: The "Wrapper" Section
            # We specifically look for the unique section class="wrapper"
            main_wrapper = soup.find('section', class_='wrapper')
            
            if main_wrapper:
                # Run generic H2 chunking ONLY on the wrapper
                self._extract_with_direct_chunking(main_wrapper)
            else:
                # Fallback: If wrapper missing, run on body but skip what we already found
                safe_log("Extractor: 'wrapper' section not found, falling back to full body scan", "WARNING")
                body = soup.find('body') or soup
                self._extract_with_direct_chunking(body)
                
            # 4. Append FAQ at the end if found
            if faq_chunk:
                faq_chunk["big_chunk_index"] = self.chunk_index
                self.big_chunks.append(faq_chunk)
                self.chunk_index += 1
            
            # Finalize
            return True, self._create_final_json(), None
            
        except Exception as e:
            return False, None, f"HTML parsing error: {str(e)}"

    def _preprocess_soup(self, soup: BeautifulSoup):
        """Remove noise elements."""
        for tag in soup(['script', 'style', 'nav', 'footer', 'aside', 'header', 'noscript', 'iframe', 'svg']):
            tag.decompose()
        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()

    def _extract_metadata_chunk(self, soup: BeautifulSoup):
        """Extracts H1, Subtitle, Lead, and Summary into Chunk #1"""
        metadata_items = []
        
        # H1
        h1 = soup.find('h1')
        if h1:
            metadata_items.append(f"H1: {clean_text(h1.get_text())}")
            h1.decompose() # Remove from tree so we don't read it again

        # Subtitle (span.sub-title.d-block)
        subtitle = soup.select_one('span.sub-title.d-block')
        if subtitle:
            metadata_items.append(f"SUBTITLE: {clean_text(subtitle.get_text())}")
            subtitle.decompose()

        # Lead (p.lead)
        lead = soup.select_one('p.lead')
        if lead:
            metadata_items.append(f"LEAD: {clean_text(lead.get_text())}")
            lead.decompose()

        # Summary (data-qa="blockCasinoSummary")
        summary_section = soup.find(attrs={'data-qa': 'blockCasinoSummary'})
        if summary_section:
            text = clean_text(summary_section.get_text())
            metadata_items.append(f"SUMMARY: {text}")
            summary_section.decompose()

        # If we found anything, create the first Big Chunk
        if metadata_items:
            self.big_chunks.append({
                "big_chunk_index": self.chunk_index,
                "content_name": "Page Metadata & Summary",
                "small_chunks": metadata_items
            })
            self.chunk_index += 1

    def _extract_faq_chunk(self, soup: BeautifulSoup) -> Optional[Dict]:
        """Extracts FAQs using data-qa="templateFAQ". Returns chunk dict or None."""
        faq_section = soup.find(attrs={'data-qa': 'templateFAQ'})
        if not faq_section:
            return None
            
        faq_items = []
        # Find questions using Schema.org attributes (Language Agnostic)
        questions = faq_section.find_all(attrs={'itemprop': 'mainEntity'})
        
        if not questions:
            # Fallback: Look for the buttons and collapses if schema is missing
            questions = faq_section.find_all('div', class_='col-md-6')

        for q in questions:
            # Try to find name/text
            q_text_el = q.find(attrs={'itemprop': 'name'}) or q.find('button')
            a_text_el = q.find(attrs={'itemprop': 'acceptedAnswer'}) or q.find('div', class_='collapse')
            
            q_str = clean_text(q_text_el.get_text()) if q_text_el else "Unknown Q"
            a_str = clean_text(a_text_el.get_text()) if a_text_el else "Unknown A"
            
            if q_str and a_str:
                faq_items.append(f"FAQ_Q: {q_str} // FAQ_A: {a_str}")
        
        # Remove from tree so generic chunker doesn't eat it
        faq_section.decompose()
        
        if faq_items:
            return {
                "content_name": "Frequently Asked Questions",
                "small_chunks": faq_items
            }
        return None

    def _extract_with_direct_chunking(self, container_element):
        """
        Scans the remaining container (Main Content) for H2s and paragraphs.
        Same logic as before, but scoped to a specific container.
        """
        current_chunk_content = []
        pre_h2_content = []
        
        current_section_name = "Main Content Intro"
        
        # Tags to capture
        tags = ['h2', 'h3', 'h4', 'p', 'table', 'ul', 'ol']
        
        for element in container_element.find_all(tags):
            # Helper to avoid processing nested elements twice
            if self._is_child_of_processed(element): continue
            
            text = clean_text(element.get_text())
            if not text and element.name != 'table': continue
            
            tag = element.name
            formatted = None

            # Format elements
            if tag == 'h2':
                # Start new chunk
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

            # Formatting logic (same as previous version)
            if 'warning' in str(element.get('class', [])).lower() or '⚠️' in text:
                formatted = f"WARNING: {text}"
            elif tag in ['h3', 'h4']:
                formatted = f"{tag.upper()}: {text}"
            elif tag == 'p':
                formatted = f"CONTENT: {text}"
            elif tag in ['ul', 'ol']:
                items = [li.get_text(strip=True) for li in element.find_all('li')]
                if items: formatted = f"LIST: {' // '.join(items)}"
            elif tag == 'table':
                rows = [" | ".join([cell.get_text(strip=True) for cell in row.find_all(['td', 'th'])]) 
                        for row in element.find_all('tr')]
                if rows: formatted = f"TABLE: {' // '.join(rows)}"
            
            if formatted:
                self._mark_processed(element)
                if current_section_name == "Main Content Intro":
                    pre_h2_content.append(formatted)
                else:
                    current_chunk_content.append(formatted)

        # Flush final chunk
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
        """Check if this element is inside a table/list we already extracted fully."""
        for parent in element.parents:
            if self._get_element_id(parent) in self.processed_elements:
                return True
        return False

    def _get_element_id(self, element) -> str:
        return f"{element.name}:{hash(element.get_text()[:50])}"

    def _mark_processed(self, element):
        self.processed_elements.add(self._get_element_id(element))
        # Also mark all children
        for child in element.find_all():
            self.processed_elements.add(self._get_element_id(child))

    def _create_final_json(self) -> str:
        if not self.big_chunks:
            self.big_chunks = [{"big_chunk_index": 1, "content_name": "Empty", "small_chunks": ["No content found"]}]
        return json.dumps({"big_chunks": self.big_chunks}, indent=2, ensure_ascii=False)

# Convenience function
def extract_html_content(html: str) -> Tuple[bool, Optional[str], Optional[str]]:
    extractor = HTMLContentExtractor()
    return extractor.extract_content(html)
