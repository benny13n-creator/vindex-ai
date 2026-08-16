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


class _Supa:
    """Lažni Supabase: A pripada kancelariji `kanc-a`, B je solo advokat."""

    def __init__(self):
        self.upiti = []

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

            def maybe_single(self):
                return self

            def limit(self, *a, **k):
                return self

            def execute(self):
                spolja.upiti.append((self.ime, dict(self.f)))
                uid = self.f.get("admin_uid") or self.f.get("user_id")
                if self.ime == "kancelarije":
                    return MagicMock(data={"id": "kanc-a"} if uid == UID_A else None)
                if self.ime == "kancelarija_clanovi":
                    return MagicMock(data=None)
                if self.ime == "predmeti":
                    if uid == UID_A:
                        return MagicMock(data=[{"id": PRED_A}])
                    if uid == UID_B:
                        return MagicMock(data=[{"id": PRED_B}])
                    return MagicMock(data=[])
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

def _sta_je_otislo_u_pinecone(prosledjen_ns=None, prosledjen_acl=None):
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
    with patch("shared.deps._get_supa", return_value=_Supa()), \
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
    _kao_korisnik("cccccccc-0000-0000-0000-000000000003")
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
