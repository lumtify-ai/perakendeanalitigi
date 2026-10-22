"""`beden_paket.politika`: dünya kopyasına paket satırları, paket seçimi, Lumoda'nın giden paketi.

Oyuncak dünya: v4'ün yayımlanan `paket` tablosu (`paketleri_uret`; her beden setine tek standart
paket, aksesuar 6'lı tek beden) ve birkaç mağaza / option. Testler `perakende_veri`'yi yalnız
kıyas için içe aktarır (politika aktarmaz).
"""

import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from perakende_veri.v4.politika import paket_tablosu
from perakende_veri.v4.urun import paketleri_uret

from beden_paket import politika, sabitler

DESENLER = np.array([[1, 1, 2, 2, 1], [1, 2, 2, 1, 1], [0, 1, 2, 2, 2]])


@pytest.fixture(scope="module")
def paketler():
    return paketleri_uret()


def _dunya(paketler, magazalar=("M1", "M2", "M3", "M4"), optionlar=None):
    optionlar = optionlar or [("O1", "Kadın Harf"), ("O2", "Erkek Numara"), ("O3", "Standart"),
                              ("O4", "Kadın Harf")]
    return SimpleNamespace(
        paketler=paketler,
        magazalar=pd.DataFrame({"magaza_id": list(magazalar)}),
        optionlar=pd.DataFrame({"option_id": [o for o, _ in optionlar],
                                "beden_seti": [b for _, b in optionlar]}))


def _g(w, gun=0):
    return SimpleNamespace(dunya=w, gun=gun)


# ---------------------------------------------------------------------------
# paket_ekle
# ---------------------------------------------------------------------------


def test_paket_ekle_standart_ilk(paketler):
    """Yeni satırlar standart paketlerin ardına gelir: ilk satırlar aynen, her setin ilk paketi
    (motorun `setdefault` kuralı) standart kalır; tek bedenli set (aksesuar) desen almaz."""
    df, harita = politika.paket_ekle(paketler, DESENLER)
    n = len(paketler)
    pd.testing.assert_frame_equal(df.iloc[:n].reset_index(drop=True), paketler)
    assert list(df.columns) == list(paketler.columns)
    assert df.dtypes.to_dict() == paketler.dtypes.to_dict()
    _, std_eski, _ = paket_tablosu(paketler)
    ids, std_yeni, icerik = paket_tablosu(df)
    assert std_yeni == std_eski                                  # standart indisler değişmedi
    bes = [bs for bs in std_eski if bs != "Standart"]
    assert len(df) == n + len(bes) * len(DESENLER) * sabitler.BEDEN_SAYISI
    assert not df.iloc[n:]["beden_seti"].eq("Standart").any()
    yeni = df.iloc[n:]["paket_id"].drop_duplicates()
    assert yeni.str.match(r"^PKD\d{2}-PKT\d{2}$").all()
    assert len(yeni) == len(bes) * len(DESENLER)
    for bs in bes:
        assert harita[(bs, politika.STANDART)] == std_eski[bs]
        for d, desen in enumerate(DESENLER):
            assert icerik[harita[(bs, d)], 1:].tolist() == desen.tolist()
    assert harita[("Standart", politika.STANDART)] == std_eski["Standart"]
    assert ("Standart", 0) not in harita


def test_paket_ekle_kararli_ve_bos(paketler):
    """Aynı girdi aynı tabloyu verir; boş desen listesi tabloyu değiştirmez; ikinci kez ekleme
    ve beşli olmayan desen reddedilir."""
    a, ha = politika.paket_ekle(paketler, DESENLER)
    b, hb = politika.paket_ekle(paketler.copy(), DESENLER.tolist())
    pd.testing.assert_frame_equal(a, b)
    assert ha == hb
    bos, hbos = politika.paket_ekle(paketler, np.zeros((0, 5), dtype=np.int64))
    pd.testing.assert_frame_equal(bos, paketler)
    assert set(d for _, d in hbos) == {politika.STANDART}
    with pytest.raises(ValueError):
        politika.paket_ekle(a, DESENLER)
    with pytest.raises(ValueError):
        politika.paket_ekle(paketler, [[1, 2, 2, 2]])
    with pytest.raises(ValueError):
        politika.paket_ekle(paketler, [[1, 2, -1, 2, 3]])


def test_paket_indisleri_tablo_ile_tutarli(paketler):
    """Politikanın indis kuralı (`paket_indisleri`, kopya) v4 `paket_tablosu` ile birebir; harita
    indisleri tablodaki `paket_id`'ye çıkar (`sevkiyat.paket_id` kategorisi bu sırayla kurulur).
    7'li ve 12'li desenler aynı kopyada tutarlı indislenir."""
    desenler = np.vstack([DESENLER, [[1, 2, 4, 3, 2], [2, 3, 4, 2, 1]]])
    df, harita = politika.paket_ekle(paketler, desenler)
    ids, std = politika.paket_indisleri(df)
    v4_ids, v4_std, icerik = paket_tablosu(df)
    assert list(ids) == list(v4_ids) and std == v4_std
    kategori = pd.Index(v4_ids.astype(str))          # tablolar.sevkiyat_tablosu'nun kategorileri
    for (bs, d), i in harita.items():
        pid = kategori[i]
        satir = df[df["paket_id"] == pid]
        assert set(satir["beden_seti"]) == {bs}
        if d == politika.STANDART:
            assert pid.startswith("PKT")
        else:
            assert pid == f"PKD{d:02d}-{kategori[std[bs]]}"
            assert satir.sort_values("beden_sira")["adet"].tolist() == desenler[d].tolist()
            assert int(icerik[i].sum()) == int(desenler[d].sum())


# ---------------------------------------------------------------------------
# PaketSecimi
# ---------------------------------------------------------------------------


def test_paket_secimi_m_uzunlukta(paketler):
    """[M] int64 indis: oyun option'ında mağazanın deseni (option'ın setindeki paket); atama dışı
    mağaza, oyun dışı option ve beş bedenli olmayan set standart paket."""
    df, harita = politika.paket_ekle(paketler, DESENLER)
    w = _dunya(df)
    _, std = politika.paket_indisleri(df)
    sec = politika.PaketSecimi({"M1": 0, "M2": 2, "M3": 1}, harita, desenler=DESENLER,
                               optionlar=["O1", "O2", "O3"])
    p = sec(_g(w), 0)
    assert p.dtype == np.int64 and p.shape == (4,)
    kh = "Kadın Harf"
    assert p.tolist() == [harita[(kh, 0)], harita[(kh, 2)], harita[(kh, 1)], std[kh]]
    en = "Erkek Numara"
    assert sec(_g(w), 1).tolist() == [harita[(en, 0)], harita[(en, 2)], harita[(en, 1)], std[en]]
    assert sec(_g(w), 2).tolist() == [std["Standart"]] * 4             # aksesuar: standart
    assert sec(_g(w), 3).tolist() == [std[kh]] * 4                     # oyun dışı option
    bos = politika.PaketSecimi({}, harita, desenler=DESENLER, optionlar=["O1"])
    assert bos(_g(w), 0).tolist() == [std[kh]] * 4                     # doğrulama kolu: atama yok


def test_paket_secimi_lumoda_ile_ayni(paketler):
    """Atamasız seçim Lumoda'nın `lumoda_paket_secimi`'yle aynı indisi verir (standart ilk kaldığı
    için eklenen satırlar Lumoda'yı değiştirmez)."""
    from perakende_veri.v4.politika import lumoda_paket_secimi

    df, harita = politika.paket_ekle(paketler, DESENLER)
    w = _dunya(df)
    sec = politika.PaketSecimi({}, harita, desenler=DESENLER, optionlar=["O1", "O2", "O3", "O4"])
    for o in range(4):
        assert sec(_g(w), o).tolist() == lumoda_paket_secimi(_g(w), o).tolist()


def test_paket_secimi_girdi_denetimi(paketler):
    df, harita = politika.paket_ekle(paketler, DESENLER)
    with pytest.raises(ValueError):
        politika.PaketSecimi({"M1": 3}, harita, desenler=DESENLER, optionlar=["O1"])   # desen yok
    with pytest.raises(ValueError):
        politika.PaketSecimi({"M1": -1}, harita, desenler=DESENLER, optionlar=["O1"])


def test_parametreler_kanonik(paketler):
    """`parametreler()` JSON'a birebir döner; sözlük sırası, Series / dict ve numpy türleri kimliği
    değiştirmez; desen ya da atama değişince değişir."""
    from allocation.motor import _kanonik

    df, harita = politika.paket_ekle(paketler, DESENLER)
    a = politika.PaketSecimi({"M2": 2, "M1": 0}, harita, desenler=DESENLER, optionlar=["O2", "O1"])
    b = politika.PaketSecimi(pd.Series({"M1": np.int64(0), "M2": np.int64(2)}), dict(reversed(harita.items())),
                             desenler=DESENLER.tolist(), optionlar=np.array(["O1", "O2"]))
    pa, pb = a.parametreler(), b.parametreler()
    assert _kanonik(pa) == pa
    assert json.dumps(pa, sort_keys=True) == json.dumps(pb, sort_keys=True)
    assert pa["desenler"] == DESENLER.tolist() and pa["atama"] == [["M1", 0], ["M2", 2]]
    c = politika.PaketSecimi({"M1": 0, "M2": 1}, harita, desenler=DESENLER, optionlar=["O1", "O2"])
    assert c.parametreler() != pa

    temel = lambda g, o: np.zeros(4, dtype=np.int64)  # noqa: E731
    n1 = politika.GidenIlkDagitim({("O1", "M2"): 3, ("O1", "M1"): np.int64(2)}, temel, ["O1"])
    n2 = politika.GidenIlkDagitim({("O1", "M1"): 2, ("O1", "M2"): 3}, temel, np.array(["O1"]))
    assert _kanonik(n1.parametreler()) == n1.parametreler()
    assert n1.parametreler() == n2.parametreler()
    assert n1.parametreler()["toplam"] == 5
    n3 = politika.GidenIlkDagitim({("O1", "M1"): 2, ("O1", "M2"): 4}, temel, ["O1"])
    assert n3.parametreler() != n1.parametreler()


# ---------------------------------------------------------------------------
# GidenIlkDagitim
# ---------------------------------------------------------------------------


def test_giden_ilk_dagitim(paketler):
    """Oyun option'ında [M] = ns (yoksa 0); oyun dışı option'da Lumoda'nın kuralı (`temel`) aynen."""
    w = _dunya(paketler)
    cagri = []

    def temel(g, o):
        cagri.append(o)
        return np.full(4, 9, dtype=np.int64)

    p = politika.GidenIlkDagitim({("O1", "M3"): 4, ("O1", "M1"): 1, ("O2", "M4"): 2, ("O9", "M1"): 5},
                                 temel, ["O1", "O2"])
    assert p.temel is temel
    a = p(_g(w), 0)
    assert a.dtype == np.int64 and a.tolist() == [1, 0, 4, 0]
    assert p(_g(w), 1).tolist() == [0, 0, 0, 2]
    assert cagri == []
    assert p(_g(w), 3).tolist() == [9, 9, 9, 9] and cagri == [3]
    with pytest.raises(ValueError):
        politika.GidenIlkDagitim({("O1", "M1"): -1}, temel, ["O1"])
