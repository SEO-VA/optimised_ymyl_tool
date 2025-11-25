#!/usr/bin/env python3
"""
Response Parser Module - Invincible Edition
1. Auto-detects List vs Dictionary JSON structure.
2. Auto-detects available fields in Violation Model to prevent crashes.
"""

import json
import re
import inspect
import streamlit as st
from typing import List, Dict, Any, Optional
from core.models import Violation, Severity
from utils.helpers import safe_log

class ResponseParser:
    """
    Robust parser that adapts to the Model definition at runtime.
    """

    @staticmethod
    def parse_to_violations(raw_text: str) -> List[Violation]:
        cleaned_json = ResponseParser._extract_json_structure(raw_text)
        
        if not cleaned_json:
            safe_log(f"Parser: Could not find JSON. Response start: {raw_text[:200]}...", "ERROR")
            return []

        try:
            data = json.loads(cleaned_json)
        except json.JSONDecodeError:
            safe_log("Parser: JSON Error, attempting heuristic fix...", "WARNING")
            healed_json = ResponseParser._heuristic_fix_json(cleaned_json)
            try:
                data = json.loads(healed_json)
            except json.JSONDecodeError as e:
                safe_log(f"Parser: Fatal JSON error: {e}", "ERROR")
                return []

        return ResponseParser._map_data_to_violations(data)

    @staticmethod
    def _extract_json_structure(text: str) -> Optional[str]:
        if not text: return None
        text = text.strip()
        
        # 1. Code Block Regex
        code_block = re.search(r'```(?:json)?\s*([\{\[][\s\S]*?[\]\}])\s*```', text)
        if code_block: return code_block.group(1)

        # 2. Greedy Search (Find first '{' or '[' and last '}' or ']')
        match = re.search(r'([\{\[])[\s\S]*([\}\]])', text)
        if match: return match.group(0)
            
        return None

    @staticmethod
    def _heuristic_fix_json(bad_json: str) -> str:
        return bad_json.replace('\t', '    ').replace('\r', '')

    @staticmethod
    def _map_data_to_violations(data: Any) -> List[Violation]:
        violations: List[Violation] = []
        raw_list = []

        # 1. Normalize Structure (Handle Dict vs List)
        if isinstance(data, dict):
            raw_list = data.get('violations', [])
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    if 'violations' in item and isinstance(item['violations'], list):
                        raw_list.extend(item['violations'])
                    else:
                        raw_list.append(item)

        if not isinstance(raw_list, list):
            safe_log(f"Parser: Expected list, got {type(raw_list)}", "ERROR")
            return []

        # 2. DYNAMIC INSPECTION (The Fix)
        # We check what fields your Violation class actually accepts.
        # This prevents "unexpected keyword argument" crashes.
        try:
            sig = inspect.signature(Violation)
            valid_keys = set(sig.parameters.keys())
        except Exception as e:
            safe_log(f"Parser: Model introspection failed: {e}", "CRITICAL")
            return []

        # 3. Map Data
        for i, v_dict in enumerate(raw_list):
            if not isinstance(v_dict, dict): continue
            try:
                # Prepare all POTENTIAL data
                sev_val = v_dict.get('severity', 'medium')
                
                candidate_data = {
                    "problematic_text": v_dict.get('problematic_text') or 'N/A',
                    "violation_type": v_dict.get('violation_type') or 'Unknown',
                    "explanation": v_dict.get('explanation') or 'No explanation',
                    "guideline_section": str(v_dict.get('guideline_section') or 'N/A'),
                    "page_number": v_dict.get('page_number') or 0,
                    "severity": Severity.from_string(sev_val),
                    "suggested_rewrite": v_dict.get('suggested_rewrite') or 'N/A',
                    # New Translation fields
                    "translation": v_dict.get('translation'),
                    "rewrite_translation": v_dict.get('rewrite_translation'),
                    "chunk_language": v_dict.get('chunk_language', 'English')
                }

                # Filter: Only keep keys that exist in the Model
                filtered_data = {k: v for k, v in candidate_data.items() if k in valid_keys}

                violation = Violation(**filtered_data)
                violations.append(violation)

            except Exception as e:
                # Log exact error to see what's breaking
                safe_log(f"Parser skipped item #{i}: {str(e)}", "WARNING")
                continue
                
        return violations
