# -*- coding: utf-8 -*-
"""
NS007 — okidač ciklusa autonomnog rada. SAMO okidač: bez poslovne logike, bez baze, bez modela, samo stdlib.

  AUTONOMY_TRIGGER_URL   pun URL rute, npr. https://vindex.rs/api/cron/autonomy (obavezno)
  AUTONOMY_CRON_SECRET   tajna (obavezno; NIKAD se ne ispisuje)
  AUTONOMY_TRIGGER_TIMEOUT  sekunde (podrazumevano 900)

Izlaz: 0 samo za 2xx (COMPLETED / SKIPPED / COMPLETED_UNRECORDED); sve ostalo ≠ 0, da raspoređivač (npr. Render Cron)
prijavi neuspeh. Ispisuje se samo bezbedan sažetak: status, prozor, run_id i brojevi. HTTP bez TLS-a je dozvoljen
samo ka localhost-u (tajna ne sme ići nešifrovano preko mreže).
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

_LOKALNI = {"localhost", "127.0.0.1", "::1"}
_SIGURNA_POLJA = ("ok", "status", "razlog", "prozor", "run_id")


def _greska(poruka: str, kod: int) -> int:
    print(f"AUTONOMY TRIGGER: GREŠKA — {poruka}", file=sys.stderr)
    return kod


def _bezbedan_sazetak(telo: dict) -> dict:
    out = {k: telo[k] for k in _SIGURNA_POLJA if k in telo}
    s = telo.get("sazetak")
    if isinstance(s, dict):
        out["sazetak"] = {k: v for k, v in s.items() if isinstance(v, int) and not isinstance(v, bool)}
    return out


def main(argv: list[str] | None = None) -> int:
    url = os.environ.get("AUTONOMY_TRIGGER_URL", "").strip()
    tajna = os.environ.get("AUTONOMY_CRON_SECRET", "")
    if not url:
        return _greska("AUTONOMY_TRIGGER_URL nije podešen", 2)
    if not tajna:
        return _greska("AUTONOMY_CRON_SECRET nije podešen", 2)
    try:
        timeout = float(os.environ.get("AUTONOMY_TRIGGER_TIMEOUT", "900"))
    except ValueError:
        return _greska("AUTONOMY_TRIGGER_TIMEOUT nije broj", 2)
    u = urllib.parse.urlsplit(url)
    if u.scheme not in ("https", "http") or not u.hostname:
        return _greska("neispravan AUTONOMY_TRIGGER_URL", 2)
    if u.scheme == "http" and u.hostname not in _LOKALNI:
        return _greska("tajna se šalje samo preko HTTPS (http je dozvoljen samo za localhost)", 2)
    if u.username or u.password:
        return _greska("URL ne sme sadržati korisnika/lozinku", 2)

    zahtev = urllib.request.Request(url, data=b"", method="POST",
                                    headers={"X-Autonomy-Secret": tajna, "Content-Length": "0",
                                             "User-Agent": "vindex-autonomy-trigger/1"})
    cilj = f"{u.scheme}://{u.hostname}{':' + str(u.port) if u.port else ''}{u.path}"
    try:
        # šema je iznad ograničena na https (http samo ka localhost-u); file:/ i druge šeme se odbijaju pre zahteva
        with urllib.request.urlopen(zahtev, timeout=timeout) as odg:  # nosec B310
            status, sirovo = odg.status, odg.read(65536)
    except urllib.error.HTTPError as e:
        try:
            sirovo = e.read(65536)            # telo greške: ispisuju se SAMO bezbedna polja (isti filter kao za uspeh)
        except Exception:
            sirovo = b""
        status = e.code
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        razlog = getattr(e, "reason", e)
        return _greska(f"{cilj} nije odgovorio ({type(razlog).__name__})", 3)

    try:
        telo = json.loads(sirovo.decode("utf-8")) if sirovo else {}
    except (ValueError, UnicodeDecodeError):
        telo = {}
    sazetak = _bezbedan_sazetak(telo if isinstance(telo, dict) else {})
    if not 200 <= status < 300:
        return _greska(f"{cilj} vratio HTTP {status} {json.dumps(sazetak, ensure_ascii=False)}", 4)
    print("AUTONOMY TRIGGER: OK " + json.dumps(sazetak, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
