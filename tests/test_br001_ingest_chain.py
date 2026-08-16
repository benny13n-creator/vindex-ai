# -*- coding: utf-8 -*-
"""
BR-001 — LANAC OD UPLOAD-A DO PRETRAŽIVOG VEKTORA.

ŠTA JE MERENO, A NE PRETPOSTAVLJENO

`predmet_dokumenti` ima 43 reda, svih 43 sa `status='sacuvano'` i sa
`pinecone_namespace` oblika `pred_<session_id>`. Nijedan od tih 43 namespace-ova
ne postoji u Pinecone-u — dakle nijedan od tih dokumenata nije pretraživ.

Ali `pred_` šema je iz koda PRE 2026-07-26 (`fa7129ff`), a najnoviji od tih 43
redova je od 2026-07-21. Ti redovi su zato istorijski talog, ne dokaz o
današnjem kodu — i upravo zato je današnji kod izmeren zasebno, pravim
kontrolisanim E2E prolaskom kroz produkcijsku rutu sa stvarnim Pinecone-om
(BR-001 FAZA 4/5): dokument je dobio `status='indeksirano'`, kanonski
namespace, deterministički ID i vraćen je stvarnom pretragom.

ZAŠTO OVI TESTOVI POSTOJE

E2E prolaz dokazuje JEDAN trenutak. Ovi testovi drže lanac zaključanim posle
tog trenutka, i mere ga na mestu na kom je već jednom pukao — na SPOJU:
namespace koji je stvarno otišao u `index.upsert()` mora biti isti onaj koji je
upisan u `predmet_dokumenti.pinecone_namespace`, a `status='indeksirano'` sme da
postoji samo ako je upsert stvarno prošao u celosti.

Test koji bi merio samo „da li ruta vrati 200" ne bi uhvatio ništa od ovoga:
43 postojeća reda su nastala uz uredan 200.

Bez naplativih poziva: embedding i Pinecone su zamenjeni na granici modula
(`uploaded_doc.ingest._get_embeddings_client` / `_get_pinecone_index`).
"""
import asyncio
import io
import json
import os
import sys
import types
from unittest.mock import MagicMock, patch

os.environ.setdefault("FOUNDER_EMAILS", "founder@test.com")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

_KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _KOREN)

import pytest  # noqa: E402

from uploaded_doc import ingest as ING  # noqa: E402
from shared.vector_identity import NedovoljanIdentitet, verzija_dokumenta  # noqa: E402

UID = "11111111-2222-3333-4444-555555555555"
PREDMET = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
KANON_NS = f"user_{UID}"
TEKST = ("PREDMET: kontrolni dokument. Svedok je 14. marta 2019. video kombi "
         "registracije NS-BR001-XZ ispred skladista u Temerinskoj 77. "
         "Ovaj tekst postoji samo radi merenja lanca ingesta.")
VERZIJA = verzija_dokumenta(TEKST)


# ═══════════════════════════════════════════════════════════════════════════
# Lažni Pinecone / embedding — beleže ŠTA je stvarno otišlo u upsert
# ═══════════════════════════════════════════════════════════════════════════

class _Index:
    def __init__(self, puca_od_batcha=None):
        self.upserts = []          # [(namespace, [vektori...])]
        self._puca_od = puca_od_batcha

    def upsert(self, vectors, namespace):
        if self._puca_od is not None and len(self.upserts) >= self._puca_od:
            raise RuntimeError("pinecone nedostupan")
        self.upserts.append((namespace, list(vectors)))

    @property
    def svi_zapisi(self):
        return [z for _ns, batch in self.upserts for z in batch]

    @property
    def namespaces(self):
        return {ns for ns, _ in self.upserts}


class _Emb:
    def __init__(self, koliko=None):
        self._koliko = koliko

    def embed_documents(self, texts):
        n = len(texts) if self._koliko is None else self._koliko
        return [[0.1] * 3072 for _ in range(n)]


def _manifest(tekst=TEKST):
    from uploaded_doc.chunker import chunk_document
    return chunk_document(tekst, {
        "source_filename": "br001.docx", "source_format": "docx",
        "source_sha256": "x" * 64, "is_scanned": False, "session_id": "__local__",
    })


def _ingest(index, emb=None, **kw):
    with patch.object(ING, "_get_pinecone_index", return_value=index), \
         patch.object(ING, "_get_embeddings_client", return_value=emb or _Emb()):
        return ING.ingest_session(**kw)


# ═══════════════════════════════════════════════════════════════════════════
# 1 — NAMESPACE: KANONSKI VLASNIČKI, NIKAD `pred_`
# ═══════════════════════════════════════════════════════════════════════════

def test_1_upsert_ide_u_kanonski_vlasnicki_namespace():
    m = _manifest()
    idx = _Index()
    n = _ingest(idx, manifest=m, session_id="sess-1",
                namespace_override=KANON_NS, verzija_dokumenta_id=VERZIJA,
                extra_metadata={"predmet_id": PREDMET, "type": "case_doc"})
    assert n == m.total_chunks
    assert idx.namespaces == {KANON_NS}, idx.namespaces


def test_1b_nijedan_upsert_ne_sme_u_pred_semu():
    """43 postojeća reda su svi u `pred_*`. Povratak te šeme je regresija."""
    m = _manifest()
    idx = _Index()
    _ingest(idx, manifest=m, session_id="sess-1",
            namespace_override=KANON_NS, verzija_dokumenta_id=VERZIJA,
            extra_metadata={"predmet_id": PREDMET, "type": "case_doc"})
    assert not any(ns.startswith("pred_") for ns in idx.namespaces)


# ═══════════════════════════════════════════════════════════════════════════
# 2 — IDENTITET: FAIL-CLOSED, BEZ TIHOG UPISA
# ═══════════════════════════════════════════════════════════════════════════

def test_2_bez_verzije_se_NE_upisuje_nista():
    idx = _Index()
    with pytest.raises(NedovoljanIdentitet):
        _ingest(idx, manifest=_manifest(), session_id="sess-2",
                namespace_override=KANON_NS, verzija_dokumenta_id=None,
                extra_metadata={"predmet_id": PREDMET})
    assert idx.upserts == [], "vektori su upisani bez identiteta"


def test_2b_nekanonska_verzija_se_odbija():
    """64-znakovni `hexdigest()` je greška koju su pisci već pravili."""
    idx = _Index()
    with pytest.raises(NedovoljanIdentitet):
        _ingest(idx, manifest=_manifest(), session_id="sess-2b",
                namespace_override=KANON_NS, verzija_dokumenta_id="a" * 64,
                extra_metadata={"predmet_id": PREDMET})
    assert idx.upserts == []


def test_2c_isti_dokument_daje_iste_ID_eve():
    """Deterministički ID je jedini razlog zbog kog ponovni upload ne duplira."""
    m = _manifest()
    a, b = _Index(), _Index()
    for idx in (a, b):
        _ingest(idx, manifest=m, session_id="druga-sesija-svaki-put",
                namespace_override=KANON_NS, verzija_dokumenta_id=VERZIJA,
                extra_metadata={"predmet_id": PREDMET})
    assert [z["id"] for z in a.svi_zapisi] == [z["id"] for z in b.svi_zapisi]


# ═══════════════════════════════════════════════════════════════════════════
# 3 — METADATA: BEZ NJE VEKTOR POSTOJI, ALI GA PRETRAGA NE VIDI
# ═══════════════════════════════════════════════════════════════════════════

def test_3_svaki_vektor_nosi_predmet_id_i_tip():
    """`retrieve_documents` filtrira po `predmet_id` + `type` (v. BR-003).
    Vektor bez tih polja je upisan, a nedohvatljiv — tiho."""
    idx = _Index()
    _ingest(idx, manifest=_manifest(), session_id="sess-3",
            namespace_override=KANON_NS, verzija_dokumenta_id=VERZIJA,
            extra_metadata={"predmet_id": PREDMET, "kancelarija_id": "",
                            "type": "case_doc"})
    assert idx.svi_zapisi
    for z in idx.svi_zapisi:
        md = z["metadata"]
        assert md.get("predmet_id") == PREDMET, md
        assert md.get("type") == "case_doc", md
        assert md.get("text"), "chunk bez teksta — pretraga ne bi imala šta da vrati"


def test_3b_pozivalac_ne_moze_da_pregazi_identitet_kroz_extra_metadata():
    """Identitet (`vx_*`) se upisuje POSLE `extra_metadata` upravo zato da ga
    pozivalac ne bi mogao da pregazi — ni greškom ni namerno. Kad bi mogao,
    `prefiks_dokumenta` više ne bi našao vektore tog dokumenta pri brisanju."""
    idx = _Index()
    _ingest(idx, manifest=_manifest(), session_id="sess-3b",
            namespace_override=KANON_NS, verzija_dokumenta_id=VERZIJA,
            extra_metadata={"predmet_id": PREDMET, "type": "case_doc",
                            "vx_verzija": "podmetnuto", "vx_scope": "podmetnuto"})
    assert idx.svi_zapisi
    for z in idx.svi_zapisi:
        assert z["metadata"]["vx_verzija"] == VERZIJA, z["metadata"]
        assert z["metadata"]["vx_scope"] == PREDMET, z["metadata"]


# ═══════════════════════════════════════════════════════════════════════════
# 4 — DELIMIČAN INGEST SE NIKAD NE PREDSTAVLJA KAO POTPUN
# ═══════════════════════════════════════════════════════════════════════════

def test_4_manje_vektora_nego_chunk_ova_diže_grešku():
    m = _manifest(TEKST * 40)
    assert m.total_chunks > 1
    idx = _Index()
    with pytest.raises(RuntimeError):
        _ingest(idx, emb=_Emb(koliko=m.total_chunks - 1), manifest=m,
                session_id="sess-4", namespace_override=KANON_NS,
                verzija_dokumenta_id=VERZIJA, extra_metadata={"predmet_id": PREDMET})
    assert idx.upserts == [], "delimičan embedding je ipak nešto upisao"


def test_4b_pad_batcha_se_propušta_pozivaocu():
    """Prvi batch je već u Pinecone-u. Pozivalac tada NE sme da tvrdi da je
    dokument indeksiran — zato izuzetak mora da izađe napolje."""
    m = _manifest(TEKST * 800)
    assert m.total_chunks > 50, m.total_chunks   # BATCH_SIZE=50 -> bar dva batcha
    idx = _Index(puca_od_batcha=1)
    with pytest.raises(RuntimeError):
        _ingest(idx, manifest=m, session_id="sess-4b",
                namespace_override=KANON_NS, verzija_dokumenta_id=VERZIJA,
                extra_metadata={"predmet_id": PREDMET})


@pytest.mark.parametrize("upisano,ocekivano,ishod", [
    (5, 5, True), (4, 5, False), (0, 0, False), (0, 3, False), (3, 0, False),
])
def test_4c_ingest_je_potpun_je_fail_closed(upisano, ocekivano, ishod):
    assert ING.ingest_je_potpun(upisano, ocekivano) is ishod


# ═══════════════════════════════════════════════════════════════════════════
# 5 — SPOJ: ONO ŠTO PIŠE U BAZI MORA ODGOVARATI ONOME ŠTO JE U PINECONE-U
# ═══════════════════════════════════════════════════════════════════════════
#
# Ovo je tačka na kojoj se BR-001 stvarno rešava. Ingest može da radi savršeno,
# a red u `predmet_dokumenti` da tvrdi nešto drugo — i advokat vidi tvrdnju iz
# baze, ne stanje Pinecone-a.

class _Q:
    def __init__(self, ime, zapis):
        self.ime, self.zapis, self.f, self.op, self.payload = ime, zapis, {}, "select", None

    def select(self, *a, **k): self.op = "select"; return self
    def insert(self, row, *a, **k): self.op, self.payload = "insert", row; return self
    def update(self, row, *a, **k): self.op, self.payload = "update", row; return self
    def eq(self, k, v): self.f[k] = v; return self
    def in_(self, k, v): self.f[k] = list(v); return self
    def neq(self, *a, **k): return self
    def order(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def single(self): return self
    def maybe_single(self): return self

    def execute(self):
        if self.op == "insert":
            if self.ime == "predmet_dokumenti":
                self.zapis["red"] = dict(self.payload)
                return MagicMock(data=[{"id": "dok-1"}])
            return MagicMock(data=[{"id": "x"}])
        if self.op == "update":
            return MagicMock(data=[])
        if self.ime == "predmeti":
            if self.f.get("id"):
                return MagicMock(data={"id": PREDMET, "naziv": "kontrolni", "tip": "opsti"})
            return MagicMock(data=[{"id": PREDMET}])
        if self.ime in ("kancelarije", "kancelarija_clanovi"):
            return MagicMock(data=None)     # solo advokat -> user_{uid}
        return MagicMock(data=[])


class _Storage:
    def from_(self, *a, **k): return self
    def upload(self, *a, **k): raise RuntimeError("storage isključen u testu")
    def remove(self, *a, **k): return None


class _Supa:
    def __init__(self, zapis):
        self.zapis, self.storage = zapis, _Storage()

    def table(self, ime):
        return _Q(ime, self.zapis)


def _docx_bajtovi(tekst=TEKST):
    from docx import Document
    d = Document()
    for p in tekst.split(". "):
        if p.strip():
            d.add_paragraph(p.strip() + ".")
    b = io.BytesIO()
    d.save(b)
    return b.getvalue()


class _Fajl:
    def __init__(self, sadrzaj):
        self.filename = "br001.docx"
        self.content_type = ("application/vnd.openxmlformats-officedocument"
                             ".wordprocessingml.document")
        self._b = sadrzaj

    async def read(self):
        return self._b


def _vozi_rutu(index, emb=None, tekst=TEKST):
    """Vozi PRAVU `predmet_upload_auto_analyze` do kraja upisa u bazu.

    Zamenjeno je samo ono što nije predmet merenja: auth, entitlement, baza,
    naplata i GPT. Ekstrakcija, chunk-ovanje, identitet, izbor namespace-a,
    ingest i odluka o statusu su STVARNI.
    """
    import api
    zapis = {}
    supa = _Supa(zapis)
    korisnik = types.SimpleNamespace(id=UID, email="br001@test.local")

    async def _auth(_a):
        return korisnik

    def _require(_n):
        async def _f(user=None, **k):
            return user
        return _f

    async def _consume(*a, **k):
        return 100

    def _oai(*a, **k):
        kl = MagicMock()
        por = MagicMock()
        por.content = json.dumps({"procena": "t"})
        kl.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=por)],
            usage=MagicMock(prompt_tokens=1, completion_tokens=1))
        return kl

    ruta = api.predmet_upload_auto_analyze
    while hasattr(ruta, "__wrapped__"):
        ruta = ruta.__wrapped__

    zahtev = MagicMock()
    zahtev.client = MagicMock(host="127.0.0.1")

    with patch.object(api, "_require_auth_async", _auth), \
         patch.object(api.PermissionService, "require", staticmethod(_require)), \
         patch.object(api, "_get_supa", lambda: supa), \
         patch.object(api.UsageService, "consume", _consume), \
         patch.object(ING, "_get_pinecone_index", return_value=index), \
         patch.object(ING, "_get_embeddings_client", return_value=emb or _Emb()), \
         patch("openai.OpenAI", _oai), \
         patch("app.services.retrieve.retrieve_documents", return_value=([], {})):
        try:
            asyncio.run(ruta(PREDMET, zahtev, _Fajl(_docx_bajtovi(tekst)), "Bearer t"))
        except BaseException as e:
            zapis["izuzetak"] = e
    return zapis


def test_5_uspesan_ingest_daje_status_indeksirano_i_isti_namespace():
    idx = _Index()
    z = _vozi_rutu(idx)
    red = z.get("red")
    assert red, f"predmet_dokumenti insert se nije desio: {z.get('izuzetak')!r}"
    assert red["status"] == "indeksirano", red["status"]
    assert red["pinecone_namespace"] == KANON_NS, red["pinecone_namespace"]
    # SPOJ: baza i Pinecone moraju govoriti o istom mestu.
    assert idx.namespaces == {red["pinecone_namespace"]}, (idx.namespaces, red)
    assert red.get("content_sha256"), "bez heša sadržaja nema ni dedupa ni brisanja"


def test_5b_ruta_nikad_ne_upisuje_pred_namespace():
    idx = _Index()
    red = _vozi_rutu(idx).get("red") or {}
    assert not (red.get("pinecone_namespace") or "").startswith("pred_")


def test_5c_kvota_daje_sacuvano_a_ne_indeksirano():
    """Kvota je jedino stanje u kom se dokument sme prihvatiti neindeksiran —
    i tada status MORA reći da nije pretraživ."""
    class _Puna(_Index):
        def upsert(self, vectors, namespace):
            raise RuntimeError("Max serverless index storage size exceeded")

    red = _vozi_rutu(_Puna()).get("red") or {}
    assert red.get("status") == "sacuvano", red


def test_5d_obicna_greska_ne_sme_da_proizvede_red_u_bazi():
    """Ne-kvota greška je 500. Red sa `status='sacuvano'` bi bio tihi gubitak:
    dokument stoji u listi, a nikad neće biti indeksiran niti ponovo pokušan."""
    class _Pukla(_Index):
        def upsert(self, vectors, namespace):
            raise RuntimeError("veza sa indeksom prekinuta")

    z = _vozi_rutu(_Pukla())
    assert z.get("red") is None, z.get("red")
    from fastapi import HTTPException
    assert isinstance(z.get("izuzetak"), HTTPException)
    assert z["izuzetak"].status_code == 500


def test_5f_ruta_sama_proverava_broj_upisanih_vektora():
    """MUTACIJA KOJA JE PREŽIVELA PRVI KRUG.

    Ruta ima sopstvenu proveru potpunosti (`ingest_je_potpun(count, ...)`) pored
    one unutar `ingest_session`. Kad se ta provera ukloni, nijedan od ostalih
    testova ne pada — zato što svi ostali mere slučaj u kom `ingest_session`
    DIŽE grešku. Ovde `ingest_session` uredno vraća, samo manji broj: tačno
    oblik u kom bi buduća regresija u `ingest_session` tiho proizvela dokument
    predstavljen kao pretraživ.
    """
    import api
    m = _manifest(TEKST * 40)
    assert m.total_chunks > 1

    def _polovican(manifest, session_id, **kw):
        return max(1, manifest.total_chunks - 1)

    with patch.object(ING, "ingest_session", _polovican):
        z = _vozi_rutu(_Index(), tekst=TEKST * 40)
    red = z.get("red") or {}
    assert red, f"insert se nije desio: {z.get('izuzetak')!r}"
    assert red.get("status") == "sacuvano", red


def test_5e_delimican_upis_ne_sme_da_dobije_indeksirano():
    """Embedding vrati manje vektora nego što ima chunk-ova → `ingest_session`
    diže grešku, ruta je klasifikuje kao ne-kvota → 500, bez reda u bazi.
    Ranije je ovakav dokument dobijao uredan 200 i `status='indeksirano'`."""
    m = _manifest(TEKST * 40)
    assert m.total_chunks > 1
    z = _vozi_rutu(_Index(), emb=_Emb(koliko=1), tekst=TEKST * 40)
    assert (z.get("red") or {}).get("status") != "indeksirano", z.get("red")
