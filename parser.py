import io
from pathlib import Path
from pypdf import PdfReader
import docx

def extract_text_from_bytes(file_bytes: bytes, filename: str) -> str:
    """Extract clean text from PDF, DOCX, or TXT/MD bytes."""
    ext = Path(filename).suffix.lower()
    text = ""
    
    if ext == ".pdf":
        try:
            reader = PdfReader(io.BytesIO(file_bytes))
            pages_text = []
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    pages_text.append(page_text)
            text = "\n".join(pages_text)
        except Exception as e:
            text = f"[Error reading PDF: {e}]"
            
    elif ext in [".docx", ".doc"]:
        try:
            doc = docx.Document(io.BytesIO(file_bytes))
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            text = "\n".join(paragraphs)
        except Exception as e:
            text = f"[Error reading DOCX: {e}]"
            
    else:  # Assume text or markdown
        try:
            text = file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text = file_bytes.decode("latin-1")
            except Exception:
                text = str(file_bytes)
                
    return text.strip()

def extract_text_from_file(file_path: str) -> str:
    """Extract text from local file path."""
    path = Path(file_path)
    if not path.exists():
        return ""
    with open(path, "rb") as f:
        return extract_text_from_bytes(f.read(), path.name)
