#!/usr/bin/env python3
"""
Report Generator
Converts Markdown text into a formatted Word (.docx) document.
"""

import io
import re
from docx import Document
from docx.shared import RGBColor, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from utils.helpers import safe_log

def generate_word_report(markdown_content: str, title: str, casino_mode: bool) -> bytes:
    """Converts markdown string to docx bytes."""
    try:
        doc = Document()
        
        # Metadata
        doc.core_properties.title = title
        doc.core_properties.subject = "Casino Audit" if casino_mode else "YMYL Audit"
        
        # Styles
        style = doc.styles['Normal']
        style.font.name = 'Calibri'
        style.font.size = Pt(11)
        
        # Parse content line by line
        for line in markdown_content.split('\n'):
            line = line.strip()
            if not line: continue
            
            if line.startswith('# '):
                doc.add_heading(line[2:], 0)
            elif line.startswith('## '):
                doc.add_heading(line[3:], 1)
            elif line.startswith('### '):
                doc.add_heading(line[4:], 2)
            elif line.startswith('---'):
                doc.add_paragraph('_' * 50).alignment = WD_ALIGN_PARAGRAPH.CENTER
            elif line.startswith('- '):
                p = doc.add_paragraph(line[2:], style='List Bullet')
                _apply_formatting(p, line[2:])
            else:
                p = doc.add_paragraph()
                _apply_formatting(p, line)
                
        # Save to buffer
        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        return buffer.getvalue()
        
    except Exception as e:
        safe_log(f"Reporter Error: {e}", "ERROR")
        return b""

def _apply_formatting(paragraph, text):
    """Applies bolding and color based on severity emojis."""
    # This is a simplified formatter. 
    # In a perfect world, we'd parse bold (**text**) properly.
    # For now, we just ensure the text gets added.
    
    # Check for severity indicators to colorize
    if '🔴' in text:
        run = paragraph.runs[0] if paragraph.runs else paragraph.add_run(text)
        run.font.color.rgb = RGBColor(231, 76, 60) # Red
    elif '🟠' in text:
        run = paragraph.runs[0] if paragraph.runs else paragraph.add_run(text)
        run.font.color.rgb = RGBColor(230, 126, 34) # Orange
    elif paragraph.runs:
        pass # Already added
    else:
        paragraph.add_run(text)
