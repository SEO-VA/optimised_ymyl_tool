#!/usr/bin/env python3
"""
HTML Content Extractor
Parses raw HTML into structured 'Big Chunks' for the AI.
Implements specific logic to handle H2 sections, Tables, and Warning blocks.
"""

import json
import re
from bs4 import BeautifulSoup, Comment
from typing import Tuple, Optional, List, Set
from utils.helpers import safe_log, clean_text

class HTMLContentExtractor:
    """Extracts structured content directly from HTML strings."""
    
    def __init__(self):
        self.processed_elements: Set[str] = set()
        self.current_h2_section = None
        self.big_chunks = []
    
    def extract_content(self, html_content: str) -> Tuple[bool, Optional[str], Optional[str]]:
        try:
            # Parse HTML
            soup = BeautifulSoup(html_content, 'html.parser')
            self._preprocess_soup(soup)
            
            # Reset state
            self.processed_elements.clear()
            self.big_chunks = []
            self.current_h2_section = None
            
            # Execute chunking strategy
            self._extract_with_direct_chunking(soup)
            
            # Finalize
            organized_content = self._create_final_json()
            return True, organized_content, None
            
        except Exception as e:
            error_msg = f"HTML parsing error: {str(e)}"
            safe_log(error_msg, "ERROR")
            return False, None, error_msg

    def _preprocess_soup(self, soup: BeautifulSoup):
        """Remove noise elements."""
        for tag in soup(['script', 'style', 'nav', 'footer', 'aside', 'header', 'noscript']):
            tag.decompose()
        
        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()

    def _get_element_id(self, element) -> str:
        """Content-based hash to prevent duplicate processing."""
        if element is None: return ""
        text = element.get_text()[:100].strip()
        return f"{element.name}:{hash((text, len(list(element.children))))}"

    def _is_processed(self, element) -> bool:
        return self._get_element_id(element) in self.processed_elements

    def _mark_processed(self, element):
        self.processed_elements.add(self._get_element_id(element))

    def _extract_with_direct_chunking(self, soup: BeautifulSoup):
        """Iterate elements and group by H2 headers."""
        pre_h2_content = []
        current_chunk_content = []
        chunk_index = 1
        
        # Find main content area
        main_area = soup.find('article') or soup.find('main') or soup.find('body') or soup
        
        # Important tags to capture
        tags = ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'table', 'ul', 'ol', 'dl', 'section', 'div']
        
        for element in main_area.find_all(tags):
            if self._is_processed(element): continue
            
            # Skip if inside a container we already processed (like a table we handled entirely)
            if any(p.name in ['table', 'ul', 'ol', 'dl'] and self._is_processed(p) for p in element.parents):
                continue

            formatted = self._format_element(element)
            if not formatted: continue
            
            if formatted.startswith('H2:'):
                # Save previous chunk
                if current_chunk_content:
                    self.big_chunks.append({
                        "big_chunk_index": chunk_index,
                        "small_chunks": current_chunk_content.copy()
                    })
                    chunk_index += 1
                elif pre_h2_content:
                    self.big_chunks.append({
                        "big_chunk_index": chunk_index,
                        "small_chunks": pre_h2_content.copy()
                    })
                    chunk_index += 1
                
                current_chunk_content = [formatted]
                self.current_h2_section = formatted
            else:
                if self.current_h2_section is None:
                    pre_h2_content.append(formatted)
                else:
                    current_chunk_content.append(formatted)

        # Add final tail
        if current_chunk_content:
            self.big_chunks.append({
                "big_chunk_index": chunk_index,
                "small_chunks": current_chunk_content
            })
        elif pre_h2_content:
            self.big_chunks.append({
                "big_chunk_index": 1,
                "small_chunks": pre_h2_content
            })

    def _format_element(self, element) -> Optional[str]:
        """Convert HTML element to text representation."""
        self._mark_processed(element)
        tag = element.name
        text = clean_text(element.get_text())
        
        if not text and tag != 'table': return None

        # Warning Blocks (Specific to your requirements)
        if 'warning' in str(element.get('class', [])).lower() or '⚠️' in text:
            return f"WARNING: {text}"

        if tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            # Remove prefix if it exists in text already to avoid "H2: H2: Title"
            tag_upper = tag.upper()
            if text.upper().startswith(f"{tag_upper}:"):
                return text
            return f"{tag_upper}: {text}"
            
        if tag == 'p': return f"CONTENT: {text}"
        
        if tag in ['ul', 'ol']:
            items = [li.get_text(strip=True) for li in element.find_all('li')]
            if items:
                # Mark children as processed so we don't grab them again
                for child in element.find_all(): self._mark_processed(child)
                return f"LIST: {' // '.join(items)}"
                
        if tag == 'table':
            rows = []
            for tr in element.find_all('tr'):
                cells = [td.get_text(strip=True) for td in tr.find_all(['td', 'th'])]
                if any(cells): rows.append(" | ".join(cells))
            if rows:
                # Mark children
                for child in element.find_all(): self._mark_processed(child)
                return f"TABLE: {' // '.join(rows)}"

        return None

    def _create_final_json(self) -> str:
        if not self.big_chunks:
            self.big_chunks = [{"big_chunk_index": 1, "small_chunks": ["CONTENT: No content extracted"]}]
        
        return json.dumps({"big_chunks": self.big_chunks}, indent=2, ensure_ascii=False)

# Convenience function
def extract_html_content(html: str) -> Tuple[bool, Optional[str], Optional[str]]:
    extractor = HTMLContentExtractor()
    return extractor.extract_content(html)
