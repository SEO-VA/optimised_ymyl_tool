#!/usr/bin/env python3
"""
Response Parser Module - Robust V3
Handles the conversion of raw AI text strings into structured Python objects.
Updated: Fixes 'NoneType' crash by safely handling null values from AI.
"""

import json
import re
from typing import List, Dict, Any, Optional
from core.models import Violation, Severity
from utils.helpers import safe_log

class ResponseParser:
    """
    Robust parser for AI responses.
    Handles Markdown stripping, JSON repair, and Model mapping.
    """

    @staticmethod
    def parse_to_violations(raw_text: str) -> List[Violation]:
        """
        Main entry point: Converts raw AI text string -> List of Violation objects.
        """
        cleaned_json = ResponseParser._extract_json_structure(raw_text)
        
        if not cleaned_json:
            preview = raw_text[:500].replace('\n', ' ')
            safe_log(f"Parser: Could not find JSON structure. Response start: {preview}...", "ERROR")
            return []

        try:
            # 1. Try standard parse
            data = json.loads(cleaned_json)
        except json.JSONDecodeError:
            # 2. If failed, try "Healing" the JSON
            safe_log("Parser: JSON Error, attempting heuristic fix...", "WARNING")
            healed_json = ResponseParser._heuristic_fix_json(cleaned_json)
            try:
                data = json.loads(healed_json)
            except json.JSONDecodeError as e:
                safe_log(f"Parser: Fatal JSON error after healing: {e}", "ERROR")
                return []

        # 3. Convert raw list/dict to strict Violation models
        return ResponseParser._map_data_to_violations(data)

    @staticmethod
    def _extract_json_structure(text: str) -> Optional[str]:
        if not text: return None
        text = text.strip()
        
        # Strategy 1: Code blocks
        code_block = re.search(r'```(?:json)?\s*(\[[\s\S]*?\])\s*```', text)
        if code_block: return code_block.group(1)

        # Strategy 2: Greedy Substring (Find first [ and last ])
        start_index = text.find('[')
        end_index = text.rfind(']')
        
        if start_index != -1 and end_index != -1 and end_index > start_index:
            return text[start_index : end_index + 1]
            
        return None

    @staticmethod
    def _heuristic_fix_json(bad_json: str) -> str:
        # Basic fix: common unescaped control characters
        fixed = bad_json.replace('\t', '    ').replace('\r', '')
        return fixed

    @staticmethod
    def _map_data_to_violations(data: Any) -> List[Violation]:
        violations: List[Violation] = []
        
        if not isinstance(data, list):
            safe_log("Parser: Expected JSON list, got something else", "ERROR")
            return []

        for section in data:
            if not isinstance(section, dict): continue
                
            raw_violations = section.get('violations')
            
            # Handle "no violation found" string case
            if isinstance(raw_violations, str) or not raw_violations:
                continue 
                
            if isinstance(raw_violations, list):
                for v_dict in raw_violations:
                    if not isinstance(v_dict, dict): continue
                        
                    try:
                        # --- SAFE MAPPING (Fixes 'NoneType' error) ---
                        # We use 'or' to default to a string if the value is None
                        
                        sev_val = v_dict.get('severity')
                        if sev_val is None: sev_val = 'medium' # Default safety
                        
                        violation = Violation(
                            problematic_text=v_dict.get('problematic_text') or 'N/A',
                            violation_type=v_dict.get('violation_type') or 'Unknown',
                            explanation=v_dict.get('explanation') or 'No explanation',
                            guideline_section=str(v_dict.get('guideline_section') or 'N/A'),
                            page_number=v_dict.get('page_number') or 0,
                            severity=Severity.from_string(sev_val),
                            suggested_rewrite=v_dict.get('suggested_rewrite') or 'N/A',
                            
                            # Optional Multilingual fields
                            translation=v_dict.get('translation'),
                            rewrite_translation=v_dict.get('rewrite_translation'),
                            chunk_language=v_dict.get('chunk_language') or 'English'
                        )
                        violations.append(violation)
                    except Exception as e:
                        safe_log(f"Parser: Failed to map individual violation: {e}", "WARNING")
                        continue

        return violations
