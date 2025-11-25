#!/usr/bin/env python3
"""
Google Doc Extractor - The "Scavenger Hunt" Edition (No Backpack)
"""

import re
import json
from bs4 import BeautifulSoup, Tag
from typing import Tuple, Optional, Dict
from utils.helpers import safe_log, clean_text

class GoogleDocExtractor:
    
    def __init__(self):
        self.big_chunks = []
        self.chunk_index = 1
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
            html_content = re.sub(r'\[email&#160;protected\]', 'EMAIL_HIDDEN', html_content)
            
            soup = BeautifulSoup(html_content, 'html.parser')
            self._remove_noise(soup)
            
            # 2. Metadata Hunt
            self._hunt_for_metadata(soup)
            
            # 3. (BACKPACK REMOVED HERE)

            # 4. Normalize Structure
            self._normalize_structure(soup)
            
            # 5. FAQ Detective
            faq_chunk = self._extract_flexible_faq(soup)

            # 6. Standard Chunking
            self._chunk_linear_content(soup)
            
            # 7. Append FAQ
            if faq_chunk:
                faq_chunk["big_chunk_index"] = self.chunk_index
                self.big_chunks.append(faq_chunk)
                self.chunk_index += 1

            return True, self._create_final_json(), None

        except Exception as e:
            return False, None, f"Google Doc parsing error: {str(e)}"

    def _remove_noise(self, soup: BeautifulSoup):
        for tag in soup(['script', 'style', 'meta', 'title', 'head']):
            tag.decompose()
        for p in soup.find_all('p'):
            if not p.get_text(strip=True):
                p.decompose()

    def _hunt_for_metadata(self, soup: BeautifulSoup):
        all_tags = soup.find_all(['p', 'li', 'td', 'h1', 'h2', 'h3'])
        metadata_chunk_items = []

        for tag in all_tags:
            text = clean_text(tag.get_text())
            if not text: continue
            
            matched_key = None
            clean_value = None
            
            for meta_type, keywords in self.metadata_keys.items():
                for keyword in keywords:
                    pattern = r'^' + re.escape(keyword) + r'[:\s]+(.*)'
                    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
                    if match:
                        if len(keyword) < 3 and ':' not in text[:5]: continue
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

    def _normalize_structure(self, soup: BeautifulSoup):
        for p in soup.find_all('p'):
            text = clean_text(p.get_text())
            if not text or len(text) > 100: continue
            
            is_bold = False
            if p.find(['b', 'strong']): is_bold = True
            if 'font-weight' in str(p).lower() and ('700' in str(p) or 'bold' in str(p)): is_bold = True
            
            if is_bold and not text.endswith(('.', '!', '?')):
                p.name = 'h2'

        for table in soup.find_all('table'):
            rows_text = []
            for tr in table.find_all('tr'):
                cells = [clean_text(td.get_text()) for td in tr.find_all('td')]
                cells = [c for c in cells if c]
                if cells:
                    rows_text.append(" | ".join(cells))
            
            if rows_text:
                new_p = soup.new_tag("p")
                new_p.string = "TABLE_DATA: " + " // ".join(rows_text)
                table.replace_with(new_p)
            else:
                table.decompose()

    def _extract_flexible_faq(self, soup: BeautifulSoup) -> Optional[Dict]:
        faq_items = []
        faq_header = None
        
        for header in soup.find_all(['h1', 'h2', 'h3', 'p']):
            txt = clean_text(header.get_text()).upper()
            if 'FAQ' in txt or 'KKK' in txt or 'PYTANIA' in txt:
                if len(txt) < 60: 
                    faq_header = header
                    break
        
        if not faq_header: return None

        current = faq_header.next_sibling
        raw_pairs = []
        
        while current:
            if isinstance(current, Tag):
                if current.name in ['h1', 'h2'] and clean_text(current.get_text()) != "": 
                    break
                if current.name in ['ul', 'ol']:
                    for li in current.find_all('li'):
                        q = clean_text(li.get_text())
                        raw_pairs.append(f"Q: {q}")
                elif current.name == 'h3':
                    txt = clean_text(current.get_text())
                    raw_pairs.append(f"Q: {txt}")
                elif current.name == 'p':
                    txt = clean_text(current.get_text())
                    if '?' in txt and len(txt) < 150:
                        raw_pairs.append(f"Q: {txt}") 
                    else:
                        raw_pairs.append(f"A: {txt}")
            current = current.next_sibling

        curr_q = ""
        for line in raw_pairs:
            if line.startswith("Q:"):
                curr_q = line[3:]
            elif line.startswith("A:") and curr_q:
                faq_items.append(f"FAQ_Q: {curr_q} // FAQ_A: {line[3:]}")
                curr_q = ""

        faq_header.decompose()
        if faq_items:
            return {"content_name": "Frequently Asked Questions", "small_chunks": faq_items}
        return None

    def _chunk_linear_content(self, soup: BeautifulSoup):
        current_chunk = []
        current_title = "Main Content"
        root = soup.find('body') or soup
        
        for elem in root.find_all(['p', 'h2', 'h3', 'ul', 'ol']):
            text = clean_text(elem.get_text())
            if not text: continue
            if elem.find_parent('table'): continue

            if elem.name in ['h2', 'h3']:
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
                prefix = "WARNING" if ('⚠️' in text or 'WARNING' in text or 'UWAGA' in text) else "CONTENT"
                current_chunk.append(f"{prefix}: {text}")

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

def extract_google_doc_content(html: str) -> Tuple[bool, Optional[str], Optional[str]]:
    extractor = GoogleDocExtractor()
    return extractor.extract_content(html)
