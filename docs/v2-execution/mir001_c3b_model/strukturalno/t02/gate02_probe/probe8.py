import sys
sys.path.insert(0, ".")
from shared import nacrt_za_sud as NZ, procesno_stanje as PS
from tests.test_mir001_c3b_procesno_stanje_ugovor import DOK06, ZAPISNIK, PREDUJAM, _d, _ZAGLAVLJE
st = lambda *d: PS.utvrdi(list(d), predmet_id="pred-1", user_id="user-A")
A = st(_d("DOK-06", DOK06), _d("DOK-07", ZAPISNIK))
B0 = st(_d("DOK-06", DOK06))
BODY = "- Model nije pročitao DOK-03.\nIznos štete treba uskladiti sa nalazom pre podnošenja."
print("=== BLOK NAPOMENA (stanje B0, bez naloga)")
for h in ["NAPOMENA ZA ADVOKATA:", "NAPOMENA ZA ADVOKATA", "**NAPOMENA ZA ADVOKATA:**", "### Napomena za advokata",
          "NAPOMENA ADVOKATU:", "Interna napomena:", "Napomene za proveru:", "Šta treba proveriti:",
          "PROVERITI PRE PODNOŠENJA:", "Ograničenja AI analize:", "Napomena (interno):", "Za advokata:"]:
    t = "Tužilac ostaje pri zahtevu.\n" + h + "\nModel nije pročitao DOK-03.\nIznos štete treba uskladiti sa nalazom."
    k = NZ.zastiti(t, B0)
    full = NZ.sastavi(k["tekst"], NZ.interne_napomene(B0, k, [], ""))
    ex, why = NZ.za_izvoz(full)
    print(f"{h!r:32} -> {'BLOCK' if why else 'EXPORT ' + repr(ex)}")
print("=== napomena usred pasusa / poslednji red / lazan naslov")
cases = {
 "usred_bez_praznog": "Tužilac ostaje pri zahtevu.\nNAPOMENA ZA ADVOKATA: proveriti iznos.\nTužilac predlaže da sud obaveže tuženog na troškove.\nU Primergradu, 01.09.2026.",
 "naslov_dvotacka_usred": "Tužilac ostaje pri zahtevu.\nNapomena:\nTužilac predlaže da sud obaveže tuženog na troškove.\nU Primergradu, 01.09.2026.",
 "poslednji_red": "Tužilac ostaje pri zahtevu.\n⚠️ Proveriti iznos štete.",
 "poslednji_red2": "Tužilac ostaje pri zahtevu.\nNapomena za advokata: proveriti iznos štete.",
 "lazni_naslov_u_podnesku": "PODNESAK TUŽIOCA\nNapomena: tužilac je promenio adresu.\nTužilac ostaje pri zahtevu.\nTužilac predlaže da sud obaveže tuženog na troškove.",
 "inline_napomena_u_recenici": "Tužilac ostaje pri zahtevu (napomena za advokata: model nije pročitao DOK-03).",
 "lista_bez_naslova": "Tužilac ostaje pri zahtevu.\n- Model nije pročitao DOK-03.\n- Pravni osnov nije potvrđen u bazi.",
 "ai_ogranicenje": "Tužilac ostaje pri zahtevu.\nOvaj nacrt je izradio AI savetnik i mora ga proveriti advokat.",
 "upozorenje_inline": "Tužilac ostaje pri zahtevu. Napomena: model nije pročitao DOK-03.",
}
for name, t in cases.items():
    k = NZ.zastiti(t, B0)
    full = NZ.sastavi(k["tekst"], NZ.interne_napomene(B0, k, [], ""))
    ex, why = NZ.za_izvoz(full)
    print(name, "| court:", repr(k["tekst"]), "| prem:", k["premesteno"], "|", "BLOCK" if why else "EXPORT")
print("=== U+2064 forge")
k = NZ.zastiti("Tužilac ostaje pri zahtevu.\n⁤\nTekst.", B0); print(repr(k["tekst"]), k["izostavljeno"])
