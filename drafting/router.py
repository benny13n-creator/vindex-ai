# -*- coding: utf-8 -*-
"""
Drafting router — generate_draft(vrsta, opis) → dict.
Uses GPT-4o for field extraction; then fills the template deterministically.

Core Consolidation Sec 1.4 (2026-07-22) — interim ownership (NOT merged,
pilot-gated by explicit founder decision, unlike every other item in
VINDEX_CORE_CONSOLIDATION.md): this module owns the QUICK single-shot
draft path (POST /api/nacrt, wrapped by routers/drafting.py) — short
description in, deterministic template fill out, no case/RAG context.
6 of its 17 types (TEMPLATES in drafting/templates.py) are duplicated by
templates/podnesci.py (routers/drafting.py's POST /api/podnesak path)
under the SAME type keys with DIFFERENT template text — known, tracked
duplication, not an oversight. Do not resolve by intuition; the founder's
explicit instruction is an empirical pilot comparison decides which
survives. A third, unrelated freeform pipeline also exists
(routers/doc_templates.py, POST /api/doc-templates/generisi) — freeze on
adding new types there that duplicate this module's or podnesci.py's
types (see VINDEX_CORE_CONSOLIDATION.md Sec 1.4 / forensic audit Part 15 Q8).
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import date
from string import Formatter

from openai import OpenAI

from shared.llm_retry import llm_retry
from shared.drafting_grounding import izvori_kontekst, CRITIQUE_SYSTEM

from .compliance import formatiraj_violations, proveri_uskladjenost
from .templates import TEMPLATES

logger = logging.getLogger(__name__)

_client: OpenAI | None = None

# Program Phoenix, Mission 010 (LIVINGSYS-DEBT-013): this quick-draft path
# used to ask GPT to invent a specific ZOO/ZR statute article number
# (pravni_osnov_clan, pravni_osnov, zakonski_clan fields) with zero RAG
# retrieval and zero critique pass, embedded directly into real legal
# document text -- the sibling /api/podnesak path already had both. Same
# availability-guard shape as routers/court_predictor.py's _RAG_AVAILABLE.
try:
    from app.services.retrieve import retrieve_documents
    _RAG_AVAILABLE = True
except Exception:
    retrieve_documents = None
    _RAG_AVAILABLE = False


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _client


@llm_retry
def _call_openai(system: str, user: str, max_tokens: int = 2000, response_format: dict | None = None) -> str:
    """FAZA 2 (2026-07-24): @llm_retry -- max 3 pokušaja sa exponential
    backoff-om za rate-limit/5xx/timeout/connection greške; 400/401 se
    NE ponavljaju."""
    kwargs = dict(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0,
        max_tokens=max_tokens,
        timeout=30.0,
    )
    if response_format is not None:
        kwargs["response_format"] = response_format
    r = _get_client().chat.completions.create(**kwargs)
    return (r.choices[0].message.content or "").strip()


def _ekstraktuj_json(tekst: str) -> dict:
    """Parsira JSON iz LLM odgovora, toleriše markdown code fences."""
    cleaned = re.sub(r"```(?:json)?\s*", "", tekst).replace("```", "").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    return {}


def normalize_date(date_str: str) -> str:
    """Uklanja trailing tačke iz datuma (LLM vraća '15.01.2025.' → '15.01.2025')."""
    return date_str.strip().rstrip(".")


_DATE_FIELDS = {
    "datum", "datum_aneksa", "datum_potpisivanja", "datum_prestanka",
    "datum_zakljucenja_originalnog_ugovora",
}


def _normalize_date_fields(fields: dict) -> dict:
    """Normalizuje sve datumske vrednosti u fields (strip trailing period)."""
    out = dict(fields)
    for key in _DATE_FIELDS:
        if key in out and isinstance(out[key], str) and out[key]:
            out[key] = normalize_date(out[key])
    return out


def _today_str() -> str:
    return date.today().strftime("%d.%m.%Y")


DEFAULTS_REGISTRY: dict[str, dict] = {
    "ugovor_neodredjeno": {
        "datum": _today_str,
        "mesto": lambda: "Beograd",
        "radno_vreme": lambda: "40",
        "otkazni_rok_zaposleni": lambda: "30 radnih dana",
        "otkazni_rok_poslodavac": lambda: "30 radnih dana",
        "rok_isplate": lambda: "15.",
    },
    "ugovor_odredjeno": {
        "datum": _today_str,
        "mesto": lambda: "Beograd",
        "radno_vreme": lambda: "40",
        "otkazni_rok_zaposleni": lambda: "30 radnih dana",
        "otkazni_rok_poslodavac": lambda: "30 radnih dana",
        "rok_isplate": lambda: "15.",
    },
    "aneks": {
        "datum_aneksa": _today_str,
        "mesto": lambda: "Beograd",
    },
    "sporazumni_raskid": {
        "datum_potpisivanja": _today_str,
        "mesto": lambda: "Beograd",
    },
    "punomocje": {
        "datum": _today_str,
        "mesto": lambda: "Beograd",
    },
    "ugovor_kupoprodaja": {
        "datum": _today_str,
        "mesto": lambda: "Beograd",
    },
    "ugovor_zakup": {
        "datum": _today_str,
        "mesto": lambda: "Beograd",
    },
    "prigovor_platni_nalog": {
        "datum": _today_str,
        "mesto": lambda: "Beograd",
    },
    "predlog_privremena_mera": {
        "datum": _today_str,
    },
    "tuzba_razvod": {
        "datum": _today_str,
    },
    "krivicna_prijava": {
        "datum": _today_str,
    },
}


def apply_defaults(fields: dict, vrsta: str) -> dict:
    """Popunjava nedostajuća polja podrazumevanim vrednostima bez gaženja eksplicitnih."""
    out = dict(fields)
    defaults = DEFAULTS_REGISTRY.get(vrsta, {})
    for key, factory in defaults.items():
        existing = out.get(key)
        if not existing:
            out[key] = factory()
    return out


def _popuni_sablon(sablon: str, fields: dict) -> str:
    """
    Popunjava {PLACEHOLDER} u šablonu.
    Samo ključevi koji nisu prisutni u fields dobijaju '[... — POPUNITI]'.
    Prazna string vrednost ("")  se tretira kao validna i ne zamenjuje se.
    """
    class _DefaultDict(dict):
        def __missing__(self, key: str) -> str:
            return f"[{key.replace('_', ' ')} — POPUNITI]"

    placeholders = {
        fname
        for _, fname, _, _ in Formatter().parse(sablon)
        if fname is not None
    }
    merged = _DefaultDict()
    for p_upper in placeholders:
        p_lower = p_upper.lower()
        if p_lower in fields:
            val = fields[p_lower]
            merged[p_upper] = val if val is not None else ""
        else:
            merged[p_upper] = f"[{p_upper.replace('_', ' ')} — POPUNITI]"

    return sablon.format_map(merged)


def _pripremi_ugovor_fields(fields: dict, vrsta: str) -> dict:
    """Kreira vrednosti za kondicionalne sekcije ugovornih šablona."""
    out = {k: (v if v is not None else "") for k, v in fields.items()}

    # PIB + MB + zastupnik — Bug 10
    pib = out.get("poslodavac_pib", "")
    mb = out.get("poslodavac_mb", "")
    zastupnik = out.get("poslodavac_zastupnik", "")

    pib_mb_parts = []
    if pib:
        pib_mb_parts.append(f"PIB: {pib}")
    if mb:
        pib_mb_parts.append(f"MB: {mb}")
    out["poslodavac_pib_clan"] = (", " + ", ".join(pib_mb_parts)) if pib_mb_parts else ""
    out["poslodavac_zastupnik_clan"] = (f", koga zastupa {zastupnik}") if zastupnik else ""

    # Probni rad
    probni = out.get("probni_rad", "")
    if probni:
        out["probni_rad_clan"] = (
            f"Zaposleni se prima na rad uz probni rad u trajanju od {probni}, "
            f"u skladu sa čl. 36 Zakona o radu."
        )
    else:
        out["probni_rad_clan"] = "Probni rad nije ugovoren."

    # Prekovremeni
    out["prekovremeni_clan"] = (
        "Prekovremeni rad može biti naložen u skladu sa čl. 53 Zakona o radu "
        "(max 8h nedeljno, 32h mesečno, 250h godišnje)."
    )

    # Godišnji odmor
    dani = out.get("godisnji_odmor_dani", "")
    if dani:
        out["godisnji_odmor_clan"] = (
            f"Zaposleni ima pravo na godišnji odmor u trajanju od {dani} radnih dana, "
            f"u skladu sa čl. 68–76 Zakona o radu."
        )
    else:
        out["godisnji_odmor_clan"] = (
            "Zaposleni ima pravo na godišnji odmor u skladu sa čl. 68–76 Zakona o radu "
            "(minimum 20 radnih dana)."
        )

    # Tajnost
    ima_tajnost = out.get("ima_tajnost") in (True, "true", "True", "1", 1)
    if ima_tajnost:
        rok = out.get("tajnost_rok", "")
        rok_tekst = (
            f" u periodu od {rok} nakon prestanka radnog odnosa"
            if rok else
            " i nakon prestanka radnog odnosa"
        )
        out["tajnost_clan"] = (
            f"Zaposleni je obavezan da čuva poverljive informacije Poslodavca{rok_tekst}, "
            f"u skladu sa čl. 83 Zakona o radu."
        )
    else:
        out["tajnost_clan"] = (
            "Zaposleni je obavezan da čuva poverljive informacije Poslodavca u skladu "
            "sa zakonom i opštim aktima Poslodavca."
        )

    # Konkurentska klauzula
    ima_konk = out.get("ima_konkurentsku") in (True, "true", "True", "1", 1)
    if ima_konk:
        trajanje = out.get("konkurentska_trajanje", "[TRAJANJE — POPUNITI]")
        naknada = out.get("konkurentska_naknada_procenat", "")
        naknada_tekst = (
            f" Za vreme trajanja zabrane Poslodavac isplaćuje Zaposlenom naknadu "
            f"od {naknada}% poslednje zarade mesečno."
            if naknada else ""
        )
        out["konkurentska_clan"] = (
            f"Zaposleni se obavezuje da po prestanku radnog odnosa neće raditi za "
            f"konkurentske firme niti osnivati preduzeće u istoj delatnosti u periodu "
            f"od {trajanje}, u skladu sa čl. 161–162 Zakona o radu.{naknada_tekst}"
        )
    else:
        out["konkurentska_clan"] = "Konkurentska klauzula nije ugovorena."

    # Bonus
    bonus = out.get("bonus_procenat", "")
    if bonus:
        out["bonus_clan"] = (
            f"Zaposleni može ostvariti pravo na varijabilni deo zarade (bonus) "
            f"do {bonus}% osnovne zarade, na osnovu procene radnog učinka."
        )
    else:
        out["bonus_clan"] = ""

    return out


def _pripremi_sporazum_fields(fields: dict) -> dict:
    out = {k: (v if v is not None else "") for k, v in fields.items()}

    # Original ugovor referenca — Bug 9
    datum_orig = out.get("datum_zakljucenja_originalnog_ugovora", "")
    if datum_orig:
        out["original_ugovor_clan"] = f", zasnovan po Ugovoru o radu od {datum_orig},"
    else:
        out["original_ugovor_clan"] = ""

    # Otpremnina
    ima_otp = out.get("ima_otpremninu") in (True, "true", "True", "1", 1)
    if ima_otp:
        iznos = out.get("otpremnina_iznos", "[IZNOS — POPUNITI]")
        out["otpremnina_clan"] = (
            f"Poslodavac se obavezuje da Zaposlenom isplati otpremninu u iznosu "
            f"od {iznos} dinara."
        )
    else:
        out["otpremnina_clan"] = ""

    napomena = out.get("napomena", "")
    out["napomena_clan"] = napomena if napomena else ""
    return out


def _pripremi_punomocje_fields(fields: dict) -> dict:
    out = {k: (v if v is not None else "") for k, v in fields.items()}
    ima_sup = out.get("ima_supstituciju") in (True, "true", "True", "1", 1)
    out["supstitucija_clan"] = (
        "Punomoćnik je ovlašćen da izda supstituciono punomoćje."
        if ima_sup else
        "Punomoćnik nije ovlašćen da izda supstituciono punomoćje."
    )
    return out


def _pripremi_kupoprodaja_fields(fields: dict) -> dict:
    out = {k: (v if v is not None else "") for k, v in fields.items()}
    return out


def _pripremi_zakup_fields(fields: dict) -> dict:
    out = {k: (v if v is not None else "") for k, v in fields.items()}
    depozit = out.get("depozit", "").strip()
    out["depozit_clan"] = (
        f"Zakupac plaća depozit u iznosu od {depozit} dinara pre preuzimanja nepokretnosti. "
        "Depozit se vraća po isteku ugovora, umanjeno za eventualne nastale štete."
        if depozit else
        "Ugovorne strane su se sporazumele da nema depozita."
    )
    return out


def _pripremi_razvod_fields(fields: dict) -> dict:
    out = {k: (v if v is not None else "") for k, v in fields.items()}
    deca = out.get("deca_opis", "").strip()
    if deca:
        out["deca_clan"] = f"Iz braka postoji zajednička deca: {deca}."
        out["zahtev_deca_clan"] = (
            "1. ZAHTEV U POGLEDU DECE\n" + (out.get("zahtev_deca", "") or "Staranje nad zajedničkom decom poverava se tužiocu.")
        )
        out["petitum_deca"] = "2. Poverava se staranje nad zajedničkom decom tužiocu;\n"
    else:
        out["deca_clan"] = "Iz braka nema zajedničke dece."
        out["zahtev_deca_clan"] = ""
        out["petitum_deca"] = ""
    zahtev_imov = out.get("zahtev_imovina", "").strip()
    if zahtev_imov:
        out["zahtev_imovina_clan"] = f"2. ZAHTEV U POGLEDU BRAČNE TEKOVINE\n{zahtev_imov}"
        out["petitum_imovina"] = "3. Raspoređuje se bračna tekovina u skladu sa iznetim zahtevom;\n"
    else:
        out["zahtev_imovina_clan"] = ""
        out["petitum_imovina"] = ""
    return out


def _pripremi_krivicna_prijava_fields(fields: dict) -> dict:
    out = {k: (v if v is not None else "") for k, v in fields.items()}
    jmbg = out.get("podnosilac_jmbg", "").strip()
    out["podnosilac_jmbg_clan"] = f"JMBG: {jmbg}" if jmbg else ""
    return out


def _pripremi_privremena_mera_fields(fields: dict) -> dict:
    out = {k: (v if v is not None else "") for k, v in fields.items()}
    iznos = out.get("iznos_potrazivanja", "").strip()
    out["iznos_potrazivanja_clan"] = f"Vrednost potraživanja: {iznos} dinara." if iznos else ""
    return out


def _pripremi_fields(fields: dict, vrsta: str) -> dict:
    if vrsta in ("ugovor_neodredjeno", "ugovor_odredjeno"):
        return _pripremi_ugovor_fields(fields, vrsta)
    if vrsta == "sporazumni_raskid":
        return _pripremi_sporazum_fields(fields)
    if vrsta == "punomocje":
        return _pripremi_punomocje_fields(fields)
    if vrsta == "ugovor_kupoprodaja":
        return _pripremi_kupoprodaja_fields(fields)
    if vrsta == "ugovor_zakup":
        return _pripremi_zakup_fields(fields)
    if vrsta == "tuzba_razvod":
        return _pripremi_razvod_fields(fields)
    if vrsta == "krivicna_prijava":
        return _pripremi_krivicna_prijava_fields(fields)
    if vrsta == "predlog_privremena_mera":
        return _pripremi_privremena_mera_fields(fields)
    return {k: (v if v is not None else "") for k, v in fields.items()}


def _kriticki_pregled(nacrt: str, kontekst: str, tip_naziv: str) -> tuple[str, bool]:
    """Drugi, brz LLM prolaz nad već generisanim nacrtom: proverava izmišljene
    članove zakona van [IZVOR-n] konteksta i obavezne formalne elemente
    dokumenta, i ispravlja ih ako postoje. Program Phoenix, Mission 010
    (LIVINGSYS-DEBT-013): sinhrona verzija routers/drafting.py::
    _critique_and_refine_draft -- generate_draft ostaje sync (već se izvršava
    unutar asyncio.to_thread iz routers/drafting.py::nacrt), pa je ovaj prolaz
    napisan sinhrono umesto da se generate_draft menja u async. Isti prompt
    (shared/drafting_grounding.py::CRITIQUE_SYSTEM), ista JSON šema, ista
    fallback logika, ista (nacrt, critique_applied) semantika kao Mission
    009's LIVINGSYS-DEBT-015 fix. Nikad ne baca: svaka greška pada nazad na
    originalni nacrt."""
    try:
        user_msg = (
            f"VRSTA PODNESKA: {tip_naziv}\n\n"
            f"IZVORI (RAG kontekst sa oznakama):\n"
            f"{kontekst or '(nema dostavljenih izvora -- oslanjaj se samo na opšte pravno znanje)'}\n\n"
            f"NACRT ZA PROVERU:\n{nacrt}"
        )
        raw = _call_openai(CRITIQUE_SYSTEM, user_msg, max_tokens=4000, response_format={"type": "json_object"})
        kritika = _ekstraktuj_json(raw)

        izmisljeni = kritika.get("izmisljeni_navodi") or []
        nedostaje = kritika.get("nedostaju_elementi") or []
        ima_problema = bool(kritika.get("ima_izmisljenih_navoda")) or bool(izmisljeni) or bool(nedostaje)

        if not ima_problema:
            return nacrt, True

        ispravljen = (kritika.get("ispravljen_tekst") or "").strip()
        if not ispravljen:
            logger.warning("Critique pass (nacrt) prijavio probleme ali nije vratio ispravljen tekst")
            return nacrt, False

        logger.info(
            "Critique pass (nacrt) ispravio nacrt: izmisljeni_navodi=%s nedostaju_elementi=%s",
            izmisljeni, nedostaje,
        )
        return ispravljen, True
    except Exception as exc:
        logger.warning("Critique pass (nacrt) neuspešan: %s -- vraćam originalni nacrt", exc)
        return nacrt, False


def generate_draft(vrsta: str, opis: str, user_id: str = "") -> dict:
    """
    Generiše strukturiran nacrt dokumenta.

    vrsta   — ključ iz TEMPLATES registra
    opis    — slobodan opis od korisnika
    user_id — opciono; ako postoji playbook_{user_id} u Pinecone, injektuje style kontekst

    Vraća {"status": "success", "data": tekst} ili {"status": "error", "message": ...}.
    """
    tpl = TEMPLATES.get(vrsta)
    if tpl is None:
        return {
            "status": "error",
            "message": f"Nepoznat tip dokumenta: '{vrsta}'. "
                       f"Dostupni tipovi: {', '.join(TEMPLATES.keys())}.",
        }

    try:
        # ── 0. Playbook kontekst (P4.4) ──────────────────────────────────────
        playbook_blok = ""
        if user_id:
            try:
                from .playbook import search_playbook
                pb_results = search_playbook(user_id, opis, top_k=3)
                if pb_results:
                    playbook_blok = (
                        "\nPLAYBOOK KANCELARIJE:\n"
                        + "\n---\n".join(pb_results)
                        + "\nKoristi ovaj stil i formulacije.\n"
                    )
            except Exception:
                logger.warning("[PLAYBOOK] pretraga neuspešna — nastavljam bez playbook-a")

        # ── 0.5 RAG pretraga (Program Phoenix, Mission 010, LIVINGSYS-DEBT-013) ─
        kontekst = ""
        if _RAG_AVAILABLE:
            try:
                rag_upit = f"{tpl['label']}: {opis[:400]}"
                docs, _retrieval_meta = retrieve_documents(rag_upit, 5)
                kontekst = izvori_kontekst(docs)
            except Exception as exc:
                logger.warning("[NACRT RAG] pretraga neuspešna [vrsta=%s]: %s -- nastavljam bez konteksta", vrsta, exc)
                kontekst = ""

        # ── 1. Ekstrakcija polja ─────────────────────────────────────────────
        system_p = tpl["ekstrakcioni_prompt"]
        user_p = (
            f"OPIS:\n{opis}{playbook_blok}"
            + (f"\n\nZAKONSKI KONTEKST (RAG):\n{kontekst}" if kontekst else "")
        )
        raw_json = _call_openai(system_p, user_p, max_tokens=800)
        fields = _ekstraktuj_json(raw_json)

        # ── 2. Defaults za nedostajuća polja ─────────────────────────────────
        fields = apply_defaults(fields, vrsta)

        # ── 3. Normalizacija datuma ───────────────────────────────────────────
        fields = _normalize_date_fields(fields)

        # ── 4. Priprema kondicionalnih sekcija ───────────────────────────────
        fields_ready = _pripremi_fields(fields, vrsta)

        # ── 5. Popuni šablon ─────────────────────────────────────────────────
        sablon = tpl["sablon"]
        nacrt_tekst = _popuni_sablon(sablon, fields_ready)

        # ── 6. Critique & self-correction pass (Mission 010, LIVINGSYS-DEBT-013) ─
        # Proverava SAMO AI-generisani tekst, pre nego što se doda deterministički
        # compliance izveštaj ispod (taj izveštaj nije GPT-generisan, ne treba
        # critique proveru).
        nacrt_tekst, critique_applied = _kriticki_pregled(nacrt_tekst, kontekst, tpl["label"])

        # ── 7. Compliance check ──────────────────────────────────────────────
        compliance_tip = tpl.get("compliance_tip")
        violations: list[dict] = []
        if compliance_tip == "ugovor_o_radu":
            violations = proveri_uskladjenost(fields, vrsta)
        compliance_tekst = formatiraj_violations(violations)

        return {
            "status": "success",
            "data": nacrt_tekst + compliance_tekst,
            "critique_applied": critique_applied,
        }

    except Exception:
        logger.exception("Greška u generate_draft (vrsta=%s)", vrsta)
        return {
            "status": "error",
            "message": "Sistem je trenutno zauzet. Pokušajte ponovo.",
        }
