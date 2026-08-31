# -*- coding: utf-8 -*-
"""
Vindex AI — services/v2_projection.py

A015 (2026-08-30) — PROJEKCIJA V2 KONTRADIKCIJE U `case_actions`.

## Jedno pravilo koje ceo modul postoji da bi sproveo

    Projekcija NE rekonstruiše identitet. Ona ga PRENOSI.

Ulaz je već perzistirana V2 kontradikcija; njen identitet je
`predmet_contradictions.id` i taj id je jedini izvor projekcionog ključa.

## Zašto ključ mora biti izveden iz `contradiction_id`

Legacy ključ (`shared/contradiction_identity.contradiction_dedupe_key`) je heš
para **oznaka lokacija** — `"DOK-01 str.2"` / `"DOK-02 str.1"`. Iz toga slede dva
merena kvara:

  A005  Dve različite sporne tačke nad istim parom dokumenata dobijaju ISTI
        ključ, pa ih `{a["dedupe_key"]: a for a in target}`
        (`services/case_evolution.py:1052`) svodi na jednu akciju — tiho.

  A013  `DOK-01` postoji u SVAKOM predmetu, a `idx_notifications_open_dedupe`
        je `(user_id, dedupe_key)` BEZ `predmet_id`. Dva predmeta istog advokata
        zato kolidiraju; reprodukovano uživo kao `23505`.

`predmet_contradictions.id` je UUID — globalno jedinstven. Time oba kvara
prestaju da budu izraziva, i to **bez ijedne izmene indeksa ili šeme**: ključ
oblika `v2:contradiction:{uuid}` ne može da se poklopi ni sa drugom
kontradikcijom istog predmeta, ni sa bilo čim u drugom predmetu.

## Šta ovaj modul NIKAD ne radi

  - ne izvodi ključ iz `opis`, `issue_label`, `lokacija_1/2`, `dokument_id_1/2`;
  - ne koristi `issue_id` kao identitet kontradikcije (jedna sporna tačka sme
    imati više kontradikcija, po `relation_type`);
  - ne koristi identitet tvrdnje kao identitet kontradikcije;
  - ne generiše nasumičan UUID — `uuid4()` u projekciji bi značio nov identitet
    na svaki refresh, dakle beskonačan churn;
  - ne piše u bazu. Ovo je čista transformacija; upis ostaje na
    `_consequence_refresh_case_actions`.

## Granica prema legacy putanji

Predmet koji još nema tvrdnje (`predmet_dokazi = 0`) ne može imati V2
kontradikciju — A014 tamo ispravno pada zatvoreno. Za takav predmet ovaj modul
vraća praznu listu, a legacy Rule 3 nastavlja da radi nepromenjeno. Identiteti se
NIKAD ne mešaju: legacy akcija nosi legacy ključ, V2 akcija nosi V2 ključ.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable, Optional

logger = logging.getLogger("vindex.v2_projection")

# Prefiks je namerno čitljiv i "grepabilan": u produkcionoj tabeli mora biti
# očigledno koja akcija dolazi iz V2, bez gledanja u `dokaz`.
PREFIKS = "v2:contradiction:"

IZVOR_TIP = "v2_contradiction"

TIP_AKCIJE = "RAZRESITI_KONTRADIKCIJU"

# Ista mapa koju Rule 3 već koristi -- ne uvodi se paralelna skala.
_TEZINA_PRIORITET = {"kriticna": "critical", "vazna": "high", "manja": "medium"}
_PODRAZUMEVANI_PRIORITET = "high"


def projekcioni_kljuc(contradiction_id: Any) -> str:
    """`v2:contradiction:{uuid}` — jedini dozvoljeni ključ za V2 akciju."""
    cid = str(contradiction_id or "").strip()
    if not cid:
        raise ValueError("projekcioni kljuc trazi contradiction_id")
    return f"{PREFIKS}{cid}"


def je_v2_kljuc(kljuc: Any) -> bool:
    return isinstance(kljuc, str) and kljuc.startswith(PREFIKS)


def contradiction_id_iz_kljuca(kljuc: Any) -> Optional[str]:
    return kljuc[len(PREFIKS):] if je_v2_kljuc(kljuc) else None


def u_akciju(kontradikcija: dict) -> dict:
    """Jedna perzistirana V2 kontradikcija -> jedan `case_actions` red.

    Očekuje spojen oblik koji `ucitaj_v2_kontradikcije` vraća."""
    cid = kontradikcija.get("id")
    if not cid:
        # Bez identiteta nema projekcije. Tiho preskakanje bi bio silent loss.
        raise ValueError("V2 kontradikcija bez `id` ne moze biti projektovana")

    label = (kontradikcija.get("issue_label") or "").strip()
    razlog = label or "Kontradikcija u predmetu"
    tezina = kontradikcija.get("tezina")

    return {
        "tip": TIP_AKCIJE,
        "razlog": razlog,
        "dokaz": {
            # Eksplicitna, mašinski čitljiva veza nazad na domen entitet.
            "source_type": IZVOR_TIP,
            "source_id": str(cid),
            "issue_id": str(kontradikcija.get("issue_id") or ""),
            "relation_type": kontradikcija.get("relation_type"),
            "state": kontradikcija.get("state"),
            # Članovi i provenijencija -- prenose se, ne učestvuju u identitetu.
            "claim_ids": sorted(str(x) for x in (kontradikcija.get("claim_ids") or [])),
            "dokument_ids": sorted(str(x) for x in (kontradikcija.get("dokument_ids") or []) if x),
        },
        "prioritet": _TEZINA_PRIORITET.get(tezina, _PODRAZUMEVANI_PRIORITET),
        "rok": None,
        "dedupe_key": projekcioni_kljuc(cid),
        "izvor_dokumenti": sorted(str(x) for x in (kontradikcija.get("dokument_ids") or []) if x),
    }


def u_akcije(kontradikcije: Iterable[dict]) -> list[dict]:
    """Deterministički redosled: po `contradiction_id`.

    Redosled ne sme zavisiti od toga kojim je redom baza vratila redove — inače
    bi dva refresh-a istog stanja dala dve različite liste, a razlika bi izgledala
    kao promena predmeta."""
    return [u_akciju(k) for k in sorted(kontradikcije or [], key=lambda k: str(k.get("id") or ""))]


async def ucitaj_v2_kontradikcije(supa, predmet_id: str) -> list[dict]:
    """OTVORENE V2 kontradikcije predmeta, sa labelom, članovima i dokumentima.

    Čita se opsegom predmeta, nikad globalno: `predmet_issues.predmet_id` je
    granica. Povučeni članovi (`removed_at`) se ne prikazuju — oni su istorija."""
    import asyncio

    if not predmet_id:
        return []

    iss = await asyncio.to_thread(
        lambda: supa.table("predmet_issues").select("id,label,status")
                   .eq("predmet_id", predmet_id).execute()
    )
    issues = {i["id"]: i for i in ((iss.data if iss else None) or [])}
    if not issues:
        return []

    kon = await asyncio.to_thread(
        lambda: supa.table("predmet_contradictions")
                   .select("id,issue_id,relation_type,state,tezina")
                   .in_("issue_id", list(issues.keys()))
                   .eq("state", "OPEN").execute()
    )
    kontradikcije = list((kon.data if kon else None) or [])
    if not kontradikcije:
        return []

    cl = await asyncio.to_thread(
        lambda: supa.table("predmet_contradiction_claims")
                   .select("contradiction_id,dokaz_id,removed_at")
                   .in_("contradiction_id", [k["id"] for k in kontradikcije]).execute()
    )
    clanovi: dict[str, list[str]] = {}
    for c in ((cl.data if cl else None) or []):
        if c.get("removed_at") is None:
            clanovi.setdefault(c["contradiction_id"], []).append(c["dokaz_id"])

    svi_dokazi = sorted({d for v in clanovi.values() for d in v})
    dok_po_dokazu: dict[str, str] = {}
    if svi_dokazi:
        dz = await asyncio.to_thread(
            lambda: supa.table("predmet_dokazi").select("id,dokument_id")
                       .in_("id", svi_dokazi).execute()
        )
        dok_po_dokazu = {d["id"]: d.get("dokument_id") for d in ((dz.data if dz else None) or [])}

    out = []
    for k in kontradikcije:
        claim_ids = clanovi.get(k["id"], [])
        out.append({
            **k,
            "issue_label": (issues.get(k["issue_id"]) or {}).get("label"),
            "claim_ids": claim_ids,
            "dokument_ids": sorted({dok_po_dokazu.get(c) for c in claim_ids if dok_po_dokazu.get(c)}),
        })
    return out


async def v2_akcije_za_predmet(supa, predmet_id: str) -> list[dict]:
    """Ceo put: baza -> akcije. Prazna lista znači „ovaj predmet nema V2"."""
    kontradikcije = await ucitaj_v2_kontradikcije(supa, predmet_id)
    if not kontradikcije:
        return []
    akcije = u_akcije(kontradikcije)
    logger.info("[V2-PROJ] predmet=%s projektovano %d V2 kontradikcija", predmet_id, len(akcije))
    return akcije
