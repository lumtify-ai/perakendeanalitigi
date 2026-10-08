"""Hikâye seçimi (spec §5): ölçüt mantığı küçük sentetik tablolarla.

`sec_tablolardan` DataFrame alan saf fonksiyondur; `sec` veriyi toplayıp onu çağırır.
Dünya: İstanbul'da üç mağaza (I1, I2 cadde, I3 AVM), Trabzon'da iki (T1 AVM, T2 cadde),
Ankara'da bir (A1). Beden sırası 1..5; çekirdek S-M-L = sıra 2-4."""

from datetime import date

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


def test_ikinci_alici_ayni_blogun_en_yuksek_w_si_ve_rakip_sayisi():
    urunler = _urunler(("O1", "Kazak"))
    stok = _stok(I1_O1=KIRIK, I2_O1=TAM, A1_O1=TAM, T1_O1=TAM)
    greedy = _hareket(("T1", "I1", "O1"))
    # aynı (T1, O1) bloğuna aday: I2 (90), A1 (40: bölge fark etmez), I3 (70); başka verici sayılmaz
    w = _w(("T1", "I2", "O1", 90.0), ("T1", "A1", "O1", 40.0), ("T1", "I3", "O1", 70.0),
           ("T2", "I3", "O1", 500.0), ("T1", "I1", "O1", 999.0))
    h = _sec(urunler, stok, greedy, _kayip(I1_O1=7), w=w)
    assert h.ikinci_alici == "I2" and h.rakip_alici_sayisi == 3
    assert "ikinci_alici_yok" not in h.gevseyen


def test_ikinci_alici_yalniz_pozitif_w_ve_negatif_rakip_sayilmaz():
    urunler = _urunler(("O1", "Kazak"))
    stok = _stok(I1_O1=KIRIK, T1_O1=TAM)
    greedy = _hareket(("T1", "I1", "O1"))
    # I2 zararına aday (w < 0): ne ikinci alıcı ne rakip
    w = _w(("T1", "I2", "O1", -11310.8), ("T1", "I3", "O1", 50.0))
    h = _sec(urunler, stok, greedy, _kayip(I1_O1=7), w=w)
    assert (h.ikinci_alici, h.rakip_alici_sayisi) == ("I3", 1)
    # yalnız zararına aday kalırsa ikinci alıcı yok
    h = _sec(urunler, stok, greedy, _kayip(I1_O1=7), w=_w(("T1", "I2", "O1", -5.0),
                                                           ("T1", "I3", "O1", 0.0)))
    assert (h.ikinci_alici, h.rakip_alici_sayisi) == (None, 0)
    assert "ikinci_alici_yok" in h.gevseyen


def test_ikinci_alici_esitlikte_pencere_kaybi_sonra_kimlik():
    urunler = _urunler(("O1", "Kazak"))
    stok = _stok(I1_O1=KIRIK, T1_O1=TAM)
    greedy = _hareket(("T1", "I1", "O1"))
    # w kuruşa yuvarlı eşit (50,001 ve 50,004 → 50,00): kaybı büyük olan I3 öne geçer
    w = _w(("T1", "I2", "O1", 50.001), ("T1", "I3", "O1", 50.004))
    h = _sec(urunler, stok, greedy, _kayip(I1_O1=7, I2_O1=2, I3_O1=9), w=w)
    assert (h.ikinci_alici, h.rakip_alici_sayisi) == ("I3", 2)
    # kayıp da eşitse alıcı kimliği
    h = _sec(urunler, stok, greedy, _kayip(I1_O1=7, I2_O1=4, I3_O1=4), w=w)
    assert h.ikinci_alici == "I2"
    # w farklıysa kayıp bakılmaz
    w2 = _w(("T1", "I2", "O1", 60.0), ("T1", "I3", "O1", 50.0))
    h = _sec(urunler, stok, greedy, _kayip(I1_O1=7, I3_O1=99), w=w2)
    assert h.ikinci_alici == "I2"


def test_karsi_verici_ayni_option_her_bolge_en_cok_stok():
    urunler = _urunler(("O1", "Kazak"))
    stok = _stok(I1_O1=KIRIK, T1_O1=TAM,
                 I3_O1=[5, 5, 5, 5, 5],             # cover 2,5: aday
                 A1_O1=[40, 40, 40, 40, 40],        # Ankara, cover 1,0: en çok stoklu, bölge fark etmez
                 T2_O1=[50, 50, 50, 50, 50])        # cover 9: eşik üstü
    h = _sec(urunler, stok, _hareket(("T1", "I1", "O1")), _kayip(I1_O1=7),
             cover=_cover(I3_O1=2.5, A1_O1=1.0, T2_O1=9.0))
    assert (h.karsi_verici, h.karsi_option_id) == ("A1", "O1")
    assert "karsi_verici_baska_option" not in h.gevseyen


def test_karsi_verici_baska_option_ayni_kategori_istanbul():
    # O1'de cover < 6 mağaza yok; aynı alt kategoride (Kazak, AW25) O2'de İstanbul 3 var,
    # Ankara'daki daha çok stoklu ama İstanbul değil; O3 Mont (başka kategori)
    urunler = _urunler(("O1", "Kazak"), ("O2", "Kazak"), ("O3", "Mont"))
    stok = _stok(I1_O1=KIRIK, T1_O1=TAM, I3_O2=[5, 5, 5, 5, 5], A1_O2=[40, 40, 40, 40, 40],
                 I2_O3=[90, 90, 90, 90, 90])
    h = _sec(urunler, stok, _hareket(("T1", "I1", "O1")), _kayip(I1_O1=7),
             cover=_cover(I3_O2=2.0, A1_O2=1.0, I2_O3=1.0, T1_O1=40.0))
    assert (h.karsi_verici, h.karsi_option_id) == ("I3", "O2")
    assert "karsi_verici_baska_option" in h.gevseyen


def test_yan_roller_yoksa_none():
    urunler = _urunler(("O1", "Kazak"))
    stok = _stok(I1_O1=KIRIK, T1_O1=TAM, I3_O1=[5, 5, 5, 5, 5])
    # blokta başka aday alıcı yok; I3'ün cover'ı 6 ve üstü ve başka option yok
    h = _sec(urunler, stok, _hareket(("T1", "I1", "O1")), _kayip(I1_O1=7),
             cover=_cover(I3_O1=6.0), w=_w(("T2", "I2", "O1", 10.0)))
    assert h.ikinci_alici is None and h.karsi_verici is None
    assert h.rakip_alici_sayisi == 0 and h.karsi_option_id is None
    assert h.gevseyen == ["ikinci_alici_yok", "karsi_verici_yok"]


def test_kullanici_secimi_iki_planda_da_tasinmali():
    opt, alici, verici = hikaye_sec.KULLANICI_SECIMI
    var = _hareket((verici, alici, opt))
    bos = _hareket(("X", "Y", "Z"))
    assert hikaye_sec.varsayilan_secim(var, var) == hikaye_sec.KULLANICI_SECIMI
    with pytest.raises(LookupError, match="mip"):
        hikaye_sec.varsayilan_secim(var, bos)
    with pytest.raises(LookupError, match="greedy"):
        hikaye_sec.varsayilan_secim(bos, var)


def test_yakin_adaylar_tutmayan_sayisina_gore_siralar():
    urunler = _urunler(("O1", "Kazak"), ("O2", "Pantolon"))
    stok = _stok(I1_O1=KIRIK, A1_O1=TAM, I3_O2=KIRIK, A1_O2=TAM, I1_O2=KIRIK)
    greedy = _hareket(("A1", "I1", "O1"), ("A1", "I3", "O2"), ("A1", "I1", "O2"))
    ya = hikaye_sec.yakin_adaylar(urunler, MAGAZALAR, stok, greedy, greedy, _kayip(I1_O1=1))
    assert list(ya["n_tutmayan"]) == [1, 2, 3]            # Kazak: yalnız trabzon
    assert ya.loc[0, "tutmayan"] == "trabzon" and ya.loc[0, "option_id"] == "O1"
    assert ya.loc[2, "tutmayan"].startswith("alt_kategori, cadde")


def _kayipli_ozet_girdisi():
    return pd.DataFrame([("2026-01-05", "MB", "OPT1-3", 12), ("2026-01-05", "MB", "OPT1-1", 3),
                         ("2026-01-12", "ME", "OPT1-2", 2)],
                        columns=["tarih", "magaza_id", "urun_id", "kayip"]
                        ).assign(tarih=lambda d: pd.to_datetime(d["tarih"]))


def _ozetle(con):
    con.execute("alter table urun add column renk varchar")      # fikstürde renk yok
    h = Hikaye(option_id="OPT1", model_adi="Model OPT1", alici="MB", verici="MA",
               ikinci_alici="MC", karsi_verici="MA", mip_de_tasiyor=True, gevseyen=[],
               rakip_alici_sayisi=1, karsi_option_id="OPT2")
    return hikaye_sec.ozet(con, date(2025, 12, 29), h, _kayipli_ozet_girdisi())


def test_ozet_rol_sayilari_ve_baska_option_karsi_verici(con):
    o = _ozetle(con)
    for rol in ("alici", "verici", "ikinci_alici", "karsi_verici"):
        assert sum(o[rol]["bedenler"].values()) == o[rol]["toplam"]
    assert o["alici"]["bedenler"] == {"XS": 2, "S": 0, "M": 0, "L": 0, "XL": 3}
    assert (o["alici"]["toplam"], o["verici"]["toplam"]) == (5, 12)
    assert o["alici"]["hiz_8h"] == pytest.approx(4.0)
    assert o["verici"]["hiz_8h"] == pytest.approx(0.5)
    assert o["alici"]["pencere_kaybi"] == 15 and o["alici"]["kayip_beden"] == {"M": 12, "XS": 3}
    # karşı verici başka option'da: rolün option_id'si ve o option'ın stoku
    kv = o["karsi_verici"]
    assert kv["option_id"] == "OPT2" and kv["magaza_id"] == "MA" and kv["toplam"] == 8
    assert kv["bedenler"] == {"XS": 2, "S": 1, "M": 2, "L": 1, "XL": 2}
    assert o["alici"]["option_id"] == o["verici"]["option_id"] == "OPT1"
    # stoksuz hücrede (cover satırı yok) hız yok: 0 değil None
    assert o["ikinci_alici"]["toplam"] == 0 and o["ikinci_alici"]["hiz_8h"] is None


def test_ozet_karar_sonrasi_satirlardan_etkilenmez(con, con_ileri):
    ref, ileri = _ozetle(con), _ozetle(con_ileri)
    for rol in ("alici", "verici", "ikinci_alici", "karsi_verici"):
        for alan in ("bedenler", "toplam", "hiz_8h", "cover", "str"):
            assert ileri[rol][alan] == ref[rol][alan], (rol, alan)


def test_cli_hikaye_ayristirma():
    assert hikaye_sec.hikaye_ayristir("OPT1:MB:MA") == ("OPT1", "MB", "MA")
    with pytest.raises(ValueError):
        hikaye_sec.hikaye_ayristir("OPT1:MB")
