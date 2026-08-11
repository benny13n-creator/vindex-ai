# -*- coding: utf-8 -*-
"""
Release Candidate — COLD START GATE.

CENTRALNO PITANJE

„Da li popravke iz Wave 8-10 rade, ili rade samo u već zagrejanom pytest
procesu koji ih je slučajno doveo u ispravno stanje?"

Sve dosadašnje tvrdnje su merene unutar jednog procesa koji je `conftest.py`
pripremio: `api` je uvezen pre prvog testa, governance patch je instaliran,
limiter je već postojao, `openai` SDK klase su već bile zamenjene. Test koji u
takvom procesu izmeri „patch je aktivan" ne razlikuje dva bitno različita
sveta — onaj u kome popravka radi i onaj u kome je stanje ostavio neko drugi.

Ovaj fajl meri isključivo PODPROCESE koji ništa nisu nasledili. Ništa se ne
zaključuje čitanjem izvornog koda: svaka tvrdnja je izlaz procesa koji je
stvarno pokrenut.

ZAŠTO SVAKI PODPROCES DOBIJA SANITIZOVAN `env`
`.env` u korenu repoa nosi ŽIVE produkcione Supabase kredencijale, a `api.py`
ih učitava na uvozu (`load_dotenv()`, red 23). `tests/conftest.py` ih poništava
— ali SAMO za pytest proces. `uvicorn api:app`, koji ovaj fajl pokreće, nije
pytest i conftest ga ne dodiruje. Zato se svakom podprocesu prosleđuje izričito
sanitizovano okruženje, a prva izmerena stvar u ovoj sesiji (`test_r0_...`) je
dokaz da je ta sanitizacija zaista preživela `load_dotenv()` unutar podprocesa.
Bez tog dokaza nijedan drugi proces se ne pokreće — fixture `sanitizovan_env`
pada fail-closed.

`encoding="utf-8"` na svakom `subprocess` pozivu nije kozmetika: `text=True` na
Windows-u podrazumeva cp1252 i lomi srpska slova u logovima i porukama grešaka,
pa bi dijagnostika pada bila nečitljiva baš kada je najpotrebnija.
"""
import base64
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

import pytest

KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_POKRETAC = os.path.join(KOREN, "scripts", "rc_cold_start.py")

# `import api` u svežem procesu traje ~8s na razvojnoj mašini (mereno). Limiti
# su postavljeni sa rezervom za sporiju mašinu/CI, ali NISU beskonačni — proces
# koji se ne digne u ovom roku je nalaz, ne „spor dan".
TIMEOUT_ZADATKA_S = 300
TIMEOUT_STARTA_S = 120
TIMEOUT_GASENJA_S = 30


# ═════════════════════════════════════════════════════════════════════════════
# Sanitizacija okruženja
# ═════════════════════════════════════════════════════════════════════════════
def _napravi_sanitizovan_env() -> dict:
    """Okruženje u kome nijedan podproces ne može da dohvati produkciju.

    `SUPABASE_DB_URL`/`DATABASE_URL` se BRIŠU, ne prepisuju: prazna vrednost bi
    i dalje bila vrednost, a `shared/*` kod na nekim mestima razlikuje „nije
    postavljeno" od „postavljeno na prazno".

    Vrednosti su iste one koje `tests/conftest.py` već koristi — `fake.supabase.co`
    nije druga baza nego domen koji ne postoji, pa ne postoji ishod u kome se
    piše u nešto stvarno.
    """
    env = dict(os.environ)
    for k in ("SUPABASE_DB_URL", "DATABASE_URL"):
        env.pop(k, None)
    env.update({
        "SUPABASE_URL": "https://fake.supabase.co",
        "SUPABASE_SERVICE_KEY": "test-only-service-key-not-a-real-jwt",
        "SUPABASE_ANON_KEY": "test-only-anon-key",
        "SUPABASE_KEY": "test-only-anon-key",
        "SUPABASE_JWT_SECRET": "test-only-jwt-secret-longer-than-32-chars",
        "OPENAI_API_KEY": "sk-test-only",
        "PINECONE_API_KEY": "test-only",
        "FIELD_ENCRYPTION_KEY": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
        "FOUNDER_EMAILS": "founder@test.rs",
        # Bez ovoga uvicorn-ov log na Windows konzoli ume da padne na srpskim
        # slovima i obori proces koji inače radi — to bi bio lažan nalaz.
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    })
    return env


def _pokreni_zadatke(imena: str, env: dict) -> dict:
    """Pokreće `scripts/rc_cold_start.py` i vraća JSON iz POSLEDNJEG reda stdout-a.

    Poslednji red, a ne ceo stdout: `api.py` na uvozu štampa i sopstvene poruke
    (npr. `[WARN] Sentry init failed`), pa bi `json.loads(stdout)` pucao na
    šumu koja nema veze sa merenjem.
    """
    r = subprocess.run(
        [sys.executable, _POKRETAC, imena],
        cwd=KOREN, env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=TIMEOUT_ZADATKA_S,
    )
    redovi = [ln for ln in (r.stdout or "").splitlines() if ln.strip()]
    assert redovi, (
        f"podproces `{imena}` nije ispisao ništa na stdout (rc={r.returncode})\n"
        f"stderr (kraj):\n{(r.stderr or '')[-3000:]}"
    )
    try:
        podaci = json.loads(redovi[-1])
    except json.JSONDecodeError as e:
        pytest.fail(
            f"poslednji red stdout-a podprocesa `{imena}` nije JSON ({e})\n"
            f"red: {redovi[-1][:500]}\nstderr (kraj):\n{(r.stderr or '')[-3000:]}"
        )
    assert "prekinuto" not in podaci, (
        f"podproces je odbio da radi: {podaci.get('prekinuto')} — {podaci.get('razlozi')}"
    )
    podaci["_rc"] = r.returncode
    podaci["_stderr"] = (r.stderr or "")[-4000:]
    return podaci


def _uzmi(rezultat: dict, ime: str) -> dict:
    """Podaci jednog zadatka; pad zadatka se prijavljuje sa tačnim traceback-om."""
    z = rezultat["zadaci"][ime]
    assert z["ok"], (
        f"zadatak `{ime}` je pao u svežem procesu: {z['greska']}: {z['poruka']}\n"
        f"{z['traceback']}"
    )
    return z["podaci"]


@pytest.fixture(scope="session")
def sanitizovan_env():
    """FAIL-CLOSED KAPIJA — ništa se ne pokreće dok sanitizacija nije dokazana.

    Dokaz se izvodi u podprocesu, POSLE `load_dotenv()`, jer je to jedino
    merodavno stanje: `api.py` isto tako prvo učita `.env`, pa tek onda gradi
    Supabase klijent. Ako `python-dotenv` ikad promeni podrazumevani
    `override=False`, ova provera pada — i to je ceo smisao.
    """
    env = _napravi_sanitizovan_env()
    rez = _pokreni_zadatke("env", env)
    razlozi = _uzmi(rez, "env")["razlozi"]
    if razlozi:
        pytest.exit(
            "COLD START GATE ZAUSTAVLJEN: sanitizacija okruženja podprocesa NIJE "
            "uspela — podproces bi dobio produkcionu konfiguraciju. Razlozi: "
            + "; ".join(razlozi),
            returncode=1,
        )
    return env


# ═════════════════════════════════════════════════════════════════════════════
# Deljeni podprocesi — R1/R3/R4/R6 se mere iz DVA procesa sa različitim
# redosledom. Grupisanje je namerno: `import api` traje sekundama, pa jedan
# podproces po tvrdnji ne bi bio ni brži ni tačniji. `failclosed` (R2) je
# NAMERNO odvojen — on kvari stanje procesa, pa bi zagadio svaki naredni zadatak.
# ═════════════════════════════════════════════════════════════════════════════
_REDOSLED_A = "gov,rate,nesting"
_REDOSLED_B = "nesting,rate,gov"


@pytest.fixture(scope="session")
def redosled_a(sanitizovan_env):
    return _pokreni_zadatke(_REDOSLED_A, sanitizovan_env)


@pytest.fixture(scope="session")
def redosled_b(sanitizovan_env):
    return _pokreni_zadatke(_REDOSLED_B, sanitizovan_env)


# ═════════════════════════════════════════════════════════════════════════════
# R0 — dokaz sanitizacije (mora biti prvi)
# ═════════════════════════════════════════════════════════════════════════════
def test_r0_sanitizacija_okruzenja_prezivljava_load_dotenv(sanitizovan_env):
    """Bez ovoga nijedan drugi test u fajlu ne sme da se pokrene.

    Meri se u podprocesu, a ne u pytest procesu: `conftest.py` je pytest već
    očistio, pa bi provera ovde dokazivala pogrešnu stvar.
    """
    rez = _pokreni_zadatke("env", sanitizovan_env)
    razlozi = _uzmi(rez, "env")["razlozi"]
    assert razlozi == [], (
        "podproces vidi produkcionu konfiguraciju i posle sanitizacije: " + str(razlozi)
    )


# ═════════════════════════════════════════════════════════════════════════════
# R1 — governance patch u svežem procesu
# ═════════════════════════════════════════════════════════════════════════════
_SDK_METODE = (
    "Completions.create", "AsyncCompletions.create",
    "Embeddings.create", "AsyncEmbeddings.create",
    "Transcriptions.create", "AsyncTranscriptions.create",
    "Speech.create", "AsyncSpeech.create",
)


def test_r1_import_api_aktivira_governance_u_svezem_procesu(redosled_a):
    """`import api` sam po sebi mora dovesti governance u aktivno stanje.

    Ako ovo prolazi samo u pytest-u, znači da ga je držao `conftest.py`, a
    produkcioni uvicorn bi se dizao bez ijedne AI kontrole — tačno stanje zbog
    kog Wave 4 i Wave 9 postoje.
    """
    s = _uzmi(redosled_a, "gov")["status"]
    assert s["attempted"] is True, "patch nije ni pokušan u svežem procesu"
    assert s["active"] is True, (
        "governance NIJE aktivan u svežem procesu — u pytest-u je izgledao "
        f"aktivan samo zato što ga je conftest instalirao. status={s}"
    )
    assert s["ai_blocked"] is False, "AI granica je zatvorena iako je patch uspeo"
    assert s["failure_reason"] is None


def test_r1_sdk_metode_su_stvarno_zamenjene(redosled_a):
    """Zastavica je tvrdnja; marker na metodi je stanje.

    `_vindex_guarded` živi na objektu koji je zaista postavljen na SDK klasu, pa
    ga ne može postaviti niko ko nije stvarno izvršio zamenu.
    """
    markeri = _uzmi(redosled_a, "gov")["markeri"]
    nedostaju = [m for m in _SDK_METODE if not markeri.get(m)]
    assert not nedostaju, (
        "SDK metode nisu presretnute u svežem procesu (nedostaje `_vindex_guarded`): "
        + ", ".join(nedostaju)
    )


def test_r1_api_version_objavljuje_isto_stanje(redosled_a):
    """Status koji `/api/version` objavljuje mora biti isti onaj koji modul drži —
    inače spoljna provera meri drugu stvar od one koja se izvršava."""
    podaci = _uzmi(redosled_a, "gov")
    assert podaci["api_version_governance"] == podaci["status"]


# ═════════════════════════════════════════════════════════════════════════════
# R2 — fail-closed politika u svežem procesu, BEZ ijednog prethodnog patch-a
# ═════════════════════════════════════════════════════════════════════════════
@pytest.fixture(scope="session")
def failclosed(sanitizovan_env):
    return _uzmi(_pokreni_zadatke("failclosed", sanitizovan_env), "failclosed")


def test_r2_pre_patcha_je_sve_neutralno(failclosed):
    """Negativna kontrola: da je proces nešto nasledio, ovo bi već bilo True."""
    pre = failclosed["pre"]
    assert pre["attempted"] is False and pre["active"] is False
    assert pre["ai_blocked"] is False


def test_r2_neuspeh_uvoza_ne_izgleda_kao_uspeh(failclosed):
    posle = failclosed["posle"]
    assert posle["attempted"] is True, "idempotencija je izgubljena"
    assert posle["active"] is False, "neuspeh patch-a se prijavljuje kao uspeh"
    assert posle["ai_blocked"] is True, (
        "guard nije aktivan, a AI granica je OSTALA OTVORENA — svaki AI poziv "
        "bi se izvršio bez prompt guard-a, firewall-a, provenance-a i timeout-a"
    )
    assert posle["failure_reason"], "neuspeh bez razloga se ne može dijagnostikovati"


def test_r2_nijedan_openai_klijent_se_ne_moze_konstruisati(failclosed):
    """Azure parnjaci su OBAVEZNI, ne kozmetika: `langchain_openai` konstruiše
    preko `openai.AzureOpenAI`/`AsyncAzureOpenAI`, pa bi brana samo nad
    `OpenAI`/`AsyncOpenAI` ostavila živu zaobilaznicu."""
    k = failclosed["konstrukcija"]
    for ime in ("OpenAI", "AsyncOpenAI", "AzureOpenAI", "AsyncAzureOpenAI"):
        assert k.get(ime) == "GovernanceUnavailable", (
            f"`openai.{ime}` se konstruisao iako governance nije aktivan "
            f"(ishod: {k.get(ime)}) — fail-closed brana ne pokriva ovu putanju"
        )


# ═════════════════════════════════════════════════════════════════════════════
# R3 — jedna kanonska Limiter instanca u svežem procesu
# ═════════════════════════════════════════════════════════════════════════════
def test_r3_svi_potrosaci_dele_istu_instancu(redosled_a):
    """Wave 10 je zatvorio dve žive instance sa dva odvojena skupa brojača.

    Meri se `is`, ne jednakost i ne broj instanci u izvoru: dve instance sa
    identičnom konfiguracijom izgledaju isto, a limitiraju odvojeno.
    """
    r = _uzmi(redosled_a, "rate")
    nisu = [k for k, v in r["isti_objekat"].items() if not v]
    assert not nisu, (
        "sledeći potrošači NE gledaju u kanonsku `shared.rate.limiter` instancu: "
        + ", ".join(nisu) + f" | idovi={r['idovi']}"
    )
    assert r["broj_razlicitih"] == 1, (
        f"u procesu postoji {r['broj_razlicitih']} različitih Limiter instanci — "
        "brojači su podeljeni i podrazumevani limit se ne primenjuje na iste "
        f"zahteve kao dekoratori. idovi={r['idovi']}"
    )


def test_r3_brojaci_su_prazni_na_startu(redosled_a):
    """Sveže podignut proces ne sme da počne sa potrošenim limitom."""
    brojaci = _uzmi(redosled_a, "rate")["brojaci"]
    glavni = brojaci["_storage"]
    assert glavni is not None, "limiter nema `_storage` — konfiguracija je neočekivana"
    assert glavni["kljuceva"] == 0 and glavni["zbir"] == 0, (
        f"brojači nisu prazni na startu svežeg procesa: {glavni}"
    )
    fallback = brojaci["_fallback_storage"]
    if fallback is not None:
        assert fallback["kljuceva"] == 0 and fallback["zbir"] == 0, (
            f"fallback brojači nisu prazni na startu: {fallback}"
        )


def test_r3_key_func_je_ocuvan(redosled_a):
    """Jedna instanca ne sme da bude kupljena promenom semantike limitiranja:
    ključ mora ostati `_get_real_ip` (X-Forwarded-For), ne slowapi default."""
    assert _uzmi(redosled_a, "rate")["key_func"] == "_get_real_ip"


# ═════════════════════════════════════════════════════════════════════════════
# R4 — wrapperi se ne ugnežđuju u svežem procesu
# ═════════════════════════════════════════════════════════════════════════════
def test_r4_ponovni_patch_ne_ugnezdjuje_wrapper(redosled_a):
    """Jedan logički SDK poziv mora stići do provajdera TAČNO jednom.

    Više od jednom znači da je wrapper obavijen oko samog sebe: dvostruka
    naplata provajderu i dvostruko izvršavanje guard-a i firewall-a nad istim
    sadržajem. Obrazac je iz `tests/test_gov4_patch_lifecycle.py::test_w9_b`,
    ovde ponovljen u procesu koji nije nasledio nikakvo stanje.
    """
    n = _uzmi(redosled_a, "nesting")
    assert n["orig_ocuvan_posle_noop"] is True, (
        "`_orig_create` je promenjen iako je zastavica `_guard_patched` bila postavljena"
    )
    assert n["orig_ocuvan_posle_zaobilaska"] is True, (
        "`_orig_create` je prepisan već-obavijenim wrapperom kada je zastavica "
        "zaobiđena — strukturna zaštita (`_vindex_guarded`) ne radi"
    )
    assert n["poziva_originala"] == 1, (
        f"jedan logički poziv je stigao do provajdera {n['poziva_originala']} puta "
        "— wrapper je ugnežđen"
    )
    assert n["status"]["active"] is True, "guard je posle drugog patch-a prestao da bude aktivan"


# ═════════════════════════════════════════════════════════════════════════════
# R6 — nezavisnost od redosleda
# ═════════════════════════════════════════════════════════════════════════════
def _uporedivo(rezultat: dict) -> dict:
    """Izbacuje sve što se legitimno razlikuje između dva procesa.

    `id()` je adresa u memoriji — različita po definiciji; ono što se poredi je
    IZVEDENA tvrdnja (`isti_objekat`, `broj_razlicitih`), koja mora biti ista.
    """
    out = {}
    for ime, z in rezultat["zadaci"].items():
        assert z["ok"], f"zadatak `{ime}` je pao: {z.get('greska')}\n{z.get('traceback')}"
        p = dict(z["podaci"])
        p.pop("idovi", None)
        out[ime] = p
    return out


def test_r6_isti_rezultat_u_dva_razlicita_redosleda(redosled_a, redosled_b):
    """Ako ijedan ishod zavisi od toga šta se u istom procesu izvršilo pre njega,
    onda rezultat nosi zagrejano stanje, a ne popravka."""
    a = _uporedivo(redosled_a)
    b = _uporedivo(redosled_b)
    assert set(a) == set(b)
    for ime in sorted(a):
        assert a[ime] == b[ime], (
            f"zadatak `{ime}` daje različit rezultat u redosledu "
            f"`{_REDOSLED_A}` i `{_REDOSLED_B}`:\n  A={a[ime]}\n  B={b[ime]}"
        )


# ═════════════════════════════════════════════════════════════════════════════
# R5 — aplikacija se stvarno diže i gasi, dva puta
# ═════════════════════════════════════════════════════════════════════════════
def _slobodan_port() -> int:
    """Port koji OS trenutno smatra slobodnim.

    `bind(0)` pa odmah `close()`: postoji teorijski prozor u kome ga neko drugi
    zauzme, ali je alternativa (fiksan port) garantovan sudar sa prethodnim
    ciklusom koji još nije oslobodio soket.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _port_slusa(port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def _uzmi_json(port: int, putanja: str, timeout: float = 10.0) -> dict:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{putanja}", timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _cekaj_health(proc: subprocess.Popen, port: int, dnevnik: str) -> dict:
    """Poll sa rokom — nikad `sleep` naslepo.

    Ako proces u međuvremenu umre, čekanje se prekida ODMAH i prijavljuje se
    njegov izlaz: „aplikacija se ne diže bez prave baze" je nalaz koji mora da
    imenuje modul i red, a ne da istekne kao anonimni timeout.
    """
    kraj = time.monotonic() + TIMEOUT_STARTA_S
    poslednja = None
    while time.monotonic() < kraj:
        if proc.poll() is not None:
            pytest.fail(
                f"uvicorn je umro pri startu (exit={proc.returncode}) pre nego što je "
                f"/health odgovorio.\n--- izlaz procesa (kraj) ---\n{_procitaj(dnevnik)}"
            )
        try:
            return _uzmi_json(port, "/health", timeout=5.0)
        except Exception as e:  # noqa: BLE001 — dok se ne digne, greška je očekivana
            poslednja = e
            time.sleep(0.25)
    _ugasi(proc)
    pytest.fail(
        f"/health nije odgovorio u {TIMEOUT_STARTA_S}s (poslednja greška: {poslednja})\n"
        f"--- izlaz procesa (kraj) ---\n{_procitaj(dnevnik)}"
    )


def _ugasi(proc: subprocess.Popen) -> int:
    """terminate → wait(timeout) → kill. Vraća exit kod.

    `kill` nije rezerva „za svaki slučaj" nego deo ugovora: proces koji ne
    reaguje na terminate mora biti ubijen, inače sledeći ciklus meri port koji
    drži leš prethodnog.

    Na Windows-u `terminate()` je `TerminateProcess`, pa je exit kod 1 i za
    uredno prekinut server — zato se exit kod NE koristi kao merilo čistoće
    gašenja; merilo je oslobođen port (v. `_jedan_ciklus`).
    """
    if proc.poll() is not None:
        return proc.returncode
    proc.terminate()
    try:
        proc.wait(timeout=TIMEOUT_GASENJA_S)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=TIMEOUT_GASENJA_S)
    return proc.returncode


def _procitaj(putanja: str) -> str:
    try:
        with open(putanja, encoding="utf-8", errors="replace") as f:
            return f.read()[-6000:]
    except OSError as e:  # noqa: BLE001
        return f"(dnevnik nije čitljiv: {e})"


def _jedan_ciklus(env: dict) -> dict:
    """Cold start → smoke → shutdown. Vraća sve što se meri, plus dokaz gašenja.

    IZLAZ SERVERA IDE U FAJL, NE U `subprocess.PIPE` — i to je ispravka stvarnog
    kvara ovog harness-a, ne opreznost. Sa PIPE-om je uvicorn blokirao na pisanju
    čim se popunio bafer anonimne cevi (na Windows-u nekoliko KB), pa se server
    nikad nije ni vezao za port. Test je to prijavio kao „aplikacija se ne diže",
    iako se identičan proces sa izlazom u fajl digao za 5.3s i uredno odgovorio.
    Lažan nalaz u release gate-u je skuplji od pravog propusta, jer troši poverenje
    u sve ostale nalaze iz istog izveštaja.
    """
    port = _slobodan_port()
    fd, dnevnik = tempfile.mkstemp(prefix="rc_uvicorn_", suffix=".log")
    os.close(fd)
    with open(dnevnik, "w", encoding="utf-8") as izlaz:
        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "api:app",
             "--host", "127.0.0.1", "--port", str(port), "--log-level", "info"],
            cwd=KOREN, env=env, stdout=izlaz, stderr=subprocess.STDOUT,
        )
        try:
            health = _cekaj_health(proc, port, dnevnik)
            version = _uzmi_json(port, "/api/version")
        finally:
            kod = _ugasi(proc)

    # Port se oslobađa asinhrono; kratak rok sa poll-om, ne fiksno čekanje.
    kraj = time.monotonic() + 15
    while time.monotonic() < kraj and _port_slusa(port):
        time.sleep(0.2)
    oslobodjen = not _port_slusa(port)

    dnevnik_tekst = _procitaj(dnevnik)
    try:
        os.unlink(dnevnik)
    except OSError:
        pass

    return {
        "port": port,
        "health": health,
        "version": version,
        "exit": kod,
        "port_oslobodjen": oslobodjen,
        "dnevnik": dnevnik_tekst,
    }


@pytest.fixture(scope="session")
def dva_ciklusa(sanitizovan_env):
    """cold start → smoke → shutdown → cold start → smoke.

    Drugi ciklus je poenta: ako se druga instanca ponaša drugačije, znači da je
    prva ostavila trag (port, fajl, lock, keš) koji produkcija ne bi tolerisala.
    """
    return [_jedan_ciklus(sanitizovan_env), _jedan_ciklus(sanitizovan_env)]


def test_r5_aplikacija_se_dize_u_oba_ciklusa(dva_ciklusa):
    for i, c in enumerate(dva_ciklusa, 1):
        assert c["health"]["status"] == "ok", f"ciklus {i}: /health nije 'ok' ({c['health']})"
        # P0-A: HTTP 200 sam po sebi ne dokazuje da se vrti Vindex.
        assert c["health"].get("app"), f"ciklus {i}: /health ne identifikuje aplikaciju"


def test_r5_governance_je_aktivan_u_pravom_serveru(dva_ciklusa):
    """Isti dokaz kao R1, ali kroz HTTP na stvarno pokrenutom uvicorn-u —
    jedini oblik koji odgovara produkciji."""
    for i, c in enumerate(dva_ciklusa, 1):
        gov = c["version"]["governance"]
        assert gov["active"] is True, f"ciklus {i}: governance nije aktivan u serveru ({gov})"
        assert gov["ai_blocked"] is False, f"ciklus {i}: AI granica je zatvorena ({gov})"
        assert gov["failure_reason"] is None, f"ciklus {i}: {gov['failure_reason']}"


def test_r5_p0a_ugovor_commit_i_commit_source(dva_ciklusa):
    """`commit`/`commit_source` moraju postojati — bez njih odgovor ne može da
    posluži kao dokaz KOJI build opslužuje korisnika."""
    for i, c in enumerate(dva_ciklusa, 1):
        v = c["version"]
        for kljuc in ("commit", "commit_short", "commit_source", "identity_proven"):
            assert kljuc in v, f"ciklus {i}: `/api/version` nema `{kljuc}`"
        assert v["commit"], f"ciklus {i}: `commit` je prazan"
        assert v["commit_source"], f"ciklus {i}: `commit_source` je prazan"


def test_r5_proces_se_gasi_cisto_i_oslobadja_port(dva_ciklusa):
    for i, c in enumerate(dva_ciklusa, 1):
        assert c["exit"] is not None, f"ciklus {i}: proces nije završio"
        assert c["port_oslobodjen"], (
            f"ciklus {i}: port {c['port']} i dalje sluša posle gašenja — "
            "proces je ostao živ ili je ostavio potomka"
        )


def test_r5_drugi_ciklus_je_ekvivalentan_prvom(dva_ciklusa):
    """STOP uslov misije: druga iteracija koja se ponaša drugačije je blocker.

    Poredi se ono što MORA biti isto (governance, identitet build-a, oblik
    odgovora), a ne ono što legitimno varira (`pid`, `started_at`, port).
    """
    a, b = dva_ciklusa
    assert a["version"]["governance"] == b["version"]["governance"], (
        f"governance se razlikuje između ciklusa:\n  1={a['version']['governance']}\n"
        f"  2={b['version']['governance']}"
    )
    assert set(a["version"]) == set(b["version"]), "oblik `/api/version` odgovora se promenio"
    assert set(a["health"]) == set(b["health"]), "oblik `/health` odgovora se promenio"
    for kljuc in ("app", "commit", "commit_short", "commit_source",
                  "identity_proven", "branch", "environment", "sw_cache"):
        assert a["version"][kljuc] == b["version"][kljuc], (
            f"`{kljuc}` se razlikuje između dva ciklusa istog build-a: "
            f"{a['version'][kljuc]!r} vs {b['version'][kljuc]!r}"
        )
    assert a["health"]["app"] == b["health"]["app"]
    assert a["health"]["commit"] == b["health"]["commit"]
    assert a["health"]["pid"] != b["health"]["pid"], (
        "oba ciklusa prijavljuju isti pid — drugi server nije novi proces, pa "
        "ovaj test ne meri ono što tvrdi"
    )


# ═════════════════════════════════════════════════════════════════════════════
# R7 — test DB bootstrap iz svežeg stanja
# ═════════════════════════════════════════════════════════════════════════════
def _test_db(*args, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, os.path.join(KOREN, "scripts", "test_db.py"), *args],
        cwd=KOREN, env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=180,
    )


@pytest.fixture(scope="session")
def status_i_verify(sanitizovan_env):
    return {
        "status": _test_db("status", env=sanitizovan_env),
        "verify": _test_db("verify", env=sanitizovan_env),
    }


def test_r7_status_prolazi_u_svezem_procesu(status_i_verify):
    r = status_i_verify["status"]
    assert r.returncode == 0, f"`test_db.py status` je pao (rc={r.returncode}):\n{r.stdout}\n{r.stderr}"
    assert "PostgreSQL alati" in r.stdout


def test_r7_verify_prolazi_u_svezem_procesu(status_i_verify):
    """Ako ovo padne, to NIJE nužno defekt koda — može značiti da lokalni test
    klaster ne radi. Poruka zato imenuje obe mogućnosti, umesto da tvrdi jednu."""
    r = status_i_verify["verify"]
    assert r.returncode == 0, (
        "`test_db.py verify` nije dokazao test bazu (rc="
        f"{r.returncode}). Ili klaster ne radi (`python scripts/test_db.py up`), "
        f"ili verifikacija stvarno odbija cilj:\n{r.stdout}\n{r.stderr}"
    )
    assert "VERIFIKOVANO" in r.stdout


@pytest.mark.parametrize("dsn,zasto", [
    ("postgresql://u:p@db.abcdefghijklm.supabase.co:5432/postgres", "upravljana baza"),
    ("postgresql://u:p@10.0.0.7:55432/postgres", "udaljeni host na test portu"),
    ("postgresql://u:p@127.0.0.1:5432/postgres", "podrazumevani port trajnog servisa"),
])
def test_r7_verify_odbija_produkcioni_oblik_dsn(sanitizovan_env, dsn, zasto):
    """Potvrda, ne duplikat: `tests/test_wave10_test_db_bootstrap.py` isto meri
    unutar pytest procesa (uvozom `scripts/test_db.py`). Ovde se meri PROCES —
    stvarni exit kod stvarnog CLI poziva, kakav bi neko i otkucao."""
    r = _test_db("verify", "--dsn", dsn, env=sanitizovan_env)
    assert r.returncode != 0, (
        f"`verify` je PRIHVATIO DSN produkcionog oblika ({zasto}) — fail-closed "
        f"kriterijum ne radi na nivou procesa:\n{r.stdout}"
    )


def test_r7_verify_ne_ispisuje_lozinku(sanitizovan_env):
    """Fail-closed alat koji u logu ostavi lozinku pravi novi problem umesto da
    zatvori stari."""
    r = _test_db("verify", "--dsn",
                 "postgresql://u:supertajnalozinka@db.abcdefghijklm.supabase.co:5432/postgres",
                 env=sanitizovan_env)
    assert "supertajnalozinka" not in (r.stdout + r.stderr)
