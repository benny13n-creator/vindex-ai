# -*- coding: utf-8 -*-
"""
RC Cold Start — pomoćni pokretač za dokaze u SVEŽEM PROCESU.

ZAŠTO OVAJ FAJL POSTOJI

Sve što je Wave 8-10 dokazao, dokazao je unutar JEDNOG već zagrejanog pytest
procesa: `tests/conftest.py` je uvezao `api`, patch je bio instaliran, limiter
je već postojao, a svaki test je posle toga merio stanje koje je neko drugi
napravio. Takav dokaz ne razlikuje „popravka radi" od „popravka radi zato što
je nešto ranije u istoj sesiji slučajno postavilo stanje kakvo treba".

Ovaj modul izvršava pojedinačne provere u procesu koji NIJE ništa nasledio, i
ispisuje rezultat kao JSON u POSLEDNJEM redu na stdout. Ne tvrdi ništa — samo
meri. Tvrdnje su u `tests/test_rc_cold_start.py`, koji ovaj izlaz parsira.

ZAŠTO JSON U POSLEDNJEM REDU, A NE exit kod
Exit kod nosi jedan bit. Kad `import api` padne (a to je jedan od mogućih
ishoda koji se traži da bude PRIJAVLJEN, ne zaobiđen), potreban je tačan modul
i red — pa se i izuzetak vraća kao podatak, sa `traceback`-om.

SIGURNOST
Ovaj skript se NIKAD ne sme pokrenuti sa produkcionim okruženjem. Pozivalac je
dužan da prosledi sanitizovan `env`; skript to i sam proverava preko
`tests/prod_db_guard.py` i odbija da uradi bilo šta ako konfiguracija miriše na
produkciju (fail-closed, isti kriterijum koji `conftest.py` primenjuje na
pytest). Nijedna vrednost kredencijala se nikad ne ispisuje.
"""
import json
import os
import sys
import traceback

KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if KOREN not in sys.path:
    sys.path.insert(0, KOREN)
_TESTOVI = os.path.join(KOREN, "tests")
if _TESTOVI not in sys.path:
    sys.path.insert(0, _TESTOVI)


# ── Kapija ───────────────────────────────────────────────────────────────────
def _proveri_okruzenje() -> list:
    """Razlozi zbog kojih je TRENUTNO okruženje produkciono (prazno = čisto).

    Namerno se poziva POSLE `load_dotenv()`, jer `api.py:23` radi isto — pa je
    jedino merodavno stanje ono koje `api.py` zaista vidi. `override=False` je
    podrazumevano ponašanje `python-dotenv`, tj. sanitizovane vrednosti koje je
    pozivalac prosledio pobeđuju nad `.env`-om; ova provera je dokaz te tvrdnje,
    ne pretpostavka o njoj.
    """
    try:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=os.path.join(KOREN, ".env"), override=False)
    except ImportError:
        pass
    from prod_db_guard import proveri_konfiguraciju
    return proveri_konfiguraciju(os.environ)


# ── Pojedinačni zadaci ───────────────────────────────────────────────────────
_CHAT = ("openai.resources.chat.completions.completions", ("Completions", "AsyncCompletions"))
_EMBED = ("openai.resources.embeddings", ("Embeddings", "AsyncEmbeddings"))
_STT = ("openai.resources.audio.transcriptions", ("Transcriptions", "AsyncTranscriptions"))
_TTS = ("openai.resources.audio.speech", ("Speech", "AsyncSpeech"))


def _markeri_na_sdk_klasama() -> dict:
    """Da li SVAKA presretnuta SDK metoda stvarno nosi `_vindex_guarded`.

    Ovo je jedina provera koja razlikuje „status kaže da je aktivno" od „metode
    su stvarno zamenjene". Wave 4 postoji zato što je zastavica umela da laže;
    zastavicu proveravamo posebno, a ovo je nezavisan izvor iste tvrdnje.
    """
    import importlib
    out = {}
    for putanja, imena in (_CHAT, _EMBED, _STT, _TTS):
        modul = importlib.import_module(putanja)
        for ime in imena:
            klasa = getattr(modul, ime)
            out[f"{ime}.create"] = bool(getattr(klasa.create, "_vindex_guarded", False))
    return out


def zadatak_env() -> dict:
    """R0 — dokaz da sanitizacija okruženja radi u podprocesu."""
    return {"razlozi": _proveri_okruzenje()}


def zadatak_gov() -> dict:
    """R1 — `import api` u svežem procesu instalira governance patch."""
    import api  # noqa: F401  (uvoz JE merena radnja: pokreće oba patch-a)
    from shared.ai_client import governance_status

    return {
        "status": governance_status(),
        "markeri": _markeri_na_sdk_klasama(),
        "api_version_governance": api.api_version()["governance"],
    }


def zadatak_failclosed() -> dict:
    """R2 — neuspeh uvoza SDK klasa zatvara AI granicu, u svežem procesu.

    NAMERNO ne uvozi `api`: traži se da fail-closed politika važi bez ijednog
    prethodnog patch-a. `openai` se uvozi PRVI da bi paket bio ceo u
    `sys.modules`; tek onda se podmeće modul koji puca na `getattr`, jer bi
    obrnut redosled dozvolio da uvoz paketa prepiše podmetnuti unos.
    """
    import types

    import openai

    class _PukliModul(types.ModuleType):
        def __getattr__(self, ime):
            raise ImportError(f"simulirani pad SDK uvoza: {ime}")

    sys.modules[_CHAT[0]] = _PukliModul(_CHAT[0])

    import shared.ai_client as ac

    pre = ac.governance_status()
    ac._patch_prompt_guard()
    posle = ac.governance_status()

    konstrukcija = {}
    for ime in ("OpenAI", "AsyncOpenAI", "AzureOpenAI", "AsyncAzureOpenAI"):
        klasa = getattr(openai, ime, None)
        if klasa is None:
            konstrukcija[ime] = "NEMA_KLASE"
            continue
        try:
            klasa(api_key="sk-test-only", azure_endpoint="https://fake.invalid",
                  api_version="2024-12-01-preview")
            konstrukcija[ime] = "KONSTRUISAN"
        except ac.GovernanceUnavailable:
            konstrukcija[ime] = "GovernanceUnavailable"
        except Exception as exc:  # noqa: BLE001 — ime klase je podatak, ne ishod
            konstrukcija[ime] = type(exc).__name__

    return {"pre": pre, "posle": posle, "konstrukcija": konstrukcija}


def _snimi_brojace(lim) -> dict:
    """Stanje brojača limitera, bez pretpostavki o internim imenima.

    Gleda i `_storage` i `_fallback_storage` — drugi postoji samo uz
    `in_memory_fallback_enabled=True` i ima SVOJE brojače koje `_storage.reset()`
    ne dira (v. `shared/rate.py::reset_limiter_state`).
    """
    out = {}
    for ime in ("_storage", "_fallback_storage"):
        st = getattr(lim, ime, None)
        if st is None:
            out[ime] = None
            continue
        d = getattr(st, "storage", None)
        ev = getattr(st, "events", None)
        out[ime] = {
            "tip": type(st).__name__,
            "kljuceva": len(d) if d is not None else None,
            "zbir": sum(int(v) for v in d.values()) if d else 0,
            "dogadjaja": len(ev) if ev is not None else None,
        }
    return out


def zadatak_rate() -> dict:
    """R3 — jedna kanonska Limiter instanca, bez ijednog `importlib.reload`."""
    import api
    import routers.drafting as drafting
    import routers.strategija as strategija
    import shared.rate as rate

    kanon = rate.limiter
    potrosaci = {
        "shared.rate.limiter": kanon,
        "api.limiter": getattr(api, "limiter", None),
        "api.app.state.limiter": getattr(api.app.state, "limiter", None),
        "routers.strategija.limiter": getattr(strategija, "limiter", None),
        "routers.drafting.limiter": getattr(drafting, "limiter", None),
    }
    return {
        "isti_objekat": {k: (v is kanon) for k, v in potrosaci.items()},
        "idovi": {k: (id(v) if v is not None else None) for k, v in potrosaci.items()},
        "broj_razlicitih": len({id(v) for v in potrosaci.values() if v is not None}),
        "brojaci": _snimi_brojace(kanon),
        "key_func": getattr(getattr(kanon, "_key_func", None), "__name__", None),
    }


def _lazni_odgovor():
    from unittest.mock import MagicMock
    r = MagicMock()
    r.usage = None
    r.model = "gpt-4o"
    poruka = MagicMock()
    poruka.content = "Rok je 15 dana."
    poruka.tool_calls = None
    izbor = MagicMock()
    izbor.message = poruka
    r.choices = [izbor]
    return r


def zadatak_nesting() -> dict:
    """R4 — ponovni `_patch_prompt_guard()` ne ugnežđuje wrapper.

    Obrazac je preuzet iz `tests/test_gov4_patch_lifecycle.py::test_w9_b`:
    lažni provajder se postavlja na DNO lanca (`_orig_create`) PRE drugog
    patch-a — ugnežđivanje živi upravo tamo, pa bi zamena posle njega obrisala
    ono što se meri. Zastavica `_guard_patched` se namerno zaobilazi, jer bi
    inače drugi poziv izašao odmah i test ne bi merio ništa.
    """
    import api  # noqa: F401  — sveža instalacija patch-a, kao u produkciji
    import openai
    import security.ai_forensics as forensics
    import shared.ai_client as ac

    brojac = {"n": 0}

    def _detektor(self, *a, **k):
        brojac["n"] += 1
        return _lazni_odgovor()

    async def _bez_provenance(**kwargs):
        return None

    forensics.log_provenance_from_wrapper = _bez_provenance
    ac._orig_create = _detektor
    prvi_orig = ac._orig_create

    # 1) poziv SA zastavicom — mora biti no-op
    ac._patch_prompt_guard()
    posle_noop = ac._orig_create is prvi_orig

    # 2) poziv BEZ zastavice — jedina odbrana je `_vindex_guarded` marker
    ac._guard_patched = False
    ac._patch_prompt_guard()
    posle_zaobilaska = ac._orig_create is prvi_orig

    greska = None
    try:
        openai.OpenAI(api_key="sk-test-only").chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Koji je rok za žalbu?"}],
        )
    except Exception as exc:  # noqa: BLE001 — firewall sme da odbije odgovor;
        # merimo KOLIKO PUTA je poziv stigao do dna, ne šta je vraćeno.
        greska = type(exc).__name__

    return {
        "poziva_originala": brojac["n"],
        "orig_ocuvan_posle_noop": posle_noop,
        "orig_ocuvan_posle_zaobilaska": posle_zaobilaska,
        "status": ac.governance_status(),
        "greska_poziva": greska,
    }


ZADACI = {
    "env": zadatak_env,
    "gov": zadatak_gov,
    "failclosed": zadatak_failclosed,
    "rate": zadatak_rate,
    "nesting": zadatak_nesting,
}


def izvrsi(imena: list) -> dict:
    """Izvršava zadatke REDOM i vraća rezultat svakog.

    Redosled je parametar zato što je i sam predmet dokaza (R6): ako ishod bilo
    kog zadatka zavisi od toga šta se u istom procesu izvršilo pre njega, onda
    zagrejano stanje — a ne popravka — nosi rezultat.
    """
    rezultat = {"redosled": imena, "zadaci": {}}
    for ime in imena:
        try:
            rezultat["zadaci"][ime] = {"ok": True, "podaci": ZADACI[ime]()}
        except BaseException as exc:  # noqa: BLE001 — pad je merodavan podatak
            rezultat["zadaci"][ime] = {
                "ok": False,
                "greska": type(exc).__name__,
                "poruka": str(exc)[:500],
                "traceback": traceback.format_exc()[-3000:],
            }
    return rezultat


def main(argv: list) -> int:
    if not argv:
        print("upotreba: rc_cold_start.py <zadatak>[,<zadatak>...]", file=sys.stderr)
        return 2
    imena = [i.strip() for i in argv[0].split(",") if i.strip()]
    nepoznati = [i for i in imena if i not in ZADACI]
    if nepoznati:
        print(f"nepoznat zadatak: {nepoznati}", file=sys.stderr)
        return 2

    # FAIL-CLOSED KAPIJA: nijedan zadatak se ne izvršava nad produkcionom
    # konfiguracijom. `env` zadatak je izuzet jer je on sam ta provera.
    razlozi = _proveri_okruzenje()
    if razlozi and imena != ["env"]:
        sys.stdout.write(json.dumps(
            {"redosled": imena, "prekinuto": "produkciona konfiguracija", "razlozi": razlozi},
            ensure_ascii=False,
        ) + "\n")
        return 3

    rezultat = izvrsi(imena)
    sys.stdout.flush()
    sys.stdout.write(json.dumps(rezultat, ensure_ascii=False) + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
