"""
Generates a downloadable Executive Hiring Audit PDF Report from the ATS evaluation data.
"""
import io
import sys
from pathlib import Path
from fpdf import FPDF
from datetime import datetime

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

class ExecutiveAuditPDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(30, 41, 59)
        self.cell(0, 8, "EXECUTIVE ATS CANDIDATE AUDIT REPORT", border=0, align="L")
        self.set_font("Helvetica", "", 9)
        self.set_text_color(100, 116, 139)
        self.cell(0, 8, datetime.now().strftime("%B %d, %Y"), border=0, align="R")
        self.ln(10)
        self.set_draw_color(226, 232, 240)
        self.line(15, 20, self.w - 15, 20)
        self.ln(2)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(148, 163, 184)
        self.cell(0, 10, f"Confidential Recruiting Dossier - Page {self.page_no()}", align="C")

def generate_audit_pdf(analysis_text: str, role_title: str = "Candidate Evaluation") -> bytes:
    """Generates PDF bytes of the executive audit report."""
    pdf = ExecutiveAuditPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(15, 15, 15)
    pdf.add_page()

    # Title section
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(pdf.epw, 10, f"Role: {role_title[:50]}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    lines = analysis_text.strip().split("\n")
    for line in lines:
        line_clean = line.strip().replace("\u2022", "-").encode("latin-1", "replace").decode("latin-1")
        if not line_clean:
            pdf.ln(2)
            continue

        if line_clean.startswith("---") or line_clean.startswith("==="):
            pdf.set_draw_color(203, 213, 225)
            pdf.line(pdf.get_x(), pdf.get_y(), pdf.get_x() + pdf.epw, pdf.get_y())
            pdf.ln(3)
        elif line_clean.isupper() or "SNAPSHOT" in line_clean or "RANKINGS" in line_clean or "MATRIX" in line_clean:
            pdf.set_font("Helvetica", "B", 12)
            pdf.set_text_color(30, 58, 138)
            pdf.multi_cell(w=pdf.epw, h=6, text=line_clean, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1)
        elif any(line_clean.startswith(p) for p in ["*1.", "*2.", "*3.", "*4.", "*5.", "*6."]):
            pdf.set_font("Helvetica", "B", 11)
            pdf.set_text_color(15, 23, 42)
            pdf.multi_cell(w=pdf.epw, h=6, text=line_clean.replace("*", ""), new_x="LMARGIN", new_y="NEXT")
        elif "ATS Score:" in line_clean:
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(5, 150, 105)
            pdf.multi_cell(w=pdf.epw, h=5, text=line_clean.replace("*", ""), new_x="LMARGIN", new_y="NEXT")
        elif line_clean.startswith("- "):
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(71, 85, 105)
            pdf.multi_cell(w=pdf.epw, h=5, text="   - " + line_clean[2:], new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(71, 85, 105)
            pdf.multi_cell(w=pdf.epw, h=5, text=line_clean.replace("*", ""), new_x="LMARGIN", new_y="NEXT")

    buf = io.BytesIO()
    pdf.output(buf)
    buf.seek(0)
    return buf.getvalue()
