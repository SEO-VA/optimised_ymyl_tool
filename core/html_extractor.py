#!/usr/bin/env python3
"""
HTML Content Extractor - Surgical Edition V15.0
Changes from V14.2:
1. _render_inline_text() helper preserves links [text](url), bold **text**, italic *text*
2. TABLE_HEADER / TABLE_ROW separate small_chunks (no more flat // rows)
3. Page metadata extracted before preprocessing (published date, author, schema.org)
4. OL: / UL: with | separator instead of LIST: with //
5. FAQ emits separate FAQ_Q: and FAQ_A: small_chunks
6. blockquote and disclaimer/notice callout support
7. base_domain filtering to skip internal nav links
"""

import json
import re
from bs4 import BeautifulSoup, Comment, NavigableString, Tag
from typing import Tuple, Optional, List, Set, Dict
from core.google_doc_extractor import extract_google_doc_content
from utils.helpers import safe_log, clean_text

# Link patterns that are always worth keeping even on internal pages
_KEEP_PATH_PATTERNS = re.compile(
    r'(terms|condition|privacy|licen|responsible|gambling|regulation|complaint|bonus|promo|withdraw|deposit)',
    re.I
)
_SKIP_CLASS_PATTERNS = re.compile(
    r'(disclaimer|notice|callout|info[-_]?box|important|caution|alert)',
    re.I
)

class HTMLContentExtractor:

    def __init__(self):
        self.processed_elements: Set[str] = set()
        self.big_chunks = []
        self.chunk_index = 1
        self._base_domain: Optional[str] = None

    def extract_content(self, html_content: str, casino_mode: bool = False, base_domain: Optional[str] = None) -> Tuple[bool, Optional[str], Optional[str]]:
        try:
            self._base_domain = base_domain
            # Pre-clean
            html_content = re.sub(r'\[email&#160;protected\]', 'EMAIL_HIDDEN', html_content)
            soup = BeautifulSoup(html_content, 'html.parser')

            # Extract head metadata BEFORE preprocessing removes scripts/meta
            self._extract_head_metadata(soup)

            self._preprocess_soup(soup)

            self.processed_elements.clear()
            # chunk_index continues after metadata chunk(s)

            if casino_mode:
                safe_log("Extractor: Running Surgical Casino Extraction V15.0")

                # 1. Granular Metadata
                self._extract_metadata_separated(soup)

                # 2. FAQ
                faq_chunks = self._extract_faq_chunks(soup)

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

                # 5. Append FAQ
                for faq_chunk in faq_chunks:
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

    # ------------------------------------------------------------------
    # Inline text renderer - preserves links, bold, italic, images
    # ------------------------------------------------------------------

    def _render_inline_text(self, element, depth: int = 0) -> str:
        """Walk element children and return Markdown-flavoured plain text.

        - <a href="...">text</a>  →  [text](url)  (external/important links only)
        - <strong>/<b>            →  **text**
        - <em>/<i>                →  *text*
        - <img alt="...">         →  [IMG: alt]
        - everything else         →  recurse / emit text
        """
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
                    if href and not href.startswith('javascript:') and self._should_include_link(href):
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
                    pass  # skip
                else:
                    inner = self._render_inline_text(child, depth + 1)
                    if inner:
                        parts.append(inner)

        result = ''.join(parts)
        return re.sub(r'\s+', ' ', result).strip()

    def _should_include_link(self, href: str) -> bool:
        """Return True if this link's URL is worth passing to the LLM."""
        if href.startswith('#') or href.startswith('mailto:'):
            return True
        # External link (different domain or absolute with different domain)
        if href.startswith('http'):
            if self._base_domain and self._base_domain in href:
                # Internal absolute link — only keep if path matches key patterns
                return bool(_KEEP_PATH_PATTERNS.search(href))
            return True  # external
        # Relative link — keep if path matches key patterns
        return bool(_KEEP_PATH_PATTERNS.search(href))

    # ------------------------------------------------------------------
    # Head metadata extraction (runs before _preprocess_soup)
    # ------------------------------------------------------------------

    def _extract_head_metadata(self, soup: BeautifulSoup):
        meta_items = []

        head = soup.find('head')
        if head:
            # Meta description
            desc_tag = head.find('meta', attrs={'name': re.compile(r'^description$', re.I)})
            if desc_tag and desc_tag.get('content'):
                meta_items.append(f"META_DESC: {clean_text(desc_tag['content'])}")

            # Published / modified dates
            for prop in ('article:published_time', 'article:modified_time', 'og:updated_time'):
                tag = head.find('meta', attrs={'property': prop}) or head.find('meta', attrs={'name': prop})
                if tag and tag.get('content'):
                    label = 'PUBLISHED' if 'published' in prop else 'UPDATED'
                    date_val = tag['content'][:10]  # YYYY-MM-DD
                    meta_items.append(f"{label}: {date_val}")

            # Author
            author_tag = head.find('meta', attrs={'name': re.compile(r'^author$', re.I)})
            if author_tag and author_tag.get('content'):
                meta_items.append(f"AUTHOR: {clean_text(author_tag['content'])}")

        # <time> elements in body (fallback for published date)
        if not any(m.startswith('PUBLISHED') for m in meta_items):
            time_tag = soup.find('time', attrs={'datetime': True})
            if time_tag:
                dt = time_tag.get('datetime', '')[:10]
                if dt:
                    meta_items.append(f"PUBLISHED: {dt}")

        # Schema.org JSON-LD — look for rating/review data
        for script in soup.find_all('script', attrs={'type': 'application/ld+json'}):
            try:
                import json as _json
                data = _json.loads(script.string or '')
                # Handle single object or @graph array
                items = data if isinstance(data, list) else data.get('@graph', [data])
                for item in items:
                    if isinstance(item, dict):
                        rating = item.get('aggregateRating') or item.get('ratingValue')
                        if isinstance(rating, dict):
                            rv = rating.get('ratingValue', '')
                            rc = rating.get('ratingCount', '')
                            best = rating.get('bestRating', '5')
                            if rv:
                                meta_items.append(f"SCHEMA_RATING: {rv}/{best} ({rc} ratings)" if rc else f"SCHEMA_RATING: {rv}/{best}")
                        elif rating:
                            meta_items.append(f"SCHEMA_RATING: {rating}")
            except Exception:
                pass

        if meta_items:
            self.big_chunks.append({
                "big_chunk_index": self.chunk_index,
                "content_name": "Page Metadata",
                "small_chunks": meta_items
            })
            self.chunk_index += 1

    # ------------------------------------------------------------------
    # Preprocessing
    # ------------------------------------------------------------------

    def _preprocess_soup(self, soup: BeautifulSoup):
        tags_to_remove = ['script', 'style', 'nav', 'footer', 'aside', 'noscript', 'iframe', 'svg', 'button', 'form']
        for tag in soup(tags_to_remove):
            tag.decompose()
        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()

    def _remove_casino_widgets(self, soup: BeautifulSoup):
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

    # ------------------------------------------------------------------
    # Casino metadata extraction
    # ------------------------------------------------------------------

    def _extract_metadata_separated(self, soup: BeautifulSoup):
        intro_container = soup.find(attrs={'data-qa': re.compile(r'templateIntro', re.I)})
        if not intro_container:
            intro_container = soup.find(class_='intro')

        search_scope = intro_container if intro_container else soup

        # --- A. Heading (H1) ---
        h1 = search_scope.find('h1')
        if h1:
            text = self._render_inline_text(h1)
            if text:
                self.big_chunks.append({
                    "big_chunk_index": self.chunk_index,
                    "content_name": "Metadata: Main Heading",
                    "small_chunks": [f"H1: {text}"]
                })
                self.chunk_index += 1
            h1.decompose()

        # --- B. Subtitle ---
        subtitle = search_scope.find(class_=re.compile(r'sub-title', re.I))
        if subtitle:
            text = self._render_inline_text(subtitle)
            if text:
                self.big_chunks.append({
                    "big_chunk_index": self.chunk_index,
                    "content_name": "Metadata: Subtitle",
                    "small_chunks": [f"SUBTITLE: {text}"]
                })
                self.chunk_index += 1
            subtitle.decompose()

        # --- C. Lead Text ---
        lead = search_scope.find(class_=re.compile(r'lead', re.I))
        if lead:
            text = self._render_inline_text(lead)
            if text:
                self.big_chunks.append({
                    "big_chunk_index": self.chunk_index,
                    "content_name": "Metadata: Lead Text",
                    "small_chunks": [f"LEAD: {text}"]
                })
                self.chunk_index += 1
            lead.decompose()

        # --- D. Summary Block ---
        summary_block = soup.find(attrs={'data-qa': 'blockCasinoSummary'})
        if summary_block:
            text = self._render_inline_text(summary_block)
            if text:
                self.big_chunks.append({
                    "big_chunk_index": self.chunk_index,
                    "content_name": "Metadata: Summary",
                    "small_chunks": [f"SUMMARY: {text}"]
                })
                self.chunk_index += 1
            summary_block.decompose()

    # ------------------------------------------------------------------
    # FAQ extraction
    # ------------------------------------------------------------------

    def _extract_faq_chunks(self, soup: BeautifulSoup) -> List[Dict]:
        """Returns a list of FAQ chunk dicts (each with separate Q/A small_chunks)."""
        faq_items = []
        faq_section = None
        faq_section = soup.find(attrs={'data-qa': 'templateFAQ'}) or soup.find(class_='faq-section')
        if not faq_section:
            faq_section = soup.find(attrs={'itemtype': re.compile(r'schema\.org/FAQPage')})

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

        if not faq_section:
            return []

        questions = faq_section.find_all(attrs={'itemtype': re.compile(r'schema\.org/Question')})
        if not questions:
            questions = faq_section.find_all(['h3', 'h4', 'h5', 'strong', 'b'])

        for q in questions:
            q_text = self._render_inline_text(q)
            if not q_text or len(q_text) < 5: continue

            a_text = ""
            a_container = q.find(attrs={'itemprop': 'acceptedAnswer'})

            if a_container:
                a_text = self._render_inline_text(a_container)
            else:
                curr = q.next_sibling
                while curr and (not isinstance(curr, Tag) or curr.name in ['br', 'span']):
                    curr = curr.next_sibling
                if curr and isinstance(curr, Tag) and curr.name in ['p', 'div']:
                    a_text = self._render_inline_text(curr)

            if q_text and a_text:
                faq_items.append(f"FAQ_Q: {q_text}")
                faq_items.append(f"FAQ_A: {a_text}")
                self._mark_processed(q)
                if 'curr' in locals() and curr: self._mark_processed(curr)

        if faq_section.parent: faq_section.decompose()
        if faq_items:
            return [{"content_name": "Frequently Asked Questions", "small_chunks": faq_items}]
        return []

    # ------------------------------------------------------------------
    # Main chunking
    # ------------------------------------------------------------------

    def _extract_with_direct_chunking(self, container):
        current_chunk_content = []
        pre_h2_content = []
        current_section_name = "Main Content"
        tags = ['h2', 'h3', 'h4', 'p', 'table', 'ul', 'ol', 'dl', 'blockquote']

        for element in container.find_all(tags):
            if self._is_child_of_processed(element): continue

            tag = element.name
            text = self._render_inline_text(element) if tag != 'table' else ''
            if not text and tag not in ('table',): continue

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
                current_section_name = clean_text(element.get_text())  # plain name for section label
                self._mark_processed(element)
                continue

            formatted = None

            # Warning / callout detection
            el_classes = ' '.join(element.get('class', []))
            is_warning = ('warning' in el_classes.lower() or '⚠️' in (text or ''))
            is_notice = bool(_SKIP_CLASS_PATTERNS.search(el_classes))

            if is_warning:
                formatted = f"WARNING: {text}"
            elif is_notice:
                formatted = f"NOTICE: {text}"
            elif tag in ('h3', 'h4'):
                formatted = f"{tag.upper()}: {text}"
            elif tag == 'p':
                formatted = f"CONTENT: {text}"
            elif tag == 'blockquote':
                formatted = f"BLOCKQUOTE: {text}"
            elif tag in ('ul', 'ol'):
                formatted = self._format_list(element, tag)
            elif tag == 'dl':
                items = []
                dts = element.find_all('dt')
                dds = element.find_all('dd')
                for dt, dd in zip(dts, dds):
                    items.append(f"{self._render_inline_text(dt)}: {self._render_inline_text(dd)}")
                if items: formatted = f"DEF_LIST: {' | '.join(items)}"
            elif tag == 'table':
                formatted = self._format_table(element, current_section_name, current_chunk_content, pre_h2_content)
                # _format_table appends directly and returns None

            if formatted:
                self._mark_processed(element)
                if current_section_name == "Main Content":
                    pre_h2_content.append(formatted)
                else:
                    current_chunk_content.append(formatted)

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

    def _format_list(self, element, tag: str) -> Optional[str]:
        """Format ul/ol as OL:/UL: with | separator, one level of nesting."""
        items = []
        for i, li in enumerate(element.find_all('li', recursive=False)):
            # Grab direct text of this li (excluding nested list text)
            nested_lists = li.find_all(['ul', 'ol'], recursive=False)
            # Temporarily detach nested lists to get just this item's text
            detached = []
            for nl in nested_lists:
                nl.extract()
                detached.append(nl)

            li_text = self._render_inline_text(li).strip()
            if tag == 'ol':
                items.append(f"{i+1}. {li_text}")
            else:
                items.append(li_text)

            # Re-attach and process nested items
            for nl in detached:
                li.append(nl)
                for nested_li in nl.find_all('li', recursive=False):
                    nested_text = self._render_inline_text(nested_li).strip()
                    if nested_text:
                        items.append(f"> {nested_text}")

        if not items:
            return None
        prefix = "OL" if tag == 'ol' else "UL"
        return f"{prefix}: {' | '.join(items)}"

    def _format_table(self, element, current_section_name: str, current_chunk_content: list, pre_h2_content: list) -> None:
        """Format table as TABLE_HEADER + TABLE_ROW small_chunks, appended directly."""
        table_items = []

        # Find header row (thead > tr > th, or first tr with th cells)
        thead = element.find('thead')
        header_row = None
        if thead:
            header_row = thead.find('tr')
        else:
            first_tr = element.find('tr')
            if first_tr and first_tr.find('th'):
                header_row = first_tr

        if header_row:
            cols = [self._render_inline_text(c).strip() for c in header_row.find_all(['th', 'td'])]
            if cols:
                table_items.append(f"TABLE_HEADER: {' | '.join(cols)}")

        # Data rows
        all_rows = element.find_all('tr')
        for tr in all_rows:
            if tr == header_row:
                continue
            cells = [self._render_inline_text(c).strip() for c in tr.find_all(['td', 'th'])]
            cells = [c for c in cells if c]
            if cells:
                table_items.append(f"TABLE_ROW: {' | '.join(cells)}")

        if table_items:
            self._mark_processed(element)
            if current_section_name == "Main Content":
                current_chunk_content  # not used here
                pre_h2_content.extend(table_items)
            else:
                current_chunk_content.extend(table_items)
        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

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


def extract_html_content(html: str, casino_mode: bool = False, base_domain: Optional[str] = None) -> Tuple[bool, Optional[str], Optional[str]]:
    if 'doc-content' in html or 'google.com/url' in html or ('<style type="text/css">' in html and '.c1{' in html):
        safe_log("Extractor: Detected Google Doc format. Using Scavenger Extractor.")
        return extract_google_doc_content(html)

    extractor = HTMLContentExtractor()
    return extractor.extract_content(html, casino_mode, base_domain=base_domain)
