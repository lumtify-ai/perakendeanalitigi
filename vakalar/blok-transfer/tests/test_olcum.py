"""İleriye bakan ölçüm (spec §4.1–4.2): küçük, elle hesaplanan tablolarla.

Tablolar elle kurulur; `con` fikstürü yalnız `tasinan` ve `verici_satisi` için."""

from datetime import date

import pandas as pd
import pytest

from blok_transfer import hazirla, olcum
from blok_transfer.olcum import Olcum, olc

KARAR = date(2025, 12, 29)
HAREKET_KOL = ["verici", "alici", "option_id", "adet", "w"]


def _tasinan(*satirlar):
    """(verici, alici, urun_id, adet) → `tasinan` biçimi (option_id urun_id'den türer)."""
    return pd.DataFrame(
        [(v, a, u.rsplit("-", 1)[0], u, n) for v, a, u, n in satirlar],
        columns=["verici", "alici", "option_id", "urun_id", "adet"])


def _kayip(*satirlar):
    return pd.DataFrame(satirlar, columns=["magaza_id", "urun_id", "kayip"])


def _satis(*satirlar):
    return pd.DataFrame(satirlar, columns=["magaza_id", "urun_id", "adet"])


def test_pencere_hazirlayla_ayni():
    assert olcum.pencere(KARAR, 8) == hazirla.pencere(KARAR, 8)
    assert olcum.pencere(KARAR, 8) == (date(2025, 12, 29), date(2026, 2, 23))
    assert olcum.pencere(KARAR) == olcum.pencere(KARAR, 8)
    assert olcum.pencere(KARAR, 1) == (KARAR, date(2026, 1, 5))


def test_beden_eslesmesi():
    # XS taşınır, kayıp M'de: aynı option, farklı SKU → kurtarılan 0
    sonuc = olc(_tasinan(("V", "A", "OPT1-1", 4)), _kayip(("A", "OPT1-3", 5)), _satis(("V", "OPT1-1", 9)))
    assert sonuc.kurtarilan == 0 and sonuc.yakalama == 0 and sonuc.p_alici == 0
    assert sonuc.tasinan_adet == 4 and sonuc.payda == 5


def test_adet_siniri():
    sonuc = olc(_tasinan(("V", "A", "OPT1-1", 3)), _kayip(("A", "OPT1-1", 10)), _satis(("V", "OPT1-1", 9)))
    assert sonuc.kurtarilan == 3 and sonuc.yakalama == pytest.approx(0.3)
    sonuc = olc(_tasinan(("V", "A", "OPT1-1", 10)), _kayip(("A", "OPT1-1", 3)), _satis(("V", "OPT1-1", 9)))
    assert sonuc.kurtarilan == 3 and sonuc.yakalama == 1.0
    assert sonuc.p_alici == pytest.approx(0.3)


def test_iki_verici_ayni_kaybi_iki_kez_kurtarmaz():
    # iki vericiden aynı alıcı SKU'suna 2 + 2, kayıp 3 → 3 (4 değil)
    tasinan = _tasinan(("V1", "A", "OPT1-1", 2), ("V2", "A", "OPT1-1", 2))
    sonuc = olc(tasinan, _kayip(("A", "OPT1-1", 3)),
                _satis(("V1", "OPT1-1", 5), ("V2", "OPT1-1", 5)))
    assert sonuc.kurtarilan == 3
    assert sonuc.tasinan_adet == 4
    assert sonuc.p_alici == pytest.approx(0.75)


def test_payda_online_ve_evren_disi_haric():
    kayip = pd.DataFrame({
        "tarih": pd.to_datetime(["2025-12-30"] * 4),
        "magaza_id": ["A", "ONL", "DISARI", "A"],
        "urun_id": ["OPT1-1", "OPT1-1", "OPT1-1", "OPT1-2"],
        "kayip": [3, 100, 50, 4]})
    tablo = olcum.kayip_tablosu(kayip, KARAR, 8, {"A", "B"}, "kayip")
    assert list(tablo.columns) == ["magaza_id", "urun_id", "kayip"]
    assert tablo.kayip.sum() == 7
    assert set(tablo.magaza_id) == {"A"}


def test_pencere_disi_kayip_sayilmaz():
    # pencere [29 Aralık, 29 Aralık + 7 gün): ilk gün dahil, bitiş günü ve öncesi değil
    kayip = pd.DataFrame({
        "tarih": pd.to_datetime(["2025-12-28", "2025-12-29", "2026-01-04", "2026-01-05"]),
        "magaza_id": ["A"] * 4, "urun_id": ["OPT1-1"] * 4, "kayip": [1, 10, 100, 1000]})
    tablo = olcum.kayip_tablosu(kayip, KARAR, 1, {"A"}, "kayip")
    assert tablo.kayip.sum() == 110
    assert olcum.kayip_tablosu(kayip, KARAR, 2, {"A"}, "kayip").kayip.sum() == 1110


def test_toplam_hucre_basina_ve_sutun_adi():
    # hakem biçimi: kayıp sütunu `karsilanmayan`; aynı hücrenin günleri toplanır
    hakem = pd.DataFrame({
        "tarih": pd.to_datetime(["2025-12-30", "2025-12-31", "2025-12-30"]),
        "magaza_id": ["A", "A", "B"], "urun_id": ["OPT1-1", "OPT1-1", "OPT1-1"],
        "talep": [5, 5, 5], "karsilanmayan": [2, 3, 4]})
    tablo = olcum.kayip_tablosu(hakem, KARAR, 8, {"A", "B"}, "karsilanmayan")
    assert list(tablo.columns) == ["magaza_id", "urun_id", "kayip"]
    degerler = {(m, u): k for m, u, k in tablo.itertuples(index=False)}
    assert degerler == {("A", "OPT1-1"): 5, ("B", "OPT1-1"): 4}


def test_hucre_suzgeci():
    # hakem kaybı Basit'in hücre evreniyle karşılaştırılır: yalnız `hucreler` içindekiler kalır
    kayip = pd.DataFrame({
        "tarih": pd.to_datetime(["2025-12-30"] * 4),
        "magaza_id": ["A", "A", "B", "B"],
        "urun_id": ["OPT1-1", "OPT1-2", "OPT1-1", "OPT1-2"],
        "karsilanmayan": [1, 10, 100, 1000]})
    hucreler = pd.DataFrame({"magaza_id": ["A", "B"], "urun_id": ["OPT1-2", "OPT1-1"]})
    tablo = olcum.kayip_tablosu(kayip, KARAR, 8, {"A", "B"}, "karsilanmayan", hucreler)
    assert {(m, u): k for m, u, k in tablo.itertuples(index=False)} == {
        ("A", "OPT1-2"): 10, ("B", "OPT1-1"): 100}
    # süzgeç evren süzgecinin yerine geçmez: evren dışı mağaza hücresi listede olsa da düşer
    dis = pd.DataFrame({"magaza_id": ["A", "B"], "urun_id": ["OPT1-1", "OPT1-1"]})
    assert olcum.kayip_tablosu(kayip, KARAR, 8, {"A"}, "karsilanmayan", dis).kayip.sum() == 1
    # boş süzgeç hiçbir hücre bırakmaz (None değil)
    bos = pd.DataFrame({"magaza_id": [], "urun_id": []})
    assert len(olcum.kayip_tablosu(kayip, KARAR, 8, {"A", "B"}, "karsilanmayan", bos)) == 0


def test_kategori_ve_str_tipleri_birlikte():
    # parquet/hakem tablosunda kimlikler category, evren str; süzgeç de category olabilir
    kayip = pd.DataFrame({
        "tarih": pd.to_datetime(["2025-12-30", "2025-12-30"]),
        "magaza_id": pd.Categorical(["A", "ONL"]),
        "urun_id": pd.Categorical(["OPT1-1", "OPT1-1"]),
        "karsilanmayan": pd.array([4, 9], dtype="int32")})
    hucreler = pd.DataFrame({"magaza_id": pd.Categorical(["A", "ONL"]),
                             "urun_id": pd.Categorical(["OPT1-1", "OPT1-1"])})
    tablo = olcum.kayip_tablosu(kayip, KARAR, 8, {"A"}, "karsilanmayan", hucreler)
    assert len(tablo) == 1 and tablo.kayip.iloc[0] == 4
    # çıktı düz metin: olc'un birleşimlerinde category uyuşmazlığı çıkmaz
    assert not isinstance(tablo.magaza_id.dtype, pd.CategoricalDtype)
    assert not isinstance(tablo.urun_id.dtype, pd.CategoricalDtype)
    sonuc = olc(_tasinan(("V", "A", "OPT1-1", 3)), tablo, _satis(("V", "OPT1-1", 3)))
    assert sonuc.kurtarilan == 3 and sonuc.yakalama == 0.75


def test_olc_kategori_girdisi():
    tasinan = _tasinan(("V", "A", "OPT1-1", 2))
    for kol in ("verici", "alici", "urun_id"):
        tasinan[kol] = tasinan[kol].astype("category")
    kayip = _kayip(("A", "OPT1-1", 5))
    kayip["magaza_id"] = kayip.magaza_id.astype("category")
    kayip["urun_id"] = kayip.urun_id.astype("category")
    satis = _satis(("V", "OPT1-1", 2))
    satis["magaza_id"] = satis.magaza_id.astype("category")
    sonuc = olc(tasinan, kayip, satis)
    assert sonuc.kurtarilan == 2 and sonuc.p_verici == 1.0


def test_p_araliklari():
    tasinan = _tasinan(("V1", "A", "OPT1-1", 6), ("V2", "B", "OPT1-2", 4), ("V2", "A", "OPT1-3", 2))
    kayip = _kayip(("A", "OPT1-1", 2), ("B", "OPT1-2", 9), ("C", "OPT1-1", 7))
    satis = _satis(("V1", "OPT1-1", 3), ("V2", "OPT1-2", 100), ("V2", "OPT1-3", 0))
    s = olc(tasinan, kayip, satis)
    assert 0 <= s.p_alici <= 1 and 0 <= s.p_verici <= 1 and 0 <= s.yakalama <= 1
    # elle: kurtarılan min(6,2)+min(4,9)+min(2,0)=6; payda 18; taşınan 12
    assert s.kurtarilan == 6 and s.payda == 18 and s.tasinan_adet == 12
    assert s.yakalama == pytest.approx(6 / 18) and s.p_alici == pytest.approx(0.5)
    # p_verici: min(6,3)+min(4,100)+min(2,0)=7 → 7/12
    assert s.p_verici == pytest.approx(7 / 12)


def test_iade_verici_satisini_eksiye_dusurmez():
    # net satış -2 (iade ağır bastı): verici payı 0'a kırpılır, negatif p_verici olmaz
    s = olc(_tasinan(("V", "A", "OPT1-1", 4)), _kayip(("A", "OPT1-1", 4)), _satis(("V", "OPT1-1", -2)))
    assert s.p_verici == 0.0 and s.kurtarilan == 4
    # satışı olmayan verici hücresi de (satış tablosunda satır yok) 0
    s = olc(_tasinan(("V", "A", "OPT1-1", 4)), _kayip(("A", "OPT1-1", 4)), _satis())
    assert s.p_verici == 0.0


def test_bos_plan_sifir():
    bos = pd.DataFrame(columns=["verici", "alici", "option_id", "urun_id", "adet"])
    s = olc(bos, _kayip(("A", "OPT1-1", 5)), _satis(("V", "OPT1-1", 9)))
    assert s == Olcum(tasinan_adet=0, kurtarilan=0.0, payda=5.0, yakalama=0.0, p_alici=0.0, p_verici=0.0)


def test_payda_sifir_yakalama_sifir():
    s = olc(_tasinan(("V", "A", "OPT1-1", 3)), _kayip(), _satis(("V", "OPT1-1", 3)))
    assert s.payda == 0 and s.yakalama == 0 and s.kurtarilan == 0 and s.p_alici == 0


def test_olcum_degismez():
    s = Olcum(1, 1.0, 2.0, 0.5, 1.0, 1.0)
    with pytest.raises(Exception):
        s.yakalama = 1.0


def test_tasinan_fiksturde(con):
    hareket = pd.DataFrame(
        [("MA", "MC", "OPT1", 12, 1.0), ("MB", "MD", "OPT1", 5, 1.0)], columns=HAREKET_KOL)
    t = olcum.tasinan(con, hareket, KARAR)
    assert list(t.columns) == ["verici", "alici", "option_id", "urun_id", "adet"]
    # MA-OPT1 karar günü: 3, 2, 3, 2, 2 (=12); MB-OPT1: 2, 0, 0, 0, 3 (=5) → sıfırlar düşer
    bekle = {("MA", "MC", "OPT1-1"): 3, ("MA", "MC", "OPT1-2"): 2, ("MA", "MC", "OPT1-3"): 3,
             ("MA", "MC", "OPT1-4"): 2, ("MA", "MC", "OPT1-5"): 2,
             ("MB", "MD", "OPT1-1"): 2, ("MB", "MD", "OPT1-5"): 3}
    assert {(v, a, u): n for v, a, _, u, n in t.itertuples(index=False)} == bekle
    assert t.adet.sum() == hareket.adet.sum()
    assert (t.option_id == "OPT1").all()


def test_tasinan_yalniz_karar_fotografi(con_ileri):
    # karar sonrası stok fotoğrafı (MB: 4'er) ve önceki haftalar sayılmaz
    hareket = pd.DataFrame([("MB", "MC", "OPT1", 5, 1.0)], columns=HAREKET_KOL)
    t = olcum.tasinan(con_ileri, hareket, KARAR)
    assert t.adet.sum() == 5 and set(t.urun_id) == {"OPT1-1", "OPT1-5"}


def test_tasinan_bos_hareket(con):
    t = olcum.tasinan(con, pd.DataFrame(columns=HAREKET_KOL), KARAR)
    assert len(t) == 0
    assert list(t.columns) == ["verici", "alici", "option_id", "urun_id", "adet"]


def test_verici_satisi_pencere_ici_net(con_ileri):
    con_ileri.execute("insert into satis values ('2026-01-06', 'MA', 'OPT1-3', -2)")    # iade, net düşer
    con_ileri.execute("insert into satis values ('2026-03-01', 'MA', 'OPT1-3', 50)")    # pencere dışı
    s = olcum.verici_satisi(con_ileri, KARAR, 2)       # [29 Aralık, 12 Ocak)
    assert list(s.columns) == ["magaza_id", "urun_id", "adet"]
    degerler = {(m, u): n for m, u, n in s.itertuples(index=False)}
    assert degerler == {("MA", "OPT1-3"): 7, ("MB", "OPT1-3"): 9}
    # pencere kısalınca (1 hafta: 5 Ocak dahil değil) hiçbir satır kalmaz
    assert len(olcum.verici_satisi(con_ileri, KARAR, 1)) == 0


def test_verici_satisi_evren_disi_yok(con_ileri):
    s = olcum.verici_satisi(con_ileri, KARAR, 8)
    assert not set(s.magaza_id) & {"ONL", "MF", "MG", "MH"}
