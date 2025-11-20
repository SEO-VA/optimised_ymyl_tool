#!/usr/bin/env python3
"""
Helper Utilities
Common functions for logging, text cleaning, validation, and UI notifications.
Updated: Added trigger_completion_notification()
"""

import logging
import re
import time
import streamlit as st
from datetime import datetime
from typing import Any, Optional

# Setup simple logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def safe_log(message: str, level: str = "INFO"):
    try:
        lvl = getattr(logging, level.upper(), logging.INFO)
        logger.log(lvl, message)
    except Exception:
        print(f"[{level}] {message}")

def validate_url(url: str) -> bool:
    if not url or not isinstance(url, str): return False
    url = url.strip()
    pattern = re.compile(
        r'^https?://' 
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'
        r'localhost|'
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
        r'(?::\d+)?'
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    return bool(pattern.match(url))

def extract_domain(url: str) -> Optional[str]:
    try:
        if not validate_url(url): return None
        domain = re.sub(r'^https?://', '', url)
        return domain.split('/')[0].split(':')[0].lower()
    except Exception:
        return None

def create_safe_filename(text: str, max_length: int = 50) -> str:
    if not text: return "untitled"
    safe_text = re.sub(r'[^\w\s-]', '', text)
    safe_text = re.sub(r'\s+', '_', safe_text)
    return safe_text[:max_length].strip('_')

def clean_text(text: str) -> str:
    if not text: return ""
    cleaned = re.sub(r'\s+', ' ', text.strip())
    return cleaned

def format_timestamp(ts: float = None) -> str:
    if ts is None: ts = time.time()
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")

# --- NEW NOTIFICATION FUNCTION ---
def trigger_completion_notification():
    """
    Plays a sound and triggers a browser notification when analysis is done.
    """
    # 1. Streamlit Toast (In-App)
    st.toast("✅ Analysis Complete! Report is ready.", icon="🎉")
    
    # 2. JavaScript for Browser Notification + Sound + Title Flashing
    # Note: The audio file is a short, pleasant 'success' chime.
    js_code = """
    <script>
        // A. Play Sound
        var audio = new Audio('https://assets.mixkit.co/sfx/preview/mixkit-software-interface-start-2574.mp3');
        audio.volume = 0.5;
        audio.play();

        // B. Request & Trigger System Notification
        if (!("Notification" in window)) {
            console.log("This browser does not support desktop notification");
        } else if (Notification.permission === "granted") {
            new Notification("✅ YMYL Audit Complete!", {
                body: "Your report is ready to download.",
                icon: "https://cdn-icons-png.flaticon.com/512/190/190411.png"
            });
        } else if (Notification.permission !== "denied") {
            Notification.requestPermission().then(function (permission) {
                if (permission === "granted") {
                    new Notification("✅ YMYL Audit Complete!", {
                        body: "Your report is ready to download."
                    });
                }
            });
        }

        // C. Flash Tab Title
        var originalTitle = document.title;
        var isFlashing = false;
        var flashInterval = setInterval(function() {
            document.title = isFlashing ? "✅ READY! - " + originalTitle : "🔔 " + originalTitle;
            isFlashing = !isFlashing;
        }, 1000);

        // Stop flashing when user moves mouse (comes back to tab)
        window.onmousemove = function() {
            clearInterval(flashInterval);
            document.title = originalTitle;
            window.onmousemove = null;
        };
    </script>
    """
    st.components.v1.html(js_code, height=0, width=0)
