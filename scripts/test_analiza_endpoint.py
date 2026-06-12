#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test skripta za /api/dokument/analiza forenzicki pipeline.
Poziva interne funkcije direktno (bez HTTP/session/upload).

Testovi:
  TEST1 — kratak ugovor o radu (~1200 ch), 2x radi za determinizam
  TEST2 — dugacak ugovor o zakupu (~3800 ch), provera truncation + clause_ref na Clan 14/15
"""

import sys
import os
import json
import unicodedata
import re

# Force UTF-8 output
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Ucitaj OPENAI_API_KEY iz .env
_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
if os.path.exists(_env_path):
    for line in open(_env_path, encoding="utf-8"):
        line = line.strip()
        if line.startswith("OPENAI_API_KEY="):
            os.environ["OPENAI_API_KEY"] = line.split("=", 1)[1]
            break

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analiza.segmenter import segment_document
from main import ask_analiza_v2

# ─── Test dokumenti ───────────────────────────────────────────────────────────

TEST1_KRATAK_UGOVOR = """UGOVOR O RADU

Ugovorne strane:
Poslodavac: DOO "TechPrimer", PIB 123456789, Beograd, ul. Kralja Milana 5
Zaposleni: Jovana Nikolic, JMBG redacted, Novi Sad

zaključuju sledeći ugovor o radu:

Član 1
PREDMET I VRSTA RADNOG ODNOSA

Poslodavac zasniva radni odnos sa zaposlenom na neodređeno vreme, na radnom
mestu Frontend Developer. Zaposlena je dužna da obavlja poslove u skladu sa
opisom radnog mesta i uputstvima poslodavca.

Član 2
ZARADA I NAKNADE

Osnovna mesečna bruto zarada zaposlene iznosi 120.000 dinara. Uz zaradu,
zaposlena ostvaruje pravo na topli obrok u iznosu od 1.500 dinara dnevno i
prevoz do posla prema važećim tarifama javnog prevoza.

Član 3
PRESTANAK RADNOG ODNOSA

Poslodavac može raskinuti ovaj ugovor bez otkaznog roka u slučaju krivice
zaposlene, bez prethodne opomene i bez poštovanja otkaznog roka. Krivica
se utvrđuje jednostranom odlukom poslodavca bez obaveze sprovođenja
disciplinskog postupka. Zaposlena nema pravo žalbe na ovu odluku.

Član 4
UGOVORNA KAZNA

U slučaju otkaza od strane zaposlene ili prevremenog napuštanja radnog mesta,
zaposlena je dužna da plati ugovornu kaznu u iznosu od 10% od godišnje bruto
zarade. Kazna se automatski odbija od poslednje zarade bez saglasnosti
zaposlene.

Član 5
POVERLJIVOST

Zaposlena se obavezuje da čuva poverljivost poslovnih informacija i posle
prestanka radnog odnosa, bez vremenskog ograničenja.
"""

TEST2_DUGACAK_UGOVOR = """UGOVOR O ZAKUPU POSLOVNOG PROSTORA

Ugovorne strane:
Zakupodavac: NEKRETNINE DOO, PIB 987654321, Beograd, ul. Knez Mihailova 10
Zakupac: STARTUP ABC DOO, PIB 111222333, Beograd, ul. Savska 25

zaključuju sledeći ugovor o zakupu:

Član 1
PREDMET ZAKUPA

Zakupodavac daje zakupcu na koriscenje poslovni prostor u Beogradu,
ul. Knez Mihailova 10, II sprat, ukupne povrsine 120 m2. Prostor je
namenjen za obavljanje poslovne delatnosti zakupca.

Član 2
TRAJANJE ZAKUPA

Zakup se zaključuje na period od 3 (tri) godine, počev od 01.01.2025. do
31.12.2027. Zakupac ima pravo preče kupovine u slučaju da zakupodavac
odluči da proda predmet zakupa.

Član 3
ZAKUPNINA

Mesečna zakupnina iznosi 2.000 EUR u dinarskoj protivrednosti po
prodajnom kursu NBS na dan plaćanja. Zakupnina se plaća unapred,
do 5. u mesecu za tekući mesec.

Član 4
DEPOZIT

Zakupac je dužan da uplati depozit u iznosu od 4 mesečne zakupnine
(8.000 EUR) u roku od 7 dana od zaključenja ovog ugovora. Depozit
se čuva kao sredstvo obezbeđenja uredno izvršavanja obaveza zakupca.

Član 5
OBAVEZE ZAKUPODAVCA

Zakupodavac je dužan da preda prostor u ispravnom stanju, sa svim
instalacijama i opremom u funkcionalnom stanju. Zakupodavac garantuje
nesmetan posed i korišćenje prostora tokom trajanja zakupa.

Član 6
OBAVEZE ZAKUPCA

Zakupac je dužan da prostor koristi namjenski, da plaća zakupninu
blagovremeno i da izvršava redovno tekuće održavanje prostora.
Zakupac ne sme vrsiti rekonstrukciju bez pismene saglasnosti zakupodavca.

Član 7
KOMUNALNE USLUGE

Sve komunalne usluge (struja, voda, grejanje, internet, odvoz otpada)
plaća zakupac direktno nadleznim javnim preduzecima. Zakupodavac nije
odgovoran za prekide u isporuci komunalnih usluga.

Član 8
OSIGURANJE

Zakupac je obavezan da zaključi polisu osiguranja prostora od požara,
poplave i provalne krađe, u vrednosti ne manjoj od 100.000 EUR.
Kopiju police dostavlja zakupodavcu u roku od 30 dana od zaključenja ugovora.

Član 9
PODZAKUP

Podzakup prostora ili bilo kog dela prostora nije dozvoljen bez
prethodne pisane saglasnosti zakupodavca. Krsenje ove odredbe
daje zakupodavcu pravo da raskine ugovor sa trenutnim dejstvom.

Član 10
VRACANJE PROSTORA

Po isteku zakupa ili pri raskidu ugovora, zakupac je dužan da preda prostor
u stanju u kаkvom ga je primio, uz uvažavanje normalnog habanja.
Eventualnu štetu procenjuje zakupodavac jednosmerno.

Član 11
PRENOSIVOST

Prava i obaveze iz ovog ugovora zakupac ne može prenositi na treca lica
bez pisane saglasnosti zakupodavca. Prenos vlasnistva zakupodavca ne
utiče na prava zakupca iz ovog ugovora.

Član 12
PROMJENA NAMENE

Zakupac ne sme menjati namenu prostora bez pisane saglasnosti zakupodavca.
Neovlascena promena namene daje zakupodavcu pravo na jednostrani raskid.

Član 13
VISI SILA

Ni jedna strana nije odgovorna za neispunjenje obaveza usled više sile
(elementarne nepogode, ratni sukobi, epidemije). Strana koja se poziva
na višu silu dužna je da o tome pisanim putem obavesti drugu stranu
u roku od 48 sati od nastanka.

Član 14
GUBITAK DEPOZITA

U slučaju prevremenog raskida ugovora od strane zakupca, iz bilo kog
razloga i bez obzira na visinu stvarno nastale štete zakupodavca,
zakupac gubi ceo depozit bez prava na povraćaj. Gubitak depozita se
primenjuje i u slučaju višeg sile ili nemogucnosti koriscenja prostora
usled okolnosti van kontrole zakupca. Depozit se ne vraća ni u jednom
slučaju osim normalnog isteka ugovornog perioda.

Član 15
PENALI ZA KASNO PLACANJE

U slučaju kašnjenja u plaćanju zakupnine duže od 5 dana, zakupac plaća
penal od 5% od mesečne zakupnine za svaki dan kašnjenja, bez obzira na
razlog kašnjenja. Zbir penala ne može biti niži od iznosa zakupnine za
jedan mesec. Zakupodavac zadržava pravo da kumulira penale i depozitne
gubitke iz Člana 14.

Član 16
MERODAVNO PRAVO I RESAVANJE SPOROVA

Na ovaj ugovor primenjuje se pravo Republike Srbije. Za sporove nadlezan
je Privredni sud u Beogradu. Pre sudskog spora stranke su dužne da pokušaju
mirno resavanje u roku od 30 dana.
"""

# ─── Helpers ─────────────────────────────────────────────────────────────────

def _norm_ws(s):
    s = unicodedata.normalize("NFC", s)
    s = re.sub(r"\s+", " ", s)
    return s.lower().strip()

def check_excerpts(findings, full_text):
    """Mirrors validator logic: strips trailing '...' before matching."""
    full_norm = _norm_ws(full_text)
    results = []
    for f in findings:
        fid = f.get("id", "?")
        excerpt = (f.get("clause_excerpt") or "").strip()
        if not excerpt:
            results.append((fid, "SKIP", "null excerpt"))
            continue
        excerpt_norm = _norm_ws(excerpt)
        # Strip trailing ellipsis — validator does the same (re.sub r'\.{2,}$|…$')
        excerpt_norm = re.sub(r'\.{2,}$|…$', '', excerpt_norm).rstrip()
        excerpt_short = excerpt_norm[:100]
        ok = bool(excerpt_short) and excerpt_short in full_norm
        results.append((fid, "PASS" if ok else "FAIL", excerpt[:60]))
    return results

def run_analiza(tekst, label):
    print(f"\n{'='*62}")
    print(f"ANALIZA: {label}")
    print(f"Chars: {len(tekst)}")
    print(f"{'='*62}")
    seg = segment_document(tekst)
    print(f"doc_type: {seg.doc_type} | segments: {seg.segment_count} | char_count: {seg.char_count}")
    result = ask_analiza_v2(seg)
    return result, seg

def print_summary(result, seg, tekst, run_label):
    if result.get("status") != "success":
        print(f"[{run_label}] ERROR: {result.get('message','?')}")
        return None, None, None

    report = result.get("data") or {}
    es = report.get("executive_summary") or {}
    findings = report.get("findings") or []
    missing = report.get("missing_clauses") or []
    lc = report.get("low_confidence_findings") or []

    score = es.get("overall_risk_score", "N/A")
    risk_label = es.get("risk_label", "?")
    n_findings = len(findings)

    print(f"\n[{run_label}] overall_risk_score: {score} ({risk_label})")
    print(f"[{run_label}] findings: {n_findings} | missing_clauses: {len(missing)} | low_conf: {len(lc)}")

    print(f"\n--- PUNI JSON ({run_label}) ---")
    print(json.dumps(report, ensure_ascii=False, indent=2)[:6000])
    if len(json.dumps(report)) > 6000:
        print("... [skraceno na 6000 znakova]")

    # Excerpt check
    print(f"\n--- CLAUSE_EXCERPT SUBSTRING CHECK ({run_label}) ---")
    ec = check_excerpts(findings, tekst)
    pass_c = sum(1 for _, s, _ in ec if s == "PASS")
    skip_c = sum(1 for _, s, _ in ec if s == "SKIP")
    fail_c = sum(1 for _, s, _ in ec if s == "FAIL")
    for fid, status, excerpt in ec:
        print(f"  [{status}] {fid}: {excerpt!r}")
    print(f"  Ukupno: {pass_c} PASS / {fail_c} FAIL / {skip_c} SKIP od {len(ec)} findings")

    return score, n_findings, ec


# ─── TEST 1: Kratak ugovor o radu — 2x za determinizam ──────────────────────

print("\n" + "#"*62)
print("TEST 1 — Kratak ugovor o radu (determinizam, 2 poziva)")
print("#"*62)

result1a, seg1a = run_analiza(TEST1_KRATAK_UGOVOR, "TEST1 Run A")
score1a, n1a, ec1a = print_summary(result1a, seg1a, TEST1_KRATAK_UGOVOR, "TEST1 Run A")

result1b, seg1b = run_analiza(TEST1_KRATAK_UGOVOR, "TEST1 Run B")
score1b, n1b, ec1b = print_summary(result1b, seg1b, TEST1_KRATAK_UGOVOR, "TEST1 Run B")

print("\n" + "-"*62)
print("DETERMINIZAM ANALIZA:")
if score1a is not None and score1b is not None:
    score_match = score1a == score1b
    findings_match = n1a == n1b
    print(f"  overall_risk_score: {score1a} vs {score1b} => {'IDENTICAN' if score_match else 'RAZLICIT (ocekivano za LLM)'}")
    print(f"  broj findings: {n1a} vs {n1b} => {'IDENTICAN' if findings_match else 'RAZLICIT'}")
    print(f"  Determinizam: {'DA' if score_match and findings_match else 'NE (GPT varijabilnost — nije greska u sistemu)'}")


# ─── TEST 2: Dugacak ugovor o zakupu — truncation + Clan 14/15 ──────────────

print("\n" + "#"*62)
print("TEST 2 — Dugacak ugovor o zakupu (truncation + Clan 14/15)")
print("#"*62)

result2, seg2 = run_analiza(TEST2_DUGACAK_UGOVOR, "TEST2")
score2, n2, ec2 = print_summary(result2, seg2, TEST2_DUGACAK_UGOVOR, "TEST2")

print("\n" + "-"*62)
print("TRUNCATION ANALIZA:")
print(f"  Original tekst: {len(TEST2_DUGACAK_UGOVOR)} ch")
print(f"  seg.char_count: {seg2.char_count} ch")
print(f"  Truncation OK (> 3000): {'DA' if seg2.char_count > 3000 else 'NE — REGRESIJA!'}")
_seg2_ids = {s.id for s in seg2.segments}
_prisutni_14_15 = {"clause_14", "clause_15", "clause_16"} & _seg2_ids
print(f"  Clan 14/15 u segmentima: {_prisutni_14_15}")

if result2.get("status") == "success" and result2.get("data"):
    findings2 = result2["data"].get("findings") or []
    refs = [f.get("clause_ref") for f in findings2]
    clan14_15 = any(r in ("clause_14","clause_15") for r in refs if r)
    print(f"  Clan 14/15 u findings clause_ref: {'DA' if clan14_15 else 'NE'}")
    if not clan14_15:
        print(f"  Sve clause_ref vrednosti: {set(refs)}")

# ─── FINALNI SUMMARY ──────────────────────────────────────────────────────────

print("\n" + "="*62)
print("FINALNI SUMMARY")
print("="*62)

ec1_all = (ec1a or []) + (ec1b or [])
ec2_all = ec2 or []
all_ec = ec1_all + ec2_all
total_pass = sum(1 for _,s,_ in all_ec if s == "PASS")
total_fail = sum(1 for _,s,_ in all_ec if s == "FAIL")
total_skip = sum(1 for _,s,_ in all_ec if s == "SKIP")
total_checked = total_pass + total_fail

if score1a is not None and score1b is not None:
    print(f"  Determinizam (overall_risk_score isti): {'DA' if score1a==score1b else 'NE'}")
trunc_ok = seg2.char_count > 3000 if result2.get("status")=="success" else False
print(f"  Truncation OK (char_count > 3000): {'DA' if trunc_ok else 'NE — REGRESIJA!'}")
print(f"  Clause_excerpt match rate: {total_pass}/{total_checked} PASS ({total_skip} skip-null)")
print("="*62)
