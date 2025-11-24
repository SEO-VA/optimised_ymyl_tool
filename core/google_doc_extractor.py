#!/usr/bin/env python3
"""
Google Doc Extractor - The "Scavenger Hunt" Edition
Designed for unstructured HTML exports from Google Docs.
Hunts for metadata, visual headers, and safety context regardless of layout or language.
"""

import re
import json
from bs4 import BeautifulSoup, NavigableString, Tag
from typing import Tuple, Optional, List, Dict, Set
from utils.helpers import safe_log, clean_text

class GoogleDocExtractor:
    
    def __init__(self):
        self.big_chunks = []
        self.chunk_index = 1
        
        # 1. Metadata Keys (Case Insensitive Hunting)
        self.metadata_keys = {
            'h1': ['h1', 'title'],
            'subtitle': ['subtitle', 'sub title', 'sub-title'],
            'lead': ['lead', 'lead text', 'intro'],
            'meta_title': ['mt', 'meta title', 'meta_title'],
            'meta_desc': ['md', 'meta description', 'meta_desc']
        }
        self.found_metadata = {}

    def extract_content(self, html_content: str) -> Tuple[bool, Optional[str], Optional[str]]:
        try:
            # Pre-clean
            html_content = re.sub(r'\[email&#160;protected\]', 'EMAIL_HIDDEN', html_content)
            
            soup = BeautifulSoup(html_content, 'html.parser')
            self._remove_noise(soup)
            
            # 2. SCAVENGER HUNT: Metadata (Top or Bottom)
            self._hunt_for_metadata(soup)
            
            # 3. SCAVENGER HUNT: Global Context Backpack
            # Licenses, Warnings (18+), Restrictions - scans full text
            self._extract_global_backpack(soup)

            # 4. TRANSFORM: Visual to Semantic
            # Convert "Bold Paragraphs" to H2, Flatten Tables
            self._normalize_structure(soup)
            
            # 5. DETECTIVE: FAQ Extraction
            # Looks for specific FAQ patterns (Lists, Headers, or Text blocks)
            faq_chunk = self._extract_flexible_faq(soup)

            # 6. CHUNKING: Standard Linear Scan
            self._chunk_linear_content(soup)
            
            # 7. Append FAQ at the end
            if faq_chunk:
                faq_chunk["big_chunk_index"] = self.chunk_index
                self.big_chunks.append(faq_chunk)
                self.chunk_index += 1

            return True, self._create_final_json(), None

        except Exception as e:
            return False, None, f"Google Doc parsing error: {str(e)}"

    def _remove_noise(self, soup: BeautifulSoup):
        """Remove CSS, Scripts, and Google Doc comments."""
        for tag in soup(['script', 'style', 'meta', 'title', 'head']):
            tag.decompose()
        
        # Remove empty paragraphs
        for p in soup.find_all('p'):
            if not p.get_text(strip=True):
                p.decompose()

    def _hunt_for_metadata(self, soup: BeautifulSoup):
        """
        Scans paragraphs/table cells for keys like 'Lead Text:', 'MT:', 'H1:'.
        Extracts value and removes the element.
        """
        all_tags = soup.find_all(['p', 'li', 'td', 'h1', 'h2', 'h3'])
        metadata_chunk_items = []

        for tag in all_tags:
            text = clean_text(tag.get_text())
            if not text: continue
            
            matched_key = None
            clean_value = None
            
            # Pattern: Start of string, case insensitive key, optional colon
            for meta_type, keywords in self.metadata_keys.items():
                for keyword in keywords:
                    # Regex: ^(Key)(:| |$)(Value)
                    pattern = r'^' + re.escape(keyword) + r'[:\s]+(.*)'
                    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
                    
                    if match:
                        # Safety: Short keys like "MT" must be followed by colon or newline
                        if len(keyword) < 3 and ':' not in text[:5]:
                            continue
                            
                        value = match.group(1).strip()
                        if value:
                            matched_key = meta_type
                            clean_value = value
                            break
                if matched_key: break
            
            if matched_key and matched_key not in self.found_metadata:
                label = matched_key.upper().replace('_', ' ')
                self.found_metadata[matched_key] = clean_value
                metadata_chunk_items.append(f"{label}: {clean_value}")
                tag.decompose()

        # Fallback: If H1 not found by key, take first H1 tag
        if 'h1' not in self.found_metadata:
            h1_tag = soup.find('h1')
            if h1_tag:
                val = clean_text(h1_tag.get_text())
                metadata_chunk_items.insert(0, f"H1: {val}")
                h1_tag.decompose()

        if metadata_chunk_items:
            self.big_chunks.append({
                "big_chunk_index": self.chunk_index,
                "content_name": "Metadata & Summary",
                "small_chunks": metadata_chunk_items
            })
            self.chunk_index += 1

    def _extract_global_backpack(self, soup: BeautifulSoup):
        """Create the Global Context Backpack (Chunk 0)."""
        context_items = []
        full_text = soup.get_text(" ", strip=True)

        # 1. Licenses (Broad keywords)
        lic_keywords = ['UKGC', 'MGA', 'Curacao', 'License', 'Licencja', 'Regulated', 'Commission']
        for kw in lic_keywords:
            matches = re.findall(r'([^.]*?' + kw + r'[^.]*\.)', full_text, re.IGNORECASE)
            for m in matches[:2]: context_items.append(f"LICENSE_CTX: {clean_text(m)}")

        # 2. Warnings (Emoji search is most reliable for Docs)
        if '⚠️' in full_text or '18+' in full_text:
            context_items.append("SAFETY_CTX: Risk Warnings found in document.")

        if context_items:
            self.big_chunks.append({
                "big_chunk_index": 0,
                "content_name": "GLOBAL CONTEXT",
                "small_chunks": list(set(context_items))
            })

    def _normalize_structure(self, soup: BeautifulSoup):
        """
        1. Convert Bold Paragraphs -> H2
        2. Flatten Tables -> Text
        """
        # 1. Visual Headers
        for p in soup.find_all('p'):
            text = clean_text(p.get_text())
            if not text or len(text) > 100: continue
            
            # Check for bold style (span style="font-weight:700" or <b>)
            is_bold = False
            if p.find(['b', 'strong']): is_bold = True
            if 'font-weight' in str(p).lower() and ('700' in str(p) or 'bold' in str(p)): is_bold = True
            
            # If bold and short and no end punctuation -> H2
            if is_bold and not text.endswith(('.', '!', '?')):
                p.name = 'h2'

        # 2. Flatten Tables
        for table in soup.find_all('table'):
            rows_text = []
            for tr in table.find_all('tr'):
                cells = [clean_text(td.get_text()) for td in tr.find_all('td')]
                cells = [c for c in cells if c]
                if cells:
                    rows_text.append(" | ".join(cells))
            
            # Replace table with P
            if rows_text:
                new_p = soup.new_tag("p")
                new_p.string = "TABLE_DATA: " + " // ".join(rows_text)
                table.replace_with(new_p)
            else:
                table.decompose()

    def _extract_flexible_faq(self, soup: BeautifulSoup) -> Optional[Dict]:
        """
        Finds FAQs via Headers ("FAQ"), Lists, or Pattern Matching.
        """
        faq_items = []
        
        # 1. Find FAQ Header
        faq_header = None
        for header in soup.find_all(['h1', 'h2', 'h3', 'p']):
            txt = clean_text(header.get_text()).upper()
            # "FAQ" or "KKK" (Estonian) or "PYTANIA" (Polish)
            if 'FAQ' in txt or 'KKK' in txt or 'PYTANIA' in txt:
                if len(txt) < 60: 
                    faq_header = header
                    break
        
        if not faq_header: return None

        # 2. Scan content AFTER header
        # Slotoro uses <ol><li>Question</li></ol><p>Answer</p>
        # Chanz uses Text Block Q? A.
        
        current = faq_header.next_sibling
        raw_pairs = []
        
        while current:
            if isinstance(current, Tag):
                # Stop if new section
                if current.name in ['h1', 'h2'] and clean_text(current.get_text()) != "": 
                    break
                
                # List Item (Slotoro style)
                if current.name in ['ul', 'ol']:
                    for li in current.find_all('li'):
                        q = clean_text(li.get_text())
                        raw_pairs.append(f"Q: {q}")
                
                # Paragraph (Answer or Chanz style)
                elif current.name == 'p':
                    txt = clean_text(current.get_text())
                    if '?' in txt and len(txt) < 150:
                        raw_pairs.append(f"Q: {txt}") # Likely a question line
                    else:
                        raw_pairs.append(f"A: {txt}") # Likely an answer
            
            current = current.next_sibling

        # Reassemble pairs
        # We look for Q followed by A
        curr_q = ""
        for line in raw_pairs:
            if line.startswith("Q:"):
                curr_q = line[3:]
            elif line.startswith("A:") and curr_q:
                faq_items.append(f"FAQ_Q: {curr_q} // FAQ_A: {line[3:]}")
                curr_q = ""

        faq_header.decompose() # Cleanup
        
        if faq_items:
            return {"content_name": "Frequently Asked Questions", "small_chunks": faq_items}
        return None

    def _chunk_linear_content(self, soup: BeautifulSoup):
        """Groups content by H2 headers."""
        current_chunk = []
        current_title = "Main Content"
        
        # Flatten the tree to a list of tags
        # We search for the 'body' or top div
        root = soup.find('body') or soup
        
        # We iterate all direct children (or all tags if flat)
        all_tags = root.find_all(['p', 'h2', 'h3', 'ul', 'ol'])
        
        for elem in all_tags:
            text = clean_text(elem.get_text())
            if not text: continue
            
            # Skip if this element was inside a table we already flattened
            if elem.find_parent('table'): continue

            if elem.name in ['h2', 'h3']:
                # Flush
                if current_chunk:
                    self.big_chunks.append({
                        "big_chunk_index": self.chunk_index,
                        "content_name": current_title,
                        "small_chunks": current_chunk
                    })
                    self.chunk_index += 1
                    current_chunk = []
                current_title = text
                current_chunk.append(f"HEADER: {text}")
            
            elif elem.name in ['ul', 'ol']:
                items = [clean_text(li.get_text()) for li in elem.find_all('li')]
                if items: current_chunk.append(f"LIST: {' // '.join(items)}")
            
            else:
                # Paragraphs
                prefix = "CONTENT"
                if '⚠️' in text or 'WARNING' in text or 'UWAGA' in text:
                    prefix = "WARNING"
                current_chunk.append(f"{prefix}: {text}")

        # Final Flush
        if current_chunk:
            self.big_chunks.append({
                "big_chunk_index": self.chunk_index,
                "content_name": current_title,
                "small_chunks": current_chunk
            })

    def _create_final_json(self) -> str:
        if not self.big_chunks:
            self.big_chunks = [{"big_chunk_index": 1, "content_name": "Empty", "small_chunks": ["No content found"]}]
        return json.dumps({"big_chunks": self.big_chunks}, indent=2, ensure_ascii=False)

def extract_google_doc_content(html_content: str) -> Tuple[bool, Optional[str], Optional[str]]:
    extractor = GoogleDocExtractor()
    return extractor.extract_content(html_content)
