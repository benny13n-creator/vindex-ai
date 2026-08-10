# VINDEX AI — RIZICI PRE IZRADE SAJTA

Redosled po tome koliko blokiraju izradu.

## MORA SE REŠITI PRE PISANJA KODA

| # | Stavka | Zašto blokira | Ko rešava |
|---|---|---|---|
| 1 | **Prikazi proizvoda** | Sajt bez ijednog dokaza da proizvod radi je najveći razlog za nepoverenje (Red Team: VISOKA). Trenutno nema upotrebljivog prikaza. | vlasnik |
| 2 | **Kontakt i pravni podaci firme** | Nema ih u repozitorijumu. Sajt bez identiteta pravnog lica deluje kao hobi projekat i onemogućava DPA. | vlasnik |
| 3 | **Odluka o izrazu „operativni sistem"** | Sukob sa `PUBLIC_CLAIMS.md` je prijavljen, nije rešen. Nisam smeo da ga rešim dodavanjem tvrdnje. | vlasnik |
| 4 | **Gde vodi prijava za testiranje** | Forma, e-pošta, ili postojeći `waitlist` ruter? Postoji `routers/waitlist.py`, ali veza sa sajtom nije odlučena. | vlasnik + izrada |

## MORA SE REŠITI PRE OBJAVLJIVANJA

| # | Stavka | Rizik |
|---|---|---|
| 5 | **Ugovor sa dobavljačem AI modela** | Bez njega se ne sme reći ništa o korišćenju podataka za treniranje — a to je prvo pitanje opreznog advokata. |
| 6 | **Cena** | U repozitorijumu više neusaglašenih varijanti. Sajt je ne sme pominjati dok se ne odluči. |
| 7 | **Kontrast `#00d4ff` na `#010308`** | Granični slučaj za WCAG AA. Meriti pre upotrebe za tekst, ne pretpostavljati. |
| 8 | **Iscureli OpenAI ključ u javnom repou** | Nije rizik sajta, ali javan repo znači da posetilac može da vidi kod. Odvojena operativna stavka. |

## TEHNIČKI RIZICI

| # | Rizik | Ublažavanje |
|---|---|---|
| 9 | Service worker (`static/sw.js`) kešira stari sadržaj | Sajt držati **van** opsega postojećeg SW-a; ne dirati `CACHE_NAME` aplikacije |
| 10 | Uvođenje build sistema zbog tri strane | Ne uvoditi. Vanilla HTML+CSS. Aplikacija radi bez njega 23k linija dugo. |
| 11 | Ruta `/` već postoji u `api.py:1478` | Odlučiti: sajt kao zaseban statički hosting ili nova ruta. **Ne menjati postojeću bez dogovora.** |
| 12 | PWA manifest i ikone su aplikacijine | Sajt ne sme da ih pregazi |

## RIZICI POZICIONIRANJA

| # | Rizik | Ublažavanje |
|---|---|---|
| 13 | Preširoko → nefokusirano | Advokatura imenovana u podnaslovu; ostalo jedan red |
| 14 | Preusko → zaključano u pravo | „AI za pravo" zabranjeno u naslovu, navigaciji i domenu |
| 15 | Tvrdnje o više dobavljača | Fabric ima **0 produkcijskih poziva** — samo kao arhitektura |
| 16 | Naduvavanje kroz „operativni sistem" | Vidi stavku 3 |

## NEPOZNATO — označeno kao takvo

- Da li postoji domen i gde se sajt hostuje — **UNKNOWN**
- Da li postoji logo u vektorskom obliku — **UNKNOWN**
- Da li Stefan Gojković pristaje da bude imenovan javno — **UNKNOWN, ne koristiti bez saglasnosti**
- Da li postoji fotografija ili biografija osnivača za sekciju poverenja — **UNKNOWN**

## ŠTA NE BLOKIRA

Odsustvo bloga, FAQ-a, cenovnika, strane „O nama" i stranica po delatnostima. To su **P2** i
njihovo odsustvo je u ovoj fazi prednost, ne nedostatak.
