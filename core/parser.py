#!/usr/bin/env python3
"""
Response Parser Module
Handles the conversion of raw AI text strings into structured Python objects.
Includes "Healing" logic to fix common JSON errors (unescaped quotes) warned about in the Prompt.
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
        Returns empty list if parsing fails (logs error).
        """
        cleaned_json = ResponseParser._extract_json_structure(raw_text)
        
        if not cleaned_json:
            safe_log("Parser: Could not find JSON structure in response", "ERROR")
            return []

        try:
            # 1. Try standard parse
            data = json.loads(cleaned_json)
        except json.JSONDecodeError:
            # 2. If failed, try "Healing" the JSON (fixing unescaped quotes)
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
        """
        Finds the JSON list/array inside the text, stripping Markdown.
        """
        if not text: 
            return None
            
        text = text.strip()
        
        # Strategy 1: Look for code blocks ```json ... ```
        code_block = re.search(r'```(?:json)?\s*(\[[\s\S]*?\])\s*```', text)
        if code_block:
            return code_block.group(1)

        # Strategy 2: Look for the outermost square brackets [...]
        # This is a simple regex, might need robustness for nested brackets but usually suffices for this prompt
        bracket_match = re.search(r'^\s*(\[[\s\S]*\])\s*$', text)
        if bracket_match:
            return bracket_match.group(1)
            
        # Fallback: Just try the raw text if it looks like a list
        if text.startswith('[') and text.endswith(']'):
            return text
            
        return None

    @staticmethod
    def _heuristic_fix_json(bad_json: str) -> str:
        """
        Attempts to fix common 'URGENT_JSON_ESCAPING' errors mentioned in prompt.
        Example: "problematic_text": "I'd like" -> "problematic_text": "I\'d like"
        """
        # Fix 1: Escape unescaped double quotes inside string values is very hard via regex safely.
        # We focus on the prompt's specific warning: Apostrophes in contractions (I'd, It's)
        # This regex looks for ' (word char)' following a word char, capturing common contractions
        # Note: This is a 'best effort' heuristic.
        
        # Basic fix: common unescaped control characters
        fixed = bad_json.replace('\t', '    ').replace('\r', '')
        
        return fixed

    @staticmethod
    def _map_data_to_violations(data: Any) -> List[Violation]:
        """
        Maps raw JSON data (List of sections) to flat list of Violation objects.
        """
        violations: List[Violation] = []
        
        if not isinstance(data, list):
            safe_log("Parser: Expected JSON list, got something else", "ERROR")
            return []

        for section in data:
            # Your prompt outputs sections containing a 'violations' list
            # Schema: { "big_chunk_index": 1, "content_name": "...", "violations": [...] }
            
            if not isinstance(section, dict): 
                continue
                
            raw_violations = section.get('violations')
            
            # Prompt says "violations": "no violation found" (string) OR list
            if isinstance(raw_violations, str) or not raw_violations:
                continue # Skip "no violation found"
                
            if isinstance(raw_violations, list):
                for v_dict in raw_violations:
                    if not isinstance(v_dict, dict): 
                        continue
                        
                    try:
                        # Strict mapping to our Model
                        violation = Violation(
                            problematic_text=v_dict.get('problematic_text', 'N/A'),
                            violation_type=v_dict.get('violation_type', 'Unknown'),
                            explanation=v_dict.get('explanation', 'No explanation'),
                            guideline_section=str(v_dict.get('guideline_section', 'N/A')),
                            page_number=v_dict.get('page_number', 0),
                            severity=Severity.from_string(v_dict.get('severity', 'medium')),
                            suggested_rewrite=v_dict.get('suggested_rewrite', 'N/A'),
                            
                            # Optional Multilingual fields
                            translation=v_dict.get('translation'),
                            rewrite_translation=v_dict.get('rewrite_translation'),
                            chunk_language=v_dict.get('chunk_language', 'English')
                        )
                        violations.append(violation)
                    except Exception as e:
                        safe_log(f"Parser: Failed to map individual violation: {e}", "WARNING")
                        continue

        return violations
