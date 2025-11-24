#!/usr/bin/env python3
"""
Response Parser Module
Updated: Verified 'import re' and 'Severity' import.
"""

import json
import re  # <--- CRITICAL FIX
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
        code_block = re.search(r'```(?:json)?\s*(\[[\s\S]*?\])\s*```', text)
        if code_block: return code_block.group(1)

        # Greedy Substring
        start_index = text.find('[')
        end_index = text.rfind(']')
        if start_index != -1 and end_index != -1 and end_index > start_index:
            return text[start_index : end_index + 1]
            
        return None

    @staticmethod
    def _heuristic_fix_json(bad_json: str) -> str:
        return bad_json.replace('\t', '    ').replace('\r', '')

    @staticmethod
    def _map_data_to_violations(data: Any) -> List[Violation]:
        violations: List[Violation] = []
        if not isinstance(data, list): return []

        for section in data:
            if not isinstance(section, dict): continue
            raw_violations = section.get('violations')
            if isinstance(raw_violations, str) or not raw_violations: continue
                
            if isinstance(raw_violations, list):
                for v_dict in raw_violations:
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
                        continue
        return violations
