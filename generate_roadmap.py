# -*- coding: utf-8 -*-
"""Vindex AI — Roadmap PDF generator"""

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

import os
from datetime import date

OUT = os.path.join(os.path.dirname(__file__), "Vindex_AI_Roadmap.pdf")

# ── Fontovi ──────────────────────────────────────────────────────────────────
pdfmetrics.registerFont(TTFont("Arial",   "C:/Windows/Fonts/arial.ttf"))
pdfmetrics.registerFont(TTFont("ArialBd", "C:/Windows/Fonts/arialbd.ttf"))
pdfmetrics.registerFont(TTFont("ArialIt", "C:/Windows/Fonts/ariali.ttf"))

# ── Boje ─────────────────────────────────────────────────────────────────────
C_BG       = colors.HexColor("#0d1117")
C_CARD     = colors.HexColor("#161b22")
C_BORDER   = colors.HexColor("#21262d")
C_BLUE     = colors.HexColor("#4aa8ff")
C_BLUE_D   = colors.HexColor("#1a4a7a")
C_GREEN    = colors.HexColor("#3fb950")
C_GREEN_D  = colors.HexColor("#1a4a2a")
C_YELLOW   = colors.HexColor("#d29922")
C_YELLOW_D = colors.HexColor("#4a3810")
C_GRAY     = colors.HexColor("#8b949e")
C_GRAY_D   = colors.HexColor("#21262d")
C_WHITE    = colors.HexColor("#e6edf3")
C_DIM      = colors.HexColor("#6e7681")
C_RED      = colors.HexColor("#f85149")
C_RED_D    = colors.HexColor("#4a1a1a")

# Hex string map (za inline font tags u Paragraph markup)
_CHX = {
    C_GREEN:  "3fb950", C_GREEN_D:  "1a4a2a",
    C_BLUE:   "4aa8ff", C_BLUE_D:   "1a4a7a",
    C_YELLOW: "d29922", C_YELLOW_D: "4a3810",
    C_GRAY:   "8b949e", C_GRAY_D:   "21262d",
    C_WHITE:  "e6edf3", C_DIM:      "6e7681",
}
def hx(c):
    """Vraća 6-char hex string boje."""
    return _CHX.get(c, "e6edf3")

W, H = A4
MARGIN = 18 * mm

# ── Stilovi ──────────────────────────────────────────────────────────────────
def sty(name, font="Arial", size=10, color=C_WHITE, bold=False, align=TA_LEFT,
        leading=None, space_before=0, space_after=0):
    return ParagraphStyle(
        name,
        fontName="ArialBd" if bold else font,
        fontSize=size,
        textColor=color,
        alignment=align,
        leading=leading or (size * 1.4),
        spaceBefore=space_before,
        spaceAfter=space_after,
    )

S_TITLE    = sty("title",    size=24, bold=True,  color=C_WHITE, align=TA_CENTER, leading=30)
S_SUBTITLE = sty("subtitle", size=11, color=C_BLUE, align=TA_CENTER, leading=16)
S_DATE     = sty("date",     size=9,  color=C_DIM,  align=TA_CENTER)
S_PH_TITLE = sty("ph_title", size=13, bold=True,  color=C_WHITE, leading=18)
S_ITEM     = sty("item",     size=9,  color=C_WHITE, leading=13)
S_ITEM_DIM = sty("item_dim", size=9,  color=C_DIM,  leading=13)
S_NOTE     = sty("note",     size=8,  color=C_GRAY,  leading=12)
S_LEGEND   = sty("legend",   size=9,  color=C_GRAY,  align=TA_LEFT)
S_SECTION  = sty("section",  size=8,  bold=True, color=C_BLUE, leading=11)
S_FOOTER   = sty("footer",   size=8,  color=C_DIM, align=TA_CENTER)

# ── Status badge helper ───────────────────────────────────────────────────────
def badge(status):
    """Vraća (tekst, bg_color, text_color) za status badge."""
    if status == "DONE":
        return ("✓  DONE",    C_GREEN_D,  C_GREEN)
    if status == "PARTIAL":
        return ("◑  PARTIAL", C_YELLOW_D, C_YELLOW)
    if status == "TODO":
        return ("○  TODO",    C_GRAY_D,   C_GRAY)
    if status == "NEXT":
        return ("▶  NEXT",    C_BLUE_D,   C_BLUE)
    if status == "PLANNED":
        return ("·  PLANNED", C_GRAY_D,   C_DIM)
    return (status, C_GRAY_D, C_GRAY)

# ── Faze i stavke ─────────────────────────────────────────────────────────────
#  (phase_id, phase_name, color, [(item_id, name, status, note)])
PHASES = [
    (
        "1", "MVP OSNOVA", C_BLUE,
        [
            ("1.1", "Predmeti CRUD — kreiranje, lista, detalji, beleške", "DONE", ""),
            ("1.2", "Auto-trigger AI analiza na upload dokumenta", "DONE", ""),
            ("1.3", "Corpus Pinecone — Zakon o radu + Porodični zakon", "DONE", "~4 500 vektora, default NS"),
            ("1.4", "Auth — Supabase JWT, krediti, Pro tier", "DONE", ""),
        ]
    ),
    (
        "2", "ENRICHMENT", C_BLUE,
        [
            ("2.1", "Document type detection + RAG inject + ZR čl. hints", "DONE", ""),
            ("2.2", "Hronologija dokaza — AI timeline extraction", "DONE", "GPT-4o mini → Supabase"),
            ("2.3", "Istorija izmena propisa — amendment badges", "DONE", "inline u citatu zakona"),
            ("2.4", "Mišljenja ministarstava — ingest + RAG + UI kartice", "DONE", "74 vektora, NS: misljenja"),
        ]
    ),
    (
        "3", "ANALITIKA", C_YELLOW,
        [
            ("3.1", "Grupisanje presuda Za/Protiv — klasifikator ishoda", "DONE", "endpoint: /api/sudska-praksa/grupisano"),
            ("3.2", "Ratio decidendi — GPT ekstrakcija + Supabase keš", "DONE", ""),
            ("3.3", "Upoređivanje presuda A vs B — GPT-4o analiza", "DONE", "endpoint: /api/praksa/uporedi"),
            ("3.4", "AI pregled predmeta v2 — sekcije 19–22 + Pinecone", "DONE", "sekcija 22 = real retrieval"),
            ("3.5", "Rokovi — ekstrakcija iz dokumenta (regex parser)", "DONE", "deadline_parser.py, 9 patterna"),
            ("3.6", "Rokovi — kalkulacija datuma + zastarelost + ICS", "NEXT",
             "relativni→datum, zastarelost SR, .ics export, 'Dodaj u kalendar'"),
        ]
    ),
    (
        "4", "PRO / DRAFTING", C_GREEN,
        [
            ("4.1", "Nacrt pravnog dokumenta — strukturirani šablon", "DONE", ""),
            ("4.2", "Podnesak generator — VKS analiza + popuni šablon", "DONE", ""),
            ("4.3", "Compliance checker (drafting.compliance)", "DONE", ""),
            ("4.4", "Playbook upload — firm-specific knowledge (Pinecone)", "DONE", "NS: playbook_{user_id}"),
        ]
    ),
    (
        "5", "SCALE / POLISH", C_GRAY,
        [
            ("5.1", "Više pravnih oblasti — Krivično, Privredno, Radno", "PLANNED", ""),
            ("5.2", "Batch ingest novih presuda (auto-scraper)", "PLANNED", ""),
            ("5.3", "Export predmeta (PDF izveštaj)", "PLANNED", ""),
            ("5.4", "Multi-user firm account + role management", "PLANNED", ""),
            ("5.5", "API za spoljne integracije (Clio, iManage...)", "PLANNED", ""),
        ]
    ),
]

# ── Builder ───────────────────────────────────────────────────────────────────
def build():
    doc = SimpleDocTemplate(
        OUT, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN, bottomMargin=MARGIN,
        title="Vindex AI — Roadmap",
        author="Vindex AI",
    )

    story = []
    cw = W - 2 * MARGIN  # usable column width

    # ── Header ───────────────────────────────────────────────────────────────
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph("VINDEX AI", S_TITLE))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph("Roadmap — AI Legal Assistant za srpske advokate", S_SUBTITLE))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(f"Ažurirano: {date.today().strftime('%d.%m.%Y.')}", S_DATE))
    story.append(Spacer(1, 5 * mm))
    story.append(HRFlowable(width=cw, thickness=1, color=C_BORDER))
    story.append(Spacer(1, 5 * mm))

    # ── Legend ───────────────────────────────────────────────────────────────
    legend_items = [
        ("✓  DONE",    C_GREEN,  C_GREEN_D),
        ("▶  NEXT",    C_BLUE,   C_BLUE_D),
        ("◑  PARTIAL", C_YELLOW, C_YELLOW_D),
        ("○  TODO",    C_GRAY,   C_GRAY_D),
        ("·  PLANNED", C_DIM,    C_GRAY_D),
    ]
    leg_data = [[
        Paragraph(f'<font color="#{hx(c)}"><b>{t}</b></font>', S_LEGEND)
        for t, c, _ in legend_items
    ]]
    leg_table = Table(leg_data, colWidths=[cw / len(legend_items)] * len(legend_items))
    leg_table.setStyle(TableStyle([
        ("ALIGN",       (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND",  (0, 0), (-1, -1), C_CARD),
        ("BOX",         (0, 0), (-1, -1), 0.5, C_BORDER),
        ("ROWPADDING",  (0, 0), (-1, -1), 5),
        ("TOPPADDING",  (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ROUNDEDCORNERS", [4]),
    ]))
    story.append(leg_table)
    story.append(Spacer(1, 7 * mm))

    # ── Faze ─────────────────────────────────────────────────────────────────
    for ph_id, ph_name, ph_color, items in PHASES:
        done_count = sum(1 for _, _, s, _ in items if s == "DONE")
        total      = len(items)
        pct        = int(done_count / total * 100) if total else 0

        # Phase header row
        ph_label  = Paragraph(f"<b>PHASE {ph_id} — {ph_name}</b>", sty("ph", size=11, bold=True, color=C_WHITE))
        ph_progress = Paragraph(
            f'<font color="#{hx(ph_color)}">{done_count}/{total} ({pct}%)</font>',
            sty("pct", size=10, color=ph_color, align=TA_RIGHT)
        )
        ph_header = Table([[ph_label, ph_progress]], colWidths=[cw * 0.78, cw * 0.22])
        ph_header.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), C_CARD),
            ("TOPPADDING",    (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("LEFTPADDING",   (0, 0), (-1, -1), 10),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("LINEBELOW",     (0, 0), (-1, -1), 2, ph_color),
        ]))
        story.append(ph_header)

        # Items
        for item_id, item_name, status, note in items:
            badge_text, badge_bg, badge_fg = badge(status)
            is_next = status == "NEXT"
            row_bg  = C_CARD if not is_next else colors.HexColor("#0d1e30")

            id_para   = Paragraph(f'<b>{item_id}</b>', sty("id", size=9, bold=True, color=C_BLUE))
            name_para = Paragraph(
                f'<b>{item_name}</b>' if is_next else item_name,
                sty("nm", size=9, bold=is_next, color=C_WHITE if not is_next else colors.HexColor("#89c8ff"), leading=13)
            )
            if note:
                name_and_note = [name_para, Paragraph(note, S_NOTE)]
                from reportlab.platypus import KeepTogether
                cell_content = name_and_note
            else:
                cell_content = [name_para]

            badge_para = Paragraph(
                f'<font color="#{hx(badge_fg)}">{badge_text}</font>',
                sty("bdg", size=8, bold=True, color=badge_fg, align=TA_CENTER)
            )

            row_data = [[id_para, cell_content, badge_para]]
            col_widths = [cw * 0.08, cw * 0.67, cw * 0.25]
            row_table = Table(row_data, colWidths=col_widths)
            row_style = [
                ("BACKGROUND",    (0, 0), (-1, -1), row_bg),
                ("TOPPADDING",    (0, 0), (-1, -1), 5 if not note else 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5 if not note else 4),
                ("LEFTPADDING",   (0, 0), (0,  0),  14),
                ("LEFTPADDING",   (1, 0), (1,  0),  4),
                ("RIGHTPADDING",  (2, 0), (2,  0),  8),
                ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
                ("LINEBELOW",     (0, 0), (-1, -1), 0.5, C_BORDER),
                ("BACKGROUND",    (2, 0), (2,  0),  badge_bg),
            ]
            if is_next:
                row_style.append(("LINEBEFORE", (0, 0), (0, 0), 3, C_BLUE))
            row_table.setStyle(TableStyle(row_style))
            story.append(row_table)

        story.append(Spacer(1, 6 * mm))

    # ── Footer ───────────────────────────────────────────────────────────────
    story.append(HRFlowable(width=cw, thickness=1, color=C_BORDER))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(
        f"Vindex AI · Legal RAG · FastAPI + Pinecone + Supabase + OpenAI · {date.today().year}",
        S_FOOTER
    ))

    # ── Build ─────────────────────────────────────────────────────────────────
    # Dark background na svakoj stranici
    def bg_canvas(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(C_BG)
        canvas.rect(0, 0, W, H, fill=1, stroke=0)
        canvas.restoreState()

    doc.build(story, onFirstPage=bg_canvas, onLaterPages=bg_canvas)
    print(f"PDF generisan: {OUT}")


if __name__ == "__main__":
    build()
