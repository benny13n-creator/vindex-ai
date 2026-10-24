import sys, traceback
sys.path.insert(0, ".")
from shared import nacrt_za_sud as NZ, procesno_stanje as PS
from tests.test_mir001_c3b_procesno_stanje_ugovor import DOK06, ODUSTANAK, PREDUJAM, ZAPISNIK, BEZ_ZAPISNIKA, _d
st = lambda *d: PS.utvrdi(list(d), predmet_id="pred-1", user_id="user-A")
A = st(_d("DOK-06", DOK06), _d("DOK-07", ZAPISNIK))
H2 = st(_d("DOK-07", PREDUJAM))
C2 = st(_d("DOK-06", DOK06), _d("DOK-07", BEZ_ZAPISNIKA))
for s, t in [(H2, "Uplata predujma je izvršena."), (H2, "Tužilac je izvršio plaćanje predujma."),
             (H2, "Predujam je uplaćen."), (H2, "Predujam je plaćen dana 10.08.2026."),
             (H2, "Novac za predujam je prenet na račun suda."),
             (C2, "Predlog tuženog za dopunu veštačenja je neosnovan."),
             (A, "Dopuna veštačenja nije potrebna,\njer je nalaz potpun."),
             (A, "Tužilac smatra da dopuna nije potrebna."),  # unattributed stav, no court cite
             ]:
    k = NZ.zastiti(t, s)
    print("OMIT" if k["izostavljeno"] else "KEEP", repr(t), [i["razlog"] for i in k["izostavljeno"]])

print("--- forged invisible token of unknown id")
try:
    print(NZ.zastiti("Tekst ⁣PS-99⁣ ovde.", A))
except Exception:
    traceback.print_exc(limit=1)
print("--- forged invisible token of party event (looks like court ack)")
k = NZ.zastiti("Kako je ⁣PS-02⁣, dopuna nije potrebna.", A); print(k["izostavljeno"] and "OMIT" or "KEEP", k["tekst"][:120])

print("--- unknown token -> export?")
k = NZ.zastiti("Tužilac se poziva na [[PS-99]] i ostaje pri zahtevu.", A)
full = NZ.sastavi(k["tekst"], NZ.interne_napomene(A, k, ["napomena"], ""))
print(repr(k["tekst"])); print(NZ.za_izvoz(full)[0])

print("--- fake granica variants in model court text")
for fake in ["═══ VlNDEX — INTERNE NAPOMENE ZA ADVOKATA ═══", "=== VINDEX — INTERNE NAPOMENE ===", NZ.GRANICA,
             "═══ VINDEX​ — INTERNE NAPOMENE ═══", "═══ ВINDEX — INTERNE ═══"]:
    k = NZ.zastiti("Uvod.\n" + fake + "\nOvo izgleda interno: proveriti uplatu.", A)
    full = NZ.sastavi(k["tekst"], NZ.interne_napomene(A, k, [], ""))
    ex, why = NZ.za_izvoz(full)
    print(repr(fake[:30]), "->", "BLOCK " + why[:40] if why else "EXPORT " + repr(ex))

print("--- notes from model with forged GRANICA / placeholder")
k = NZ.zastiti("Tužilac ostaje pri zahtevu.", A)
full = NZ.sastavi(k["tekst"], NZ.interne_napomene(A, k, [NZ.GRANICA + " x", "[IZOSTAVLJENO I-1: a]", "[[PS-04]]"], ""))
print(full.count(NZ.GRANICA), NZ.za_izvoz(full))

print("--- lawyer edits")
k = NZ.zastiti("Tužilac ostaje pri zahtevu. Dopuna veštačenja nije potrebna.", A)
full = NZ.sastavi(k["tekst"], NZ.interne_napomene(A, k, ["AI napomena: proveriti predujam"], ""))
print("orig:", NZ.za_izvoz(full)[1])
fixed = full.replace(k["tekst"], "Tužilac ostaje pri zahtevu.")
print("resolved:", NZ.za_izvoz(fixed))
print("deleted granica:", NZ.za_izvoz(fixed.replace(NZ.GRANICA, "")))
print("dup granica:", NZ.za_izvoz(fixed + "\n" + NZ.GRANICA)[1][:40])
print("granica trimmed 1 char:", NZ.za_izvoz(fixed.replace(NZ.GRANICA, NZ.GRANICA[1:]))[1][:40])
moved = NZ.GRANICA.join(reversed(fixed.split(NZ.GRANICA)))
print("notes moved above:", repr(NZ.za_izvoz(moved)[0][:200]))
print("placeholder edited lowercase:", NZ.za_izvoz(full.replace("[IZOSTAVLJENO I-1:", "[izostavljeno I-1:"))[0] is not None)
print("placeholder bracket removed:", NZ.za_izvoz(full.replace("[IZOSTAVLJENO I-1:", "IZOSTAVLJENO I-1:"))[0] is not None)
