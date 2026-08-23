# -*- coding: utf-8 -*-
"""
Vindex AI — routers/billing_reports.py

Billing izveštaji i export:

GET /billing/report/godisnji?godina=YYYY     — godišnji pregled s mesečnim breakdownom
GET /billing/report/csv?od=&do=              — CSV export stavki za period
GET /billing/report/zastarele               — aging: 0-30/31-60/61-90/90+ dana
GET /billing/report/po-tipu                 — prihodi grupisani po tipu predmeta
GET /billing/report/po-klijentu?od=&do=     — prihodi grupisani po klijentu s trendom
"""
from __future__ import annotations

import asyncio
import csv
import io
import logging
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from shared.deps import _get_supa, get_current_user
from shared.rate import limiter

logger = logging.getLogger("vindex.billing_reports")
router = APIRouter(prefix="/billing/report", tags=["billing"])


def _db(fn):
    return asyncio.to_thread(fn)


# ─── B2 — NEUSPEO PODUPIT NIJE PRAZAN REZULTAT ───────────────────────────────
#
# ŠTA JE BILO — mereno nad produkcionom šemom, ne pretpostavljeno:
#
# Svaki izveštaj u ovom fajlu radio je `asyncio.gather(..., return_exceptions=
# True)` pa `(r.data or []) if not isinstance(r, Exception) else []`. Neuspeh
# podupita je time postajao PRAZNA LISTA, a prazna lista je nizvodno postajala
# finansijska tvrdnja: `ukupno_naplaceno_rsd: 0`, koje frontend ispisuje
# podebljano kao `0 RSD` (`static/vindex.js::billing_renderReport`), odnosno
# „Nema faktura za ovaj period."
#
# I to nije bio teorijski scenario — podupiti su padali UVEK, jer su imenovali
# kolone kojih u šemi nema (sonda produkcije, PostgREST OpenAPI koren):
#
#   fakture         -> `iznos_rsd` NE POSTOJI (iznosi su iznos_bez_pdv /
#                      pdv_iznos / iznos_sa_pdv)
#                   -> `klijent_id` NE POSTOJI. Faktura NEMA vezu ka `klijenti`;
#                      identitet klijenta je denormalizovan snimak
#                      `klijent_naziv` / `klijent_pib` (v. pisca u
#                      routers/billing.py:639-653)
#   billing_entries -> `klijent_id` NE POSTOJI (samo `predmet_id`, `faktura_id`)
#   klijenti        -> kolona je `firma`, ne `naziv_firme`
#
# PostgREST odbija ceo zahtev sa 42703 bez obzira na broj redova, pa je izveštaj
# bio deterministički prazan.
#
# PRAVILO KOJE SE OVDE UVODI — dva različita izvora, dva različita ishoda:
#
#   `_mora`   izvor koji NOSI BROJ koji advokat čita kao činjenicu (iznosi,
#             brojanja rokova/ročišta). Neuspeh = izveštaj se NE proizvodi
#             (HTTP 503). Isti ugovor koji `shared/rokovi.py::zahtevaj` već
#             drži za rokove: „ne znam" se ne sme prikazati kao „nula".
#   `_dopuna` izvor koji nosi SAMO oznaku/grupisanje (naziv, tip predmeta).
#             Neuspeh se IMENUJE u `nepotpuno`, izveštaj ostaje upotrebljiv.
#             Isti obrazac koji `routers/search.py` već koristi.


def _mora(r, ime: str) -> list:
    """Podupit koji nosi broj. Neuspeh je 503 — nikad tiha nula."""
    if isinstance(r, Exception):
        logger.error("[BILLING-REPORT] izvor '%s' nije procitan: %s", ime, r)
        # Namerni korisnicki ugovor (B2 gate): korisnik MORA da razlikuje pao
        # izvor od iznosa NULA. Poruka je rucno pisana i ne sadrzi izuzetak.
        from shared.http_errors import NamerniHTTPException as _Namerni
        raise _Namerni(
            status_code=503,
            detail=(f"Izveštaj nije izračunat — izvor „{ime}” trenutno nije "
                    f"dostupan. Prikazani iznos bi bio netačan, pa se ne "
                    f"prikazuje."),
        )
    return getattr(r, "data", None) or []


def _dopuna(r, ime: str, nepotpuno: list) -> list:
    """Podupit koji nosi samo oznaku. Neuspeh se imenuje, ne prećutkuje."""
    if isinstance(r, Exception):
        logger.warning("[BILLING-REPORT] dopunski izvor '%s' nije procitan: %s", ime, r)
        nepotpuno.append(ime)
        return []
    return getattr(r, "data", None) or []


def _naziv_klijenta(f: dict) -> str:
    """Identitet klijenta sa fakture — njeno SOPSTVENO polje, ne izvedena veza.

    `fakture` nema `klijent_id`; pisac (`routers/billing.py:643`) upisuje
    `klijent_naziv` kao snimak u trenutku izdavanja. Grupisanje po tom polju je
    jedino grupisanje po klijentu koje se iz šeme može dokazati. Put
    `fakture -> predmet_id -> predmet_klijenti -> klijenti` NIJE korišćen: jedan
    predmet ima više klijenata sa različitim ulogama, pa bi izbor „onog pravog"
    bio izmišljeno pravilo, a `predmet_klijenti` u produkciji ima 0 redova.
    """
    return (f.get("klijent_naziv") or "").strip()


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _month_range(godina: int) -> list[str]:
    return [f"{godina}-{m:02d}" for m in range(1, 13)]


def _ym(iso_date: str) -> str:
    return iso_date[:7] if iso_date else ""


# ─── GET /billing/report/godisnji ────────────────────────────────────────────

@router.get("/godisnji")
@limiter.limit("20/minute")
async def billing_godisnji(
    request: Request,
    godina:  Optional[int] = None,
    user:    dict          = Depends(get_current_user),
):
    uid  = user["user_id"]
    supa = _get_supa()

    if godina is None:
        godina = date.today().year
    if godina < 2000 or godina > 2100:
        raise HTTPException(status_code=422, detail="Nevalidna godina.")

    od = f"{godina}-01-01"
    do = f"{godina}-12-31"

    # `klijenti` upit je uklonjen, ne preimenovan: postojao je isključivo da
    # preslika `fakture.klijent_id` -> ime, a te kolone nema. Upit čiji se
    # rezultat nema na šta spojiti nije upit koji treba popraviti.
    entries_r, fakture_r, predmeti_r = await asyncio.gather(
        _db(lambda: supa.table("billing_entries")
            .select("iznos_rsd, datum, obracunato, predmet_id")
            .eq("user_id", uid)
            .gte("datum", od).lte("datum", do)
            .execute()),
        _db(lambda: supa.table("fakture")
            .select("iznos_sa_pdv, status, datum_fakture, klijent_naziv")
            .eq("user_id", uid)
            .gte("datum_fakture", od).lte("datum_fakture", do)
            .execute()),
        _db(lambda: supa.table("predmeti")
            .select("id, naziv, tip")
            .eq("user_id", uid)
            .execute()),
        return_exceptions=True,
    )

    nepotpuno: list[str] = []
    entries  = _mora(entries_r, "stavke naplate")
    fakture  = _mora(fakture_r, "fakture")
    predmeti = _dopuna(predmeti_r, "tipovi predmeta", nepotpuno)

    pred_map = {p["id"]: p for p in predmeti}

    # Mesečni breakdown
    meseci: dict[str, dict] = {m: {"mesec": m, "uneseno": 0.0, "naplaceno": 0.0, "stavki": 0} for m in _month_range(godina)}
    for e in entries:
        ym = _ym(e.get("datum", ""))
        if ym in meseci:
            meseci[ym]["uneseno"] += float(e.get("iznos_rsd") or 0)
            meseci[ym]["stavki"]  += 1
    for f in fakture:
        ym = _ym(f.get("datum_fakture", ""))
        if ym in meseci and f.get("status") == "placena":
            meseci[ym]["naplaceno"] += float(f.get("iznos_sa_pdv") or 0)

    # Ukupni KPIs
    ukupno_uneseno  = sum(float(e.get("iznos_rsd") or 0) for e in entries)
    ukupno_naplaceno = sum(float(f.get("iznos_sa_pdv") or 0) for f in fakture if f.get("status") == "placena")
    ukupno_fakturisano = sum(float(f.get("iznos_sa_pdv") or 0) for f in fakture)
    stopa = round(ukupno_naplaceno / ukupno_fakturisano * 100, 1) if ukupno_fakturisano else 0.0

    # Top klijenti — po nazivu sa same fakture (v. `_naziv_klijenta`).
    kl_iznosi: dict[str, float] = {}
    for f in fakture:
        naziv = _naziv_klijenta(f)
        if not naziv:
            continue
        kl_iznosi[naziv] = kl_iznosi.get(naziv, 0.0) + float(f.get("iznos_sa_pdv") or 0)
    top_klijenti = sorted(
        [{"naziv": naziv, "iznos": round(izn, 2)} for naziv, izn in kl_iznosi.items()],
        key=lambda x: x["iznos"], reverse=True
    )[:5]

    # Top tipovi predmeta
    tip_iznosi: dict[str, float] = {}
    tip_brojevi: dict[str, set] = {}
    for e in entries:
        pid  = e.get("predmet_id", "")
        pred = pred_map.get(pid, {})
        tip  = pred.get("tip") or "ostalo"
        tip_iznosi[tip]  = tip_iznosi.get(tip, 0.0) + float(e.get("iznos_rsd") or 0)
        tip_brojevi.setdefault(tip, set()).add(pid)
    top_tipovi = sorted(
        [{"tip": t, "iznos": round(izn, 2), "predmeta": len(tip_brojevi.get(t, set()))}
         for t, izn in tip_iznosi.items()],
        key=lambda x: x["iznos"], reverse=True
    )[:5]

    return {
        "godina":              godina,
        "ukupno_uneseno_rsd":  round(ukupno_uneseno, 2),
        "ukupno_fakturisano":  round(ukupno_fakturisano, 2),
        "ukupno_naplaceno_rsd": round(ukupno_naplaceno, 2),
        "stopa_naplate_pct":   stopa,
        "po_mesecima":         list(meseci.values()),
        "top_klijenti":        top_klijenti,
        "top_tipovi_predmeta": top_tipovi,
        # Prazno = sve pročitano. Neprazno = navedene grupe su nepouzdane i
        # frontend to MORA prikazati (v. billing_renderReport).
        "nepotpuno":           nepotpuno,
    }


# ─── GET /billing/report/csv ─────────────────────────────────────────────────

@router.get("/csv")
@limiter.limit("10/minute")
async def billing_csv_export(
    request: Request,
    od:      Optional[str] = None,
    do:      Optional[str] = None,
    user:    dict          = Depends(get_current_user),
):
    uid  = user["user_id"]
    supa = _get_supa()

    today    = date.today()
    od_date  = od or date(today.year, 1, 1).isoformat()
    do_date  = do or today.isoformat()

    try:
        date.fromisoformat(od_date)
        date.fromisoformat(do_date)
    except ValueError:
        raise HTTPException(status_code=422, detail="Nevalidan format datuma (YYYY-MM-DD).")

    # `billing_entries` NEMA `klijent_id` (šema: predmet_id, faktura_id) — kolona
    # je uklonjena iz `select`, a sa njom i `klijenti` upit koji je služio samo
    # njoj. Kolona „Klijent" u CSV-u zato ostaje prazna: iz ovog izvora se
    # klijent ne može izvesti bez izmišljanja pravila (v. `_naziv_klijenta`).
    #
    # Za IZVOZ nema „delimično": dokument koji advokat šalje dalje mora biti
    # kompletan ili se ne sme proizvesti. Zato je i `predmeti` ovde `_mora`, a
    # ne `_dopuna` — tiho prazna kolona „Predmet" u eksportu je gora od greške.
    entries_r, predmeti_r = await asyncio.gather(
        _db(lambda: supa.table("billing_entries")
            .select("datum, predmet_id, tarifa_sifra, tarifa_naziv, opis, sati, iznos_rsd, obracunato, faktura_id")
            .eq("user_id", uid)
            .gte("datum", od_date).lte("datum", do_date)
            .order("datum")
            .execute()),
        _db(lambda: supa.table("predmeti").select("id, naziv").eq("user_id", uid).execute()),
        return_exceptions=True,
    )

    entries  = _mora(entries_r, "stavke naplate")
    predmeti = _mora(predmeti_r, "predmeti")

    pred_map = {p["id"]: p.get("naziv", "") for p in predmeti}

    buf = io.StringIO()
    w   = csv.writer(buf, delimiter=";", quoting=csv.QUOTE_MINIMAL)
    w.writerow(["Datum", "Predmet", "Klijent", "Šifra tarife", "Naziv tarife", "Opis", "Sati", "Iznos RSD", "Obračunato", "Faktura ID"])

    for e in entries:
        w.writerow([
            e.get("datum", ""),
            pred_map.get(e.get("predmet_id", ""), ""),
            "",
            e.get("tarifa_sifra", ""),
            e.get("tarifa_naziv", ""),
            e.get("opis", ""),
            e.get("sati", ""),
            e.get("iznos_rsd", ""),
            "da" if e.get("obracunato") else "ne",
            e.get("faktura_id", ""),
        ])

    filename = f"billing_{od_date}_{do_date}.csv"
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue().encode("utf-8-sig")]),
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─── GET /billing/report/zastarele ───────────────────────────────────────────

@router.get("/zastarele")
@limiter.limit("20/minute")
async def billing_zastarele(
    request: Request,
    user:    dict = Depends(get_current_user),
):
    """Nenaplaćene stavke grupisane po starosti (aging report)."""
    uid   = user["user_id"]
    supa  = _get_supa()
    today = date.today()

    # `billing_entries.klijent_id` NE POSTOJI, pa je i ovde `klijenti` upit bio
    # bez ključa za spajanje. „Top dužnici" se iz ovog izvora ne mogu izvesti —
    # to se sada IZRIČITO objavljuje (`top_duznici_dostupno: False`) umesto da
    # prazna lista izgleda kao „nema dužnika".
    entries_r = (await asyncio.gather(
        _db(lambda: supa.table("billing_entries")
            .select("id, datum, iznos_rsd, opis, predmet_id")
            .eq("user_id", uid)
            .eq("obracunato", False)
            .order("datum")
            .execute()),
        return_exceptions=True,
    ))[0]

    entries = _mora(entries_r, "nenaplaćene stavke")

    buckets = {
        "do_30_dana":  {"iznos": 0.0, "stavki": 0, "stavke": []},
        "31_60_dana":  {"iznos": 0.0, "stavki": 0, "stavke": []},
        "61_90_dana":  {"iznos": 0.0, "stavki": 0, "stavke": []},
        "starije_90":  {"iznos": 0.0, "stavki": 0, "stavke": []},
    }
    for e in entries:
        try:
            d    = date.fromisoformat(e.get("datum", today.isoformat()))
            dana = (today - d).days
        except ValueError:
            dana = 0

        if   dana <= 30:  bucket = "do_30_dana"
        elif dana <= 60:  bucket = "31_60_dana"
        elif dana <= 90:  bucket = "61_90_dana"
        else:             bucket = "starije_90"

        iznos = float(e.get("iznos_rsd") or 0)
        buckets[bucket]["iznos"]  += iznos
        buckets[bucket]["stavki"] += 1
        buckets[bucket]["stavke"].append({
            "id":          e["id"],
            "datum":       e.get("datum"),
            "opis":        e.get("opis"),
            "iznos_rsd":   iznos,
            "predmet_id":  e.get("predmet_id"),
            "dana_staro":  dana,
        })

    for b in buckets.values():
        b["iznos"] = round(b["iznos"], 2)

    ukupno = round(sum(b["iznos"] for b in buckets.values()), 2)
    return {
        "ukupno_nenaplaceno_rsd": ukupno,
        "aging":                  buckets,
        # Prazna lista uz `dostupno: False` znači „ne može se izračunati", ne
        # „nema dužnika". `billing_entries` nema vezu ka klijentu.
        "top_duznici":            [],
        "top_duznici_dostupno":   False,
    }


# ─── GET /billing/report/po-tipu ─────────────────────────────────────────────

@router.get("/po-tipu")
@limiter.limit("20/minute")
async def billing_po_tipu(
    request: Request,
    od:      Optional[str] = None,
    do:      Optional[str] = None,
    user:    dict          = Depends(get_current_user),
):
    """Prihodi grupisani po tipu predmeta — koja oblast prava donosi najviše prihoda."""
    uid  = user["user_id"]
    supa = _get_supa()

    today   = date.today()
    od_date = od or date(today.year, 1, 1).isoformat()
    do_date = do or today.isoformat()

    entries_r, predmeti_r = await asyncio.gather(
        _db(lambda: supa.table("billing_entries")
            .select("iznos_rsd, predmet_id, sati")
            .eq("user_id", uid)
            .gte("datum", od_date).lte("datum", do_date)
            .execute()),
        _db(lambda: supa.table("predmeti")
            .select("id, tip, naziv")
            .eq("user_id", uid)
            .execute()),
        return_exceptions=True,
    )

    nepotpuno: list[str] = []
    entries  = _mora(entries_r, "stavke naplate")
    predmeti = _dopuna(predmeti_r, "tipovi predmeta", nepotpuno)
    pred_map = {p["id"]: p for p in predmeti}

    tipovi: dict[str, dict] = {}
    for e in entries:
        pred = pred_map.get(e.get("predmet_id", ""), {})
        tip  = pred.get("tip") or "ostalo"
        if tip not in tipovi:
            tipovi[tip] = {"tip": tip, "iznos_rsd": 0.0, "stavki": 0, "sati": 0.0, "predmeta": set()}
        tipovi[tip]["iznos_rsd"] += float(e.get("iznos_rsd") or 0)
        tipovi[tip]["stavki"]    += 1
        tipovi[tip]["sati"]      += float(e.get("sati") or 0)
        if e.get("predmet_id"):
            tipovi[tip]["predmeta"].add(e["predmet_id"])

    ukupno_iznos = sum(t["iznos_rsd"] for t in tipovi.values())
    result = sorted([
        {
            "tip":          t["tip"],
            "iznos_rsd":    round(t["iznos_rsd"], 2),
            "stavki":       t["stavki"],
            "sati":         round(t["sati"], 2),
            "predmeta":     len(t["predmeta"]),
            "ucesce_pct":   round(t["iznos_rsd"] / ukupno_iznos * 100, 1) if ukupno_iznos else 0.0,
        }
        for t in tipovi.values()
    ], key=lambda x: x["iznos_rsd"], reverse=True)

    return {
        "od":           od_date,
        "do":           do_date,
        "ukupno_rsd":   round(ukupno_iznos, 2),
        "po_tipu":      result,
        # Ako `predmeti` nije pročitan, SVE stavke padnu u „ostalo" — ukupan
        # iznos je tačan, ali je raspodela po tipu neupotrebljiva. To se imenuje.
        "nepotpuno":    nepotpuno,
    }


# ─── GET /billing/report/po-klijentu ─────────────────────────────────────────

@router.get("/po-klijentu")
@limiter.limit("20/minute")
async def billing_po_klijentu(
    request: Request,
    od:      Optional[str] = None,
    do:      Optional[str] = None,
    user:    dict          = Depends(get_current_user),
):
    """
    Prihodi grupisani po klijentu za zadati period.

    Vraća po svakom klijentu:
      - ukupno_rsd: zbir svih fakturisanih iznosa (iznos_rsd)
      - naplaceno_rsd: iznos plaćenih faktura
      - neplaceno_rsd: iznos neplaćenih faktura
      - broj_faktura: ukupan broj faktura
      - trend: mesečni breakdown za period (za sparkline grafikon)
    Sortira od najvećeg ukupnog iznosa.
    """
    uid  = user["user_id"]
    supa = _get_supa()

    today   = date.today()
    od_date = od or date(today.year, 1, 1).isoformat()
    do_date = do or today.isoformat()

    try:
        date.fromisoformat(od_date)
        date.fromisoformat(do_date)
    except ValueError:
        raise HTTPException(status_code=422, detail="Nevalidan format datuma (YYYY-MM-DD).")

    # `fakture` nema ni `klijent_id` ni `iznos_rsd`. Grupisanje ide po
    # `klijent_naziv` (sopstveno polje fakture), a svi iznosi su `iznos_sa_pdv`
    # — jedan i isti osnov kroz ceo izveštaj, isti koji `godisnji` i `mesecni`
    # već koriste. Mešanje neto i bruto osnova bi dalo brojeve koji se ne
    # sabiraju.
    fakture_r = (await asyncio.gather(
        _db(lambda: supa.table("fakture")
            .select("id, klijent_naziv, iznos_sa_pdv, status, datum_fakture")
            .eq("user_id", uid)
            .gte("datum_fakture", od_date)
            .lte("datum_fakture", do_date)
            .order("datum_fakture")
            .execute()),
        return_exceptions=True,
    ))[0]

    fakture = _mora(fakture_r, "fakture")

    # Agregacija po klijentu
    agg: dict[str, dict] = {}
    for f in fakture:
        naziv = _naziv_klijenta(f)
        kid   = naziv or "_bez_klijenta"
        iznos = float(f.get("iznos_sa_pdv") or 0)
        iznos_pdv = iznos
        placena   = f.get("status") == "placena"
        ym        = (f.get("datum_fakture") or "")[:7]

        if kid not in agg:
            agg[kid] = {
                # Ključ je NAZIV sa fakture, ne id klijenta — polje se zato više
                # ne zove `klijent_id`. Vraćati ime pod tim imenom značilo bi
                # tvrditi vezu ka `klijenti` koja u šemi ne postoji.
                "kljuc":         kid,
                "naziv":         naziv or "—",
                "ukupno_rsd":    0.0,
                "naplaceno_rsd": 0.0,
                "neplaceno_rsd": 0.0,
                "broj_faktura":  0,
                "trend":         {},
            }
        e = agg[kid]
        e["ukupno_rsd"]    += iznos
        e["broj_faktura"]  += 1
        if placena:
            e["naplaceno_rsd"] += iznos_pdv
        else:
            e["neplaceno_rsd"] += iznos
        if ym:
            e["trend"][ym] = e["trend"].get(ym, 0.0) + iznos

    ukupno_rsd = sum(e["ukupno_rsd"] for e in agg.values())

    result = sorted([
        {
            "naziv":         e["naziv"],
            "ukupno_rsd":    round(e["ukupno_rsd"], 2),
            "naplaceno_rsd": round(e["naplaceno_rsd"], 2),
            "neplaceno_rsd": round(e["neplaceno_rsd"], 2),
            "broj_faktura":  e["broj_faktura"],
            "ucesce_pct":    round(e["ukupno_rsd"] / ukupno_rsd * 100, 1) if ukupno_rsd else 0.0,
            "trend":         [
                {"mesec": ym, "iznos_rsd": round(iznos, 2)}
                for ym, iznos in sorted(e["trend"].items())
            ],
        }
        for e in agg.values()
        if e["kljuc"] != "_bez_klijenta"
    ], key=lambda x: x["ukupno_rsd"], reverse=True)

    return {
        "od":          od_date,
        "do":          do_date,
        "ukupno_rsd":  round(ukupno_rsd, 2),
        "po_klijentu": result,
        "bez_klijenta": round(
            agg.get("_bez_klijenta", {}).get("ukupno_rsd", 0.0), 2
        ),
    }


# ─── GET /billing/report/mesecni ─────────────────────────────────────────────

@router.get("/mesecni")
@limiter.limit("30/minute")
async def billing_mesecni(
    request: Request,
    mesec:   Optional[str] = None,   # YYYY-MM, default = tekući mesec
    user:    dict          = Depends(get_current_user),
):
    """
    Mesečni operativni izveštaj — jedinstven prikaz za advokata:
    aktivni predmeti, ročišta, fakturisano, naplaćeno, prekoračeni rokovi.
    Koristi se za dashboard i mesečni pregled na jednom ekranu.
    """
    uid  = user["user_id"]
    supa = _get_supa()
    today = date.today()

    if mesec:
        try:
            godina, mese = int(mesec[:4]), int(mesec[5:7])
        except Exception:
            raise HTTPException(status_code=422, detail="Format meseca: YYYY-MM")
    else:
        godina, mese = today.year, today.month

    od_iso = f"{godina}-{mese:02d}-01"
    if mese == 12:
        do_iso = f"{godina + 1}-01-01"
    else:
        do_iso = f"{godina}-{mese + 1:02d}-01"

    do_inc_iso = (date.fromisoformat(do_iso) - timedelta(days=1)).isoformat()
    today_iso  = today.isoformat()

    (pred_r, rocista_r, billing_r, fakture_r, rokovi_r, hronologija_r) = await asyncio.gather(
        asyncio.to_thread(lambda: supa.table("predmeti")
            .select("id,naziv,tip,status")
            .eq("user_id", uid)
            .eq("status", "aktivan")
            .execute()),
        asyncio.to_thread(lambda: supa.table("rocista")
            .select("id,datum,sud,vreme,predmet_id,status")
            .eq("user_id", uid)
            .gte("datum", od_iso)
            .lte("datum", do_inc_iso)
            .order("datum")
            .execute()),
        asyncio.to_thread(lambda: supa.table("billing_entries")
            .select("iznos_rsd,obracunato,datum")
            .eq("user_id", uid)
            .gte("datum", od_iso)
            .lte("datum", do_inc_iso)
            .execute()),
        asyncio.to_thread(lambda: supa.table("fakture")
            .select("iznos_sa_pdv,status,datum_fakture")
            .eq("user_id", uid)
            .gte("datum_fakture", od_iso)
            .lte("datum_fakture", do_inc_iso)
            .execute()),
        asyncio.to_thread(lambda: supa.table("predmet_hronologija")
            .select("id,datum_iso,dogadjaj,vaznost,predmet_id")
            .eq("user_id", uid)
            .eq("vaznost", "kritičan")
            .lt("datum_iso", today_iso)
            .execute()),
        asyncio.to_thread(lambda: supa.table("predmet_hronologija")
            .select("id,datum_iso,dogadjaj,predmet_id")
            .eq("user_id", uid)
            .gte("datum_iso", today_iso)
            .lte("datum_iso", (today + timedelta(days=14)).isoformat())
            .order("datum_iso")
            .execute()),
        return_exceptions=True,
    )

    # Svih šest izvora ovde postaje BROJ na ekranu (aktivnih predmeta, ročišta,
    # fakturisano, naplaćeno, prekoračeni rokovi). Nijedan od tih brojeva ne sme
    # biti nula zato što upit nije uspeo — „0 prekoračenih rokova" iz pale
    # pretrage je isti kvar kao „0 RSD". Zato su svi `_mora`.
    # Frontend (`mesecniIzvestajUcitaj`) na `!r.ok` ispisuje grešku, pa 503 daje
    # poštenu poruku umesto lažnog izveštaja.
    predmeti    = _mora(pred_r,        "predmeti")
    rocista     = _mora(rocista_r,     "ročišta")
    entries     = _mora(billing_r,     "stavke naplate")
    fakture     = _mora(fakture_r,     "fakture")
    prekoraceni = _mora(rokovi_r,      "prekoračeni rokovi")
    sledeci14   = _mora(hronologija_r, "nadolazeći rokovi")

    # B2-MESECNI-001 — TRI POJMA KOJA SE NE SMEJU MEŠATI.
    #
    # Ovde je stajalo:
    #     fakturisano = sum(float(e.get("iznos_rsd") or 0) for e in entries)
    # `entries` su `billing_entries`, dakle NEOBRAČUNAT rad. Mereno uživo na
    # `15302e0`: tenant sa 3 stavke rada (1.000 + 2.500 + 500) i NIJEDNOM
    # fakturom dobijao je `fakturisano_rsd = 4000` i time `neplaceno_rsd = 4000`
    # — advokatu je prikazan dug koji klijentu nikad nije ispostavljen.
    #
    # `fakture` se u ovoj funkciji VEĆ dohvata, skopirana po `user_id` i po
    # `datum_fakture` unutar meseca, kroz `_mora` (pad izvora = 503, ne nula).
    # Ista, ispravna semantika postoji u godišnjem izveštaju iznad.
    #
    #   rad        `billing_entries.iznos_rsd`      uneseno, još nefakturisano
    #   fakturisan `fakture.iznos_sa_pdv`           izdato klijentu
    #   naplaćen   `fakture` sa `status='placena'`  stvarno naplaćeno
    fakturisano = sum(float(f.get("iznos_sa_pdv") or 0) for f in fakture)
    naplaceno   = sum(
        float(f.get("iznos_sa_pdv") or 0)
        for f in fakture if f.get("status") == "placena"
    )
    # Rad meseca ne sme da nestane sa ekrana — samo prestaje da se zove
    # „fakturisano". Isto ime nosi i godišnji izveštaj (`ukupno_uneseno_rsd`).
    uneseno = sum(float(e.get("iznos_rsd") or 0) for e in entries)

    pred_by_tip: dict[str, int] = {}
    for p in predmeti:
        t = p.get("tip", "opsti")
        pred_by_tip[t] = pred_by_tip.get(t, 0) + 1

    return {
        "mesec":              f"{godina}-{mese:02d}",
        "mesec_prikaz":       f"{mese:02d}/{godina}",
        "aktivnih_predmeta":  len(predmeti),
        "predmeti_po_tipu":   pred_by_tip,
        "rocista_mesec":      len(rocista),
        "rocista":            rocista[:20],
        "uneseno_rsd":        round(uneseno, 2),      # rad meseca, još nefakturisan
        "fakturisano_rsd":    round(fakturisano, 2),  # iz `fakture`, nikad iz rada
        "naplaceno_rsd":      round(naplaceno, 2),
        "neplaceno_rsd":      round(fakturisano - naplaceno, 2),
        "prekoraceni_rokovi": len(prekoraceni),
        "sledecih_14_dana":   sledeci14[:10],
        "generisano":         today_iso,
    }
