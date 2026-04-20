import datetime
import re
from pathlib import Path

from fpdf import FPDF

def save_cover_letter_pdf(
    content: str, 
    company: str, 
    output_dir: str | Path | None, 
    name: str | None = None, 
    contact: str | None = None,
    style: str = "modern"
) -> Path:
    
    company_slug = re.sub(r"[^a-z0-9]+", "-", company.lower()).strip("-") or "company"
    filename = f"{datetime.date.today().isoformat()}-{company_slug}-cover-letter.pdf"
    
    if not output_dir:
        output_dir = Path("output/cover-letters")
    else:
        output_dir = Path(output_dir)
        
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / filename
    
    # Initialize PDF template structure
    pdf = FPDF(unit="in", format="Letter")
    pdf.add_page()
    pdf.set_margins(left=1.0, top=1.0, right=1.0)
    pdf.set_auto_page_break(auto=True, margin=1.0)
    
    font_family = "Helvetica" if style == "modern" else "Times"
    align_header = "C" if style == "modern" else "L"
    
    # Add Header (Candidate Name)
    pdf.set_font(font_family, style="B", size=14 if style == "modern" else 12)
    display_name = name if name and name.strip() else "Candidate Name"
    pdf.cell(w=0, h=0.25, text=display_name, new_x="LMARGIN", new_y="NEXT", align=align_header)
    
    # Add Subheader (Contact details)
    pdf.set_font(font_family, size=10)
    display_contact = contact if contact and contact.strip() else "email@example.com | 555-0100"
    pdf.cell(w=0, h=0.25, text=display_contact, new_x="LMARGIN", new_y="NEXT", align=align_header)
    
    pdf.ln(0.5)
    
    # Add Date
    pdf.set_font(font_family, size=11)
    date_str = datetime.date.today().strftime("%B %d, %Y")
    pdf.cell(w=0, h=0.2, text=date_str, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(0.3)
    
    # Add Body Content
    pdf.set_font(font_family, size=11)
    
    # Standardize content slightly for typical PDF display (clean encodings for FPDF built-in fonts)
    content_encoded = content.encode('latin-1', 'replace').decode('latin-1')
    pdf.multi_cell(w=0, h=0.25, text=content_encoded)
    
    pdf.output(str(target))
    return target
