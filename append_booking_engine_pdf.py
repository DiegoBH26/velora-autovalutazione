"""Aggiorna i due PDF storici con una pagina di evidenza sul booking engine."""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


ROOT = Path(__file__).resolve().parent
FILES = (
    (ROOT / "src" / "perla-saracena-audit.json", ROOT / "src" / "perla-saracena-report.pdf"),
    (ROOT / "src" / "santantonio-audit.json", ROOT / "src" / "santantonio-report.pdf"),
)
PURPLE = colors.HexColor("#23124A")
GOLD = colors.HexColor("#C8A96B")
GRAY = colors.HexColor("#52627A")
PALE = colors.HexColor("#F7F4FB")
MARKER = "Appendice booking engine e fornitore"


def appendix(data: dict) -> bytes:
    pdfmetrics.registerFont(TTFont("Velora", "C:/Windows/Fonts/arial.ttf"))
    pdfmetrics.registerFont(TTFont("Velora-Bold", "C:/Windows/Fonts/arialbd.ttf"))
    styles = {
        "eyebrow": ParagraphStyle("eyebrow", fontName="Velora-Bold", fontSize=9, leading=13, textColor=GOLD, spaceAfter=11),
        "title": ParagraphStyle("title", fontName="Velora-Bold", fontSize=22, leading=27, textColor=PURPLE, spaceAfter=12),
        "body": ParagraphStyle("body", fontName="Velora", fontSize=10, leading=15, textColor=PURPLE, spaceAfter=10),
        "small": ParagraphStyle("small", fontName="Velora", fontSize=8.5, leading=12, textColor=GRAY, spaceAfter=7),
        "cell": ParagraphStyle("cell", fontName="Velora", fontSize=9, leading=13, textColor=PURPLE, alignment=TA_LEFT),
        "label": ParagraphStyle("label", fontName="Velora-Bold", fontSize=9, leading=13, textColor=PURPLE),
    }
    engine = data["bookingEngine"]
    status = {"provider_identified": "Fornitore riconosciuto dal dominio del percorso pubblico",
              "provider_unknown": "Prenotazione diretta visibile; fornitore non identificato",
              "not_found_in_page": "Percorso di prenotazione non rilevato nel campione"}.get(engine["status"], "Non verificato")
    url = engine.get("url", "")
    safe_url = escape(url, {'"': '&quot;'})
    display_url = f'<link href="{safe_url}" color="#2853A3">{escape(url)}</link>' if url else "Non disponibile"
    rows = [
        ("Esito", status),
        ("Fornitore", engine.get("provider") or "Non identificato con certezza"),
        ("Percorso", engine.get("mode") or "Non verificato"),
        ("URL di prova", display_url),
        ("Evidenza", escape(engine.get("evidence") or "Nessun riscontro registrato")),
    ]
    table = Table([[Paragraph(label, styles["label"]), Paragraph(value, styles["cell"])] for label, value in rows],
                  colWidths=[42 * mm, 130 * mm], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), PALE),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#DED6EC")),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#DED6EC")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    story = [
        Paragraph("VELORA / AUDIT WEB", styles["eyebrow"]),
        Paragraph(MARKER, styles["title"]),
        Paragraph(escape(data["name"]), styles["body"]),
        Paragraph(f"Aggiornamento del {escape(data['auditedAt'])}. Questo allegato integra il report storico e non sostituisce le verifiche tariffarie.", styles["small"]),
        Spacer(1, 7 * mm), table, Spacer(1, 8 * mm),
        Paragraph("Come interpretare il dato", styles["body"]),
        Paragraph("Il dominio di un percorso pubblico può identificare il fornitore del booking engine (per esempio ErmesHotels o Kross Booking). Un dominio personalizzato o un widget senza marchio può nasconderlo. Un link o una pagina con date non dimostrano che disponibilità, pagamento e checkout siano completabili; se il fornitore non è verificabile, il report lo dichiara.", styles["small"]),
    ]
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=23 * mm, bottomMargin=20 * mm)
    doc.build(story)
    return buffer.getvalue()


def update_pdf(data_path: Path, pdf_path: Path) -> None:
    data = json.loads(data_path.read_text(encoding="utf-8"))
    original = PdfReader(str(pdf_path))
    writer = PdfWriter()
    pages = original.pages
    count = len(pages) - (1 if MARKER in (pages[-1].extract_text() or "") else 0)
    for page in pages[:count]:
        writer.add_page(page)
    for page in PdfReader(BytesIO(appendix(data))).pages:
        writer.add_page(page)
    temporary = pdf_path.with_suffix(".pdf.tmp")
    with temporary.open("wb") as stream:
        writer.write(stream)
    check = PdfReader(str(temporary))
    if len(check.pages) != count + 1 or MARKER not in (check.pages[-1].extract_text() or ""):
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"Appendice non verificata: {pdf_path}")
    temporary.replace(pdf_path)
    print(f"{pdf_path.name}: {len(check.pages)} pagine, appendice verificata")


if __name__ == "__main__":
    for data_path, pdf_path in FILES:
        update_pdf(data_path, pdf_path)
