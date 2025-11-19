#!/usr/bin/env python3
"""
Feature Registry
Manages the available analysis features (URL vs HTML).
"""

from typing import Dict, Any, Type
from utils.helpers import safe_log

class FeatureRegistry:
    """Central registry for dynamic loading of features."""
    
    _features = {}
    _handlers = {}
    
    @classmethod
    def register_feature(cls, feature_id: str, config: Dict[str, Any], handler_class: Type):
        cls._features[feature_id] = config
        cls._handlers[feature_id] = handler_class
        safe_log(f"Registry: Registered {feature_id}")
    
    @classmethod
    def get_handler(cls, feature_id: str):
        if feature_id not in cls._handlers:
            raise ValueError(f"Unknown feature: {feature_id}")
        return cls._handlers[feature_id]()

# --- Auto-register available features ---
def _register_default_features():
    # 1. URL Analysis
    try:
        from features.url_analysis import URLAnalysisFeature
        FeatureRegistry.register_feature(
            'url_analysis',
            {'display_name': '🌐 URL Analysis'},
            URLAnalysisFeature
        )
    except ImportError as e:
        safe_log(f"Registry: URL feature missing: {e}", "WARNING")

    # 2. HTML Analysis
    try:
        from features.html_analysis import HTMLAnalysisFeature
        FeatureRegistry.register_feature(
            'html_analysis',
            {'display_name': '📄 HTML Analysis'},
            HTMLAnalysisFeature
        )
    except ImportError as e:
        safe_log(f"Registry: HTML feature missing: {e}", "WARNING")

# Initialize on load
_register_default_features()
