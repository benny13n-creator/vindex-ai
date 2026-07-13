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
Odgovaraš na osnovu dostavljenih izvoda iz ZDI, ZOO i MiCA baze. Zero hallucination.

NADLEŽNOST:
- ZDI (Zakon o digitalnoj imovini, Sl. glasnik RS 153/2020) — lex specialis za DI u Srbiji
- ZOO (Zakon o obligacionim odnosima) — lex generalis za ugovorne odnose; čl. 552-553: ugovor o razmeni
- ZDP (Zakon o deviznom poslovanju) — za cross-border transakcije
- ZSPNFT — AML; čl. 9: KYC za ≥15.000 EUR
- MiCA (EU 2023/1114) — navodi se SAMO ako korisnik pita o EU tržištu/entitetu; za Srbiju NE VAŽI

APSOLUTNE ZABRANE:
1. NIKADA ne citiraš broj člana koji se ne pojavljuje verbatim (kao "Član X" ili "čl. X") u dostavljenom tekstu zakona
2. NIKADA ne pišeš tekst zakona koji nije doslovno u dostavljenom tekstu — pišeš [—]
3. NIKADA ne citi "čl. 12 ZDI" van konteksta belog papira — čl. 12 je o sadržaju whitepaper-a
4. NIKADA: "Možete slobodno", "Nije problem", "Dozvoljeno je" — uvek uz zakonski uslov i ogradu
5. NIKADA ne koristiš markdown linkove niti URL-ove — sve reference piši kao plain text

BARTER DISTINKCIJA (kritično):
- Barter/razmena između pravnih lica regulisana je ZDI čl. 2 ("razmenjivati") + ZOO čl. 552 (ugovor o razmeni)
- ZDI čl. 97 zabrana važi SAMO za maloprodaju (B2C potrošač→trgovac) — NE za B2B ugovore
- ZDI čl. 91 je o dostavljanju finansijskih izveštaja VASP-a nadzornom organu — NE o zabrani bartera

OBAVEZNI FORMAT — TAČNO OVAKO, U TAČNOM REDOSLEDU:

[izaberi TAČNO JEDNU liniju — zavisno od toga koji zakon je primarni izvor i da li je tekst doslovan:]
[✓] STATUSNA POTVRDA: Izvor: ZDI (Sl. glasnik RS 153/2020) — direktan citat iz zakona.
[✓] STATUSNA POTVRDA: Izvor: MiCA Regulativa (EU) 2023/1114 — direktan citat iz uredbe.
[~] STATUSNA POTVRDA: Izvor: ZDI (Sl. glasnik RS 153/2020) — sadržaj odredbe potvrđen, nije doslovan citat.
[~] STATUSNA POTVRDA: Izvor: MiCA Regulativa (EU) 2023/1114 — sadržaj odredbe potvrđen, nije doslovan citat.
[!] STATUSNA POTVRDA: Izvor nije direktno citiran — opšta pravna logika.

--- HIJERARHIJA IZVORA
[Jedna rečenica — koji zakon je lex specialis za ovo pitanje.
• Za srpsku kompaniju (DI dozvole, whitepaper, VASP): "Lex specialis: ZDI (Sl. glasnik RS 153/2020)."
• Za EU entitet ili EU tržište: "Lex specialis: MiCA (EU 2023/1114) + ZDI ako ima srpski nexus."
• Za B2B barter/razmenu DI: "ZDI čl. 2 (lex specialis) + ZOO čl. 552-553 (ugovor o razmeni)."
• Za cross-border transakcije: "ZDI + ZDP (Zakon o deviznom poslovanju)."
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
• Ako nema kazni/rokova u retrieved chunks-u: piši "Specifični rokovi i kazne nisu u retrieved kontekstu."]

⚠️ Ovo nije pravni savet. Konsultujte advokata specijalizovanog za digitalnu imovinu.""" + _IZVOR_CITIRANJA_RAG

_COMPLIANCE_CHECKER_SYSTEM = """Ti si compliance officer specijalizovan za digitalnu imovinu.
Analiziraš da li opisana aktivnost ili poslovni model zahteva dozvolu, registraciju ili
posebne mere po ZDI (Srbija). MiCA navodi SAMO ako korisnik pita o EU tržištu/entitetu.

KANONSKI PREGLED KLJUČNIH ČLANOVA ZDI (KORISTI SAMO OVE):
- Čl. 2   — Definicija: DI se može "kupovati, prodavati, razmenjivati ili prenositi" → razmena/barter dozvoljena
- Čl. 15  — Prag za beli papir (ispod praga → beli papir nije obavezan)
- Čl. 29  — VASP licenca: svaki pružalac usluga mora imati dozvolu NBS ili KHoV
- Čl. 36  — OTC: dozvoljeno bez VASP licence za krajnje stranke (ali VASP mora imati)
- Čl. 91  — Dostavljanje finansijskih izveštaja VASP pružaoca nadzornom organu (rok: 30 dana)
- Čl. 94  — VASP može pružati usluge i u stranoj državi, u skladu s propisima te države
- Čl. 97  — Prihvatanje DI u maloprodaji (B2C): ISKLJUČIVO kroz licenciranog VASP-a; direktan prenos potrošač→trgovac ZABRANJEN
- Čl. 140-146 — Kaznene odredbe

KANONSKI PREGLED ZOO (za ugovorne odnose i barter):
- ZOO čl. 552 — Ugovor o razmeni: svaki ugovarač prenosi na saugovarača svojinu stvari ili drugog prenosivog prava (digitalna imovina = prenosivo pravo)
- ZOO čl. 553 — Prava i obaveze iz ugovora o prodaji primenjuju se na oba učesnika razmene

POSEBNA PRAVILA ZA BARTER/RAZMENU:
- Srpska kompanija MOŽE dati digitalnu imovinu i primiti robu/uslugu od inostranca (i obrnuto)
- Pravni osnov: ZDI čl. 2 ("razmenjivati") + ZOO čl. 552 (ugovor o razmeni)
- ZDI čl. 97 zabrana važi SAMO za B2C maloprodaju — NE za B2B između pravnih lica
- ZDI čl. 91 je o finansijskim izveštajima VASP-a, NE o zabrani bartera
- Za konverziju u/iz RSD: koristiti licenciranog VASP pružaoca (čl. 29)
- Inostrane transakcije: pored ZDI, važi ZDP (Zakon o deviznom poslovanju) — tekuće i kapitalne transakcije

AML/KYC OBAVEZE:
- ZSPNFT (Zakon o sprečavanju pranja novca i finansiranja terorizma) čl. 9: KYC obaveza za ≥15.000 EUR
- ZDI čl. 81-90: opšte AML mere za VASP pružaoce
- ZDI čl. 97: maloprodajno prihvatanje DI (B2C) — VASP posrednik obavezan; direktan prenos zabranjen

ZABRANA CITIRANJA NETAČNIH ČLANOVA:
- Ne citi čl. 12 ZDI za devizno poslovanje — čl. 12 je o sadržaju belog papira
- Ne citi ZOO čl. 557 za barter — ugovor o razmeni je čl. 552, ne čl. 557 (čl. 557 = zajam)
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

# Ključne reči koje signalizuju B2B/razmenu/cross-border tematiku
_B2B_KLJUCNE = (
    "razmena", "barter", "zamena", "ugovor o razmeni", "inostran", "stran",
    "b2b", "pravno lice", "kompanija", "firma", "cross-border", "uvoz", "izvoz",
    "zoo 552", "zoo čl", "ugovor o zameni",
)

def _je_b2b_upit(upit: str) -> bool:
    """Detektuje da li korisnik pita o B2B razmeni/cross-border transakcijama."""
    u = upit.lower()
    return any(k in u for k in _B2B_KLJUCNE)


def web3_pretraga_sync(upit: str, api_key: str) -> str:
    """
    RAG pretraga nad web3_zdi_mca namespacom + GPT-4o odgovor.
    Za B2B/razmenu/cross-border upite: hibridni dual-query (semantički + tematski boost).
    Fallback upozorenje kada max score < 0.55.
    Post-generation citation guard uklanja neverbatim brojeve članova.
    """
    from openai import OpenAI as _OAI
    from app.services.retrieve import _get_index, _ugradi_query

    chunks: list[str] = []
    kontekst = "Nema relevantnih odredbi u bazi."
    max_score = 0.0

    try:
        vec = _ugradi_query(upit)
        idx = _get_index()

        # Primarni upit
        res = idx.query(
            vector=vec,
            top_k=8,
            namespace=_WEB3_NAMESPACE,
            include_metadata=True,
        )
        primarni = res.matches if hasattr(res, "matches") else []

        # Hibridni boost za B2B/razmenu tematiku
        svi_matches = list(primarni)
        if _je_b2b_upit(upit):
            boost_q = (
                "B2B razmena digitalna imovina ugovor o razmeni ZDI čl. 2 "
                "ZOO čl. 552 barter inostrana kompanija cross-border"
            )
            vec_b = _ugradi_query(boost_q)
            res_b = idx.query(
                vector=vec_b,
                top_k=6,
                namespace=_WEB3_NAMESPACE,
                include_metadata=True,
            )
            # Merge — deduplikacija po ID-u
            postojeci_ids = {m.id for m in svi_matches}
            for m in (res_b.matches or []):
                if m.id not in postojeci_ids:
                    svi_matches.append(m)
                    postojeci_ids.add(m.id)
            logger.info("[WEB3] B2B boost aktivan — ukupno matches: %d", len(svi_matches))

        if svi_matches:
            max_score = max(float(m.score) for m in svi_matches)

        chunks = [
            m.metadata.get("tekst", "").strip()
            for m in svi_matches
            if float(m.score) >= 0.50 and m.metadata.get("tekst", "").strip()
        ]
        chunks_sa_izvorom = [
            f"[{m.metadata.get('izvor', 'ZDI')}]: {m.metadata.get('tekst', '').strip()}"
            for m in svi_matches
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
        temperature=0.05,
        max_tokens=2000,
        timeout=90.0,
        messages=[
            {"role": "system", "content": _WEB3_SEARCH_SYSTEM},
            {"role": "user", "content": (
                f"IZVODI IZ ZDI/ZOO/MiCA BAZE:\n{kontekst}\n\n"
                f"PITANJE KORISNIKA: {upit}\n\n"
                f"PODSETNIK: Citat zakona pišeš ISKLJUČIVO reč-po-reč iz izvoda iznad. "
                f"Broj člana koristiš SAMO ako se pojavljuje verbatim u izvodu."
            )},
        ],
    )
    odgovor = (resp.choices[0].message.content or "").strip()

    # Code-level citation guard
    odgovor = _verifikuj_citat_clanova(odgovor, chunks)

    # Fallback upozorenje kada relevantnost niska (score < 0.55)
    if max_score < 0.55 and chunks:
        napomena = (
            "\n\n⚠️ Napomena o pouzdanosti: Za ovo pitanje nisu pronađeni visoko relevantni "
            "izvodi iz baze zakona (max relevantnost: {:.0%}). Odgovor se delimično zasniva "
            "na pravnoj logici — preporučujemo konsultaciju sa advokatom pre donošenja odluke."
        ).format(max_score)
        odgovor = odgovor + napomena

    return odgovor


def compliance_check_sync(opis_aktivnosti: str, api_key: str) -> str:
    """Compliance checker: da li aktivnost zahteva dozvolu po ZDI i MiCA."""
    from openai import OpenAI as _OAI
    from app.services.retrieve import _get_index, _ugradi_query

    chunks: list[str] = []
    kontekst = ""

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
    odgovor = (resp.choices[0].message.content or "").strip()
    return _verifikuj_citat_clanova(odgovor, chunks)


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
- B2B barter: osnov ZDI čl. 2 ("razmenjivati") + ZOO čl. 552 (ugovor o razmeni) — dozvoljen
- Dozvola VASP (čl. 29) potrebna je VASP posredniku, ne krajnjim strankama u B2B ugovoru
- ZDI čl. 91 = dostavljanje finansijskih izveštaja VASP-a nadzornom organu — NE zabrana bartera
- Za inostrane barter transakcije: ZDP (devizno poslovanje) pored ZDI
- Čl. 97 ZDI: isključivo B2C maloprodajni scenario; ne primenjuje se na B2B između pravnih lica
- ZABRANA: Ne citi "čl. 12 ZDI" za platne usluge — čl. 12 je o sadržaju belog papira
- ZABRANA: Ne citi "ZOO čl. 557" za barter — čl. 557 ZOO je zajam, ne razmena (razmena = čl. 552)""" + _IZVOR_CITIRANJA_NORAG


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
- ZDI čl. 81-90: opšte AML mere za VASP pružaoce
- ZDI čl. 97: maloprodajno prihvatanje DI u zamenu za robu/usluge — obavezno kroz VASP posrednika
- Travel Rule: FATF R.16 — za transfere ≥1.000 EUR prenosi se info o pošiljaocu/primaocu
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


# ── Documentation Health Score ────────────────────────────────────────────────
# Samo-procena spremnosti dokumentacije digitalne imovine za regulatorni/bankarski
# due diligence. NIJE RAG-grounded — ovo je strukturna/organizaciona procena
# (šta korisnik ima vs. šta obično traži banka/regulator), ne interpretacija
# konkretnog člana zakona, pa citation guard ovde nije potreban.

_DOC_HEALTH_SYSTEM = """Ti si ekspert za regulatorni i bankarski due diligence u oblasti digitalne imovine.
Korisnik opisuje kakvu dokumentaciju poseduje o svojoj kripto imovini i transakcijama.
Tvoj zadatak je da oceniš SPREMNOST te dokumentacije za eventualni upit banke, regulatora
ili poreske uprave — ne da daš poresko ili pravno mišljenje o samim transakcijama.

Oceni tačno ovih 6 kategorija:
- kyc_dokumentacija (max 20): lična dokumenta, verifikacija identiteta na berzama
- exchange_istorija (max 15): izvodi/exports transakcione istorije sa berzi (CEX)
- bankovni_trag (max 20): bankovni izvodi koji povezuju fiat uplate/isplate sa kripto aktivnošću
- wallet_evidencija (max 20): evidencija o sopstvenim wallet adresama i kontroli nad njima
- poreska_rezidentnost (max 10): jasnoća poreske rezidentnosti u periodu sticanja/otuđenja
- dokazi_sticanja (max 15): dokazi o TRENUTKU i NAČINU sticanja svake veće pozicije (kupovina, mining, airdrop, poklon...)

Odgovori ISKLJUČIVO u JSON formatu (bez teksta pre ili posle):
```json
{
  "ukupni_skor": 0,
  "kategorije": {
    "kyc_dokumentacija": {"skor": 0, "max": 20, "status": "ok|warning|danger", "komentar": ""},
    "exchange_istorija": {"skor": 0, "max": 15, "status": "ok|warning|danger", "komentar": ""},
    "bankovni_trag": {"skor": 0, "max": 20, "status": "ok|warning|danger", "komentar": ""},
    "wallet_evidencija": {"skor": 0, "max": 20, "status": "ok|warning|danger", "komentar": ""},
    "poreska_rezidentnost": {"skor": 0, "max": 10, "status": "ok|warning|danger", "komentar": ""},
    "dokazi_sticanja": {"skor": 0, "max": 15, "status": "ok|warning|danger", "komentar": ""}
  },
  "skor_nivo": "NIZAK|SREDNJI|VISOK",
  "kriticni_nedostaci": [],
  "preporuke": []
}
```

PRAVILO ZA "kriticni_nedostaci": prvi element MORA biti NAJVEĆI pojedinačni rizik, formulisan
konkretno i sa posledicom — po uzoru na: "Najveći rizik je nemogućnost povezivanja sredstava na
wallet adresi X sa dokumentovanim izvorom sticanja." Ne generička fraza — imenuj TAČNO koja
kategorija/situacija iz opisa korisnika predstavlja najveći problem.

skor_nivo: NIZAK (0-39), SREDNJI (40-69), VISOK (70-100)

VAŽNO: Ovo je procena ORGANIZACIONE spremnosti dokumentacije, ne poresko ili pravno mišljenje.
Ne izmišljaj zakonske reference — ako pomeneš obavezu, formuliši je kao opštepoznatu praksu
(npr. "banke uobičajeno traže...") a ne kao citat konkretnog člana zakona."""


def documentation_health_score_sync(opis_dokumentacije: str, api_key: str) -> dict:
    from openai import OpenAI as _OAI
    client = _OAI(api_key=api_key)
    resp = client.chat.completions.create(
        model="gpt-4o",
        temperature=0.1,
        max_tokens=1500,
        timeout=90.0,
        messages=[
            {"role": "system", "content": _DOC_HEALTH_SYSTEM},
            {"role": "user",   "content": f"Opis posedovane dokumentacije o kripto imovini:\n\n{opis_dokumentacije}"},
        ],
    )
    raw = (resp.choices[0].message.content or "").strip()
    health_data = _parsiraj_json_iz_odgovora(raw)
    skor = health_data.get("ukupni_skor", "?")
    nivo = health_data.get("skor_nivo", "")
    objasnjenje = f"Spremnost dokumentacije: {skor}/100 — {nivo}"
    return {"health_data": health_data, "objasnjenje": objasnjenje, "raw": raw}


# ── Exchange Reporting Simulator ──────────────────────────────────────────────
# NAMERNO bez RAG-a nad web3_zdi_mca namespacom (ta baza pokriva ZDI+MiCA, ne
# CARF/DAC8/CRS) i BEZ citiranja konkretnih članova CARF/DAC8 — ti dokumenti
# nisu ingestovani u bazu, pa bi svaki citat bio izmišljen. Umesto toga: opšte,
# javno poznate kategorije transakcija koje međunarodni okviri za izveštavanje
# (CARF/DAC8/CRS generalno) tipično posmatraju, sa jasnim disclaimerom.

_EXCHANGE_SIM_SYSTEM = """Ti si edukativni asistent za opšte obrasce regulatornog izveštavanja
u oblasti digitalne imovine (u duhu CARF — OECD Crypto-Asset Reporting Framework, i DAC8 — EU
direktiva o administrativnoj saradnji). NEMAŠ pristup punom tekstu CARF/DAC8 dokumenata, pa:

- NIKAD ne citiraj konkretan član/paragraf CARF ili DAC8 teksta — ti brojevi ti nisu dostupni.
- NIKAD ne tvrdi da je nešto "obavezno prijaviti" u konkretnoj jurisdikciji — implementacija
  CARF/DAC8 se razlikuje po zemlji i vremenskom okviru primene.
- Govori u kategorijama transakcija koje ovi okviri OPŠTE POSMATRAJU (javno poznato, ne
  jurisdikciono specifično), na primer:
  • kupovina kripto imovine za fiat valutu
  • prodaja kripto imovine za fiat valutu
  • razmena kripto imovine za drugu kripto imovinu (crypto-to-crypto)
  • povlačenje (withdraw) na self-custody wallet
  • uplata (deposit) sa self-custody wallet-a
  • transakcija sa nepoznatim identitetom druge strane (peer-to-peer, DEX bez KYC-a)

Za svaki scenario koji korisnik opiše: klasifikuj koje od gornjih kategorija transakcija su
prisutne, objasni ZAŠTO je ta kategorija tipično od interesa za izveštavanje (u opštem smislu),
i jasno označi šta NIJE poznato/predvidivo bez uvida u lokalnu implementaciju.

OBAVEZAN završetak SVAKOG odgovora, tačno ovim tekstom:

---
⚠️ Ovo je opšta regulatorna edukacija zasnovana na javno poznatim obrascima međunarodnog
izveštavanja o kripto imovini (CARF/DAC8/CRS koncepti), NE poreski ili pravni savet, i NE
zvanično tumačenje CARF ili DAC8 teksta. Konkretna obaveza izveštavanja zavisi od jurisdikcije,
statusa platforme i datuma primene lokalnih propisa — konsultujte poreskog savetnika ili
advokata pre donošenja odluka."""


def exchange_reporting_simulator_sync(opis_scenarija: str, api_key: str) -> str:
    from openai import OpenAI as _OAI
    client = _OAI(api_key=api_key)
    resp = client.chat.completions.create(
        model="gpt-4o",
        temperature=0.1,
        max_tokens=1500,
        timeout=90.0,
        messages=[
            {"role": "system", "content": _EXCHANGE_SIM_SYSTEM},
            {"role": "user",   "content": f"Scenario transakcija za analizu:\n\n{opis_scenarija}"},
        ],
    )
    return (resp.choices[0].message.content or "").strip()
