#!/usr/bin/env python3
"""
Helper Utilities
Common functions for logging, text cleaning, and validation.
"""

import logging
import re
import time
from datetime import datetime
from typing import Any, Optional

# Setup simple logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def safe_log(message: str, level: str = "INFO"):
    """Safely log a message to console."""
    try:
        lvl = getattr(logging, level.upper(), logging.INFO)
        logger.log(lvl, message)
    except Exception:
        print(f"[{level}] {message}")

def validate_url(url: str) -> bool:
    """Basic URL validation."""
    if not url or not isinstance(url, str):
        return False
    url = url.strip()
    # Basic pattern for http/https
    pattern = re.compile(
        r'^https?://' 
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'
        r'localhost|'
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
        r'(?::\d+)?'
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    return bool(pattern.match(url))

def extract_domain(url: str) -> Optional[str]:
    """Extract domain from URL for filenames."""
    try:
        if not validate_url(url): return None
        domain = re.sub(r'^https?://', '', url)
        return domain.split('/')[0].split(':')[0].lower()
    except Exception:
        return None

def create_safe_filename(text: str, max_length: int = 50) -> str:
    """Create OS-safe filename from text."""
    if not text: return "untitled"
    safe_text = re.sub(r'[^\w\s-]', '', text)
    safe_text = re.sub(r'\s+', '_', safe_text)
    return safe_text[:max_length].strip('_')

def clean_text(text: str) -> str:
    """Remove control characters and extra whitespace."""
    if not text: return ""
    cleaned = re.sub(r'\s+', ' ', text.strip())
    return cleaned

def format_timestamp(ts: float = None) -> str:
    if ts is None: ts = time.time()
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
