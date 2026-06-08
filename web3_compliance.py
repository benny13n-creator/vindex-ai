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


# ── Helper: JSON ekstrakcija iz GPT odgovora ──────────────────────────────────

def _parsiraj_json_iz_odgovora(odgovor: str) -> dict:
    import json, re
    match = re.search(r"```json\s*([\s\S]*?)```", odgovor)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except Exception:
            pass
    match = re.search(r"\{[\s\S]*\}", odgovor)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            pass
    return {}


# ── MiCA Readiness Score ──────────────────────────────────────────────────────

_MICA_READINESS_SYSTEM = """Ti si ekspert za MiCA usklađenost (EU Regulation 2023/1114) i ZDI (Srbija).
Analiziraj opis kripto projekta i izračunaj MiCA Readiness Score.

Odgovori ISKLJUČIVO u JSON formatu (bez dodatnog teksta pre ili posle JSON-a):
```json
{
  "ukupni_skor": 0,
  "kategorije": {
    "whitepaper_uskladenost": {"skor": 0, "max": 20, "status": "ok|warning|danger", "komentar": ""},
    "casp_zahtevi": {"skor": 0, "max": 20, "status": "ok|warning|danger", "komentar": ""},
    "aml_kyc": {"skor": 0, "max": 20, "status": "ok|warning|danger", "komentar": ""},
    "rezerve_i_backing": {"skor": 0, "max": 20, "status": "ok|warning|danger", "komentar": ""},
    "market_abuse": {"skor": 0, "max": 20, "status": "ok|warning|danger", "komentar": ""}
  },
  "skor_nivo": "NIZAK|SREDNJI|VISOK",
  "kriticni_nedostaci": [],
  "preporuke": []
}
```

Pravila bodovanja (0-100):
- whitepaper_uskladenost: 0-20 (da li projekt ima MiCA-kompatibilan whitepaper)
- casp_zahtevi: 0-20 (autorizacija, kapital, organizacija)
- aml_kyc: 0-20 (KYC procedure, travel rule, monitoring)
- rezerve_i_backing: 0-20 (za ART/EMT — da li postoji backing; za ostale tokene — 20 automatski)
- market_abuse: 0-20 (zabrana insider trading, wash trading, pump&dump)

skor_nivo: NIZAK (0-39), SREDNJI (40-69), VISOK (70-100)"""


def mica_readiness_score_sync(tekst_projekta: str, api_key: str) -> dict:
    from openai import OpenAI as _OAI
    client = _OAI(api_key=api_key)
    resp = client.chat.completions.create(
        model="gpt-4o",
        temperature=0.1,
        max_tokens=1500,
        timeout=90.0,
        messages=[
            {"role": "system", "content": _MICA_READINESS_SYSTEM},
            {"role": "user",   "content": f"Kripto projekt za MiCA analizu:\n\n{tekst_projekta}"},
        ],
    )
    raw = (resp.choices[0].message.content or "").strip()
    score_data = _parsiraj_json_iz_odgovora(raw)
    objasnjenje = f"Ukupni skor: {score_data.get('ukupni_skor', '?')}/100 — {score_data.get('skor_nivo', '')}"
    return {"score_data": score_data, "objasnjenje": objasnjenje, "raw": raw}


# ── ZDI License Checker ───────────────────────────────────────────────────────

_ZDI_LICENSE_SYSTEM = """Ti si pravni ekspert za Zakon o digitalnoj imovini (ZDI, Sl. glasnik RS 153/2020).
Analiziraj opis aktivnosti i utvrdi koja licenca/dozvola je potrebna po ZDI.

Odgovori ISKLJUČIVO u JSON formatu:
```json
{
  "klasifikacija_imovine": "virtualna_valuta|digitalni_token|nije_digitalna_imovina|neodredjeno",
  "nadlezni_organ": "NBS|KHoV|oba|nije_primenjivo",
  "dozvola_potrebna": true,
  "tip_dozvole": "",
  "rizik_nivo": "NIZAK|SREDNJI|VISOK",
  "pravni_osnov": [],
  "obavezne_mere": [],
  "kazne_pri_kršenju": ""
}
```

Klasifikacija:
- virtualna_valuta: kriptovalute bez centralnog izdavaoca (BTC, ETH i slično) → nadležna NBS
- digitalni_token: tokeni koji predstavljaju prava (HoV tokeni, utility tokeni) → nadležna KHoV
- nije_digitalna_imovina: ne potpada pod ZDI

rizik_nivo: NIZAK (informacione aktivnosti), SREDNJI (razmena/čuvanje), VISOK (javna ponuda/CASP bez dozvole)"""


def zdi_license_checker_sync(opis_aktivnosti: str, api_key: str) -> dict:
    from openai import OpenAI as _OAI
    client = _OAI(api_key=api_key)
    resp = client.chat.completions.create(
        model="gpt-4o",
        temperature=0.1,
        max_tokens=1000,
        timeout=90.0,
        messages=[
            {"role": "system", "content": _ZDI_LICENSE_SYSTEM},
            {"role": "user",   "content": f"Aktivnost za proveru licence:\n\n{opis_aktivnosti}"},
        ],
    )
    raw = (resp.choices[0].message.content or "").strip()
    license_data = _parsiraj_json_iz_odgovora(raw)
    dozvola = "POTREBNA" if license_data.get("dozvola_potrebna") else "NIJE POTREBNA"
    organ = license_data.get("nadlezni_organ", "")
    objasnjenje = f"Dozvola: {dozvola} | Nadležni organ: {organ} | Rizik: {license_data.get('rizik_nivo', '?')}"
    return {"license_data": license_data, "objasnjenje": objasnjenje, "raw": raw}


# ── AML/KYC Auditor ───────────────────────────────────────────────────────────

_AML_AUDITOR_SYSTEM = """Ti si ekspert za AML/KYC usklađenost u oblasti digitalne imovine po srpskom pravu
(ZDI čl. 81-97, ZSPNFT) i međunarodnim standardima (FATF).

Analiziraj dostavljeni tekst AML/KYC politike i izračunaj skor usklađenosti.

Odgovori ISKLJUČIVO u JSON formatu:
```json
{
  "ukupna_uskladenost": 0,
  "kategorije": {
    "kyc_procedure": {"skor": 0, "max": 15, "status": "ok|warning|danger", "komentar": ""},
    "pep_screening": {"skor": 0, "max": 10, "status": "ok|warning|danger", "komentar": ""},
    "transakcijski_monitoring": {"skor": 0, "max": 15, "status": "ok|warning|danger", "komentar": ""},
    "travel_rule": {"skor": 0, "max": 15, "status": "ok|warning|danger", "komentar": ""},
    "izvestavanje_sumljivih": {"skor": 0, "max": 15, "status": "ok|warning|danger", "komentar": ""},
    "cuvanje_dokumentacije": {"skor": 0, "max": 10, "status": "ok|warning|danger", "komentar": ""},
    "obuka_zaposlenih": {"skor": 0, "max": 10, "status": "ok|warning|danger", "komentar": ""},
    "interna_kontrola": {"skor": 0, "max": 10, "status": "ok|warning|danger", "komentar": ""}
  },
  "uskladenost_nivo": "NIZAK|SREDNJI|VISOK",
  "kriticni_nedostaci": [],
  "preporuke": []
}
```

ukupna_uskladenost: zbir skorova svih kategorija (0-100)
uskladenost_nivo: NIZAK (0-39), SREDNJI (40-69), VISOK (70-100)"""


def aml_kyc_auditor_sync(tekst_politike: str, api_key: str) -> dict:
    from openai import OpenAI as _OAI
    client = _OAI(api_key=api_key)
    resp = client.chat.completions.create(
        model="gpt-4o",
        temperature=0.1,
        max_tokens=1500,
        timeout=90.0,
        messages=[
            {"role": "system", "content": _AML_AUDITOR_SYSTEM},
            {"role": "user",   "content": f"AML/KYC politika za audit:\n\n{tekst_politike}"},
        ],
    )
    raw = (resp.choices[0].message.content or "").strip()
    audit_data = _parsiraj_json_iz_odgovora(raw)
    skor = audit_data.get("ukupna_uskladenost", "?")
    nivo = audit_data.get("uskladenost_nivo", "")
    objasnjenje = f"AML/KYC usklađenost: {skor}/100 — {nivo}"
    return {"audit_data": audit_data, "objasnjenje": objasnjenje, "raw": raw}
