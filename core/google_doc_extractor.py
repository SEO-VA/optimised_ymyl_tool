#!/usr/bin/env python3
"""
Google Doc Extractor - V3.0
Changes from V2.0:
1. Output format changed from big_chunks/small_chunks (tagged strings) to sections (markdown)
2. Each section has: index, name, content (plain markdown string)
3. Eliminates custom tags (HEADER:, CONTENT:, UL:, TABLE_HEADER:, etc.)
4. Inline text renderer unchanged (preserves links, bold, italic)
"""

import re
import json
from bs4 import BeautifulSoup, NavigableString, Tag
from typing import Tuple, Optional, Dict, List
from utils.helpers import safe_log, clean_text


class GoogleDocExtractor:

    def __init__(self):
        self.sections = []
        self.section_index = 1
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
                faq_chunk["index"] = self.section_index
                self.sections.append(faq_chunk)
                self.section_index += 1

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
        metadata_lines = []

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
                self.found_metadata[matched_key] = clean_value
                label = matched_key.upper().replace('_', ' ')
                metadata_lines.append(f"**{label.title()}:** {clean_value}")
                tag.decompose()

        if 'h1' not in self.found_metadata:
            h1_tag = soup.find('h1')
            if h1_tag:
                val = self._render_inline_text(h1_tag)
                metadata_lines.insert(0, f"# {val}")
                h1_tag.decompose()

        if metadata_lines:
            self.sections.append({
                "index": self.section_index,
                "name": "Metadata & Summary",
                "content": "\n\n".join(metadata_lines)
            })
            self.section_index += 1

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

    def _extract_flexible_faq(self, soup: BeautifulSoup) -> Optional[Dict]:
        faq_lines = []
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
                faq_lines.append(f"**Q: {curr_q}**\n\n> {line[3:].strip()}")
                curr_q = ""

        faq_header.decompose()
        if faq_lines:
            return {"name": "Frequently Asked Questions", "content": "\n\n".join(faq_lines)}
        return None

    def _chunk_linear_content(self, soup: BeautifulSoup):
        current_lines = []
        current_title = "Main Content"
        root = soup.find('body') or soup

        for elem in root.find_all(['p', 'h2', 'h3', 'ul', 'ol', 'table']):
            text = clean_text(elem.get_text())
            if not text and elem.name != 'table': continue
            if elem.find_parent('table') and elem.name != 'table': continue

            if elem.name in ['h2', 'h3']:
                if current_lines:
                    self.sections.append({
                        "index": self.section_index,
                        "name": current_title,
                        "content": "\n\n".join(current_lines)
                    })
                    self.section_index += 1
                    current_lines = []
                current_title = clean_text(elem.get_text())
                level = "##" if elem.name == 'h2' else "###"
                current_lines.append(f"{level} {self._render_inline_text(elem)}")

            elif elem.name in ['ul', 'ol']:
                items = []
                for i, li in enumerate(elem.find_all('li', recursive=False)):
                    li_text = self._render_inline_text(li).strip()
                    if elem.name == 'ol':
                        items.append(f"{i+1}. {li_text}")
                    else:
                        items.append(f"- {li_text}")
                if items:
                    current_lines.append("\n".join(items))

            elif elem.name == 'table':
                # Extract table as markdown
                thead = elem.find('thead')
                header_row = None
                if thead:
                    header_row = thead.find('tr')
                else:
                    first_tr = elem.find('tr')
                    if first_tr and first_tr.find('th'):
                        header_row = first_tr

                table_lines = []
                if header_row:
                    cols = [self._render_inline_text(c).strip() for c in header_row.find_all(['th', 'td'])]
                    if cols:
                        table_lines.append('| ' + ' | '.join(cols) + ' |')
                        table_lines.append('| ' + ' | '.join(['---'] * len(cols)) + ' |')

                for tr in elem.find_all('tr'):
                    if tr == header_row:
                        continue
                    cells = [self._render_inline_text(c).strip() for c in tr.find_all(['td', 'th'])]
                    cells = [c for c in cells if c]
                    if cells:
                        table_lines.append('| ' + ' | '.join(cells) + ' |')

                if table_lines:
                    current_lines.append('\n'.join(table_lines))

            else:
                rendered = self._render_inline_text(elem)
                if not rendered: continue
                if '⚠️' in text or 'WARNING' in text or 'UWAGA' in text:
                    current_lines.append(f"> **Warning:** {rendered}")
                else:
                    current_lines.append(rendered)

        if current_lines:
            self.sections.append({
                "index": self.section_index,
                "name": current_title,
                "content": "\n\n".join(current_lines)
            })

    def _create_final_json(self) -> str:
        if not self.sections:
            self.sections = [{"index": 1, "name": "Empty", "content": "No content found"}]
        return json.dumps({"sections": self.sections}, indent=2, ensure_ascii=False)


def extract_google_doc_content(html: str) -> Tuple[bool, Optional[str], Optional[str]]:
    extractor = GoogleDocExtractor()
    return extractor.extract_content(html)
