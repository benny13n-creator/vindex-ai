# -*- coding: utf-8 -*-
"""Email cron — ugovor rezultata (night/deadlines-alerts-vcr002, T03/T04).

Izvršava STVARNI `run` korak iz `.github/workflows/email-cron.yml` u bash-u, kao GitHub Actions
(`bash --noprofile --norc -eo pipefail`), sa `${{ ... }}` izrazima zamenjenim kao što to radi runner.
`curl` je lažan (prvi na PATH-u): beleži pozive i vraća zadat HTTP kod i telo — nijedan mrežni poziv.

Zeleno sme da bude samo: 2xx + JSON objekat sa 4 nenegativna cela brojača + greske=0 + neisporuceno=0.
„Nema aktivnih profila“ je NO_RECIPIENTS, nikad tvrdnja o isporuci. Uspeh SMTP-a nije prijem u sanduče.
"""
import json
import os
import re
import shutil
import subprocess
import sys

import pytest
import yaml

KOREN = os.path.join(os.path.dirname(__file__), "..")
WORKFLOW = os.path.join(KOREN, ".github", "workflows", "email-cron.yml")
TAJNA = "test-kljuc-7f3a9c"          # sintetička vrednost, nije produkciona tajna
BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(BASH is None, reason="bash nije dostupan")

LAZNI_CURL = r'''#!/usr/bin/env bash
if [ "$1" = "--vindex-lazni-curl" ]; then echo LAZNI_CURL_OK; exit 0; fi
printf '%s\n' "$@" >> "$MOCK_LOG"
echo "---" >> "$MOCK_LOG"
out=""; prev=""
for a in "$@"; do
  if [ "$prev" = "-o" ]; then out="$a"; fi
  prev="$a"
done
if [ -n "$out" ] && [ -n "$MOCK_BODY_FILE" ]; then cat "$MOCK_BODY_FILE" > "$out"; fi
if [ "${MOCK_CURL_EXIT:-0}" != "0" ]; then printf '000'; exit "$MOCK_CURL_EXIT"; fi
printf '%s' "$MOCK_HTTP_CODE"
'''


def _korak():
    with open(WORKFLOW, encoding="utf-8") as f:
        wf = yaml.safe_load(f)
    poslovi = wf["jobs"]
    for posao in poslovi.values():
        for korak in posao.get("steps", []):
            if "send-reminders" in (korak.get("run") or ""):
                return wf, posao, korak
    raise AssertionError("korak koji poziva send-reminders nije pronađen")


def _izrazi(tekst, tajna):
    """GitHub Actions zamena izraza `${{ secrets.CRON_TOKEN }}` (jedini izraz u ovom koraku)."""
    tekst = re.sub(r"\$\{\{\s*secrets\.CRON_TOKEN\s*\}\}", tajna, str(tekst))
    assert "${{" not in tekst, "neočekivan GitHub izraz: " + tekst
    return tekst


MRTAV_PROXY = "http://127.0.0.1:9"   # discard port: niko ne sluša, veza odmah odbijena


def pokreni(tmp_path, http="200", telo=None, curl_izlaz=0, tajna=TAJNA):
    _, posao, korak = _korak()
    alat = tmp_path / "bin"
    alat.mkdir()
    (alat / "curl").write_text(LAZNI_CURL, encoding="utf-8", newline="\n")
    py = sys.executable.replace("\\", "/")
    (alat / "python3").write_text('#!/usr/bin/env bash\nexec "%s" "$@"\n' % py, encoding="utf-8", newline="\n")
    skripta = tmp_path / "korak.sh"
    skripta.write_text(_izrazi(korak["run"], tajna), encoding="utf-8", newline="\n")
    telo_f = tmp_path / "telo.json"
    if telo is not None:
        telo_f.write_text(telo if isinstance(telo, str) else json.dumps(telo), encoding="utf-8", newline="\n")
    log = tmp_path / "curl.log"
    env = {k: v for k, v in os.environ.items() if not k.startswith("MOCK_")}
    for izvor in (posao.get("env") or {}, korak.get("env") or {}):
        env.update({k: _izrazi(v, tajna) for k, v in izvor.items()})
    env.update({"MOCK_LOG": str(log), "MOCK_HTTP_CODE": http, "MOCK_CURL_EXIT": str(curl_izlaz),
                "MOCK_BODY_FILE": str(telo_f) if telo is not None else "",
                "PATH": str(alat) + os.pathsep + env.get("PATH", "")})
    env["PYTHONIOENCODING"] = "utf-8"   # GitHub ubuntu runner je UTF-8
    # NS3 gejt 4 (drugi, nezavisni sloj): i kad bi korak ipak dobio PRAVI curl, svaki HTTP(S) zahtev ide na mrtav
    # lokalni port (curl tada ne razrešava ni ime cilja) — nijedan paket ka produkciji. NO_PROXY se briše.
    for _k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        env[_k] = MRTAV_PROXY
    for _k in ("NO_PROXY", "no_proxy"):
        env.pop(_k, None)
    for k in ("PYTHONHOME", "PYTHONPATH"):
        env.pop(k, None)
    # Na Linux-u (CI) PATH preskače fajl bez izvršnog bita i nalazi PRAVI curl — korak bi tada gađao produkcioni
    # URL. Zato izvršni bit, i pre pokretanja provera da `curl` u tom okruženju jeste lažni (pravi curl na
    # nepoznatu opciju izlazi bez mreže). Ako nije — test pada, korak se NE pokreće.
    for alatka in ("curl", "python3"):
        (alat / alatka).chmod(0o755)
    proba = subprocess.run([BASH, "--noprofile", "--norc", "-c", "curl --vindex-lazni-curl"], capture_output=True,
                           text=True, encoding="utf-8", errors="replace", env=env, cwd=str(tmp_path), timeout=30)
    if proba.stdout.strip() != "LAZNI_CURL_OK":
        pytest.fail("lažni curl nije prvi na PATH-u — workflow korak se ne pokreće da ne bi gađao produkciju")
    r = subprocess.run([BASH, "--noprofile", "--norc", "-eo", "pipefail", str(skripta)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, cwd=str(tmp_path), timeout=60)
    pozivi = log.read_text(encoding="utf-8").split("---\n")[:-1] if log.exists() else []
    return r.returncode, r.stdout + r.stderr, pozivi


def ok(poslato=1, greske=0, preskoceno=0, neisporuceno=0, **dod):
    return {"poslato": poslato, "greske": greske, "preskoceno": preskoceno, "neisporuceno": neisporuceno, **dod}


# ── legitimni slučajevi ────────────────────────────────────────────────────────

def test_uspeh_smtp_prihvacen_ali_ne_tvrdi_prijem(tmp_path):
    kod, izlaz, pozivi = pokreni(tmp_path, "200", ok(poslato=1))
    assert kod == 0, izlaz
    assert len(pozivi) == 1
    assert "INBOX_UNCONFIRMED" in izlaz and "DELIVERY_VERIFIED" not in izlaz


def test_nema_aktivnih_profila_je_no_recipients(tmp_path):
    kod, izlaz, _ = pokreni(tmp_path, "200", ok(poslato=0, napomena="Nema aktivnih profila"))
    assert kod == 0, izlaz
    assert "NO_RECIPIENTS" in izlaz and "SMTP_ACCEPTED" not in izlaz


def test_nula_poslato_bez_napomene_je_izvrsen_posao(tmp_path):
    kod, izlaz, _ = pokreni(tmp_path, "200", ok(poslato=0))
    assert kod == 0, izlaz
    assert "JOB_EXECUTED" in izlaz and "NO_RECIPIENTS" not in izlaz


def test_preskoceno_rezervisano_nije_greska(tmp_path):
    kod, izlaz, _ = pokreni(tmp_path, "200", ok(poslato=0, preskoceno=2))
    assert kod == 0, izlaz


def test_salje_x_cron_key_iz_okruzenja_i_ne_ispisuje_tajnu(tmp_path):
    kod, izlaz, pozivi = pokreni(tmp_path, "200", ok())
    assert kod == 0, izlaz
    argumenti = pozivi[0].splitlines()
    assert "X-Cron-Key: " + TAJNA in argumenti
    assert "https://vindex.rs/email-notif/send-reminders" in argumenti
    assert not any(a.lower().startswith("authorization") for a in argumenti)
    assert TAJNA not in izlaz


# ── lažno zeleno: svaki mora pasti ────────────────────────────────────────────

@pytest.mark.parametrize("telo,razlog", [
    (ok(poslato=0, greske=1), "greske"),
    (ok(poslato=1, greske=1), "greske uz poslato"),
    (ok(poslato=0, neisporuceno=1), "neisporuceno"),
    (ok(poslato=3, neisporuceno=1), "neisporuceno uz poslato"),
    ("{nije json", "nevalidan JSON"),
    ("", "prazno telo"),
    ("[]", "niz umesto objekta"),
    ("null", "null"),
    ({"poslato": 1, "greske": 0}, "nedostaju brojači"),
    ({"poslato": 0, "greske": 0, "napomena": "Nema aktivnih profila"}, "stari oblik bez brojača"),
    (ok(poslato=-1), "negativan broj"),
    (ok(poslato="1"), "string umesto broja"),
    (ok(greske=False), "bool umesto broja"),
    (ok(neisporuceno=0.5), "razlomak"),
    (ok(greske=None), "null brojač"),
])
def test_200_sa_neuspehom_nije_zeleno(tmp_path, telo, razlog):
    kod, izlaz, _ = pokreni(tmp_path, "200", telo)
    assert kod != 0, "lažno zeleno (%s): %s" % (razlog, izlaz)
    assert TAJNA not in izlaz


@pytest.mark.parametrize("http", ["403", "401", "429", "500", "502", "302"])
def test_http_neuspeh(tmp_path, http):
    kod, izlaz, _ = pokreni(tmp_path, http, {"detail": "x"})
    assert kod != 0, izlaz


@pytest.mark.parametrize("http", ["403", "500", "302", "204x", ""])
def test_ne_2xx_pada_i_sa_validnim_telom(tmp_path, http):
    """HTTP provera mora sama da obori posao — npr. proksi koji vrati 500 uz keširano „uspešno“ telo."""
    kod, izlaz, _ = pokreni(tmp_path, http, ok(poslato=1))
    assert kod != 0, izlaz


def test_transportna_greska_timeout(tmp_path):
    kod, izlaz, _ = pokreni(tmp_path, "200", ok(), curl_izlaz=28)
    assert kod != 0, izlaz


def test_prazan_kljuc_pada_pre_http_poziva(tmp_path):
    kod, izlaz, pozivi = pokreni(tmp_path, "200", ok(), tajna="")
    assert kod != 0, izlaz
    assert pozivi == [], "HTTP poziv poslat sa praznim ključem"


def test_kljuc_samo_razmaci_pada_pre_http_poziva(tmp_path):
    kod, izlaz, pozivi = pokreni(tmp_path, "200", ok(), tajna="   ")
    assert kod != 0 and pozivi == [], izlaz


def test_neisporuceno_ne_pokrece_ponovni_poziv(tmp_path):
    """Nepoznat ishod se ne ponavlja automatski — tačno jedan HTTP poziv."""
    kod, _, pozivi = pokreni(tmp_path, "200", ok(poslato=0, neisporuceno=1))
    assert kod != 0 and len(pozivi) == 1


def test_workflow_nema_automatski_retry_ni_continue_on_error():
    _, posao, korak = _korak()
    assert not korak.get("continue-on-error") and not posao.get("continue-on-error")
    assert "--retry" not in korak["run"]
    assert "|| true" not in korak["run"]
