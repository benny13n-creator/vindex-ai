# -*- coding: utf-8 -*-
"""Kanonski identitet Pinecone vektora.

BETA-DATA-ID-01.

PROBLEM

`uploaded_doc/chunker.py:157` je davao `chunk_id = str(uuid.uuid4())`, a
`ingest.py` je baš to koristio kao Pinecone `id`. Posledica u tri koraka:

  1. ponovni upload istog fajla proizvodi POTPUNO nove ID-eve → duplikati,
  2. ne postoji način da se nađu svi vektori jednog dokumenta → nema brisanja,
  3. ne postoji način da se vektor veže za red u bazi → nema orphan detekcije.

Bez identiteta nema ni brisanja (`PINE-01`), ni pouzdanog ponavljanja, ni GDPR
čl. 17 nad Pinecone kopijom.

NASLEDNIK, NE IZUM

Obrazac `{stabilni_id_izvora}__chunk_{index}` je dominantan i dokazan na
**407.795 živih vektora** u namespace-u `sudska_praksa`
(`chunker_case_law.py:279`, izmereno preko `Index.list()`). Ovaj modul ga ne
zamenjuje nego dovršava: dodaje verziju sadržaja i verziju chunking šeme, bez
kojih obrazac ne razlikuje dve verzije istog dokumenta.

ISPRAVKA RANIJE TVRDNJE U OVOM FAJLU: prva verzija je navodila
`routers/law_upload.py:126` kao dokaz da obrazac radi u produkciji. Forenzički
inventar je izmerio da `law_docs` ima **0 redova**, a da su ID-evi u `zakoni_rs`
md5 iz `semantic_chunker.py:107` — dakle taj pisač nije dokaz ničega. Tvrdnja je
zamenjena merenom.

MODEL

    vector_id = {scope}__{version}__k{chunk_schema}_c{chunk_index}

  scope         — granica vlasništva i brisanja. Za dokumente predmeta to je
                  `predmet_id`; za privremene sesije `session_id`. Time dva
                  tenanta koja otpreme ISTI fajl dobijaju RAZLIČITE ID-eve, jer
                  im se scope razlikuje — v. `test_id01_isti_sadrzaj_razliciti
                  _tenanti_daju_razlicite_id`.
  version       — SHA-256 sadržaja. Isti fajl → isti ID-evi → `upsert` prepisuje
                  umesto da duplira. Izmenjen fajl → nova verzija → novi ID-evi,
                  a stara verzija ostaje jednoznačno adresabilna (RULE 9).
  chunk_schema  — verzija algoritma za deljenje. Bez nje bi promena veličine
                  chunk-a ili preklapanja tiho promenila ZNAČENJE `chunk_index`,
                  pa bi novi chunk-ovi prepisali stare kao da su isti (RULE 6 u
                  §6 mandata to izričito traži).

ŠTA OVAJ MODUL NIJE

Nije autorizacija. `version` je heš sadržaja i služi identitetu i integritetu —
nikad kao dokaz da neko sme da vidi dokument. Kanonska kapija ostaje
`api.py::get_predmet` (vlasnik ili aktivna delegacija) i
`shared/rag_acl.py`. Heš koji se poklopi između dva korisnika NE spaja njihove
podatke, jer se `scope` razlikuje.

MIGRACIJA NIJE POTREBNA

`predmet_dokumenti.content_sha256` postoji od migracije 095 i već se upisuje.
`predmet_id` postoji. Identitet se gradi iz onoga što šema već ima.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Optional

# Verzija šeme deljenja teksta. POVEĆATI kad se promeni bilo šta što menja
# granice chunk-ova (veličina, preklapanje, article-aware logika) — inače bi
# novi chunk-ovi prepisali stare pod istim ID-em, a to su različiti podaci.
CHUNK_SCHEMA_VERSION = 1

# Koliko heksadecimalnih znakova SHA-256 ulazi u ID. 32 znaka = 128 bita; unutar
# jednog `scope`-a je verovatnoća sudara zanemarljiva, a ID ostaje kratak.
_VERZIJA_DUZINA = 32

_DOZVOLJENI = re.compile(r"[^A-Za-z0-9_.\-]")
LF = chr(10)
CR = chr(13)
CRLF = CR + LF
_VISE_PRELOMA = re.compile(LF + "{3,}")


class NedovoljanIdentitet(ValueError):
    """Diže se kad vektor ne može dobiti jednoznačan identitet.

    Fail-closed po RULE 6: bez identiteta se vektor NE UPISUJE. Tiho
    preskakanje bi vratilo tačno stanje koje ovaj modul uklanja — vektor koji
    postoji, a ne zna se čiji je ni kom dokumentu pripada.
    """


def verzija_sadrzaja(sadrzaj: bytes | str) -> str:
    """SHA-256 sadržaja, skraćen na `_VERZIJA_DUZINA` heks znakova."""
    if isinstance(sadrzaj, str):
        sadrzaj = sadrzaj.encode("utf-8")
    return hashlib.sha256(sadrzaj).hexdigest()[:_VERZIJA_DUZINA]


def _ocisti(vrednost: str, ime: str) -> str:
    v = (vrednost or "").strip()
    if not v:
        raise NedovoljanIdentitet(f"{ime} je prazan — vektor se ne upisuje")
    # Pinecone ID mora biti ASCII; nedozvoljene znakove zamenjujemo, ali NE
    # praznimo — ako bi čišćenje pojelo sve, identitet nije jednoznačan.
    ocisceno = _DOZVOLJENI.sub("-", v)
    if not ocisceno.strip("-"):
        raise NedovoljanIdentitet(f"{ime} nema nijedan upotrebljiv znak")
    return ocisceno


def _normalizuj_verziju(verzija: str) -> str:
    """Uvek istih `_VERZIJA_DUZINA` znakova, bez obzira šta je pozivalac dao.

    `verzija_sadrzaja()` vraća skraćen heš, ali `ingest_session` prosleđuje pun
    64-znakovni `manifest.source_sha256`. Bez normalizacije bi ista verzija
    davala dva različita ID-a zavisno od pozivnog mesta — pa `prefiks_dokumenta`
    ne bi našao vektore koje je `canonical_vector_id` upisao, i brisanje bi tiho
    promašivalo.
    """
    return _ocisti(verzija, "verzija")[:_VERZIJA_DUZINA]


def prefiks_dokumenta(scope: str, verzija: str,
                      chunk_schema: int = CHUNK_SCHEMA_VERSION) -> str:
    """Zajednički prefiks SVIH vektora jedne verzije jednog dokumenta.

    Ovo je ono što `PINE-01` treba: `Index.list(prefix=...)` vraća tačno
    chunk-ove te verzije tog dokumenta i ničije druge, pa `delete(ids=[...])`
    postaje precizan umesto da briše ceo predmet.
    """
    return f"{_ocisti(scope, 'scope')}__{_normalizuj_verziju(verzija)}__k{int(chunk_schema)}_c"


def canonical_vector_id(
    scope: str,
    verzija: str,
    chunk_index: int,
    chunk_schema: int = CHUNK_SCHEMA_VERSION,
) -> str:
    """Deterministički ID jednog vektora.

    Isti ulaz uvek daje isti izlaz — nezavisno od procesa, vremena i broja
    pokušaja. To je jedini razlog zbog kog ponovni ingest ne duplira.
    """
    if chunk_index is None or int(chunk_index) < 0:
        raise NedovoljanIdentitet(f"chunk_index je neispravan: {chunk_index!r}")
    return f"{prefiks_dokumenta(scope, verzija, chunk_schema)}{int(chunk_index)}"


def metapodaci_identiteta(
    scope: str,
    verzija: str,
    chunk_index: int,
    predmet_id: Optional[str] = None,
    document_id: Optional[str] = None,
    chunk_schema: int = CHUNK_SCHEMA_VERSION,
) -> dict:
    """Minimalan skup metapodataka potreban za brisanje, audit i orphan detekciju.

    NAMERNO ne sadrži ime klijenta, e-mail, JMBG, adresu ni tekst dokumenta
    (§7 mandata) — ovo je identitet, ne sadržaj. Tekst se u metapodatke upisuje
    na drugom mestu i iz drugog razloga; ovde mu nije mesto.

    `document_id` je opcion jer ga jedan deo pisaca dobija tek POSLE upsert-a.
    Kad ga ima, upisuje se i time se zatvara veza vektor → red u bazi.
    """
    m = {
        "vx_scope": _ocisti(scope, "scope"),
        "vx_verzija": _normalizuj_verziju(verzija),
        "vx_chunk_schema": int(chunk_schema),
        "chunk_index": int(chunk_index),
    }
    if predmet_id:
        m["predmet_id"] = predmet_id
    if document_id:
        m["vx_document_id"] = document_id
    return m


# ─── KANONSKI IDENTITET SADRŽAJA (BETA-DATA-ID-02) ──────────────────────────
#
# ODLUKA: identitet sadržaja dokumenta je SHA-256 NJEGOVOG IZVUČENOG TEKSTA,
# uz eksplicitnu verziju ekstrakcije. NIJE heš bajtova fajla.
#
# ZAŠTO NE BAJTOVI — merena činjenica, ne preferencija:
# `routers/smart_intake.py` deli JEDAN otpremljen fajl na N dokumenata
# (`for idx, doc_entry in enumerate(documents)`, :1314), a `raw_bytes` dohvata
# JEDNOM pre petlje (:1273). Heš bajtova je zato isti za svih N. Izmereno:
#
#     dokument 1 chunk0 = pred-A__8f4bd21e...__k1_c0
#     dokument 2 chunk0 = pred-A__8f4bd21e...__k1_c0     ← ISTI ID
#
# Drugi dokument bi `upsert`-om PREPISAO prvi. Bajtovi identifikuju UPLOAD,
# ne DOKUMENT.
#
# ČETIRI SEMANTIKE SE NE SMEJU MEŠATI (§4 misije):
#   upload/job identitet  = heš bajtova   (`smart_intake.py:155`, idempotencija
#                                          posla — ostaje bajtovi, i to je tačno)
#   identitet dokumenta   = ovaj modul    (heš teksta + verzija ekstrakcije)
#   identitet verzije     = isto          (izmenjen tekst → nova verzija)
#   identitet vektora     = scope + verzija + chunk
#
# ZAŠTO VERZIJA EKSTRAKCIJE (§10):
# tekst zavisi od parsera i OCR-a. Bez eksplicitne verzije bi nadogradnja
# `pytesseract`-a tiho promenila identitet svakog skeniranog dokumenta —
# „isti dokument danas → heš A, sutra → heš B". Sa njom je promena vidljiva i
# namerna: nova verzija ekstrakcije JESTE nova reprezentacija sadržaja.
EXTRACTION_VERSION = 1


def kanonski_tekst(tekst: str) -> str:
    """Jedan i jedini oblik teksta iz kog se racuna identitet dokumenta.

    BETA-DATA-PINE-02 §4. Bez ove funkcije isti dokument dobija DVA identiteta,
    sto je izmereno na stvarnoj razlici izmedju dva legalna pipeline-a:

      `uploaded_doc/extractor.py:247` u OCR grani vraca `ocr_text` kao
      `"

".join(p for p in ocr_pages if p)` -- prazne strane ISPADAJU --
      ali kao cetvrtu vrednost vraca `ocr_pages`, koji ih ZADRZAVA (`:250`).

      `api.py` hesira `text` (bez praznih strana).
      `routers/smart_intake.py` za segment hesira `"

".join(pages[a:b])`
      (sa praznim stranama).

    Skenirani PDF sa jednom neuspesno prepoznatom stranom je dovoljan:

        api.py       -> 'Prva strana.

Treca strana.'
        smart_intake -> 'Prva strana.



Treca strana.'
        hes          -> 9b6c3ee4...  vs  478efa88...

    Normalizacija spaja ta dva, a NE spaja stvarno razlicite dokumente
    (kontrolisano testom).

    Sta se normalizuje i zasto:
      NFC          -- ista slova zapisana razlicito ("č" kao jedan znak ili kao
                      "c" + kvacica) daju isti bajt-niz
      prelomi reda -- CRLF/CR -> LF; zavise od platforme, ne od dokumenta
      rep reda     -- razmaci na kraju reda su artefakt ekstrakcije
      prazni redovi -- 3+ uzastopna preloma -> 2; ovo je ono sto zatvara
                      razliku izmedju dva pipeline-a
      rubovi       -- vodeci/prateci razmak celog dokumenta
    """
    if tekst is None:
        raise NedovoljanIdentitet("tekst dokumenta je None — nema identiteta")
    t = unicodedata.normalize("NFC", tekst)
    t = t.replace(CRLF, LF).replace(CR, LF)
    t = LF.join(red.rstrip() for red in t.split(LF))
    t = _VISE_PRELOMA.sub(LF + LF, t)
    return t.strip()


def verzija_dokumenta(tekst: str, extraction_version: int = EXTRACTION_VERSION) -> str:
    """Kanonski identitet sadržaja jednog dokumenta.

    Isti dokument kroz BILO KOJI produkcijski pipeline mora dati istu vrednost —
    to je jedini razlog zbog kog detekcija duplikata i brisanje mogu da rade
    preko granica pipeline-a.
    """
    osnova = f"e{int(extraction_version)}|{kanonski_tekst(tekst)}"
    return hashlib.sha256(osnova.encode("utf-8")).hexdigest()[:_VERZIJA_DUZINA]



_KANONSKI_OBLIK = re.compile(r"^[0-9a-f]{%d}$" % _VERZIJA_DUZINA)


def proveri_kanonsku_verziju(verzija: str) -> str:
    """Odbija sve što nije izlaz `verzija_dokumenta()`.

    Pisač koji prosledi nešto drugo — recimo `hashlib.sha256(raw).hexdigest()`,
    koji ima 64 znaka umesto 32 — ovde pada, umesto da tiho proizvede vektore
    pod pogrešnim identitetom. To je struktura koja hvata tačno grešku koju su
    pisci već pravili: heš BAJTOVA umesto heša TEKSTA.

    Ne dokazuje da je heširan pravi tekst — to nijedna provera ovde ne može.
    Dokazuje da vrednost potiče iz kanonske funkcije, a ne iz slučajnog
    `hexdigest()` poziva.
    """
    v = (verzija or "").strip()
    if not _KANONSKI_OBLIK.match(v):
        raise NedovoljanIdentitet(
            f"verzija nije kanonskog oblika ({_VERZIJA_DUZINA} heks znakova): "
            f"dobijeno {len(v)} znakova"
        )
    return v
