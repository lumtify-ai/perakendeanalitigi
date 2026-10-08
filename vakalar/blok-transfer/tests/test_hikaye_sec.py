"""Hikâye seçimi (spec §5): ölçüt mantığı küçük sentetik tablolarla.

`sec_tablolardan` DataFrame alan saf fonksiyondur; `sec` veriyi toplayıp onu çağırır.
Dünya: İstanbul'da üç mağaza (I1, I2 cadde, I3 AVM), Trabzon'da iki (T1 AVM, T2 cadde),
Ankara'da bir (A1). Beden sırası 1..5; çekirdek S-M-L = sıra 2-4."""

import pandas as pd
import pytest

from blok_transfer import hikaye_sec
from blok_transfer.hikaye_sec import Hikaye, sec_tablolardan

MAGAZALAR = pd.DataFrame([
    ("I1", "İstanbul 1", "İstanbul", "Cadde"),
    ("I2", "İstanbul 2", "İstanbul", "Cadde"),
    ("I3", "İstanbul 3", "İstanbul", "AVM"),
    ("T1", "Trabzon 1", "Trabzon", "AVM"),
    ("T2", "Trabzon 2", "Trabzon", "Cadde"),
    ("A1", "Ankara 1", "Ankara", "Cadde"),
], columns=["magaza_id", "ad", "sehir", "tip"])

TAM = [2, 2, 2, 2, 2]
KIRIK = [2, 0, 0, 0, 3]          # uçlar var, S-M-L sıfır
ORTA_VAR = [1, 1, 0, 1, 1]       # M sıfır ama S ve L var: üçü birden sıfır değil


def _urunler(*opsiyonlar):
    """(option_id, alt_kategori[, line, sezon, n_beden]) → urun özeti; varsayılan Collection, AW25, 5."""
    satirlar = []
    for o in opsiyonlar:
        opt, alt, *geri = o
        line, sezon, n = (geri + ["Collection", "AW25", 5][len(geri):])
        satirlar.append((opt, f"Model {opt}", alt, line, sezon, n))
    return pd.DataFrame(satirlar, columns=["option_id", "model_adi", "alt_kategori", "line",
                                           "sezon_kodu", "n_beden"])


def _olcut(h):
    """gevseyen'in ölçüt kısmı (yan rol notları `_yok` ile biter)."""
    return [g for g in h.gevseyen if not g.endswith("_yok")]


def _stok(**hucreler):
    """`I1_O1=[...]` → SKU düzeyi stok satırları (anahtar: MAGAZA_OPTION)."""
    satirlar = []
    for anahtar, adetler in hucreler.items():
        magaza, opt = anahtar.split("_")
        for sira, adet in enumerate(adetler, start=1):
            satirlar.append((magaza, opt, f"{opt}-{sira}", sira, adet))
    return pd.DataFrame(satirlar, columns=["magaza_id", "option_id", "urun_id", "beden_sira", "adet"])


def _hareket(*uclular):
    return pd.DataFrame(uclular, columns=["verici", "alici", "option_id"]).assign(adet=10, w=100.0)


def _kayip(**degerler):
    """`I1_O1=7` → alıcı hücrenin pencere kaybı (option toplamı)."""
    satirlar = [(*k.split("_"), v) for k, v in degerler.items()]
    return pd.DataFrame(satirlar, columns=["magaza_id", "option_id", "kayip"])


def _cover(**degerler):
    satirlar = [(*k.split("_"), v) for k, v in degerler.items()]
    return pd.DataFrame(satirlar, columns=["magaza_id", "option_id", "cover"])


def _w(*uclular):
    return pd.DataFrame(uclular, columns=["verici", "alici", "option_id", "w"])


def _sec(urunler, stok, greedy, kayip, mip=None, cover=None, w=None, zorla=None):
    return sec_tablolardan(
        urunler=urunler, magazalar=MAGAZALAR, stok=stok,
        greedy=greedy, mip=greedy if mip is None else mip, kayip=kayip,
        cover=_cover() if cover is None else cover,
        w=_w() if w is None else w, zorla=zorla)


def test_butun_olcutleri_saglayan_secilir():
    urunler = _urunler(("O1", "Kazak"))
    stok = _stok(I1_O1=KIRIK, T1_O1=TAM,
                 I2_O1=TAM,               # kırık değil: alıcı olamaz
                 A1_O1=TAM)               # Trabzon değil: verici olamaz
    greedy = _hareket(("T1", "I1", "O1"), ("T1", "I2", "O1"), ("A1", "I1", "O1"))
    h = _sec(urunler, stok, greedy, _kayip(I1_O1=7))
    assert isinstance(h, Hikaye)
    assert (h.option_id, h.alici, h.verici) == ("O1", "I1", "T1")
    assert h.model_adi == "Model O1"
    assert _olcut(h) == []
    assert h.mip_de_tasiyor is True


def test_kategori_onceligi_kazak_sweatshirt_diger_ustgiyim():
    # kaybı en yüksek Mont, en düşük Kazak: öncelik sırası kayıptan önce gelir
    urunler = _urunler(("O1", "Mont"), ("O2", "Sweatshirt"), ("O3", "Kazak"))
    stok = _stok(I1_O1=KIRIK, I1_O2=KIRIK, I1_O3=KIRIK, T1_O1=TAM, T1_O2=TAM, T1_O3=TAM)
    greedy = _hareket(("T1", "I1", "O1"), ("T1", "I1", "O2"), ("T1", "I1", "O3"))
    h = _sec(urunler, stok, greedy, _kayip(I1_O1=90, I1_O2=50, I1_O3=1))
    assert h.option_id == "O3"
    h = _sec(urunler, stok, greedy.query("option_id != 'O3'"), _kayip(I1_O1=90, I1_O2=50))
    assert h.option_id == "O2"


def test_sezon_hat_ve_bes_beden_zorunlu():
    # AW24, Basic ve 4 bedenli seçenekler elenir; hiçbiri kalmazsa gevşetmeyle de gelmez
    urunler = _urunler(("O1", "Kazak", "Collection", "SS25", 5), ("O2", "Kazak", "Basic", "AW25", 5),
                       ("O3", "Kazak", "Collection", "AW25", 4))
    stok = _stok(I1_O1=KIRIK, T1_O1=TAM, I1_O2=KIRIK, T1_O2=TAM, I1_O3=[2, 0, 0, 3], T1_O3=[2, 2, 2, 2])
    greedy = _hareket(("T1", "I1", "O1"), ("T1", "I1", "O2"), ("T1", "I1", "O3"))
    with pytest.raises(LookupError):
        _sec(urunler, stok, greedy, _kayip(I1_O1=9, I1_O2=9, I1_O3=9))
    # NOS hattı geçerli
    urunler = _urunler(("O4", "Kazak", "NOS", "AW25", 5))
    h = _sec(urunler, _stok(I1_O4=KIRIK, T1_O4=TAM), _hareket(("T1", "I1", "O4")), _kayip(I1_O4=1))
    assert h.option_id == "O4"


def test_alici_s_m_l_ucu_de_sifir_olmali():
    # I1'de yalnız M sıfır (S, L var): ölçüt "üçü de 0" → alıcı değil
    urunler = _urunler(("O1", "Kazak"))
    stok = _stok(I1_O1=ORTA_VAR, T1_O1=TAM)
    with pytest.raises(LookupError):
        _sec(urunler, stok, _hareket(("T1", "I1", "O1")), _kayip(I1_O1=5))


def test_verici_seti_tam_olmali():
    urunler = _urunler(("O1", "Kazak"))
    stok = _stok(I1_O1=KIRIK, T1_O1=[2, 2, 0, 2, 2])
    with pytest.raises(LookupError):
        _sec(urunler, stok, _hareket(("T1", "I1", "O1")), _kayip(I1_O1=5))


def test_kayba_gore_siralar():
    urunler = _urunler(("O1", "Kazak"), ("O2", "Kazak"), ("O3", "Kazak"))
    stok = _stok(I1_O1=KIRIK, I1_O2=KIRIK, I1_O3=KIRIK, I2_O3=KIRIK,
                 T1_O1=TAM, T1_O2=TAM, T1_O3=TAM)
    greedy = _hareket(("T1", "I1", "O1"), ("T1", "I1", "O2"), ("T1", "I1", "O3"), ("T1", "I2", "O3"))
    h = _sec(urunler, stok, greedy, _kayip(I1_O1=5, I1_O2=9, I1_O3=2, I2_O3=3))
    assert (h.option_id, h.alici) == ("O2", "I1")
    # eşit kayıpta option_id küçük olan
    h = _sec(urunler, stok, greedy, _kayip(I1_O1=4, I1_O2=4, I1_O3=2))
    assert h.option_id == "O1"


def test_plan_tasimiyorsa_secilmez():
    urunler = _urunler(("O1", "Kazak"), ("O2", "Kazak"))
    stok = _stok(I1_O1=KIRIK, I1_O2=KIRIK, T1_O1=TAM, T1_O2=TAM)
    greedy = _hareket(("T1", "I1", "O1"))                  # O2'yi plan taşımıyor
    h = _sec(urunler, stok, greedy, _kayip(I1_O1=1, I1_O2=99))
    assert h.option_id == "O1"
    # MIP O1'i taşımıyor
    h = _sec(urunler, stok, greedy, _kayip(I1_O1=1, I1_O2=99), mip=_hareket(("T1", "I1", "O2")))
    assert h.option_id == "O1" and h.mip_de_tasiyor is False


def test_tek_olcut_gevser_ve_kaydedilir():
    # alt kategori: yalnız Pantolon var → üst giyim ölçütü gevşer
    h = _sec(_urunler(("O1", "Pantolon")), _stok(I1_O1=KIRIK, T1_O1=TAM),
             _hareket(("T1", "I1", "O1")), _kayip(I1_O1=3))
    assert (h.option_id, _olcut(h)) == ("O1", ["alt_kategori"])
    # cadde: alıcı AVM
    h = _sec(_urunler(("O1", "Kazak")), _stok(I3_O1=KIRIK, T1_O1=TAM),
             _hareket(("T1", "I3", "O1")), _kayip(I3_O1=3))
    assert (h.alici, _olcut(h)) == ("I3", ["cadde"])
    # Trabzon: verici Ankara
    h = _sec(_urunler(("O1", "Kazak")), _stok(I1_O1=KIRIK, A1_O1=TAM),
             _hareket(("A1", "I1", "O1")), _kayip(I1_O1=3))
    assert (h.verici, _olcut(h)) == ("A1", ["trabzon"])


def test_gevsetme_sirasi_tekli_once_ikili_sonra():
    # O1 yalnız cadde ölçütünü bozar, O2 yalnız alt kategoriyi bozar: sırada 1 (alt kategori) önce
    urunler = _urunler(("O1", "Kazak"), ("O2", "Pantolon"))
    stok = _stok(I3_O1=KIRIK, T1_O1=TAM, I1_O2=KIRIK, T1_O2=TAM)
    greedy = _hareket(("T1", "I3", "O1"), ("T1", "I1", "O2"))
    h = _sec(urunler, stok, greedy, _kayip(I3_O1=50, I1_O2=1))
    assert (h.option_id, _olcut(h)) == ("O2", ["alt_kategori"])
    # ikisi birden bozuk tek aday: ikili gevşetme, ikisi de yazılır (sıra 1 sonra 2)
    h = _sec(_urunler(("O1", "Pantolon")), _stok(I3_O1=KIRIK, T1_O1=TAM),
             _hareket(("T1", "I3", "O1")), _kayip(I3_O1=1))
    assert _olcut(h) == ["alt_kategori", "cadde"]
    h = _sec(_urunler(("O1", "Pantolon")), _stok(I1_O1=KIRIK, A1_O1=TAM),
             _hareket(("A1", "I1", "O1")), _kayip(I1_O1=1))
    assert _olcut(h) == ["alt_kategori", "trabzon"]
    h = _sec(_urunler(("O1", "Kazak")), _stok(I3_O1=KIRIK, A1_O1=TAM),
             _hareket(("A1", "I3", "O1")), _kayip(I3_O1=1))
    assert _olcut(h) == ["cadde", "trabzon"]


def test_hicbiri_yoksa_hata():
    # üçü birden bozuk: iki ölçütten fazlası gevşemez
    with pytest.raises(LookupError):
        _sec(_urunler(("O1", "Pantolon")), _stok(I3_O1=KIRIK, A1_O1=TAM),
             _hareket(("A1", "I3", "O1")), _kayip(I3_O1=1))
    # plan hiçbir şey taşımıyor
    with pytest.raises(LookupError):
        _sec(_urunler(("O1", "Kazak")), _stok(I1_O1=KIRIK, T1_O1=TAM),
             _hareket(), _kayip(I1_O1=1))


def test_bulunamayinca_hata_hunisini_soyler():
    # plan bloğu var ama alıcı kırık değil: huni "alici_kirik 0" der
    with pytest.raises(LookupError, match="alici_kirik 0"):
        _sec(_urunler(("O1", "Kazak")), _stok(I1_O1=TAM, T1_O1=TAM),
             _hareket(("T1", "I1", "O1")), _kayip(I1_O1=1))


def test_zorla_gecersiz_kilar():
    urunler = _urunler(("O1", "Kazak"), ("O2", "Pantolon"))
    stok = _stok(I1_O1=KIRIK, T1_O1=TAM, I2_O2=KIRIK, T2_O2=TAM)
    greedy = _hareket(("T1", "I1", "O1"), ("T2", "I2", "O2"))
    kayip = _kayip(I1_O1=99, I2_O2=1)
    h = _sec(urunler, stok, greedy, kayip, zorla=("O2", "I2", "T2"))
    assert (h.option_id, h.alici, h.verici) == ("O2", "I2", "T2")
    assert _olcut(h) == ["alt_kategori"]           # zorlanan adayın tutmadığı ölçüt
    # plan o bloğu taşımıyorsa o da yazılır
    h = _sec(urunler, stok, greedy, kayip, zorla=("O1", "I2", "T1"))
    assert "greedy_hareketi" in h.gevseyen and "alici_kirik" in h.gevseyen
    with pytest.raises(LookupError):
        _sec(urunler, stok, greedy, kayip, zorla=("YOK", "I1", "T1"))


def test_yan_roller_secilir():
    urunler = _urunler(("O1", "Kazak"))
    stok = _stok(I1_O1=KIRIK, I2_O1=[1, 0, 0, 0, 1],        # ikinci alıcı: kırık
                 I3_O1=[5, 5, 5, 5, 5], T1_O1=TAM, T2_O1=TAM,  # I3 çok stoklu
                 A1_O1=[40, 40, 40, 40, 40])                   # İstanbul değil
    greedy = _hareket(("T1", "I1", "O1"), ("T1", "I2", "O1"))
    h = _sec(urunler, stok, greedy, _kayip(I1_O1=7, I2_O1=4),
             cover=_cover(I3_O1=2.5, A1_O1=1.0, T1_O1=50.0),
             w=_w(("T1", "I2", "O1", 90.0), ("T2", "I2", "O1", 40.0)))
    assert h.ikinci_alici == "I2"
    assert h.karsi_verici == "I3"                           # İstanbul, cover 2,5 < 6, en çok stok
    assert h.gevseyen == []


def test_ikinci_alici_en_yuksek_w_baska_vericiyse_secilmez():
    urunler = _urunler(("O1", "Kazak"))
    stok = _stok(I1_O1=KIRIK, I2_O1=[1, 0, 0, 0, 1], T1_O1=TAM, T2_O1=TAM)
    greedy = _hareket(("T1", "I1", "O1"))
    h = _sec(urunler, stok, greedy, _kayip(I1_O1=7, I2_O1=4),
             w=_w(("T1", "I2", "O1", 40.0), ("T2", "I2", "O1", 90.0)))
    assert h.ikinci_alici is None and "ikinci_alici" in " ".join(h.gevseyen)


def test_yan_roller_yoksa_none():
    urunler = _urunler(("O1", "Kazak"))
    stok = _stok(I1_O1=KIRIK, T1_O1=TAM, I3_O1=[5, 5, 5, 5, 5])
    # I3'ün cover'ı 6 ve üstü: karşı verici değil; başka kırık İstanbul mağazası yok
    h = _sec(urunler, stok, _hareket(("T1", "I1", "O1")), _kayip(I1_O1=7),
             cover=_cover(I3_O1=6.0))
    assert h.ikinci_alici is None and h.karsi_verici is None
    assert h.gevseyen == ["ikinci_alici_yok", "karsi_verici_yok"]


def test_cli_hikaye_ayristirma():
    assert hikaye_sec.hikaye_ayristir("OPT1:MB:MA") == ("OPT1", "MB", "MA")
    with pytest.raises(ValueError):
        hikaye_sec.hikaye_ayristir("OPT1:MB")
