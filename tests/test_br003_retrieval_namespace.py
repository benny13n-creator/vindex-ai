# -*- coding: utf-8 -*-
"""
BR-003 — VLASNIČKI NAMESPACE MORA STIĆI DO RETRIEVAL-A.

ŠTA JE BILO — mereno, ne pretpostavljeno

`retrieve_documents` ima **14 produkcijskih pozivalaca**. `kancelarija_namespace`
prosleđivao je **tačno jedan** — auto-analiza u `api.py:5476`, unutar same
upload rute. Za svako normalno pitanje advokata namespace je bio `None`, pa se
grana koja pretražuje vlasnikov prostor **nikad nije izvršila**.

Posledica: dokumenti advokata nisu bili u opsegu pretrage ni kad su uredno
indeksirani. Jedini trenutak kad je sistem gledao u njih bila je auto-analiza
odmah posle upload-a.

ZAŠTO PARAMETAR NIJE PROVUČEN KROZ 14 POZIVA

Parametar koji svako mora da se seti da prosledi je isti onaj koji je ovde
zaboravljen 13 puta. Identitet se zato uzima sa mesta na kom ga sistem već ima:
iz `set_request_context(user_id=...)`, koju postavljaju auth choke point-i iz
**verifikovanog JWT `sub`**.

ZAŠTO OVI TESTOVI NISU „retrieve_documents(namespace=...)"

Test koji sam prosledi namespace dokazuje da ga funkcija **ume da primi** — a
upravo je to bila rupa: 6 postojećih testova radi tačno to i nijedan nije
uhvatio da ga niko ne prosleđuje. Ovde se namespace nikad ne prosleđuje ručno;
postavlja se **identitet**, a meri se **šta je stiglo do Pinecone sloja**.
"""
import os
import sys
from unittest.mock import MagicMock, patch

os.environ.setdefault("FOUNDER_EMAILS", "founder@test.com")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

_KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _KOREN)

import pytest  # noqa: E402

from app.services import retrieve as R  # noqa: E402
from shared import ai_provenance as PROV  # noqa: E402

UID_A = "aaaaaaaa-0000-0000-0000-000000000001"
UID_B = "bbbbbbbb-0000-0000-0000-000000000002"
PRED_A = "pred-a-1"
PRED_B = "pred-b-1"
UID_C = "cccccccc-0000-0000-0000-000000000003"
UID_D = "dddddddd-0000-0000-0000-000000000004"
PRED_C = "pred-c-1"


class _Supa:
    """Lažni Supabase: A pripada kancelariji `kanc-a`, B je solo advokat."""

    def __init__(self, delegated=True):
        self.upiti = []
        self.delegated = delegated

    def table(self, ime):
        spolja = self

        class _Q:
            def __init__(self):
                self.ime, self.f = ime, {}

            def select(self, *a, **k):
                return self

            def eq(self, k, v):
                self.f[k] = v
                return self

            def in_(self, k, v):
                self.f[k] = list(v)
                return self

            def is_(self, k, v):
                self.f[k] = None if v == "null" else v
                return self

            def maybe_single(self):
                return self

            def limit(self, *a, **k):
                return self

            def execute(self):
                spolja.upiti.append((self.ime, dict(self.f)))
                uid = self.f.get("admin_uid") or self.f.get("user_id") or self.f.get("na_user_id")
                if self.ime == "kancelarije":
                    return MagicMock(data={"id": "kanc-a"} if uid == UID_A else None)
                if self.ime == "kancelarija_clanovi":
                    return MagicMock(data={"kancelarija_id": "kanc-a"} if uid in (UID_C, UID_D) else None)
                if self.ime == "predmeti":
                    if isinstance(self.f.get("id"), list):
                        return MagicMock(data=[{"id": x} for x in self.f["id"]])
                    if uid == UID_A:
                        return MagicMock(data=[{"id": PRED_A}])
                    if uid == UID_B:
                        return MagicMock(data=[{"id": PRED_B}])
                    if uid == UID_C:
                        return MagicMock(data=[{"id": PRED_C}])
                    return MagicMock(data=[])
                if self.ime == "predmet_delegiranja":
                    return MagicMock(data=[{"predmet_id": PRED_A}] if uid == UID_D and spolja.delegated else [])
                return MagicMock(data=[])
        return _Q()


def _kao_korisnik(uid):
    """Postavlja SAMO identitet — isto što rade auth choke point-i."""
    PROV.set_request_context(user_id=uid, correlation_id="c-test")


def _izvedi():
    """Vraća (namespace, acl) koje bi retrieval stvarno upotrebio."""
    with patch.object(R, "_vlasnicki_opseg_iz_konteksta",
                      wraps=R._vlasnicki_opseg_iz_konteksta):
        with patch("shared.deps._get_supa", return_value=_Supa()):
            return R._vlasnicki_opseg_iz_konteksta()


@pytest.fixture(autouse=True)
def _cist_kontekst():
    PROV.set_request_context(user_id=None, correlation_id="c-clean")
    yield
    PROV.set_request_context(user_id=None, correlation_id="c-clean")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 1–3 — IDENTITET → NAMESPACE, I A ≠ B
# ═══════════════════════════════════════════════════════════════════════════

def test_1_korisnik_A_dobija_svoj_namespace():
    _kao_korisnik(UID_A)
    ns, acl = _izvedi()
    assert ns == "kancelarija_kanc-a", ns
    assert acl == [PRED_A]


def test_2_korisnik_B_dobija_svoj_namespace():
    """B nije u kancelariji — kanonska šema tada daje `user_{uid}`."""
    _kao_korisnik(UID_B)
    ns, acl = _izvedi()
    assert ns == "user_" + UID_B, ns
    assert acl == [PRED_B]


def test_3_A_nikada_ne_dobija_B_namespace():
    _kao_korisnik(UID_A)
    ns_a, _ = _izvedi()
    _kao_korisnik(UID_B)
    ns_b, _ = _izvedi()
    assert ns_a != ns_b
    assert UID_B not in ns_a
    assert "kanc-a" not in ns_b


# ═══════════════════════════════════════════════════════════════════════════
# TEST 4 — PROSLEĐEN TUĐI NAMESPACE MORA BITI ODBIJEN
# ═══════════════════════════════════════════════════════════════════════════

def _sta_je_otislo_u_pinecone(prosledjen_ns=None, prosledjen_acl=None, supa=None):
    """Vozi PRAVI `retrieve_documents` i hvata namespace koji je stigao do
    Pinecone pretrage. Meri se posledica, ne argument."""
    zabelezeno = {}

    def _lazna_pretraga(vektor, ns, k, filt):
        zabelezeno["namespace"] = ns
        zabelezeno["filter"] = filt
        return []

    # Svi naplativi ulazi su zatvoreni: embedding (`_ugradi_query`) i dve LLM
    # grane (`_dekomponuj_query`, `_generiši_hyde`). `conftest.py` blokira
    # stvarne pozive ka api.openai.com — i to je ispravno: test koji zove
    # plaćeni API je nedeterminističan i naplaćuje se na račun vlasnika ključa.
    with patch("shared.deps._get_supa", return_value=supa or _Supa()), \
         patch.object(R, "_pretraga_ns", _lazna_pretraga), \
         patch.object(R, "_ugradi_query", return_value=[0.0] * 3072), \
         patch.object(R, "_dekomponuj_query", return_value=[]), \
         patch.object(R, "_generiši_hyde", return_value=""):
        try:
            R.retrieve_documents(
                "test upit", k=3,
                kancelarija_namespace=prosledjen_ns,
                dozvoljeni_predmeti=prosledjen_acl,
            )
        except BaseException:
            # Ostatak pipeline-a nije predmet ovog testa; namespace i filter su
            # zabeleženi PRE bilo kakvog daljeg koraka. `BaseException` jer je
            # `conftest.NetworkAccessBlocked` namerno izvan `Exception`.
            pass
    return zabelezeno


def test_4_prosledjen_TUDJI_namespace_se_odbija():
    """NAJVAŽNIJI BEZBEDNOSNI TEST.

    Čak i kad pozivalac eksplicitno traži tuđi prostor, pretraga mora ostati
    u prostoru autentifikovanog korisnika.
    """
    _kao_korisnik(UID_A)
    z = _sta_je_otislo_u_pinecone(prosledjen_ns="kancelarija_TUDJA")
    assert z.get("namespace") == "kancelarija_kanc-a", z
    assert z.get("namespace") != "kancelarija_TUDJA"


def test_4b_prosledjen_ACL_ne_moze_da_prosiri_opseg():
    """Pozivalac sme da SUZI skup predmeta, nikad da ga proširi."""
    _kao_korisnik(UID_A)
    z = _sta_je_otislo_u_pinecone(prosledjen_acl=[PRED_A, PRED_B, "pred-tudji"])
    dozvoljeni = (z.get("filter") or {}).get("predmet_id", {}).get("$in", [])
    assert PRED_B not in dozvoljeni, dozvoljeni
    assert "pred-tudji" not in dozvoljeni, dozvoljeni
    assert dozvoljeni == [PRED_A]


# ═══════════════════════════════════════════════════════════════════════════
# TEST 5 — PREDMETNI ACL OSTAJE AKTIVAN
# ═══════════════════════════════════════════════════════════════════════════

def test_5_acl_filter_stize_do_pinecone_upita():
    _kao_korisnik(UID_A)
    z = _sta_je_otislo_u_pinecone()
    filt = z.get("filter")
    assert filt is not None, "namespace pretražen BEZ filtera — to je rupa"
    assert filt["predmet_id"]["$in"] == [PRED_A]
    assert "case_doc" in filt["type"]["$in"]


def test_5b_korisnik_bez_predmeta_NE_pretrazuje_namespace():
    """Fail-closed: prazan ACL znači „nema šta da se traži", ne „traži sve"."""
    _kao_korisnik("cccccccc-0000-0000-0000-000000000099")
    z = _sta_je_otislo_u_pinecone()
    assert z.get("namespace") is None, z


# ═══════════════════════════════════════════════════════════════════════════
# TEST 6 — BEZ IDENTITETA NEMA VLASNIČKE PRETRAGE
# ═══════════════════════════════════════════════════════════════════════════

def test_6_bez_autentifikacije_vlasnicki_namespace_se_ne_dira():
    """Pozadinski poslovi i skripte nemaju korisnika — ponašanje ostaje
    zatečeno: vlasnikov prostor se ne pretražuje."""
    ns, acl = _izvedi()
    assert ns is None and acl is None


def test_6b_pad_razresavanja_ne_otvara_pretragu():
    """Ako razrešavanje padne, namespace mora ostati `None` — nikad „pretraži
    sve". Greška ne sme da proširi vidljivost."""
    _kao_korisnik(UID_A)

    class _Puca:
        def table(self, *a, **k):
            raise RuntimeError("baza nedostupna")

    with patch("shared.deps._get_supa", return_value=_Puca()):
        ns, acl = R._vlasnicki_opseg_iz_konteksta()
    assert ns is None and acl is None


def test_6c_no_identity_cannot_use_explicit_private_namespace_or_acl():
    z = _sta_je_otislo_u_pinecone("kancelarija_TUDJA", ["pred-tudji"])
    assert z.get("namespace") is None, z


def test_6d_failed_acl_resolution_cannot_use_explicit_private_namespace_or_acl():
    _kao_korisnik(UID_C)

    class _Puca:
        def table(self, *a, **k):
            raise RuntimeError("synthetic ACL outage")

    z = _sta_je_otislo_u_pinecone("kancelarija_TUDJA", ["pred-tudji"], supa=_Puca())
    assert z.get("namespace") is None, z


# ═══════════════════════════════════════════════════════════════════════════
# TEST 7 — SVAKI PRODUKCIJSKI POZIVALAC JE POKRIVEN
# ═══════════════════════════════════════════════════════════════════════════

def test_7_nijedan_pozivalac_ne_mora_da_prosledjuje_namespace():
    """Brava nad IZVOROM kvara.

    Ranije je ispravnost zavisila od toga da svaki pozivalac zapamti da
    prosledi `kancelarija_namespace` — i 13 od 14 nije. Sada izvođenje živi
    unutar kanonskog sloja, pa se ovaj test drži jedne činjenice: derivacija
    se poziva bezuslovno, pre grane koja pretražuje vlasnikov prostor.
    """
    import inspect
    izvor = inspect.getsource(R.retrieve_documents)
    assert "_vlasnicki_opseg_iz_konteksta()" in izvor
    poz_der = izvor.index("_vlasnicki_opseg_iz_konteksta()")
    poz_grana = izvor.index("if kancelarija_namespace:")
    assert poz_der < poz_grana, (
        "derivacija se dešava POSLE grane koja pretražuje — ne bi imala efekta"
    )


def test_7b_stara_pred_sema_se_ne_koristi_u_retrieval_sloju():
    """Migracija ne sme da se vrati na mala vrata."""
    import io as _io
    izvor = _io.open(os.path.join(_KOREN, "app", "services", "retrieve.py"),
                     encoding="utf-8").read()
    assert 'f"pred_' not in izvor
    assert "'pred_' +" not in izvor


class _Vektor:
    def __init__(self, ident, metadata, score=0.99):
        self.id = ident
        self.metadata = metadata
        self.score = score


class _FilterAwarePinecone:
    """Deterministic Pinecone adapter that actually applies metadata filters."""
    def __init__(self, namespace_rows):
        self.namespace_rows = namespace_rows
        self.queries = []

    def query(self, **kwargs):
        self.queries.append(dict(kwargs))
        matches = list(self.namespace_rows.get(kwargs.get("namespace"), []))
        filt = kwargs.get("filter") or {}
        for key, condition in filt.items():
            if isinstance(condition, dict) and "$in" in condition:
                allowed = condition["$in"]
            elif isinstance(condition, dict) and "$eq" in condition:
                allowed = [condition["$eq"]]
            else:
                continue
            matches = [m for m in matches if (m.metadata or {}).get(key) in allowed]
        from types import SimpleNamespace
        return SimpleNamespace(matches=matches[:kwargs.get("top_k", 5)])


def _synthetic_rag_run(uid, extra_namespaces, adapter, *, supa=None):
    """Run the actual retrieval function and return delivered docs + Pinecone calls."""
    _kao_korisnik(uid)
    no_client = MagicMock()
    no_client.chat.completions.create.side_effect = RuntimeError("LLM disabled in ACL test")
    with patch("shared.deps._get_supa", return_value=supa or _Supa()), \
         patch.object(R, "_get_index", return_value=adapter), \
         patch.object(R, "_ugradi_query", return_value=[0.0] * 3072), \
         patch.object(R, "_dekomponuj_query", return_value=[]), \
         patch.object(R, "_generiši_hyde", return_value=""), \
         patch.object(R, "_prosiri_query_gpt_wrapper", return_value=[]), \
         patch.object(R, "_pretraga_praksa", return_value=[]), \
         patch.object(R, "_jedan_retrieval_krug", return_value=([], {})), \
         patch.object(R, "_cohere_rerank", return_value=[]), \
         patch.object(R, "_oceni_relevantnost", return_value="RELEVANTNO"), \
         patch.object(R, "_get_client", return_value=no_client), \
         patch.object(R, "_karantin_chunka", return_value=(False, 0.0)):
        docs, meta = R.retrieve_documents(
            "sintetički ACL test", k=3, extra_namespaces=extra_namespaces,
        )
    return docs, meta, adapter.queries


def test_8_same_office_undelegated_marker_is_excluded_after_acl_fix():
    """C's owner query stays matter-filtered and the legacy extra path is excluded.

    Before the fix this exact assertion failed because the adapter returned A's
    marker from the office namespace without a matter filter.
    """
    marker_a = "SYNTH_PRIVATE_MARKER_OWNER_A_7391" + (" segment" * 12)
    marker_c = "SYNTH_PRIVATE_MARKER_OWNER_C_2846" + (" segment" * 12)
    adapter = _FilterAwarePinecone({
        "firm_kanc-a": [
            _Vektor("a-office", {"type": "case_doc", "predmet_id": PRED_A,
                                  "owner_user_id": UID_A, "text": marker_a}),
            _Vektor("c-office", {"type": "case_doc", "predmet_id": PRED_C,
                                  "owner_user_id": UID_C, "text": marker_c}),
        ],
        "kancelarija_kanc-a": [
            _Vektor("a-canonical", {"type": "case_doc", "predmet_id": PRED_A,
                                     "owner_user_id": UID_A, "text": marker_a}),
            _Vektor("c-canonical", {"type": "case_doc", "predmet_id": PRED_C,
                                     "owner_user_id": UID_C, "text": marker_c}),
        ],
    })

    docs, meta, queries = _synthetic_rag_run(UID_C, ["firm_kanc-a"], adapter)
    delivered = "\n".join(docs) + "\n" + str(meta.get("doc_passages"))
    assert marker_a not in delivered, "undelegated same-office document reached retrieval output"
    assert marker_c in delivered, "positive control: C must still retrieve its own matter"


def _ab_dataset():
    marker_a = "SYNTH_PRIVATE_MARKER_OWNER_A_7391" + (" segment" * 12)
    marker_b = "SYNTH_PRIVATE_MARKER_OWNER_B_5072" + (" segment" * 12)
    marker_c = "SYNTH_PRIVATE_MARKER_OWNER_C_2846" + (" segment" * 12)
    return marker_a, marker_b, marker_c, _FilterAwarePinecone({
        "firm_kanc-a": [
            _Vektor("a-office", {"type": "case_doc", "predmet_id": PRED_A,
                                  "owner_user_id": UID_A, "text": marker_a}),
            _Vektor("c-office", {"type": "case_doc", "predmet_id": PRED_C,
                                  "owner_user_id": UID_C, "text": marker_c}),
        ],
        "kancelarija_kanc-a": [
            _Vektor("a-canonical", {"type": "case_doc", "predmet_id": PRED_A,
                                     "owner_user_id": UID_A, "text": marker_a}),
            _Vektor("c-canonical", {"type": "case_doc", "predmet_id": PRED_C,
                                     "owner_user_id": UID_C, "text": marker_c}),
        ],
        "user_" + UID_B: [
            _Vektor("b-canonical", {"type": "case_doc", "predmet_id": PRED_B,
                                     "owner_user_id": UID_B, "text": marker_b}),
        ],
        "tmp_session-a": [
            _Vektor("a-tmp", {"type": "tmp_doc", "owner_user_id": UID_A,
                               "text": marker_a}),
        ],
    }),


def test_9_owner_can_retrieve_own_persistent_matter():
    marker_a, _, _, adapter = _ab_dataset()
    docs, meta, queries = _synthetic_rag_run(UID_A, None, adapter)
    delivered = "\n".join(docs) + str(meta["doc_passages"])
    assert marker_a in delivered
    owner_query = next(q for q in queries if q.get("namespace") == "kancelarija_kanc-a")
    assert owner_query["filter"]["predmet_id"]["$in"] == [PRED_A]


def test_10_independent_tenant_gets_own_but_not_a_and_cannot_inject_office_ns():
    marker_a, marker_b, _, adapter = _ab_dataset()
    docs, meta, queries = _synthetic_rag_run(UID_B, ["firm_kanc-a", "kancelarija_kanc-a"], adapter)
    delivered = "\n".join(docs) + str(meta["doc_passages"])
    assert marker_b in delivered
    assert marker_a not in delivered
    assert not any(q.get("namespace") in {"firm_kanc-a", "kancelarija_kanc-a"} for q in queries)


def test_11_active_delegation_retrieves_only_delegated_matter():
    marker_a, _, marker_c, adapter = _ab_dataset()
    docs, meta, queries = _synthetic_rag_run(UID_D, None, adapter)
    delivered = "\n".join(docs) + str(meta["doc_passages"])
    assert marker_a in delivered
    assert marker_c not in delivered
    owner_query = next(q for q in queries if q.get("namespace") == "kancelarija_kanc-a")
    assert owner_query["filter"]["predmet_id"]["$in"] == [PRED_A]


def test_12_revoked_delegation_removes_retrieval_access():
    marker_a, _, _, adapter = _ab_dataset()
    docs, meta, queries = _synthetic_rag_run(UID_D, None, adapter, supa=_Supa(delegated=False))
    delivered = "\n".join(docs) + str(meta["doc_passages"])
    assert marker_a not in delivered
    assert not any(q.get("namespace") == "kancelarija_kanc-a" for q in queries)


def test_13_temporary_session_is_owner_filtered_for_positive_and_foreign_attempt():
    marker_a, _, _, adapter = _ab_dataset()
    docs_a, meta_a, queries_a = _synthetic_rag_run(UID_A, ["tmp_session-a"], adapter)
    delivered_a = "\n".join(docs_a) + str(meta_a["doc_passages"])
    assert marker_a in delivered_a
    q_a = next(q for q in queries_a if q.get("namespace") == "tmp_session-a")
    assert q_a["filter"] == {"owner_user_id": {"$eq": UID_A}}

    adapter.queries.clear()
    docs_c, meta_c, queries_c = _synthetic_rag_run(UID_C, ["tmp_session-a"], adapter)
    delivered_c = "\n".join(docs_c) + str(meta_c["doc_passages"])
    assert marker_a not in delivered_c
    q_c = next(q for q in queries_c if q.get("namespace") == "tmp_session-a")
    assert q_c["filter"] == {"owner_user_id": {"$eq": UID_C}}


def test_14_missing_identity_skips_private_tmp_retrieval():
    marker_a, _, _, adapter = _ab_dataset()
    docs, meta, queries = _synthetic_rag_run(None, ["tmp_session-a"], adapter)
    delivered = "\n".join(docs) + str(meta["doc_passages"])
    assert marker_a not in delivered
    assert not any(q.get("namespace") == "tmp_session-a" for q in queries)


def test_15_failed_acl_resolution_skips_persistent_private_retrieval():
    marker_a, _, _, adapter = _ab_dataset()

    class _Puca:
        def table(self, *args, **kwargs):
            raise RuntimeError("synthetic authorization lookup failure")

    docs, meta, queries = _synthetic_rag_run(UID_C, ["firm_kanc-a"], adapter, supa=_Puca())
    delivered = "\n".join(docs) + str(meta["doc_passages"])
    assert marker_a not in delivered
    assert not any(q.get("namespace") in {"firm_kanc-a", "kancelarija_kanc-a"} for q in queries)
