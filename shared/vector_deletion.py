# -*- coding: utf-8 -*-
"""Kanonsko brisanje vektora jednog dokumenta.

BETA-DATA-PINE-01.

ZAŠTO OVAJ MODUL POSTOJI

Do sada nije postojao nijedan način da se iz Pinecone-a ukloni tačno jedan
dokument. Najuži izvodljiv zahvat bio je `delete_all` nad celim namespace-om —
što za `kancelarija_{id}` znači **sve dokumente cele kancelarije**. GDPR čl. 17
je time bio tehnički nesprovodiv.

ULAZ JE `document_id`, NIKAD VECTOR ID

Ovo je najvažnija odluka u modulu. Da funkcija prima Pinecone vector ID iz
zahteva, autorizacija bi bila zaobiđena po definiciji: napadač bi prosledio tuđi
ID i obrisao tuđe podatke. Zato se ID-evi **izvode** iz reda u bazi koji je
prošao kanonsku kapiju, i nikad ne dolaze spolja.

ŠTA JE FAIL-CLOSED (RULE: nema „best effort" brisanja)

Odbija se, bez izuzetka, ako:
  · pozivalac nije vlasnik predmeta (ili izričito delegiran) — ista kapija kao
    `api.py::get_predmet` i `shared/rag_acl.py`
  · dokument ne pripada tom predmetu
  · `content_sha256` nedostaje ili nije kanonskog oblika
  · `pinecone_namespace` nedostaje
  · ijedan nađeni ID ne počinje kanonskim prefiksom
  · verifikacija posle brisanja ne potvrdi rezultat

Nijedan od tih slučajeva ne sme da se degradira u „obriši šta možeš".

ŠTA OVAJ MODUL NIKAD NE RADI

Ne briše po sličnosti, po imenu fajla, po `delete_all` nad namespace-om, niti po
prefiksu koji nije izgrađen `prefiks_dokumenta`-om. Nepoznat identitet se ne
briše — takav vektor ide u karantin (v. `klasifikuj_orphan`), jer brisanje
onoga što ne umemo da identifikujemo je pogađanje, ne brisanje.
"""
from __future__ import annotations

import logging
from typing import Optional

from shared.vector_identity import (
    NedovoljanIdentitet,
    prefiks_dokumenta,
    proveri_kanonsku_verziju,
)

logger = logging.getLogger("vindex.vector_deletion")


class Ishod:
    """Eksplicitno stanje — nikad „uspeh jer nije bilo izuzetka" (§10)."""

    DELETED = "DELETED"
    ALREADY_ABSENT = "ALREADY_ABSENT"
    REFUSED = "REFUSED"
    PARTIAL_FAILURE = "PARTIAL_FAILURE"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"


class Rezultat:
    def __init__(self, ishod: str, razlog: str = "", obrisano: int = 0,
                 ocekivano: int = 0, prefiks: str = ""):
        self.ishod = ishod
        self.razlog = razlog
        self.obrisano = obrisano
        self.ocekivano = ocekivano
        self.prefiks = prefiks

    @property
    def uspeh(self) -> bool:
        return self.ishod in (Ishod.DELETED, Ishod.ALREADY_ABSENT)

    def __repr__(self):
        return (f"<Rezultat {self.ishod} obrisano={self.obrisano}/"
                f"{self.ocekivano} razlog={self.razlog!r}>")

    def as_dict(self) -> dict:
        return {"ishod": self.ishod, "razlog": self.razlog,
                "obrisano": self.obrisano, "ocekivano": self.ocekivano}


def _sme_predmet(supa, user_id: str, predmet_id: str) -> bool:
    """Ista kapija kao `api.py::get_predmet`: vlasnik ILI aktivna delegacija.

    Namerno se NE koristi `predmet_saradnici` — kanonska kapija je ne
    konsultuje, pa bi je uključiti ovde značilo dati pravo brisanja koje pravo
    čitanja ne daje.
    """
    if not (user_id and predmet_id):
        return False
    try:
        r = (supa.table("predmeti").select("id")
             .eq("id", predmet_id).eq("user_id", user_id).limit(1).execute())
        if r.data:
            return True
        d = (supa.table("predmet_delegiranja").select("id")
             .eq("predmet_id", predmet_id).eq("na_user_id", user_id)
             .eq("status", "aktivno").limit(1).execute())
        return bool(d.data)
    except Exception as e:
        logger.warning("[DELETE] provera vlasništva pala, odbijam: %s", e)
        return False


def _izlistaj_po_prefiksu(index, namespace: str, prefiks: str) -> Optional[list]:
    """Vraća ID-eve sa datim prefiksom, ili `None` ako listanje nije moguće.

    `None` je bitno različito od prazne liste: prazna znači „nema ničega",
    `None` znači „ne znam" — a na „ne znam" se ne briše.
    """
    try:
        out = []
        for strana in index.list(prefix=prefiks, namespace=namespace):
            out.extend(strana if isinstance(strana, list) else [strana])
        return [str(x) for x in out]
    except Exception as e:
        logger.error("[DELETE] listanje po prefiksu nije uspelo (ns=%s): %s",
                     namespace, e)
        return None


# Prozor u kome se čeka da Pinecone-ov `list()` prizna već izvršeno brisanje.
# 8 × 1.5s ≈ 12s: mereno je da je stvarno kašnjenje reda sekunde, a gornja
# granica mora ostati unutar trajanja jednog HTTP zahteva.
VERIFIKACIJA_POKUSAJA = 8
VERIFIKACIJA_PAUZA_S = 1.5


def _cekaj_da_nestanu(index, namespace: str, prefiks: str,
                      pokusaja: int = VERIFIKACIJA_POKUSAJA,
                      pauza_s: float = VERIFIKACIJA_PAUZA_S,
                      _spavaj=None) -> Optional[list]:
    """Lista po prefiksu dok ne bude prazna ili dok prozor ne istekne.

    Vraća poslednje viđeno stanje: `[]` (nestali), lista preostalih, ili `None`
    ako listanje uopšte nije moguće. `None` se NE ponavlja — „ne znam" se ne
    popravlja čekanjem, i ne sme da se degradira u „prazno je".
    """
    import time as _time
    spavaj = _spavaj or _time.sleep
    preostali = None
    for pokusaj in range(max(1, pokusaja)):
        preostali = _izlistaj_po_prefiksu(index, namespace, prefiks)
        if preostali is None or preostali == []:
            return preostali
        if pokusaj < pokusaja - 1:
            spavaj(pauza_s)
    logger.warning("[DELETE] posle %d provera ostalo %d vektora (ns=%s)",
                   pokusaja, len(preostali or []), namespace)
    return preostali


def obrisi_vektore_dokumenta(
    supa,
    index,
    *,
    user_id: str,
    predmet_id: str,
    document_id: str,
) -> Rezultat:
    """Briše SVE vektore jednog dokumenta — i ništa drugo.

    Nijedan Pinecone ID ne dolazi od pozivaoca; svi se izvode iz reda u bazi
    koji je prošao autorizaciju.
    """
    # ── 1. AUTORIZACIJA ─────────────────────────────────────────────────────
    if not _sme_predmet(supa, user_id, predmet_id):
        return Rezultat(Ishod.REFUSED, "nema pravo pristupa predmetu")

    # ── 2. RED U BAZI — mora pripadati BAŠ tom predmetu i korisniku ─────────
    try:
        r = (supa.table("predmet_dokumenti")
             .select("id, predmet_id, user_id, content_sha256, pinecone_namespace")
             .eq("id", document_id).eq("predmet_id", predmet_id)
             .limit(1).execute())
    except Exception as e:
        logger.warning("[DELETE] čitanje dokumenta palo: %s", e)
        return Rezultat(Ishod.REFUSED, "dokument nije čitljiv")
    if not r.data:
        # 404-semantika: ne odaje se da li dokument postoji pod drugim predmetom.
        return Rezultat(Ishod.REFUSED, "dokument nije pronađen u tom predmetu")
    red = r.data[0]

    # ── 3. IDENTITET — bez njega se NE briše ────────────────────────────────
    verzija = (red.get("content_sha256") or "").strip()
    namespace = (red.get("pinecone_namespace") or "").strip()
    if not verzija:
        return Rezultat(Ishod.REFUSED,
                        "dokument nema content_sha256 — identitet nije poznat")
    if not namespace:
        return Rezultat(Ishod.REFUSED, "dokument nema pinecone_namespace")
    try:
        proveri_kanonsku_verziju(verzija)
        prefiks = prefiks_dokumenta(predmet_id, verzija)
    except NedovoljanIdentitet as e:
        # Legacy dokument sa 64-znakovnim hešem bajtova završava ovde — i to je
        # tačno: njegov identitet nije kanonski, pa se ne sme brisati po
        # pretpostavci da jeste.
        return Rezultat(Ishod.REFUSED, f"identitet nije kanonski: {e}")

    # ── 4. IZVOĐENJE SKUPA ID-eva ───────────────────────────────────────────
    idevi = _izlistaj_po_prefiksu(index, namespace, prefiks)
    if idevi is None:
        return Rezultat(Ishod.REFUSED, "listanje vektora nije uspelo",
                        prefiks=prefiks)
    if not idevi:
        return Rezultat(Ishod.ALREADY_ABSENT, "nema vektora sa tim identitetom",
                        prefiks=prefiks)

    # Pojas i tregeri: Pinecone je vratio listu po prefiksu, ali se ne oslanjamo
    # na to — svaki ID se proverava ponovo. Ako se ijedan ne poklapa, NIŠTA se
    # ne briše. Bolje odbiti nego obrisati tuđe.
    stranci = [i for i in idevi if not i.startswith(prefiks)]
    if stranci:
        logger.error("[DELETE] listanje vratilo %d ID-eva van prefiksa — odbijam",
                     len(stranci))
        return Rezultat(Ishod.REFUSED,
                        "listanje je vratilo ID-eve van kanonskog prefiksa",
                        prefiks=prefiks)

    ocekivano = len(idevi)

    # ── 5. BRISANJE ─────────────────────────────────────────────────────────
    try:
        index.delete(ids=idevi, namespace=namespace)
    except Exception as e:
        logger.error("[DELETE] brisanje palo (ns=%s, %d ID-eva): %s",
                     namespace, ocekivano, e)
        return Rezultat(Ishod.PARTIAL_FAILURE, f"brisanje nije uspelo: {e}",
                        ocekivano=ocekivano, prefiks=prefiks)

    # ── 6. VERIFIKACIJA — HTTP 200 NIJE DOKAZ (§8) ──────────────────────────
    #
    # NS001/FAZA 2 — JEDNO ČITANJE ODMAH POSLE BRISANJA NIJE DOKAZ ni u jednom
    # smeru. Pinecone-ov `list()` je eventualno konzistentan: mereno stvarnim
    # brisanjem, `delete()` je prošao, vektor je stvarno nestao, a `list()`
    # sekundu kasnije ga je i dalje vraćao. Ova funkcija je zbog toga vraćala
    # `PARTIAL_FAILURE`, pozivalac je odbijao ceo posao, i brisanje dokumenta
    # NIKAD nije uspevalo — iako su vektori bili uklonjeni. Advokat je dobijao
    # „ništa nije promenjeno" uz dokument koji je već ispao iz pretrage.
    #
    # Zato se čeka da indeks stigne sebe, u ograničenom prozoru. Prozor je
    # ograničen namerno: posle njega se i dalje prijavljuje neuspeh, jer
    # „sačekaj još malo" bez granice je isto što i „proglasi uspeh".
    preostali = _cekaj_da_nestanu(index, namespace, prefiks)
    if preostali is None:
        return Rezultat(Ishod.VERIFICATION_FAILED,
                        "brisanje izvršeno, ali rezultat nije proverljiv",
                        ocekivano=ocekivano, prefiks=prefiks)
    if preostali:
        return Rezultat(Ishod.PARTIAL_FAILURE,
                        f"posle brisanja ostalo {len(preostali)} vektora",
                        obrisano=ocekivano - len(preostali),
                        ocekivano=ocekivano, prefiks=prefiks)

    logger.info("[DELETE] dokument=%.8s predmet=%.8s obrisano=%d ns=%s",
                document_id, predmet_id, ocekivano, namespace)
    return Rezultat(Ishod.DELETED, "", obrisano=ocekivano,
                    ocekivano=ocekivano, prefiks=prefiks)


# ─── KARANTIN ZA NEIDENTIFIKOVANE VEKTORE (§1) ──────────────────────────────

ORPHAN_UNIDENTIFIABLE = "ORPHAN_UNIDENTIFIABLE"
KANONSKI = "KANONSKI"
LEGACY_POZNAT = "LEGACY_POZNAT"


def klasifikuj_orphan(vector_id: str, metadata: Optional[dict] = None) -> str:
    """Razvrstava vektor po tome MOŽE LI mu se identitet dokazati.

    Namerno ne pokušava rekonstrukciju. `ORPHAN_UNIDENTIFIABLE` je konačna
    klasifikacija, ne međukorak ka brisanju: vektor čiji identitet ne znamo se
    **ne briše nikad**, jer bi to bilo pogađanje. Karantin je ispravan ishod.
    """
    meta = metadata or {}
    if meta.get("vx_scope") and meta.get("vx_verzija"):
        return KANONSKI
    vid = vector_id or ""
    if "__" in vid and "_c" in vid.rsplit("__", 1)[-1]:
        return KANONSKI
    if "__chunk_" in vid or vid.startswith(("kb_", "discovery_")):
        return LEGACY_POZNAT
    return ORPHAN_UNIDENTIFIABLE


# ─── BRANA NAD GLOBALNIM BRISANJEM (PINE-02 §7) ─────────────────────────────

class GlobalnoBrisanjeOdbijeno(RuntimeError):
    """Diže se kad `delete_all` nad namespace-om nije dokazano bezbedan."""


DOZVOLA_ENV = "VINDEX_ALLOW_DESTRUCTIVE_ROLLBACK"


def dozvoli_globalno_brisanje(index, namespace: str, kreirano_ovim_pokretanjem: int = 0) -> int:
    """Kapija ispred svakog `delete_all`. Vraća broj vektora koji BI nestao.

    ZAŠTO POSTOJI

    `scripts/ingest_case_law.py` ima dve rollback grane koje rade
    `index.delete(delete_all=True, namespace="sudska_praksa")`. Napisane su kad
    je taj namespace bio prazan i punio ga je samo taj skript. Danas u njemu
    stoji **407.795 vektora iz tri različita izvora** (`ingest_case_law`,
    `ingest_bilten_to_pinecone`, `ingest_sudskapraksa`), pa bi rollback jednog
    ingesta uništio podatke druga dva — kao kolateralu, bez ijedne poruke.

    ŠTA OVA FUNKCIJA NAMERNO NE RADI

    Ne pokušava da „suzi" brisanje na vektore koje je taj skript napravio. To bi
    tražilo dokaz o opsegu koji ne postoji — ID obrasci tri pisača nisu
    disjunktni na način koji bi to garantovao. §7 izričito zabranjuje pretvaranje
    globalnog brisanja u „malo sigurnije" bez dokazanog opsega.

    Umesto toga radi jedino što je pošteno: odbija, kaže koliko bi nestalo, i
    traži izričitu dozvolu.
    """
    try:
        stat = index.describe_index_stats()
        ns = (getattr(stat, "namespaces", None) or
              (stat.get("namespaces") if isinstance(stat, dict) else {}) or {})
        podaci = ns.get(namespace) or {}
        ukupno = (getattr(podaci, "vector_count", None)
                  if not isinstance(podaci, dict) else podaci.get("vector_count", 0)) or 0
    except Exception as e:
        raise GlobalnoBrisanjeOdbijeno(
            f"broj vektora u namespace-u '{namespace}' nije merljiv ({e}) — "
            f"globalno brisanje se odbija"
        ) from e

    tudje = int(ukupno) - int(kreirano_ovim_pokretanjem or 0)
    if tudje > 0:
        raise GlobalnoBrisanjeOdbijeno(
            f"namespace '{namespace}' sadrzi {ukupno} vektora, a ovo pokretanje "
            f"je napravilo {kreirano_ovim_pokretanjem} — {tudje} tudjih vektora bi "
            f"bilo unisteno. Odbijam. Ako je to zaista namera, postavi "
            f"{DOZVOLA_ENV}=1."
        )
    return int(ukupno)
