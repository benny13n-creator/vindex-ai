"""Kontrola roka za ODOBRENE izuzetke ranjivosti u pip-audit koraku (.github/workflows/security.yml).

JRC001: osnivač je 2026-10-11 odobrio izuzetak za CVE-2026-85394 (python-jose==3.5.0) na najviše 90 dana.
Ova provera NIŠTA ne potiskuje i NE produžava. Pada (izlaz 1) kad:
  - zapis odobrenja nedostaje ili je neispravan (nikad ne prolazi „tiho“);
  - je današnji datum (UTC) posle `vazi_do` ili pre `odobreno`;
  - trajanje premašuje 90 dana;
  - requirements.txt ne zakucava tačno odobrenu verziju paketa (promena verzije = ponovni pregled);
  - pip-audit u workflow-u ignoriše ID koji nije ni odobren ovde ni poznata zasebna odluka, ili mu nedostaje
    odobreni ID (izuzetak se ne sme tiho proširiti niti premestiti).
Samo standardna biblioteka — radi u `dependency-scan` poslu pre pip-audit-a.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

KOREN = Path(__file__).resolve().parent.parent
ODOBRENJA = Path(__file__).with_name("izuzeci_ranjivosti.json")
REQUIREMENTS = KOREN / "requirements.txt"
WORKFLOW = KOREN / ".github" / "workflows" / "security.yml"
MAKS_DANA = 90
OBAVEZNA_POLJA = ("paket", "verzija", "odobreno", "vazi_do", "vlasnik", "odluka")
# Postojeći izuzetak iz ranije, ZASEBNE odluke (python-ecdsa timing, dokumentovan u security.yml). Nije deo JRC001
# odobrenja i nema rok u ovom zapisu; naveden je samo da ga provera ne bi proglasila nepoznatim.
ZASEBNE_ODLUKE = frozenset({"PYSEC-2026-1325"})


def _datum(v, polje: str, id_: str, greske: list[str]):
    if not isinstance(v, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
        greske.append(f"{id_}: polje `{polje}` nije ISO datum (YYYY-MM-DD): {v!r}")
        return None
    try:
        return date.fromisoformat(v)
    except ValueError:
        greske.append(f"{id_}: polje `{polje}` nije stvaran datum: {v!r}")
        return None


def proveri(meta, danas: date, requirements: str, workflow: str, koren: Path | None = None) -> list[str]:
    """Vraća listu grešaka; prazna lista = svi odobreni izuzeci važe na dan `danas`."""
    greske: list[str] = []
    if not isinstance(meta, dict) or not meta:
        return ["zapis odobrenja je prazan ili nije JSON objekat"]
    ignorisani = re.findall(r"--ignore-vuln\s+([A-Za-z0-9._-]+)", workflow or "")
    if len(ignorisani) != len(set(ignorisani)):
        greske.append(f"workflow ponavlja ignore ID: {sorted(ignorisani)}")
    for id_, z in meta.items():
        if not isinstance(z, dict):
            greske.append(f"{id_}: zapis nije objekat")
            continue
        nedostaje = [p for p in OBAVEZNA_POLJA if not isinstance(z.get(p), str) or not z.get(p).strip()]
        if nedostaje:
            greske.append(f"{id_}: nedostaju polja {nedostaje}")
            continue
        od = _datum(z["odobreno"], "odobreno", id_, greske)
        do = _datum(z["vazi_do"], "vazi_do", id_, greske)
        if od and do:
            if do < od:
                greske.append(f"{id_}: vazi_do {do} je pre odobreno {od}")
            elif (do - od).days > MAKS_DANA:
                greske.append(f"{id_}: trajanje {(do - od).days} dana premašuje {MAKS_DANA}")
            if danas < od:
                greske.append(f"{id_}: odobrenje počinje {od}, danas je {danas}")
            if danas > do:
                greske.append(f"{id_}: ODOBRENJE ISTEKLO {do} (danas {danas}) — potrebno novo izričito odobrenje "
                              f"osnivača; nema automatskog produženja")
        pin = re.search(rf"(?im)^\s*{re.escape(z['paket'])}(?:\[[^\]]*\])?\s*==\s*([^\s;#]+)", requirements or "")
        if not pin:
            greske.append(f"{id_}: requirements.txt nema tačno zakucan `{z['paket']}==...`")
        elif pin.group(1) != z["verzija"]:
            greske.append(f"{id_}: requirements.txt ima {z['paket']}=={pin.group(1)}, odobreno je samo "
                          f"=={z['verzija']} — ponovni pregled")
        if id_ not in ignorisani:
            greske.append(f"{id_}: pip-audit ga ne ignoriše — zapis i workflow se ne slažu")
        if koren is not None and not (koren / z["odluka"]).is_file():
            greske.append(f"{id_}: dokument odluke ne postoji: {z['odluka']}")
    for i in ignorisani:
        if i not in meta and i not in ZASEBNE_ODLUKE:
            greske.append(f"pip-audit ignoriše {i}, a za to nema odobrenja u zapisu — izuzetak se ne sme tiho dodati")
    return greske


def main(argv: list[str] | None = None, danas: date | None = None) -> int:
    danas = danas or datetime.now(timezone.utc).date()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")   # ispis nikad ne sme da obori proveru
    try:
        meta = json.loads(ODOBRENJA.read_text(encoding="utf-8"))
        requirements = REQUIREMENTS.read_text(encoding="utf-8")
        workflow = WORKFLOW.read_text(encoding="utf-8")
    except (OSError, ValueError) as exc:
        print(f"[IZUZECI] NEUSPEH: zapis odobrenja ili ulazni fajl nije čitljiv: {exc}")
        return 1
    greske = proveri(meta, danas, requirements, workflow, koren=KOREN)
    if greske:
        for g in greske:
            print(f"[IZUZECI] NEUSPEH: {g}")
        return 1
    for id_, z in meta.items():
        ostalo = (date.fromisoformat(z["vazi_do"]) - danas).days
        print(f"[IZUZECI] OK: {id_} ({z['paket']}=={z['verzija']}) važi do {z['vazi_do']} — još {ostalo} dana")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
