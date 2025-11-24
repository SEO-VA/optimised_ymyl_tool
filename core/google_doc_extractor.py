#!/usr/bin/env python3
"""
Google Doc Extractor - The "Scavenger Hunt" Edition
Designed for unstructured HTML exports from Google Docs.
Hunts for metadata, visual headers, and safety context regardless of layout.
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
        # Keys to hunt for (Case Insensitive)
        self.metadata_keys = {
            'h1': ['h1:', 'h1'],
            'subtitle': ['subtitle:', 'sub-title:', 'subtitle'],
            'lead': ['lead:', 'lead text:', 'lead'],
            'meta_title': ['mt', 'meta title', 'meta_title'],
            'meta_desc': ['md', 'meta description', 'meta_desc']
        }
        # Store found metadata to avoid repetition
        self.found_metadata = {}

    def extract_content(self, html_content: str) -> Tuple[bool, Optional[str], Optional[str]]:
        try:
            # 1. Parse & Clean
            soup = BeautifulSoup(html_content, 'html.parser')
            self._remove_noise(soup)
            
            # 2. SCAVENGER HUNT: Metadata (Top or Bottom)
            # We extract and REMOVE these elements so they don't duplicate in the body
            self._hunt_for_metadata(soup)
            
            # 3. SCAVENGER HUNT: Global Context Backpack
            # Licenses, Warnings (18+), Restrictions
            self._extract_global_backpack(soup)

            # 4. TRANSFORM: Visual to Semantic
            # Convert "Bold Paragraphs" to H2/H3, Flatten Tables
            self._normalize_structure(soup)
            
            # 5. DETECTIVE: FAQ Extraction
            # Looks for specific FAQ patterns (Lists vs Text blocks)
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
        for tag in soup(['script', 'style', 'meta', 'title']):
            tag.decompose()
        
        # Remove empty paragraphs which Google Docs creates a lot of
        for p in soup.find_all('p'):
            if not p.get_text(strip=True):
                p.decompose()

    def _hunt_for_metadata(self, soup: BeautifulSoup):
        """
        Scans EVERY paragraph/table cell for metadata keys (H1:, LEAD:, MT).
        Extracts the value and Decomposes the tag.
        """
        # We scan a copy of the list because we modify the tree
        all_tags = soup.find_all(['p', 'li', 'td', 'h1', 'h2', 'h3'])
        
        metadata_chunk_items = []

        for tag in all_tags:
            text = clean_text(tag.get_text())
            if not text: continue
            
            # Check against all keys
            matched_key = None
            clean_value = None
            
            lower_text = text.lower()
            
            for meta_type, keywords in self.metadata_keys.items():
                for keyword in keywords:
                    # Match "Key: Value" or "Key<br>Value"
                    # Regex looks for Key at start, optional colon, optional newline
                    pattern = r'^' + re.escape(keyword) + r'[:\s]*(.*)'
                    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
                    
                    if match:
                        # Special check: specific keys like "MT" might be too short and match random text
                        # So we ensure "MT" is usually followed by line break or colon
                        if keyword == 'mt' or keyword == 'md':
                            if not (':' in text[:4] or '\n' in text[:4] or len(text) < 300):
                                continue

                        value = match.group(1).strip()
                        if value:
                            matched_key = meta_type
                            clean_value = value
                            break
                if matched_key: break
            
            if matched_key and matched_key not in self.found_metadata:
                # Found it! Save and Destroy.
                label = matched_key.upper().replace('_', ' ')
                self.found_metadata[matched_key] = clean_value
                metadata_chunk_items.append(f"{label}: {clean_value}")
                tag.decompose()

        # If we found H1 in the hunt, good. If not, try finding the first <H1> tag.
        if 'h1' not in self.found_metadata:
            h1_tag = soup.find('h1')
            if h1_tag:
                val = clean_text(h1_tag.get_text())
                metadata_chunk_items.insert(0, f"H1: {val}")
                h1_tag.decompose()

        # Create the Metadata Chunk
        if metadata_chunk_items:
            self.big_chunks.append({
                "big_chunk_index": self.chunk_index,
                "content_name": "Metadata & Summary",
                "small_chunks": metadata_chunk_items
            })
            self.chunk_index += 1

    def _extract_global_backpack(self, soup: BeautifulSoup):
        """Create the Global Context Backpack from the remaining text."""
        context_items = []
        full_text = soup.get_text(" ", strip=True)

        # 1. Licenses
        lic_keywords = ['UKGC', 'MGA/', 'Curacao', 'License', 'Regulated by']
        for kw in lic_keywords:
            matches = re.findall(r'([^.]*?' + kw + r'[^.]*\.)', full_text, re.IGNORECASE)
            for m in matches[:2]: context_items.append(f"LICENSE_CTX: {clean_text(m)}")

        # 2. Restrictions
        res_keywords = ['not available in', 'restricted countr', 'players from']
        for kw in res_keywords:
            matches = re.findall(r'([^.]*?' + kw + r'[^.]*\.)', full_text, re.IGNORECASE)
            for m in matches[:2]: context_items.append(f"RESTRICTION_CTX: {clean_text(m)}")

        # 3. Warnings (Emoji search is very effective for Google Docs)
        if '⚠️' in full_text or '18+' in full_text:
            context_items.append("SAFETY_CTX: Risk Warnings found in document.")

        if context_items:
            self.big_chunks.append({
                "big_chunk_index": 0, # Backpack index
                "content_name": "GLOBAL CONTEXT",
                "small_chunks": list(set(context_items))
            })

    def _normalize_structure(self, soup: BeautifulSoup):
        """
        Converts 'Visual' formatting (Bold spans) into 'Semantic' tags (H2).
        Flattens tables into text.
        """
        # 1. Convert Bold Paragraphs to H2
        # Criteria: Short text, Bold style, No ending punctuation
        for p in soup.find_all('p'):
            text = clean_text(p.get_text())
            if not text or len(text) > 80: continue
            
            # Check if it contains bold
            # Google Docs uses font-weight:700 in style attributes or <b>/<strong> tags
            is_bold = False
            if p.find(['b', 'strong']): is_bold = True
            if 'font-weight:700' in p.get('style', '') or 'font-weight: bold' in p.get('style', ''): is_bold = True
            # Check children spans
            for span in p.find_all('span'):
                if 'font-weight:700' in span.get('style', ''): is_bold = True; break
            
            if is_bold and not text.endswith(('.', '!', '?')):
                p.name = 'h2' # Upgrade to Header

        # 2. Flatten Tables (Preserve text, destroy layout)
        for table in soup.find_all('table'):
            rows_text = []
            for tr in table.find_all('tr'):
                cells = [clean_text(td.get_text()) for td in tr.find_all('td')]
                cells = [c for c in cells if c] # Filter empty
                if cells:
                    rows_text.append(" | ".join(cells))
            
            # Replace table with a P containing the flattened text
            if rows_text:
                new_p = soup.new_tag("p")
                new_p.string = "TABLE_DATA: " + " // ".join(rows_text)
                table.replace_with(new_p)
            else:
                table.decompose()

    def _extract_flexible_faq(self, soup: BeautifulSoup) -> Optional[Dict]:
        """
        Finds FAQs whether they are Headers, Lists, or Q&A Text Blocks (Chanz style).
        """
        faq_items = []
        
        # Find the start of the FAQ section
        # Look for headers containing "FAQ", "KKK", "Questions"
        faq_header = None
        for header in soup.find_all(['h1', 'h2', 'h3', 'p']):
            txt = clean_text(header.get_text()).upper()
            if 'FAQ' in txt or 'KKK' in txt or 'FREQUENTLY ASKED' in txt:
                if len(txt) < 50: # Ensure it's a title, not a sentence mentioning FAQs
                    faq_header = header
                    break
        
        if not faq_header: return None

        # Scan siblings after the header
        current_element = faq_header.next_sibling
        raw_faq_text = ""
        
        while current_element:
            if isinstance(current_element, Tag):
                # Stop if we hit another H2 (New section)
                if current_element.name == 'h2': break
                
                txt = clean_text(current_element.get_text())
                if txt:
                    # Heuristic: If text contains a '?', assume it's a Question line
                    if '?' in txt:
                        raw_faq_text += f"\nQ: {txt}\n"
                    else:
                        raw_faq_text += f"A: {txt}\n"
            
            current_element = current_element.next_sibling

        # Clean up the extracted text pairs
        # This handles the "Chanz" style where Q and A might be in one block separated by <br>
        # or separate paragraphs.
        pairs = raw_faq_text.split('Q: ')
        for p in pairs:
            if not p.strip(): continue
            parts = p.split('\nA:')
            if len(parts) >= 1:
                q_text = parts[0].strip()
                a_text = parts[1].strip() if len(parts) > 1 else "Answer in context"
                faq_items.append(f"FAQ_Q: {q_text} // FAQ_A: {a_text}")

        # Cleanup: We remove the header. The content siblings are tricky to remove safely 
        # without breaking the loop, so we leave them (they are just text now).
        faq_header.decompose()

        if faq_items:
            return {
                "content_name": "Frequently Asked Questions",
                "small_chunks": faq_items
            }
        return None

    def _chunk_linear_content(self, soup: BeautifulSoup):
        """Standard Linear Chunking (Grouping by H2/H3)."""
        current_chunk = []
        current_title = "Main Content"
        
        # Iterate over all top-level elements in body
        # (Google Docs usually dump p/h2 tags directly in body or a wrapper div)
        root = soup.find('body') or soup
        
        for elem in root.find_all(['p', 'h2', 'h3', 'ul', 'ol'], recursive=False):
            text = clean_text(elem.get_text())
            if not text: continue
            
            if elem.name in ['h2', 'h3']:
                # Flush current
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
                current_chunk.append(f"LIST: {' // '.join(items)}")
            
            else:
                # Paragraphs (Content)
                # Check for warnings that might have survived
                if '⚠️' in text:
                    current_chunk.append(f"WARNING: {text}")
                else:
                    current_chunk.append(f"CONTENT: {text}")

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
