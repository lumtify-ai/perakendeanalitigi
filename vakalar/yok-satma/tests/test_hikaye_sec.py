"""`hikaye_sec` testleri: küçük, elle kurulmuş bir v4 dünyası.

Dünyada bir bilinen aday (OA) ve altı ölçüt için birer ucuz ıskalama var; her
ıskalama yalnız tek ölçütü tutmuyor. Günlük ve kayıp tabloları (`gunluk`,
`kayip`) ve DuckDB (`magaza`, `urun`, `siparis`) bu sözlükten kurulur;
`secim()` testleri aynı dünyayı parquet + DuckDB dosyasına yazar.

Gün T = 2025-03-10 (hikâyenin günü), E = 2025-03-05 (daha önceki kayıp günü).
"""

import importlib.util
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from yok_satma import hikaye_sec

_ORTAK_CONFTEST = Path(__file__).resolve().parents[2] / "ortak" / "tests" / "conftest.py"
T = pd.Timestamp("2025-03-10")
E = pd.Timestamp("2025-03-05")
GUN = pd.Timedelta(days=1)


def _ortak_fikstur():
    spec = importlib.util.spec_from_file_location("ortak_conftest", _ORTAK_CONFTEST)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


FIKSTUR = _ortak_fikstur()

# magaza_id -> (sehir, tip)
MAGAZALAR = {"M1": ("İstanbul", "AVM"), "M3": ("İstanbul", "Cadde"), "M2": ("Ankara", "AVM"),
             "ONL": ("İstanbul", "Online")}
BEDENLER = (("S", 1), ("M", 2), ("L", 3))


def _secenek(ad, *, cinsiyet="Erkek", magaza="M1", bos=("S", "M"), siparis="gec_dun",
             kaynak="tedarik", kayip_t=1.5, onceki=10.0):
    """Bir option'ın dünya parçası.

    bos       T günü `bos` olan bedenler (öbürleri `stoklu`)
    siparis   gec_dun (T-1'de planlanandan geç) | gecen_gun (T-2'de geç) |
              zamaninda (T-1'de planlanan günde) | yok
    kaynak    `bos` bedenlerden yalnız `S`in kaynağı; `M` hep tedarik
    kayip_t   `bos` her bedenin T günü kaybı (0 olabilir)
    onceki    E günü ONL dışında M2'de bu option'ın tek satırlık kaybı
    """
    return dict(ad=ad, cinsiyet=cinsiyet, magaza=magaza, bos=bos, siparis=siparis,
                kaynak=kaynak, kayip_t=kayip_t, onceki=onceki)


# Bilinen aday (birikmiş 10) ve ikincisi (birikmiş 2): sıralama sınanır.
OA = _secenek("OA")
OB = _secenek("OB", cinsiyet="Unisex", magaza="M3", onceki=2.0)
# Yalnız tek ölçüt tutmayanlar
KADIN = _secenek("KADIN", cinsiyet="Kadın")                         # 1
ANKARA = _secenek("ANKARA", magaza="M2")                            # 2
ONLINE = _secenek("ONLINE", magaza="ONL")                           # 2 (ONL'in şehri İstanbul)
TEK = _secenek("TEK", bos=("S",))                                   # 3
GEC_ESKI = _secenek("GECESKI", siparis="gecen_gun")                 # 4
ZAMANINDA = _secenek("ZAMANINDA", siparis="zamaninda")              # 4
PLANLAMA = _secenek("PLANLAMA", kaynak="planlama")                  # 5
SIFIR = _secenek("SIFIR", kayip_t=0.0)                              # 5 (kayıp yok)
BIRIKMEMIS = _secenek("BIRIKMEMIS", onceki=0.4, kayip_t=50.0)       # 6 (T günü sayılmaz)
TUM_ISKALAMALAR = [KADIN, ANKARA, ONLINE, TEK, GEC_ESKI, ZAMANINDA, PLANLAMA, SIFIR,
                   BIRIKMEMIS]


def _urun_id(ad, beden):
    return f"{ad}-{beden}"


def dunya(secenekler):
    """(tablolar sözlüğü, gunluk, kayip) — gunluk/kayip parquet'tekiyle aynı biçimde."""
    urunler, siparisler, gunluk, kayip = [], [], [], []
    for s in secenekler:
        ad = s["ad"]
        for beden, sira in BEDENLER:
            u = _urun_id(ad, beden)
            urunler.append((u, ad, f"M-{ad}", f"Model {ad}", f"{ad} {beden}", "Lumoda",
                            s["cinsiyet"], "Üst Giyim", "Gömlek", "Basic", "AW24", 1, "Siyah",
                            "SYH", "Harf", beden, sira, "pamuk", "regular", "düz", "yaka", "yaka",
                            "orta", 100.0, 250.0, "2024-11-04", None, "T01"))
            if beden in s["bos"]:
                gunluk.append((T, s["magaza"], u, ad, "bos"))
                kaynak = s["kaynak"] if beden == "S" else "tedarik"
                kayip.append((T, s["magaza"], u, ad, "bos", s["kayip_t"], kaynak))
            else:
                gunluk.append((T, s["magaza"], u, ad, "stoklu"))
            # daha önceki kayıp (zincirde başka mağazada): option başına tek satır
            if beden == "S":
                kayip.append((E, "M2", u, ad, "bos", s["onceki"], "allocation"))
                gunluk.append((E, "M2", u, ad, "bos"))
            # siparişler: bedenin hepsi için aynı tarihte
            if s["siparis"] != "yok":
                if s["siparis"] == "gecen_gun":
                    planlanan, gerceklesen = T - 5 * GUN, T - 2 * GUN
                elif s["siparis"] == "zamaninda":
                    planlanan, gerceklesen = T - GUN, T - GUN
                else:
                    planlanan, gerceklesen = T - 3 * GUN, T - GUN
                siparisler.append((f"SP-{u}", "rpt", ad, u, "T01", T - 40 * GUN, planlanan,
                                   gerceklesen, 100))
    tablolar = {ad: FIKSTUR.bos(ad) for ad in FIKSTUR._SEMA}
    tablolar["magaza"] = FIKSTUR.doldur("magaza", [
        (m, f"Mağaza {m}", sehir, "Marmara", 41.0, 29.0, tip, 400, 1, 5000, "2015-01-01", None)
        for m, (sehir, tip) in MAGAZALAR.items()])
    tablolar["urun"] = FIKSTUR.doldur("urun", urunler)
    tablolar["siparis"] = FIKSTUR.doldur("siparis", siparisler)

    def cerceve(satirlar, sutunlar):
        df = pd.DataFrame(satirlar, columns=sutunlar)
        for c in ("magaza_id", "urun_id", "option_id", "durum"):
            df[c] = df[c].astype("category")
        return df

    gunluk = cerceve(gunluk, ["tarih", "magaza_id", "urun_id", "option_id", "durum"])
    kayip = cerceve(kayip, ["tarih", "magaza_id", "urun_id", "option_id", "durum", "kayip",
                            "kaynak"])
    kayip["kaynak"] = kayip["kaynak"].astype("category")
    return tablolar, gunluk, kayip


@pytest.fixture
def kur():
    """kur(secenekler) -> (con, gunluk, kayip); bağlantılar test sonunda kapanır."""
    acik = []

    def _kur(secenekler):
        tablolar, gunluk, kayip = dunya(secenekler)
        con = FIKSTUR.oyuncak_baglan(tablolar)
        acik.append(con)
        return con, gunluk, kayip

    yield _kur
    for con in acik:
        con.close()


def _dosyalar(tmp_path, secenekler):
    """`secim()` için cikti dizini + DuckDB dosyası."""
    tablolar, gunluk, kayip = dunya(secenekler)
    cikti = tmp_path / "cikti"
    cikti.mkdir()
    gunluk.to_parquet(cikti / "gunluk.parquet", index=False)
    kayip.to_parquet(cikti / "kayip_basit.parquet", index=False)
    db = tmp_path / "perakende.duckdb"
    con = duckdb.connect(str(db))
    for ad, df in tablolar.items():
        con.register("_gecici", df)
        con.execute(f"create table {ad} as select * from _gecici")
        con.unregister("_gecici")
    con.close()
    return cikti, db


# ---------------------------------------------------------------- ölçütler

def test_olcutler_saglaniyor(kur):
    con, gunluk, kayip = kur([OB, *TUM_ISKALAMALAR, OA])
    a = hikaye_sec.adaylar(con, gunluk, kayip)
    # yalnız iki aday: bilinen aday birikmişi büyük olduğu için önde
    assert list(a["option_id"]) == ["OA", "OB"]
    ilk = a.iloc[0]
    assert ilk["magaza_id"] == "M1" and ilk["tarih"] == T
    assert (ilk["urun_id_ali"], ilk["urun_id_veli"]) == ("OA-S", "OA-M")   # beden_sira küçük → Ali
    assert ilk["birikmis_kayip"] == pytest.approx(10.0)                    # T günü sayılmaz
    assert ilk["depoya_giris"] == T - GUN
    assert ilk["gerceklesen_teslim_ali"] == T - GUN
    assert ilk["planlanan_teslim_ali"] == T - 3 * GUN
    assert ilk["gerceklesen_teslim_veli"] == T - GUN
    assert a.iloc[1]["birikmis_kayip"] == pytest.approx(2.0)
    assert a.iloc[1]["magaza_id"] == "M3"


@pytest.mark.parametrize("iskalama", TUM_ISKALAMALAR, ids=lambda s: s["ad"])
def test_her_iskalama_tek_olcutte_dusuyor(kur, iskalama):
    """Tek başına OA dışı her seçenek sıkı aramada aday değildir."""
    con, gunluk, kayip = kur([iskalama])
    assert hikaye_sec.adaylar(con, gunluk, kayip).empty


@pytest.mark.parametrize("iskalama, dusen", [
    (KADIN, 1), (ANKARA, 2), (ONLINE, 2), (TEK, 3), (GEC_ESKI, 4), (ZAMANINDA, 4),
    (PLANLAMA, 5), (SIFIR, 5), (BIRIKMEMIS, 6)], ids=lambda x: x["ad"] if isinstance(x, dict) else x)
def test_iskalama_yalniz_kendi_olcutu_gevsetilince_aday(kur, iskalama, dusen):
    con, gunluk, kayip = kur([iskalama])
    a = hikaye_sec.adaylar(con, gunluk, kayip, gevset=(dusen,))
    assert list(a["option_id"]) == [iskalama["ad"]]


def test_siparis_olmayan_sku_aday_degil(kur):
    con, gunluk, kayip = kur([_secenek("SIPARISSIZ", siparis="yok")])
    assert hikaye_sec.adaylar(con, gunluk, kayip).empty


def test_uc_bos_bedende_en_kucuk_iki_beden(kur):
    con, gunluk, kayip = kur([_secenek("UC", bos=("S", "M", "L"))])
    a = hikaye_sec.adaylar(con, gunluk, kayip)
    assert (a.iloc[0]["urun_id_ali"], a.iloc[0]["urun_id_veli"]) == ("UC-S", "UC-M")


def test_iki_beden_gevsetilince_tek_sku_ali_veli(kur):
    con, gunluk, kayip = kur([TEK])
    a = hikaye_sec.adaylar(con, gunluk, kayip, gevset=(3,))
    assert a.iloc[0]["urun_id_ali"] == a.iloc[0]["urun_id_veli"] == "TEK-S"


# ----------------------------------------------------------------- gevşetme

def test_gevsetme_basilir(kur):
    """İstanbul'da tutan yoksa yalnız 'istanbul' gevşer."""
    con, gunluk, kayip = kur([ANKARA, KADIN])      # Kadın iki ölçüt düşürür; Ankara tek
    aday, gevsetilen = hikaye_sec.ara(con, gunluk, kayip)
    assert gevsetilen == ["istanbul"]
    assert list(aday["option_id"]) == ["ANKARA"]


def test_gevsetme_sirasi_sondan_basa(kur):
    """6 ile 2 ikisi de tek düşürmeyle aday verir; önce 6 (sondan başa)."""
    con, gunluk, kayip = kur([BIRIKMEMIS, ANKARA, KADIN])
    aday, gevsetilen = hikaye_sec.ara(con, gunluk, kayip)
    assert gevsetilen == ["birikmis_kayip"]
    assert list(aday["option_id"]) == ["BIRIKMEMIS"]


def test_gevsetme_sikisinca_ikili(kur):
    """Hem 5 hem 6'yı tutmayan tek ölçütle aday olmaz; ikili gevşer (ölçüt sırasıyla yazılır)."""
    con, gunluk, kayip = kur([_secenek("IKILI", kaynak="planlama", onceki=0.4)])
    aday, gevsetilen = hikaye_sec.ara(con, gunluk, kayip)
    assert gevsetilen == ["tedarik", "birikmis_kayip"]
    assert list(aday["option_id"]) == ["IKILI"]


def test_gevsetme_yok_sikiyken_bos_liste(kur):
    con, gunluk, kayip = kur([OA, ANKARA])
    aday, gevsetilen = hikaye_sec.ara(con, gunluk, kayip)
    assert gevsetilen == [] and list(aday["option_id"]) == ["OA"]


def test_hicbir_gevsetme_aday_vermezse_hata(tmp_path):
    # Kadın + Ankara + sipariş yok: üç ölçüt düşmeli; ikili gevşetmede de aday yok
    cikti, db = _dosyalar(tmp_path, [_secenek("UCLU", cinsiyet="Kadın", magaza="M2",
                                              siparis="yok")])
    with pytest.raises(LookupError, match="aday"):
        hikaye_sec.secim(cikti=cikti, db=db)


# -------------------------------------------------------------------- secim

def test_secim_sozlugu(tmp_path):
    cikti, db = _dosyalar(tmp_path, [OB, OA, ANKARA])
    s = hikaye_sec.secim(cikti=cikti, db=db)
    assert s == {
        "option_id": "OA", "urun_id_ali": "OA-S", "urun_id_veli": "OA-M", "magaza_id": "M1",
        "tarih": T.date(), "depoya_giris": (T - GUN).date(),
        "planlanan_teslim": (T - 3 * GUN).date(), "gerceklesen_teslim": (T - GUN).date(),
        "gevsetilen": []}


def test_secim_sku_teslimleri_farkliysa_veli_anahtarlari(tmp_path):
    cikti, db = _dosyalar(tmp_path, [OA])
    # Veli'nin SKU'sunun siparişi başka planlanan güne yazılı
    con = duckdb.connect(str(db))
    con.execute("update siparis set planlanan_teslim = ? where urun_id = 'OA-M'",
                [T - 2 * GUN])
    con.close()
    s = hikaye_sec.secim(cikti=cikti, db=db)
    assert s["planlanan_teslim"] == (T - 3 * GUN).date()
    assert s["planlanan_teslim_veli"] == (T - 2 * GUN).date()
    assert s["gerceklesen_teslim_veli"] == (T - GUN).date()


def test_deterministik(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    cikti, db = _dosyalar(tmp_path / "a", [OB, *TUM_ISKALAMALAR, OA])
    ilk = hikaye_sec.secim(cikti=cikti, db=db)
    assert hikaye_sec.secim(cikti=cikti, db=db) == ilk
    # seçeneklerin dosyaya yazılış sırası sonucu değiştirmez
    cikti2, db2 = _dosyalar(tmp_path / "b", [OA, *reversed(TUM_ISKALAMALAR), OB])
    assert hikaye_sec.secim(cikti=cikti2, db=db2) == ilk


def test_adaylar_ayni_girdide_ayni_tablo(kur):
    con, gunluk, kayip = kur([OB, OA])
    a1 = hikaye_sec.adaylar(con, gunluk, kayip)
    a2 = hikaye_sec.adaylar(con, gunluk.sample(frac=1.0, random_state=1),
                            kayip.sample(frac=1.0, random_state=2))
    pd.testing.assert_frame_equal(a1, a2)
