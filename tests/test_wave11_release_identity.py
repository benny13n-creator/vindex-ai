# -*- coding: utf-8 -*-
"""
Wave 11 — SPREGA između frontend bundle-a i imena service-worker keša.

ŠTA JE BILA RUPA
────────────────
`static/sw.js:4` nosi `CACHE_NAME = "vindex-v123"`. Service worker po tom imenu
drži precache; dok se ime ne promeni, vraćeni korisnik dobija STARI
`static/vindex.js` iz keša, bez obzira što je na serveru novi.

Dva postojeća testa mere taj broj, ali oba samo u JEDNOM smeru:
  • `tests/test_iron_lawyer_frontend_fixes.py::test_sw_cache_bumped`
    — `>= 120`, tj. „ne sme da OPADNE"
  • `tests/test_lambda001_beta_readiness_fixes.py::test_sw_cache_bumped_for_this_sprints_frontend_change`
    — `>= 92`, isto

Nijedan ne tvrdi da broj mora da PORASTE kad se `static/vindex.js` promeni. To
nije teorijski rizik: commit `f87f9e45` je izmenio `static/vindex.js` i nije
dirao `static/sw.js` (v122 → v122). Ceo suite je ostao zelen. Sledeći commit je
slučajno popravio stvar — da nije, korisnici bi u tom deploy-u dobijali stari
bundle.

ŠTA OVAJ FAJL MERI
──────────────────
Ne stanje radnog direktorijuma, nego COMMIT: šta je HEAD dirnuo u odnosu na
`HEAD~1`, i kako se između ta dva commit-a promenilo `CACHE_NAME`. Detekcija je
izdvojena u čistu funkciju `_prekrsaj(...)`, pa se ista logika može pustiti i
preko istorijskih commit-a — `test_ng_*` je pušta preko `f87f9e45` (dokazan
propust) i preko `966e0e77` (uredan bump). Bez te dve kontrole detektor bi mogao
da ne prijavljuje ništa, ili da prijavljuje sve, a da to niko ne primeti.

GRANICE
───────
  • Nema `git`-a → ceo fajl se preskače (činjenica o okruženju).
  • `HEAD~1` ne postoji (prvi commit, shallow clone) → test se preskače sa
    razlogom, ne pada.
  • Commit koji NE dira frontend → test prolazi bez ijedne tvrdnje o broju;
    normalan backend commit ne sme da traži bump.
"""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SW_PUTANJA = "static/sw.js"

# Fajlovi koje service worker keš servira korisniku. Promena bilo kog od njih
# bez novog `CACHE_NAME` znači da vraćeni korisnik i dalje vidi staru verziju.
FRONTEND_ARTEFAKTI = ("static/vindex.js", "index.html")

_CACHE_RE = re.compile(r'CACHE_NAME\s*=\s*"vindex-v(\d+)"')

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None,
    reason="git nije dostupan — sprega frontend/CACHE_NAME se ne može izmeriti",
)


def _git(*args, dozvoli_pad: bool = False):
    """`git` u korenu repoa.

    `encoding="utf-8"` je obavezan: na Windows-u `text=True` dekodira izlaz kao
    cp1252, pa bi svaki ćirilični/latinični dijakritik u imenu fajla ili poruci
    razbio parsiranje.
    """
    r = subprocess.run(
        ["git", *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    if r.returncode != 0 and not dozvoli_pad:
        raise AssertionError(f"`git {' '.join(args)}` je pao:\n{r.stderr}")
    return r


def _postoji(revizija: str) -> bool:
    return _git("rev-parse", "--verify", "--quiet", f"{revizija}^{{commit}}",
                dozvoli_pad=True).returncode == 0


def _cache_broj(sadrzaj_sw: str):
    """Broj iz `CACHE_NAME = "vindex-vN"`, ili `None` ako oblik ne odgovara."""
    m = _CACHE_RE.search(sadrzaj_sw or "")
    return int(m.group(1)) if m else None


def _sw_na(revizija: str):
    """Sadržaj `static/sw.js` u datom commit-u; `None` ako ga tamo nema."""
    r = _git("show", f"{revizija}:{SW_PUTANJA}", dozvoli_pad=True)
    return r.stdout if r.returncode == 0 else None


def _izmenjeni(od: str, do: str) -> set:
    r = _git("diff", "--name-only", od, do)
    return {l.strip() for l in r.stdout.splitlines() if l.strip()}


def _prekrsaj(izmenjeni: set, sw_pre: str, sw_posle: str):
    """Jezgro detekcije. Vraća poruku o prekršaju, ili `None` ako je sve u redu.

    Namerno je čista funkcija bez `git`-a: tako je ista logika koja gleda HEAD
    proverljiva i nad istorijskim commit-ima, bez ijedne kopije pravila.
    """
    dirnuti = sorted(set(izmenjeni) & set(FRONTEND_ARTEFAKTI))
    if not dirnuti:
        return None

    pre, posle = _cache_broj(sw_pre), _cache_broj(sw_posle)
    if posle is None:
        return (
            f"{SW_PUTANJA} više ne sadrži `CACHE_NAME = \"vindex-vN\"`; "
            "sprega sa frontend bundle-om se ne može ni izmeriti"
        )
    if pre is None:
        # sw.js je novouveden ili preimenovan — nema od čega da poraste.
        return None
    if posle > pre:
        return None
    return (
        f"commit menja {', '.join(dirnuti)}, a CACHE_NAME je ostao vindex-v{posle} "
        f"(pre: vindex-v{pre}).\n"
        f"POSLEDICA: service worker vraćenim korisnicima i dalje servira STARI "
        f"bundle iz keša — nova verzija se na njihovim uređajima ne vidi.\n"
        f"URADITI: podigni broj u {SW_PUTANJA} na vindex-v{posle + 1} i uključi "
        f"tu izmenu u ISTI commit."
    )


# ═══════════════════════════════════════════════════════════════════════════
# 1. OBLIK — bez njega sve ostalo tiho prestane da meri
# ═══════════════════════════════════════════════════════════════════════════

def test_cache_name_odgovara_obrascu_vindex_v_broj():
    """`CACHE_NAME` mora ostati `vindex-v<broj>`.

    Preimenovanje u npr. `vindex-2026-08` nije kozmetika: svaki test u repou
    koji taj broj poredi (uključujući ovaj fajl) prestao bi da meri išta.
    """
    sadrzaj = (REPO_ROOT / "static" / "sw.js").read_text(encoding="utf-8")
    m = _CACHE_RE.search(sadrzaj)
    assert m, (
        "CACHE_NAME u static/sw.js ne odgovara obrascu `vindex-v<broj>` — "
        "sprega sa frontend deploy-em se više ne može izmeriti"
    )
    assert int(m.group(1)) > 0, "verzija keša mora biti pozitivan broj"


# ═══════════════════════════════════════════════════════════════════════════
# 2. SPREGA NA HEAD COMMIT-U
# ═══════════════════════════════════════════════════════════════════════════

def test_frontend_izmena_u_HEAD_commitu_mora_podici_cache_name():
    """Ako HEAD dira `static/vindex.js` ili `index.html`, `CACHE_NAME` mora biti
    veći nego u `HEAD~1`.

    Commit koji frontend ne dira prolazi bez ijedne tvrdnje o broju — ovaj test
    ne sme da traži bump od backend izmene.
    """
    if not _postoji("HEAD"):
        pytest.skip("nema HEAD commit-a — prazan repozitorijum")
    if not _postoji("HEAD~1"):
        pytest.skip("HEAD nema roditelja (prvi commit ili shallow clone) — "
                    "nema od čega da se meri porast CACHE_NAME")

    sw_pre = _sw_na("HEAD~1")
    sw_posle = _sw_na("HEAD")
    assert sw_posle is not None, f"{SW_PUTANJA} ne postoji u HEAD commit-u"

    problem = _prekrsaj(_izmenjeni("HEAD~1", "HEAD"), sw_pre, sw_posle)
    assert problem is None, problem


# ═══════════════════════════════════════════════════════════════════════════
# 3. NEGATIVNE KONTROLE NAD SAMIM DETEKTOROM
# ═══════════════════════════════════════════════════════════════════════════
# Test iznad je zelen na svakom commit-u koji ne dira frontend — što je tačno
# ono stanje u kome bi pokvaren detektor bio nevidljiv. Zato se ista funkcija
# pušta preko dva PRAVA commit-a ovog repoa, jednog lošeg i jednog dobrog.

_PROPUST = "f87f9e45"   # menja static/vindex.js, CACHE_NAME v122 → v122
_UREDAN = "966e0e77"    # menja static/vindex.js, CACHE_NAME v122 → v123


def _scenario(commit: str):
    if not _postoji(commit) or not _postoji(f"{commit}~1"):
        pytest.skip(f"commit {commit} nije dostupan (plitak klon) — "
                    "kontrola detektora se ne može izvršiti")
    return (
        _izmenjeni(f"{commit}~1", commit),
        _sw_na(f"{commit}~1"),
        _sw_na(commit),
    )


def test_ng_detektor_hvata_stvarni_istorijski_propust():
    """`f87f9e45` je izmenio `static/vindex.js` i nije dirao `static/sw.js`.

    Tada je ceo suite bio zelen. Ako detektor ovaj commit ne prijavi kao
    prekršaj, on ne meri ništa — bez obzira što je test iznad zelen.
    """
    izmenjeni, sw_pre, sw_posle = _scenario(_PROPUST)
    assert "static/vindex.js" in izmenjeni, (
        f"{_PROPUST} više ne dira static/vindex.js — kontrola je izgubila predmet"
    )
    assert _cache_broj(sw_pre) == _cache_broj(sw_posle), (
        f"{_PROPUST} je ipak podigao CACHE_NAME — pretpostavka kontrole je pogrešna"
    )

    problem = _prekrsaj(izmenjeni, sw_pre, sw_posle)
    assert problem is not None, (
        f"detektor NE vidi dokazan propust ({_PROPUST}) — pokvaren je"
    )
    assert "vindex-v123" in problem, (
        f"poruka ne kaže koji broj treba upisati: {problem}"
    )
    assert "static/vindex.js" in problem, "poruka ne imenuje fajl koji je izmenjen"


def test_ng_detektor_ne_prijavljuje_uredan_bump():
    """`966e0e77` je izmenio frontend I podigao v122 → v123.

    Detektor koji prijavljuje SVE bio bi jednako bezvredan kao detektor koji ne
    prijavljuje ništa — samo bi ga neko brže isključio.
    """
    izmenjeni, sw_pre, sw_posle = _scenario(_UREDAN)
    assert "static/vindex.js" in izmenjeni
    assert _prekrsaj(izmenjeni, sw_pre, sw_posle) is None, (
        f"uredan bump ({_UREDAN}) je prijavljen kao prekršaj"
    )


def test_ng_backend_commit_ne_trazi_bump():
    """Commit bez ijednog frontend artefakta ne sme ništa da traži — inače bi
    ovaj fajl padao na svakom backend commit-u i bio isključen u prvoj nedelji.
    """
    assert _prekrsaj({"routers/strategija.py", "tests/test_x.py"},
                     'const CACHE_NAME = "vindex-v50";',
                     'const CACHE_NAME = "vindex-v50";') is None
