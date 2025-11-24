#!/usr/bin/env python3
"""
HTML Content Extractor - V5 (Global Context Backpack)
Feature: Creates a 'Chunk 0' containing global safety context (Licenses, Warnings, Restrictions)
so the AI doesn't 'forget' them when analyzing specific sections.
"""

import json
import re
from bs4 import BeautifulSoup, Comment
from typing import Tuple, Optional, List, Set, Dict
from utils.helpers import safe_log, clean_text
from core.google_doc_extractor import extract_google_doc_content

class HTMLContentExtractor:
    
    def __init__(self):
        self.processed_elements: Set[str] = set()
        self.big_chunks = []
        self.chunk_index = 1 # We start at 1, but Backpack will be 0
    
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
                safe_log("Extractor: Running Context-Aware Casino Extraction")
                
                # --- STEP 0: THE BACKPACK (New) ---
                # Grab global context (Footer warnings, Intro restrictions) before we delete anything
                self._extract_global_backpack(soup)

                # 1. Extract Metadata
                self._extract_metadata_chunk(soup)
                
                # 2. Extract FAQ
                faq_chunk = self._extract_faq_chunk(soup)
                
                # 3. Clean Noise
                self._remove_casino_widgets(soup)
                
                # 4. Main Content Scan
                main_wrapper = soup.find('section', class_='wrapper')
                if main_wrapper:
                    self._extract_with_direct_chunking(main_wrapper)
                else:
                    safe_log("Extractor: 'wrapper' missing, scanning cleaned body", "WARNING")
                    body = soup.find('body') or soup
                    self._extract_with_direct_chunking(body)
                
                # 5. Append FAQ
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
        for tag in soup(['script', 'style', 'nav', 'aside', 'noscript', 'iframe', 'svg', 'button']):
            tag.decompose()
        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()

    def _extract_global_backpack(self, soup: BeautifulSoup):
        """
        Scans the entire page for 'Global Context' signals (Licenses, Warnings, Restrictions).
        Creates a 'Chunk 0' that the AI MUST read first.
        """
        context_items = []
        
        # 1. Scan for LICENSE info (usually in footer)
        # We look for common regulator keywords
        text_content = soup.get_text(" ", strip=True)
        license_patterns = [
            r'UKGC', r'Gambling Commission', r'Malta Gaming Authority', r'MGA/', 
            r'Curacao', r'Licen[cs]e', r'Regulated by'
        ]
        for pattern in license_patterns:
            # Find the sentence containing this keyword
            matches = re.findall(r'([^.]*?' + pattern + r'[^.]*\.)', text_content, re.IGNORECASE)
            for match in matches[:2]: # Keep it brief
                if len(match) < 300:
                    context_items.append(f"LICENSE_CONTEXT: {clean_text(match)}")

        # 2. Scan for RESTRICTIONS (Intro/Terms)
        # Look for "Not available", "Restricted", "Players from"
        restriction_patterns = [r'not available in', r'restricted countr', r'players from']
        for pattern in restriction_patterns:
            matches = re.findall(r'([^.]*?' + pattern + r'[^.]*\.)', text_content, re.IGNORECASE)
            for match in matches[:3]:
                context_items.append(f"RESTRICTION_CONTEXT: {clean_text(match)}")

        # 3. Scan for WARNINGS (18+, GambleAware)
        # We look for specific safety markers
        if "18+" in text_content: context_items.append("SAFETY_MARKER: '18+' found on page.")
        if "GambleAware" in text_content or "GamCare" in text_content: context_items.append("SAFETY_MARKER: RG Help Links found on page.")
        if "Play Responsibly" in text_content: context_items.append("SAFETY_MARKER: 'Play Responsibly' msg found.")

        # 4. Grab Intro Text High-Level (redundant to metadata but good for context)
        intro = soup.find(attrs={'data-qa': re.compile(r'templateIntro', re.I)})
        if intro:
            context_items.append(f"PAGE_INTRO_SUMMARY: {clean_text(intro.get_text())[:500]}...")

        # CREATE THE BACKPACK CHUNK
        if context_items:
            # Remove duplicates
            context_items = list(set(context_items))
            self.big_chunks.append({
                "big_chunk_index": 0,  # Special Index 0
                "content_name": "GLOBAL PAGE CONTEXT (Read First)",
                "small_chunks": context_items
            })
            # Note: We do NOT increment chunk_index here, so the first real content is Chunk 1

    def _remove_casino_widgets(self, soup: BeautifulSoup):
        noise_patterns = [
            re.compile(r'^blockCasinoInfo'),
            re.compile(r'^blockCasinoRating'),
            re.compile(r'^blockCasinoPopularSlots'),
            re.compile(r'^blockCasinoDetails'),
            re.compile(r'^templateAuthor'),
            re.compile(r'^blockCasinoInfoSticky'),
            re.compile(r'^templateFooter') 
        ]
        for pattern in noise_patterns:
            for element in soup.find_all(attrs={'data-qa': pattern}):
                element.decompose()

    def _extract_metadata_chunk(self, soup: BeautifulSoup):
        metadata_items = []
        intro_container = soup.find(attrs={'data-qa': re.compile(r'templateIntro', re.I)})
        search_area = intro_container if intro_container else soup
        
        h1 = search_area.find('h1')
        if h1:
            metadata_items.append(f"H1: {clean_text(h1.get_text())}")
            h1.decompose()

        subtitle = search_area.select_one('.sub-title')
        if subtitle:
            metadata_items.append(f"SUBTITLE: {clean_text(subtitle.get_text())}")
            subtitle.decompose()

        lead = search_area.select_one('.lead')
        if lead:
            metadata_items.append(f"LEAD: {clean_text(lead.get_text())}")
            lead.decompose()

        summary_block = soup.find(attrs={'data-qa': 'blockCasinoSummary'})
        if summary_block:
            h2 = summary_block.find('h2')
            if h2: h2.decompose()
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
        faq_section = soup.find(attrs={'data-qa': 'templateFAQ'})
        if not faq_section: return None
        faq_items = []
        questions = faq_section.find_all(attrs={'itemtype': re.compile(r'schema\.org/Question')})
        if not questions: questions = faq_section.find_all(class_='card')

        for q in questions:
            q_el = q.find(attrs={'itemprop': 'name'}) or q.find('button')
            q_text = clean_text(q_el.get_text()) if q_el else ""
            
            a_container = q.find(attrs={'itemprop': 'acceptedAnswer'})
            if a_container:
                a_el = a_container.find(attrs={'itemprop': 'text'}) or a_container
                a_text = clean_text(a_el.get_text())
            else:
                collapse = q.find(class_='collapse')
                a_text = clean_text(collapse.get_text()) if collapse else ""

            if q_text and a_text:
                faq_items.append(f"FAQ_Q: {q_text} // FAQ_A: {a_text}")
        
        faq_section.decompose()
        if faq_items:
            return {"content_name": "Frequently Asked Questions", "small_chunks": faq_items}
        return None

    def _extract_with_direct_chunking(self, container):
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
    """
    Smart Switch: Detects if content is a Google Doc Export or a Web Scrape.
    """
    # Detection Logic: Google Docs usually have this specific class in the body
    if 'doc-content' in html or 'google-doc' in html or 'c1' in html[:500] and 'c2' in html[:500]:
        safe_log("Extractor: Detected Google Doc HTML format. Switching to GoogleDocExtractor.")
        return extract_google_doc_content(html)
    
    # Default to the Web Extractor (Surgical/Generic)
    extractor = HTMLContentExtractor()
    return extractor.extract_content(html, casino_mode)
