import sys
sys.path.insert(0, ".")
from shared import nacrt_za_sud as NZ, procesno_stanje as PS
from tests.test_mir001_c3b_procesno_stanje_ugovor import DOK06, ZAPISNIK, PREDUJAM, _d, _ZAGLAVLJE
st = lambda *d: PS.utvrdi(list(d), predmet_id="pred-1", user_id="user-A")
B0 = st(_d("DOK-06", DOK06))
def run(t, s=B0):
    k = NZ.zastiti(t, s)
    full = NZ.sastavi(k["tekst"], NZ.interne_napomene(s, k, [], ""))
    ex, why = NZ.za_izvoz(full)
    return k, ("BLOCK" if why else "EXPORT")
BODY = "\nModel nije pročitao DOK-03.\nIznos štete treba uskladiti sa nalazom."
print("=== naslovi koje model moze napisati (telo bez markera)")
for h in ["NAPOMENA ZA ADVOKATA.", "1. Napomena za advokata", "📌 NAPOMENA ZA ADVOKATA", "<b>NAPOMENA ZA ADVOKATA</b>",
          "N A P O M E N A", "NAPOMENA ZA ADVOKATA — ne podnosi se sudu", "Napomena za advokata (ne ulazi u podnesak, proveriti pre slanja sudu)",
          "II. NAPOMENE", "Napomene i preporuke za dalji rad", "Preporuke za advokata:", "Rizici:", "Šta nedostaje:",
          "Dalji koraci:", "Komentar:", "Beleška za advokata:", "Podsetnik:", "Interne beleške", "Note for lawyer:",
          "---\nNAPOMENA ZA ADVOKATA", "NAPOMENA ZA ADVOKATA:\n\nModel nije pročitao DOK-03."]:
    k, r = run("Tužilac ostaje pri zahtevu.\n" + h + BODY)
    print(f"{h[:45]!r:50} -> {r} | sud: {k['tekst'][:90]!r}")
print("=== legitiman podnesak sa recima sa spiska")
LEG = {
 "napomena_suda": "Tužilac ostaje pri zahtevu.\nNapomena suda iz zapisnika (DOK-07) odnosi se na rok za izjašnjenje\nTužilac predlaže da sud obaveže tuženog na troškove.\nU Primergradu, 01.09.2026.",
 "upozorenje_tuzenom": "Tužilac ostaje pri zahtevu.\nUpozorenje tuženom od 01.03.2024. godine\nTužilac je tuženog pisanim putem upozorio na nedostatke.\nTuženi nije postupio po upozorenju.",
 "za_advokata_tuzenog": "Tužilac ostaje pri zahtevu.\nZa advokata tuženog: dopis je dostavljen 01.03.2024.\nTužilac predlaže da sud obaveže tuženog na troškove.",
 "proveriti_treba": "Tužilac ostaje pri zahtevu.\nProveriti treba i navode tuženog o kvalitetu materijala\nTužilac predlaže saslušanje svedoka.",
 "ogranicenja_ugovor": "Tužilac ostaje pri zahtevu.\nOgraničenja odgovornosti izvođača iz čl. 12 ugovora\nPrema čl. 12 ugovora, izvođač odgovara za skrivene nedostatke.\nTuženi je izvođač radova.\nTužilac predlaže da sud obaveže tuženog na troškove.\n\nU Primergradu, 01.09.2026.",
 "napomena_ugovor_naslov": "DOKAZI\nNapomena uz ugovor o građenju\nUgovor je zaključen 10.01.2023.\nTuženi je preuzeo obavezu izvođenja radova.\nTužilac je platio ugovorenu cenu.",
 "ai_u_recenici": "Tužilac ostaje pri zahtevu, a ovaj nacrt je izradio AI savetnik.\nTužilac predlaže saslušanje svedoka.",
 "warn_u_recenici": "Tuženi je izvođač radova ⚠️ i odgovara za nedostatke.\nTužilac predlaže saslušanje svedoka.",
}
for n, t in LEG.items():
    k, r = run(t)
    print(n, r, "| sud:", repr(k["tekst"][:120]), "| izost:", [i["recenica"][:80] for i in k["izostavljeno"]], "| prem:", k["premesteno"])
print("=== polaritet klauza/modalitet")
pod = lambda r: st(_d("DOK-07", PREDUJAM), _d("DOK-08", _ZAGLAVLJE + "PODNESAK TUZIOCA (SINTETICKI PREDMET)\n" + r + "\nDatum podneska: 20.08.2026. godine."))
R = "Tužilac u podnesku (DOK-08) navodi da je uplatio predujam za dopunu veštačenja."
for src in ["Tuzilac navodi da je uplatio predujam za dopunu vestacenja.",
            "Tuzilac navodi da nije, zbog bolesti, uplatio predujam za dopunu vestacenja.",
            "Tuzilac navodi da predujam nije, kako je vec navedeno, uplatio za dopunu vestacenja.",
            "Tuzilac navodi da nije a ni mogao uplatio predujam za dopunu vestacenja.",
            "Tuzilac navodi da nikako i ni pod kojim uslovima i nikada do sada nije uplatio predujam za dopunu vestacenja.",
            "Tuzilac navodi da je uplatio predujam za dopunu vestacenja, ali ce dostaviti dokaz naknadno.",
            "Tuzilac navodi da je, kako tvrdi tuzeni, uplatio predujam za dopunu vestacenja.",
            "Tuzilac navodi da je jednako kao i ranije uplatio predujam za dopunu vestacenja.",
            "Tuzilac navodi da je uplatio predujam za dopunu vestacenja, ako se racuna i avans.",
            "Tuzilac navodi da tuzeni lazno tvrdi da je tuzilac uplatio predujam za dopunu vestacenja.",
            "Tuzilac navodi da je predujam za dopunu vestacenja uplatio, ne samo za sebe vec i za tuzenog."]:
    k = NZ.zastiti(R, pod(src))
    print("OMIT" if k["izostavljeno"] else "KEEP", "| izvor:", src[17:95])
