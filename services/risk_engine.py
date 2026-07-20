# -*- coding: utf-8 -*-
"""
Procesni rizik predmeta — jedini deterministicki izvor istine (G-027, AR-01).

AR-01: nijedan LLM izlaz ne sme biti jedini izvor poslovnog stanja (rizik,
status, rok, spremnost, prioritet) — LLM sme samo da ga interpretira/objasni.
Svaki UI/API element koji prikazuje "procesni rizik predmeta" MORA da poziva
ovu funkciju, ne da racuna svoju verziju. Pre ove funkcije, matter_intel.py i
Cockpit (api.py) su nezavisno racunali dva razlicita broja za isti koncept —
empirijski potvrdjeno (scripts/g027_risk_validation.py, 2026-07-20): Cockpit
je vratio "srednji" za 16/16 predmeta bez varijanse, dok je deterministicka
formula ispravno pratila stvarne podatke.

Logika je 1:1 prenesena iz routers/matter_intel.py (bila je inline u ruti) —
ponasanje NAMERNO nepromenjeno, ovo je ekstrakcija, ne redizajn formule.
"""
from datetime import datetime, timezone
from typing import Any


def calculate_procesni_rizik(
    dokazi: list[dict],
    dokumenti: list[dict],
    rocista: list[dict],
    tip_predmeta: str,
    expected_docs: dict[str, list[str]],
) -> dict[str, Any]:
    """
    dokazi:     redovi iz predmet_dokazi (snaga,kategorija,pravni_element)
    dokumenti:  redovi iz predmet_dokumenti (mora imati tip_dokaza da bi
                nedostajuci_dokazi bilo tacno — vidi G-028 napomenu u
                routers/matter_intel.py, ovo ponasanje je NEPROMENJENO)
    rocista:    redovi iz rocista (mora imati 'datum' polje)
    expected_docs: EXPECTED_DOCS mapa iz shared.constants
    """
    now = datetime.now(timezone.utc)

    # ── Dokazi analiza ───────────────────────────────────────────────────────
    snaga_count = {"jaka": 0, "srednja": 0, "slaba": 0}
    for d in dokazi:
        s = d.get("snaga", "srednja")
        if s in snaga_count:
            snaga_count[s] += 1
    ukupno = sum(snaga_count.values())

    if ukupno == 0:
        snaga_label = "Nema dokaza"
        snaga_pct = 0
    else:
        jaka_pct = snaga_count["jaka"] / ukupno
        sred_pct = snaga_count["srednja"] / ukupno
        if jaka_pct >= 0.5:
            snaga_label = "Jaka"
            snaga_pct = int(jaka_pct * 100)
        elif jaka_pct + sred_pct >= 0.6:
            snaga_label = "Srednja"
            snaga_pct = int((jaka_pct + sred_pct) * 100)
        else:
            snaga_label = "Slaba"
            snaga_pct = max(10, int(jaka_pct * 100))

    # ── Nedostajući dokumenti ────────────────────────────────────────────────
    expected = expected_docs.get(tip_predmeta, expected_docs["ostalo"])
    postojeci_tipovi = {d.get("tip_dokaza") for d in dokumenti if d.get("tip_dokaza")}
    nedostajuci = [t for t in expected if t not in postojeci_tipovi]

    predstojeći = 0
    kriticni = 0
    for r in rocista:
        try:
            ds = r.get("datum", "") or ""
            dt = datetime.fromisoformat((ds + "T00:00:00") if len(ds) == 10 else ds.replace("Z", "+00:00"))
            dana = (dt - now).days
            if 0 <= dana <= 30:
                predstojeći += 1
            if 0 <= dana <= 7:
                kriticni += 1
        except Exception:
            pass

    # ── Procesni rizik ───────────────────────────────────────────────────────
    rizik_score = 50
    if ukupno == 0:
        rizik_score += 20
    elif snaga_label == "Jaka":
        rizik_score -= 20
    elif snaga_label == "Slaba":
        rizik_score += 15
    if len(nedostajuci) >= 3:
        rizik_score += 15
    if kriticni > 0:
        rizik_score += 20

    if rizik_score <= 35:
        procesni_rizik = "Nizak"
        rizik_boja = "green"
    elif rizik_score <= 60:
        procesni_rizik = "Srednji"
        rizik_boja = "orange"
    else:
        procesni_rizik = "Visok"
        rizik_boja = "red"

    health = 100 - rizik_score
    health = max(5, min(95, health))

    return {
        "nivo": procesni_rizik,
        "boja": rizik_boja,
        "health_score": health,
        "snaga_dokaza": snaga_label,
        "snaga_pct": snaga_pct,
        "snaga_detalji": snaga_count,
        "nedostajuci_dokazi": nedostajuci,
        "nedostajuci_count": len(nedostajuci),
        "predstojeći_rokovi": predstojeći,
        "kriticni_rokovi": kriticni,
    }
