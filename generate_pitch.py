# -*- coding: utf-8 -*-
"""Generiše Vindex AI pitch PDF za sastanak."""

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, HRFlowable,
    Table, TableStyle, KeepTogether
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily

FONTS_DIR = "C:/Windows/Fonts/"
pdfmetrics.registerFont(TTFont("Arial",        FONTS_DIR + "arial.ttf"))
pdfmetrics.registerFont(TTFont("Arial-Bold",   FONTS_DIR + "arialbd.ttf"))
pdfmetrics.registerFont(TTFont("Arial-Italic", FONTS_DIR + "ariali.ttf"))
pdfmetrics.registerFont(TTFont("Arial-BoldIt", FONTS_DIR + "arialbi.ttf"))
registerFontFamily("Arial", normal="Arial", bold="Arial-Bold",
                   italic="Arial-Italic", boldItalic="Arial-BoldIt")

OUTPUT = "Vindex_AI_Skripta.pdf"

PLAVA  = colors.HexColor("#4aa8ff")
TAMNA  = colors.HexColor("#0f172a")
SIVA   = colors.HexColor("#64748b")
SVETLA = colors.HexColor("#f1f5f9")

def st(name, **kw):
    s = ParagraphStyle(name, fontName="Arial", fontSize=10,
                       leading=15, textColor=colors.HexColor("#1e293b"))
    for k, v in kw.items(): setattr(s, k, v)
    return s

NASLOV   = st("n",  fontName="Arial-Bold", fontSize=26, textColor=TAMNA,
              leading=32, spaceAfter=4)
TAGLINE  = st("tl", fontName="Arial",      fontSize=13, textColor=PLAVA,
              leading=18, spaceAfter=4)
UVOD     = st("uv", fontName="Arial-Italic", fontSize=11, textColor=colors.HexColor("#334155"),
              leading=17, spaceAfter=16)
SEKCIJA  = st("s",  fontName="Arial-Bold", fontSize=12, textColor=PLAVA,
              leading=17, spaceBefore=16, spaceAfter=4)
TEKST    = st("t",  fontName="Arial",      fontSize=10, leading=16,
              spaceAfter=8, alignment=TA_JUSTIFY)
BULLET   = st("b",  fontName="Arial",      fontSize=10, leading=15,
              spaceAfter=5, leftIndent=14)
MALI     = st("m",  fontName="Arial",      fontSize=8.5, textColor=SIVA,
              leading=13, spaceAfter=4)
FOOTER_S = st("f",  fontName="Arial",      fontSize=8, textColor=SIVA,
              leading=12, alignment=TA_CENTER)
TABELAH  = st("th", fontName="Arial-Bold", fontSize=9, textColor=colors.white, leading=13)
TABELAT  = st("tt", fontName="Arial",      fontSize=9, leading=14,
              textColor=colors.HexColor("#1e293b"))
FAZANAZIV= st("fz", fontName="Arial-Bold", fontSize=10, textColor=PLAVA,
              spaceBefore=8, spaceAfter=2)

def hr():
    return HRFlowable(width="100%", thickness=0.5,
                      color=colors.HexColor("#e2e8f0"), spaceAfter=10, spaceBefore=4)
def sp(n=6): return Spacer(1, n)
def nsek(txt):
    return KeepTogether([sp(4), Paragraph(txt, SEKCIJA),
                         HRFlowable(width="100%", thickness=1.2,
                                    color=PLAVA, spaceAfter=8)])
def tacka(txt): return Paragraph(f"• {txt}", BULLET)
def b(t):  return f"<b>{t}</b>"
def pl(t): return f'<font color="#4aa8ff"><b>{t}</b></font>'

doc = SimpleDocTemplate(OUTPUT, pagesize=A4,
    leftMargin=2.2*cm, rightMargin=2.2*cm,
    topMargin=2.2*cm,  bottomMargin=2.2*cm,
    title="Vindex AI — Pravni operativni sistem", author="Vindex AI")
story = []

# ── Zaglavlje ──────────────────────────────────────────────────────────────────
story.append(Paragraph("Vindex AI", NASLOV))
story.append(Paragraph("Pravni operativni sistem za advokate u Srbiji", TAGLINE))
story.append(Paragraph(
    "Prva platforma koja pokriva celokupno poslovanje advokatske kancelarije — "
    "od prvog kontakta sa klijentom do naplate honorara.", UVOD))
story.append(hr())
story.append(sp(4))
story.append(Paragraph(
    "Ovaj dokument je interna skripta namenjena razgovoru o platformi Vindex AI — "
    "njenim mogućnostima, tržišnom kontekstu i viziji razvoja.", MALI))
story.append(sp(10))

# ── 1. Šta je Vindex AI ────────────────────────────────────────────────────────
story.append(nsek("1. Šta je Vindex AI"))
story.append(Paragraph(
    f"Vindex AI je {b('pravni operativni sistem')} — centralna platforma kroz koju advokat "
    "vodi celokupno poslovanje svoje kancelarije. Nije reč o još jednom alatu koji se dodaje "
    "na gomilu programa. Vindex zamenjuje rasuti skup fajlova, tabela, podsetnike u telefonu "
    "i manuelne pretrage — jednim integrisanim sistemom koji razume srpsko pravo.", TEKST))
story.append(Paragraph(
    "Kada advokat otvori Vindex, ima pred sobom: sve aktivne predmete, sve nadolazeće rokove, "
    "sve dokumente klijenata i direktan pristup srpskim zakonima i sudskoj praksi. "
    f"Sistem {b('nikada ne izmišlja pravne odgovore')} — svaki zaključak koji prikaže "
    "potkrepljen je direktnim citatom iz važećeg srpskog zakona ili sudske prakse, "
    "sa oznakom izvora i stepenom pouzdanosti.", TEKST))

# ── 2. Problemi ────────────────────────────────────────────────────────────────
story.append(nsek("2. Problemi koje Vindex AI rešava"))
story.append(Paragraph(
    "Razgovarajući sa advokatima, identifikovali smo šest problema koji im "
    "svakodnevno oduzimaju vreme i energiju:", TEKST))
problemi = [
    ("Pretraga zakona i sudske prakse traje satima",
     "Advokat pretražuje Sl. glasnik, sudske portale i štampane zbirke. "
     "Kroz Vindex — advokat postavi pitanje na srpskom jeziku i za sekunde dobija "
     "tačan odgovor sa citatom iz zakona i naznakom koji član se primenjuje."),
    ("Rokovi se propuštaju ili prate ručno",
     "Zakonski rokovi — zastarelost, žalbe, ročišta — beleže se u Excelu ili "
     "telefonu. Kroz Vindex — svaki rok se automatski evidentira i advokat dobija "
     "e-mail podsetnik dan pre isteka."),
    ("Dokumentacija predmeta je rasuta",
     "Fajlovi su po folderima, imejlovi po sandučetu, beleške po papiru. "
     "Kroz Vindex — klijent, predmet, svi dokumenti, hronologija i beleške "
     "nalaze se na jednom mestu, dostupne sa svakog uređaja."),
    ("Analiza dokumenata oduzima ceo dan",
     "Presude, ugovori i podnesci čitaju se ručno. "
     "Kroz Vindex — advokat učita dokument i sistem automatski izvlači stranke, "
     "ključne datume, tužbene zahteve i potencijalne rizike."),
    ("Izrada podnesaka je spora i ponavljajuća",
     "Svaka tužba, žalba ili ugovor piše se iznova od nule. "
     "Kroz Vindex — advokat odabere vrstu podneska, unese podatke predmeta i "
     "sistem generiše nacrt za sekunde, koji advokat zatim doradi."),
    ("Billing i naplata honorara nisu sistematizovani",
     "Sati rada se ne beleže tačno, a fakture se prave ručno. "
     "Kroz Vindex — tajmer po predmetu, AKS tarifni obračun i "
     "faktura u PDF formatu generišu se jednim klikom."),
]
for naziv, opis in problemi:
    story.append(tacka(f"{b(naziv)}: {opis}"))
    story.append(sp(2))

# ── 3. Šta advokat radi kroz Vindex ───────────────────────────────────────────
story.append(nsek("3. Šta advokat radi kroz Vindex AI — korak po korak"))
story.append(Paragraph(
    "Vindex prati advokataov radni dan od početka do kraja:", TEKST))
koraci = [
    [Paragraph(b("Korak"), TABELAH),
     Paragraph(b("Akcija u Vindex-u"), TABELAH),
     Paragraph(b("Rezultat"), TABELAH)],
    [Paragraph("Novi klijent", TABELAT),
     Paragraph("Advokat otvori predmet, unese podatke klijenta ili ih skenira iz dokumenta", TABELAT),
     Paragraph("Predmet je odmah aktivan, rokovi se prate automatski", TABELAT)],
    [Paragraph("Istraživanje", TABELAT),
     Paragraph("Postavi pitanje na srpskom: 'Koji je rok zastarelosti za naknadu štete?'", TABELAT),
     Paragraph("Tačan odgovor sa citatom iz ZOO i oznakom člana za 3 sekunde", TABELAT)],
    [Paragraph("Analiza dokumenta", TABELAT),
     Paragraph("Učita presudu, ugovor ili podnesak u PDF formatu", TABELAT),
     Paragraph("Sistem izvlači sve ključne elemente i markira rizike", TABELAT)],
    [Paragraph("Izrada nacrta", TABELAT),
     Paragraph("Odabere vrstu dokumenta (tužba, žalba, ugovor) i potvrdi podatke", TABELAT),
     Paragraph("Kompletan nacrt podneska za sekunde, spreman za doradu", TABELAT)],
    [Paragraph("Praćenje rokova", TABELAT),
     Paragraph("Pregleda kalendar ročišta i zakonskih rokova za tekući mesec", TABELAT),
     Paragraph("E-mail podsetnik dan pre svakog roka, automatski", TABELAT)],
    [Paragraph("Naplata", TABELAT),
     Paragraph("Po završetku predmeta generiše fakturu", TABELAT),
     Paragraph("AKS tarifa je automatski obračunata, faktura u PDF-u jednim klikom", TABELAT)],
]
tbl = Table(koraci, colWidths=[3.5*cm, 7*cm, 6*cm])
tbl.setStyle(TableStyle([
    ("BACKGROUND",    (0, 0), (-1, 0),  TAMNA),
    ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, SVETLA]),
    ("GRID",          (0, 0), (-1, -1), 0.3, colors.HexColor("#cbd5e1")),
    ("VALIGN",        (0, 0), (-1, -1), "TOP"),
    ("TOPPADDING",    (0, 0), (-1, -1), 6),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ("LEFTPADDING",   (0, 0), (-1, -1), 8),
]))
story.append(tbl)

# ── 4. Analiza tržišta ─────────────────────────────────────────────────────────
story.append(nsek("4. Analiza tržišta — Srbija i region"))
story.append(Paragraph(
    f"U Srbiji je registrovano oko {b('11.000 advokata')} i veći broj pravnih lica koja "
    "svakodnevno koriste pravne resurse. Region Zapadnog Balkana — Bosna i Hercegovina, "
    "Crna Gora, Severna Makedonija, Hrvatska — dodaje još "
    f"{b('25.000 – 35.000')} pravnih profesionalaca koji dele sličan pravni sistem "
    "i jezičko područje.", TEKST))
story.append(Paragraph(
    f"{b('Ključni nalaz analize tržišta:')} Nakon detaljnog pregleda dostupnih rešenja "
    "na srpskom i regionalnom tržištu, ne postoji niti jedan konkurentski proizvod koji "
    "kombinuje pretragu srpskih zakona, upravljanje predmetima, analizu dokumenata i "
    "billing u jednoj platformi na srpskom jeziku. "
    "Postoje parcijalna rešenja — portali za pretragu zakona, generički CRM sistemi — "
    "ali nijedan integrisani pravni operativni sistem.", TEKST))
story.append(Paragraph(
    f"Vindex AI je {pl('jedina platforma ovog tipa na srpskom jeziku')} — "
    "to nije marketinška tvrdnja, to je verifikovana tržišna pozicija.", TEKST))

# ── 5. Inspiracija ─────────────────────────────────────────────────────────────
story.append(nsek("5. Globalni uzori i inspiracija"))
story.append(Paragraph(
    "Vindex AI je razvijan uz pažljivo praćenje vodećih svetskih platformi koje su "
    "transformisale pravnu industriju u SAD, Kanadi i Velikoj Britaniji. "
    "Ovi projekti su definisali standard koji srpsko tržište još uvek ne poznaje:", TEKST))
uzori = [
    ("Harvey AI (SAD)",
     "Operativna AI platforma za pravnike, podržana od OpenAI i vodećih investicionih "
     "fondova iz Silicijumske doline. Koriste je vodeće advokatske kancelarije u SAD i Evropi. "
     "Vrednovanje: 3 milijarde dolara (2024). Harvey je dokazao da AI može biti pouzdan "
     "partner advokatu — ne zamena, nego višestruki uvećavač produktivnosti."),
    ("Clio (Kanada)",
     "Vodeća platforma za upravljanje advokatskom kancelarijom. Vrednovanje 1,6 milijardi dolara. "
     "Clio je definisao standard za upravljanje predmetima, billing i dokumentaciju u "
     "pravnoj industriji. Vindex implementira isti princip za srpsko tržište, "
     "uz AI sloj koji Clio nema."),
    ("Lexion / Kira Systems",
     "Platforme za automatsku analizu pravnih dokumenata — ugovora, presuda i podnesaka. "
     "Koriste ih Fortune 500 kompanije za ubrzanje pravnih procesa. "
     "Isti princip primenjen u Vindex-u, prilagođen srpskim pravnim formama i terminologiji."),
    ("Luminance (UK)",
     "AI platforma za pravnu analizu koju koriste vodeće evropske advokatske kancelarije. "
     "Pokazuje da je evropsko tržište još uvek u ranoj fazi — "
     "što znači da Srbija i region imaju otvoren prozor prilike."),
    ("Jus Mundi (Francuska)",
     "Višejezična platforma za pretragu sudske prakse koja pokriva više jurisdikcija. "
     "Direktan uzor za Vindexovu strategiju ekspanzije na region Zapadnog Balkana."),
]
for naziv, opis in uzori:
    story.append(tacka(f"{b(naziv)}: {opis}"))
    story.append(sp(3))
story.append(Paragraph(
    f"Zajednički imenitelj svih ovih projekata: "
    f"{b('advokatima treba sistem koji razume njihov jezik, njihov pravni sistem i njihove predmete.')} "
    "Vindex je taj sistem za srpsko govorno područje.", TEKST))

# ── 6. Vizija ──────────────────────────────────────────────────────────────────
story.append(nsek("6. Vizija i plan razvoja"))
story.append(Paragraph(
    "Vindex AI nije alat za jednu namenu — to je osnova za sveobuhvatan "
    "pravni operativni sistem koji prati advokataov celokupan radni život. "
    "Razvojni put je definisan u tri faze:", TEKST))
faze = [
    ("Faza 1 — Operativna osnova (danas aktivno)",
     "Funkcionalna platforma koja pokriva celokupno svakodnevno poslovanje: "
     "pretraga zakona, upravljanje predmetima i klijentima, praćenje rokova, "
     "analiza dokumenata, izrada podnesaka, billing. "
     "Cilj: prvih 50 advokata koji svakodnevno vode predmete kroz Vindex."),
    ("Faza 2 — Specijalizacija i premium podaci (2026–2027)",
     "Integracija nejavne sudske prakse po oblastima: upravno, radno, privredno pravo. "
     "Specijalizovani moduli po tipu prakse. "
     "Klijentski portal za direktnu komunikaciju između advokata i stranke. "
     "Cilj: 200–500 korisnika, pretplata po kancelariji."),
    ("Faza 3 — Regionalna ekspanzija (2027–2028)",
     "Prilagođavanje za Bosnu i Hercegovinu, Crnu Goru i Severnu Makedoniju — "
     "slični pravni sistemi, isto jezičko područje. Potencijalno i Hrvatska (EU okvir). "
     "Dugoročni cilj: vodeći pravni operativni sistem na prostoru "
     "Zapadnog Balkana i bivše Jugoslavije."),
]
for naziv, opis in faze:
    story.append(KeepTogether([
        Paragraph(naziv, FAZANAZIV),
        Paragraph(opis, TEKST),
    ]))

# ── 7. Zašto sada ─────────────────────────────────────────────────────────────
story.append(nsek("7. Zašto je ovo pravi trenutak"))
story.append(Paragraph(
    f"Srpska pravna industrija je {b('5–7 godina iza')} zapadnih tržišta u usvajanju "
    "digitalnih alata za pravnu praksu. To što je Harvey AI u SAD već mainstream — "
    "u Srbiji tek počinje. Ovo je prozor prilike koji se zatvara u roku od 2–3 godine, "
    "kada će i internacionalni igrači početi da gledaju u region.", TEKST))
story.append(Paragraph(
    f"Prednost Vindex AI je što {b('razume srpski pravni sistem iznutra')} — "
    "terminologiju, hijerarhiju pravnih izvora, specifičnosti svakog zakona. "
    "Ni jedna strana platforma ne može to da replikuje bez godina lokalnog rada "
    "i lokalnih podataka. To je konkurentska prednost koju novac ne može da kupi.", TEKST))
story.append(Paragraph(
    f"Zemlja sa 11.000 advokata i {b('bez ijednog pravnog operativnog sistema')} "
    "nije malo tržište — to je netaknuta kategorija.", TEKST))

# ── 8. Kontakt ────────────────────────────────────────────────────────────────
story.append(nsek("8. Kontakt i sledeći korak"))
story.append(Paragraph(
    "Vindex AI je aktivan sistem koji danas koriste advokati na stvarnim predmetima. "
    "Otvoreni smo za pilot program sa pravnicima koji žele da testiraju platformu "
    "i svojom povratnom informacijom oblikuju njen dalji razvoj.", TEKST))
story.append(sp(8))
story.append(Paragraph("✉   benny13.n@gmail.com", TEKST))
story.append(Paragraph("🌐   vindex.rs", TEKST))
story.append(sp(20))
story.append(hr())
story.append(Paragraph(
    "Vindex AI © 2026  —  Ovaj dokument je poverlјiv i namenjen isklјučivo primaocu.",
    FOOTER_S))

doc.build(story)
print(f"PDF generisan: {OUTPUT}")
