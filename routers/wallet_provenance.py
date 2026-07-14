# -*- coding: utf-8 -*-
"""
Vindex AI — routers/wallet_provenance.py

F15: Wallet Provenance v1 (Faza 3) — poreklo i istorija Ethereum novčanika:
starost novčanika, obim aktivnosti, i unakrsna provera SVIH direktnih
kontakata (counterparty adresa) protiv OFAC SDN liste (routers/ofac_screening.py).

Izvor podataka: Etherscan API V2 (api.etherscan.io/v2/api, chainid=1 za
Ethereum mainnet). Stari V1 endpoint (bez chainid) je deprecated 15.8.2025 —
verifikovano direktno iz zvanične dokumentacije (docs.etherscan.io), ne
pretpostavljeno iz sećanja.

v1 obim: samo Ethereum mainnet (najveći ERC-20/stablecoin volumen), samo
DIREKTNI (1-hop) kontakti — ne multi-hop graf tragova (to je v2, mnogo skuplje
u broju API poziva). "Provenance" ovde znači: da li je NOVČANIK SAM sankcionisan,
i da li je NOVČANIK direktno transakcionisao sa sankcionisanom adresom — ne
dubinsku forenzičku analizu porekla sredstava.

Bez ETHERSCAN_API_KEY env varijable, endpoint vraća jasnu 503 poruku —
funkcija je kod-kompletna ali neaktivna dok korisnik ne obezbedi ključ
(besplatan Etherscan nalog, vidi napomenu u odgovoru).
"""
import asyncio
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from routers.ofac_screening import _load as _ofac_load
from shared.deps import _audit
from shared.permissions import PermissionService
from shared.usage import UsageService
from shared.rate import limiter

router = APIRouter()
logger = logging.getLogger("vindex.wallet_provenance")

_ETHERSCAN_BASE = "https://api.etherscan.io/v2/api"
_ETH_ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
_MAX_TX_PREGLED = 1000  # Etherscan Free tier limit po pozivu (od 1.7.2026)

# ── Confidence model (auditabilnost — vidi feedback sesije 2026-07-13) ──────
# VISOKA  — direktno pronađena na OFAC SDN listi (deterministički pogodak).
# SREDNJA — direktan (1-hop) kontakt sa adresom koja JE na OFAC listi.
# NISKA   — heuristička opservacija o obrascu ponašanja (npr. neuobičajeno
#           visok broj kontakata) — NIJE nalaz o sankcijama, samo analitički
#           signal koji sam analitičar treba dalje da proceni. Danas je jedina
#           populisana heuristika broj kontakata; arhitektura je spremna za
#           dodatne (npr. CEX tagging) kad bude postojao pouzdan izvor podataka.
CONFIDENCE_VISOKA = "VISOKA"
CONFIDENCE_SREDNJA = "SREDNJA"
CONFIDENCE_NISKA = "NISKA"

_KONTAKT_PRAG_HEURISTIKA = 300  # proizvoljan prag — heuristika, nije kalibrisan model

# ── Ograničenja analize — fiksna lista, uvek na vrhu izveštaja (UI + PDF) ────
# Ono što pravni/compliance tim mora da vidi PRE bilo kog nalaza, ne posle,
# ne u sitnom fusnoti tekstu. Vidi feedback sesije 2026-07-13.
OGRANICENJA_ANALIZE = [
    "Analiza je trenutno ograničena na Ethereum mrežu (mainnet).",
    "Proveravaju se isključivo direktni (1-hop) kontakti novčanika — sredstva se ne "
    "prate kroz više transakcija unazad (multi-hop).",
    "Rezultat NE predstavlja potpunu blockchain forenzičku analizu.",
    "Ne vrši se identifikacija vlasnika novčanika niti atribucija entiteta, osim putem "
    "javno dostupnih oznaka i zvaničnih sankcionih lista (OFAC SDN).",
]


class WalletProvenanceRequest(BaseModel):
    adresa: str = Field(..., min_length=42, max_length=42)

    @field_validator("adresa")
    @classmethod
    def validiraj(cls, v: str) -> str:
        v = v.strip()
        if not _ETH_ADDRESS_RE.match(v):
            raise ValueError("Adresa mora biti validna Ethereum adresa (0x + 40 hex karaktera).")
        return v


async def _etherscan_call(client: httpx.AsyncClient, api_key: str, params: dict) -> dict:
    full_params = {**params, "chainid": "1", "apikey": api_key}
    resp = await client.get(_ETHERSCAN_BASE, params=full_params, timeout=20.0)
    resp.raise_for_status()
    data = resp.json()
    return data


def _wei_to_eth(wei_str: str) -> float:
    try:
        return int(wei_str) / 1e18
    except (ValueError, TypeError):
        return 0.0


def _token_iznos(value_str: str, decimals_str: str) -> float:
    try:
        decimals = int(decimals_str)
        return int(value_str) / (10 ** decimals)
    except (ValueError, TypeError):
        return 0.0


def etherscan_konfigurisan() -> bool:
    return bool(os.getenv("ETHERSCAN_API_KEY"))


async def sakupi_wallet_provenance(adresa: str) -> dict:
    """Deljena core logika — koristi je i standalone F15.1 endpoint i Source-of-Funds
    dossier (routers/source_of_funds.py). Baca HTTPException na grešku (503/502/500)."""
    api_key = os.getenv("ETHERSCAN_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail=(
                "Wallet Risk Assessment servis nije konfigurisan (ETHERSCAN_API_KEY). "
                "Besplatan Etherscan API ključ se dobija na etherscan.io/apis — kontaktirajte administratora."
            ),
        )

    try:
        async with httpx.AsyncClient() as client:
            balans_data, txlist_data, tokentx_data = await asyncio.gather(
                _etherscan_call(client, api_key, {"module": "account", "action": "balance", "address": adresa}),
                _etherscan_call(client, api_key, {
                    "module": "account", "action": "txlist", "address": adresa,
                    "startblock": "0", "endblock": "999999999", "page": "1",
                    "offset": str(_MAX_TX_PREGLED), "sort": "asc",
                }),
                _etherscan_call(client, api_key, {
                    "module": "account", "action": "tokentx", "address": adresa,
                    "startblock": "0", "endblock": "999999999", "page": "1",
                    "offset": str(_MAX_TX_PREGLED), "sort": "asc",
                }),
            )
    except httpx.HTTPError:
        logger.exception("[F15] Etherscan poziv neuspešan")
        raise HTTPException(status_code=502, detail="Etherscan servis trenutno nedostupan. Pokušajte ponovo.")
    except Exception:
        logger.exception("[F15] wallet_provenance greška")
        raise HTTPException(status_code=500, detail="Greška pri proveri novčanika. Pokušajte ponovo.")

    if balans_data.get("status") not in ("1", 1) and balans_data.get("message") != "OK":
        raise HTTPException(
            status_code=502,
            detail=f"Etherscan greška: {balans_data.get('message', 'nepoznata greška')}",
        )

    balans_eth = _wei_to_eth(balans_data.get("result", "0"))
    eth_txs = txlist_data.get("result") if isinstance(txlist_data.get("result"), list) else []
    token_txs = tokentx_data.get("result") if isinstance(tokentx_data.get("result"), list) else []

    adresa_lower = adresa.lower()

    # ── OFAC provera novčanika samog i svih direktnih kontakata ─────────────
    ofac_baza = _ofac_load()
    ofac_lookup = ofac_baza["adrese"] if ofac_baza else {}

    novcanik_sankcionisan = ofac_lookup.get(adresa_lower)

    kontakti: dict = {}
    for tx in eth_txs:
        for polje in ("from", "to"):
            drugi = (tx.get(polje) or "").lower()
            if drugi and drugi != adresa_lower:
                kontakti.setdefault(drugi, {"broj_transakcija": 0, "poslednja": None})
                kontakti[drugi]["broj_transakcija"] += 1
                kontakti[drugi]["poslednja"] = tx.get("timeStamp")
    for tx in token_txs:
        for polje in ("from", "to"):
            drugi = (tx.get(polje) or "").lower()
            if drugi and drugi != adresa_lower:
                kontakti.setdefault(drugi, {"broj_transakcija": 0, "poslednja": None})
                kontakti[drugi]["broj_transakcija"] += 1
                kontakti[drugi]["poslednja"] = tx.get("timeStamp")

    sankcionisani_kontakti = []
    for drugi, info in kontakti.items():
        pogodak = ofac_lookup.get(drugi)
        if pogodak:
            sankcionisani_kontakti.append({
                "adresa": pogodak["adresa_originalna"],
                "entitet": pogodak["entitet"],
                "programi": pogodak["programi"],
                "broj_transakcija_sa_ovim_novcanikom": info["broj_transakcija"],
            })

    # ── Osnovna statistika aktivnosti ───────────────────────────────────────
    svi_tx_timestamps = [int(t["timeStamp"]) for t in eth_txs if t.get("timeStamp")] + \
                        [int(t["timeStamp"]) for t in token_txs if t.get("timeStamp")]
    prva_aktivnost = min(svi_tx_timestamps) if svi_tx_timestamps else None
    poslednja_aktivnost = max(svi_tx_timestamps) if svi_tx_timestamps else None
    starost_dana = int((time.time() - prva_aktivnost) / 86400) if prva_aktivnost else None

    ukupno_poslato_eth = sum(
        _wei_to_eth(t["value"]) for t in eth_txs
        if (t.get("from") or "").lower() == adresa_lower and t.get("isError") == "0"
    )
    ukupno_primljeno_eth = sum(
        _wei_to_eth(t["value"]) for t in eth_txs
        if (t.get("to") or "").lower() == adresa_lower and t.get("isError") == "0"
    )

    limit_dostignut = len(eth_txs) >= _MAX_TX_PREGLED or len(token_txs) >= _MAX_TX_PREGLED
    tx_prikazano_upozorenje = (
        f"Prikazano poslednjih {_MAX_TX_PREGLED} transakcija (Etherscan Free tier limit) — "
        f"stariji novčanici sa mnogo aktivnosti mogu imati dodatnu, ovde neprikazanu istoriju."
        if limit_dostignut else None
    )

    # ── Nalazi — razdvojeni po vrsti, NE svi pod "rizik" (auditabilnost) ────
    sankcioni_nalazi = []
    if novcanik_sankcionisan:
        sankcioni_nalazi.append({
            "tip": "novcanik_na_ofac_listi",
            "confidence": CONFIDENCE_VISOKA,
            "opis": (
                f"Novčanik je direktno pronađen na trenutno učitanoj OFAC SDN listi — "
                f"entitet: {novcanik_sankcionisan['entitet']}, "
                f"programi: {', '.join(novcanik_sankcionisan['programi'])}."
            ),
            "detalji": novcanik_sankcionisan,
        })
    for k in sankcionisani_kontakti:
        sankcioni_nalazi.append({
            "tip": "direktan_kontakt_sa_sankcionisanom_adresom",
            "confidence": CONFIDENCE_SREDNJA,
            "opis": (
                f"Direktan (1-hop) kontakt sa adresom na OFAC SDN listi — "
                f"{k['entitet']} ({', '.join(k['programi'])}), "
                f"{k['broj_transakcija_sa_ovim_novcanikom']} transakcija sa ovim novčanikom."
            ),
            "detalji": k,
        })

    analiticki_nalazi = []
    if len(kontakti) > _KONTAKT_PRAG_HEURISTIKA:
        analiticki_nalazi.append({
            "tip": "visok_broj_kontakata",
            "confidence": CONFIDENCE_NISKA,
            "opis": (
                f"{len(kontakti)} jedinstvenih kontakata u analiziranom periodu — neuobičajeno "
                f"visoko za pojedinačni novčanik, može ukazivati na agregatorsku/exchange aktivnost "
                f"ili visok obim transakcija. Ovo je heuristička opservacija (prag: "
                f"{_KONTAKT_PRAG_HEURISTIKA}), NE nalaz o sankcijama — zahteva dalju procenu analitičara."
            ),
        })

    nedostatak_podataka_nalazi = [{
        "tip": "samo_direktni_kontakti",
        "opis": (
            "Provera pokriva samo direktne (1-hop) kontakte novčanika — ne prati sredstva "
            "kroz više transakcija unazad (multi-hop)."
        ),
    }]
    if tx_prikazano_upozorenje:
        nedostatak_podataka_nalazi.append({
            "tip": "transakcijski_limit",
            "opis": tx_prikazano_upozorenje,
        })

    return {
        "modul": "wallet_provenance",
        "adresa": adresa,
        "ogranicenja_analize": OGRANICENJA_ANALIZE,
        "coverage": {
            "lanac": "Ethereum (mainnet)",
            "izvor": "Etherscan API V2",
            "analizirano_eth_transakcija": len(eth_txs),
            "analizirano_token_transakcija": len(token_txs),
            "limit_dostignut": limit_dostignut,
            "poslednje_osvezavanje": datetime.now(timezone.utc).isoformat(),
        },
        "nalazi": {
            "sankcioni": sankcioni_nalazi,
            "analiticki": analiticki_nalazi,
            "nedostatak_podataka": nedostatak_podataka_nalazi,
        },
        # Zadržana ravna polja radi jednostavnog prikaza (tabela/summary) —
        # nalazi iznad su izvor istine za bilo kakvu compliance/audit odluku.
        "novcanik_sankcionisan": bool(novcanik_sankcionisan),
        "novcanik_sankcije_detalji": novcanik_sankcionisan,
        "sankcionisani_direktni_kontakti": sankcionisani_kontakti,
        "balans_eth": round(balans_eth, 6),
        "prva_aktivnost_timestamp": prva_aktivnost,
        "poslednja_aktivnost_timestamp": poslednja_aktivnost,
        "starost_dana": starost_dana,
        "broj_eth_transakcija": len(eth_txs),
        "broj_token_transakcija": len(token_txs),
        "broj_jedinstvenih_kontakata": len(kontakti),
        "ukupno_poslato_eth": round(ukupno_poslato_eth, 6),
        "ukupno_primljeno_eth": round(ukupno_primljeno_eth, 6),
        "upozorenje_limit": tx_prikazano_upozorenje,
        "napomena": (
            "Provera pokriva samo Ethereum mainnet i DIREKTNE (1-hop) kontakte novčanika — "
            "ne prati sredstva kroz više transakcija unazad (multi-hop). Odsustvo poklapanja NE "
            "predstavlja potvrdu da su sredstva bez rizika — samo da nema poznatog poklapanja sa "
            "trenutno učitanom OFAC SDN listom. Ovo nije pravni savet niti zamena za profesionalni "
            "AML/sankcijski program."
        ),
    }


@router.post("/web3/wallet-provenance")  # F15.1
@limiter.limit("10/minute")
async def post_wallet_provenance(
    req: WalletProvenanceRequest, request: Request,
    user: dict = Depends(PermissionService.require("da_wallet_risk_assessment")),
):
    """F15.1 — Wallet Provenance v1: starost/aktivnost novčanika + OFAC provera direktnih kontakata (PRO)."""
    asyncio.create_task(_audit(user["user_id"], "wallet_provenance", ""))
    rezultat = await sakupi_wallet_provenance(req.adresa)
    await UsageService.consume(user["user_id"], user.get("email", ""), "da_wallet_risk_assessment")
    return rezultat
