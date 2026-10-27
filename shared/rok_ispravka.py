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


def upisi_ispravljen_rok(supa, *, uid: str, predlog: dict, izvor: dict, opis: str, datum: date) -> Optional[str]:
    """Vraća id ispravljenog roka; ponovni pokušaj posle delimičnog neuspeha koristi postojeću ispravku (isti
    predmet, opis, datum, akter ispravke) umesto da napravi drugi nov rok. Izuzetak upisa ide pozivaocu."""
    try:
        post_r = (supa.table("predmet_hronologija").select("id")
                  .eq("user_id", uid).eq("predmet_id", predlog.get("predmet_id")).eq("datum_iso", datum.isoformat())
                  .eq("akter", AKTER_ISPRAVKE).eq("dogadjaj", opis[:500]).limit(1).execute())
        postojeci = (post_r.data or [{}])[0].get("id") if post_r and post_r.data else None
    except Exception:
        postojeci = None
    if postojeci:
        return postojeci
    nov_r = supa.table("predmet_hronologija").insert({
        "predmet_id": predlog.get("predmet_id"), "user_id": uid, "dogadjaj": opis[:500],
        "datum": datum.isoformat(), "datum_iso": datum.isoformat(),
        "vaznost": predlog.get("vaznost") or _rokovi_domen.normalizuj_vaznost("bitan"),
        "akter": AKTER_ISPRAVKE, "izvor": _rokovi_domen.IZVOR_HUMAN_DIRECT,
        "dokument_id": izvor.get("dokument_id"), "dokument_naziv": izvor.get("dokument_naziv"),
        **_rokovi_domen.oznake(vrsta=_rokovi_domen.VRSTA_ROK, supa=supa),
    }).execute()
    return (nov_r.data or [{}])[0].get("id")
