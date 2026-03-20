#!/usr/bin/env python3
"""
Google Doc Extractor - V2.0
Changes from V1:
1. _render_inline_text() preserves links [text](url), bold **text**, italic *text*
2. TABLE_HEADER / TABLE_ROW separate small_chunks
3. OL: / UL: with | separator
4. FAQ emits separate FAQ_Q: and FAQ_A: small_chunks
5. Google Doc bold detection via font-weight style
"""

import re
import json
from bs4 import BeautifulSoup, NavigableString, Tag
from typing import Tuple, Optional, Dict, List
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

    # ------------------------------------------------------------------
    # Inline text renderer (same logic as HTMLContentExtractor)
    # ------------------------------------------------------------------

    def _render_inline_text(self, element, depth: int = 0) -> str:
        """Walk element children and return Markdown-flavoured plain text."""
        if depth > 12:
            return clean_text(element.get_text())

        parts = []
        for child in element.children:
            if isinstance(child, NavigableString):
                text = str(child)
                if text.strip():
                    parts.append(text)
            elif isinstance(child, Tag):
                name = child.name
                if name == 'a':
                    inner = self._render_inline_text(child, depth + 1).strip()
                    href = child.get('href', '').strip()
                    if not inner:
                        inner = clean_text(child.get_text())
                    if href and not href.startswith('javascript:'):
                        parts.append(f"[{inner}]({href})")
                    elif inner:
                        parts.append(inner)
                elif name in ('strong', 'b'):
                    inner = self._render_inline_text(child, depth + 1).strip()
                    if inner:
                        parts.append(f"**{inner}**")
                elif name in ('em', 'i'):
                    inner = self._render_inline_text(child, depth + 1).strip()
                    if inner:
                        parts.append(f"*{inner}*")
                elif name == 'img':
                    alt = child.get('alt', '').strip()
                    if alt:
                        parts.append(f"[IMG: {alt}]")
                elif name in ('br',):
                    parts.append(' ')
                elif name in ('script', 'style', 'noscript'):
                    pass
                else:
                    # Google Docs uses spans with inline style for bold
                    style = child.get('style', '')
                    is_bold = ('font-weight:700' in style.replace(' ', '') or
                               'font-weight:bold' in style.replace(' ', ''))
                    inner = self._render_inline_text(child, depth + 1)
                    if inner and is_bold:
                        parts.append(f"**{inner.strip()}**")
                    elif inner:
                        parts.append(inner)

        result = ''.join(parts)
        return re.sub(r'\s+', ' ', result).strip()

    # ------------------------------------------------------------------
    # Main extraction
    # ------------------------------------------------------------------

    def extract_content(self, html_content: str) -> Tuple[bool, Optional[str], Optional[str]]:
        try:
            html_content = re.sub(r'\[email&#160;protected\]', 'EMAIL_HIDDEN', html_content)

            soup = BeautifulSoup(html_content, 'html.parser')
            self._remove_noise(soup)

            # Metadata Hunt
            self._hunt_for_metadata(soup)

            # Normalize Structure (bold short paragraphs → h2, tables → chunks)
            self._normalize_structure(soup)

            # FAQ Detective
            faq_chunk = self._extract_flexible_faq(soup)

            # Standard Chunking
            self._chunk_linear_content(soup)

            # Append FAQ
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
                val = self._render_inline_text(h1_tag)
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
        # Bold short paragraphs → h2
        for p in soup.find_all('p'):
            text = clean_text(p.get_text())
            if not text or len(text) > 100: continue

            is_bold = False
            if p.find(['b', 'strong']): is_bold = True
            if 'font-weight' in str(p).lower() and ('700' in str(p) or 'bold' in str(p)): is_bold = True

            if is_bold and not text.endswith(('.', '!', '?')):
                p.name = 'h2'

        # Tables → replace with a sentinel div containing table data attributes
        # We handle tables directly in _chunk_linear_content via find_all
        # so no transformation needed here

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
                        q = self._render_inline_text(li)
                        raw_pairs.append(f"Q: {q}")
                elif current.name == 'h3':
                    txt = self._render_inline_text(current)
                    raw_pairs.append(f"Q: {txt}")
                elif current.name == 'p':
                    txt = self._render_inline_text(current)
                    if '?' in txt and len(txt) < 150:
                        raw_pairs.append(f"Q: {txt}")
                    else:
                        raw_pairs.append(f"A: {txt}")
            current = current.next_sibling

        curr_q = ""
        for line in raw_pairs:
            if line.startswith("Q:"):
                curr_q = line[3:].strip()
            elif line.startswith("A:") and curr_q:
                faq_items.append(f"FAQ_Q: {curr_q}")
                faq_items.append(f"FAQ_A: {line[3:].strip()}")
                curr_q = ""

        faq_header.decompose()
        if faq_items:
            return {"content_name": "Frequently Asked Questions", "small_chunks": faq_items}
        return None

    def _chunk_linear_content(self, soup: BeautifulSoup):
        current_chunk = []
        current_title = "Main Content"
        root = soup.find('body') or soup

        for elem in root.find_all(['p', 'h2', 'h3', 'ul', 'ol', 'table']):
            text = clean_text(elem.get_text())
            if not text and elem.name != 'table': continue
            if elem.find_parent('table') and elem.name != 'table': continue

            if elem.name in ['h2', 'h3']:
                if current_chunk:
                    self.big_chunks.append({
                        "big_chunk_index": self.chunk_index,
                        "content_name": current_title,
                        "small_chunks": current_chunk
                    })
                    self.chunk_index += 1
                    current_chunk = []
                current_title = clean_text(elem.get_text())
                current_chunk.append(f"HEADER: {self._render_inline_text(elem)}")

            elif elem.name in ['ul', 'ol']:
                items = []
                for i, li in enumerate(elem.find_all('li', recursive=False)):
                    li_text = self._render_inline_text(li).strip()
                    if elem.name == 'ol':
                        items.append(f"{i+1}. {li_text}")
                    else:
                        items.append(li_text)
                if items:
                    prefix = "OL" if elem.name == 'ol' else "UL"
                    current_chunk.append(f"{prefix}: {' | '.join(items)}")

            elif elem.name == 'table':
                # Extract table as TABLE_HEADER + TABLE_ROW items
                thead = elem.find('thead')
                header_row = None
                if thead:
                    header_row = thead.find('tr')
                else:
                    first_tr = elem.find('tr')
                    if first_tr and first_tr.find('th'):
                        header_row = first_tr

                if header_row:
                    cols = [self._render_inline_text(c).strip() for c in header_row.find_all(['th', 'td'])]
                    if cols:
                        current_chunk.append(f"TABLE_HEADER: {' | '.join(cols)}")

                for tr in elem.find_all('tr'):
                    if tr == header_row:
                        continue
                    cells = [self._render_inline_text(c).strip() for c in tr.find_all(['td', 'th'])]
                    cells = [c for c in cells if c]
                    if cells:
                        current_chunk.append(f"TABLE_ROW: {' | '.join(cells)}")

            else:
                rendered = self._render_inline_text(elem)
                if not rendered: continue
                prefix = "WARNING" if ('⚠️' in text or 'WARNING' in text or 'UWAGA' in text) else "CONTENT"
                current_chunk.append(f"{prefix}: {rendered}")

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
