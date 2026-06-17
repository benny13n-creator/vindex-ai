# -*- coding: utf-8 -*-
"""
Vindex AI — predmet_pdf.py

Phase 5.3: Generisanje PDF izveštaja za predmet.
Koristi ReportLab za generisanje PDF-a sa svim podacima predmeta.
"""
from __future__ import annotations

from datetime import datetime
from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ─── Boje ─────────────────────────────────────────────────────────────────────

_TEAL    = colors.HexColor("#00d4ff")
_DARK    = colors.HexColor("#0d1b2a")
_GREY    = colors.HexColor("#888888")
_LGREY   = colors.HexColor("#f0f4f8")
_WHITE   = colors.white
_BLACK   = colors.black
_GOLD    = colors.HexColor("#c9a84c")

# ─── Stilovi ──────────────────────────────────────────────────────────────────

def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "header_title": ParagraphStyle(
            "header_title",
            fontName="Helvetica-Bold",
            fontSize=9,
            textColor=_TEAL,
            alignment=2,  # right
        ),
        "header_date": ParagraphStyle(
            "header_date",
            fontName="Helvetica",
            fontSize=8,
            textColor=_GREY,
            alignment=2,
        ),
        "doc_title": ParagraphStyle(
            "doc_title",
            fontName="Helvetica-Bold",
            fontSize=16,
            textColor=_DARK,
            spaceAfter=4,
        ),
        "doc_sub": ParagraphStyle(
            "doc_sub",
            fontName="Helvetica",
            fontSize=10,
            textColor=_GREY,
            spaceAfter=12,
        ),
        "section": ParagraphStyle(
            "section",
            fontName="Helvetica-Bold",
            fontSize=11,
            textColor=_DARK,
            spaceBefore=14,
            spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "body",
            fontName="Helvetica",
            fontSize=9,
            textColor=_DARK,
            leading=13,
            spaceAfter=4,
        ),
        "label": ParagraphStyle(
            "label",
            fontName="Helvetica-Bold",
            fontSize=9,
            textColor=_DARK,
        ),
        "value": ParagraphStyle(
            "value",
            fontName="Helvetica",
            fontSize=9,
            textColor=_DARK,
        ),
        "meta": ParagraphStyle(
            "meta",
            fontName="Helvetica",
            fontSize=8,
            textColor=_GREY,
        ),
    }


# ─── Helper: format date ──────────────────────────────────────────────────────

def _fmt_date(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%d.%m.%Y")
    except Exception:
        return str(iso)[:10]


# ─── Core PDF builder ─────────────────────────────────────────────────────────

def generiši_predmet_pdf(
    predmet: dict[str, Any],
    dokumenti: list[dict] | None = None,
    beleske: list[dict] | None = None,
    hronologija: list[dict] | None = None,
) -> bytes:
    """
    Generisanje PDF izveštaja za jedan predmet.
    Vraća bytes koji se mogu poslati klijentu kao application/pdf.
    """
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    s = _styles()
    story = []

    # ── Header ────────────────────────────────────────────────────────────────
    story.append(Paragraph("VINDEX AI", s["header_title"]))
    story.append(Paragraph(
        f"Generisano: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
        s["header_date"],
    ))
    story.append(HRFlowable(width="100%", thickness=1.5, color=_TEAL, spaceAfter=10))

    # ── Naslov predmeta ───────────────────────────────────────────────────────
    naziv = predmet.get("naziv") or "Bez naziva"
    tip   = predmet.get("tip") or "opsti"
    status = predmet.get("status") or "aktivan"

    story.append(Paragraph(naziv, s["doc_title"]))
    story.append(Paragraph(
        f"Tip: {tip.upper()}  •  Status: {status.upper()}  •  "
        f"Kreiran: {_fmt_date(predmet.get('created_at'))}",
        s["doc_sub"],
    ))

    # ── Opis ──────────────────────────────────────────────────────────────────
    opis = (predmet.get("opis") or "").strip()
    if opis:
        story.append(Paragraph("OPIS PREDMETA", s["section"]))
        story.append(HRFlowable(width="100%", thickness=0.5, color=_GREY, spaceAfter=6))
        story.append(Paragraph(opis, s["body"]))

    # ── Hronologija ───────────────────────────────────────────────────────────
    hronos = hronologija or []
    if hronos:
        story.append(Paragraph("HRONOLOGIJA", s["section"]))
        story.append(HRFlowable(width="100%", thickness=0.5, color=_GREY, spaceAfter=6))

        tbl_data = [["Datum", "Događaj", "Akter", "Važnost"]]
        for h in hronos:
            vaznost = h.get("vaznost") or "informativan"
            tbl_data.append([
                _fmt_date(h.get("datum_iso") or h.get("datum")),
                Paragraph(h.get("dogadjaj") or "—", s["body"]),
                Paragraph(h.get("akter") or "—", s["body"]),
                vaznost,
            ])

        tbl = Table(
            tbl_data,
            colWidths=[2.8 * cm, 9.5 * cm, 3.5 * cm, 2.5 * cm],
        )
        _vaznost_colors = {
            "kritičan":    colors.HexColor("#fde8e8"),
            "važan":       colors.HexColor("#fef9e7"),
            "informativan": _LGREY,
        }
        tbl_style = [
            ("BACKGROUND",   (0, 0), (-1, 0), _DARK),
            ("TEXTCOLOR",    (0, 0), (-1, 0), _WHITE),
            ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",     (0, 0), (-1, 0), 8),
            ("ALIGN",        (0, 0), (-1, -1), "LEFT"),
            ("VALIGN",       (0, 0), (-1, -1), "TOP"),
            ("FONTSIZE",     (0, 1), (-1, -1), 8),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_LGREY, _WHITE]),
            ("GRID",         (0, 0), (-1, -1), 0.3, _GREY),
            ("TOPPADDING",   (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
            ("LEFTPADDING",  (0, 0), (-1, -1), 4),
        ]
        for i, h in enumerate(hronos, start=1):
            bg = _vaznost_colors.get(h.get("vaznost") or "informativan", _LGREY)
            tbl_style.append(("BACKGROUND", (0, i), (-1, i), bg))
        tbl.setStyle(TableStyle(tbl_style))
        story.append(tbl)

    # ── Dokumenti ─────────────────────────────────────────────────────────────
    docs = dokumenti or []
    if docs:
        story.append(Paragraph("PRILOŽENI DOKUMENTI", s["section"]))
        story.append(HRFlowable(width="100%", thickness=0.5, color=_GREY, spaceAfter=6))

        tbl_data = [["Naziv fajla", "Status", "Veličina (KB)", "Priložen"]]
        for d in docs:
            tbl_data.append([
                Paragraph(d.get("naziv_fajla") or "—", s["body"]),
                d.get("status") or "—",
                str(d.get("velicina_kb") or "—"),
                _fmt_date(d.get("created_at")),
            ])
        tbl = Table(
            tbl_data,
            colWidths=[8 * cm, 3 * cm, 3 * cm, 3 * cm],
        )
        tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0), _DARK),
            ("TEXTCOLOR",     (0, 0), (-1, 0), _WHITE),
            ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",      (0, 0), (-1, -1), 8),
            ("ALIGN",         (0, 0), (-1, -1), "LEFT"),
            ("VALIGN",        (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS",(0, 1), (-1, -1), [_LGREY, _WHITE]),
            ("GRID",          (0, 0), (-1, -1), 0.3, _GREY),
            ("TOPPADDING",    (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ]))
        story.append(tbl)

    # ── Beleške ───────────────────────────────────────────────────────────────
    bels = beleske or []
    if bels:
        story.append(Paragraph("BELEŠKE", s["section"]))
        story.append(HRFlowable(width="100%", thickness=0.5, color=_GREY, spaceAfter=6))

        for i, b in enumerate(bels, start=1):
            sadrzaj = (b.get("sadrzaj") or "").strip()
            datum   = _fmt_date(b.get("created_at"))
            story.append(Paragraph(f"<b>Beleška {i}</b> — {datum}", s["label"]))
            if sadrzaj:
                story.append(Paragraph(sadrzaj, s["body"]))
            story.append(Spacer(1, 4))

    # ── Footer separator ──────────────────────────────────────────────────────
    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", thickness=0.5, color=_GREY))
    story.append(Paragraph(
        "Vindex AI — Softver za upravljanje pravnim predmetima • Poverljivo",
        ParagraphStyle("footer", fontName="Helvetica", fontSize=7,
                       textColor=_GREY, alignment=1),
    ))

    doc.build(story)
    return buf.getvalue()
