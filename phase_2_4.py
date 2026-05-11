import sys
import io
import time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
import requests
from pathlib import Path
import docx

UGOVOR_TEXT = """UGOVOR O RADU

Zaključen dana 11. maja 2026. godine između:

POSLODAVAC: "INNOVATECH" d.o.o., sa sedištem u Beogradu, Bulevar oslobođenja 25, koga zastupa direktor (u daljem tekstu: Poslodavac)

i

ZAPOSLENI (u daljem tekstu: Zaposleni)

Član 1 — Predmet ugovora
Ovim ugovorom uređuju se prava, obaveze i odgovornosti iz radnog odnosa između Poslodavca i Zaposlenog, u skladu sa Zakonom o radu i opštim aktima Poslodavca.

Član 2 — Vrsta radnog odnosa
Zaposleni se prima u radni odnos na neodređeno vreme, sa probnim radom u trajanju od tri (3) meseca.

Član 3 — Probni rad
Probni rad počinje 12. maja 2026. godine i traje do 12. avgusta 2026. godine. Tokom probnog rada, svaka ugovorna strana može otkazati ovaj ugovor sa otkaznim rokom od pet (5) radnih dana.

Član 4 — Radno mesto i opis posla
Zaposleni se zapošljava na radnom mestu "Software Developer". Opis posla obuhvata razvoj softverskih rešenja, testiranje koda, učešće u code review procesima, i druge zadatke u okviru struke.

Član 5 — Mesto rada
Mesto rada Zaposlenog je u sedištu Poslodavca u Beogradu. Zaposleni može povremeno raditi sa udaljene lokacije (rad od kuće), uz prethodnu saglasnost neposrednog rukovodioca.

Član 6 — Radno vreme
Puno radno vreme iznosi 40 sati nedeljno, raspoređeno od ponedeljka do petka, od 09:00 do 17:00 časova.

Član 7 — Prekovremeni rad
Zaposleni je obavezan da na zahtev Poslodavca radi prekovremeno, ali ne više od 8 časova nedeljno i 32 časa mesečno. Prekovremeni rad biće dodatno plaćen u skladu sa zakonom.

Član 8 — Osnovna zarada
Osnovna mesečna zarada Zaposlenog iznosi 180.000,00 dinara u bruto iznosu. Zarada se isplaćuje najkasnije do 10. u mesecu za prethodni mesec, na tekući račun Zaposlenog.

Član 9 — Stimulacije i nagrade
Zaposleni može ostvariti pravo na varijabilni deo zarade (bonus) na osnovu kvartalne procene radnog učinka, u iznosu do 30% osnovne zarade.

Član 10 — Godišnji odmor
Zaposleni ima pravo na godišnji odmor u trajanju od 20 radnih dana u kalendarskoj godini. Pravo na pun godišnji odmor stiče se posle navršenih šest meseci neprekidnog rada kod Poslodavca.

Član 11 — Bolovanje
Zaposleni ostvaruje pravo na naknadu zarade za vreme privremene sprečenosti za rad u skladu sa Zakonom o radu i zakonom kojim se uređuje zdravstveno osiguranje.

Član 12 — Klauzula o čuvanju poslovne tajne
Zaposleni je obavezan da čuva sve poverljive informacije Poslodavca, uključujući poslovne planove, klijentske podatke, izvorni kod, finansijske podatke, i ostale informacije označene kao poverljive. Ova obaveza traje i nakon prestanka radnog odnosa, bez vremenskog ograničenja.

Član 13 — Konkurentska klauzula
Zaposleni se obavezuje da po prestanku radnog odnosa neće raditi za konkurentske firme, niti osnivati sopstvenu firmu u istoj delatnosti, u periodu od TRI (3) godine od dana prestanka radnog odnosa. Za pridržavanje ove klauzule, Poslodavac će Zaposlenom isplatiti naknadu u iznosu od 30% poslednje primljene zarade, mesečno tokom trajanja zabrane.

Član 14 — Korišćenje sredstava rada
Sva sredstva rada (računar, telefon, software licence) ostaju vlasništvo Poslodavca i Zaposleni je obavezan da ih koristi isključivo u svrhu obavljanja poslova.

Član 15 — Stručno usavršavanje
Poslodavac može uputiti Zaposlenog na stručno usavršavanje. U slučaju da troškove usavršavanja snosi Poslodavac u iznosu većem od 100.000,00 dinara, Zaposleni je obavezan da nakon usavršavanja ostane u radnom odnosu kod Poslodavca najmanje 18 meseci.

Član 16 — Otkaz ugovora
Ovaj ugovor o radu može prestati na osnove utvrđene Zakonom o radu. Otkazni rok kod otkaza od strane Zaposlenog iznosi 15 radnih dana. Otkazni rok kod otkaza od strane Poslodavca iznosi 15 radnih dana.

Član 17 — Otpremnina
U slučaju otkaza ugovora od strane Poslodavca zbog tehnoloških, ekonomskih ili organizacionih promena (tehnološki višak), Zaposleni ima pravo na otpremninu u skladu sa Zakonom o radu.

Član 18 — Dostojanstvo na radu
Poslodavac garantuje Zaposlenom radno okruženje slobodno od diskriminacije i zlostavljanja, u skladu sa Zakonom o sprečavanju zlostavljanja na radu.

Član 19 — Zabrana takmičenja tokom rada
Tokom trajanja radnog odnosa, Zaposleni ne sme bez pisane saglasnosti Poslodavca obavljati poslove iz delatnosti Poslodavca za sopstveni račun ili za račun trećeg lica.

Član 20 — Završne odredbe
Ovaj ugovor sastavljen je u 2 istovetna primerka, od kojih svaka strana zadržava po jedan. Sve izmene i dopune mogu se vršiti isključivo u pisanoj formi, uz saglasnost obe ugovorne strane. Za sve što nije regulisano ovim ugovorom primenjuju se odredbe Zakona o radu i drugih važećih propisa Republike Srbije.
"""

DOCX_OUT = Path("ugovor_test.docx")
BASE_URL = "https://vindex-ai.onrender.com"
QUESTIONS = [
    "Da li je probni rad u ovom ugovoru u skladu sa članom 36 Zakona o radu?",
    "Postoji li klauzula o tajnosti i da li je u skladu sa zakonom?",
    "Šta ugovor predviđa za prekovremeni rad i da li je usklađen sa članom 53 ZR?",
    "Da li otkazni rok u ovom ugovoru ispunjava minimum iz člana 189 ZR?",
    "Postoji li konkurentska klauzula? Da li je vremenski ograničena u skladu sa članom 162 ZR?",
    "Da li ugovor predviđa otpremninu pri tehnološkom višku?",
    "Postoji li bilo koja klauzula koja je nepovoljnija za zaposlenog od minimuma iz ZR?",
]

print("=" * 78)
print("KORAK 1: Generisanje test ugovora")
print("=" * 78)
doc = docx.Document()
for para in UGOVOR_TEXT.strip().split("\n\n"):
    if para.strip():
        doc.add_paragraph(para.strip())
doc.save(str(DOCX_OUT))
print(f"OK: sacuvan kao {DOCX_OUT} ({len(UGOVOR_TEXT)} karaktera)")

print()
print("=" * 78)
print("KORAK 2: Upload na Vindex")
print("=" * 78)
with open(DOCX_OUT, "rb") as f:
    mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    u = requests.post(f"{BASE_URL}/api/dokument/upload",
                      files={"file": (DOCX_OUT.name, f, mime)})
if u.status_code != 200:
    print(f"FAIL: {u.status_code} - {u.text}")
    raise SystemExit(1)
meta = u.json()
sid = meta["session_id"]
print(f"OK: Session {sid}")
print(f"    Chunks: {meta['chunk_count']}, mode: {meta['chunk_mode_used']}")
print(f"    Articles: {meta['article_labels_detected']}")

print()
print("=" * 78)
print(f"KORAK 3: {len(QUESTIONS)} pitanja")
print("=" * 78)
for i, q in enumerate(QUESTIONS, 1):
    print()
    print("-" * 78)
    print(f"PITANJE {i}/{len(QUESTIONS)}: {q}")
    print("-" * 78)
    time.sleep(3)
    r = requests.post(f"{BASE_URL}/api/dokument/pitanje",
                      json={"session_id": sid, "pitanje": q})
    if r.status_code != 200:
        print(f"FAIL: {r.status_code} - {r.text}")
        continue
    body = r.json()
    print(f"Confidence: {body.get('confidence')} | Law score: {body.get('top_score', 0):.4f} | Law: {body.get('top_article')} ({body.get('top_law')})")
    print()
    print(body.get("data", "[no data]"))

print()
print("=" * 78)
print(f"GOTOVO. Session ID: {sid}")
print("=" * 78)