import io
import re
from pathlib import Path
from pypdf import PdfReader
import docx

def extract_text_from_bytes(file_bytes: bytes, filename: str) -> str:
    """
    Extract clean, readable text from any supported format:
    PDF, DOCX, DOC, TXT, MD, RTF, HTML, CSV.
    """
    ext = Path(filename).suffix.lower()
    text = ""
    
    # 1. PDF
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
            text = f"[Error reading PDF {filename}: {e}]"
            
    # 2. DOCX & DOC
    elif ext in [".docx", ".doc"]:
        parsed_successfully = False
        try:
            doc = docx.Document(io.BytesIO(file_bytes))
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            text = "\n".join(paragraphs)
            parsed_successfully = bool(text.strip())
        except Exception:
            parsed_successfully = False

        # Fallback for binary .doc or damaged docx: extract printable text strings
        if not parsed_successfully:
            try:
                # Find all continuous printable character sequences (length >= 3)
                words = re.findall(rb"[\x20-\x7E\t\n\r]{3,}", file_bytes)
                text = " ".join([w.decode("latin-1", errors="ignore") for w in words])
            except Exception as e:
                text = f"[Error reading DOC: {e}]"

    # 3. RTF / Rich Text Format
    elif ext == ".rtf":
        try:
            raw = file_bytes.decode("utf-8", errors="ignore")
            # Strip simple rtf tags
            text = re.sub(r"\\[a-zA-Z0-9\-]+ ?", " ", raw)
            text = re.sub(r"[{}]", " ", text)
        except Exception:
            text = str(file_bytes)

    # 4. Text / Markdown / Code / Plain
    else:
        for encoding in ["utf-8", "utf-16", "latin-1", "cp1252"]:
            try:
                text = file_bytes.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if not text:
            text = file_bytes.decode("utf-8", errors="ignore")
                
    return text.strip()

def extract_text_from_file(file_path: str) -> str:
    """Extract text from local file path."""
    path = Path(file_path)
    if not path.exists():
        return ""
    with open(path, "rb") as f:
        return extract_text_from_bytes(f.read(), path.name)
