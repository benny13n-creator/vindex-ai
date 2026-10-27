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
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from xml.sax.saxutils import escape as _esc
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ─── Font ─────────────────────────────────────────────────────────────────────
# N6: ugrađeni Helvetica (WinAnsi) NEMA č, ć, đ, Č, Ć, Đ — izmereno: „Đorđević“ se u PDF-u ispisivao kao
# „IorIeviI“, a ćirilica je nestajala. Redosled: DejaVu Sans (latinica + ćirilica; produkcijska slica ga dobija
# paketom fonts-dejavu-core), Arial (Windows), pa Vera iz reportlab-a (samo latinica — tada se ćirilica
# PRESLOVLJAVA na latinicu i to se kaže u podnožju, umesto da tiho nestane).
_KANDIDATI_FONTA = (
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
)


def _registruj_fontove() -> bool:
    """Registruje VxSans/VxSans-Bold; vraća True ako font ima ćirilicu."""
    import os
    import reportlab
    if "VxSans" in pdfmetrics.getRegisteredFontNames():
        return _CIRILICA
    for obican, debeo in _KANDIDATI_FONTA:
        if os.path.exists(obican) and os.path.exists(debeo):
            pdfmetrics.registerFont(TTFont("VxSans", obican))
            pdfmetrics.registerFont(TTFont("VxSans-Bold", debeo))
            return True
    d = os.path.join(os.path.dirname(reportlab.__file__), "fonts")
    pdfmetrics.registerFont(TTFont("VxSans", os.path.join(d, "Vera.ttf")))
    pdfmetrics.registerFont(TTFont("VxSans-Bold", os.path.join(d, "VeraBd.ttf")))
    return False


_CIRILICA = False
_CIRILICA = _registruj_fontove()
_FONT, _FONT_B = "VxSans", "VxSans-Bold"
_CIR_LAT = str.maketrans({
    "А": "A", "Б": "B", "В": "V", "Г": "G", "Д": "D", "Ђ": "Đ", "Е": "E", "Ж": "Ž", "З": "Z", "И": "I", "Ј": "J",
    "К": "K", "Л": "L", "Љ": "Lj", "М": "M", "Н": "N", "Њ": "Nj", "О": "O", "П": "P", "Р": "R", "С": "S", "Т": "T",
    "Ћ": "Ć", "У": "U", "Ф": "F", "Х": "H", "Ц": "C", "Ч": "Č", "Џ": "Dž", "Ш": "Š",
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "ђ": "đ", "е": "e", "ж": "ž", "з": "z", "и": "i", "ј": "j",
    "к": "k", "л": "l", "љ": "lj", "м": "m", "н": "n", "њ": "nj", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
    "ћ": "ć", "у": "u", "ф": "f", "х": "h", "ц": "c", "ч": "č", "џ": "dž", "ш": "š",
})
_PRESLOVLJENO = {"desilo": False}


def _t(v) -> str:
    """Korisnički tekst u Paragraph: bez markup-a. Tagovi iz beleške/opisa su menjali prikaz („<b>…“ nestaje), a
    neispravan tag (npr. `<font name=…>`) obara ceo PDF — izmereno."""
    t = str(v if v is not None else "")
    if not _CIRILICA and t != t.translate(_CIR_LAT):
        _PRESLOVLJENO["desilo"] = True
        t = t.translate(_CIR_LAT)
    return _esc(t)


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
            fontName=_FONT_B,
            fontSize=9,
            textColor=_TEAL,
            alignment=2,  # right
        ),
        "header_date": ParagraphStyle(
            "header_date",
            fontName=_FONT,
            fontSize=8,
            textColor=_GREY,
            alignment=2,
        ),
        "doc_title": ParagraphStyle(
            "doc_title",
            fontName=_FONT_B,
            fontSize=16,
            textColor=_DARK,
            spaceAfter=4,
        ),
        "doc_sub": ParagraphStyle(
            "doc_sub",
            fontName=_FONT,
            fontSize=10,
            textColor=_GREY,
            spaceAfter=12,
        ),
        "section": ParagraphStyle(
            "section",
            fontName=_FONT_B,
            fontSize=11,
            textColor=_DARK,
            spaceBefore=14,
            spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "body",
            fontName=_FONT,
            fontSize=9,
            textColor=_DARK,
            leading=13,
            spaceAfter=4,
        ),
        "label": ParagraphStyle(
            "label",
            fontName=_FONT_B,
            fontSize=9,
            textColor=_DARK,
        ),
        "value": ParagraphStyle(
            "value",
            fontName=_FONT,
            fontSize=9,
            textColor=_DARK,
        ),
        "meta": ParagraphStyle(
            "meta",
            fontName=_FONT,
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
    rocista: list[dict] | None = None,
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
    _PRESLOVLJENO["desilo"] = False

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

    story.append(Paragraph(_t(naziv), s["doc_title"]))
    story.append(Paragraph(
        f"Tip: {_t(tip.upper())}  •  Status: {_t(status.upper())}  •  "
        f"Kreiran: {_fmt_date(predmet.get('created_at'))}",
        s["doc_sub"],
    ))

    # ── Opis ──────────────────────────────────────────────────────────────────
    opis = (predmet.get("opis") or "").strip()
    if opis:
        story.append(Paragraph("OPIS PREDMETA", s["section"]))
        story.append(HRFlowable(width="100%", thickness=0.5, color=_GREY, spaceAfter=6))
        story.append(Paragraph(_t(opis), s["body"]))

    # ── Ročišta (N6) ──────────────────────────────────────────────────────────
    _STATUS_ROC = {"zakazano": "zakazano", "odrzano": "održano", "odlozeno": "odloženo", "otkazano": "otkazano"}
    rocs = rocista or []
    story.append(Paragraph("ROČIŠTA", s["section"]))
    story.append(HRFlowable(width="100%", thickness=0.5, color=_GREY, spaceAfter=6))
    if not rocs:
        story.append(Paragraph("Za predmet nije upisano nijedno ročište.", s["body"]))
    else:
        tbl_data = [["Datum", "Vreme", "Sud / sudnica", "Stanje"]]
        for r in rocs:
            sud = (r.get("sud") or "—") + (f", sudnica {r.get('sudnica')}" if r.get("sudnica") else "")
            tbl_data.append([_fmt_date(r.get("datum")), str(r.get("vreme") or "—")[:5], Paragraph(_t(sud), s["body"]),
                             _STATUS_ROC.get(r.get("status") or "zakazano", r.get("status") or "—")])
        tbl = Table(tbl_data, colWidths=[2.8 * cm, 1.8 * cm, 9.7 * cm, 3.0 * cm])
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), _DARK), ("TEXTCOLOR", (0, 0), (-1, 0), _WHITE),
            ("FONTNAME", (0, 0), (-1, 0), _FONT_B), ("FONTNAME", (0, 1), (-1, -1), _FONT), ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("VALIGN", (0, 0), (-1, -1), "TOP"), ("GRID", (0, 0), (-1, -1), 0.3, _GREY),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_LGREY, _WHITE]),
        ]))
        story.append(tbl)

    # ── Hronologija ───────────────────────────────────────────────────────────
    hronos = hronologija or []
    if hronos:
        story.append(Paragraph("HRONOLOGIJA", s["section"]))
        story.append(HRFlowable(width="100%", thickness=0.5, color=_GREY, spaceAfter=6))

        tbl_data = [["Datum", "Događaj", "Akter", "Važnost"]]
        for h in hronos:
            vaznost = h.get("vaznost") or "informativan"
            # FAZA 6.5: PDF je advokatov radni izvoz (INTERNAL), pa nepotvrđen
            # rok OSTAJE — ali mora biti vidljivo označen. Tiho izostavljanje
            # roka iz spisa bilo bi gore od prikazivanja kandidata.
            # N6: oznaka odluke važi samo za ROK (vrsta='rok'); običan događaj hronologije nije odluka
            # („Podneta tužba“ je ranije dobijala „[NEPOTVRĐENO]“). `stanje_odluke=None` = nije rok.
            _stanje = h.get("stanje_odluke")
            _dog = _t(h.get("dogadjaj") or "—")
            if _stanje == "UNCONFIRMED":
                _dog = "[NEPOTVRĐENO] " + _dog
            elif _stanje == "REJECTED":
                _dog = "[ODBIJENO] " + _dog
            elif _stanje == "UNKNOWN":
                # N03-FD8: lanac odluka nije procitan -- ne zna se da li je potvrdjen.
                _dog = "[STANJE ODLUKE NEPOZNATO] " + _dog
            tbl_data.append([
                _fmt_date(h.get("datum_iso") or h.get("datum")),
                Paragraph(_dog, s["body"]),
                Paragraph(_t(h.get("akter") or "—"), s["body"]),
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
            ("FONTNAME",     (0, 0), (-1, 0), _FONT_B),
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
                Paragraph(_t(d.get("naziv_fajla") or "—"), s["body"]),
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
            ("FONTNAME",      (0, 0), (-1, 0), _FONT_B),
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
                story.append(Paragraph(_t(sadrzaj), s["body"]))
            story.append(Spacer(1, 4))

    # ── Footer separator ──────────────────────────────────────────────────────
    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", thickness=0.5, color=_GREY))
    if _PRESLOVLJENO["desilo"]:
        story.append(Paragraph("Napomena: tekst pisan ćirilicom je u ovom izveštaju preslovljen na latinicu (font bez ćirilice).",
                               ParagraphStyle("napomena", fontName=_FONT, fontSize=7, textColor=_GREY, alignment=1)))
    story.append(Paragraph(
        "Vindex AI — Softver za upravljanje pravnim predmetima • Poverljivo",
        ParagraphStyle("footer", fontName=_FONT, fontSize=7,
                       textColor=_GREY, alignment=1),
    ))

    doc.build(story)
    return buf.getvalue()
