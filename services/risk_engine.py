# -*- coding: utf-8 -*-
"""
Procesni rizik predmeta — jedini deterministicki izvor istine (G-027, AR-01).

AR-01: nijedan LLM izlaz ne sme biti jedini izvor poslovnog stanja (rizik,
status, rok, spremnost, prioritet) — LLM sme samo da ga interpretira/objasni.
Svaki UI/API element koji prikazuje "procesni rizik predmeta" MORA da poziva
ovu funkciju, ne da racuna svoju verziju. Pre ove funkcije, matter_intel.py i
Cockpit (api.py) su nezavisno racunali dva razlicita broja za isti koncept —
empirijski potvrdjeno (scripts/g027_risk_validation.py, 2026-07-20): Cockpit
je vratio "srednji" za 16/16 predmeta bez varijanse, dok je deterministicka
formula ispravno pratila stvarne podatke.

Logika je 1:1 prenesena iz routers/matter_intel.py (bila je inline u ruti) —
ponasanje NAMERNO nepromenjeno, ovo je ekstrakcija, ne redizajn formule.
"""
import logging
from datetime import datetime, timezone
from typing import Any

# TASK 004 — jedan kanonski derivation layer. `pokrivenost_procene` je već
# jedini vlasnik pojma „koliko je tvrdnji procenjeno" (TASK 003B); ovde se
# KORISTI, ne kopira. Nijedan potrošač ne sme sam izvoditi ovo stanje.
from shared.evidence_write import (
    IZVORI_PROCENJENO,
    KOLONA_IZVOR_SNAGE,
    POKRIVENOST_NEMA_TVRDNJI,
    pokrivenost_procene,
)

logger = logging.getLogger("vindex.risk_engine")

# TASK 004 — `snaga_dokaza` je do sada mešao DVE ose: postojanje tvrdnji
# („Nema dokaza") i kvalitet procenjenih („Jaka/Srednja/Slaba"). Zbog toga je
# predmet sa tvrdnjama koje niko nije procenio bio nerazlučiv od praznog
# predmeta. Ova vrednost razdvaja te dve ose: „Nema dokaza" od sada znači
# STROGO da tvrdnji nema, a ovo da tvrdnje postoje ali nijedna nije procenjena.
# Nije strength klasa -- ne ulazi ni u jedan brojač, procenat ni bonus/kaznu.
SNAGA_NEPROCENJENO = "Nije procenjeno"


def calculate_procesni_rizik(
    dokazi: list[dict],
    dokumenti: list[dict],
    rocista: list[dict],
    tip_predmeta: str,
    expected_docs: dict[str, list[str]],
) -> dict[str, Any]:
    """
    dokazi:     redovi iz predmet_dokazi (snaga,kategorija,pravni_element)
    dokumenti:  redovi iz predmet_dokumenti (mora imati tip_dokaza da bi
                nedostajuci_dokazi bilo tacno — vidi G-028 napomenu u
                routers/matter_intel.py, ovo ponasanje je NEPROMENJENO)
    rocista:    redovi iz rocista (mora imati 'datum' polje)
    expected_docs: EXPECTED_DOCS mapa iz shared.constants
    """
    now = datetime.now(timezone.utc)

    # ── Dokazi analiza ───────────────────────────────────────────────────────
    # TASK 004: strength se računa ISKLJUČIVO nad procenjenim tvrdnjama.
    # Ranije je stajalo `d.get("snaga", "srednja")` nad SVIM redovima -- a pošto
    # je `predmet_dokazi.snaga` NOT NULL DEFAULT 'srednja', svaka NEPROCENJENA
    # tvrdnja je ulazila u imenilac kao procenjena tvrdnja srednje snage. To je
    # razvodnjavalo advokatovu izričitu ocenu (10 neprocenjenih tvrdnji je
    # obaralo „Jaka" na „Srednja") i maskiralo slabu evidenciju kao srednju.
    pokrivenost = pokrivenost_procene(dokazi)
    procenjeni = [d for d in dokazi if (d or {}).get(KOLONA_IZVOR_SNAGE) in IZVORI_PROCENJENO]

    snaga_count = {"jaka": 0, "srednja": 0, "slaba": 0}
    for d in procenjeni:
        # Bez `default="srednja"`: procenjen red UVEK nosi `snaga`. Red bez nje
        # je greška podataka i ne sme se tiho prebrojati kao srednji.
        s = d.get("snaga")
        if s in snaga_count:
            snaga_count[s] += 1
    ukupno = sum(snaga_count.values())

    if ukupno == 0:
        # Dve različite činjenice, dva različita iskaza (Gate 008/009).
        snaga_label = (
            "Nema dokaza" if pokrivenost["status"] == POKRIVENOST_NEMA_TVRDNJI
            else SNAGA_NEPROCENJENO
        )
        snaga_pct = 0
    else:
        jaka_pct = snaga_count["jaka"] / ukupno
        sred_pct = snaga_count["srednja"] / ukupno
        if jaka_pct >= 0.5:
            snaga_label = "Jaka"
            snaga_pct = int(jaka_pct * 100)
        elif jaka_pct + sred_pct >= 0.6:
            snaga_label = "Srednja"
            snaga_pct = int((jaka_pct + sred_pct) * 100)
        else:
            snaga_label = "Slaba"
            snaga_pct = max(10, int(jaka_pct * 100))

    # ── Nedostajući dokumenti ────────────────────────────────────────────────
    expected = expected_docs.get(tip_predmeta, expected_docs["ostalo"])
    postojeci_tipovi = {d.get("tip_dokaza") for d in dokumenti if d.get("tip_dokaza")}
    nedostajuci = [t for t in expected if t not in postojeci_tipovi]

    predstojeći = 0
    kriticni = 0
    zakasneli = 0
    kriticni_rocista: list[dict] = []
    for r in rocista:
        try:
            ds = r.get("datum", "") or ""
            # Project Synapse (2026-08-03) bug fix: was comparing a naive
            # datetime (built from a plain "YYYY-MM-DD" via +"T00:00:00", no
            # tz) against `now` (timezone-AWARE) whenever `datum` arrived as
            # a 10-char date string -- Python raises TypeError subtracting
            # naive from aware, silently swallowed by the bare except below,
            # so EVERY hearing stored as a plain date (the realistic shape
            # for a Postgres DATE column) was silently excluded from both
            # predstojeći_rokovi and kriticni_rokovi. Comparing calendar
            # dates (not instants) is also more semantically correct here --
            # a hearing "date" has no meaningful sub-day precision for this
            # day-count check.
            if len(ds) == 10:
                dana = (datetime.fromisoformat(ds).date() - now.date()).days
            else:
                dana = (datetime.fromisoformat(ds.replace("Z", "+00:00")).date() - now.date()).days
            if 0 <= dana <= 30:
                predstojeći += 1
            # BLACKSWAN-CRIT-002 fix (Operation Black Swan, Mission 001, Scenario 15):
            # `0 <= dana <= 7` treated a NEGATIVE dana (an OVERDUE hearing) as neither
            # upcoming nor critical -- identical to "no deadline at all." Reproduced: a
            # hearing 5 days overdue scored IDENTICAL nivo/health to one 25 days out.
            # An overdue hearing is MORE urgent than one still within the 7-day window,
            # not less -- now always critical, and counted separately so a caller can
            # distinguish "still time" from "already missed."
            if dana < 0:
                zakasneli += 1
                kriticni += 1
                kriticni_rocista.append(r)
            elif dana <= 7:
                kriticni += 1
                kriticni_rocista.append(r)
        except Exception as _e:
            # Program Phoenix, Mission 003 (LIVINGSYS-DEBT-055): this exact loop has already
            # hidden 2 real bugs behind a silent except before (naive/aware datetime mismatch,
            # then the negative-dana overdue-hearing bug -- see the 2 comments above). A
            # malformed/unparseable `datum` is silently excluded from risk scoring exactly like
            # "no hearing exists" -- now logged (not raised, behavior unchanged) so a 3rd
            # instance of this pattern doesn't go undetected for months like the first two did.
            logger.warning(
                "[RISK_ENGINE] rociste sa nevalidnim datumom preskočen u proračunu rizika (id=%s, datum=%r): %s",
                r.get("id"), r.get("datum"), _e,
            )

    # ── Procesni rizik ───────────────────────────────────────────────────────
    rizik_score = 50
    if ukupno == 0:
        rizik_score += 20
    elif snaga_label == "Jaka":
        rizik_score -= 20
    elif snaga_label == "Slaba":
        rizik_score += 15
    if len(nedostajuci) >= 3:
        rizik_score += 15
    if kriticni > 0:
        rizik_score += 20
    if zakasneli > 0:
        # An overdue deadline is a more severe signal than a merely-approaching one --
        # additional escalation on top of the kriticni bump above.
        rizik_score += 15

    if rizik_score <= 35:
        procesni_rizik = "Nizak"
        rizik_boja = "green"
    elif rizik_score <= 60:
        procesni_rizik = "Srednji"
        rizik_boja = "orange"
    else:
        procesni_rizik = "Visok"
        rizik_boja = "red"

    health = 100 - rizik_score
    health = max(5, min(95, health))

    return {
        "nivo": procesni_rizik,
        "boja": rizik_boja,
        "health_score": health,
        "snaga_dokaza": snaga_label,
        "snaga_pct": snaga_pct,
        "snaga_detalji": snaga_count,
        # TASK 004 — COVERAGE OSA, aditivno. Strength kaže KOLIKO su jaki
        # procenjeni dokazi; ovo kaže KOLIKO ih je uopšte procenjeno. Dve
        # nezavisne ose; nijedna se ne sme izvoditi iz druge.
        "broj_tvrdnji": pokrivenost["broj_tvrdnji"],
        "broj_procenjenih": pokrivenost["broj_procenjenih"],
        "pokrivenost_procene": pokrivenost["status"],
        "nedostajuci_dokazi": nedostajuci,
        "nedostajuci_count": len(nedostajuci),
        "predstojeći_rokovi": predstojeći,
        "kriticni_rokovi": kriticni,
        # BLACKSWAN-CRIT-002: overdue hearings, a subset of kriticni_rokovi/
        # kriticni_rocista above -- surfaced separately so a caller can say "N rokova
        # je već prekoračeno" instead of collapsing it into the generic critical count.
        "zakasneli_rokovi": zakasneli,
        # Project Synapse (2026-08-03): the actual critical rociste rows, not
        # just the count above -- added so a caller can emit EventType.ROK_KRITICAN
        # (a real, already-wired proactive-alert handler, previously never
        # triggered by anything) without re-deriving the same 0<=days<=7 date
        # math a second time. Purely additive -- existing callers reading only
        # "kriticni_rokovi" are unaffected.
        "kriticni_rocista": kriticni_rocista,
    }


_NEDOSTAJUCI_LABELS = {
    "sudska_odluka": "sudsku odluku/presudu", "podnesak": "podnesak stranke",
    "ugovor": "relevantni ugovor", "dopis": "pisanu komunikaciju",
    "medicinska_dokumentacija": "medicinski nalaz", "finansijska_dokumentacija": "finansijsku dokumentaciju",
    "javna_isprava": "javnu ispravu", "vestacki_nalaz": "nalaz veštaka",
}

_TIPOVI_SR = {
    "parnicno": "parnični", "krivicno": "krivični", "radno": "radni",
    "upravno": "upravni", "porodicno": "porodični", "privredno": "privredni",
    "nepokretnosti": "predmet nepokretnosti", "ostalo": "predmet",
}


def identify_case_problems(rizik: dict[str, Any], tip_predmeta: str) -> list[dict[str, str]]:
    """
    Otkriveni problemi — jedini deterministicki izvor "sledece akcije" u
    celoj platformi (Core Consolidation Sec 1.2, 2026-07-22).

    Zamenjuje TRI nezavisne implementacije koje su ranije nezavisno
    "predlagale" sledeci korak (Cockpit sledeca_akcija/GPT, Matter Intel
    _compute_next_action/rule-based, Case Ready Score copilot_preporuka/GPT)
    jednom listom konkretnih, proverljivih nalaza. Ovo NIJE savet — ovo je
    analiza cinjenicnog stanja predmeta. Advokat odlucuje sta da radi sa tim.

    Ulaz je vec-izracunat `calculate_procesni_rizik()` recnik (jedini izvor
    tih brojeva, AR-01) — ova funkcija ne racuna nista novo o riziku, samo
    ga interpretira u listu problema.

    Vraca listu {"problem": str, "ozbiljnost": "kritican"|"vazan"|"info"},
    prazna lista = nema otkrivenih problema (predmet cist po ovim proverama).
    """
    problemi: list[dict[str, str]] = []

    kriticni = rizik.get("kriticni_rokovi", 0)
    if kriticni > 0:
        problemi.append({
            "problem": f"{kriticni} kritičan rok(a) u narednih 7 dana",
            "ozbiljnost": "kritican",
        })

    if rizik.get("snaga_dokaza") == "Nema dokaza":
        tip_sr = _TIPOVI_SR.get(tip_predmeta, "predmet")
        problemi.append({
            "problem": f"Nema uploadovanih dokaza za {tip_sr} predmet" if tip_sr != "predmet"
                       else "Nema uploadovanih dokaza za predmet",
            "ozbiljnost": "kritican",
        })
    elif rizik.get("snaga_dokaza") == SNAGA_NEPROCENJENO:
        # TASK 004: do sada je OVAJ slučaj upadao u granu iznad i tvrdio da
        # dokaza nema -- činjenično netačno za predmet koji ima tvrdnje.
        # Potrebna radnja nije „prikupi dokaze" nego „proceni postojeće".
        _n = rizik.get("broj_tvrdnji") or 0
        problemi.append({
            "problem": f"{_n} tvrdnji u spisu nije procenjeno — dokazna snaga nije utvrđena",
            "ozbiljnost": "vazan",
        })
    elif (rizik.get("pokrivenost_procene") == "EVIDENCE_PARTIAL"):
        _n = rizik.get("broj_tvrdnji") or 0
        _p = rizik.get("broj_procenjenih") or 0
        problemi.append({
            "problem": f"Procenjeno {_p} od {_n} tvrdnji — ocena snage počiva na delu spisa",
            "ozbiljnost": "vazan",
        })

    for t in (rizik.get("nedostajuci_dokazi") or [])[:3]:
        problemi.append({
            "problem": f"Nedostaje {_NEDOSTAJUCI_LABELS.get(t, t)} u spisu",
            "ozbiljnost": "vazan",
        })

    predstojeci = rizik.get("predstojeći_rokovi", 0)
    if predstojeci >= 3:
        problemi.append({
            "problem": f"{predstojeci} predstojećih rokova u narednih 30 dana — nije prioritizovano",
            "ozbiljnost": "vazan",
        })

    if rizik.get("snaga_dokaza") == "Slaba":
        problemi.append({
            "problem": "Dokazi slabe snage — nedostaje veštačenje ili dodatni svedoci",
            "ozbiljnost": "info",
        })

    return problemi
