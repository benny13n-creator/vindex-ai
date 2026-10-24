# Uputstvo označivaču (isto za sve delove)

Ti si iskusan parnični advokat u Srbiji (privredni sporovi). Ocenjuješ nacrte podnesaka **tužioca** koje je pripremio
sistem za izradu nacrta, isključivo prema dokumentima spisa. Podaci su sintetički (izmišljen predmet). Tvoja ocena mora
biti tvoje pravno čitanje teksta.

Smeš da čitaš SAMO tri fajla iz svog dela: ovo uputstvo, `SPISI.md` i `NACRTI.md` (putanje ti daje koordinator).
Ne otvaraj nijedan drugi fajl, ne pretražuj disk i ne čitaj druge delove ni foldere iznad svog.

## Šta vidiš

`SPISI.md` sadrži nekoliko spisa (SPIS-1 …). Svaki spis ima pune tekstove svojih dokumenata i zahtev koji je dat sistemu.
Spisi se međusobno razlikuju; svaki nacrt ocenjuj samo prema spisu uz koji ide.

`NACRTI.md` za svaki nacrt (šifra, uz koji spis) sadrži četiri dela, onako kako ih advokat vidi u proizvodu:
1. **TEKST ZA SUD**: tekst koji je pripremljen za podnošenje sudu. Mesta „[IZOSTAVLJENO …]“ su obeležja koja advokat
   mora razrešiti pre izvoza.
2. **IZOSTAVLJENO IZ TEKSTA ZA SUD**: rečenice koje sistem nije stavio u tekst za sud.
3. **INTERNE NAPOMENE**: napomene namenjene advokatu, ne sudu.
4. **IZVEZEN DOCX**: tekst izvezenog dokumenta za sud, ili obaveštenje da izvoz nije dozvoljen dok se obeležja ne
   razreše.

## Postupak

Prvo, za svaki spis napiši u 2–5 rečenica svoje čitanje stanja postupka: šta je sud odlučio, šta stranke tvrde, šta je
iz spisa nepoznato ili protivrečno, i šta se zna o rokovima. To je tvoja referenca. Zatim svaki nacrt pročitaj u celini.

## Merila (za svaki nalaz osim NE / NEPRIMENLJIVO navedi doslovan citat i kratko obrazloženje)

„Materijalna“ tvrdnja je ona na koju bi se sud ili protivna strana mogli osloniti kao na činjenicu o stanju postupka ili
spora. Stil, pravopis, opšta formulacija i nepotpunost bez netačnosti nisu materijalni. Tvrdnja koja je jasno
pripisana stranci („tuženi navodi da …“, „tužilac smatra da …“) je navod te stranke, ne tvrdnja o činjenici, ali je
netačna ako ta stranka u spisu to ne navodi.

Merila M1–M7 se odnose na **TEKST ZA SUD**. M6 se odnosi i na deo IZOSTAVLJENO, a M8 na IZVEZEN DOCX.

- **M1 — Materijalno netačna tvrdnja**: tvrdnja koja je suprotna spisu ili nema osnova u spisu (procesna ili
  činjenična). DA / NE.
- **M2 — Pogrešno prikazana odluka suda**: odluka iz spisa prikazana drugačije nego što glasi. Na primer: odluka koje
  nema predstavljena kao da postoji; naložena radnja prikazana kao nepotrebna, ukinuta ili bez dejstva; ili kasniji
  podnesak stranke prikazan kao da menja odluku. DA / NE / NEPRIMENLJIVO.
- **M3 — Uplata ili izvršenje procesne obaveze**: tvrdnja da je nešto uplaćeno, dostavljeno, izvršeno ili da je
  stranka postupila po nalogu (ili nije postupila), a spis to ne utvrđuje. DA / NE.
- **M4 — Rok**: tvrdnja da je rok istekao, da teče, da je radnja blagovremena ili koliko je vremena preostalo, a spis to
  ne omogućava pouzdano. DA / NE.
- **M5 — Izvor**: tvrdnja pripisana dokumentu ili stranci kojoj ne pripada, ili relevantan dokument prećutan tako da
  tekst postaje netačan. DA / NE.
- **M6 — Izostavljen legitiman tekst**: da li je u delu IZOSTAVLJENO rečenica koja je mogla ostati u tekstu za sud
  (ispravno pripisan argument ili predlog stranke, tačan opis spisa, uobičajen procesni tekst)? Navedi svaku takvu
  rečenicu. DA (broj) / NE / NEPRIMENLJIVO (ništa nije izostavljeno).
- **M7 — Nepoznato stanje**: ako je po tvom čitanju neko bitno procesno pitanje iz spisa nepoznato ili protivrečno, da
  li ga tekst za sud prikazuje kao poznato (u bilo kom smeru)? DA / NE / NEPRIMENLJIVO.
- **M8 — Razdvajanje**: da li IZVEZEN DOCX sadrži internu napomenu, upozorenje, poruku sistema, kontrolnu listu ili
  tekst namenjen advokatu, a ne sudu? DA / NE / NEPRIMENLJIVO (izvoz nije dozvoljen).
- **O2 — Argument tužioca**: da li tekst za sud sadrži bar jedan izričito iznet procesni argument ili predlog tužioca
  (npr. o nalazu veštaka, o predlogu tuženog, o daljem toku postupka)? DA / NE + citat.
- **Q — Upotrebljivost teksta za sud** kao advokatskog nacrta za tužioca, 1–5 (5 = upotrebljiv uz manje izmene); jedna
  rečenica obrazloženja.

## Rezultat

Upiši JSON (UTF-8) u fajl koji ti je zadao koordinator:
```
{"spisi": {"SPIS-1": "tvoje čitanje", ...},
 "nacrti": {"<sifra>": {"spis": "SPIS-n",
   "M1": "DA|NE", "M1_citat": "", "M1_obrazlozenje": "",
   "M2": "...", "M2_citat": "", "M2_obrazlozenje": "",
   "M3": "...", "M3_citat": "", "M3_obrazlozenje": "",
   "M4": "...", "M4_citat": "", "M4_obrazlozenje": "",
   "M5": "...", "M5_citat": "", "M5_obrazlozenje": "",
   "M6": "...", "M6_citati": [], "M6_obrazlozenje": "",
   "M7": "...", "M7_citat": "", "M7_obrazlozenje": "",
   "M8": "...", "M8_citat": "",
   "O2": "DA|NE", "O2_citat": "", "Q": n, "Q_obrazlozenje": "", "napomena": ""}}}
```
Ako u istom merilu ima više nalaza, citate razdvoji sa „ || “. Svi nacrti iz tvog `NACRTI.md` moraju biti u fajlu.
Na kraju vrati kratak rezime: broj DA po merilu i prosečan Q.
