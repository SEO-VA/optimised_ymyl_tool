#!/usr/bin/env python3
"""
Response Parser Module - Universal Edition
Handles both List (Old) and Dictionary (New) formats from AI.
"""

import json
import re
from typing import List, Dict, Any, Optional
from core.models import Violation, Severity
from utils.helpers import safe_log

class ResponseParser:
    """
    Robust parser for AI responses.
    """

    @staticmethod
    def parse_to_violations(raw_text: str) -> List[Violation]:
        cleaned_json = ResponseParser._extract_json_structure(raw_text)
        
        if not cleaned_json:
            safe_log(f"Parser: Could not find JSON. Text start: {raw_text[:100]}...", "ERROR")
            return []

        try:
            data = json.loads(cleaned_json)
        except json.JSONDecodeError:
            safe_log("Parser: JSON Error, attempting repair...", "WARNING")
            healed_json = ResponseParser._heuristic_fix_json(cleaned_json)
            try:
                data = json.loads(healed_json)
            except json.JSONDecodeError:
                return []

        return ResponseParser._map_data_to_violations(data)

    @staticmethod
    def _extract_json_structure(text: str) -> Optional[str]:
        if not text: return None
        text = text.strip()
        
        # 1. Try Code Block
        code_block = re.search(r'```(?:json)?\s*([\{\[][\s\S]*?[\]\}])\s*```', text)
        if code_block: return code_block.group(1)

        # 2. Try Greedy Search (Finds largest valid JSON wrapper)
        match = re.search(r'([\{\[])[\s\S]*([\}\]])', text)
        if match: return match.group(0)
            
        return None

    @staticmethod
    def _heuristic_fix_json(bad_json: str) -> str:
        return bad_json.replace('\t', '    ').replace('\r', '')

    @staticmethod
    def _map_data_to_violations(data: Any) -> List[Violation]:
        raw_list = []

        # === CRITICAL FIX: Handle Dict vs List ===
        if isinstance(data, dict):
            # New Prompt Format: {"violations": [...]}
            raw_list = data.get('violations', [])
        elif isinstance(data, list):
            # Old Prompt Format: [{"violation_type":...}, ...]
            for item in data:
                if isinstance(item, dict):
                    if 'violations' in item and isinstance(item['violations'], list):
                        raw_list.extend(item['violations']) # Flatten nested chunks
                    else:
                        raw_list.append(item) # It's a direct violation object

        if not isinstance(raw_list, list):
            return []

        # Convert to Models
        final_violations = []
        for v_dict in raw_list:
            if not isinstance(v_dict, dict): continue
            try:
                # Safely extract fields with defaults
                sev_str = v_dict.get('severity', 'medium')
                
                violation = Violation(
                    problematic_text=v_dict.get('problematic_text') or 'N/A',
                    violation_type=v_dict.get('violation_type') or 'Unknown',
                    explanation=v_dict.get('explanation') or 'No explanation',
                    guideline_section=str(v_dict.get('guideline_section') or 'N/A'),
                    page_number=v_dict.get('page_number') or 0,
                    severity=Severity.from_string(sev_str),
                    suggested_rewrite=v_dict.get('suggested_rewrite') or 'N/A',
                    # New Translation Fields
                    translation=v_dict.get('translation'),
                    rewrite_translation=v_dict.get('rewrite_translation'),
                    chunk_language=v_dict.get('chunk_language', 'English')
                )
                final_violations.append(violation)
            except Exception as e:
                safe_log(f"Parser skipped item due to error: {e}", "WARNING")
                continue
                
        return final_violations
