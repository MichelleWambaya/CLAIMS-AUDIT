"""
Server-side PDF export (§7). Two paths, chosen by what's being exported:

  1. `pptx_to_pdf` — the simplest, most robust route: build the PPTX
     (reports/pptx_generator.py) then convert it via LibreOffice headless.
     This is what a "PDF of the presentation slides" request should use —
     it guarantees pixel parity with the PPTX rather than re-implementing
     layout twice.
  2. `dashboard_to_pdf` — a direct ReportLab-built PDF for "PDF of the
     current dashboard view" (KPIs + table), for cases where a slide
     format doesn't fit and a plain report layout is more useful.
"""
import subprocess
import tempfile
import os
from typing import Any, Dict, List

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from .brand import COLOR_ORANGE, COLOR_BLACK, COLOR_WHITE
from .pptx_generator import build_presentation


def pptx_to_pdf(pptx_path: str, output_dir: str) -> str:
    """Convert an already-built PPTX to PDF via headless LibreOffice.
    Returns the resulting PDF path."""
    subprocess.run(
        ["soffice", "--headless", "--convert-to", "pdf", "--outdir", output_dir, pptx_path],
        check=True, timeout=120,
    )
    base = os.path.splitext(os.path.basename(pptx_path))[0]
    return os.path.join(output_dir, f"{base}.pdf")


def presentation_view_to_pdf(
    session_name: str,
    kpis: Dict[str, Any],
    top_categories: List[Dict[str, Any]],
    priority_flags: List[Dict[str, Any]],
    recommendations: List[str],
    output_dir: str,
) -> str:
    """Builds the same 5-slide deck as pptx_generator, then converts it —
    so 'PDF export of the presentation view' is always pixel-identical to
    the PPTX, not a second hand-maintained layout."""
    with tempfile.TemporaryDirectory() as tmp:
        pptx_path = os.path.join(tmp, "presentation.pptx")
        build_presentation(session_name, kpis, top_categories, priority_flags, recommendations, pptx_path)
        return pptx_to_pdf(pptx_path, output_dir)


def dashboard_view_to_pdf(
    session_name: str,
    kpis: Dict[str, Any],
    table_rows: List[Dict[str, Any]],
    table_headers: List[str],
    output_path: str,
) -> str:
    """A plain, AAR-branded report layout for 'PDF of the current
    dashboard view' — KPI row + data table — for one-click export straight
    from the dashboard rather than the slide deck."""
    doc = SimpleDocTemplate(output_path, pagesize=A4,
                             leftMargin=0.6 * inch, rightMargin=0.6 * inch,
                             topMargin=0.6 * inch, bottomMargin=0.6 * inch)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "AARTitle", parent=styles["Title"], textColor=colors.HexColor(f"#{COLOR_BLACK}"),
        fontSize=20, spaceAfter=4,
    )
    subtitle_style = ParagraphStyle(
        "AARSubtitle", parent=styles["Normal"], textColor=colors.HexColor(f"#{COLOR_ORANGE}"),
        fontSize=12, spaceAfter=20,
    )

    elements = [
        Paragraph("Claims Forensic Audit — AAR Insurance Kenya", title_style),
        Paragraph(session_name, subtitle_style),
    ]

    kpi_data = [list(kpis.keys()), list(kpis.values())]
    kpi_table = Table(kpi_data, hAlign="LEFT")
    kpi_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("FONTSIZE", (0, 1), (-1, 1), 16),
        ("TEXTCOLOR", (0, 1), (-1, 1), colors.HexColor(f"#{COLOR_ORANGE}")),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F2F2F2")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.white),
    ]))
    elements.append(kpi_table)
    elements.append(Spacer(1, 24))

    table_data = [table_headers] + [[str(r.get(h, "")) for h in table_headers] for r in table_rows]
    detail_table = Table(table_data, hAlign="LEFT", repeatRows=1)
    detail_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(f"#{COLOR_BLACK}")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F2F2")]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#DDDDDD")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(detail_table)

    doc.build(elements)
    return output_path
