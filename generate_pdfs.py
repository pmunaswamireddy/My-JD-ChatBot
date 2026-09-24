"""
Generates clean, professional PDF documents for all JDs and Resumes
in both sample_data/ and ready_to_upload/ folders using fpdf2.
"""
import sys
from pathlib import Path
from fpdf import FPDF

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = Path(__file__).resolve().parent
SAMPLE_DIR = BASE_DIR / "sample_data"
UPLOAD_DIR = BASE_DIR / "ready_to_upload"
JD_UPLOAD_DIR = UPLOAD_DIR / "1_Job_Descriptions"
RESUME_UPLOAD_DIR = UPLOAD_DIR / "2_Candidate_Resumes"

def create_pdf(text: str, output_path: Path):
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(15, 15, 15)
    pdf.add_page()
    
    # Document header
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(100, 116, 139)
    pdf.cell(pdf.epw, 7, "JOB FIT & ATS EVALUATION SYSTEM", align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    lines = text.strip().split("\n")
    is_first = True

    for line in lines:
        line_clean = line.strip()
        if not line_clean:
            pdf.ln(2)
            continue

        # Clean non-latin-1 characters and replace bullets
        safe_line = line_clean.replace("\u2022", "-").encode("latin-1", "replace").decode("latin-1")

        # Headings
        if is_first or safe_line.isupper() or any(safe_line.startswith(h) for h in ["Job Title:", "Company:", "OVERVIEW", "TECHNICAL SKILLS", "EXPERIENCE", "EDUCATION", "SUMMARY", "RESPONSIBILITIES", "REQUIREMENTS"]):
            pdf.set_font("Helvetica", "B", 12 if is_first else 11)
            pdf.set_text_color(15, 23, 42)
            pdf.multi_cell(w=pdf.epw, h=6, text=safe_line, new_x="LMARGIN", new_y="NEXT")
            is_first = False
            pdf.ln(1)
        elif safe_line.startswith("- "):
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(51, 65, 85)
            bullet_text = "   - " + safe_line[2:]
            pdf.multi_cell(w=pdf.epw, h=5, text=bullet_text, new_x="LMARGIN", new_y="NEXT")

        else:
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(71, 85, 105)
            pdf.multi_cell(w=pdf.epw, h=5, text=safe_line, new_x="LMARGIN", new_y="NEXT")

    pdf.output(str(output_path))
    print(f"✓ Created PDF: {output_path.name}")

def main():
    print("📄 Generating PDF files for JDs and Resumes...\n")
    
    # 1. sample_data/
    for tf in SAMPLE_DIR.glob("*.txt"):
        create_pdf(tf.read_text(encoding="utf-8"), SAMPLE_DIR / f"{tf.stem}.pdf")

    # 2. ready_to_upload/1_Job_Descriptions/
    for tf in JD_UPLOAD_DIR.glob("*.txt"):
        create_pdf(tf.read_text(encoding="utf-8"), JD_UPLOAD_DIR / f"{tf.stem}.pdf")

    # 3. ready_to_upload/2_Candidate_Resumes/
    for tf in RESUME_UPLOAD_DIR.glob("*.txt"):
        create_pdf(tf.read_text(encoding="utf-8"), RESUME_UPLOAD_DIR / f"{tf.stem}.pdf")

    print("\n🎉 All PDF files generated successfully!")

if __name__ == "__main__":
    main()
