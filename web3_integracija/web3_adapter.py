# -*- coding: utf-8 -*-
"""
Web3Adapter — produkcijski bridge između EVM blockchaina i VindexAI Legal Engine-a.

ARHITEKTONSKA GARANCIJA:
  Jednosmerni adapter. Output je uvek Web3LegalEvent (JSON-serijalizabilan).
  Ne importuje niti modifikuje nijedan fajl van /web3_integracija direktorijuma.

Komunikacija sa Legal Engine-om:
  event.to_prompt()   → str   → POST /api/pitanje  { "pitanje": <str> }
  event.to_json()     → str   → za logove / audit trail
  event.to_dict()     → dict  → za programatski pristup
"""
from __future__ import annotations

import datetime
from typing import Any, Optional

from .schemas     import Web3LegalEvent, event_iz_krsenja
from .zoo_mapping import detektuj_krsenje


# BlockchainDogadjaj — normalizovani format za internu upotrebu adaptera
class _LegacyDogadjaj:
    """Normalizovana blockchain transakcija — interni format pre konverzije u Web3LegalEvent."""
    def __init__(self, transaction_id, strana_a="", strana_b="", vrednost_wei=0,
                 naziv_dobra="", status_uplate="Potpun", status_dobra="Ispravno",
                 rok_isporuke="Aktivan", timestamp=None, raw=None):
        import datetime as _dt
        self.transaction_id = transaction_id
        self.strana_a       = strana_a
        self.strana_b       = strana_b
        self.vrednost_wei   = vrednost_wei
        self.naziv_dobra    = naziv_dobra
        self.status_uplate  = status_uplate
        self.status_dobra   = status_dobra
        self.rok_isporuke   = rok_isporuke
        self.timestamp      = timestamp or _dt.datetime.utcnow()
        self.raw            = raw or {}

    @property
    def vrednost_eth(self) -> float:
        return self.vrednost_wei / 1e18

    def kao_recnik(self) -> dict:
        return {
            "transaction_id": self.transaction_id,
            "strana_a":       self.strana_a,
            "strana_b":       self.strana_b,
            "vrednost_eth":   self.vrednost_eth,
            "naziv_dobra":    self.naziv_dobra,
            "status_uplate":  self.status_uplate,
            "status_dobra":   self.status_dobra,
            "rok_isporuke":   self.rok_isporuke,
            "timestamp":      self.timestamp.isoformat(),
        }


# Eksponuj kao BlockchainDogadjaj za korisnike modula
BlockchainDogadjaj = _LegacyDogadjaj

# Minimalni ABI za ERC-20 + kupoprodajne ugovore
_MINIMALNI_ABI: list[dict] = [
    {
        "name":   "Transfer",
        "type":   "event",
        "inputs": [
            {"name": "from",  "type": "address", "indexed": True},
            {"name": "to",    "type": "address", "indexed": True},
            {"name": "value", "type": "uint256", "indexed": False},
        ],
    },
    {
        "name":   "OrderFulfilled",
        "type":   "event",
        "inputs": [
            {"name": "orderId",   "type": "bytes32", "indexed": True},
            {"name": "buyer",     "type": "address", "indexed": False},
            {"name": "seller",    "type": "address", "indexed": False},
            {"name": "amount",    "type": "uint256", "indexed": False},
            {"name": "fulfilled", "type": "bool",    "indexed": False},
        ],
    },
]


class Web3Adapter:
    """
    Bridge između EVM-kompatibilnih blockchaina i VindexAI.

    Upotreba (sa mrežom):
        adapter = Web3Adapter(rpc_url="https://mainnet.infura.io/v3/KEY",
                              contract_address="0x...")
        if adapter.connect():
            dogadjaj = adapter.procitaj_transakciju("0xabc...")
            event    = adapter.generiši_event(dogadjaj)

    Upotreba (bez mreže):
        from web3_integracija.demo import simuliraj_blockchain_dogadjaj
        r = simuliraj_blockchain_dogadjaj("nepotpuna_uplata")
        print(r["event"].to_json())    # strukturirani JSON
        print(r["prompt"])             # tekst za /api/pitanje
    """

    def __init__(
        self,
        rpc_url:          str  = "",
        contract_address: str  = "",
        abi:              list = None,
        mreza_naziv:      str  = "Ethereum Mainnet",
    ):
        self._rpc_url          = rpc_url
        self._contract_address = contract_address
        self._abi              = abi or _MINIMALNI_ABI
        self._mreza_naziv      = mreza_naziv
        self._w3               = None
        self._contract         = None
        self._connected        = False

    # ── Konekcija ─────────────────────────────────────────────────────────────

    def connect(self) -> bool:
        """Vraća False (ne baca) ako web3 nije instaliran ili RPC ne odgovara."""
        if not self._rpc_url:
            return False
        try:
            from web3 import Web3
            w3 = Web3(Web3.HTTPProvider(self._rpc_url, request_kwargs={"timeout": 10}))
            if not w3.is_connected():
                return False
            self._w3 = w3
            if self._contract_address:
                self._contract = w3.eth.contract(
                    address=Web3.to_checksum_address(self._contract_address),
                    abi=self._abi,
                )
            self._connected = True
            return True
        except (ImportError, Exception):
            return False

    @property
    def je_konektovan(self) -> bool:
        return self._connected

    # ── Čitanje sa blockchaina ────────────────────────────────────────────────

    def procitaj_transakciju(self, tx_hash: str) -> _LegacyDogadjaj:
        """Dohvata transakciju i vraća BlockchainDogadjaj (legacy format za zoo_mapping)."""
        if not self._connected or not self._w3:
            raise RuntimeError(
                "Adapter nije konektovan. Pozovite connect() "
                "ili koristite simuliraj_blockchain_dogadjaj() za testiranje."
            )
        tx      = self._w3.eth.get_transaction(tx_hash)
        receipt = self._w3.eth.get_transaction_receipt(tx_hash)
        block   = self._w3.eth.get_block(receipt.blockNumber)
        uspesno = receipt.get("status", 0) == 1
        return _LegacyDogadjaj(
            transaction_id = tx_hash,
            strana_a       = tx.get("from", ""),
            strana_b       = tx.get("to", ""),
            vrednost_wei   = tx.get("value", 0),
            status_uplate  = "Potpun" if uspesno else "Nepotpun",
            timestamp      = datetime.datetime.utcfromtimestamp(block.timestamp),
            raw            = dict(tx),
        )

    def procitaj_dogadjaje_ugovora(
        self,
        naziv_dogadjaja: str,
        od_bloka:        int       = 0,
        do_bloka:        int | str = "latest",
    ) -> list[dict]:
        """Vraća log-ove specifičnog događaja pametnog ugovora."""
        if not self._contract:
            raise RuntimeError("Pametni ugovor nije inicijalizovan.")
        event = getattr(self._contract.events, naziv_dogadjaja, None)
        if not event:
            raise ValueError(f"Događaj '{naziv_dogadjaja}' nije u ABI-ju.")
        return [dict(log.args) for log in event.get_logs(fromBlock=od_bloka, toBlock=do_bloka)]

    # ── Bridge: BlockchainDogadjaj → Web3LegalEvent (JSON) ───────────────────

    def generiši_event(self, dogadjaj: _LegacyDogadjaj) -> list[Web3LegalEvent]:
        """
        Konvertuje blockchain transakciju u listu Web3LegalEvent objekata.
        Jedan događaj može generisati više eventa (jedno po kršenju).
        Vraća praznu listu ako nema detektovanog kršenja.
        """
        podaci  = dogadjaj.kao_recnik()
        krsenja = detektuj_krsenje(podaci)
        if not krsenja:
            return []
        return [
            event_iz_krsenja(
                tx_hash    = dogadjaj.transaction_id,
                amount_eth = dogadjaj.vrednost_eth,
                tx_status  = podaci.get("status_uplate", ""),
                article    = k.clan.broj,
                breach_type= k.clan.naziv,
            )
            for k in krsenja
        ]

    def analiziraj_blok_dogadjaje(
        self,
        dogadjaji: list[_LegacyDogadjaj],
    ) -> list[dict]:
        """Batch analiza — vraća strukturirane izveštaje samo za kršenja."""
        rezultati = []
        for dogadjaj in dogadjaji:
            eventi = self.generiši_event(dogadjaj)
            for ev in eventi:
                rezultati.append({
                    "transaction_id": dogadjaj.transaction_id,
                    "event_id":       ev.event_id,
                    "article":        ev.legal_context.article,
                    "breach_type":    ev.legal_context.breach_type,
                    "prompt":         ev.to_prompt(),
                    "json":           ev.to_dict(),
                    "tip_podneska":   _tip_za_clan(ev.legal_context.article),
                })
        return rezultati


def _tip_za_clan(article: str) -> str:
    """Mapira ZOO član na tip podneska koji Legal Engine razume."""
    return {
        "124": "predlog_izvrsenje",
        "154": "tuzba_naknada_stete",
        "262": "tuzba_naknada_stete",
    }.get(article, "tuzba_naknada_stete")
