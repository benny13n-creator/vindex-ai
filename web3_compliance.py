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

# ── Citiranje — zajednička pravila ────────────────────────────────────────────

# Za RAG funkcije (compliance_check): broj člana samo ako verbatim u retrieved chunkovima
_IZVOR_CITIRANJA_RAG = """
IZVOR CITIRANJA (STROGO OBAVEZNO):
- Svaki pravni stav mora imati referencu u formatu: [ZDI čl. X] ili [ZSPNFT čl. X]
- Broj člana citiraj ISKLJUČIVO ako se taj broj pojavljuje verbatim u retrieved chunk-u koji ti je dostupljen
- Ako broj člana NIJE eksplicitno u retrieved chunk-u: piši "ZDI [opis odredbe]" — BEZ broja
- Zabranjen je inference broja člana iz konteksta, pozicije ili logičkog redosleda
- Primer ispravno: "[ZDI čl. 91]" jer chunk sadrži "Član 91"
- Primer pogrešno: "[ZDI čl. 97]" ako chunk ne sadrži eksplicitno "97" ili "Član 97"
"""

# Za non-RAG funkcije: broj samo iz kanonskog pregleda ugrađenog u prompt
_IZVOR_CITIRANJA_NORAG = """
IZVOR CITIRANJA (STROGO OBAVEZNO):
- Svaki pravni stav mora imati referencu u formatu: [ZDI čl. X] ili [ZSPNFT čl. X]
- Broj člana citiraj ISKLJUČIVO iz kanonskog pregleda definisanog u ovom promptu
- Ako tema nije pokrivena kanonskim pregledom: piši samo naziv zakona (npr. "po ZDI") — BEZ broja
- Zabranjen je inference broja člana iz konteksta, pozicije ili logičkog redosleda
"""

# ── Code-level citation verifier ──────────────────────────────────────────────

_LAWS = r'(?:ZDI|ZSPNFT|ZOO|ZDP|ZR|KZ|ZPDG|ZZPL|MiCA)'
_CL   = r'(?:čl\.|član[a-z]*|art\.?|member)'

def _verifikuj_citat_clanova(odgovor: str, chunks: list) -> str:
    """
    Code-level citation guard — runs AFTER generation.

    Catches ALL orderings:
      • "ZDI čl. 97"          (law first)
      • "čl. 97 ZDI"          (article first)
      • "člana 97 ZDI"        (genitive form)
      • "čl. 97"              (standalone — ambiguous, still checked)

    Action when NOT in chunks: REMOVES the article number entirely,
    replaces with "[br. nije u bazi]" — the number must not appear in output.
    """
    import re as _re
    if not chunks or not odgovor:
        return odgovor

    chunk_combined = " ".join(chunks).lower()

    # Pattern A: "ZDI čl. 97"  →  groups: (law_prefix, number)
    pat_a = _re.compile(
        r'(' + _LAWS + r'\s+' + _CL + r'\s*)(\d+(?:[-–]\d+)?)',
        _re.IGNORECASE,
    )
    # Pattern B: "čl. 97 ZDI"  →  groups: (cl_prefix, number, law_suffix)
    pat_b = _re.compile(
        r'(' + _CL + r'\s*)(\d+(?:[-–]\d+)?)(\s+' + _LAWS + r')',
        _re.IGNORECASE,
    )

    flagged: list[str] = []

    def _num_in_chunks(num: str) -> bool:
        base = num.split("–")[0].split("-")[0]
        return bool(_re.search(r'\b' + _re.escape(base) + r'\b', chunk_combined))

    def _check_a(m: _re.Match) -> str:
        num  = m.group(2)
        full = m.group(0)
        if _num_in_chunks(num):
            return full
        flagged.append(full)
        # Remove number — keep law+čl. prefix, replace number with [br. nije u bazi]
        return m.group(1) + "[br. nije u bazi]"

    def _check_b(m: _re.Match) -> str:
        num  = m.group(2)
        full = m.group(0)
        if _num_in_chunks(num):
            return full
        flagged.append(full)
        # Remove number — keep čl. prefix and law suffix
        return m.group(1) + "[br. nije u bazi]" + m.group(3)

    # Apply B first (more specific — prevents A from partially matching)
    result = pat_b.sub(_check_b, odgovor)
    result = pat_a.sub(_check_a, result)

    if flagged:
        logger.warning(
            "[WEB3_CITAT_GUARD] Uklonjene halucinacije: %s",
            ", ".join(flagged),
        )
    return result


# ── System promptovi ──────────────────────────────────────────────────────────

_WEB3_SEARCH_SYSTEM = """Ti si Vindex AI — specijalizovani pravni sistem za digitalnu imovinu u Srbiji.
Odgovaraš ISKLJUČIVO na osnovu dostavljenih retrieved chunk-ova iz ZDI/MiCA baze. Zero hallucination.

NADLEŽNOST:
- ZDI (Zakon o digitalnoj imovini, Sl. glasnik RS 153/2020) — lex specialis za Srbiju
- MiCA (EU 2023/1114) — navodi se SAMO ako korisnik pita o EU tržištu/entitetu; za Srbiju NE VAŽI
- ZOO (Zakon o obligacionim odnosima) — lex generalis za ugovorne odnose
- ZDP (Zakon o deviznom poslovanju) — za cross-border transakcije
- ZSPNFT — AML; čl. 9: KYC za ≥15.000 EUR

APSOLUTNE ZABRANE:
1. NIKADA ne citiraš broj člana koji se ne pojavljuje verbatim (kao "Član X" ili "čl. X") u retrieved chunk-u
2. NIKADA ne pišeš tekst zakona koji nije doslovno u retrieved chunk-u — pišeš [—]
3. NIKADA ne citi "čl. 97 ZDI" za teme prihvatanja imovine — taj broj je iz AML sekcije, ne o maloprodaji
4. NIKADA ne citi "čl. 12 ZDI" van konteksta belog papira — čl. 12 je o sadržaju whitepaper-a
5. NIKADA: "Možete slobodno", "Nije problem", "Dozvoljeno je" — uvek uz zakonski uslov i ogradu

BARTER DISTINKCIJA (kritično):
- ZDI čl. 91 zabranjuje SAMO "zakonsko sredstvo plaćanja" (legal tender) — NE zabranjuje barter
- Dobrovoljni barter je regulisan ZDI čl. 2 + ZOO čl. 557-570 (ugovor o razmeni)
- Ovo pišeš SAMO ako je čl. 2 ili čl. 91 u retrieved chunk-u; inače pišeš [—] za citat

OBAVEZNI FORMAT — TAČNO OVAKO, U TAČNOM REDOSLEDU:

[izaberi TAČNO JEDNU liniju:]
[✓] STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u retrieved chunk-u ZDI/MiCA baze.
[~] STATUSNA POTVRDA: Parafrazirano — sadržaj odredbe potvrđen, nije doslovan citat iz retrieved chunk-a.
[!] STATUSNA POTVRDA: Opšta pravna logika — nema direktnog člana u retrieved chunk-u za ovo pitanje.

--- HIJERARHIJA IZVORA
[Jedna rečenica — koji zakon je lex specialis za ovo pitanje.
• Za srpsku kompaniju: "Lex specialis: ZDI (Sl. glasnik RS 153/2020) — matični propis za digitalnu imovinu u Srbiji."
• Za EU entitet ili EU tržište: "Lex specialis: MiCA (EU 2023/1114) + ZDI ako ima srpski nexus."
• Za barter/ugovor: "Lex specialis: ZDI čl. 2 + ZOO čl. 557 — ugovor o razmeni digitalne imovine."
NIKADA: "Opšti propis: ZOO" — ZOO je lex generalis, ne opšti propis]

--- PRAVNI ZAKLJUČAK
[2 rečenice maksimum.
(1) Direktan odgovor na pitanje — uz OBAVEZNU ogradu: "Uz ispunjenje zakonskih uslova", "Po dostupnim informacijama".
(2) Šta konkretno uslovljava ili ograničava — licenca, prag, jurisdikcija.
ZABRANJENO: "Imate pravo", "Garantovano je", "Slobodno možete" bez zakonskog uslova.]

--- CITAT ZAKONA [RAG]
[DOSLOVNI tekst iz retrieved chunk-a — preuzmi reč po reč, BEZ izmena.
Ako tačan tekst člana NIJE u retrieved chunk-u → piši samo: [—]
NIKADA ne generišeš sopstveni tekst zakona. NIKADA ne pišeš "Tekst nije dostupan".]

--- PRAVNI OSNOV
[Naziv zakona i broj člana.
ISKLJUČIVO ako se broj pojavljuje verbatim (kao "Član X" ili "čl. X") u retrieved chunk-u.
Ako broj NIJE verbatim u chunk-u: piši "ZDI [opis odredbe]" — BEZ broja.
Primer ispravno: "ZDI čl. 2 — digitalna imovina zamenjiva (barter dozvoljen)"
Primer pogrešno: "ZDI čl. 97 — prihvatanje u maloprodaji" ako "97" nije u chunk-u]

--- COMPLIANCE KORACI
[Konkretan redosled koraka. SAMO ako su direktno relevantni za pitanje — inače IZOSTAVI sekciju.
Svaki korak mora imati zakonski osnov iz retrieved chunk-a ili kanonskog pregleda.]

--- RIZICI I ROKOVI
[Kazne, rok za registraciju/licencu, prag za KYC.
STROGO PRAVILO ZA OVU SEKCIJU — identično sa svim ostalim sekcijama:
• Broj člana navoditi ISKLJUČIVO ako se pojavljuje verbatim u retrieved chunk-u (kao "Član X" ili "čl. X")
• Ako broj NIJE u chunk-u: "• ZDI [opis rizika/kazne]" — BEZ broja
• Primer ispravno: "• ZDI čl. 140 — [kazna]" ako je "140" doslovno u chunk-u
• Primer pogrešno: "• ZDI čl. 97 — ..." ako "97" NIJE u chunk-u
• Ako nema kazni/rokova u retrieved chunks-u: piši "Specifični rokovi i kazne nisu u retrieved kontekstu."
NIKADA ne navodi čl. 97 ZDI za ovu temu — taj broj nije relevantan za barter/razmenu.]

⚠️ Ovo nije pravni savet. Konsultujte advokata specijalizovanog za digitalnu imovinu.""" + _IZVOR_CITIRANJA_RAG

_COMPLIANCE_CHECKER_SYSTEM = """Ti si compliance officer specijalizovan za digitalnu imovinu.
Analiziraš da li opisana aktivnost ili poslovni model zahteva dozvolu, registraciju ili
posebne mere po ZDI (Srbija). MiCA navodi SAMO ako korisnik pita o EU tržištu/entitetu.

KANONSKI PREGLED KLJUČNIH ČLANOVA ZDI (KORISTI SAMO OVE):
- Čl. 2   — Definicija: "zamenjivati" → barter dozvoljen; razmena digitalne imovine za robu = legalno
- Čl. 15  — Prag za beli papir (ispod praga → beli papir nije obavezan)
- Čl. 29  — VASP licenca: svaki pružalac usluga mora imati dozvolu NBS ili KHoV
- Čl. 36  — OTC: dozvoljeno bez VASP licence za krajnje stranke (ali VASP mora imati)
- Čl. 91  — Zabrana ZAKONSKOG SREDSTVA PLAĆANJA — NE zabranjuje barter/dobrovoljnu razmenu
- Čl. 140-146 — Kaznene odredbe

POSEBNA PRAVILA ZA BARTER/RAZMENU:
- Srpska kompanija MOŽE dati digitalnu imovinu i primiti robu/uslugu od inostranca (i obrnuto)
- Pravni osnov: ZDI čl. 2 + ZOO čl. 557-570 (ugovor o razmeni)
- Zabrana iz čl. 91 se odnosi na "legal tender", NE na barter
- Za konverziju u/iz RSD: koristiti licenciranog VASP pružaoca (čl. 29)
- Inostrane transakcije: pored ZDI, važi ZDP (Zakon o deviznom poslovanju) — tekuće i kapitalne transakcije

AML/KYC OBAVEZE:
- ZSPNFT (Zakon o sprečavanju pranja novca i finansiranja terorizma) čl. 9: KYC obaveza za ≥15.000 EUR
- ZDI čl. 81-90: opšte AML mere za VASP pružaoce
- NE postoji "čl. 97 ZDI" koji reguliše maloprodajno prihvatanje — ne citi taj broj

ZABRANA CITIRANJA IZMIŠLJENIH ČLANOVA:
- Ne citi čl. 97 ZDI za prihvatanje imovine — to je kraj AML sekcije, ne odnosi se na maloprodaju
- Ne citi čl. 12 ZDI za devizno poslovanje — čl. 12 je o sadržaju belog papira
- Ako nisi siguran koji tačan član važi — navedi samo zakon (npr. "po ZDI"), bez broja člana

Struktura odgovora (obavezna):
1. KLASIFIKACIJA DIGITALNE IMOVINE
   - Po ZDI: Virtuelna valuta / Digitalni token / Hibridni / Nije digitalna imovina

2. NADLEŽNI ORGAN (Srbija)
   - NBS (za virtuelne valute) / KHoV (za digitalne tokene) / Oba / Nije primenljivo

3. DOZVOLA/REGISTRACIJA POTREBNA?
   - Po ZDI: DA / NE / DELIMIČNO — navedi konkretan čl. ZDI iz kanonskog pregleda

4. BELI PAPIR (WHITEPAPER) POTREBAN?
   - Po ZDI: DA / NE (sa pragovima iz čl. 15 ZDI)

5. AML/KYC OBAVEZE
   - ZSPNFT čl. 9: KYC za ≥15.000 EUR; ZDI čl. 81-90 za VASP pružaoce

6. RIZICI I KAZNE
   - Šta se dešava ako se ne uskladi (čl. 140-146 ZDI)

7. PREPORUČENE AKCIJE (konkretan redosled koraka)

Na kraju: UKUPNA PROCENA RIZIKA: NIZAK / SREDNJI / VISOK""" + _IZVOR_CITIRANJA_RAG

_WHITEPAPER_CHECKER_SYSTEM = """Ti si pravni ekspert za bele papire (whitepaper) digitalne imovine.
Analiziraš da li dostavljeni whitepaper (ili opis projekta) ispunjava zahteve
ZDI čl. 12-19 (Srbija, isključivo o belom papiru/white paper) i MiCA čl. 6 (EU, samo za EU entitete).

NAPOMENA: ZDI čl. 12-19 ISKLJUČIVO pokriva beli papir. Ovo nisu odredbe o platnim uslugama,
deviznom poslovanju ni barterskim transakcijama — ne navodi ih van konteksta belog papira.

Struktura odgovora (obavezna):
1. OBAVEZNI ELEMENTI KOJI POSTOJE ✓
2. OBAVEZNI ELEMENTI KOJI NEDOSTAJU ✗
   Za svaki: šta nedostaje, koji član to zahteva, predlog kako dodati
3. ZABRANJENI SADRŽAJI (obmanjujuće izjave, garantovanje prinosa)
4. PREPORUKA: SPREMAN / POTREBNE DOPUNE / ODBACITI
5. PROCENJENI ROK ODOBRAVANJA (po ZDI: KHoV/NBS ima 30 dana)""" + _IZVOR_CITIRANJA_NORAG


# ── Sync funkcije ──────────────────────────────────────────────────────────────

def web3_pretraga_sync(upit: str, api_key: str) -> str:
    """
    RAG pretraga nad web3_zdi_mca namespacom + GPT-4o odgovor.
    Output format: identičan sa 'Istraživanje zakona' (--- sekcije + STATUSNA POTVRDA).
    Post-generation citation guard: svaki broj člana koji nije u retrieved chunk-u se flaguje.
    """
    from openai import OpenAI as _OAI
    from app.services.retrieve import _get_index, _ugradi_query

    chunks: list[str] = []
    kontekst = "Nema relevantnih odredbi u bazi."
    try:
        vec = _ugradi_query(upit)
        idx = _get_index()
        res = idx.query(
            vector=vec,
            top_k=8,
            namespace=_WEB3_NAMESPACE,
            include_metadata=True,
        )
        matches = res.matches if hasattr(res, "matches") else []
        chunks = [
            m.metadata.get("tekst", "").strip()
            for m in matches
            if float(m.score) >= 0.50 and m.metadata.get("tekst", "").strip()
        ]
        chunks_sa_izvorom = [
            f"[{m.metadata.get('izvor', 'ZDI')}]: {m.metadata.get('tekst', '').strip()}"
            for m in matches
            if float(m.score) >= 0.50 and m.metadata.get("tekst", "").strip()
        ]
        if chunks_sa_izvorom:
            kontekst = "\n\n".join(chunks_sa_izvorom)
        else:
            kontekst = "Nema relevantnih odredbi u bazi — odgovor se zasniva na kanonskom pregledu."
    except Exception as e:
        logger.warning("[WEB3] Pinecone pretraga neuspešna: %s", e)
        kontekst = "Baza nije dostupna — odgovor se zasniva na opštim pravilima."
        chunks = []

    client = _OAI(api_key=api_key)
    resp = client.chat.completions.create(
        model="gpt-4o",
        temperature=0.05,   # niža temperatura = manje slobode za izmišljanje
        max_tokens=2000,
        timeout=90.0,
        messages=[
            {"role": "system", "content": _WEB3_SEARCH_SYSTEM},
            {"role": "user", "content": (
                f"RETRIEVED CHUNKS IZ ZDI/MiCA BAZE:\n{kontekst}\n\n"
                f"PITANJE KORISNIKA: {upit}\n\n"
                f"PODSETNIK: Citat zakona pišeš ISKLJUČIVO reč-po-reč iz retrieved chunks-a iznad. "
                f"Broj člana koristiš SAMO ako se pojavljuje verbatim u retrieved chunks-u."
            )},
        ],
    )
    odgovor = (resp.choices[0].message.content or "").strip()

    # Code-level citation guard — runs AFTER generation
    odgovor = _verifikuj_citat_clanova(odgovor, chunks)

    return odgovor


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

skor_nivo: NIZAK (0-39), SREDNJI (40-69), VISOK (70-100)""" + _IZVOR_CITIRANJA_NORAG


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

rizik_nivo: NIZAK (informacione aktivnosti), SREDNJI (razmena/čuvanje), VISOK (javna ponuda/CASP bez dozvole)

POSEBNA PRAVILA — BARTER I RAZMENA:
- Barter digitalne imovine za robu/uslugu: dozvola za VASP pružaoca (čl. 29), ali ne za krajnje stranke
- ZDI čl. 91 zabranjuje samo "zakonsko sredstvo plaćanja" — NE zabranjuje dobrovoljni barter
- Za inostrane barter transakcije: ZDP (devizno poslovanje) pored ZDI
- ZABRANA: Ne citi "čl. 97 ZDI" za prihvatanje imovine — taj čl. spada u kraj AML sekcije
- ZABRANA: Ne citi "čl. 12 ZDI" za platne usluge — čl. 12 je o sadržaju belog papira""" + _IZVOR_CITIRANJA_NORAG


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
(ZDI čl. 81-90, ZSPNFT) i međunarodnim standardima (FATF).

TAČNI AML PRAGOVI I REFERENCE:
- ZSPNFT čl. 9: KYC obaveza za transakcije ≥15.000 EUR (ili ekvivalent)
- ZSPNFT čl. 37: monitoring sumnjivih transakcija
- ZSPNFT čl. 47: prijava APML u roku od 24h
- ZDI čl. 81-90: opšte AML mere za VASP pružaoce (NE čl. 97)
- Travel Rule: FATF R.16 — za transfere ≥1.000 EUR prenosi se info o pošiljaocu/primaocu
ZABRANA: Ne navodi "čl. 97 ZDI" kao regulatora maloprodajnog prihvatanja — taj broj ne postoji u tom kontekstu.
""" + _IZVOR_CITIRANJA_NORAG + """
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
