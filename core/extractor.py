#!/usr/bin/env python3
"""
URL Extractor
Fetches content from Web URLs and passes it to the HTML Extractor.
"""

import requests
from typing import Tuple, Optional
from core.html_extractor import extract_html_content
from utils.helpers import safe_log

DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

def extract_url_content(url: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Fetches URL -> Extracts HTML -> Returns JSON.
    """
    try:
        safe_log(f"Fetcher: Requesting {url}")
        response = requests.get(url, headers=DEFAULT_HEADERS, timeout=30)
        response.raise_for_status()
        
        # Check size (limit to 5MB to prevent crashing)
        if len(response.content) > 5 * 1024 * 1024:
            return False, None, "Content too large (>5MB)"

        # Pass raw HTML to our standard extractor
        html_content = response.text
        return extract_html_content(html_content)
        
    except requests.exceptions.Timeout:
        return False, None, "Request timed out"
    except requests.exceptions.RequestException as e:
        return False, None, f"Connection error: {e}"
    except Exception as e:
        return False, None, f"Unexpected error: {e}"
