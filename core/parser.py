#!/usr/bin/env python3
"""
Response Parser Module
Updated: Supports both Dictionary (New) and List (Old) JSON structures.
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
            preview = raw_text[:500].replace('\n', ' ')
            safe_log(f"Parser: Could not find JSON structure. Response start: {preview}...", "ERROR")
            return []

        try:
            data = json.loads(cleaned_json)
        except json.JSONDecodeError:
            safe_log("Parser: JSON Error, attempting heuristic fix...", "WARNING")
            healed_json = ResponseParser._heuristic_fix_json(cleaned_json)
            try:
                data = json.loads(healed_json)
            except json.JSONDecodeError as e:
                safe_log(f"Parser: Fatal JSON error after healing: {e}", "ERROR")
                return []

        return ResponseParser._map_data_to_violations(data)

    @staticmethod
    def _extract_json_structure(text: str) -> Optional[str]:
        if not text: return None
        text = text.strip()
        
        # Code blocks
        code_block = re.search(r'```(?:json)?\s*([\{\[][\s\S]*?[\]\}])\s*```', text)
        if code_block: return code_block.group(1)

        # Greedy Substring (Find first { or [ and last } or ])
        # Updated to support Dict start '{'
        match = re.search(r'([\{\[])[\s\S]*([\}\]])', text)
        if match:
            return match.group(0)
            
        return None

    @staticmethod
    def _heuristic_fix_json(bad_json: str) -> str:
        return bad_json.replace('\t', '    ').replace('\r', '')

    @staticmethod
    def _map_data_to_violations(data: Any) -> List[Violation]:
        violations: List[Violation] = []
        raw_objects = []

        # SCENARIO 1: New Format (Dictionary with "violations" key)
        if isinstance(data, dict):
            raw_objects = data.get('violations', [])
            
        # SCENARIO 2: Old Format (List of Chunk Objects)
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    # Extract from 'violations' key inside chunk
                    if 'violations' in item and isinstance(item['violations'], list):
                        raw_objects.extend(item['violations'])
                    # Or if the list is just a flat list of violation objects (Legacy)
                    elif 'violation_type' in item:
                        raw_objects.append(item)

        if not isinstance(raw_objects, list):
            return []

        # Process the flattened list of raw violation dictionaries
        for v_dict in raw_objects:
            if not isinstance(v_dict, dict): continue
            try:
                sev_val = v_dict.get('severity')
                if sev_val is None: sev_val = 'medium'
                
                violation = Violation(
                    problematic_text=v_dict.get('problematic_text') or 'N/A',
                    violation_type=v_dict.get('violation_type') or 'Unknown',
                    explanation=v_dict.get('explanation') or 'No explanation',
                    guideline_section=str(v_dict.get('guideline_section') or 'N/A'),
                    page_number=v_dict.get('page_number') or 0,
                    severity=Severity.from_string(sev_val),
                    suggested_rewrite=v_dict.get('suggested_rewrite') or 'N/A',
                    translation=v_dict.get('translation'),
                    rewrite_translation=v_dict.get('rewrite_translation'),
                    chunk_language=v_dict.get('chunk_language') or 'English'
                )
                violations.append(violation)
            except Exception as e:
                safe_log(f"Parser Error skipping item: {e}", "WARNING")
                continue
                
        return violations
