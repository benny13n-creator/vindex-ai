# VINDEX AI — SINTETIČKI DEMO PREDMET (specifikacija)

**Scenario nije kreiran** — ovo je specifikacija koju sledeća misija sprovodi.

Pravni predmet, jer je advokatura prvo tržište; ali biran tako da **svaki pojam ima ekvivalent
u drugim delatnostima**.

---

## ZAŠTO NAPLATA POTRAŽIVANJA

Razumljiv nepravniku · ima dokumente, datume, rokove i protivrečnost · **i banka, i osiguranje,
i revizija imaju isti oblik**: obaveza + dokumentacija + rok + sporna činjenica.

Time jedan snimak služi i pravnoj poruci i široj poruci o primenljivosti — bez pravljenja
posebnih materijala po delatnosti.

## STRANKE — potpuno izmišljene

Tužilac: **„Meridijan Trade d.o.o."** · Tuženi: **„Aurora Logistika d.o.o."**

Bez stvarnih firmi, bez ličnih imena, bez PIB-a i matičnog broja.
**Provera pre upotrebe:** nijedan naziv ne sme postojati u APR-u.

## DOKUMENTI (4)

| # | Dokument | Uloga u demonstraciji |
|---|---|---|
| 1 | Ugovor o isporuci | izvor obaveze i roka plaćanja |
| 2 | Faktura | iznos i datum dospeća |
| 3 | Opomena pred tužbu | dokaz o pozivu na plaćanje |
| 4 | Odgovor druge strane | **unosi protivrečnost** — tvrdi delimično plaćanje |

Dokument 4 postoji da bi se pokazalo **uočavanje protivrečnosti**. Bez njega demonstracija
pokazuje samo sažimanje, a to je roba široke potrošnje koju ima svako.

## ČINJENICE koje sistem treba da izvuče

iznos duga · datum dospeća · datum opomene · tvrdnja o delimičnom plaćanju *(sporna)*

## ROKOVI

zastarelost potraživanja · rok za odgovor na tužbu

## PRIMER POREKLA — srce demonstracije

```
Dug: 1.240.000 RSD          [izvor: faktura-2026-0431.pdf]
Dospelo: 15.03.2026.        [izvor: ugovor-o-isporuci.pdf, čl. 7]
Sporno: delimično plaćanje  [izvor: odgovor-druge-strane.pdf]
```

**Ova tri reda su najvredniji vizuel na celom sajtu.** Objašnjavaju diferencijator bez ijedne
rečenice marketinga.

## DATUMI

Isključivo prošli ili neutralni. Nijedan datum ne sme sugerisati stvarni tekući spor.

## BEZBEDNOSNA PRAVILA

Nijedno lično ime · nijedna stvarna firma · nijedan stvarni broj predmeta · nijedan stvarni sud.

Dokumenti se **pišu za ovu svrhu** — nikad anonimizovani stvarni podnesci. Anonimizacija je
nepouzdana i ostavlja tragove u formulacijama, brojevima i strukturi.

## GDE ŽIVI

Zaseban demo nalog, **odvojen od produkcijskih podataka**. Ne kreirati u nalogu vlasnika pored
stvarnih predmeta — snimak lako uhvati bočnu traku sa tuđim predmetima.

---

## JAVNI API — odluka

`routers/export.py` izlaže `/v1/query` sa API ključevima (`api_kljucevi`).

**Ne stavljati na sajt sada:** nije dokazano produkcijski spreman, a ekran sa ključevima nije
bezbedan za snimanje.

Pominjati **isključivo pojmovno**, u sekciji o arhitekturi: *„drugi sistemi mogu da čitaju iz
sloja"* — bez naziva endpointa, bez primera poziva, bez prikaza ključa.
