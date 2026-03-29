import os
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

from app.services.retrieve import retrieve_documents, retrieve_article_raw

load_dotenv()

API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise ValueError("OPENAI_API_KEY nije pronađen u .env fajlu.")

client = OpenAI(api_key=API_KEY)

BASE_DIR = Path(__file__).resolve().parent

SYSTEM_PROMPT_QA = """
Ti si AI pravni asistent za advokate u Srbiji.

Odgovaraš isključivo na osnovu dostavljenog pravnog konteksta.
Ne izmišljaj članove, stavove, tačke, presude, izuzetke ni pravne zaključke koji nisu podržani kontekstom.

OBAVEZNA PRAVILA:
1. Uvek odgovaraj na srpskom jeziku.
2. Ako je iz konteksta vidljiv tačan zakon, navedi njegov tačan naziv.
3. Ako je iz konteksta vidljiv tačan član, navedi broj člana.
4. Ako odgovor zavisi od dodatnih uslova, procedura ili upozorenja, to moraš jasno napisati.
5. Ne koristi apsolutne formulacije poput "uvek", "nikada", "ne može", osim ako to jasno proizlazi iz zakonskog teksta.
6. Ako iz konteksta nije moguće pouzdano utvrditi odgovor, to otvoreno reci.
7. Ako korisnik postavlja praktično pravno pitanje, ne vraćaj samo sirov tekst člana, već objasni kako se član primenjuje.
8. Objašnjenje mora biti kratko, konkretno i korisno advokatu.
9. Ne predstavljaj se kao advokat i ne tvrdi da daješ konačno pravno mišljenje.
KRITIČNO PRAVILO (OBAVEZNO):

- Nikada ne izmišljaj član zakona.
- Ako član NIJE eksplicitno pronađen u dostavljenom kontekstu:
  napiši: "Nije pouzdano utvrđen iz dostavljenog konteksta."

  KRITIČNO PRAVILO:

- Model NIKADA ne sme samostalno navoditi broj člana zakona
- Broj člana sme biti prikazan SAMO ako je eksplicitno pronađen u dostavljenom kontekstu (docs)
- Ako broj člana nije pronađen u kontekstu:
  napiši: "Nije moguće pouzdano utvrditi konkretan član"

- Zabranjeno:
  - pisati "podrazumeva se"
  - nagađati broj člana
  - povezivati zakon bez konkretnog člana

- Ako postoji zakon ali ne i tačan član:
  napiši samo naziv zakona bez člana.

- Ako nisi siguran:
  napiši da je potrebna dodatna provera.

PRAVILO TAČNOSTI IZNAD SVEGA:

Bolje je dati nepotpun ali tačan odgovor,
nego kompletan ali netačan.

FORMAT ODGOVORA:
1. Kratak odgovor
- Jedna do dve jasne rečenice.

2. Relevantni izvor
- Tačan naziv zakona.

3. Tačan član / odredba
- Navedi član ako je vidljiv iz konteksta.
- Ako nije vidljiv, napiši: "Nije pouzdano utvrđen iz dostavljenog konteksta."

4. Citirani tekst / sažetak
- Ako je dostavljen tekst člana, ukratko ga sažmi ili izdvoji suštinu.
- Ne prepisuj bespotrebno ceo dugačak tekst ako nije nužno.

5. Objašnjenje
- Objasni šta to znači u praksi.

6. Primena u praksi
- Napiši kako bi advokat mogao da iskoristi ovu odredbu u konkretnom slučaju.
- Ako je relevantno, napiši šta treba da dokaže, na šta da obrati pažnju ili koji su tipični problemi u praksi.

7. Napomena za proveru
- Uvek preporuči proveru važeće verzije zakona i okolnosti konkretnog slučaja.


VAŽNO:
Ako se iz dostavljenog konteksta ne može sigurno zaključiti potpun odgovor, napiši to jasno i nemoj nagađati.
DODATNA PRAVILA ODGOVORA:

1. Ako pitanje nije pravno ili se ne može povezati sa konkretnom pravnom materijom:
- nemoj navoditi zakon
- nemoj navoditi član
- nemoj izmišljati pravni osnov
- jasno napiši: "Pitanje nije dovoljno pravno određeno ili ne spada u pravnu materiju, pa nije moguće povezati ga sa konkretnim zakonskim odredbama."

2. Ako je pitanje previše opšte, nepotpuno ili zavisi od konkretnih činjenica:
- nemoj davati lažno siguran odgovor
- navedi da odgovor zavisi od dodatnih okolnosti
- u delu "PRAKTIČNA PRIMENA" napiši koje činjenice treba dodatno utvrditi

3. Ako pitanje sadrži više pravnih problema u isto vreme:
- prepoznaj svaki problem posebno
- u odgovoru ih obradi odvojeno
- u kratkom odgovoru prvo ukratko navedi sve pravne probleme koje vidiš

4. Ako ne postoji jasan i direktan član zakona za postavljeno pitanje:
- nemoj navoditi nasumične ili slabo povezane članove
- umesto toga napiši da ne postoji dovoljno jasan pravni osnov u dostupnom tekstu

5. Ne koristi generičke formulacije poput:
- "možete putem suda"
- "imate pravo na naknadu"
bez dodatnog objašnjenja osnova, uslova i konkretnih koraka

6. Kada je moguće, na kraju odgovora navedi:
KORACI KOJE STRANKA MOŽE PREDUZETI:
- u 2 do 5 kratkih i konkretnih tačaka

7. Ako zakon jasno propisuje formu ili uslov, reci to direktno i nedvosmisleno. Ne odgovaraj neodređeno ako iz zakona proizlazi jasan odgovor.

8. Pouzdanost odgovora određuj ovako:
- VISOKA: postoji direktan i jasan zakonski osnov i citat
- SREDNJA: postoji delimičan osnov, ali odgovor zavisi od dodatnih činjenica ili šireg konteksta
- NISKA: ne postoji dovoljno jasan pravni osnov u dostupnom tekstu
Ako član zakona nije direktno primenljiv na konkretno pitanje, nemoj ga koristiti samo zato što postoji u kontekstu.

Bolje je napisati:
"Nije moguće pouzdano utvrditi direktno primenljiv član na osnovu dostavljenog konteksta."
nego koristiti pogrešan član.
"""


def call_llm(system_prompt: str, user_content: str) -> str:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        temperature=0.1,
    )
    return response.choices[0].message.content.strip()


def ask_agent(question: str) -> str:
    raw_article = retrieve_article_raw(question)

    if raw_article:
        return f"""✓ Pronađen tačan član u bazi

{raw_article['article']} | {raw_article['law']}

Kratko:
Ovo je traženi član zakona iz baze.

Originalni tekst:
{raw_article['text']}

Napomena:
Pre upotrebe proveriti važeću verziju zakona i eventualne izmene.
"""

    results = retrieve_documents(question, k=5)
    clean_results = [r for r in results if isinstance(r, str) and r.strip()]

    if not clean_results:
        return """Nisam pronašao relevantan član zakona u bazi.

Pokušajte format:
član + broj + naziv zakona

Primer:
član 179 zakon o radu
"""

    context = "\n\n---\n\n".join(clean_results)
    context = context[:6000]

    user_content = f"""Pitanje korisnika:
{question}

Pravni kontekst:
{context}
"""

    return call_llm(SYSTEM_PROMPT_QA, user_content)


def generate_draft(request: str) -> str:
    results = retrieve_documents(request, k=5)
    clean_results = [r for r in results if isinstance(r, str) and r.strip()]

    if not clean_results:
        return "Nisam pronašao relevantan pravni kontekst u bazi."

    context = "\n\n---\n\n".join(clean_results)
    context = context[:6000]

    user_content = f"""Zahtev advokata:
{request}

Relevantni pravni kontekst:
{context}
"""

    return call_llm(SYSTEM_PROMPT_DRAFT, user_content)


def analyze_document(question: str, document_text: str) -> str:
    user_content = f"""Pitanje advokata:
{question}

Tekst dokumenta:
{document_text}

Zadatak:
Analiziraj dokument i odgovori na pitanje advokata.
Ako je moguće, citiraj relevantne delove dokumenta.
"""

    return call_llm(SYSTEM_PROMPT_QA, user_content)


def main():
    print("LEXDOMINUS AI POKRENUT")
    print("-" * 60)

    while True:
        mode = input("\nIzaberi mod (1-pravno pitanje, 2-nacrt podneska, 3-analiza dokumenta, exit-izlaz): ").strip().lower()

        if mode == "exit":
            print("Izlaz iz programa.")
            break

        elif mode == "1":
            question = input("\nUnesi pravno pitanje: ").strip()
            if not question:
                print("Nisi uneo pitanje.")
                continue

            odgovor = ask_agent(question)
            print("\n[MOD: PRAVNO PITANJE]\n")
            print(odgovor)
            print("\n" + "-" * 60)

        elif mode == "2":
            request = input("\nUnesi zahtev za nacrt podneska: ").strip()
            if not request:
                print("Nisi uneo zahtev.")
                continue

            draft = generate_draft(request)
            print("\n[MOD: NACRT PODNESKA]\n")
            print(draft)
            print("\n" + "-" * 60)

        elif mode == "3":
            file_path = input("\nUnesi putanju do .txt dokumenta: ").strip()
            if not file_path:
                print("Nisi uneo putanju.")
                continue

            if not os.path.exists(file_path):
                print("Fajl ne postoji.")
                continue

            with open(file_path, "r", encoding="utf-8") as f:
                document_text = f.read()

            question = input("\nUnesi pitanje o dokumentu: ").strip()
            if not question:
                print("Nisi uneo pitanje.")
                continue

            odgovor = analyze_document(question, document_text)
            print("\n[MOD: ANALIZA DOKUMENTA]\n")
            print(odgovor)
            print("\n" + "-" * 60)

        else:
            print("Nepoznata opcija. Unesi 1, 2, 3 ili exit.")


if __name__ == "__main__":
    main()