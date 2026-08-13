-- =====================================================================
-- PINE-02 — PLAN MUTACIJE: backfill `predmet_dokumenti.content_sha256`
--
-- STATUS: NIJE IZVRŠENO. Ovo je plan, ne migracija.
-- Generisano forenzičkim read-only sprintom PINE-02 nad baseline-om 053c3cc4.
--
-- ŠTA RADI: upisuje kanonski identitet sadržaja u 43 reda kojima je kolona NULL.
--
-- ODAKLE VREDNOSTI: svaka vrednost je izlaz PRODUKCIJSKE funkcije
--   shared/vector_identity.py :: verzija_dokumenta(tekst_sadrzaj)
--   = sha256("e1|" || tekst_sadrzaj).hexdigest()[:32]
-- izračunate nad `tekst_sadrzaj` koji VEĆ STOJI u tom istom redu.
-- SQL NE računa heš sam (Postgres `digest()` nad TEXT bi zavisio od
-- server_encoding i od toga da li je pgcrypto instaliran) — vrednosti su
-- literali, tako da je ono što se upisuje tačno ono što je izmereno.
--
-- ZAŠTITE UGRAĐENE U SVAKI `UPDATE`:
--   1. `WHERE content_sha256 IS NULL` — nikad ne prepisuje postojeću vrednost.
--   2. `AND id = '<uuid>'` — tačno jedan red.
--   3. transakcija sa završnom proverom broja pogođenih redova.
--
-- INVARIJANTNOST (v. PINE02-F4): `verzija_dokumenta` je tokom merenja izmenjena
-- u radnom stablu (dodat `kanonski_tekst()`). Vrednosti ispod su provereno
-- IDENTIČNE pod verzijom sa baseline-a 053c3cc4 i pod izmenjenom verzijom --
-- 43/43. Ako se normalizacija ubuduće promeni tako da dira kratke tekstove,
-- ovaj plan se mora ponovo izračunati pre pokretanja.
--
-- PREDUSLOV KOJI NIJE TEHNIČKI (v. PINE02-F1 u izveštaju):
--   posle ovog upisa `routers/smart_intake.py:1376` počinje da vraća
--   `duplikat_u_drugom_predmetu` za svaki budući upload istog sadržaja tog
--   korisnika. Svih 19 različitih sadržaja već postoji u ≥2 predmeta.
--   To je promena PONAŠANJA, ne samo podataka, i traži izričitu odluku.
-- =====================================================================

BEGIN;

-- Sanity: tačno 43 reda sa praznom kolonom pre upisa.
DO $$
DECLARE n int;
BEGIN
  SELECT count(*) INTO n FROM predmet_dokumenti WHERE content_sha256 IS NULL;
  IF n <> 43 THEN
    RAISE EXCEPTION 'PINE-02 preduslov nije ispunjen: ocekivano 43 NULL redova, nadjeno %', n;
  END IF;
END $$;


--  1/43  predmet=00a56895  tekst=533 zn.
UPDATE predmet_dokumenti SET content_sha256 = 'f6339d82e41dc682a7c942abe353c37d'
 WHERE id = 'abf8101c-8c16-4ad4-b492-0fc79f7eca4b' AND content_sha256 IS NULL;

--  2/43  predmet=00a56895  tekst=527 zn.
UPDATE predmet_dokumenti SET content_sha256 = '6cc189eba5fc07ffad3b329888d3441d'
 WHERE id = '3ed20dae-9aa1-4f20-a8e0-c716a52d7e4e' AND content_sha256 IS NULL;

--  3/43  predmet=00a56895  tekst=424 zn.
UPDATE predmet_dokumenti SET content_sha256 = 'aa51923b2408eaf07d828dea7951bf86'
 WHERE id = '39b7463a-52d8-4e47-b5cb-71b9768832b8' AND content_sha256 IS NULL;

--  4/43  predmet=0129f973  tekst=533 zn.
UPDATE predmet_dokumenti SET content_sha256 = 'f6339d82e41dc682a7c942abe353c37d'
 WHERE id = '0d39c48a-9e0a-428f-b6b8-fbfff3d43ecd' AND content_sha256 IS NULL;

--  5/43  predmet=0129f973  tekst=527 zn.
UPDATE predmet_dokumenti SET content_sha256 = '6cc189eba5fc07ffad3b329888d3441d'
 WHERE id = '3d177a32-bff6-496d-840d-c9dc099228f9' AND content_sha256 IS NULL;

--  6/43  predmet=0129f973  tekst=424 zn.
UPDATE predmet_dokumenti SET content_sha256 = 'aa51923b2408eaf07d828dea7951bf86'
 WHERE id = '67536829-53db-49b3-a688-a6f5a67eb5f0' AND content_sha256 IS NULL;

--  7/43  predmet=01f137cf  tekst=328 zn.
UPDATE predmet_dokumenti SET content_sha256 = '7e7c56f7f68d5f7e7a8284c1b33abe45'
 WHERE id = 'a93ef3df-6e2f-49b0-9bc1-2bf00b549674' AND content_sha256 IS NULL;

--  8/43  predmet=01f137cf  tekst=265 zn.
UPDATE predmet_dokumenti SET content_sha256 = '8700a5205ff96b8feb6cfb9b6db66e0f'
 WHERE id = 'f9f6c5f2-3fe7-42ac-bcbf-601a39c5cf20' AND content_sha256 IS NULL;

--  9/43  predmet=01f137cf  tekst=227 zn.
UPDATE predmet_dokumenti SET content_sha256 = '6adef833812a6b28af66392a5e84b0ce'
 WHERE id = '11d3e4a9-476d-44f8-9927-02218fe0a029' AND content_sha256 IS NULL;

-- 10/43  predmet=01f137cf  tekst=206 zn.
UPDATE predmet_dokumenti SET content_sha256 = '6b992662ea7c400054d9c0a3de9d7ca7'
 WHERE id = '0577f41e-cfc3-44d3-b4f1-58d1825c17b5' AND content_sha256 IS NULL;

-- 11/43  predmet=1f909976  tekst=405 zn.
UPDATE predmet_dokumenti SET content_sha256 = 'f1dfb14e71d1fe8f9376ee58a6a89e62'
 WHERE id = 'd363a085-2835-4f80-a7cb-a794c1b20bcc' AND content_sha256 IS NULL;

-- 12/43  predmet=1f909976  tekst=312 zn.
UPDATE predmet_dokumenti SET content_sha256 = '02f28aee6617badfb449cf4591009c93'
 WHERE id = '1880fc72-855f-40f6-bf92-f9974a0245e1' AND content_sha256 IS NULL;

-- 13/43  predmet=1f909976  tekst=580 zn.
UPDATE predmet_dokumenti SET content_sha256 = 'b6e182440e98f5d03d787fb0d0c7e47e'
 WHERE id = '3828c17b-3452-4170-8818-3022aa4deac6' AND content_sha256 IS NULL;

-- 14/43  predmet=26c12a60  tekst=346 zn.
UPDATE predmet_dokumenti SET content_sha256 = 'e55b7d0adec4cd80df8fd5a60a08746e'
 WHERE id = '52e76915-fcd6-43e2-b954-7bd3e2ef469f' AND content_sha256 IS NULL;

-- 15/43  predmet=26c12a60  tekst=77 zn.
UPDATE predmet_dokumenti SET content_sha256 = '599fec9a0d9e0968c1b2e708b4e431ed'
 WHERE id = 'b5ed492e-25eb-488f-9a82-6ad35acf84db' AND content_sha256 IS NULL;

-- 16/43  predmet=26c12a60  tekst=282 zn.
UPDATE predmet_dokumenti SET content_sha256 = '545342a763a4b0b1598908d6ae8a2d67'
 WHERE id = '88c36999-be39-4122-b6ab-3dee3349b382' AND content_sha256 IS NULL;

-- 17/43  predmet=47b4884e  tekst=405 zn.
UPDATE predmet_dokumenti SET content_sha256 = 'f1dfb14e71d1fe8f9376ee58a6a89e62'
 WHERE id = '72c461f5-85cb-480d-abce-b9b22ec11589' AND content_sha256 IS NULL;

-- 18/43  predmet=47b4884e  tekst=312 zn.
UPDATE predmet_dokumenti SET content_sha256 = '02f28aee6617badfb449cf4591009c93'
 WHERE id = '565aaaad-ca1e-43d6-b745-97db131bf7ab' AND content_sha256 IS NULL;

-- 19/43  predmet=47b4884e  tekst=580 zn.
UPDATE predmet_dokumenti SET content_sha256 = 'b6e182440e98f5d03d787fb0d0c7e47e'
 WHERE id = '42cd5e12-edeb-4a66-86fe-97c963a310ed' AND content_sha256 IS NULL;

-- 20/43  predmet=47dc4817  tekst=548 zn.
UPDATE predmet_dokumenti SET content_sha256 = 'dd541bad555c71c94969569d323c234b'
 WHERE id = '0050a23f-791a-4f52-a193-ec1133ff48ea' AND content_sha256 IS NULL;

-- 21/43  predmet=4f28f4b9  tekst=323 zn.
UPDATE predmet_dokumenti SET content_sha256 = '3a43c209ac80feb48cdd05ba42a6e03f'
 WHERE id = 'f77f8881-ee17-4c78-b142-45cd81c0f518' AND content_sha256 IS NULL;

-- 22/43  predmet=4f28f4b9  tekst=370 zn.
UPDATE predmet_dokumenti SET content_sha256 = '1a3d3140ef6bf10119240ec609f1ea60'
 WHERE id = 'c6481d9b-fac2-49bc-958c-d1e125a9c9b3' AND content_sha256 IS NULL;

-- 23/43  predmet=4f28f4b9  tekst=263 zn.
UPDATE predmet_dokumenti SET content_sha256 = 'eb8dd4dbe114882e0f41a226689977f3'
 WHERE id = '8f45a0c5-7590-44c5-a1ae-7d85ae979d84' AND content_sha256 IS NULL;

-- 24/43  predmet=4f28f4b9  tekst=107 zn.
UPDATE predmet_dokumenti SET content_sha256 = '875d3881a8c84c996127d31ca42a0591'
 WHERE id = 'db85b0d1-d82d-4d41-8b02-c168615a23c1' AND content_sha256 IS NULL;

-- 25/43  predmet=6c07ab5d  tekst=328 zn.
UPDATE predmet_dokumenti SET content_sha256 = '7e7c56f7f68d5f7e7a8284c1b33abe45'
 WHERE id = '3006377a-285d-4df3-81d2-519c1ae45012' AND content_sha256 IS NULL;

-- 26/43  predmet=6c07ab5d  tekst=265 zn.
UPDATE predmet_dokumenti SET content_sha256 = '8700a5205ff96b8feb6cfb9b6db66e0f'
 WHERE id = '4f1b1afc-cae0-4897-8bac-5e46ddf46dca' AND content_sha256 IS NULL;

-- 27/43  predmet=6c07ab5d  tekst=227 zn.
UPDATE predmet_dokumenti SET content_sha256 = '6adef833812a6b28af66392a5e84b0ce'
 WHERE id = 'b48e303a-fe7a-4638-9ffb-178782d9156e' AND content_sha256 IS NULL;

-- 28/43  predmet=6c07ab5d  tekst=206 zn.
UPDATE predmet_dokumenti SET content_sha256 = '6b992662ea7c400054d9c0a3de9d7ca7'
 WHERE id = '45eab367-fe9b-496f-bd5f-cf624d8c3f4e' AND content_sha256 IS NULL;

-- 29/43  predmet=720c36b2  tekst=256 zn.
UPDATE predmet_dokumenti SET content_sha256 = '872fd0e83660e2a56d49868abf1522bc'
 WHERE id = 'b7d3e1a5-c00d-4096-a0a2-9468f01a479d' AND content_sha256 IS NULL;

-- 30/43  predmet=7faf7d8e  tekst=323 zn.
UPDATE predmet_dokumenti SET content_sha256 = '3a43c209ac80feb48cdd05ba42a6e03f'
 WHERE id = 'e9fba600-ce27-457c-b96c-2de67e69470d' AND content_sha256 IS NULL;

-- 31/43  predmet=7faf7d8e  tekst=370 zn.
UPDATE predmet_dokumenti SET content_sha256 = '1a3d3140ef6bf10119240ec609f1ea60'
 WHERE id = '3333a2d9-984e-40ad-8b19-2f3194ec67e5' AND content_sha256 IS NULL;

-- 32/43  predmet=7faf7d8e  tekst=263 zn.
UPDATE predmet_dokumenti SET content_sha256 = 'eb8dd4dbe114882e0f41a226689977f3'
 WHERE id = '4c8daf1a-18dc-47d9-a2fd-b5753771472e' AND content_sha256 IS NULL;

-- 33/43  predmet=7faf7d8e  tekst=107 zn.
UPDATE predmet_dokumenti SET content_sha256 = '875d3881a8c84c996127d31ca42a0591'
 WHERE id = '96901dfb-6a88-44ed-87ab-e2bef259d7ae' AND content_sha256 IS NULL;

-- 34/43  predmet=87b76dc2  tekst=548 zn.
UPDATE predmet_dokumenti SET content_sha256 = 'dd541bad555c71c94969569d323c234b'
 WHERE id = '4a4ce1e5-0faa-402e-8064-f92be462e7ab' AND content_sha256 IS NULL;

-- 35/43  predmet=ab37c832  tekst=548 zn.
UPDATE predmet_dokumenti SET content_sha256 = 'dd541bad555c71c94969569d323c234b'
 WHERE id = 'a1903480-77c7-475e-9c57-9809abef2e34' AND content_sha256 IS NULL;

-- 36/43  predmet=b3f7eae5  tekst=548 zn.
UPDATE predmet_dokumenti SET content_sha256 = 'dd541bad555c71c94969569d323c234b'
 WHERE id = 'a1c4c90c-a441-4b68-ba30-4f8bff620d52' AND content_sha256 IS NULL;

-- 37/43  predmet=d2fb1e1f  tekst=256 zn.
UPDATE predmet_dokumenti SET content_sha256 = '872fd0e83660e2a56d49868abf1522bc'
 WHERE id = 'd1883f57-94e2-4973-a109-ff39345218ae' AND content_sha256 IS NULL;

-- 38/43  predmet=e0a54af1  tekst=533 zn.
UPDATE predmet_dokumenti SET content_sha256 = 'f6339d82e41dc682a7c942abe353c37d'
 WHERE id = 'c8574c9f-ed87-4b15-9087-13495d42f28d' AND content_sha256 IS NULL;

-- 39/43  predmet=e0a54af1  tekst=527 zn.
UPDATE predmet_dokumenti SET content_sha256 = '6cc189eba5fc07ffad3b329888d3441d'
 WHERE id = '456334e3-5cd2-4cca-b39a-cd01289d0014' AND content_sha256 IS NULL;

-- 40/43  predmet=e0a54af1  tekst=424 zn.
UPDATE predmet_dokumenti SET content_sha256 = 'aa51923b2408eaf07d828dea7951bf86'
 WHERE id = '9ec336aa-fcf9-466e-9922-dc0a66cad6a3' AND content_sha256 IS NULL;

-- 41/43  predmet=f4bbb99b  tekst=346 zn.
UPDATE predmet_dokumenti SET content_sha256 = 'e55b7d0adec4cd80df8fd5a60a08746e'
 WHERE id = '96c62120-a704-4da2-ace7-8491043fb7ea' AND content_sha256 IS NULL;

-- 42/43  predmet=f4bbb99b  tekst=77 zn.
UPDATE predmet_dokumenti SET content_sha256 = '599fec9a0d9e0968c1b2e708b4e431ed'
 WHERE id = '07077228-8f9e-4573-bff3-c89da4bf43c0' AND content_sha256 IS NULL;

-- 43/43  predmet=f4bbb99b  tekst=282 zn.
UPDATE predmet_dokumenti SET content_sha256 = '545342a763a4b0b1598908d6ae8a2d67'
 WHERE id = '814e386a-d322-4dde-aa44-7d23f2575b49' AND content_sha256 IS NULL;


-- Verifikacija: nijedan red ne sme ostati bez identiteta, i nijedna vrednost
-- ne sme biti van kanonskog oblika (32 heks znaka).
DO $$
DECLARE n_null int; n_bad int;
BEGIN
  SELECT count(*) INTO n_null FROM predmet_dokumenti WHERE content_sha256 IS NULL;
  SELECT count(*) INTO n_bad  FROM predmet_dokumenti
   WHERE content_sha256 IS NOT NULL AND content_sha256 !~ '^[0-9a-f]{32}$';
  IF n_null <> 0 OR n_bad <> 0 THEN
    RAISE EXCEPTION 'PINE-02 verifikacija pala: NULL=%, nekanonskih=%', n_null, n_bad;
  END IF;
END $$;

COMMIT;

-- =====================================================================
-- ROLLBACK (ako se odluka povuče): vraća tačno ono što je ovaj skript upisao,
-- i ništa drugo — poklapanje po vrednosti sprečava brisanje tuđeg identiteta.
-- =====================================================================
-- BEGIN;

-- UPDATE predmet_dokumenti SET content_sha256 = NULL WHERE id = 'abf8101c-8c16-4ad4-b492-0fc79f7eca4b' AND content_sha256 = 'f6339d82e41dc682a7c942abe353c37d';

-- UPDATE predmet_dokumenti SET content_sha256 = NULL WHERE id = '3ed20dae-9aa1-4f20-a8e0-c716a52d7e4e' AND content_sha256 = '6cc189eba5fc07ffad3b329888d3441d';

-- UPDATE predmet_dokumenti SET content_sha256 = NULL WHERE id = '39b7463a-52d8-4e47-b5cb-71b9768832b8' AND content_sha256 = 'aa51923b2408eaf07d828dea7951bf86';

-- UPDATE predmet_dokumenti SET content_sha256 = NULL WHERE id = '0d39c48a-9e0a-428f-b6b8-fbfff3d43ecd' AND content_sha256 = 'f6339d82e41dc682a7c942abe353c37d';

-- UPDATE predmet_dokumenti SET content_sha256 = NULL WHERE id = '3d177a32-bff6-496d-840d-c9dc099228f9' AND content_sha256 = '6cc189eba5fc07ffad3b329888d3441d';

-- UPDATE predmet_dokumenti SET content_sha256 = NULL WHERE id = '67536829-53db-49b3-a688-a6f5a67eb5f0' AND content_sha256 = 'aa51923b2408eaf07d828dea7951bf86';

-- UPDATE predmet_dokumenti SET content_sha256 = NULL WHERE id = 'a93ef3df-6e2f-49b0-9bc1-2bf00b549674' AND content_sha256 = '7e7c56f7f68d5f7e7a8284c1b33abe45';

-- UPDATE predmet_dokumenti SET content_sha256 = NULL WHERE id = 'f9f6c5f2-3fe7-42ac-bcbf-601a39c5cf20' AND content_sha256 = '8700a5205ff96b8feb6cfb9b6db66e0f';

-- UPDATE predmet_dokumenti SET content_sha256 = NULL WHERE id = '11d3e4a9-476d-44f8-9927-02218fe0a029' AND content_sha256 = '6adef833812a6b28af66392a5e84b0ce';

-- UPDATE predmet_dokumenti SET content_sha256 = NULL WHERE id = '0577f41e-cfc3-44d3-b4f1-58d1825c17b5' AND content_sha256 = '6b992662ea7c400054d9c0a3de9d7ca7';

-- UPDATE predmet_dokumenti SET content_sha256 = NULL WHERE id = 'd363a085-2835-4f80-a7cb-a794c1b20bcc' AND content_sha256 = 'f1dfb14e71d1fe8f9376ee58a6a89e62';

-- UPDATE predmet_dokumenti SET content_sha256 = NULL WHERE id = '1880fc72-855f-40f6-bf92-f9974a0245e1' AND content_sha256 = '02f28aee6617badfb449cf4591009c93';

-- UPDATE predmet_dokumenti SET content_sha256 = NULL WHERE id = '3828c17b-3452-4170-8818-3022aa4deac6' AND content_sha256 = 'b6e182440e98f5d03d787fb0d0c7e47e';

-- UPDATE predmet_dokumenti SET content_sha256 = NULL WHERE id = '52e76915-fcd6-43e2-b954-7bd3e2ef469f' AND content_sha256 = 'e55b7d0adec4cd80df8fd5a60a08746e';

-- UPDATE predmet_dokumenti SET content_sha256 = NULL WHERE id = 'b5ed492e-25eb-488f-9a82-6ad35acf84db' AND content_sha256 = '599fec9a0d9e0968c1b2e708b4e431ed';

-- UPDATE predmet_dokumenti SET content_sha256 = NULL WHERE id = '88c36999-be39-4122-b6ab-3dee3349b382' AND content_sha256 = '545342a763a4b0b1598908d6ae8a2d67';

-- UPDATE predmet_dokumenti SET content_sha256 = NULL WHERE id = '72c461f5-85cb-480d-abce-b9b22ec11589' AND content_sha256 = 'f1dfb14e71d1fe8f9376ee58a6a89e62';

-- UPDATE predmet_dokumenti SET content_sha256 = NULL WHERE id = '565aaaad-ca1e-43d6-b745-97db131bf7ab' AND content_sha256 = '02f28aee6617badfb449cf4591009c93';

-- UPDATE predmet_dokumenti SET content_sha256 = NULL WHERE id = '42cd5e12-edeb-4a66-86fe-97c963a310ed' AND content_sha256 = 'b6e182440e98f5d03d787fb0d0c7e47e';

-- UPDATE predmet_dokumenti SET content_sha256 = NULL WHERE id = '0050a23f-791a-4f52-a193-ec1133ff48ea' AND content_sha256 = 'dd541bad555c71c94969569d323c234b';

-- UPDATE predmet_dokumenti SET content_sha256 = NULL WHERE id = 'f77f8881-ee17-4c78-b142-45cd81c0f518' AND content_sha256 = '3a43c209ac80feb48cdd05ba42a6e03f';

-- UPDATE predmet_dokumenti SET content_sha256 = NULL WHERE id = 'c6481d9b-fac2-49bc-958c-d1e125a9c9b3' AND content_sha256 = '1a3d3140ef6bf10119240ec609f1ea60';

-- UPDATE predmet_dokumenti SET content_sha256 = NULL WHERE id = '8f45a0c5-7590-44c5-a1ae-7d85ae979d84' AND content_sha256 = 'eb8dd4dbe114882e0f41a226689977f3';

-- UPDATE predmet_dokumenti SET content_sha256 = NULL WHERE id = 'db85b0d1-d82d-4d41-8b02-c168615a23c1' AND content_sha256 = '875d3881a8c84c996127d31ca42a0591';

-- UPDATE predmet_dokumenti SET content_sha256 = NULL WHERE id = '3006377a-285d-4df3-81d2-519c1ae45012' AND content_sha256 = '7e7c56f7f68d5f7e7a8284c1b33abe45';

-- UPDATE predmet_dokumenti SET content_sha256 = NULL WHERE id = '4f1b1afc-cae0-4897-8bac-5e46ddf46dca' AND content_sha256 = '8700a5205ff96b8feb6cfb9b6db66e0f';

-- UPDATE predmet_dokumenti SET content_sha256 = NULL WHERE id = 'b48e303a-fe7a-4638-9ffb-178782d9156e' AND content_sha256 = '6adef833812a6b28af66392a5e84b0ce';

-- UPDATE predmet_dokumenti SET content_sha256 = NULL WHERE id = '45eab367-fe9b-496f-bd5f-cf624d8c3f4e' AND content_sha256 = '6b992662ea7c400054d9c0a3de9d7ca7';

-- UPDATE predmet_dokumenti SET content_sha256 = NULL WHERE id = 'b7d3e1a5-c00d-4096-a0a2-9468f01a479d' AND content_sha256 = '872fd0e83660e2a56d49868abf1522bc';

-- UPDATE predmet_dokumenti SET content_sha256 = NULL WHERE id = 'e9fba600-ce27-457c-b96c-2de67e69470d' AND content_sha256 = '3a43c209ac80feb48cdd05ba42a6e03f';

-- UPDATE predmet_dokumenti SET content_sha256 = NULL WHERE id = '3333a2d9-984e-40ad-8b19-2f3194ec67e5' AND content_sha256 = '1a3d3140ef6bf10119240ec609f1ea60';

-- UPDATE predmet_dokumenti SET content_sha256 = NULL WHERE id = '4c8daf1a-18dc-47d9-a2fd-b5753771472e' AND content_sha256 = 'eb8dd4dbe114882e0f41a226689977f3';

-- UPDATE predmet_dokumenti SET content_sha256 = NULL WHERE id = '96901dfb-6a88-44ed-87ab-e2bef259d7ae' AND content_sha256 = '875d3881a8c84c996127d31ca42a0591';

-- UPDATE predmet_dokumenti SET content_sha256 = NULL WHERE id = '4a4ce1e5-0faa-402e-8064-f92be462e7ab' AND content_sha256 = 'dd541bad555c71c94969569d323c234b';

-- UPDATE predmet_dokumenti SET content_sha256 = NULL WHERE id = 'a1903480-77c7-475e-9c57-9809abef2e34' AND content_sha256 = 'dd541bad555c71c94969569d323c234b';

-- UPDATE predmet_dokumenti SET content_sha256 = NULL WHERE id = 'a1c4c90c-a441-4b68-ba30-4f8bff620d52' AND content_sha256 = 'dd541bad555c71c94969569d323c234b';

-- UPDATE predmet_dokumenti SET content_sha256 = NULL WHERE id = 'd1883f57-94e2-4973-a109-ff39345218ae' AND content_sha256 = '872fd0e83660e2a56d49868abf1522bc';

-- UPDATE predmet_dokumenti SET content_sha256 = NULL WHERE id = 'c8574c9f-ed87-4b15-9087-13495d42f28d' AND content_sha256 = 'f6339d82e41dc682a7c942abe353c37d';

-- UPDATE predmet_dokumenti SET content_sha256 = NULL WHERE id = '456334e3-5cd2-4cca-b39a-cd01289d0014' AND content_sha256 = '6cc189eba5fc07ffad3b329888d3441d';

-- UPDATE predmet_dokumenti SET content_sha256 = NULL WHERE id = '9ec336aa-fcf9-466e-9922-dc0a66cad6a3' AND content_sha256 = 'aa51923b2408eaf07d828dea7951bf86';

-- UPDATE predmet_dokumenti SET content_sha256 = NULL WHERE id = '96c62120-a704-4da2-ace7-8491043fb7ea' AND content_sha256 = 'e55b7d0adec4cd80df8fd5a60a08746e';

-- UPDATE predmet_dokumenti SET content_sha256 = NULL WHERE id = '07077228-8f9e-4573-bff3-c89da4bf43c0' AND content_sha256 = '599fec9a0d9e0968c1b2e708b4e431ed';

-- UPDATE predmet_dokumenti SET content_sha256 = NULL WHERE id = '814e386a-d322-4dde-aa44-7d23f2575b49' AND content_sha256 = '545342a763a4b0b1598908d6ae8a2d67';

-- COMMIT;