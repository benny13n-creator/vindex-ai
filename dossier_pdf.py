# -*- coding: utf-8 -*-
"""
Vindex AI — dossier_pdf.py

F16: Source-of-Funds / Source-of-Wealth Compliance Dossier — PDF builder.
Isti ReportLab stil i paleta kao predmet_pdf.py (Vindex brend), ali novi
sadržajni layout koji spaja tri modula u jedan dokument:
  1. Documentation Health Score (F11.7)
  2. CARF/DAC8 Readiness (F11.9)
  3. Wallet Provenance (F15, opciono — samo ako je dostavljena adresa)
"""
from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
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

_TEAL  = colors.HexColor("#00d4ff")
_DARK  = colors.HexColor("#0d1b2a")
_GREY  = colors.HexColor("#888888")
_LGREY = colors.HexColor("#f0f4f8")
_WHITE = colors.white
_RED   = colors.HexColor("#c0392b")
_RED_BG = colors.HexColor("#fde8e8")
_AMBER_BG = colors.HexColor("#fef9e7")
_GREEN_BG = colors.HexColor("#e8f8f0")

_STATUS_BG = {"ok": _GREEN_BG, "warning": _AMBER_BG, "danger": _RED_BG}


def _styles() -> dict[str, ParagraphStyle]:
    getSampleStyleSheet()  # ensures reportlab base registration side-effects
    return {
        "header_title": ParagraphStyle("header_title", fontName="Helvetica-Bold", fontSize=9, textColor=_TEAL, alignment=2),
        "header_date":  ParagraphStyle("header_date", fontName="Helvetica", fontSize=8, textColor=_GREY, alignment=2),
        "doc_title":    ParagraphStyle("doc_title", fontName="Helvetica-Bold", fontSize=16, textColor=_DARK, spaceAfter=4),
        "doc_sub":      ParagraphStyle("doc_sub", fontName="Helvetica", fontSize=10, textColor=_GREY, spaceAfter=12),
        "section":      ParagraphStyle("section", fontName="Helvetica-Bold", fontSize=11, textColor=_DARK, spaceBefore=14, spaceAfter=4),
        "body":         ParagraphStyle("body", fontName="Helvetica", fontSize=9, textColor=_DARK, leading=13, spaceAfter=4),
        "label":        ParagraphStyle("label", fontName="Helvetica-Bold", fontSize=9, textColor=_DARK),
        "score_big":    ParagraphStyle("score_big", fontName="Helvetica-Bold", fontSize=28, textColor=_DARK),
        "score_nivo":   ParagraphStyle("score_nivo", fontName="Helvetica-Bold", fontSize=11, textColor=_GREY),
        "risk_item":    ParagraphStyle("risk_item", fontName="Helvetica", fontSize=9, textColor=_RED, leading=13, spaceAfter=3),
        "meta":         ParagraphStyle("meta", fontName="Helvetica", fontSize=8, textColor=_GREY),
        "disclaimer":   ParagraphStyle("disclaimer", fontName="Helvetica", fontSize=7.5, textColor=_GREY, leading=11),
    }


def _fmt_ts(ts: int | None) -> str:
    if not ts:
        return "—"
    try:
        return datetime.utcfromtimestamp(int(ts)).strftime("%d.%m.%Y")
    except Exception:
        return "—"


def _section_header(story: list, naslov: str, s: dict):
    story.append(Paragraph(naslov, s["section"]))
    story.append(HRFlowable(width="100%", thickness=0.5, color=_GREY, spaceAfter=6))


def _get_git_hash() -> str:
    """Isti pristup kao api.py._get_git_hash — namerno dupliran (ne uvožen iz
    api.py) da se izbegne kružni import (api.py → routers → dossier_pdf.py)."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(Path(__file__).resolve().parent), stderr=subprocess.DEVNULL, timeout=3,
        ).decode().strip()
    except Exception:
        return "nepoznata"


def generisi_dossier_pdf(kontekst: dict[str, Any]) -> bytes:
    """
    kontekst = {
        "korisnik_email": str,
        "health_data": dict | None,       # iz documentation_health_score_sync
        "carf_odgovor": str | None,       # iz carf_dac8_readiness_sync
        "carf_pitanje": str | None,
        "wallet": dict | None,            # iz sakupi_wallet_provenance
    }
    """
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        rightMargin=2 * cm, leftMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm,
    )
    s = _styles()
    story = []

    # ── Header ────────────────────────────────────────────────────────────────
    story.append(Paragraph("VINDEX AI — DIGITALNA IMOVINA & USKLAĐENOST", s["header_title"]))
    story.append(Paragraph(f"Generisano: {datetime.now().strftime('%d.%m.%Y %H:%M')}", s["header_date"]))
    story.append(HRFlowable(width="100%", thickness=1.5, color=_TEAL, spaceAfter=10))

    story.append(Paragraph("Source-of-Funds Compliance Dossier", s["doc_title"]))
    podnaslov = "Konsolidovani izveštaj: spremnost dokumentacije, CARF/DAC8 kontekst"
    if kontekst.get("wallet"):
        podnaslov += ", provera novčanika"
    story.append(Paragraph(podnaslov + ".", s["doc_sub"]))

    # ── 1. Documentation Health Score ────────────────────────────────────────
    health = kontekst.get("health_data")
    if health:
        _section_header(story, "1. SPREMNOST DOKUMENTACIJE", s)
        skor = health.get("ukupni_skor", "?")
        nivo = health.get("skor_nivo", "")
        story.append(Paragraph(f"{skor}/100", s["score_big"]))
        story.append(Paragraph(f"Nivo spremnosti: {nivo}", s["score_nivo"]))
        story.append(Spacer(1, 8))

        kategorije = health.get("kategorije") or {}
        if kategorije:
            tbl_data = [["Kategorija", "Skor", "Status"]]
            for naziv, info in kategorije.items():
                if not isinstance(info, dict):
                    continue
                tbl_data.append([
                    Paragraph(naziv.replace("_", " ").capitalize(), s["body"]),
                    f"{info.get('skor', '?')}/{info.get('max', '?')}",
                    str(info.get("status", "")).upper(),
                ])
            tbl = Table(tbl_data, colWidths=[9 * cm, 3 * cm, 4 * cm])
            tbl_style = [
                ("BACKGROUND", (0, 0), (-1, 0), _DARK),
                ("TEXTCOLOR", (0, 0), (-1, 0), _WHITE),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.3, _GREY),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ]
            for i, (_, info) in enumerate(kategorije.items(), start=1):
                if isinstance(info, dict):
                    bg = _STATUS_BG.get(info.get("status"), _LGREY)
                    tbl_style.append(("BACKGROUND", (0, i), (-1, i), bg))
            tbl.setStyle(TableStyle(tbl_style))
            story.append(tbl)
            story.append(Spacer(1, 8))

        kriticni = health.get("kriticni_nedostaci") or []
        if kriticni:
            story.append(Paragraph("Kritični nedostaci (od najvažnijeg):", s["label"]))
            for k in kriticni:
                story.append(Paragraph(f"⚠ {k}", s["risk_item"]))
            story.append(Spacer(1, 6))

        preporuke = health.get("preporuke") or []
        if preporuke:
            story.append(Paragraph("Preporuke:", s["label"]))
            for p in preporuke:
                story.append(Paragraph(f"• {p}", s["body"]))

    # ── 2. CARF/DAC8 Readiness ───────────────────────────────────────────────
    carf_odgovor = kontekst.get("carf_odgovor")
    if carf_odgovor:
        _section_header(story, "2. CARF/DAC8 REGULATORNI KONTEKST", s)
        pitanje = kontekst.get("carf_pitanje")
        if pitanje:
            story.append(Paragraph(f"<i>Upit: {pitanje}</i>", s["meta"]))
            story.append(Spacer(1, 4))
        for pasus in carf_odgovor.split("\n"):
            if pasus.strip():
                story.append(Paragraph(pasus.strip(), s["body"]))

    # ── 3. Wallet Provenance (opciono) ───────────────────────────────────────
    wallet = kontekst.get("wallet")
    if wallet:
        _section_header(story, "3. PROVERA NOVČANIKA (WALLET PROVENANCE)", s)

        # Ograničenja analize — UVEK prvo, pre adrese i pre bilo kog nalaza.
        ogranicenja = wallet.get("ogranicenja_analize") or []
        if ogranicenja:
            story.append(Paragraph("Ograničenja analize", s["label"]))
            for o in ogranicenja:
                story.append(Paragraph(f"• {o}", s["meta"]))
            story.append(Spacer(1, 6))

        story.append(Paragraph(f"Adresa: {wallet.get('adresa', '—')}", s["label"]))
        story.append(Spacer(1, 4))

        nalazi = wallet.get("nalazi") or {"sankcioni": [], "analiticki": [], "nedostatak_podataka": []}

        if nalazi.get("sankcioni"):
            story.append(Paragraph(
                f"⚠ {len(nalazi['sankcioni'])} sankcioni nalaz(a) — vidi detalje ispod.",
                s["risk_item"],
            ))
        else:
            story.append(Paragraph(
                "✓ Nisu pronađena poklapanja sa trenutno učitanom OFAC SDN listom.", s["body"]
            ))

        # Coverage — auditabilnost: šta je tačno analizirano, čime, i kada
        cov = wallet.get("coverage") or {}
        if cov:
            cov_txt = (
                f"Coverage: analizirano {cov.get('analizirano_eth_transakcija', '?')} ETH + "
                f"{cov.get('analizirano_token_transakcija', '?')} token transakcija · "
                f"lanac: {cov.get('lanac', '?')} · izvor: {cov.get('izvor', '?')}"
                + (" · limit dostignut" if cov.get("limit_dostignut") else "")
                + f" · osveženo: {cov.get('poslednje_osvezavanje', '?')}"
            )
            story.append(Paragraph(cov_txt, s["meta"]))
        story.append(Spacer(1, 4))

        tbl_data = [["Metrika", "Vrednost"]]
        tbl_data.append(["Balans (ETH)", f"{wallet.get('balans_eth', '?')} ETH"])
        tbl_data.append(["Prva aktivnost", _fmt_ts(wallet.get("prva_aktivnost_timestamp"))])
        tbl_data.append(["Poslednja aktivnost", _fmt_ts(wallet.get("poslednja_aktivnost_timestamp"))])
        tbl_data.append(["Starost novčanika", f"{wallet.get('starost_dana', '?')} dana" if wallet.get("starost_dana") is not None else "—"])
        tbl_data.append(["Broj ETH transakcija", str(wallet.get("broj_eth_transakcija", "?"))])
        tbl_data.append(["Broj token transakcija", str(wallet.get("broj_token_transakcija", "?"))])
        tbl_data.append(["Jedinstveni kontakti", str(wallet.get("broj_jedinstvenih_kontakata", "?"))])
        tbl_data.append(["Ukupno poslato", f"{wallet.get('ukupno_poslato_eth', '?')} ETH"])
        tbl_data.append(["Ukupno primljeno", f"{wallet.get('ukupno_primljeno_eth', '?')} ETH"])

        tbl = Table(tbl_data, colWidths=[7 * cm, 9 * cm])
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), _DARK),
            ("TEXTCOLOR", (0, 0), (-1, 0), _WHITE),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_LGREY, _WHITE]),
            ("GRID", (0, 0), (-1, -1), 0.3, _GREY),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(tbl)
        story.append(Spacer(1, 8))

        if nalazi.get("sankcioni"):
            story.append(Paragraph("Sankcioni nalazi", s["label"]))
            for n in nalazi["sankcioni"]:
                story.append(Paragraph(f"[{n.get('confidence', '?')}] {n.get('opis', '')}", s["risk_item"]))
            story.append(Spacer(1, 4))
        else:
            story.append(Paragraph(
                "✓ Nijedan direktan kontakt sa adresom na OFAC SDN listi nije pronađen.", s["body"]
            ))
            story.append(Spacer(1, 4))

        if nalazi.get("analiticki"):
            story.append(Paragraph("Analitički nalazi (heuristika, ne sankcioni nalaz)", s["label"]))
            for n in nalazi["analiticki"]:
                story.append(Paragraph(f"[{n.get('confidence', '?')}] {n.get('opis', '')}", s["body"]))
            story.append(Spacer(1, 4))

        if nalazi.get("nedostatak_podataka"):
            story.append(Paragraph("Nedostatak podataka / ograničenja provere", s["label"]))
            for n in nalazi["nedostatak_podataka"]:
                story.append(Paragraph(f"• {n.get('opis', '')}", s["meta"]))

    # ── Metodologija — audit trail: čime/kada/kojom verzijom je izveštaj rađen ──
    story.append(Spacer(1, 16))
    story.append(Paragraph("Metodologija", s["label"]))
    story.append(HRFlowable(width="100%", thickness=0.5, color=_GREY, spaceAfter=4))
    metodologija = []
    if kontekst.get("wallet"):
        metodologija += [
            "Izvor blockchain podataka: Etherscan API V2",
            "Izvor sankcionih podataka: OFAC SDN lista",
            "Obuhvat: Ethereum mainnet",
            "Maksimalan broj analiziranih transakcija: 1000",
        ]
    metodologija += [
        f"Datum generisanja izveštaja: {datetime.now(timezone.utc).isoformat()}",
        f"Verzija sistema: Vindex AI (build {_get_git_hash()})",
    ]
    for m in metodologija:
        story.append(Paragraph(f"• {m}", s["meta"]))

    # ── Disclaimer / Footer ──────────────────────────────────────────────────
    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", thickness=0.5, color=_GREY))
    story.append(Paragraph(
        "OVAJ DOKUMENT NIJE PRAVNI, PORESKI NITI FINANSIJSKI SAVET, NITI ZVANIČNO REGULATORNO "
        "MIŠLJENJE. Predstavlja automatizovanu, AI-potpomognutu i deterministički generisanu "
        "pomoć pri organizaciji dokumentacije i proceni rizika, na osnovu informacija koje je "
        "korisnik samostalno uneo i javno dostupnih izvora (OFAC SDN lista, on-chain podaci). "
        "Ne predstavlja garanciju usklađenosti niti zamenu za pregled od strane kvalifikovanog "
        "poreskog savetnika, advokata ili licenciranog compliance profesionalca. Vindex AI ne "
        "preuzima odgovornost za odluke donete na osnovu ovog dokumenta.",
        s["disclaimer"],
    ))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "Vindex AI — Softver za upravljanje pravnim predmetima • Poverljivo",
        ParagraphStyle("footer", fontName="Helvetica", fontSize=7, textColor=_GREY, alignment=1),
    ))

    doc.build(story)
    return buf.getvalue()
