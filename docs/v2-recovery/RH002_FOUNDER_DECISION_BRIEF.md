# RH002 — odluke za foundera

**Ukratko:** propust sa poverljivim beleškama **i dalje postoji u produkciji**. Popravka je spremna i proverena kao Draft PR #11 ka `main`, ali čeka vaše odobrenje. U RH002 sam našao još jednu rupu iste vrste: kolega je mogao da *upiše* belešku u graf vašeg predmeta. Ta rupa je zatvorena u istom PR-u. Ništa nije spojeno, deployovano ni migrirano.

## 1. Najhitnije: hotfix (PR #11)

**Šta je pogrešno u produkciji danas.** Advokat iz iste kancelarije, bez delegacije, može:
- da vidi vaše beleške o predmetima i klijentima, uključujući i one koje AI chat ubacuje u njegove odgovore;
- da potvrdi ili deaktivira vašu belešku;
- **(novo)** da pripoji svoj tekst grafu vašeg predmeta. Vi taj tekst onda vidite kao deo svog predmeta, a završava i u vašem AI odgovoru.

**Ko može da iskoristi propust.** Samo prijavljen korisnik koji je aktivni član iste kancelarije. Spoljni korisnici i druge kancelarije ne mogu.

**Zašto je hitno.** Repozitorijum na GitHub-u je **javan**. Opis popravke i test koji reprodukuje napad vidljivi su svima od trenutka push-a.

**Šta je provereno:**
- pre popravke napad uspeva, posle popravke ne uspeva;
- opšte beleške kancelarije (npr. o sudiji) i dalje vide svi;
- delegacija i dalje radi, a opoziv delegacije odmah zatvara pristup;
- CI ne pokazuje nijedan nov pad u odnosu na `main`, Docker slika se gradi, gitleaks nije našao tajne.

**Rollback:** jedan klik u Render-u („Rollback“ na prethodni deploy). Nema promene baze.

**Odluka:** odobrite spajanje PR #11 u `main` i deploy. Posle toga treba izvršiti produkcionu proveru sa dva **izmišljena** test naloga (postupak je u PR-u).

## 2. Da li je neko stvarno video tuđe beleške?

**Nepoznato.** Ove stranice nisu beležile ko je šta čitao, pa to ne mogu da dokažem ni da opovrgnem. To što niko nije prijavio problem nije dokaz.

Prvi korak koji ne otkriva ničije podatke: u Supabase-u sami pokrenite brojanje koliko kancelarija ima **više od jednog aktivnog člana**.
- Ako je odgovor 0, niko nije mogao da vidi tuđe beleške.
- Ako nije 0, posavetujte se sa pravnikom da li je potrebno obaveštavanje (zaštita podataka, advokatska tajna). Tu odluku ne donosim ja.

## 3. Redosled izdanja V2

PR #10 i dalje pokazuje na **staru** NS008 granu, bez bezbednosnih popravki. Najmanja ispravka je da odobrite „fast-forward“ (pomeranje bez prepisivanja istorije) za tri grane:
- NS006 → rh001-ns006;
- NS007 → rh001-ns007;
- NS008 → rh001-ns008.

Posle toga postojeći PR-ovi automatski sadrže popravke. Proverio sam da se hotfix spaja bez konflikata sa svim granama.

Redosled, uz vaše odobrenje na svakom koraku:
1. hotfix;
2. NS006;
3. NS007 (prvo migracija 136, pa kod; Cron posebno);
4. NS008.

## 4. NS007: migracija 136 i Cron

- **Migracija 136** samo dodaje nove tabele i ne dira postojeće, pa može da se primeni pre deploy-a NS007. Da li je već primenjena: nepoznato (nemam pristup bazi). Pretpostavka je da nije.
- **Ispravka ranije tvrdnje.** Pad rasporedivača gubi **jedan ciklus**, a ne „najviše jedan sat“. Uz noćni raspored to znači ~24 sata kašnjenja: priprema za sutrašnje ročište stiže tek ujutru na dan ročišta.
- **Odluka:** koliko unapred advokat mora da ima pripremu? Od toga zavisi izbor:
  - A: noćno;
  - B: noću i pre podne;
  - C: svakog sata radnim danima.

  Ako izaberete noćno, preporučujem `AUTONOMY_HEARING_WINDOW_DAYS = 2`.

## 5. Zaštita GitHub grana

Trenutno je nema, ni na `main`. Predlog (ne menjam ga bez vaše dozvole):
- na `main`: zabrana prepisivanja i brisanja, spajanje samo kroz PR i obavezne samo provere koje su već zelene;
- na release granama: zabrana prepisivanja i brisanja.

Napomena: agent koristi vaš admin pristup. Zato pravilo „admin sme da zaobiđe“ ne bi zaustavilo ni agenta.

## Statusi

- **HOTFIX:** spreman za vaše odobrenje.
- **Bezbednost produkcije danas:** POZNATO IZLOŽENA.
- **NS006:** spreman, uz fast-forward i spajanje posle hotfix-a.
- **NS007:** BLOKIRAN. Čeka migraciju 136, izbor kadence i Cron.
- **NS008:** BLOKIRAN. PR #10 ne sadrži popravke dok se ne uradi fast-forward ili ne otvori nov PR. Brzina na pravim podacima je nepoznata.
- **Beta:** NO-GO dok hotfix nije u produkciji.

**Sledeći korak:** odobrite i spojite PR #11 (https://github.com/benny13n-creator/vindex-ai/pull/11), pa deploy i produkciona provera.

Detalji: `docs/v2-recovery/RH002_SECURITY_AND_RELEASE_EVIDENCE.md`.
