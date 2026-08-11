# -*- coding: utf-8 -*-
"""
Wave 9 — higijena repozitorijuma: §20 (secrets u .gitignore) i §18 (mrtav
security modul).

MERILO KOJE OVAJ FAJL PRIMENJUJE

Nijedan test ovde ne sme da prolazi zato što je našao string u `.gitignore`.
Čitanje obrasca nije dokaz da obrazac radi — jedini dokaz je pitati sam git
šta bi uradio (`git check-ignore`). Isto važi za §18: „fajl je obrisan" se
dokazuje odsustvom fajla I odsustvom referenci, ne komentarom.

ZAŠTO POSTOJI NEGATIVNA KONTROLA

Obrazac koji ignoriše previše je opasniji od obrasca koji ignoriše premalo:
prvi tiho briše produkcioni fajl iz build-a, drugi samo propušta smeće. Ovaj
repo je tu grešku već platio — P0-A: neanchored `build_*.py` je progutao
`shared/build_info.py` i oborio produkcioni start. Zato svaki pozitivan test
ovde ima svoj par koji dokazuje da obrazac NE hvata legitimne fajlove.
"""
import os
import subprocess

import pytest

_KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _git(*args: str, ulaz: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=_KOREN,
        input=ulaz,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _ignorisan(putanja: str) -> bool:
    """Pita GIT, ne .gitignore tekst. rc==0 znači „ignorisan"."""
    return _git("check-ignore", "-q", "--no-index", putanja).returncode == 0


# ─── §20: secrets.json JESTE ignorisan ──────────────────────────────────────

def test_secrets_json_je_ignorisan():
    assert _ignorisan("secrets.json"), (
        "secrets.json nije pokriven .gitignore-om — jedan `git add -A` bi ga "
        "commit-ovao u javni repo."
    )


@pytest.mark.parametrize("putanja", [
    "config/secrets.json",
    "app/nested/deep/secrets.json",
])
def test_secrets_json_je_ignorisan_i_u_poddirektorijumima(putanja):
    """Namerno NEanchored obrazac: secret sa tim tačnim imenom je secret na
    svakoj dubini. Da je obrazac napisan kao `/secrets.json`, ovaj test bi pao
    i rupa bi bila stvarna."""
    assert _ignorisan(putanja), f"{putanja} nije ignorisan"


@pytest.mark.parametrize("putanja", [
    "secrets.prod.json",
    "secrets.local.json",
    "api.secrets.json",
])
def test_srodni_oblici_su_ignorisani(putanja):
    assert _ignorisan(putanja), f"{putanja} nije ignorisan"


# ─── §20: NEGATIVNA KONTROLA — obrazac ne guta previše ──────────────────────

@pytest.mark.parametrize("putanja", [
    ".env.example",
    "secrets.example.json",
    "secrets.template.json",
    "secrets.sample.json",
    "app.secrets.example.json",
    "evaluation/phase_0_5/datasets/dataset_manifest.template.json",
])
def test_template_i_example_fajlovi_nisu_ignorisani(putanja):
    """Dokazuje da secrets obrazac ne pojede legitiman template.

    `secrets.*.json` bi BEZ negacija progutao `secrets.example.json` — tačno
    onaj razred greške koji je P0-A opisao. Ako neko ukloni `!` linije iz
    .gitignore-a, ovaj test pada."""
    assert not _ignorisan(putanja), (
        f"{putanja} je ignorisan — .gitignore obrazac je preširok i guta "
        f"legitiman template/example fajl."
    )


# ─── §20: generalna zaštita od `build_*.py` klase greške ────────────────────

def _tracked_ignorisani(glob: str) -> list[str]:
    """Vraća tracked fajlove koje .gitignore obrasci poklapaju.

    DVE ZAMKE, obe izmerene pri pisanju ovog testa:

    1. `--no-index` je OBAVEZAN. Bez njega `git check-ignore` po definiciji
       preskače fajlove koji su u indeksu — a to su tačno oni koje ovde
       tražimo. Test bi „prolazio" uvek i ne bi mogao da padne ni za jedan
       obrazac. Vakuumski zeleno je gore od crvenog.

    2. NUL separacija (`-z`) umesto `\\n`. Na Windows-u `subprocess` u tekst
       režimu prevodi `\\n` u `\\r\\n` pri UPISU na stdin, pa git dobija
       putanje sa repom `\\r`, ne prepoznaje ih kao tracked i prijavljuje
       lažne pogotke (prvo izvođenje ovog testa je tako prijavilo 1357
       nepostojećih sudara).
    """
    tracked = subprocess.run(
        ["git", "ls-files", "-z", glob], cwd=_KOREN, capture_output=True
    )
    assert tracked.returncode == 0, f"git ls-files pao: {tracked.stderr!r}"
    stavke = [x for x in tracked.stdout.split(b"\0") if x]
    assert stavke, f"git ls-files {glob} nije vratio nijedan fajl — test bi bio prazan"

    res = subprocess.run(
        ["git", "check-ignore", "--no-index", "-z", "--stdin"],
        cwd=_KOREN, input=b"\0".join(stavke) + b"\0", capture_output=True,
    )
    return [x.decode("utf-8", "replace") for x in res.stdout.split(b"\0") if x]


# Jednokratne skripte NA KORENU koje su ipak commit-ovane (`git add -f`).
# Obrasci `/ingest_*.py` i `/verify_*.py` ih poklapaju NAMERNO — to je
# deklarisana svrha tog bloka u .gitignore-u. Imenovane su ovde da bi bile
# svesno prihvaćeno stanje, a ne tiho izuzeće: svaki NOVI sudar pada test.
_PRIHVACENI_ROOT_SUDARI = {
    "ingest_kz.py",
    "ingest_laws.py",
    "ingest_misljenja.py",
    "verify_subquery_fix.py",
}


def test_nijedan_tracked_python_modul_nije_ignorisan():
    """Najvažniji test u fajlu i jedini koji hvata BUDUĆE preširoke obrasce.

    Ako iko ikad doda obrazac koji poklapa `.py` fajl koji je već u gitu (kao
    što je `build_*.py` poklopio `shared/build_info.py` i oborio produkcioni
    start), ovaj test pada odmah — bez obzira koji je obrazac i ko ga je dodao.

    Wave 9 je ovim testom našao 4 stvarna sudara koji su postojali pre njega:
    `scripts/ingest_{carf_dac8,case_law,ofac_sdn,web3_addendum}.py` su bili
    tracked ALI poklopljeni neanchored obrascem `ingest_*.py`. Popravljeno
    usidrenjem na koren.
    """
    sudari = [p for p in _tracked_ignorisani("*.py")
              if p not in _PRIHVACENI_ROOT_SUDARI]
    assert not sudari, (
        "Sledeći .py fajlovi su TRACKED ali ih .gitignore poklapa. Isti razred "
        "greške kao P0-A. Usidri obrazac (`/prefiks`) ili dodaj negaciju:\n  "
        + "\n  ".join(sudari[:50])
    )


def test_paketni_direktorijumi_nemaju_nijedan_ignorisan_modul():
    """Uža, oštrija varijanta: u direktorijumima iz kojih se aplikacija
    STVARNO importuje, nijedan tracked modul ne sme biti poklopljen — ovde
    nema legitimnog „one-off skripta" izuzetka, pa ni prihvaćene liste."""
    sudari = _tracked_ignorisani("*.py")
    paketi = ("shared/", "security/", "routers/", "app/", "services/",
              "klijenti/", "scripts/", "tests/")
    u_paketima = [p for p in sudari if p.startswith(paketi)]
    assert not u_paketima, (
        "Tracked moduli u paketnim direktorijumima koje .gitignore poklapa — "
        "produkcioni import bi pukao posle čistog checkout-a:\n  "
        + "\n  ".join(u_paketima)
    )


# ─── §18: mrtav security modul je uklonjen ──────────────────────────────────

def test_data_classification_modul_ne_postoji():
    """§18: modul je imao nula importera — dokumentacija je tvrdila zaštitu
    koja se nikad nije izvršila (SEC-055, W0 „declaration only"). Uklonjen je
    umesto da ostane dekorativni security sloj."""
    putanja = os.path.join(_KOREN, "security", "data_classification.py")
    assert not os.path.exists(putanja), (
        "security/data_classification.py je vraćen. Ako je vraćen namerno, mora "
        "imati STVARNOG potrošača na živoj putanji — inače je to security "
        "teatar koji dokumentacija naplaćuje kao kontrolu."
    )


def test_nijedan_python_fajl_ne_referencira_data_classification():
    """Zaštita od import-a ka nepostojećem modulu (ImportError na startu).

    Skenira SVE .py fajlove u repou, uključujući `tests/` — dinamički poziv
    preko importlib/getattr bi takođe bio pogodak, jer se traži ime modula kao
    string, ne samo `import` naredba."""
    pogodci = []
    preskoci = {".git", ".venv", "venv", "env", "data", "node_modules",
                "__pycache__", "vector_store", "nvector_store",
                "vindex_scraper_output"}
    for dirpath, dirnames, filenames in os.walk(_KOREN):
        dirnames[:] = [d for d in dirnames if d not in preskoci]
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            p = os.path.join(dirpath, fn)
            if os.path.abspath(p) == os.path.abspath(__file__):
                continue  # ovaj fajl sme da pominje ime, on ga i brani
            try:
                with open(p, encoding="utf-8", errors="replace") as fh:
                    sadrzaj = fh.read()
            except OSError:
                continue
            if "data_classification" in sadrzaj:
                pogodci.append(os.path.relpath(p, _KOREN))

    assert not pogodci, (
        "Ovi .py fajlovi referenciraju uklonjeni modul `data_classification` — "
        "import bi pukao na startu:\n  " + "\n  ".join(pogodci)
    )


def test_architecture_bible_ne_tvrdi_da_modul_postoji():
    """Dokumentacija koja navodi nepostojeću kontrolu je gora od nedostajuće
    dokumentacije — čita se kao garancija."""
    p = os.path.join(_KOREN, "docs", "architecture",
                     "VINDEX_AI_ARCHITECTURE_BIBLE_v1.0.md")
    with open(p, encoding="utf-8") as fh:
        redovi = fh.readlines()

    # Red koji nabraja security module ne sme vise da sadrzi modul.
    lista_redova = [r for r in redovi if "prompt_guard" in r or "agent_isolation" in r]
    assert lista_redova, "Nije pronađen red sa listom security modula — dokument je promenjen?"
    for r in lista_redova:
        assert "data_classification" not in r, (
            "Architecture Bible i dalje navodi data_classification kao deo "
            f"security stack-a: {r.strip()}"
        )
