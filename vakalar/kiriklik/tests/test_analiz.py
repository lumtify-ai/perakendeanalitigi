"""analiz.py: referans pazartesisi ve hafta numarası (oyuncak takvimle); `veri` işaretli: yayımlanan v4'te uygunluk
hunisi tasarımın keşif sayılarını (§0 ve K18) yeniden üretir ve referans pazartesisinin fotoğrafı karar anının
girdisiyle aynı kırıklığı verir."""

from datetime import date

import pytest

import analiz
from kiriklik import sabitler


def test_referans_ve_hafta(con):
    """Referans pazartesisi indirim − 28'den sonraki ilk pazartesidir; test sezonunda karar günü. Hafta indirim gününün
    haftasına göre."""
    g = analiz.sezon_gunleri(con, "AW24")
    assert g["referans"] == sabitler.KARAR["AW24"] == date(2024, 12, 9) and g["lansman"] == date(2024, 8, 19)
    assert analiz.hafta_no(date(2024, 12, 30), g) == 0 and analiz.hafta_no(date(2024, 12, 9), g) == -3
    p = analiz.pazartesiler(g)
    assert p[0] == date(2024, 8, 19) and p[-1] == date(2025, 2, 17) and all(d.weekday() == 0 for d in p)


@pytest.mark.veri
def test_analiz_kesif_sayilari(veri_con):
    """Tasarım §0 keşif olguları ve K18: AW24 4.051 stoklu, 1.873 kırık, dar tanımla 1.407, 1.126 depoda yok, 819 uygun;
    SS25 4.258, 1.985, 931, 651. Haftalık serinin referans pazartesisi karar girdisiyle aynı kırıklığı verir."""
    beklenen = {"AW24": (4051, 1873, 1126, 819, 819), "SS25": (4258, 1985, 931, 651, 651)}
    for z, b in beklenen.items():
        h = analiz.huni(veri_con, z)
        assert tuple(x["cift"] for x in h["basamaklar"]) == b
        assert h["neden"]["uygun"] == b[-1] and h["neden"]["magaza"] == 0
    h = analiz.huni(veri_con, "AW24")
    assert h["ozet"]["dar_kirik_cift"] == 1407 and round(100 * h["ozet"]["net_oran"], 1) == 20.2
    assert (h["kesif"]["sku"], h["kesif"]["sku_depolu"], h["kesif"]["option_deposuz"]) == (905, 392, 42)
    s = analiz.sezon_blogu(veri_con, "AW24")
    assert {a: s["referans"]["butun"][a] for a in analiz.OZET_ALANLARI} == {a: h["ozet"][a] for a in analiz.OZET_ALANLARI}
    assert s["referans"]["hafta"] == -3 and len(s["haftalik"]) == 27
    # R39: çift satışı bütün bedenlerden; AW24 referans pazartesisi: satmayan 47 / 993, atıl (eşik 2) 164 / 5.036, atıl ya da
    # satmayan payı kırık %5,50, tam %4,96; yalnız kalan bedenlerin satışıyla kırık %11,37
    w = next(x for x in s["haftalik"] if x["hafta"] == -3)["atil"]
    x2 = w["cift"][f"x{sabitler.ATIL_ESIK_OPTION}"]
    assert (x2["satmayan"]["n"], x2["satmayan"]["adet"], x2["atil"]["n"], x2["atil"]["adet"]) == (47, 993, 164, 5036)

    def pay(k):
        return round(100 * (k["atil"]["n"] + k["satmayan"]["n"]) / (sum(c["n"] for c in k.values()) - k["yeni"]["n"]), 2)

    assert (pay(w["kirik_atil"]["kirik"]), pay(w["kirik_atil"]["tam"])) == (5.50, 4.96)
    assert (pay(w["kirik_atil_kalan"]["kirik"]), pay(w["kirik_atil_kalan"]["tam"])) == (11.37, 4.96)


def test_beden_sirasi_ozetle_esit():
    """Beden sırası tablosunun toplamları aynı fotoğrafın `olcu.ozet`'ine eşittir; değilse `ValueError` (tanım tek)."""
    import pandas as pd

    from kiriklik import olcu
    foto = pd.DataFrame([("M1", "O1", i + 1, a) for i, a in enumerate((1, 0, 0, 1, 1))]
                        + [("M2", "O1", i + 1, a) for i, a in enumerate((1, 1, 2, 1, 1))]
                        + [("M3", "O1", i + 1, 0) for i in range(5)],
                        columns=["magaza_id", "option_id", "beden_sira", "stok"])
    oz = olcu.ozet(olcu.cift_tablosu(foto))
    t = analiz.beden_sirasi(foto, oz)
    assert [x["kirik_cift"] for x in t] == [0, 1, 1, 0, 0] and [x["eksik_adet"] for x in t] == [0, 3, 2, 0, 0]
    assert t[1]["pay"] == 0.5
    with pytest.raises(ValueError, match="olcu.ozet"):
        analiz.beden_sirasi(foto, oz | {"eksik_adet": oz["eksik_adet"] + 1})


# --------------------------------------------------------------------------- atıl stok (K2, Ruling R39)

T = date(2024, 12, 9)
ESKI = date(2024, 10, 1)            # rafta 28 günden uzun
YENI = date(2024, 12, 2)            # rafta 28 günden kısa


def _atil_oyuncak():
    """Beş çift, fotoğraf `t`:

    M1/O1 kırık: U1-S tükenmiş (stok 0), pencerede 3 sattı; U1-M'de 4 adet, 0 satış.
    M1/O2 kırık: U2-S tükenmiş ve fotoğrafta satırı yok, pencerede 1 sattı; U2-M'de 2 adet, 0 satış.
    M1/O3 tam: 0 satış. M1/O4 yeni: kırık, rafta 7 gün. M1/O5 stoksuz: bütün bedenler 0, pencerede 9 sattı.
    Pencere dışı (t − 29, t): sayılmaz."""
    import pandas as pd

    foto = pd.DataFrame([("M1", "U1-S", "O1", 0, 100.0), ("M1", "U1-M", "O1", 4, 100.0),
                         ("M1", "U2-M", "O2", 2, 50.0),
                         ("M1", "U3-S", "O3", 1, 10.0), ("M1", "U3-M", "O3", 1, 10.0),
                         ("M1", "U4-S", "O4", 0, 10.0), ("M1", "U4-M", "O4", 3, 10.0),
                         ("M1", "U5-S", "O5", 0, 10.0)],
                        columns=["magaza_id", "urun_id", "option_id", "stok", "alis"])
    hafta_ici = date(2024, 11, 25)
    satis = pd.DataFrame([(hafta_ici, "M1", "U1-S", "O1", 3), (hafta_ici, "M1", "U2-S", "O2", 1),
                          (hafta_ici, "M1", "U5-S", "O5", 9), (hafta_ici, "M1", "U4-S", "O4", 8),
                          (date(2024, 11, 4), "M1", "U1-M", "O1", 5), (T, "M1", "U1-M", "O1", 5)],
                         columns=["hafta", "magaza_id", "urun_id", "option_id", "adet"])
    ilk_cift = pd.Series({("M1", "O1"): ESKI, ("M1", "O2"): ESKI, ("M1", "O3"): ESKI, ("M1", "O4"): YENI})
    ilk_hucre = pd.Series({("M1", "U1-M"): ESKI, ("M1", "U2-M"): ESKI, ("M1", "U3-S"): ESKI, ("M1", "U3-M"): ESKI,
                           ("M1", "U4-M"): YENI})
    cift = pd.DataFrame([("M1", "O1", True), ("M1", "O2", True), ("M1", "O3", False), ("M1", "O4", True)],
                        columns=["magaza_id", "option_id", "kirik"])
    return foto, satis, ilk_cift, ilk_hucre, cift


def test_atil_cift_satisi_butun_bedenlerden():
    """Ruling R39: pencerede satıp tükenen beden çiftin satışında kalır. Kalan bedende 0, tükenen bedende 3 satan çift
    `satan`dır (eşik 2), `satmayan` değil; fotoğrafta satırı kalmamış beden de sayılır. Stoğu sıfır çift çıkmaz; adet ve
    değer stoklu hücrelerden; pencere dışı satış ve `yeni` çift sayılmaz."""
    foto, satis, ilk_cift, ilk_hucre, cift = _atil_oyuncak()
    r = analiz.atil_haftasi(foto, satis, ilk_cift, ilk_hucre, T, cift)
    x2 = r["cift"]["x2"]
    assert {c: x2[c]["n"] for c in x2} == {"satmayan": 1, "atil": 1, "satan": 1, "yeni": 1}
    assert (x2["satan"]["adet"], x2["satan"]["alis"]) == (4, 400.0)         # O1: yalnız stoklu U1-M
    assert (x2["atil"]["adet"], x2["atil"]["alis"]) == (2, 100.0)           # O2: 1 satış, stoklu U2-M
    assert (x2["satmayan"]["adet"], x2["yeni"]["adet"]) == (2, 3)           # O3; O4
    assert r["cift"]["x1"]["atil"]["n"] == 1 and r["cift"]["x3"]["atil"]["n"] == 2      # O2; O2 ve O1


def test_atil_kesisimi_iki_olcu():
    """`kirik_atil` bütün bedenlerin satışıyla; `kirik_atil_kalan` yalnız stoklu bedenlerinkiyle (ölçüm tuzağının sayısı,
    kırık ile tam kıyası bununla yapılmaz). Tam çiftte ikisi aynıdır: düşen beden yok."""
    foto, satis, ilk_cift, ilk_hucre, cift = _atil_oyuncak()
    r = analiz.atil_haftasi(foto, satis, ilk_cift, ilk_hucre, T, cift)
    k, kk = r["kirik_atil"], r["kirik_atil_kalan"]
    assert {c: k["kirik"][c]["n"] for c in k["kirik"]} == {"satmayan": 0, "atil": 1, "satan": 1, "yeni": 1}
    assert {c: kk["kirik"][c]["n"] for c in kk["kirik"]} == {"satmayan": 2, "atil": 0, "satan": 0, "yeni": 1}
    assert k["tam"] == kk["tam"] and k["tam"]["satmayan"]["n"] == 1


def test_atil_sku_duzeyi_kendi_satisiyla():
    """Beden düzeyi hücrenin kendi satışını sayar: tükenen hücre çıkar, kalan U1-M `satmayan`."""
    foto, satis, ilk_cift, ilk_hucre, cift = _atil_oyuncak()
    sku = analiz.atil_haftasi(foto, satis, ilk_cift, ilk_hucre, T, cift)["sku"]
    assert {c: sku[c]["n"] for c in sku} == {"satmayan": 4, "atil": 0, "satan": 0, "yeni": 1}
    assert sku["satmayan"]["adet"] == 4 + 2 + 1 + 1 and sku["yeni"]["adet"] == 3


def test_haftalik_satis_option_tasir(con):
    """Çift satışı için `haftalik_satis` option'ı taşır: satırı fotoğrafta kalmamış beden de çifte yazılır."""
    g = analiz.sezon_gunleri(con, "AW24")
    df = analiz.haftalik_satis(con, "AW24", g["lansman"], g["cikis"])
    assert list(df.columns) == ["hafta", "magaza_id", "urun_id", "option_id", "adet"]
