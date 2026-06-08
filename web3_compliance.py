# -*- coding: utf-8 -*-
"""
F11 — Web3/MiCA AI Compliance moduli (ZDI + MiCA).
Sve funkcije su sinhroni pozivi — pozivaju se preko asyncio.to_thread u api.py.
Pinecone namespace: "web3_zdi_mca"
"""
from __future__ import annotations
import logging
import os

logger = logging.getLogger(__name__)

_WEB3_NAMESPACE = "web3_zdi_mca"

# ── System promptovi ──────────────────────────────────────────────────────────

_WEB3_SEARCH_SYSTEM = """Ti si specijalizovani pravni savetnik za digitalnu imovinu i kripto-regulativu.
Koristiš isključivo srpski ZDI (Zakon o digitalnoj imovini, Sl. glasnik RS 153/2020)
i EU MiCA regulativu (Regulation EU 2023/1114).

Pravila odgovaranja:
- Za srpsko pravo: uvek navedi tačan član ZDI
- Za EU pravo: navedi Title i Article MiCA
- Jasno razgraničiti šta važi u Srbiji (ZDI) vs šta važi u EU (MiCA)
- Ako se pitanje tiče oba sistema — komparativno objasni
- Ne izmišljaj članove — ako nisi siguran, reci to
- Na kraju svakog odgovora dodaj: "⚠️ Ovo nije pravni savet. Konsultujte advokata specijalizovanog za digitalnu imovinu."
"""

_COMPLIANCE_CHECKER_SYSTEM = """Ti si compliance officer specijalizovan za digitalnu imovinu.
Analiziraš da li opisana aktivnost ili poslovni model zahteva dozvolu, registraciju ili
posebne mere po ZDI (Srbija) i MiCA (EU).

Odgovori ISKLJUČIVO na osnovu ZDI i MiCA.

Struktura odgovora (obavezna):
1. KLASIFIKACIJA DIGITALNE IMOVINE
   - Po ZDI: Virtuelna valuta / Digitalni token / Hibridni / Nije digitalna imovina
   - Po MiCA: ART / EMT / Other crypto-asset / Van MiCA

2. NADLEŽNI ORGAN (Srbija)
   - NBS (za virtuelne valute) / KHoV (za digitalne tokene) / Oba / Nije primenljivo

3. DOZVOLA/REGISTRACIJA POTREBNA?
   - Po ZDI: DA / NE / DELIMIČNO (sa objašnjenjem koji čl. ZDI)
   - Po MiCA: DA / NE / DELIMIČNO (sa objašnjenjem koji Title/Article MiCA)

4. BELI PAPIR (WHITEPAPER) POTREBAN?
   - Po ZDI: DA / NE (sa pragovima iz čl. 15 ZDI)
   - Po MiCA: DA / NE (sa pragovima iz čl. 4 MiCA)

5. AML/KYC OBAVEZE
   - Koje mere su obavezne (čl. 81-97 ZDI)

6. RIZICI I KAZNE
   - Šta se dešava ako se ne uskladi (čl. 140-144 ZDI, MiCA sankcije)

7. PREPORUČENE AKCIJE (konkretan redosled koraka)

Na kraju: UKUPNA PROCENA RIZIKA: NIZAK / SREDNJI / VISOK"""

_WHITEPAPER_CHECKER_SYSTEM = """Ti si pravni ekspert za bele papire (whitepaper) digitalne imovine.
Analiziraš da li dostavljeni whitepaper (ili opis projekta) ispunjava zahteve
ZDI čl. 12-19 (Srbija) i MiCA čl. 6 (EU).

Struktura odgovora (obavezna):
1. OBAVEZNI ELEMENTI KOJI POSTOJE ✓
2. OBAVEZNI ELEMENTI KOJI NEDOSTAJU ✗
   Za svaki: šta nedostaje, koji član to zahteva, predlog kako dodati
3. ZABRANJENI SADRŽAJI (obmanjujuće izjave, garantovanje prinosa)
4. PREPORUKA: SPREMAN / POTREBNE DOPUNE / ODBACITI
5. PROCENJENI ROK ODOBRAVANJA (po ZDI: KHoV/NBS ima 30 dana)"""


# ── Sync funkcije ──────────────────────────────────────────────────────────────

def web3_pretraga_sync(upit: str, api_key: str) -> str:
    """RAG pretraga nad web3_zdi_mca namespacom + GPT-4o odgovor."""
    from openai import OpenAI as _OAI
    from app.services.retrieve import _get_index, _ugradi_query

    try:
        vec = _ugradi_query(upit)
        idx = _get_index()
        res = idx.query(
            vector=vec,
            top_k=5,
            namespace=_WEB3_NAMESPACE,
            include_metadata=True,
        )
        matches = res.matches if hasattr(res, "matches") else []
        chunks = [
            f"[{m.metadata.get('izvor', '')}]: {m.metadata.get('tekst', '')}"
            for m in matches
            if float(m.score) >= 0.55 and m.metadata.get("tekst", "").strip()
        ]
        kontekst = "\n\n".join(chunks) if chunks else "Nema relevantnih odredbi u bazi."
    except Exception as e:
        logger.warning("[WEB3] Pinecone pretraga neuspešna: %s", e)
        kontekst = "Baza nije dostupna — odgovor se zasniva na opštim pravilima."

    client = _OAI(api_key=api_key)
    resp = client.chat.completions.create(
        model="gpt-4o",
        temperature=0.1,
        max_tokens=2000,
        timeout=90.0,
        messages=[
            {"role": "system", "content": _WEB3_SEARCH_SYSTEM},
            {"role": "user", "content": (
                f"Relevantne odredbe iz baze znanja:\n{kontekst}\n\n"
                f"Pitanje: {upit}"
            )},
        ],
    )
    return (resp.choices[0].message.content or "").strip()


def compliance_check_sync(opis_aktivnosti: str, api_key: str) -> str:
    """Compliance checker: da li aktivnost zahteva dozvolu po ZDI i MiCA."""
    from openai import OpenAI as _OAI
    from app.services.retrieve import _get_index, _ugradi_query

    try:
        vec = _ugradi_query(opis_aktivnosti)
        idx = _get_index()
        res = idx.query(
            vector=vec,
            top_k=6,
            namespace=_WEB3_NAMESPACE,
            include_metadata=True,
        )
        matches = res.matches if hasattr(res, "matches") else []
        chunks = [
            f"[{m.metadata.get('izvor', '')}]: {m.metadata.get('tekst', '')}"
            for m in matches
            if float(m.score) >= 0.52 and m.metadata.get("tekst", "").strip()
        ]
        kontekst = "\n\n".join(chunks) if chunks else ""
    except Exception as e:
        logger.warning("[WEB3] Compliance Pinecone neuspešna: %s", e)
        kontekst = ""

    client = _OAI(api_key=api_key)
    resp = client.chat.completions.create(
        model="gpt-4o",
        temperature=0.1,
        max_tokens=2500,
        timeout=90.0,
        messages=[
            {"role": "system", "content": _COMPLIANCE_CHECKER_SYSTEM},
            {"role": "user", "content": (
                (f"Relevantne odredbe:\n{kontekst}\n\n" if kontekst else "")
                + f"Opis aktivnosti/poslovnog modela:\n{opis_aktivnosti}"
            )},
        ],
    )
    return (resp.choices[0].message.content or "").strip()


def whitepaper_check_sync(tekst_whitepaper: str, api_key: str) -> str:
    """Analiza whitepapera po ZDI i MiCA zahtevima. Bez RAG — samo GPT-4o."""
    from openai import OpenAI as _OAI
    client = _OAI(api_key=api_key)
    resp = client.chat.completions.create(
        model="gpt-4o",
        temperature=0.1,
        max_tokens=2500,
        timeout=90.0,
        messages=[
            {"role": "system", "content": _WHITEPAPER_CHECKER_SYSTEM},
            {"role": "user", "content": f"Whitepaper / opis projekta za analizu:\n\n{tekst_whitepaper}"},
        ],
    )
    return (resp.choices[0].message.content or "").strip()
