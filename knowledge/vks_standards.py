# -*- coding: utf-8 -*-
"""
VKS Orijentacioni kriterijumi za nematerijalnu štetu (Srbija).
Zasnovani na stavovima Vrhovnog kasacionog suda, ažurirani 2019–2023.
Izvor: Orijentacioni kriterijumi i iznosi za utvrđivanje visine pravične novčane
naknade nematerijalne štete — VKS Srbije.
"""
from __future__ import annotations
from typing import Optional

# ── Fizički bolovi (RSD po danu) ─────────────────────────────────────────────
FIZICKI_BOLOVI_PO_DANU: dict[str, dict] = {
    "jak":     {"min": 3_000, "max": 5_000, "vas": "VAS 7–10", "opis": "jak intenzitet"},
    "srednji": {"min": 1_500, "max": 3_000, "vas": "VAS 4–6",  "opis": "srednji intenzitet"},
    "laki":    {"min":   500, "max": 1_500, "vas": "VAS 1–3",  "opis": "laki intenzitet"},
}

# ── Strah (RSD, jednokratno) ──────────────────────────────────────────────────
STRAH_IZNOSI: dict[str, dict] = {
    "primarni_visok":     {"min": 100_000, "max": 250_000,
                           "opis": "primarni visoki intenzitet (vitalna ugroženost, gubitak svesti)"},
    "primarni_srednji":   {"min":  40_000, "max": 100_000,
                           "opis": "primarni srednji intenzitet"},
    "primarni_laki":      {"min":  10_000, "max":  40_000,
                           "opis": "primarni laki intenzitet"},
    "sekundarni_visok":   {"min":  50_000, "max": 150_000,
                           "opis": "sekundarni strah (operacije, ICU, duga hospitalizacija)"},
    "sekundarni_srednji": {"min":  20_000, "max":  50_000,
                           "opis": "sekundarni strah (dijagnostičke procedure, kraća hospitalizacija)"},
    "sekundarni_laki":    {"min":   5_000, "max":  20_000,
                           "opis": "sekundarni laki (ambulantno lečenje)"},
}

# ── Umanjenje opšte životne aktivnosti — RSD po 1% trajnog invaliditeta ──────
UMANJENJE_PO_PROCENTU: dict = {
    "min_po_procent": 15_000,
    "max_po_procent": 25_000,
    "napomena": (
        "Korekcija za starost: mlađi od 30 god. +20%, "
        "30–50 god. bez korekcije, stariji od 60 god. −15%."
    ),
}

# ── Naruženost (RSD, jednokratno) ─────────────────────────────────────────────
NARUZENOST_STEPENI: dict[str, dict] = {
    "laka":        {"min":  30_000, "max":   100_000,
                    "opis": "jedva primetan / teško vidljiv (pokriveni delovi tela)"},
    "srednja":     {"min": 100_000, "max":   300_000,
                    "opis": "vidljiv na nezaštićenim delovima tela, ne deformiše"},
    "teska":       {"min": 300_000, "max":   800_000,
                    "opis": "uočljiva, deformiše izgled lica ili tela"},
    "veoma_teska": {"min": 800_000, "max": 2_000_000,
                    "opis": "izrazita, trajno i ozbiljno narušava izgled (amputacija, opekotine III stepena)"},
}

# ── Profili tipičnih povreda: dani bolova + nivo straha + tipični % invaliditeta
POVREDE_PROFILI: dict[str, dict] = {
    "prelom_podlaktice": {
        "kw": ["prelom podlaktice", "prelom ručnog zgloba", "prelom radijusa",
               "prelom ulne", "fraktura podlaktice", "prelom ruke"],
        "bolovi_dani":        {"jak": 30, "srednji": 30, "laki": 30},
        "strah_prim":         "primarni_srednji",
        "strah_sek":          "sekundarni_srednji",
        "umanjenje_pct":      5,
        "naruzenost_stepen":  "laka",
    },
    "prelom_nadlaktice": {
        "kw": ["prelom nadlaktice", "prelom humerusa", "prelom ramena",
               "prelom lakta", "fraktura humerusa"],
        "bolovi_dani":        {"jak": 45, "srednji": 35, "laki": 30},
        "strah_prim":         "primarni_srednji",
        "strah_sek":          "sekundarni_srednji",
        "umanjenje_pct":      8,
        "naruzenost_stepen":  "laka",
    },
    "prelom_noge": {
        "kw": ["prelom noge", "prelom potkolenice", "prelom butne kosti",
               "prelom femura", "prelom tibije", "prelom fibule",
               "prelom skočnog zgloba", "prelom kolena", "fraktura noge",
               "fraktura femura", "prelom potkoljenice"],
        "bolovi_dani":        {"jak": 50, "srednji": 40, "laki": 30},
        "strah_prim":         "primarni_srednji",
        "strah_sek":          "sekundarni_visok",
        "umanjenje_pct":      10,
        "naruzenost_stepen":  "laka",
    },
    "politrauma": {
        "kw": ["politrauma", "multiple povrede", "višestruke povrede",
               "prelomi rebara", "prelom karlice", "prelom kičme",
               "povreda kičme", "polifraktura"],
        "bolovi_dani":        {"jak": 75, "srednji": 60, "laki": 45},
        "strah_prim":         "primarni_visok",
        "strah_sek":          "sekundarni_visok",
        "umanjenje_pct":      20,
        "naruzenost_stepen":  "srednja",
    },
    "potres_mozga": {
        "kw": ["potres mozga", "kontuzija mozga", "traumatska povreda mozga",
               "kraniocerebralna", "povreda glave", "cerebralnacontusio"],
        "bolovi_dani":        {"jak": 15, "srednji": 30, "laki": 30},
        "strah_prim":         "primarni_visok",
        "strah_sek":          "sekundarni_visok",
        "umanjenje_pct":      10,
        "naruzenost_stepen":  "laka",
    },
    "povreda_kicme_diska": {
        "kw": ["hernia diska", "hernija diska", "diskus hernija", "prolaps diska",
               "lumbalni sindrom", "cervikalni sindrom", "whiplash", "šibanje",
               "povreda vrata", "cervikobrahijalni"],
        "bolovi_dani":        {"jak": 20, "srednji": 45, "laki": 60},
        "strah_prim":         "primarni_srednji",
        "strah_sek":          "sekundarni_srednji",
        "umanjenje_pct":      12,
        "naruzenost_stepen":  None,
    },
    "opekotine": {
        "kw": ["opekotina", "opekotine", "opekline", "termička povreda",
               "opekotina ii stepena", "opekotina iii stepena"],
        "bolovi_dani":        {"jak": 60, "srednji": 45, "laki": 30},
        "strah_prim":         "primarni_visok",
        "strah_sek":          "sekundarni_visok",
        "umanjenje_pct":      15,
        "naruzenost_stepen":  "teska",
    },
    "uganuće_distorzija": {
        "kw": ["uganuće", "distorzija", "iščašenje", "uganuće zgloba",
               "distorzija skočnog", "distorzija kolena"],
        "bolovi_dani":        {"jak": 7, "srednji": 14, "laki": 21},
        "strah_prim":         "primarni_laki",
        "strah_sek":          "sekundarni_laki",
        "umanjenje_pct":      0,
        "naruzenost_stepen":  None,
    },
    "rana_laceracija": {
        "kw": ["laceracija", "lacerozna rana", "sečena rana", "ubodna rana",
               "posekotina", "rana na glavi", "rana na licu"],
        "bolovi_dani":        {"jak": 10, "srednji": 14, "laki": 14},
        "strah_prim":         "primarni_laki",
        "strah_sek":          "sekundarni_laki",
        "umanjenje_pct":      0,
        "naruzenost_stepen":  "laka",
    },
}

# ── Regionalne razlike u sudskoj praksi ───────────────────────────────────────
REGIONALNE_RAZLIKE: dict[str, dict] = {
    "beograd": {
        "procenat": +25,
        "napomena": (
            "Sudovi u Beogradu (Viši sud Beograd, Apelacioni sud Beograd) "
            "tipično dosuđuju 20–30% više od nacionalnog proseka VKS."
        ),
    },
    "novi_sad": {
        "procenat": +20,
        "napomena": "Vojvodinski sudovi (Novi Sad, Subotica, Zrenjanin): 15–20% iznad proseka.",
    },
    "nis_kragujevac": {
        "procenat": 0,
        "napomena": (
            "Sudovi u Nišu i Kragujevcu: blizu nacionalnog proseka (±5%). "
            'Sigurna "srednja" kalibacija.'
        ),
    },
    "unutrasnjost": {
        "procenat": -12,
        "napomena": (
            "Manji sudovi u unutrašnjosti Srbije: 10–15% ispod proseka VKS kriterijuma. "
            "Preporučuje se konzervativniji petitum."
        ),
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Pomocne funkcije
# ─────────────────────────────────────────────────────────────────────────────

def _fmt(iznos: int) -> str:
    """Formatuje RSD iznos sa tačkama (srpski standard)."""
    return f"{iznos:,}".replace(",", ".")


def _detektuj_povredu(tekst: str) -> Optional[dict]:
    """Vraća profil povrede ako je prepoznata u slobodnom tekstu, inače None."""
    if not tekst:
        return None
    t = tekst.lower()
    for profil in POVREDE_PROFILI.values():
        if any(kw in t for kw in profil["kw"]):
            return profil
    return None


def _detektuj_region(sud_naziv: str) -> dict:
    """Vraća regionalnu razliku na osnovu naziva suda."""
    s = sud_naziv.lower()
    if "beograd" in s:
        return REGIONALNE_RAZLIKE["beograd"]
    if any(x in s for x in ["novi sad", "subotica", "zrenjanin", "sombor", "pančevo", "pancevo"]):
        return REGIONALNE_RAZLIKE["novi_sad"]
    if any(x in s for x in ["niš", "nis", "kragujevac"]):
        return REGIONALNE_RAZLIKE["nis_kragujevac"]
    return REGIONALNE_RAZLIKE["unutrasnjost"]


# ─────────────────────────────────────────────────────────────────────────────
# Glavna funkcija: preporuka iznosa
# ─────────────────────────────────────────────────────────────────────────────

def preporuci_iznose(entiteti: dict) -> dict:
    """
    Na osnovu ekstraktovanih entiteta tužbe vraća:
      kontekst_tekst — injektovati u LLM obog prompt pre RAG-a
      analiza_tekst  — dodati kao poslednju sekciju generisanog dokumenta
    """
    fiz_raw   = entiteti.get("fizicki_bolovi_raw", "") or ""
    strah_raw = entiteti.get("strah_raw", "") or ""
    ima_uma   = bool(entiteti.get("ima_umanjenje", False))
    ima_nar   = bool(entiteti.get("ima_naruzenost", False))
    sud       = entiteti.get("sud_naziv", "") or ""

    profil = _detektuj_povredu(fiz_raw) or _detektuj_povredu(strah_raw)
    region = _detektuj_region(sud)

    # ── Fizički bolovi ───────────────────────────────────────────────────────
    if profil:
        d = profil["bolovi_dani"]
        fiz_min = (
            d["jak"]     * FIZICKI_BOLOVI_PO_DANU["jak"]["min"] +
            d["srednji"] * FIZICKI_BOLOVI_PO_DANU["srednji"]["min"] +
            d["laki"]    * FIZICKI_BOLOVI_PO_DANU["laki"]["min"]
        )
        fiz_max = (
            d["jak"]     * FIZICKI_BOLOVI_PO_DANU["jak"]["max"] +
            d["srednji"] * FIZICKI_BOLOVI_PO_DANU["srednji"]["max"] +
            d["laki"]    * FIZICKI_BOLOVI_PO_DANU["laki"]["max"]
        )
        fiz_opis = (
            f"{d['jak']} dana jakog + {d['srednji']} dana srednjeg "
            f"+ {d['laki']} dana lakog bola"
        )
        sp = STRAH_IZNOSI[profil["strah_prim"]]
        ss = STRAH_IZNOSI[profil["strah_sek"]]
        str_min = sp["min"] + ss["min"]
        str_max = sp["max"] + ss["max"]
        str_opis = f"{sp['opis']}; {ss['opis']}"
    else:
        fiz_min, fiz_max = 150_000, 600_000
        fiz_opis = "Nije detektovana specifična povreda — generičke vrednosti"
        str_min, str_max = 40_000, 200_000
        str_opis = "Generička procena — precizirati prema medicinskoj dokumentaciji"

    # ── Umanjenje ────────────────────────────────────────────────────────────
    uma_min = uma_max = 0
    uma_pct = profil["umanjenje_pct"] if profil else 10
    if ima_uma and uma_pct > 0:
        uma_min = uma_pct * UMANJENJE_PO_PROCENTU["min_po_procent"]
        uma_max = uma_pct * UMANJENJE_PO_PROCENTU["max_po_procent"]

    # ── Naruženost ───────────────────────────────────────────────────────────
    nar_min = nar_max = 0
    nar_stepen = "srednja"
    if ima_nar:
        nar_stepen = (
            profil["naruzenost_stepen"]
            if profil and profil.get("naruzenost_stepen")
            else "srednja"
        )
        ns = NARUZENOST_STEPENI[nar_stepen]
        nar_min, nar_max = ns["min"], ns["max"]

    # ── Ukupno ───────────────────────────────────────────────────────────────
    uk_min = fiz_min + str_min + uma_min + nar_min
    uk_max = fiz_max + str_max + uma_max + nar_max

    # ── kontekst za LLM (inject u obog prompt) ───────────────────────────────
    F = FIZICKI_BOLOVI_PO_DANU
    S = STRAH_IZNOSI
    N = NARUZENOST_STEPENI
    kontekst_tekst = (
        f"VKS ORIJENTACIONI KRITERIJUMI (Srbija, 2023):\n"
        f"Fizički bolovi: jak {_fmt(F['jak']['min'])}–{_fmt(F['jak']['max'])} RSD/dan | "
        f"srednji {_fmt(F['srednji']['min'])}–{_fmt(F['srednji']['max'])} RSD/dan | "
        f"laki {_fmt(F['laki']['min'])}–{_fmt(F['laki']['max'])} RSD/dan\n"
        f"Strah primarni: visoki {_fmt(S['primarni_visok']['min'])}–{_fmt(S['primarni_visok']['max'])} | "
        f"srednji {_fmt(S['primarni_srednji']['min'])}–{_fmt(S['primarni_srednji']['max'])} | "
        f"laki {_fmt(S['primarni_laki']['min'])}–{_fmt(S['primarni_laki']['max'])} RSD\n"
        f"Strah sekundarni: visoki {_fmt(S['sekundarni_visok']['min'])}–{_fmt(S['sekundarni_visok']['max'])} | "
        f"srednji {_fmt(S['sekundarni_srednji']['min'])}–{_fmt(S['sekundarni_srednji']['max'])} RSD\n"
        f"Umanjenje: {_fmt(UMANJENJE_PO_PROCENTU['min_po_procent'])}–"
        f"{_fmt(UMANJENJE_PO_PROCENTU['max_po_procent'])} RSD po 1% invaliditeta\n"
        f"Naruženost: laka {_fmt(N['laka']['min'])}–{_fmt(N['laka']['max'])} | "
        f"srednja {_fmt(N['srednja']['min'])}–{_fmt(N['srednja']['max'])} | "
        f"teška {_fmt(N['teska']['min'])}–{_fmt(N['teska']['max'])} RSD\n\n"
        f"PROCENA ZA OVAJ SLUČAJ:\n"
        f"• Fizički bolovi: {_fmt(fiz_min)}–{_fmt(fiz_max)} RSD ({fiz_opis})\n"
        f"• Strah: {_fmt(str_min)}–{_fmt(str_max)} RSD\n"
    )
    if ima_uma and uma_min:
        kontekst_tekst += (
            f"• Umanjenje ({uma_pct}% tipično): {_fmt(uma_min)}–{_fmt(uma_max)} RSD "
            f"({UMANJENJE_PO_PROCENTU['napomena']})\n"
        )
    if ima_nar and nar_min:
        kontekst_tekst += f"• Naruženost (stepen: {nar_stepen}): {_fmt(nar_min)}–{_fmt(nar_max)} RSD\n"
    kontekst_tekst += (
        f"• UKUPNI PROCENJENI OPSEG: {_fmt(uk_min)}–{_fmt(uk_max)} RSD\n"
        f"• Regionalna korekcija: {region['napomena']}\n\n"
        f"NAPOMENA ZA LLM: Iznosi su ISKLJUČIVO orijentacioni. "
        f"Ako korisnik nije naveo konkretne iznose, ostavi placeholder [IZNOS — POPUNITI] "
        f"u petitumu — NE upisuj ove procene automatski u tužbu."
    )

    # ── analiza_tekst za kraj dokumenta ──────────────────────────────────────
    redovi_tabele = (
        f"| Fizički bolovi | {_fmt(fiz_min)} – {_fmt(fiz_max)} | {fiz_opis[:55]} |\n"
        f"| Strah | {_fmt(str_min)} – {_fmt(str_max)} | Primarni + sekundarni |"
    )
    if ima_uma and uma_min:
        redovi_tabele += (
            f"\n| Umanjenje živ. aktivnosti | {_fmt(uma_min)} – {_fmt(uma_max)} "
            f"| Tipično {uma_pct}% invaliditeta za ovu povredu |"
        )
    if ima_nar and nar_min:
        redovi_tabele += (
            f"\n| Naruženost | {_fmt(nar_min)} – {_fmt(nar_max)} "
            f"| Procenjeni stepen: {nar_stepen.replace('_', ' ')} |"
        )
    redovi_tabele += f"\n| **UKUPNO** | **{_fmt(uk_min)} – {_fmt(uk_max)}** | Pre korekcije za region |"

    petitum_napomena = (
        "Petitum sadrži konkretne iznose koje je korisnik naveo."
        if entiteti.get("iznos_fizicki_bolovi")
        else (
            "Petitum sadrži placeholder [IZNOS — POPUNITI]. "
            f"Razmotriti gornji opseg i uskladiti sa nalazom veštaka pre podnošenja."
        )
    )

    analiza_tekst = (
        f"\n\n---\n\n"
        f"### VIKI PRAVNA ANALIZA\n\n"
        f"**Orijentacioni iznosi prema stavovima Vrhovnog kasacionog suda Srbije:**\n\n"
        f"| Osnov štete | Okvirni raspon (RSD) | Napomena |\n"
        f"|---|---|---|\n"
        f"{redovi_tabele}\n\n"
        f"**Regionalna napomena:** {region['napomena']}\n\n"
        f"**Status petituma:** {petitum_napomena}\n\n"
        f"> NAPOMENA: Ova analiza je isključivo informativna i ne zamenjuje pravni savet. "
        f"Konačne iznose utvrđuje sud po slobodnoj oceni (ZOO čl. 200 st. 2). "
        f"Orijentacioni kriterijumi VKS nisu obavezujući za niže sudove.\n"
    )

    return {
        "kontekst_tekst": kontekst_tekst,
        "analiza_tekst":  analiza_tekst,
    }
