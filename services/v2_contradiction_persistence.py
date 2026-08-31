# -*- coding: utf-8 -*-
"""
Vindex AI — services/v2_contradiction_persistence.py

A013 (2026-08-30) — V2 PERSISTENCE ADAPTER.

JEDINI most između već dokazanog domenskog sloja (`shared/issue_v2.py`) i već
dokazane atomske funkcije u bazi (`v2_persist_contradiction`, migracije 119/120/121).

## Granica odgovornosti — namerno uska

    PYTHON DOMEN   odlučuje ŠTA je sporna tačka, koje tvrdnje učestvuju, koji je
                   tip relacije i postoji li DETERMINISTIČKI dokaz kontinuiteta.
                   Vlasnik: `shared/issue_v2.py`. Ovaj modul ga NE dopunjuje.

    OVAJ ADAPTER   samo prevodi: učita poznate tvrdnje i postojeće sporne tačke,
                   pozove domen, i za svaki ishod pozove RPC. Ne donosi nijednu
                   odluku o identitetu.

    BAZA (RPC)     odlučuje atomičnost, vlasništvo, bezbednost od trke,
                   idempotenciju i ishod trke. Vlasnik: migracija 121.

## Šta ovaj modul NIKAD ne radi

  - ne pravi `dedupe_key` niti ga koristi za odlučivanje identiteta;
  - ne izvodi identitet iz para dokumenata, labele, `opis`-a ni LLM teksta;
  - ne koristi `uuid4()` kao identitet;
  - ne koristi fuzzy poređenje ni prag sličnosti;
  - ne guta izuzetke i nema fallback na legacy persistence;
  - ne upisuje ništa mimo RPC-a (baza sama NE štiti minimum članova ni
    vlasništvo — izmereno u A012, zato je RPC jedini dozvoljeni pisac).

## Poznati gap koji ovaj modul NE zaobilazi

`ODLUKA_PREGLED` (`REVIEW_REQUIRED`) se NE perzistira. `v2_persist_contradiction`
uvek upisuje `state='OPEN'`, a A013 §1 zabranjuje izmenu te funkcije. Upisati
tačku koja traži ljudski pregled kao „OPEN" značilo bi tvrditi nešto što domen
nije zaključio. Zato se takav ishod vraća pozivaocu neperzistiran, sa
kandidatima — vidi A013 izveštaj, GAP-2.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Iterable, Optional

from shared.deps import _get_supa
from shared.issue_v2 import (
    ODLUKA_DUPLIKAT,
    ODLUKA_NASTAVAK,
    ODLUKA_NEISPRAVNO,
    ODLUKA_NOVA,
    ODLUKA_PREGLED,
    STATUSI_OTVORENI,
    otisak_pocetnog_skupa,
    razresi_paket,
)

logger = logging.getLogger("vindex.v2_contradiction")

_RPC = "v2_persist_contradiction"


class V2PersistenceError(RuntimeError):
    """Greška RPC-a se PROPAGIRA, ne prevodi u tihi neuspeh.

    Nosi indeks predloga i razrešenu odluku da bi pozivalac znao koji tačno
    predlog nije upisan — ali NE nastavlja obradu preostalih predloga umesto
    pozivaoca. `__cause__` ostaje originalni izuzetak baze."""

    def __init__(self, indeks: int, odluka: str, poruka: str):
        super().__init__(f"predlog #{indeks} ({odluka}): {poruka}")
        self.indeks = indeks
        self.odluka = odluka


# ═══════════════════════════════════════════════════════════════════════════
# 1. ČITANJE STANJA — ulaz za domen, bez ijedne odluke
# ═══════════════════════════════════════════════════════════════════════════

def _ucitaj_poznate_dokaze(supa, predmet_id: str) -> dict[str, dict]:
    """Sve tvrdnje predmeta, ključ = `predmet_dokazi.id`.

    Uključuje i soft-obrisane: `validiraj_claim_ref` mora da vidi `deleted_at`
    da bi ih odbio kao članove. Filtriranje ovde značilo bi da domen ne može da
    razlikuje „ne postoji" od „obrisana", a to su dva različita razloga odbijanja."""
    res = supa.table("predmet_dokazi") \
              .select("id,predmet_id,identitet,deleted_at") \
              .eq("predmet_id", predmet_id).execute()
    return {r["id"]: r for r in (res.data or [])}


def _ucitaj_postojece_teme(supa, predmet_id: str) -> list[dict]:
    """Otvorene sporne tačke predmeta sa svojim AKTIVNIM članstvom.

    `claim_set` sporne tačke je unija aktivnih članova svih njenih kontradikcija:
    sporna tačka je kontinuitetni entitet (A007), a kontradikcija je njen presek
    po tipu relacije. Povučeni članovi (`removed_at`) se ne računaju — oni su
    istorija, ne trenutno članstvo."""
    iss = supa.table("predmet_issues").select("id,status") \
              .eq("predmet_id", predmet_id).execute().data or []
    otvorene = [i for i in iss if i.get("status") in STATUSI_OTVORENI]
    if not otvorene:
        return []

    ids = [i["id"] for i in otvorene]
    kon = supa.table("predmet_contradictions").select("id,issue_id") \
              .in_("issue_id", ids).execute().data or []
    if not kon:
        return [{"issue_id": i["id"], "status": i["status"], "claim_set": frozenset()}
                for i in otvorene]

    kon_po_issue: dict[str, list[str]] = {}
    for k in kon:
        kon_po_issue.setdefault(k["issue_id"], []).append(k["id"])

    cl = supa.table("predmet_contradiction_claims").select("contradiction_id,dokaz_id,removed_at") \
             .in_("contradiction_id", [k["id"] for k in kon]).execute().data or []
    clan_po_kontr: dict[str, set] = {}
    for c in cl:
        if c.get("removed_at") is None:
            clan_po_kontr.setdefault(c["contradiction_id"], set()).add(c["dokaz_id"])

    out = []
    for i in otvorene:
        skup: set = set()
        for kid in kon_po_issue.get(i["id"], []):
            skup |= clan_po_kontr.get(kid, set())
        out.append({"issue_id": i["id"], "status": i["status"], "claim_set": frozenset(skup)})
    return out


# ═══════════════════════════════════════════════════════════════════════════
# 2. UPIS — jedan RPC poziv po razrešenom predlogu
# ═══════════════════════════════════════════════════════════════════════════

def _identiteti_za(claim_ids: list[str], poznati: dict[str, dict]) -> list[Optional[str]]:
    """`predmet_dokazi.identitet` uparen sa `claim_ids`, po poziciji.

    `None` je ispravna vrednost — u produkciji nijedan red trenutno nema
    `identitet` (izmereno A013). Ovde se ništa ne izmišlja i ništa ne izvodi
    iz teksta."""
    return [(poznati.get(cid) or {}).get("identitet") for cid in claim_ids]


def _upisi(supa, *, predmet_id: str, user_id: str, issue_id: Optional[str],
           label: Optional[str], relation_type: str, tezina: Optional[str],
           fingerprint: str, claim_ids: list[str],
           claim_identiteti: list[Optional[str]]) -> dict:
    res = supa.rpc(_RPC, {
        "p_predmet_id": predmet_id,
        "p_user_id": user_id,
        "p_issue_id": issue_id,
        "p_label": label,
        "p_relation_type": relation_type,
        "p_tezina": tezina,
        "p_fingerprint": fingerprint,
        "p_dokaz_ids": claim_ids,
        "p_claim_identiteti": claim_identiteti,
    }).execute()
    red = (res.data or [None])[0]
    if not isinstance(red, dict) or not red.get("out_issue_id"):
        # Prazan odgovor nije uspeh. Bez ovoga bi pad na strani baze koji ne
        # podigne izuzetak prošao kao upisana sporna tačka.
        raise RuntimeError(f"{_RPC} nije vratio issue_id (odgovor: {res.data!r})")
    return red


# ═══════════════════════════════════════════════════════════════════════════
# 3. JAVNI ULAZ
# ═══════════════════════════════════════════════════════════════════════════

async def persist_paket(
    *, predmet_id: str, user_id: str, predlozi: Any,
    tezina_po_indeksu: Optional[dict[int, str]] = None,
) -> list[dict]:
    """Upisuje CEO proizvođačev paket kroz V2, čuvajući mnogostrukost.

    `predlozi` je lista objekata oblika koji `shared/issue_v2.py` već propisuje:
    `{"claim_refs": [predmet_dokazi.id, …], "relation_type": …, "issue_label": …}`.

    Vraća listu ishoda — JEDAN po predlogu, istim redosledom i sa `indeks`-om:
    ništa se ne sažima, ni po labeli, ni po dokumentima, ni po ključu.

    Podiže `V2PersistenceError` na prvi neuspeh upisa. Namerno NE nastavlja sa
    ostatkom paketa: delimično upisan paket bez signala pozivaocu je upravo tihi
    gubitak koji ovaj sprint zatvara."""
    if not predmet_id or not user_id:
        raise ValueError("persist_paket: predmet_id i user_id su obavezni")

    supa = _get_supa()
    poznati = await asyncio.to_thread(_ucitaj_poznate_dokaze, supa, predmet_id)
    postojece = await asyncio.to_thread(_ucitaj_postojece_teme, supa, predmet_id)

    razreseni = razresi_paket(predlozi, predmet_id, poznati, postojece)

    # Tema nastala UNUTAR ovog istog paketa još nema `predmet_issues.id` — domen
    # je čist i ne zna za bazu, pa je označava rezervisanim imenom `__nova__<i>`
    # (`shared/issue_v2.py::razresi_paket`). Taj token NIJE UUID i ne sme stići do
    # baze. Ovde se prevodi u stvarni id koji je RPC vratio za predlog #i.
    #
    # Bez ovog prevoda paket u kojem drugi predlog nastavlja prvi (`{C1,C2}` pa
    # `{C1,C2,C3}`) poslao bi `p_issue_id="__nova__0"` i pao bi na `22P02`.
    stvarni_id: dict[str, str] = {}

    def _prevedi(oznaka: Optional[str]) -> Optional[str]:
        if oznaka is None:
            return None
        return stvarni_id.get(oznaka, oznaka)

    ishodi: list[dict] = []
    for r in razreseni:
        i = r["indeks"]
        odluka = r["odluka"]
        osnovno = {
            "indeks": i, "odluka": odluka, "label": r["label"],
            "relation_type": r["relation_type"],
            "claim_ids": sorted(r["claim_set"]),
            "kandidati": [_prevedi(k) for k in r["kandidati"]],
            "razlog": r["razlog"], "odbacene_reference": r["odbacene_reference"],
            "issue_id": None, "contradiction_id": None, "created_issue": False,
            "persisted": False,
        }

        if odluka in (ODLUKA_NEISPRAVNO, ODLUKA_DUPLIKAT):
            # Ne upisuje se, ali se ni ne gubi: ishod je vidljiv pozivaocu.
            ishodi.append(osnovno)
            continue

        if odluka == ODLUKA_PREGLED:
            # GAP-2: RPC upisuje isključivo `state='OPEN'`, a A013 §1 zabranjuje
            # njegovu izmenu. Upisati ovo kao OPEN značilo bi tvrditi kontinuitet
            # koji domen NIJE utvrdio. Vraća se neperzistirano, sa kandidatima.
            logger.info("[V2] REVIEW_REQUIRED, nije upisano: predmet=%s predlog=%s kandidati=%s",
                        predmet_id, i, r["kandidati"])
            ishodi.append(osnovno)
            continue

        claim_ids = sorted(r["claim_set"])
        try:
            red = await asyncio.to_thread(
                _upisi, supa,
                predmet_id=predmet_id, user_id=user_id,
                issue_id=_prevedi(r["issue_id"]) if odluka == ODLUKA_NASTAVAK else None,
                label=r["label"], relation_type=r["relation_type"],
                tezina=(tezina_po_indeksu or {}).get(i),
                fingerprint=otisak_pocetnog_skupa(claim_ids),
                claim_ids=claim_ids,
                claim_identiteti=_identiteti_za(claim_ids, poznati),
            )
        except Exception as exc:                       # noqa: BLE001 — namerno široko
            # Bez `return legacy_result`, bez `pass`, bez tihog preskakanja.
            raise V2PersistenceError(i, odluka, str(exc)) from exc

        osnovno.update({
            "issue_id": red["out_issue_id"],
            "contradiction_id": red["out_contradiction_id"],
            "created_issue": bool(red["out_created_issue"]),
            "persisted": True,
        })
        # Veza `__nova__<i>` -> stvarni id, za predloge koji tek slede u paketu.
        # Odluku o kontinuitetu unutar paketa je već doneo domen; ovde se samo
        # dopisuje identitet koji domen nije mogao znati.
        stvarni_id[f"__nova__{i}"] = red["out_issue_id"]
        ishodi.append(osnovno)

    return ishodi


# ═══════════════════════════════════════════════════════════════════════════
# 4. PAKETNI ULAZ — A016.7
#
# `persist_paket` upisuje predlog po predlog, svaki u sopstvenoj transakciji.
# A016.3 je izmerio posledicu: paket u kojem #0 prođe a #1 padne ostavlja #0
# upisan. Advokat tada vidi V2 sliku koja tvrdi manje nego što je Genome
# zaključio, a ništa ne kaže da je nepotpuna.
#
# Ovde je JEDNO opažanje JEDNA transakcija. Ne zato što je „čistije", nego zato
# što je to jedina granica na kojoj se sme tvrditi da je V2 slika kompletna.
#
# `persist_paket` se NE uklanja: A012 ga je dokazao uživo, a acceptance testovi
# ovog sprinta su BLOCKED dok migracija 124 ne bude pokrenuta. Ukloniti dokazan
# put u korist nedokazanog značilo bi zameniti izmereno nameravanim.
# ═══════════════════════════════════════════════════════════════════════════

_RPC_PAKET = "v2_persist_observation_package"


class V2PackageRejected(RuntimeError):
    """Paket je odbijen PRE ijednog upisa — nijedan red nije nastao.

    Podiže se kada domen proglasi bilo koji predlog neispravnim. Namerno se ne
    upisuje „bar ono što je ispravno": delimično opažanje koje izgleda kompletno
    je tačno stanje koje §4 mandata zabranjuje."""

    def __init__(self, indeksi: list[int], razlozi: list[str]):
        super().__init__(
            f"paket odbijen zbog neispravnih predloga {indeksi}: {'; '.join(razlozi)}")
        self.indeksi = indeksi
        self.razlozi = razlozi


class V2StaleObservation(RuntimeError):
    """Baza je odbila opažanje jer je zastarelo (`40001`).

    NIJE greška i NIJE uspeh. Novije opažanje je već primenjeno, a ovo se
    odbacuje bez ijedne mutacije. Pozivalac ovo NE SME prikazati kao neuspeo
    refresh — ništa nije pokvareno, samo je stiglo prekasno."""


def _ucitaj_verziju(supa, predmet_id: str) -> int:
    res = supa.table("predmeti").select("observation_version") \
              .eq("id", predmet_id).limit(1).execute()
    red = (res.data or [None])[0]
    if not isinstance(red, dict) or red.get("observation_version") is None:
        raise RuntimeError(
            f"predmet {predmet_id}: `observation_version` nije čitljiv. "
            "Migracija 124 nije pokrenuta — paketni upis se NE izvodi bez nje.")
    return int(red["observation_version"])


def _ucitaj_verzije_tema(supa, predmet_id: str) -> dict[str, str]:
    """`predmet_issues.id` -> `xmin` u trenutku donošenja odluke.

    Zaseban čitač, a ne prošireni `_ucitaj_postojece_teme`, da se ugovor koji
    A012/A013 već drže dokazanim ne bi menjao zbog novog sloja."""
    res = supa.table("predmet_issues").select("id,xmin") \
              .eq("predmet_id", predmet_id).execute()
    return {r["id"]: str(r["xmin"]) for r in (res.data or []) if r.get("xmin") is not None}


async def persist_observation_package(
    *, predmet_id: str, user_id: str, event_id: Optional[str], predlozi: Any,
    tezina_po_indeksu: Optional[dict[int, str]] = None,
    kompletno_opazanje: bool = True,
) -> dict:
    """CELO opažanje kao JEDNA atomska jedinica. Jedan poziv, jedna transakcija.

    Vraća `{"observation_version", "observation_complete", "event_id", "ishodi"}`.

    Podiže:
      `V2PackageRejected`  — neispravan predlog; NIJEDAN red nije nastao;
      `V2StaleObservation` — novije opažanje je preteklo ovo; bez mutacije;
      `V2PersistenceError` — transakcija je pala i vraćena; bez parcijalne slike.
    """
    if not predmet_id or not user_id:
        raise ValueError("persist_observation_package: predmet_id i user_id su obavezni")

    supa = _get_supa()
    verzija = await asyncio.to_thread(_ucitaj_verziju, supa, predmet_id)
    poznati = await asyncio.to_thread(_ucitaj_poznate_dokaze, supa, predmet_id)
    postojece = await asyncio.to_thread(_ucitaj_postojece_teme, supa, predmet_id)
    xmin_tema = await asyncio.to_thread(_ucitaj_verzije_tema, supa, predmet_id)

    # Odluka o kontinuitetu ostaje u domenu. Ovaj sloj je ne donosi, ne dopunjuje
    # i ne preispituje — samo je prenosi, zajedno sa `xmin`-om koji dokazuje nad
    # kojim je stanjem doneta.
    razreseni = razresi_paket(predlozi, predmet_id, poznati, postojece)

    lose = [(r["indeks"], r["razlog"]) for r in razreseni if r["odluka"] == ODLUKA_NEISPRAVNO]
    if lose:
        raise V2PackageRejected([i for i, _ in lose], [z for _, z in lose])

    # Kompletnost nije pretpostavka nego zaključak. Ako makar jedan predlog traži
    # ljudski pregled, ne zna se kojoj postojećoj spornoj tački pripada — pa se ne
    # sme tvrditi da ono što nije upisano „više nije opaženo". Bez ovoga bi
    # zatvaranje neopaženih ugasilo baš tačku koju je taj predlog gledao.
    pregled = [r["indeks"] for r in razreseni if r["odluka"] == ODLUKA_PREGLED]
    # A017: kompletnost može biti uskraćena i IZVAN ovog sloja. Materijalizacija
    # (`shared/contradiction_materializer.py`) odbija kandidata koji se ne može
    # razrešiti — Genome je tu kontradikciju VIDEO, ali je mi nismo mogli izraziti.
    # Ako bismo i tada tvrdili kompletnost, zatvaranje neopaženih bi ugasilo baš
    # onu spornu tačku na koju se odbijeni kandidat odnosio. Zato `and`, ne `or`:
    # kompletnost mora potvrditi SVAKI sloj koji je mogao nešto da izgubi.
    kompletno = bool(kompletno_opazanje) and not pregled

    stavke: list[dict] = []
    ishodi: dict[int, dict] = {}
    for r in razreseni:
        i, odluka = r["indeks"], r["odluka"]
        claim_ids = sorted(r["claim_set"])
        ishodi[i] = {
            "indeks": i, "odluka": odluka, "label": r["label"],
            "relation_type": r["relation_type"], "claim_ids": claim_ids,
            "kandidati": r["kandidati"], "razlog": r["razlog"],
            "odbacene_reference": r["odbacene_reference"],
            "issue_id": None, "contradiction_id": None,
            "created_issue": False, "persisted": False,
        }
        if odluka not in (ODLUKA_NOVA, ODLUKA_NASTAVAK):
            continue

        ref = r["issue_id"] if odluka == ODLUKA_NASTAVAK else None
        u_paketu = bool(ref) and str(ref).startswith("__nova__")
        stavke.append({
            "indeks": i,
            # `__nova__<i>` se NE prevodi ovde: u paketnom režimu nema
            # međurezultata između stavki. Prevod radi migracija 124, u istoj
            # transakciji, jer jedino ona zna id koji tek nastaje.
            "issue_ref": ref,
            "label": r["label"],
            "relation_type": r["relation_type"],
            "tezina": (tezina_po_indeksu or {}).get(i),
            "fingerprint": otisak_pocetnog_skupa(claim_ids),
            "dokaz_ids": claim_ids,
            "claim_identiteti": _identiteti_za(claim_ids, poznati),
            # Snapshot nad kojim je odluka doneta. Baza ga revalidira; ako se red
            # u međuvremenu promenio (npr. advokat ga je razrešio), ceo paket pada.
            # Tema nastala U OVOM paketu nema prethodni `xmin` — nije ni postojala.
            "expected_xmin": None if (not ref or u_paketu) else xmin_tema.get(ref),
        })

    def _poziv():
        return supa.rpc(_RPC_PAKET, {
            "p_predmet_id": predmet_id,
            "p_user_id": user_id,
            "p_event_id": event_id,
            "p_expected_version": verzija,
            "p_observation_complete": kompletno,
            "p_paket": stavke,
        }).execute()

    try:
        res = await asyncio.to_thread(_poziv)
    except Exception as exc:                            # noqa: BLE001 — namerno široko
        tekst = str(exc)
        # Prepoznavanje ide PRVENSTVENO po poruci, jer je poruka naša i stabilna,
        # a SQLSTATE se već jednom promenio: migracija 124 je koristila `40001`,
        # što je A016.8 izmerio kao neupotrebljivo — PostgREST klasu 40 tretira
        # kao prolaznu i ponavlja zahtev u krug (30s timeout naspram 0.32s za
        # `23503` nad ISTOM funkcijom). Migracija 125 to menja u `55000`.
        # Oba koda se priznaju jer u prelaznom periodu baza može imati bilo koji
        # od njih — to nije fallback na drugu logiku, nego dva imena za isti,
        # nedvosmisleno prepoznat ishod.
        if ("55000" in tekst or "40001" in tekst or "ustajalo opazanje" in tekst
                or "promenjena od donosenja odluke" in tekst):
            raise V2StaleObservation(tekst) from exc
        raise V2PersistenceError(-1, "PACKAGE", tekst) from exc

    redovi = res.data or []
    if stavke and not redovi:
        # Prazan odgovor na neprazan paket nije uspeh. Bez ovoga bi pad koji ne
        # podigne izuzetak prošao kao upisano opažanje.
        raise V2PersistenceError(
            -1, "PACKAGE",
            f"{_RPC_PAKET} nije vratio nijedan red za {len(stavke)} stavki")

    nova_verzija = verzija
    for red in redovi:
        idx = int(red["out_indeks"])
        nova_verzija = int(red["out_version"])
        ishodi[idx].update({
            "issue_id": red["out_issue_id"],
            "contradiction_id": red["out_contradiction_id"],
            "created_issue": bool(red["out_created_issue"]),
            "persisted": True,
        })

    if pregled:
        logger.info("[V2] opažanje predmeta %s NIJE kompletno — predlozi %s traže "
                    "pregled; neopažene kontradikcije se NE zatvaraju", predmet_id, pregled)

    return {
        "observation_version": nova_verzija,
        "observation_complete": kompletno,
        "event_id": event_id,
        "ishodi": [ishodi[i] for i in sorted(ishodi)],
    }
