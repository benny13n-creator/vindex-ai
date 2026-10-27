"""Upis roka koji je advokat uneo ispravljajući AI predlog (N4, POST /api/rokovi/{id}/ispravi).

Ruta odluke (`routers/rok_odluka.py`) po ugovoru FAZA 6.5 samo ČITA hronologiju; odluka (potvrda/odbijanje)
ide kroz `shared/rok_potvrda.py`. Ispravka zato ovde upisuje NOV red — `izvor=HUMAN_DIRECT`, isti predmet i
dokument kao predlog — a sam predlog se ne menja (odbijanje predloga radi ruta odluke, ne ovaj modul).
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from shared import rokovi as _rokovi_domen

AKTER_ISPRAVKE = "Advokat (ispravka predloga)"


def postojeca_neupisana_veza(supa, *, uid: str, predlog: dict, opis: str, datum: date) -> Optional[str]:
    """Id već upisanog reda ispravke (isti predmet, opis, datum, akter ispravke) — ponovni pokušaj ga koristi umesto da
    napravi drugi red. Pad čitanja = None (pravi se nov id; predlog se odbija vezom na NJEGA, pa nema dve obaveze)."""
    try:
        post_r = (supa.table("predmet_hronologija").select("id")
                  .eq("user_id", uid).eq("predmet_id", predlog.get("predmet_id")).eq("datum_iso", datum.isoformat())
                  .eq("akter", AKTER_ISPRAVKE).eq("dogadjaj", opis[:500]).limit(1).execute())
        return (post_r.data or [{}])[0].get("id") if post_r and post_r.data else None
    except Exception:
        return None


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


def napomena_ispravke(rok_id: str) -> str:
    """Napomena potvrde ispravljenog roka u audit lancu — jedina veza ispravke i predloga (bez nove kolone)."""
    return f"Ispravka predloga roka {rok_id}"


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
        if red.get("action") == AKCIJA_POTVRDA and ((red.get("metadata") or {}).get("napomena") == trazena):
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
        napomena = str((red.get("metadata") or {}).get("napomena") or "")
        if red.get("action") == AKCIJA_ODBIJANJE and napomena.startswith(PREFIKS_ODBIJANJA):
            return napomena[len(PREFIKS_ODBIJANJA):].strip() or None
    return None
