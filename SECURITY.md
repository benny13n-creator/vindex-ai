# Vindex AI — Bezbednosna Politika

*Poslednje ažuriranje: 2026-06-18*

---

## Pregled

Vindex AI je dizajniran za advokatske kancelarije koje obrađuju poverljive klijentske podatke pod zakonskom obavezom čuvanja tajne. Svaka tehnička odluka u sistemu odražava ovaj zahtev.

---

## 1. Enkriptovanje Podataka

### Polja u bazi podataka
Sledeća polja su enkriptovana **AES-256-GCM** pre upisa u bazu — čak i u slučaju kompromitacije baze, podaci su nečitljivi:

| Polje | Klasa | Standard |
|-------|-------|----------|
| JMBG / broj LK | Klijent | AES-256-GCM |
| Broj pasoša | Klijent | AES-256-GCM |
| PIB (opciono) | Klijent | AES-256-GCM |
| SEF API ključ | Integracije | AES-256-GCM |

Ključ za enkripciju (`FIELD_ENCRYPTION_KEY`) se čuva isključivo u environment varijablama i nikada nije deo koda ili baze. Aplikacija odbija da se pokrene ako ključ nije validan.

### Lozinke
Svi korisnički nalozi koriste **Argon2id** — algoritam koji je pobednik Password Hashing Competition i preporučen standard za zaštitu lozinki od brute-force napada.

### Transport
Sva komunikacija se odvija isključivo preko **HTTPS/TLS**. HTTP je blokiran na infrastrukturnom nivou.

---

## 2. Row Level Security (Supabase)

Svaka tabela u bazi podataka ima aktiviranu **Row Level Security (RLS)** politiku. Ovo znači da čak i ako napadač dobije direktan pristup bazi, ne može videti podatke koji mu ne pripadaju.

Princip je jednostavan: svaki upit automatski dodaje uslov `WHERE user_id = trenutni_korisnik`. Nema izuzetaka.

| Tabela | RLS | Politika |
|--------|-----|----------|
| predmeti | ✅ | user_id = auth.uid() |
| klijenti | ✅ | user_id = auth.uid() |
| predmet_klijenti | ✅ | via predmeti.user_id |
| billing_entries | ✅ | user_id = auth.uid() |
| fakture | ✅ | user_id = auth.uid() |
| dokumenti | ✅ | user_id = auth.uid() |
| komentari | ✅ | user_id = auth.uid() |
| rocista | ✅ | user_id = auth.uid() |
| notifications | ✅ | user_id = auth.uid() |
| sef_podesavanja | ✅ | user_id = auth.uid() |
| client_portal_tokens | ✅ | user_id = auth.uid() |
| audit_log | ✅ | append-only, bez DELETE |

---

## 3. Multi-Tenant Izolacija

Vindex AI je **multi-tenant** sistem — više advokatskih kancelarija koristi isti sistem, ali nikada ne mogu videti međusobne podatke.

Izolacija je implementirana na **dva nivoa** (defense in depth):
1. **API nivo**: Svaki upit u bazu eksplicitno filtrira po `user_id` autentifikovanog korisnika
2. **Baza podataka (RLS)**: Čak i kada bi API propustio grešku, baza odbija vraćanje tuđih podataka

Ovo je verifikovano automatizovanim testovima koji kreiraju dva nezavisna korisnička naloga i pokušavaju svaki mogući vid pristupa između naloga.

---

## 4. Autentifikacija i Sesije

- **JWT tokeni** (JSON Web Token) — svaki zahtev mora imati validan token
- Tokeni se verifikuju trostrukim mehanizmom: Supabase SDK → HS256 → ES256/JWKS
- **Server-side logout**: `/api/logout` invaliduje sve aktivne sesije na nivou baze (ne samo klijenta)
- Token lifetime: 1h pristupni token, 7d refresh token (Supabase default)
- **Brute force zaštita**: Supabase Auth uvodi exponential backoff nakon neuspešnih pokušaja prijave

---

## 5. Dokumenti i Fajlovi

- Svi dokumenti se čuvaju u **privatnom Supabase Storage bucketu** — nema javnih URL-ova
- Pristup dokumentu zahteva generisanje **signed URL** sa rokom trajanja od 3600 sekundi
- Putanje u storage-u su **randomizovane UUID vrednosti** — nije moguće pogoditi URL tuđeg dokumenta
- Originalni nazivi fajlova se sanitizuju pre čuvanja (uklanjaju se specijalni karakteri)

---

## 6. Klijentski Portal

Klijentski portal (link koji advokat šalje klijentu za pregled predmeta) koristi:
- **HMAC-SHA256 tokene** sa 256-bit entropijom
- Svaki token je vezan za tačno jedan predmet i jednog advokata
- Token hash se čuva u bazi — originalni token nikada nije sačuvan
- Svaki pristup portalnom linka proverava DB revokaciju (token se može opozvati u realnom vremenu)
- Maksimalni rok trajanja: 90 dana

---

## 7. AI Bezbednost

- Korisničke poruke se **nikada ne ubacuju u sistemski prompt** — isključivo u `role: user`
- Sistemski prompti ne sadrže tajne, API ključeve, niti podatke o infrastrukturi
- **Prompt injection** testovi su redovno pokretani kao deo CI/CD procesa
- AI odgovori se renderuju kroz HTML escaping pre prikaza — nije moguć XSS napad kroz AI output

---

## 8. Audit Log

Sva kritična akcija u sistemu se beleži u audit log koji je:
- **Append-only**: nema UPDATE ni DELETE operacija
- Sadrži: ko, kada, šta (hash pitanja — ne originalni sadržaj)
- Usklađen sa ZZPL čl. 5(1)(f) — integritet i poverljivost podataka

---

## 9. Sigurnosni Headeri

Svaki HTTP odgovor sadrži:

```
X-Frame-Options: SAMEORIGIN
X-Content-Type-Options: nosniff
Content-Security-Policy: default-src 'self'; script-src 'self' cdn.jsdelivr.net ...
Permissions-Policy: microphone=(self)
```

---

## 10. Backup i Oporavak

| Aspekt | Implementacija |
|--------|---------------|
| Baza podataka | Supabase automatski backup svaki dan (Point-in-Time Recovery 7 dana) |
| Vektori (Pinecone) | Ingestion pipeline se može ponovo pokrenuti iz originalnih PDF-ova |
| Konfiguracija | Infrastructure-as-code, environment varijable u Render |

---

## 11. Sigurnosne Granice — Šta Ne Radimo

Radi transparentnosti, ovo je izvan trenutnog opsega:

- **E2E enkripcija poruka** — u planu za Q3 2026
- **SOC 2 sertifikacija** — u evaluaciji
- **Penetration testing treće strane** — planiran pre GA lansiranja

---

## 12. Prijavljivanje Sigurnosnih Propusta

Ako ste pronašli sigurnosni propust, molimo vas da nas kontaktirate direktno na:

**security@vindex.rs** (ili osnivač direktno)

Ne prijavljujte sigurnosne propuste kao javne GitHub issue-e. Dajemo razuman rok od 90 dana za ispravku pre javnog obelodanjivanja.

---

*Vindex AI — Pravna AI platforma za advokate u Republici Srbiji*
