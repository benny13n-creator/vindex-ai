import sys; sys.path.insert(0, ".")
from shared import nacrt_za_sud as NZ, procesno_stanje as PS
from tests.test_mir001_c3b_procesno_stanje_ugovor import DOK06, ZAPISNIK, PREDUJAM, _d, _ZAGLAVLJE
st = lambda *d: PS.utvrdi(list(d), predmet_id="pred-1", user_id="user-A")
pod = lambda n, r: _ZAGLAVLJE + n + " (SINTETICKI PREDMET)\n" + r + "\nDatum podneska: 20.08.2026. godine."
def H(r): return st(_d("DOK-07", PREDUJAM), _d("DOK-08", pod("PODNESAK TUZIOCA", r)))
def A(r): return st(_d("DOK-06", DOK06), _d("DOK-07", ZAPISNIK), _d("DOK-08", pod("PODNESAK TUZENOG", r)))
UP = "Tuzilac navodi da je uplatio predujam za dopunu vestacenja."
NEG = "Tuzilac navodi da nije uplatio predujam za dopunu vestacenja."
FAR = "Tuzilac navodi da nije u celosti i na vreme uplatio predujam za dopunu vestacenja."
DBL = "Tuzilac navodi da nije tacno da nije uplatio predujam za dopunu vestacenja."
NINI = "Tuzilac navodi da predujam za dopunu vestacenja ni uplatio ni obezbedio nije."
COND = "Tuzilac navodi da bi uplatio predujam za dopunu vestacenja da je primio zapisnik."
Q = "Tuzilac navodi da ce proveriti da li je uplatio predujam za dopunu vestacenja."
ODB = "Tuzilac navodi da je odbijeno da uplati predujam za dopunu vestacenja."
TV = "Tuzilac navodi da je pokusao da uplati predujam za dopunu vestacenja, ali uplata nije prosla."
R = "Tužilac u podnesku (DOK-08) navodi da je uplatio predujam za dopunu veštačenja."
RN = "Tužilac u podnesku (DOK-08) navodi da nije uplatio predujam za dopunu veštačenja."
for name, s, t in [
 ("UP->pos", H(UP), R), ("UP->neg (odrecna nad potvrdnim)", H(UP), RN), ("NEG->neg", H(NEG), RN),
 ("FAR(4 reci)->pos", H(FAR), R), ("DBL->pos", H(DBL), R), ("NINI->pos", H(NINI), R), ("COND->pos", H(COND), R),
 ("Q->pos", H(Q), R), ("TV->pos", H(TV), R),
 ("UP->dbl", H(UP), "Tužilac u podnesku (DOK-08) navodi da nije tačno da nije uplatio predujam za dopunu veštačenja."),
 ("NEG->sent far neg", H(NEG), "Tužilac u podnesku (DOK-08) navodi da nikako nije ni u kom slučaju uplatio predujam."),
 ("NEG->sent pos w/ 'ne' elsewhere", H(NEG), "Tužilac u podnesku (DOK-08), ne ulazeći u ostalo, navodi da je uplatio predujam za dopunu veštačenja."),
 ("UP->'nesporno je da je uplatio'", H(UP), "Tužilac u podnesku (DOK-08) navodi da je uplatio predujam, što tuženi ne osporava, pa je nalog ispunjen."),
 ("A dostavio far neg", A("Tuzeni navodi da gradjevinski dnevnik do sada iz objektivnih razloga nije mogao dostaviti."), "Tuženi u podnesku (DOK-08) navodi da je građevinski dnevnik dostavio."),
 ("A 'nije sacuvan, ali je dostavio kopiju'", A("Tuzeni navodi da original dnevnika nije sacuvan, ali je dostavio kopiju."), "Tuženi u podnesku (DOK-08) navodi da je građevinski dnevnik dostavio."),
]:
    k = NZ.zastiti(t, s); print("OMIT" if k["izostavljeno"] else "KEEP", name, "|", [i["razlog"][:40] for i in k["izostavljeno"]])
print("=== lazno izostavljanje glagola predaje (A, nalog postoji)")
As = st(_d("DOK-06", DOK06), _d("DOK-07", ZAPISNIK))
for t in ["Tužilac je primio nalaz veštaka 20.06.2026. godine.", "Tužilac je primio zapisnik sa ročišta.",
          "Tuženi je predao radove investitoru u martu 2024. godine.", "Objekat je primljen bez primedbi.",
          "Pismo tuženog stiglo je tužiocu 10.03.2024.", "Tužilac je investitoru predao ključeve objekta.",
          "Primopredaja objekta izvršena je 15.03.2024.", "Radovi su završeni u martu 2024. godine.",
          "Tuženi je radove izveo i predao objekat.", "Reklamacija je tuženom dostavljena 01.04.2024."]:
    k = NZ.zastiti(t, As); print("OMIT" if k["izostavljeno"] else "KEEP", repr(t), [i["razlog"][:40] for i in k["izostavljeno"]])
