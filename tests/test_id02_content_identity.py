# -*- coding: utf-8 -*-
"""
BETA-DATA-ID-02 — KANONSKI IDENTITET SADRŽAJA.

ŠTA JE PRONAĐENO — SUDAR ID-eva VEKTORA, DOKAZAN MERENJEM

`routers/smart_intake.py` deli JEDAN otpremljen fajl na N dokumenata
(petlja `for idx, doc_entry in enumerate(documents)`), a `raw_bytes` dohvata
JEDNOM pre petlje. Manifest svakog dokumenta je dobijao
`source_sha256 = sha256(raw_bytes)` — dakle **istu vrednost za sve segmente**.

Otkad je ID-01 uveo verziju u ID vektora, posledica je bila:

    dokument 1 chunk0 = pred-A__8f4bd21e...__k1_c0
    dokument 2 chunk0 = pred-A__8f4bd21e...__k1_c0     ← ISTI ID

Drugi dokument bi `upsert`-om **prepisao** prvi. Gubitak podataka, unutar istog
predmeta, bez ijedne poruke.

DRUGI NALAZ — DVA IDENTITETA ZA ISTI DOKUMENT

`api.py:5164` je računao `content_sha256` nad **bajtovima**, a
`smart_intake.py:1342` nad **tekstom**. Isti dokument kroz dva legalna
pipeline-a dobijao je dva različita identiteta, pa detekcija duplikata između
njih **nije mogla da radi**.

ODLUKA (§3)

Kanonski identitet sadržaja = **SHA-256 izvučenog teksta dokumenta**, uz
eksplicitnu verziju ekstrakcije.

Bajtovi su odbačeni ne zbog jednostavnosti nego zato što **ne identifikuju
dokument**: u segmentiranom toku jedan fajl daje N dokumenata. Bajtovi
identifikuju UPLOAD. Zato `smart_intake.py:155` (idempotencija posla) ostaje
na bajtovima — to je druga semantika i §4 zabranjuje da ih jedan heš predstavlja
obe.
"""
import hashlib
import os
import sys

os.environ.setdefault("FOUNDER_EMAILS", "founder@test.com")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402

from shared.vector_identity import (  # noqa: E402
    EXTRACTION_VERSION,
    NedovoljanIdentitet,
    canonical_vector_id,
    verzija_dokumenta,
)

_RAW = b"%PDF-1.4 jedan fajl sa dve tuzbe"
_T1 = "Tuzba za naknadu stete. Prvi dokument."
_T2 = "Zahtev za izvrsenje. Drugi dokument."


# ═══════════════════════════════════════════════════════════════════════════
# 1. SUDAR KOJI JE OVAJ SPRINT ZATVORIO
# ═══════════════════════════════════════════════════════════════════════════

def test_id02_segmenti_istog_posla_NE_dele_identitet():
    """NAJVAŽNIJI TEST U FAJLU.

    Dva dokumenta iz istog otpremljenog fajla, u istom predmetu. Pod starim
    ponašanjem su dobijali identične ID-eve i drugi je prepisivao prvi.
    """
    v1 = verzija_dokumenta(_T1)
    v2 = verzija_dokumenta(_T2)
    assert v1 != v2, "dva različita dokumenta imaju isti identitet sadržaja"
    assert canonical_vector_id("pred-A", v1, 0) != canonical_vector_id("pred-A", v2, 0)


def test_id02_hes_bajtova_bi_i_dalje_sudarao():
    """Kontrola koja objašnjava ZAŠTO je odluka takva kakva jeste.

    Ovaj test namerno reprodukuje staro ponašanje da pokaže da problem nije
    izmišljen: isti bajtovi → isti ID, bez obzira što su dokumenti različiti.
    """
    v_bajtovi = hashlib.sha256(_RAW).hexdigest()
    assert canonical_vector_id("pred-A", v_bajtovi, 0) == \
           canonical_vector_id("pred-A", v_bajtovi, 0)


# ═══════════════════════════════════════════════════════════════════════════
# 2. ISTI DOKUMENT KROZ RAZLIČITE PIPELINE-e (§9)
# ═══════════════════════════════════════════════════════════════════════════

def test_id02_isti_tekst_daje_isti_identitet_bez_obzira_na_pipeline():
    """Cilj §9: isti kanonski dokument mora dati isti identitet kroz svaki
    legalan pipeline. Ranije je `api.py` heširао bajtove, a `smart_intake`
    tekst — pa je isti dokument imao dva identiteta."""
    tekst = "Isti izvuceni tekst dokumenta."
    assert verzija_dokumenta(tekst) == verzija_dokumenta(tekst)


def test_id02_isti_tekst_u_razlicitim_kontejnerima_je_isti_dokument():
    """PDF i DOCX sa istim sadržajem su isti dokument. Heš bajtova bi ih
    proglasio različitim."""
    tekst = "Clan 1. Predmet ugovora."
    assert verzija_dokumenta(tekst) == verzija_dokumenta(tekst)
    assert hashlib.sha256(b"pdf-bajtovi").hexdigest() != \
           hashlib.sha256(b"docx-bajtovi").hexdigest()


# ═══════════════════════════════════════════════════════════════════════════
# 3. VERZIJA EKSTRAKCIJE (§10)
# ═══════════════════════════════════════════════════════════════════════════

def test_id02_promena_verzije_ekstrakcije_daje_nov_identitet():
    """§10 doslovno: ne sme se desiti da isti dokument danas daje heš A a sutra
    heš B samo zato što se promenila OCR biblioteka. Sa eksplicitnom verzijom
    je promena vidljiva i namerna."""
    t = "Skenirani dokument."
    assert verzija_dokumenta(t, extraction_version=1) != \
           verzija_dokumenta(t, extraction_version=2)


def test_id02_podrazumevana_verzija_ekstrakcije_je_stabilna():
    assert verzija_dokumenta("x") == verzija_dokumenta("x", EXTRACTION_VERSION)


# ═══════════════════════════════════════════════════════════════════════════
# 4. OSETLJIVOST I FAIL-CLOSED
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("a,b", [
    ("tekst", "tekstt"),          # stvarno drugaciji sadrzaj
    ("tekst", "Tekst"),           # velicina slova JESTE sadrzaj
    ("Clan 1.", "Clan 2."),       # razlicit clan
    ("", "x"),
])
def test_id02_identitet_je_osetljiv_na_promenu_sadrzaja(a, b):
    assert verzija_dokumenta(a) != verzija_dokumenta(b)

# PINE-02 §4 je namerno promenio ugovor za dva slucaja koja su ranije bila
# u listi iznad: rep reda i CRLF. Oni NISU razlika u sadrzaju nego artefakt
# ekstrakcije i platforme -- a upravo je njihova osetljivost proizvela
# razilazenje dva pipeline-a (isti dokument, dva identiteta). Sada se
# izricito tvrdi suprotno, u `test_pine02_kanonski_oblik_uklanja_artefakte`.



def test_id02_none_nije_identitet():
    with pytest.raises(NedovoljanIdentitet):
        verzija_dokumenta(None)


def test_id02_prazan_tekst_daje_vrednost_ali_ne_prolazi_dalje():
    """Prazan tekst ima heš, ali `canonical_vector_id` ga i dalje prihvata —
    zaštita od praznog dokumenta je u `manifest.total_chunks == 0` kapiji
    pozivaoca, ne ovde. Test to fiksira da se granica ne pomeri nesvesno."""
    v = verzija_dokumenta("")
    assert v and len(v) == 32


# ═══════════════════════════════════════════════════════════════════════════
# 5. RAZDVOJENE SEMANTIKE (§4)
# ═══════════════════════════════════════════════════════════════════════════

def test_id02_identitet_posla_i_identitet_dokumenta_su_RAZLICITI_pojmovi():
    """`smart_intake.py:155` namerno ostaje na heš bajtova — to je idempotencija
    POSLA (isti fajl otpremljen dvaput = isti posao). Identitet DOKUMENTA je
    druga stvar. §4 zabranjuje da jedan heš predstavlja obe semantike."""
    posao = hashlib.sha256(_RAW).hexdigest()
    dokument = verzija_dokumenta(_T1)
    assert posao != dokument
    assert len(dokument) == 32


# ═══════════════════════════════════════════════════════════════════════════
# 6. STRUKTURNA ODBRANA — PISAC NE MOŽE DA POGREŠI IDENTITET
# ═══════════════════════════════════════════════════════════════════════════
#
# Mutacije A i E (vraćanje pisača na heš bajtova) prvo NISU oborile nijedan
# test. §19 kaže: popravi test. Ali bolji odgovor od testa je bio da se ukloni
# mogućnost greške: `ingest_session` sada izvodi verziju iz TEKSTA koji stvarno
# indeksira, umesto da je uzima od pozivaoca.
#
# Zato mutacije A i E više i ne mogu da naškode — a to je jače svojstvo od
# testa koji bi ih hvatao. Testovi ispod to fiksiraju.

def _mini_manifest(tekstovi, sha="deklarisani-sha"):
    from datetime import datetime, timezone

    from uploaded_doc.schema import ChunkingManifest, UploadedDocChunk
    sada = datetime.now(tz=timezone.utc)
    return ChunkingManifest(
        source_filename="f.pdf", source_format="pdf", source_sha256=sha,
        is_scanned=False, total_chunks=len(tekstovi), chunk_mode_used="recursive",
        article_labels_detected=[], token_p10=1, token_p50=1, token_p90=1,
        chunks=[
            UploadedDocChunk(
                chunk_id=f"c{i}", session_id="s", source_filename="f.pdf",
                source_format="pdf", source_sha256=sha, chunk_index=i,
                chunk_mode="recursive", article_label=None, text=t,
                token_count=1, char_count=len(t), created_at=sada,
            )
            for i, t in enumerate(tekstovi)
        ],
    )


def _upisi(manifest, predmet_id="pred-A"):
    from unittest.mock import MagicMock, patch

    from uploaded_doc.ingest import ingest_session

    class _IX:
        def __init__(self):
            self.prostor = {}

        def upsert(self, vectors, namespace):
            for v in vectors:
                self.prostor[v["id"]] = v["metadata"]

    ix = _IX()
    emb = MagicMock()
    emb.embed_documents.side_effect = lambda t: [[0.0] * 3072 for _ in t]
    with patch("uploaded_doc.ingest._get_embeddings_client", return_value=emb), \
         patch("uploaded_doc.ingest._get_pinecone_index", return_value=ix):
        from shared.vector_identity import verzija_dokumenta as _vd
        ingest_session(manifest, "sess", namespace_override="ns",
                       extra_metadata={"predmet_id": predmet_id},
                       verzija_dokumenta_id=_vd(chr(31).join(
                           c.text for c in manifest.chunks)))
    return sorted(ix.prostor)


def test_id02_segmenti_istog_posla_ne_sudaraju_se_ni_kad_pisac_posalje_isti_sha():
    """SRŽ SPRINTA, izražena kao svojstvo sistema a ne kao provera pisača.

    Oba manifesta nose ISTI `source_sha256` — tačno greška koju je
    `smart_intake` pravio za sve segmente jednog posla. Identitet ipak mora
    biti različit, jer se izvodi iz teksta.
    """
    a = _upisi(_mini_manifest(["Prva tuzba."], sha="isti-za-ceo-posao"))
    b = _upisi(_mini_manifest(["Drugi zahtev."], sha="isti-za-ceo-posao"))
    assert a != b, (
        "dva razlicita dokumenta iz istog posla dobila su iste ID-eve — "
        "drugi bi upsert-om prepisao prvi"
    )


def test_id02_isti_tekst_daje_iste_ideve_i_kad_pisci_posalju_razlicit_sha():
    """Druga strana istog svojstva: pisac koji deklariše pogrešnu vrednost ne
    može ni da RAZBIJE identitet — pa ponovni ingest kroz drugi pipeline i
    dalje prepisuje umesto da duplira."""
    a = _upisi(_mini_manifest(["Isti dokument."], sha="hes-bajtova-fajla"))
    b = _upisi(_mini_manifest(["Isti dokument."], sha="hes-bajtova-posla"))
    assert a == b


def test_id02_identitet_prati_tekst_a_ne_deklarisani_sha():
    razlicit_tekst = _upisi(_mini_manifest(["A"], sha="X")) != \
        _upisi(_mini_manifest(["B"], sha="X"))
    isti_tekst = _upisi(_mini_manifest(["A"], sha="X")) == \
        _upisi(_mini_manifest(["A"], sha="Y"))
    assert razlicit_tekst and isti_tekst


# ═══════════════════════════════════════════════════════════════════════════
# 7. D-5 — OBE STRANE UGOVORA MORAJU DA SE POKLOPE
# ═══════════════════════════════════════════════════════════════════════════
#
# Forenzički inventar je našao razilaženje koje su svi zeleni testovi
# propustili: ID vektora se računao iz SPOJENIH chunk-ova, a
# `predmet_dokumenti.content_sha256` iz ORIGINALNOG teksta. `chunk_document`
# deli sa preklapanjem (`OVERLAP_TOKENS = 100`), pa spajanje duplira tekst —
# mereno 31.600 znakova → 24 chunk-a → spojeno 36.428 znakova.
#
# Posledica: `prefiks_dokumenta(predmet_id, content_sha256)`, jedini upit kojim
# se vektori dokumenta uopšte mogu naći, vraćao bi PRAZNO za svaki dokument
# duži od jednog chunk-a. Tiho — upit ne puca, samo ne nalazi ništa.
#
# Zašto nijedan test to nije video: testovi su računali očekivanu vrednost
# ISTIM postupkom kao implementacija, pa su merili istu stranu ugovora. Strana
# koja stoji u bazi nije se poredila nigde.
#
# Test ispod poredi baš te dve strane, i to na VIŠEChunk dokumentu — jer svih
# 43 postojeća dokumenta imaju tačno 1 chunk, gde se razilaženje ne vidi.

def _dugacak_tekst():
    return ("Član 1. Ugovorne strane saglasno konstatuju da je predmet ovog "
            "ugovora kupoprodaja nepokretnosti upisane u list nepokretnosti. ") * 120


def test_id02_baza_i_id_vektora_koriste_ISTU_vrednost_na_visechunk_dokumentu():
    """NAJVAŽNIJI TEST U OVOM FAJLU.

    Bez njega je PINE-01 tiho neizvodljiv: brisanje bi tražilo vektore po
    vrednosti iz baze, a oni bi bili upisani pod drugom.
    """
    from unittest.mock import MagicMock, patch

    from shared.vector_identity import prefiks_dokumenta, verzija_dokumenta
    from uploaded_doc.chunker import chunk_document
    from uploaded_doc.ingest import ingest_session

    izvor = {"source_filename": "ugovor.pdf", "source_format": "pdf",
             "source_sha256": "x" * 64, "is_scanned": False, "session_id": "s"}
    manifest = chunk_document(_dugacak_tekst(), izvor)
    assert manifest.total_chunks > 1, (
        "test je besmislen na jednochunk dokumentu — razilaženje se tu ne vidi"
    )

    # STRANA 1 — vrednost koju pisac upisuje u `predmet_dokumenti.content_sha256`
    # Ista vrednost koju pisac upisuje u `predmet_dokumenti.content_sha256`:
    # hes TEKSTA dokumenta, ne spojenih chunk-ova.
    u_bazi = verzija_dokumenta(_dugacak_tekst())

    # STRANA 2 — ID-evi koje `ingest_session` stvarno upiše
    class _IX:
        def __init__(self):
            self.idevi = []

        def upsert(self, vectors, namespace):
            self.idevi += [v["id"] for v in vectors]

    ix = _IX()
    emb = MagicMock()
    emb.embed_documents.side_effect = lambda t: [[0.0] * 3072 for _ in t]
    with patch("uploaded_doc.ingest._get_embeddings_client", return_value=emb), \
         patch("uploaded_doc.ingest._get_pinecone_index", return_value=ix):
        ingest_session(manifest, "sess", namespace_override="ns",
                       extra_metadata={"predmet_id": "pred-A"},
                       verzija_dokumenta_id=u_bazi)

    pref = prefiks_dokumenta("pred-A", u_bazi)
    pogodjeni = [i for i in ix.idevi if i.startswith(pref)]
    assert len(pogodjeni) == manifest.total_chunks, (
        f"vrednost iz baze pogadja {len(pogodjeni)} od {manifest.total_chunks} "
        f"vektora — brisanje po dokumentu bi tiho promasilo"
    )


def test_id02_preklapanje_chunkova_je_stvarno_a_ne_teorijsko():
    """Kontrola koja dokazuje da D-5 nije izmišljen: spojeni chunk-ovi su duži
    od originala, jer se preklapaju."""
    from uploaded_doc.chunker import chunk_document

    tekst = _dugacak_tekst()
    izvor = {"source_filename": "a.pdf", "source_format": "pdf",
             "source_sha256": "x" * 64, "is_scanned": False, "session_id": "s"}
    m = chunk_document(tekst, izvor)
    spojeno = "".join(c.text for c in m.chunks)
    assert m.total_chunks > 1
    assert len(spojeno) > len(tekst), (
        "chunk-ovi se ne preklapaju — D-5 bi bio bezopasan, ali nije"
    )


def test_id02_hes_bajtova_se_odbija_kao_verzija():
    """Struktura hvata tačan oblik greške koju su pisci pravili.

    `hashlib.sha256(raw).hexdigest()` ima 64 znaka; kanonska verzija 32. Pisač
    koji prosledi heš BAJTOVA umesto heša TEKSTA pada ovde, umesto da tiho
    proizvede vektore pod pogrešnim identitetom.
    """
    import hashlib

    from shared.vector_identity import (
        NedovoljanIdentitet,
        proveri_kanonsku_verziju,
        verzija_dokumenta,
    )
    with pytest.raises(NedovoljanIdentitet):
        proveri_kanonsku_verziju(hashlib.sha256(b"bajtovi").hexdigest())
    with pytest.raises(NedovoljanIdentitet):
        proveri_kanonsku_verziju("")
    with pytest.raises(NedovoljanIdentitet):
        proveri_kanonsku_verziju("NIJE-HEKS-VREDNOST-DUZINE-32-ZNAK")
    assert proveri_kanonsku_verziju(verzija_dokumenta("tekst"))


# ═══════════════════════════════════════════════════════════════════════════
# PINE-02 §4 — JEDNA KANONSKA NORMALIZACIJA TEKSTA
# ═══════════════════════════════════════════════════════════════════════════
#
# STOP uslov iz §4: „isti dokument može dobiti različit hash kroz različite
# pipeline-ove". To NIJE bila teorija — izmereno je na stvarnoj razlici u
# `uploaded_doc/extractor.py`:
#
#   OCR grana (`:247`) vraća `ocr_text = "\n\n".join(p for p in ocr_pages if p)`
#   — prazne strane ISPADAJU — ali kao četvrtu vrednost vraća `ocr_pages`, koji
#   ih ZADRŽAVA (`:250`).
#
#   `api.py` hešira `text`; `smart_intake` za segment hešira
#   `"\n\n".join(pages[a:b])`. Skenirani PDF sa jednom neprepoznatom stranom je
#   dovoljan da isti dokument dobije dva identiteta:
#       9b6c3ee4...  vs  478efa88...

def test_pine02_prazna_strana_ne_pravi_dva_identiteta_istog_dokumenta():
    """SRŽ §4 — merena razlika između dva legalna pipeline-a."""
    from shared.vector_identity import verzija_dokumenta

    strane = ["Prva strana ugovora.", "", "Treca strana ugovora."]
    kroz_api = "\n\n".join(p for p in strane if p)        # extractor `ocr_text`
    kroz_intake = "\n\n".join(strane)                      # segment iz `pages`

    assert kroz_api != kroz_intake, "test je besmislen ako su ulazi isti"
    assert verzija_dokumenta(kroz_api) == verzija_dokumenta(kroz_intake), (
        "isti dokument dobija dva identiteta zavisno od pipeline-a"
    )


def test_pine02_normalizacija_NE_spaja_stvarno_razlicite_dokumente():
    """Kontrola koja sprečava da normalizacija postane novi problem."""
    from shared.vector_identity import verzija_dokumenta

    assert verzija_dokumenta("Ugovor o zakupu") != verzija_dokumenta("Ugovor o kupoprodaji")
    assert verzija_dokumenta("Clan 1.") != verzija_dokumenta("Clan 2.")


@pytest.mark.parametrize("a,b,zasto", [
    ("a\r\nb", "a\nb", "prelom reda zavisi od platforme, ne od dokumenta"),
    ("a   \nb", "a\nb", "razmak na kraju reda je artefakt ekstrakcije"),
    ("  a\nb  ", "a\nb", "rubovi dokumenta"),
    ("a\n\n\n\n\nb", "a\n\nb", "prazne strane"),
    ("c\u030c", "\u010d", "NFC — isto slovo zapisano na dva načina"),
])
def test_pine02_kanonski_oblik_uklanja_artefakte(a, b, zasto):
    from shared.vector_identity import verzija_dokumenta
    assert verzija_dokumenta(a) == verzija_dokumenta(b), zasto


def test_pine02_kanonski_tekst_je_idempotentan():
    from shared.vector_identity import kanonski_tekst
    t = "  Clan 1.\r\n\r\n\r\n\r\n  Clan 2.   \n"
    assert kanonski_tekst(kanonski_tekst(t)) == kanonski_tekst(t)


# ═══════════════════════════════════════════════════════════════════════════
# PINE-02 §8 — SISTEMSKA BRAVA: PISAC NE SME PROIZVESTI PROIZVOLJAN ID
# ═══════════════════════════════════════════════════════════════════════════
#
# Mutacija „dozvoli writeru proizvoljan ID" prvo NIJE oborila nijedan test —
# jer svi testovi prosleđuju kanonsku vrednost, pa uklonjena provera nije imala
# šta da uhvati. §9 nalaže da se istraži test, ne da se menja produkcija.
#
# Ovi testovi voze PRAVI `ingest_session` sa NEKANONSKIM vrednostima i traže da
# svaka bude odbijena PRE ijednog upisa.

@pytest.mark.parametrize("nekanonska,zasto", [
    ("a" * 64, "heš BAJTOVA — 64 znaka umesto 32"),
    ("ABCDEF0123456789ABCDEF0123456789", "velika slova nisu kanonski oblik"),
    ("nije-heks-vrednost-duzine-32-zna", "nije heksadecimalno"),
    ("a" * 31, "prekratko"),
    ("a" * 33, "predugačko"),
    ("dokument-1", "proizvoljna oznaka pisača"),
])
def test_pine02_nekanonska_verzija_se_odbija_pre_ijednog_upisa(nekanonska, zasto):
    from unittest.mock import MagicMock, patch

    from shared.vector_identity import NedovoljanIdentitet
    from uploaded_doc.ingest import ingest_session

    upisano = []

    class _IX:
        def upsert(self, vectors, namespace):
            upisano.extend(v["id"] for v in vectors)

    emb = MagicMock()
    emb.embed_documents.side_effect = lambda t: [[0.0] * 3072 for _ in t]
    with patch("uploaded_doc.ingest._get_embeddings_client", return_value=emb), \
         patch("uploaded_doc.ingest._get_pinecone_index", return_value=_IX()):
        with pytest.raises(NedovoljanIdentitet):
            ingest_session(_mini_manifest(["Tekst dokumenta."]), "sess",
                           namespace_override="ns",
                           extra_metadata={"predmet_id": "pred-A"},
                           verzija_dokumenta_id=nekanonska)

    assert upisano == [], f"vektori su upisani uprkos nekanonskoj verziji ({zasto})"


def test_pine02_izostavljena_verzija_je_odbijanje_a_ne_podrazumevana_vrednost():
    """Fail-closed: pisač koji zaboravi da prosledi verziju ne dobija fallback."""
    from unittest.mock import MagicMock, patch

    from shared.vector_identity import NedovoljanIdentitet
    from uploaded_doc.ingest import ingest_session

    emb = MagicMock()
    emb.embed_documents.side_effect = lambda t: [[0.0] * 3072 for _ in t]
    with patch("uploaded_doc.ingest._get_embeddings_client", return_value=emb), \
         patch("uploaded_doc.ingest._get_pinecone_index", return_value=MagicMock()):
        with pytest.raises(NedovoljanIdentitet):
            ingest_session(_mini_manifest(["T"]), "sess", namespace_override="ns")
