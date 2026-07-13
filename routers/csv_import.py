# -*- coding: utf-8 -*-
"""
Vindex AI — routers/csv_import.py

F13: CSV Import za Exchange transakcije (CARF/DAC8 Readiness — Faza 2)

Prihvata CSV export sa Binance ili Kraken, detektuje format po tacnim
kolonama, normalizuje u internu semu, i klasifikuje transakcije u CARF/DAC8
kategorije (vidi web3_compliance.py exchange_reporting_simulator_sync za
objasnjenje kategorija).

Format detekcija — TACNI, verifikovani nazivi kolona (ne nagadjanje):
  Binance: User_ID, UTC_Time, Account, Operation, Coin, Change, Remark
  Kraken:  txid, refid, time, type, subtype, aclass, asset, amount, fee, balance
    (izvor: support.kraken.com "How to interpret Ledger history fields")

v1 obim: samo ova dva provajdera (najveca korisnicka baza u regionu).
Cist deterministicki kod — NEMA AI poziva, nema troska kredita.
"""
import csv
import io
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from shared.deps import get_current_user, require_pro

router = APIRouter()
logger = logging.getLogger("vindex.csv_import")

MAX_CSV_SIZE_BYTES = 5 * 1024 * 1024  # 5MB — dovoljno za par godina istorije
MAX_REDOVA = 50_000

# ── Format signature-i (tacni nazivi kolona) ────────────────────────────────────

_BINANCE_KOLONE = {"user_id", "utc_time", "account", "operation", "coin", "change"}
_KRAKEN_KOLONE  = {"txid", "refid", "time", "type", "asset", "amount"}

# ── Klasifikacija Binance "Operation" → CARF kategorija ─────────────────────────

_BINANCE_OPERACIJA_MAP = {
    "buy": "kupovina_fiat",
    "sell": "prodaja_fiat",
    "transaction related": "crypto_to_crypto",
    "transaction spend": "crypto_to_crypto",
    "transaction revenue": "crypto_to_crypto",
    "transaction buy": "kupovina_fiat",
    "transaction sold": "prodaja_fiat",
    "deposit": "transfer_in",
    "withdraw": "transfer_out",
    "fee": "naknada",
    "transaction fee": "naknada",
    "staking rewards": "staking_prihod",
    "staking purchase": "staking_prihod",
    "pos savings interest": "staking_prihod",
    "cash voucher distribution": "airdrop_bonus",
    "airdrop assets": "airdrop_bonus",
    "distribution": "airdrop_bonus",
    "commission history": "naknada",
}

# ── Klasifikacija Kraken "type" → CARF kategorija ───────────────────────────────

_KRAKEN_TIP_MAP = {
    "trade": "crypto_to_crypto",  # precizira se dalje na osnovu asset/valuta para
    "deposit": "transfer_in",
    "withdrawal": "transfer_out",
    "staking": "staking_prihod",
    "earn": "staking_prihod",
    "reward": "staking_prihod",
    "transfer": "transfer_interni",
    "spend": "crypto_to_crypto",
    "receive": "crypto_to_crypto",
    "adjustment": "korekcija",
    "margin": "crypto_to_crypto",
}

_FIAT_VALUTE = {"EUR", "USD", "RSD", "GBP", "CHF", "JPY", "ZUSD", "ZEUR", "ZGBP"}


def _detektuj_format(header: list[str]) -> Optional[str]:
    header_set = {h.strip().lower() for h in header}
    if _BINANCE_KOLONE.issubset(header_set):
        return "binance"
    if _KRAKEN_KOLONE.issubset(header_set):
        return "kraken"
    return None


def _parsiraj_binance(reader: csv.DictReader) -> list[dict]:
    transakcije = []
    for row in reader:
        operacija_raw = (row.get("Operation") or "").strip()
        operacija_lower = operacija_raw.lower()
        kategorija = _BINANCE_OPERACIJA_MAP.get(operacija_lower, "nepoznato")
        try:
            iznos = float(row.get("Change") or 0)
        except ValueError:
            iznos = 0.0
        transakcije.append({
            "datum": (row.get("UTC_Time") or "").strip(),
            "asset": (row.get("Coin") or "").strip(),
            "iznos": iznos,
            "kategorija": kategorija,
            "izvorna_oznaka": operacija_raw,
            "napomena": (row.get("Remark") or "").strip(),
            "platforma": "binance",
        })
    return transakcije


def _parsiraj_kraken(reader: csv.DictReader) -> list[dict]:
    """
    Kraken predstavlja svaki trade kao DVA ledger reda povezana istim refid-om
    (npr. -100 ZEUR / +0.002 XXBT za jednu kupovinu BTC-a za EUR). Grupisemo po
    refid PRE klasifikacije, jer ako gledamo svaki red izolovano, crypto-nogu
    trade-a (npr. XXBT) bismo pogresno oznacili "crypto_to_crypto" umesto
    "kupovina_fiat" — tacna klasifikacija zavisi od DRUGE noge istog trade-a.
    """
    sirovi = list(reader)

    # Prvi prolaz: grupisi trade redove po refid da znamo da li par ukljucuje fiat
    trade_ima_fiat: dict[str, bool] = {}
    for row in sirovi:
        if (row.get("type") or "").strip().lower() != "trade":
            continue
        refid = (row.get("refid") or "").strip()
        asset = (row.get("asset") or "").strip().upper()
        if asset in _FIAT_VALUTE:
            trade_ima_fiat[refid] = True
        else:
            trade_ima_fiat.setdefault(refid, False)

    transakcije = []
    for row in sirovi:
        tip_raw = (row.get("type") or "").strip()
        tip_lower = tip_raw.lower()
        asset = (row.get("asset") or "").strip()
        refid = (row.get("refid") or "").strip()
        kategorija = _KRAKEN_TIP_MAP.get(tip_lower, "nepoznato")
        try:
            iznos = float(row.get("amount") or 0)
        except ValueError:
            iznos = 0.0
        # Ako je trade i BAR JEDNA noga para (po refid) je fiat valuta → cela
        # transakcija je kupovina/prodaja za fiat, ne crypto-to-crypto — vazi i
        # za nogu koja je sama po sebi crypto asset (npr. XXBT u BTC/EUR trade-u).
        if tip_lower == "trade" and trade_ima_fiat.get(refid):
            if asset.upper() in _FIAT_VALUTE:
                kategorija = "prodaja_fiat" if iznos > 0 else "kupovina_fiat"
            else:
                # Crypto noga istog fiat trade-a: predznak je OBRNUT u odnosu na fiat nogu
                kategorija = "kupovina_fiat" if iznos > 0 else "prodaja_fiat"
        transakcije.append({
            "datum": (row.get("time") or "").strip(),
            "asset": asset,
            "iznos": iznos,
            "kategorija": kategorija,
            "izvorna_oznaka": tip_raw,
            "napomena": (row.get("subtype") or "").strip(),
            "platforma": "kraken",
        })
    return transakcije


_KATEGORIJA_LABELE = {
    "kupovina_fiat":    "Kupovina za fiat valutu",
    "prodaja_fiat":     "Prodaja za fiat valutu",
    "crypto_to_crypto": "Crypto-to-crypto razmena",
    "transfer_in":      "Uplata (deposit)",
    "transfer_out":     "Isplata / povlačenje (withdraw) — potencijalno self-custody",
    "transfer_interni": "Interni transfer (isti nalog)",
    "staking_prihod":   "Staking / earn prihod",
    "airdrop_bonus":     "Airdrop / bonus",
    "naknada":          "Naknada (fee)",
    "korekcija":        "Korekcija stanja",
    "nepoznato":        "Nepoznata kategorija — proveriti ručno",
}


@router.post("/csv-import/analiziraj")  # F13.1
async def post_csv_analiziraj(
    file: UploadFile = File(...),
    user: dict = Depends(require_pro),
):
    """
    F13.1 — Upload CSV exporta (Binance ili Kraken), vraća klasifikovan pregled
    transakcija po CARF/DAC8 kategorijama. Čist deterministički parser — bez AI
    poziva, bez troška kredita.
    """
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=422, detail="Fajl mora biti .csv format.")

    sadrzaj = await file.read()
    if len(sadrzaj) > MAX_CSV_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="Fajl je prevelik (max 5MB).")

    try:
        tekst = sadrzaj.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            tekst = sadrzaj.decode("latin-1")
        except Exception:
            raise HTTPException(status_code=422, detail="Ne mogu da pročitam kodiranje fajla.")

    try:
        reader = csv.DictReader(io.StringIO(tekst))
        header = reader.fieldnames or []
    except Exception:
        raise HTTPException(status_code=422, detail="Neispravan CSV format.")

    if not header:
        raise HTTPException(status_code=422, detail="CSV fajl nema zaglavlje (header).")

    format_detektovan = _detektuj_format(header)
    if not format_detektovan:
        raise HTTPException(
            status_code=422,
            detail=(
                "Format CSV fajla nije prepoznat. Trenutno podržani exporti: "
                "Binance (Transaction History) i Kraken (Ledger History). "
                "Proverite da li ste izvezli tačan tip istorije."
            ),
        )

    if format_detektovan == "binance":
        transakcije = _parsiraj_binance(reader)
    else:
        transakcije = _parsiraj_kraken(reader)

    if len(transakcije) > MAX_REDOVA:
        transakcije = transakcije[:MAX_REDOVA]
        logger.warning("[CSV_IMPORT] Fajl skraćen na %d redova (limit)", MAX_REDOVA)

    # Agregacija po kategoriji
    stat_po_kategoriji: dict[str, dict] = {}
    for t in transakcije:
        kat = t["kategorija"]
        if kat not in stat_po_kategoriji:
            stat_po_kategoriji[kat] = {"broj": 0, "labela": _KATEGORIJA_LABELE.get(kat, kat)}
        stat_po_kategoriji[kat]["broj"] += 1

    broj_nepoznatih = stat_po_kategoriji.get("nepoznato", {}).get("broj", 0)
    broj_self_custody = stat_po_kategoriji.get("transfer_out", {}).get("broj", 0)

    return {
        "platforma_detektovana": format_detektovan,
        "ukupno_transakcija": len(transakcije),
        "statistika_po_kategoriji": stat_po_kategoriji,
        "upozorenja": (
            [f"{broj_nepoznatih} transakcija nije moglo biti klasifikovano — proverite ručno."]
            if broj_nepoznatih else []
        ) + (
            [
                f"{broj_self_custody} isplata (withdraw) detektovano — ovo su potencijalni "
                f"self-custody transferi, relevantni za CARF/DAC8 'Transfer' kategoriju "
                f"(Section II tacka (i)/(ix))."
            ] if broj_self_custody else []
        ),
        "transakcije": transakcije[:500],  # cap na 500 za prikaz, statistika je nad svim
        "napomena": (
            "Ovo je deterministička klasifikacija na osnovu naziva operacije/tipa iz CSV "
            "exporta — NIJE poreski savet i ne zamenjuje pregled od strane poreskog savetnika. "
            "Kategorije 'crypto_to_crypto' i 'nepoznato' posebno zahtevaju ručnu proveru."
        ),
    }


@router.get("/csv-import/podrzani-formati")  # F13.2
async def get_podrzani_formati(user: dict = Depends(get_current_user)):
    """F13.2 — Lista trenutno podržanih CSV formata (besplatno, bez PRO gate-a)."""
    return {
        "podrzano": [
            {
                "platforma": "Binance",
                "tip_exporta": "Transaction History (Account Statement)",
                "kako": "Binance → Wallet → Transaction History → Generate all statements → CSV",
            },
            {
                "platforma": "Kraken",
                "tip_exporta": "Ledger History",
                "kako": "Kraken Pro → Documents → Export → Ledgers → CSV",
            },
        ],
        "uskoro": ["Coinbase", "Bitget"],
    }
