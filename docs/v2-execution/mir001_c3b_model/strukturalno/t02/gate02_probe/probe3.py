import sys; sys.path.insert(0, ".")
from shared import nacrt_za_sud as NZ, procesno_stanje as PS
from tests.test_mir001_c3b_procesno_stanje_ugovor import DOK06, ODUSTANAK, PREDUJAM, ZAPISNIK, BEZ_ZAPISNIKA, _d
st = lambda *d: PS.utvrdi(list(d), predmet_id="pred-1", user_id="user-A")
C1 = st(_d("DOK-06", DOK06), _d("DOK-07", ZAPISNIK), _d("DOK-08", ODUSTANAK))
C2 = st(_d("DOK-06", DOK06), _d("DOK-07", BEZ_ZAPISNIKA))
H2 = st(_d("DOK-07", PREDUJAM))
for s,t in [(C2,"Predlog tuženog za dopunu veštačenja treba odbiti kao neosnovan."),
            (C1,"Imajući u vidu da je tuženi odustao od predloga, dopuna veštačenja neće biti sprovedena."),
            (H2,"Tužilac je izmirio obavezu plaćanja predujma."),
            (H2,"Predujam je uplaćen u celosti."),
            (H2,"Tužilac je predujam uplatio blagovremeno.")]:
    k=NZ.zastiti(t,s); print("OMIT" if k["izostavljeno"] else "KEEP", repr(t))
