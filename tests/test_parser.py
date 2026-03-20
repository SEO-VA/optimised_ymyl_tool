#!/usr/bin/env python3

import unittest

from core.parser import ResponseParser


VALID_VIOLATION = {
    "problematic_text": "Bet now, guaranteed riches.",
    "violation_type": "Overpromising outcome",
    "explanation": "Claims guaranteed results in a YMYL context.",
    "guideline_section": "2.1",
    "page_number": 7,
    "severity": "high",
    "suggested_rewrite": "Bet responsibly and avoid guarantees.",
}


class ResponseParserTests(unittest.TestCase):
    def test_parse_structured_payload(self):
        violations, parse_success = ResponseParser.parse_payload_to_violations(
            {"violations": [VALID_VIOLATION]}
        )

        self.assertTrue(parse_success)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].violation_type, "Overpromising outcome")

    def test_parse_legacy_text_fallback(self):
        raw_text = """```json
        {"violations": [{"problematic_text": "Bet now, guaranteed riches.", "violation_type": "Overpromising outcome", "explanation": "Claims guaranteed results in a YMYL context.", "guideline_section": "2.1", "page_number": 7, "severity": "high", "suggested_rewrite": "Bet responsibly and avoid guarantees."}]}
        ```"""

        violations, parse_success = ResponseParser.parse_text_to_violations(raw_text)

        self.assertTrue(parse_success)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].severity.value, "high")

    def test_parse_malformed_output(self):
        violations, parse_success = ResponseParser.parse_text_to_violations("not valid json")

        self.assertFalse(parse_success)
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
