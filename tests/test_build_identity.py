# -*- coding: utf-8 -*-
"""
P0-A — identitet build-a (BTM-P0-04).

ŠTA OVI TESTOVI ŠTITE

Ne "da endpoint vraća 200". Štite tri svojstva bez kojih odgovor sa servera ne
može da posluži kao dokaz o tome koji build opslužuje korisnika:

  1. Odgovor SAM SEBE identifikuje kao Vindex. Tokom TASK-3D je `localhost:8000`
     vraćao HTTP 200 i bio protumačen kao Vindex, a vrtela se druga aplikacija
     ("Focus IP Core Engine"). Nijedan odgovor to nije mogao da opovrgne.

  2. SHA nikad nije POGOĐEN. Ako se ne može razrešiti, `commit` je `None` i
     `identity_proven` je `False`. Lažan identitet je gori od nikakvog, jer
     bi se na njega neko pozvao kao na dokaz da je popravka deployovana.

  3. `commit_source` prati `commit`. Vrednost bez porekla je tvrdnja, ne dokaz.

NEGATIVNA KONTROLA
`test_ng_*` testovi dokazuju da provera stvarno razlikuje ispravno od
neispravnog stanja -- da ne prolaze vakuumski.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared import build_info as bi  # noqa: E402

_SVE_SHA_PROMENLJIVE = bi._SHA_ENV_KEYS + bi._BRANCH_ENV_KEYS + ("ENVIRONMENT", "BUILD_TIMESTAMP")


@pytest.fixture(autouse=True)
def _vrati_kes_posle_svakog_testa():
    """`refresh()` menja modul-globalni kes.

    Bez vraćanja, poslednji test koji je radio sa lažnim okruženjem ostavlja
    zatrovan `_BUILD_INFO` svemu što se izvršava posle njega -- uključujući
    `/health` u drugim test fajlovima. Ovo je ista klasa greške koju smo već
    imali sa stale assertion-ima: test koji menja globalno stanje i ne vraća ga.
    """
    sacuvano = bi._BUILD_INFO
    yield
    bi._BUILD_INFO = sacuvano


@pytest.fixture
def cisto_okruzenje(monkeypatch):
    """Uklanja svaki spoljni izvor identiteta.

    Bez ovoga bi testovi merili okruženje u kome se slučajno izvršavaju (CI
    postavlja neke od ovih promenljivih), a ne ponašanje koda.
    """
    for k in _SVE_SHA_PROMENLJIVE:
        monkeypatch.delenv(k, raising=False)
    return monkeypatch


# ─── 1. IDENTITET APLIKACIJE ────────────────────────────────────────────────

def test_a_odgovor_nosi_ime_aplikacije():
    """Bez ovoga se Vindex ne razlikuje od bilo koje druge FastAPI aplikacije."""
    assert bi.get_build_info()["app"] == "vindex-ai"


def test_a2_health_i_version_tvrde_isti_identitet():
    """Dva endpointa ne smeju da tvrde različit identitet."""
    from shared.build_info import APP_NAME
    assert bi.get_build_info()["app"] == APP_NAME


# ─── 2. SHA SE NIKAD NE POGAĐA ──────────────────────────────────────────────

def test_b_bez_ijednog_izvora_sha_je_none_a_ne_izmisljen(cisto_okruzenje, tmp_path):
    """Kad se SHA ne može razrešiti, vraća se `None`, ne pogođena vrednost."""
    cisto_okruzenje.setattr(bi, "_BASE_DIR", tmp_path)   # nema .git
    info = bi.refresh()
    assert info["commit"] is None
    assert info["commit_short"] is None
    assert info["commit_source"] == "unknown"
    assert bi.build_identity_proven() is False


def test_b2_smece_u_promenljivoj_se_odbija(cisto_okruzenje, tmp_path):
    """Pogrešno postavljena promenljiva ne sme da prođe kao identitet build-a.

    Ovo je stvarni rizik: `GIT_SHA=$GIT_SHA` u nepopunjenom šablonu daje
    doslovan string, a ne SHA.
    """
    cisto_okruzenje.setattr(bi, "_BASE_DIR", tmp_path)
    for smece in ("$GIT_SHA", "unknown", "latest", "", "   ", "nije-sha", "zzzzzzz"):
        cisto_okruzenje.setenv("GIT_SHA", smece)
        info = bi.refresh()
        assert info["commit"] is None, f"prihvaćeno smeće: {smece!r}"
        assert info["commit_source"] == "unknown"


def test_b3_ispravan_sha_prolazi_i_nosi_poreklo(cisto_okruzenje, tmp_path):
    cisto_okruzenje.setattr(bi, "_BASE_DIR", tmp_path)
    cisto_okruzenje.setenv("GIT_SHA", "790d6704" + "a" * 32)
    info = bi.refresh()
    assert info["commit"] == "790d6704" + "a" * 32
    assert info["commit_short"] == "790d670"
    assert info["commit_source"] == "GIT_SHA"
    assert bi.build_identity_proven() is True


# ─── 3. PLATFORMSKE PROMENLJIVE — zašto P0-A ne zavisi ni od koga ───────────

@pytest.mark.parametrize("kljuc", ["RENDER_GIT_COMMIT", "RAILWAY_GIT_COMMIT_SHA"])
def test_c_platforma_sama_daje_sha_bez_ikakve_konfiguracije(cisto_okruzenje, tmp_path, kljuc):
    """Render i Railway postavljaju ove same. Ako ovaj test padne, P0-A opet
    zavisi od ručnog podešavanja u dashboard-u -- što je bio ceo problem."""
    cisto_okruzenje.setattr(bi, "_BASE_DIR", tmp_path)
    cisto_okruzenje.setenv(kljuc, "b" * 40)
    info = bi.refresh()
    assert info["commit"] == "b" * 40
    assert info["commit_source"] == kljuc


def test_c2_eksplicitni_git_sha_ima_prednost_nad_platformskim(cisto_okruzenje, tmp_path):
    """Ako oba postoje, naš namerno injektovan pobeđuje."""
    cisto_okruzenje.setattr(bi, "_BASE_DIR", tmp_path)
    cisto_okruzenje.setenv("GIT_SHA", "a" * 40)
    cisto_okruzenje.setenv("RENDER_GIT_COMMIT", "b" * 40)
    assert bi.refresh()["commit_source"] == "GIT_SHA"


# ─── 4. .git FALLBACK ───────────────────────────────────────────────────────

def test_d_cita_git_dir_kad_nema_promenljivih(cisto_okruzenje, tmp_path):
    """Produkcioni image nosi .git jer Dockerfile nema .dockerignore.

    Ako to neko kasnije doda, ova grana tiho prestaje da radi -- ali
    `commit_source` će to odmah pokazati kao `unknown`, a ne prećutati.
    """
    g = tmp_path / ".git"
    (g / "refs" / "heads").mkdir(parents=True)
    (g / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (g / "refs" / "heads" / "main").write_text("c" * 40 + "\n", encoding="utf-8")
    cisto_okruzenje.setattr(bi, "_BASE_DIR", tmp_path)
    info = bi.refresh()
    assert info["commit"] == "c" * 40
    assert info["commit_source"] == "git-dir"
    assert info["branch"] == "main"


def test_d2_packed_refs(cisto_okruzenje, tmp_path):
    """Sveže kloniran repo drži ref u packed-refs, ne kao zaseban fajl."""
    g = tmp_path / ".git"
    g.mkdir()
    (g / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (g / "packed-refs").write_text(
        "# pack-refs with: peeled fully-peeled sorted\n"
        + "d" * 40 + " refs/heads/main\n"
        + "e" * 40 + " refs/remotes/origin/main\n",
        encoding="utf-8",
    )
    cisto_okruzenje.setattr(bi, "_BASE_DIR", tmp_path)
    info = bi.refresh()
    assert info["commit"] == "d" * 40
    assert info["commit_source"] == "git-dir-packed"


def test_d3_detached_head(cisto_okruzenje, tmp_path):
    g = tmp_path / ".git"
    g.mkdir()
    (g / "HEAD").write_text("f" * 40 + "\n", encoding="utf-8")
    cisto_okruzenje.setattr(bi, "_BASE_DIR", tmp_path)
    assert bi.refresh()["commit"] == "f" * 40


# ─── 5. ENVIRONMENT: deklarisano ≠ podrazumevano ────────────────────────────

def test_e_nepostavljen_environment_se_ne_predstavlja_kao_namerno(cisto_okruzenje, tmp_path):
    """`ENVIRONMENT` ne postoji u .env, a `api.py:46` pada na "production".

    Bez `environment_declared` te dve situacije izgledaju identično, pa se
    lokalne greške tiho prijavljuju kao produkcione (RG-11).
    """
    cisto_okruzenje.setattr(bi, "_BASE_DIR", tmp_path)
    info = bi.refresh()
    assert info["environment"] == "production"
    assert info["environment_declared"] is False

    cisto_okruzenje.setenv("ENVIRONMENT", "staging")
    info = bi.refresh()
    assert info["environment"] == "staging"
    assert info["environment_declared"] is True


# ─── 6. built_at se ne izmišlja ─────────────────────────────────────────────

def test_f_built_at_je_none_bez_eksplicitnog_injektovanja(cisto_okruzenje, tmp_path):
    """Namerno se NE pogađa iz mtime-a: to meri kada je kod kopiran, ne kada
    je napravljen. Lažan timestamp je gori od nikakvog."""
    cisto_okruzenje.setattr(bi, "_BASE_DIR", tmp_path)
    assert bi.refresh()["built_at"] is None
    cisto_okruzenje.setenv("BUILD_TIMESTAMP", "2026-08-11T09:00:00Z")
    assert bi.refresh()["built_at"] == "2026-08-11T09:00:00Z"


# ─── 7. sw_cache — otkrivanje razlaza frontenda i backenda ──────────────────

def test_g_sw_cache_se_cita_iz_stvarnog_sw_js():
    """Backend i frontend se deploy-uju zajedno ali keširaju odvojeno.
    `sw_cache` je jedini način da se taj razlaz uopšte primeti."""
    bi.refresh()
    val = bi.get_build_info()["sw_cache"]
    assert val is not None and val.startswith("vindex-v"), (
        "static/sw.js::CACHE_NAME se više ne može pročitati -- ako je format "
        "promenjen, ovaj test treba prepisati oko novog, ne obrisati"
    )


# ─── 8. NEGATIVNA KONTROLA ──────────────────────────────────────────────────

def test_ng_provera_identiteta_stvarno_razlikuje(cisto_okruzenje, tmp_path):
    """Dokaz da `build_identity_proven()` nije uvek `True`.

    Bez ovoga bi svi gornji testovi mogli da prolaze čak i da funkcija
    bezuslovno vraća `True` -- tj. da ne meri ništa.
    """
    cisto_okruzenje.setattr(bi, "_BASE_DIR", tmp_path)
    bi.refresh()
    assert bi.build_identity_proven() is False, "bez ijednog izvora mora biti False"

    cisto_okruzenje.setenv("GIT_SHA", "a" * 40)
    bi.refresh()
    assert bi.build_identity_proven() is True, "sa ispravnim SHA mora biti True"


def test_ng_kes_se_ne_moze_izmeniti_spolja():
    """`get_build_info()` vraća kopiju -- pozivalac ne sme da zatruje kes."""
    bi.refresh()
    a = bi.get_build_info()
    a["commit"] = "zatrovano"
    assert bi.get_build_info()["commit"] != "zatrovano"


# ─── 9. UGOVOR ENDPOINT-A ───────────────────────────────────────────────────

def test_h_version_endpoint_ne_izlaze_infrastrukturu():
    """`/api/version` je javan. Ne sme da nosi pid, worker-e ni putanje."""
    info = bi.get_build_info()
    zabranjeno = {"pid", "workers", "redis", "path", "cwd", "base_dir", "env"}
    assert not (set(info.keys()) & zabranjeno), (
        f"build_info nosi infrastrukturno polje: {set(info.keys()) & zabranjeno}"
    )


def test_h3_cache_busting_fallback_ne_lici_na_commit(cisto_okruzenje, tmp_path):
    """`?v=` vrednost ne sme da se lažno predstavlja kao git hash.

    Ranija implementacija (`api.py`, pre P0-A) je na grešci vraćala
    `str(int(time.time()))[-6:]` -- šestocifren broj koji izgleda kao skraćen
    SHA. A `python:3.11-slim` nema `git` binarni fajl, pa je u produkciji ta
    grana bila JEDINA koja se izvršavala. Vrednost koja se lažno predstavlja
    kao identitet je gora od izostanka identiteta.
    """
    import importlib
    cisto_okruzenje.setattr(bi, "_BASE_DIR", tmp_path)
    bi.refresh()
    assert bi.get_build_info()["commit_short"] is None

    api = importlib.import_module("api")
    val = api._get_git_hash()
    assert val.startswith("nover-"), (
        f"fallback vrednost {val!r} ne kaže da identitet nije dokazan"
    )
    assert not bi._SHA_RE.match(val), "fallback i dalje liči na git SHA"


def test_h4_cache_busting_koristi_pravi_sha_kad_postoji(cisto_okruzenje, tmp_path):
    import importlib
    cisto_okruzenje.setattr(bi, "_BASE_DIR", tmp_path)
    cisto_okruzenje.setenv("GIT_SHA", "a1b2c3d" + "0" * 33)
    bi.refresh()
    api = importlib.import_module("api")
    assert api._get_git_hash() == "a1b2c3d"


def test_h2_obavezna_polja_postoje():
    info = bi.get_build_info()
    for polje in ("app", "commit", "commit_short", "commit_source", "branch",
                  "built_at", "started_at", "environment", "environment_declared",
                  "python", "sw_cache"):
        assert polje in info, f"nedostaje {polje}"
