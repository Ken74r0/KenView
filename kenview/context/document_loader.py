import os
from pathlib import Path

def extract_text(file_path):
    """
    Extracts text from .txt, .md. 
    Stubs for .pdf and .docx (would normally use pypdf or python-docx).
    """
    path = Path(file_path)
    if not path.exists():
        return ""
    
    ext = path.suffix.lower()
    
    if ext in [".txt", ".md"]:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    
    # Placeholder for PDF/DOCX
    return f"[Unsupported file type: {ext}. Re-saving as .txt recommended.]"
