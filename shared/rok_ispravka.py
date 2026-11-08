"""Upis roka koji je advokat uneo ispravljajući AI predlog (N4, POST /api/rokovi/{id}/ispravi).

Ruta odluke (`routers/rok_odluka.py`) po ugovoru FAZA 6.5 samo ČITA hronologiju; odluka (potvrda/odbijanje)
ide kroz `shared/rok_potvrda.py`. Ispravka zato ovde upisuje NOV red — `izvor=HUMAN_DIRECT`, isti predmet i
dokument kao predlog — a sam predlog se ne menja (odbijanje predloga radi ruta odluke, ne ovaj modul).
"""
from __future__ import annotations

import json
import re
from datetime import date
from typing import Optional

from shared import rokovi as _rokovi_domen

AKTER_ISPRAVKE = "Advokat (ispravka predloga)"
_MESECI = ("januar", "februar", "mart", "april", "maj", "jun", "jul", "avgust", "septembar", "oktobar", "novembar", "decembar")


def upisi_ispravljen_rok(supa, *, nov_id: str, uid: str, predlog: dict, izvor: dict, opis: str, datum: date) -> Optional[str]:
    """Upisuje red ispravke sa UNAPRED određenim id-em (S1: predlog je već odbijen vezom na taj id). Izuzetak ide
    pozivaocu."""
    nov_r = supa.table("predmet_hronologija").insert({
        "id": nov_id,
        "predmet_id": predlog.get("predmet_id"), "user_id": uid, "dogadjaj": opis[:500],
        "datum": datum.isoformat(), "datum_iso": datum.isoformat(),
        "vaznost": predlog.get("vaznost") or _rokovi_domen.normalizuj_vaznost("bitan"),
        "akter": AKTER_ISPRAVKE, "izvor": _rokovi_domen.IZVOR_HUMAN_DIRECT,
        "dokument_id": izvor.get("dokument_id"), "dokument_naziv": izvor.get("dokument_naziv"),
        **_rokovi_domen.oznake(vrsta=_rokovi_domen.VRSTA_ROK, supa=supa),
    }).execute()
    return (nov_r.data or [{}])[0].get("id") or None


def _bez_datuma(tekst: str, stari: Optional[str]) -> str:
    """Izostavlja („…“) SAMO ispravljeni datum (brojčano ili sa nazivom meseca, i ćirilicom preslovljen nije potreban —
    citat je onakav kakav je pročitan); ostali datumi rečenice ostaju."""
    try:
        g, m, d = (int(x) for x in str(stari)[:10].split("-"))
    except (TypeError, ValueError):
        return tekst
    mesec = _MESECI[m - 1]
    obrazac = re.compile(rf"(?<!\d)0?{d}\s*\.\s*(?:0?{m}\s*\.|{mesec[:-2] if mesec.endswith('ar') else mesec}\w*)\s*{g}\.?(?!\d)", re.I)
    return obrazac.sub("…", tekst)


def opis_ispravke(opis_advokata: Optional[str], opis_predloga: Optional[str], datum: date,
                  stari_datum: Optional[str] = None) -> str:
    """Naziv ispravljenog roka. Advokatov tekst ima prednost. Bez njega se preuzima naziv predloga — ali naziv koji
    CITIRA dokument („Rok iz dokumenta…: <rečenica>“, `shared.rokovi.naslov_roka_iz_izvora`) nosi datum iz dokumenta,
    koji je advokat upravo ispravio; zato se izričito kaže da je datum ispravio advokat (S10)."""
    sopstveni = (opis_advokata or "").strip()
    if sopstveni:
        return sopstveni[:500]
    osnova = (opis_predloga or "").strip() or "Rok"
    if osnova.startswith("Rok iz dokumenta") and ": " in osnova:
        # datum iz citata je upravo proglašen pogrešnim — izostavlja se („…“), tačan datum se navodi izričito
        osnova = f"{_bez_datuma(osnova, stari_datum)} — datum ispravio advokat: {datum.strftime('%d.%m.%Y.')}"
    return osnova[:500]


def napomena_ispravke(rok_id: str) -> str:
    """Napomena potvrde ispravljenog roka u audit lancu — jedina veza ispravke i predloga (bez nove kolone)."""
    return f"Ispravka predloga roka {rok_id}"


def _audit_metadata(raw: object) -> dict:
    """Decode audit metadata from JSONB object or the writer's JSONB string.

    Malformed audit data fails closed so prior corrections are never ignored.
    """
    if raw is None:
        return {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid correction audit metadata") from exc
    if not isinstance(raw, dict):
        raise ValueError("Invalid correction audit metadata type")
    return raw


def postojeca_ispravka(supa, *, uid: str, predlog: dict, rok_id: str) -> Optional[str]:
    """Id POTVRĐENE ispravke ovog predloga, ili None. G3: ako odbijanje predloga padne posle potvrđene ispravke,
    predlog ostaje nepotvrđen — bez ove provere druga ispravka ili potvrda predloga pravila je DRUGU potvrđenu obavezu.
    Pad čitanja ide pozivaocu (fail-closed: ništa se ne upisuje)."""
    from shared.rok_potvrda import AKCIJA_POTVRDA, procitaj_lanac
    kandidati = (supa.table("predmet_hronologija").select("id")
                 .eq("user_id", uid).eq("predmet_id", predlog.get("predmet_id")).eq("akter", AKTER_ISPRAVKE).execute())
    ids = [r.get("id") for r in (kandidati.data or []) if r.get("id")]
    if not ids:
        return None
    trazena = napomena_ispravke(rok_id)
    for red in procitaj_lanac(ids, "action, resource_id, metadata, seq"):
        if red.get("action") == AKCIJA_POTVRDA and (_audit_metadata(red.get("metadata")).get("napomena") == trazena):
            return str(red.get("resource_id"))
    return None


PREFIKS_ODBIJANJA = "Ispravljen — tačan rok je "


def napomena_odbijanja(nov_id: str) -> str:
    """Napomena ODBIJANJA predloga — veza predlog → ispravljen rok, upisana PRE potvrde ispravke (S1)."""
    return f"{PREFIKS_ODBIJANJA}{nov_id}"


def ispravka_iz_odbijanja(rok_id: str) -> Optional[str]:
    """Id ispravljenog roka iz napomene odbijanja predloga, ili None. Pad čitanja ide pozivaocu (fail-closed)."""
    from shared.rok_potvrda import AKCIJA_ODBIJANJE, procitaj_lanac
    for red in procitaj_lanac([rok_id], "action, resource_id, metadata, seq"):
        if red.get("action") != AKCIJA_ODBIJANJE:
            continue
        napomena = str(_audit_metadata(red.get("metadata")).get("napomena") or "")
        if napomena.startswith(PREFIKS_ODBIJANJA):
            return napomena[len(PREFIKS_ODBIJANJA):].strip() or None
    return None
