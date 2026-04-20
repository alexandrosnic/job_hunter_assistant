import datetime
import re
from pathlib import Path
from typing import Any

from fpdf import FPDF

STYLE_PRESETS: dict[str, dict[str, Any]] = {
    "modern": {
        "page": {"format": "Letter", "margins": {"left": 1.0, "top": 1.0, "right": 1.0, "bottom": 1.0}},
        "header": {"font": "Helvetica", "size": 14, "bold": True, "align": "C"},
        "contact": {"font": "Helvetica", "size": 10, "bold": False, "align": "C"},
        "date": {"font": "Helvetica", "size": 11, "bold": False, "spacing_before": 0.5, "spacing_after": 0.3},
        "body": {"font": "Helvetica", "size": 11, "line_height": 0.25},
    },
    "classic": {
        "page": {"format": "Letter", "margins": {"left": 1.25, "top": 1.0, "right": 1.0, "bottom": 1.0}},
        "header": {"font": "Times", "size": 12, "bold": True, "align": "L"},
        "contact": {"font": "Times", "size": 10, "bold": False, "align": "L"},
        "date": {"font": "Times", "size": 11, "bold": False, "spacing_before": 0.5, "spacing_after": 0.3},
        "body": {"font": "Times", "size": 11, "line_height": 0.25},
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    result = base.copy()
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def save_cover_letter_pdf(
    content: str,
    company: str,
    output_dir: str | Path | None,
    name: str | None = None,
    contact: str | None = None,
    style: str = "modern",
    template: dict | None = None,
) -> Path:
    company_slug = re.sub(r"[^a-z0-9]+", "-", company.lower()).strip("-") or "company"
    filename = f"{datetime.date.today().isoformat()}-{company_slug}-cover-letter.pdf"

    if not output_dir:
        output_dir = Path("output/cover-letters")
    else:
        output_dir = Path(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / filename

    # Build config: start from preset, deep-merge user template overrides on top
    preset = STYLE_PRESETS.get(style, STYLE_PRESETS["modern"])
    cfg = _deep_merge(preset, template or {})

    margins = cfg["page"]["margins"]
    h_cfg = cfg["header"]
    c_cfg = cfg["contact"]
    d_cfg = cfg["date"]
    b_cfg = cfg["body"]

    pdf = FPDF(unit="in", format=cfg["page"]["format"])
    pdf.add_page()
    pdf.set_margins(left=margins["left"], top=margins["top"], right=margins["right"])
    pdf.set_auto_page_break(auto=True, margin=margins["bottom"])

    # Name header
    pdf.set_font(h_cfg["font"], style="B" if h_cfg["bold"] else "", size=h_cfg["size"])
    display_name = name if name and name.strip() else "Candidate Name"
    pdf.cell(w=0, h=0.25, txt=display_name, new_x="LMARGIN", new_y="NEXT", align=h_cfg["align"])

    # Contact line
    pdf.set_font(c_cfg["font"], style="B" if c_cfg["bold"] else "", size=c_cfg["size"])
    display_contact = contact if contact and contact.strip() else "email@example.com | 555-0100"
    pdf.cell(w=0, h=0.25, txt=display_contact, new_x="LMARGIN", new_y="NEXT", align=c_cfg["align"])

    pdf.ln(d_cfg["spacing_before"])

    # Date
    pdf.set_font(d_cfg["font"], style="B" if d_cfg["bold"] else "", size=d_cfg["size"])
    date_str = datetime.date.today().strftime("%B %d, %Y")
    pdf.cell(w=0, h=0.2, txt=date_str, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(d_cfg["spacing_after"])

    # Body
    pdf.set_font(b_cfg["font"], size=b_cfg["size"])
    content_encoded = content.encode("latin-1", "replace").decode("latin-1")
    pdf.multi_cell(w=0, h=b_cfg["line_height"], txt=content_encoded)

    pdf.output(str(target))
    return target

