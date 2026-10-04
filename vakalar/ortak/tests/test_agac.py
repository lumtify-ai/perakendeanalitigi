"""agac.kaynak_ata: kayıp hücre-günlerin kaynak ağacı (spec §4.6)."""

import numpy as np
import pandas as pd
import pytest
from conftest import ekle, oyuncak_baglan, oyuncak_tablolar

from perakende_analitik import agac, ozellikler, stok

T = pd.Timestamp

# ------------------------------------------------------------------ senaryolar
# Temel senaryoya DOKUNULMAZ (R2); yeni SKU / mağazalarla eklenir. Yeni SKU'ların
# `urun` satırı gerekmez: ağaç yalnız sevkiyat, depo_stok ve siparişe bakar.
# M001 yol süresi 1 gün (temel), M008 2 gün (aşağıda eklenir).
#
# Çarşamba 2025-01-15 kaybı, yol 1: x = 01-14 (salı) -> fırsat pazartesi 01-13.

GUNLER = pd.date_range("2025-01-06", "2025-01-27", freq="D")


def _depo(t, urun: str, gunler: dict[str, int], varsayilan: int = 0) -> None:
    """depo_stok: 01-06 ... 01-27 günlük; `gunler` belirli günlerin adedini verir."""
    ekle(t, "depo_stok", [(g, urun, gunler.get(g.strftime("%Y-%m-%d"), varsayilan))
                          for g in GUNLER])


def _siparis(t, sid: str, urun: str, planlanan: str, gerceklesen, adet: int = 50) -> None:
    ekle(t, "siparis", [(sid, "rpt", urun.rsplit("-", 1)[0], urun, "T01", "2025-01-02",
                         planlanan, gerceklesen, adet)])


@pytest.fixture
def ag_con():
    t = oyuncak_tablolar()
    # M008: yol süresi 2 gün (en sık değer)
    ekle(t, "sevkiyat", [("2024-12-30", "2025-01-01", "DEPO", "M008", "AG-PLN", 5,
                          "ilk_dagitim", "PKT01")])

    # hikâye: depo boş, sipariş 01-08 planlı, 01-14 gerçekleşen (fırsattan sonraki gece)
    _depo(t, "AG-TED", {"2025-01-15": 50, "2025-01-16": 50, "2025-01-17": 50}, 0)
    _siparis(t, "S1", "AG-TED", "2025-01-08", "2025-01-14")
    # depoda mal var
    _depo(t, "AG-ALL", {}, 20)
    # depo fırsat sabahı boş ama o gün tedarikçi teslimi girdi (motor: teslim önce)
    _depo(t, "AG-AYNI", {}, 0)
    _siparis(t, "S2", "AG-AYNI", "2025-01-06", "2025-01-13", 30)
    # hiçbir şey yok
    _depo(t, "AG-PLN", {}, 0)
    # gerçekleşen teslim boş (pencereden sonra)
    _depo(t, "AG-NULL", {}, 0)
    _siparis(t, "S3", "AG-NULL", "2025-01-10", None)
    # planlanan teslim fırsattan sonra
    _depo(t, "AG-SONRA", {}, 0)
    _siparis(t, "S4", "AG-SONRA", "2025-01-14", "2025-01-16", 5)
    # sipariş fırsattan önce gelmiş (depo yine de boş)
    _depo(t, "AG-ONCE", {}, 0)
    _siparis(t, "S5", "AG-ONCE", "2025-01-03", "2025-01-10")
    # lojistik: depoda mal var ama sevk geç varıyor (yol 1: beklenen varış 01-11)
    _depo(t, "AG-LOJ", {}, 20)
    ekle(t, "sevkiyat", [("2025-01-10", "2025-01-14", "DEPO", "M001", "AG-LOJ", 4,
                          "replenishment", None)])
    # kirli tek taraflı transfer: varış boş -> lojistik değil
    _depo(t, "AG-ELLE", {}, 0)
    ekle(t, "sevkiyat", [("2025-01-10", None, "M002", "M001", "AG-ELLE", 2,
                          "elle_transfer", None)])
    # rota M002 -> M001 her zaman 3 gün sürer (3 sevk); AG-R5 sevki bir kez 5 gün sürer.
    # Mağazalar arası rotanın beklenen süresi o rotanın en sık değeridir (R19), depo yolu değil
    for u in ("AG-R3", "AG-R3B", "AG-R3C", "AG-R5"):
        _depo(t, u, {}, 20)
    ekle(t, "sevkiyat", [
        ("2025-01-08", "2025-01-11", "M002", "M001", "AG-R3", 1, "elle_transfer", None),
        ("2025-01-08", "2025-01-11", "M002", "M001", "AG-R3B", 1, "elle_transfer", None),
        ("2025-01-08", "2025-01-11", "M002", "M001", "AG-R3C", 1, "elle_transfer", None),
        ("2025-01-08", "2025-01-13", "M002", "M001", "AG-R5", 1, "elle_transfer", None)])
    # online
    _depo(t, "AG-ONL", {}, 20)
    _depo(t, "AG-ONLT", {}, 0)
    _siparis(t, "S6", "AG-ONLT", "2025-01-10", "2025-01-16")
    con = oyuncak_baglan(t)
    yield con
    con.close()


def satirlar(*girdiler, indeks=None, kategori=True) -> pd.DataFrame:
    """Kayıp tablosu: (tarih, magaza, urun) demetlerinden, şemalı satırlar."""
    n = len(girdiler)
    df = pd.DataFrame({
        "tarih": pd.to_datetime([g[0] for g in girdiler]).astype("datetime64[ns]"),
        "magaza_id": pd.Series([g[1] for g in girdiler], dtype=object),
        "urun_id": pd.Series([g[2] for g in girdiler], dtype=object),
        "option_id": pd.Series([g[2].rsplit("-", 1)[0] for g in girdiler], dtype=object),
        "satis_oncesi": np.zeros(n, dtype="int32"),
        "brut_satis": np.zeros(n, dtype="int32"),
        "net_satis": np.zeros(n, dtype="int32"),
        "durum": pd.Categorical(["bos"] * n, categories=stok.DURUMLAR),
        "tahmini_talep": np.ones(n),
        "kayip": np.ones(n),
        "kayip_saf": np.ones(n),
        "satis": np.zeros(n, dtype="int32"),
    })
    if kategori:
        df["magaza_id"] = df["magaza_id"].astype("category")
        df["urun_id"] = df["urun_id"].astype("category")
    if indeks is not None:
        df.index = indeks
    return df


def kaynak_of(con, d, m, u) -> str:
    return str(agac.kaynak_ata(satirlar((d, m, u)), con).kaynak.iloc[0])


# ------------------------------------------------------------------ dallar

def test_dallar_sabiti():
    assert agac.DALLAR == ("lojistik", "magaza", "allocation", "tedarik", "planlama",
                           "bilinmiyor")


def test_onceki_gece_giren_mal_allocation_degil(ag_con):
    # M001 yol süresi 1; kayıp 2025-01-15 (çarşamba) -> fırsat pazartesi 2025-01-13;
    # depo fırsatta boş; sipariş planlanan 01-08, gerçekleşen 01-14 (önceki gece)
    sonuc = agac.kaynak_ata(satirlar(("2025-01-15", "M001", "AG-TED")), ag_con)
    assert sonuc.kaynak.iloc[0] == "tedarik"
    assert sonuc.firsat.iloc[0] == T("2025-01-13")


def test_allocation_firsatta_depoda_mal_var(ag_con):
    assert kaynak_of(ag_con, "2025-01-15", "M001", "AG-ALL") == "allocation"


def test_ayni_gun_tedarikci_teslimi_allocation(ag_con):
    # depo_stok sabah fotoğrafı 0, ama teslim 01-13'te replenishment'tan ÖNCE girer
    assert kaynak_of(ag_con, "2025-01-15", "M001", "AG-AYNI") == "allocation"


def test_tedarik_teslim_bos(ag_con):
    assert kaynak_of(ag_con, "2025-01-15", "M001", "AG-NULL") == "tedarik"


def test_planlama_hicbir_siparis_yok(ag_con):
    assert kaynak_of(ag_con, "2025-01-15", "M001", "AG-PLN") == "planlama"


def test_planlama_siparis_firsattan_sonra_planlanmis(ag_con):
    assert kaynak_of(ag_con, "2025-01-15", "M001", "AG-SONRA") == "planlama"


def test_planlama_siparis_firsattan_once_gelmis(ag_con):
    assert kaynak_of(ag_con, "2025-01-15", "M001", "AG-ONCE") == "planlama"


def test_lojistik_gec_varan_sevk(ag_con):
    # beklenen varış 01-10 + 1 = 01-11, gerçek varış 01-14: 01-11 <= d < 01-14
    for d in ("2025-01-11", "2025-01-12", "2025-01-13"):
        assert kaynak_of(ag_con, d, "M001", "AG-LOJ") == "lojistik", d
    # pencerenin dışı: sevk henüz beklenmiyor / varmış / başka mağaza
    assert kaynak_of(ag_con, "2025-01-10", "M001", "AG-LOJ") == "allocation"
    assert kaynak_of(ag_con, "2025-01-14", "M001", "AG-LOJ") == "allocation"
    assert kaynak_of(ag_con, "2025-01-12", "M002", "AG-LOJ") == "allocation"


def test_lojistik_allocation_ve_tedarikten_once(ag_con):
    # AG-LOJ depoda mal var (allocation olurdu); lojistik önce tutar
    assert kaynak_of(ag_con, "2025-01-13", "M001", "AG-LOJ") == "lojistik"


def test_magazalar_arasi_rota_hep_ayni_surede_gelirse_lojistik_degil(ag_con):
    # M002 -> M001 rotası her zaman 3 gün: depo yolu (1) ile kıyaslanırsa "geç" görünürdü
    for d in ("2025-01-08", "2025-01-09", "2025-01-10", "2025-01-11", "2025-01-12"):
        assert kaynak_of(ag_con, d, "M001", "AG-R3") == "allocation", d


def test_magazalar_arasi_rota_bir_kez_uzarsa_lojistik(ag_con):
    # aynı rota bir kez 5 gün sürdü (en sık değer 3): 01-08 + 3 = 01-11 <= d < 01-13
    for d in ("2025-01-11", "2025-01-12"):
        assert kaynak_of(ag_con, d, "M001", "AG-R5") == "lojistik", d
    for d in ("2025-01-08", "2025-01-10", "2025-01-13"):
        assert kaynak_of(ag_con, d, "M001", "AG-R5") == "allocation", d


def test_tek_tarafli_transfer_lojistik_degil(ag_con):
    # varis_tarihi boş: veri hatası, geç varan sevk sayılmaz
    assert kaynak_of(ag_con, "2025-01-12", "M001", "AG-ELLE") == "planlama"


def test_magaza_dali_hic_dolmaz(ag_con):
    g = satirlar(*[(d, m, u) for d in ("2025-01-12", "2025-01-13", "2025-01-15")
                   for m in ("M001", "M002", "M008", "ONL")
                   for u in ("AG-TED", "AG-ALL", "AG-PLN", "AG-LOJ", "AG-ELLE")])
    assert "magaza" not in set(agac.kaynak_ata(g, ag_con).kaynak.astype(str))


def test_pencere_basinda_bilinmiyor(ag_con):
    # mağaza: fırsat 2023-01-01'den önce
    #   pazar 2023-01-01 -> x = 2022-12-31 -> fırsat 2022-12-26
    #   pazartesi 2023-01-02 (yol 1: x = 01-01 pazar) -> fırsat 2022-12-26
    #   salı 2023-01-03 -> x = 01-02 pazartesi -> fırsat 2023-01-02 (bilinir)
    g = satirlar(("2023-01-01", "M001", "AG-ALL"), ("2023-01-02", "M001", "AG-ALL"),
                 ("2023-01-03", "M001", "AG-ALL"), ("2023-01-01", "ONL", "AG-ALL"))
    s = agac.kaynak_ata(g, ag_con)
    assert list(s.kaynak.astype(str)) == ["bilinmiyor", "bilinmiyor", "planlama", "planlama"]
    assert list(s.firsat) == [T("2022-12-26"), T("2022-12-26"), T("2023-01-02"),
                              T("2023-01-01")]


def test_lojistik_bilinmiyorun_onunde_gelir():
    t = oyuncak_tablolar()
    ekle(t, "sevkiyat", [("2022-12-29", "2023-01-03", "DEPO", "M001", "AG-X", 3,
                          "replenishment", None)])
    con = oyuncak_baglan(t)
    # beklenen varış 2022-12-30, gerçek 2023-01-03; d = 2023-01-01 fırsatı 2022-12-26
    assert kaynak_of(con, "2023-01-01", "M001", "AG-X") == "lojistik"
    con.close()


# ------------------------------------------------------------------ fırsat

def test_firsat_son_pazartesi_ve_magaza_yolu(ag_con):
    # M001 yol 1: x = d - 1. M008 yol 2: x = d - 2.
    beklenen = [
        ("2025-01-13", "M001", "2025-01-06"),  # pzt: x = pazar -> önceki pazartesi
        ("2025-01-14", "M001", "2025-01-13"),  # salı: x = pazartesi
        ("2025-01-15", "M001", "2025-01-13"),
        ("2025-01-19", "M001", "2025-01-13"),  # pazar
        ("2025-01-20", "M001", "2025-01-13"),  # pzt: x = pazar
        ("2025-01-14", "M008", "2025-01-06"),  # yol 2: x = pazar
        ("2025-01-15", "M008", "2025-01-13"),  # yol 2: x = pazartesi
        ("2025-01-15", "ONL", "2025-01-15"),   # online: fırsat = d
    ]
    s = agac.kaynak_ata(satirlar(*[(d, m, "AG-PLN") for d, m, _ in beklenen]), ag_con)
    assert list(s.firsat) == [T(f) for _, _, f in beklenen]


def test_online_allocation_dali_yok(ag_con):
    # depo dolu: mağazada allocation olurdu, online'da değil
    assert kaynak_of(ag_con, "2025-01-15", "M001", "AG-ALL") == "allocation"
    s = agac.kaynak_ata(satirlar(("2025-01-15", "ONL", "AG-ALL")), ag_con)
    assert s.kaynak.iloc[0] == "planlama"
    assert s.firsat.iloc[0] == T("2025-01-15")


def test_online_tedarik_firsat_ayni_gun(ag_con):
    # planlanan 01-10 <= d = 01-15, gerçekleşen 01-16 > d
    assert kaynak_of(ag_con, "2025-01-15", "ONL", "AG-ONLT") == "tedarik"
    # online'da planlanan = d de tedarik (S4: planlanan 01-14, gerçekleşen 01-16)
    assert kaynak_of(ag_con, "2025-01-14", "ONL", "AG-SONRA") == "tedarik"
    # d = gerçekleşen teslim günü: artık gecikme yok
    assert kaynak_of(ag_con, "2025-01-16", "ONL", "AG-ONLT") == "planlama"


# ------------------------------------------------------------------ sözleşme

def test_cikti_sozlesmesi(ag_con):
    g = satirlar(("2025-01-15", "M001", "AG-ALL"), ("2025-01-15", "M001", "AG-PLN"),
                 ("2025-01-15", "M001", "AG-TED"), ("2025-01-12", "M001", "AG-LOJ"),
                 indeks=pd.Index([40, 7, 22, 3]))
    kopya = g.copy()
    s = agac.kaynak_ata(g, ag_con)
    pd.testing.assert_frame_equal(g, kopya)                 # girdi değişmez
    assert list(s.index) == [40, 7, 22, 3]                  # sıra ve indeks korunur
    assert list(s.columns) == list(g.columns) + ["kaynak", "firsat"]
    for c in g.columns:
        pd.testing.assert_series_equal(s[c], g[c])
    assert isinstance(s.kaynak.dtype, pd.CategoricalDtype)
    assert list(s.kaynak.cat.categories) == list(agac.DALLAR)
    assert s.firsat.dtype == np.dtype("datetime64[ns]")
    assert list(s.kaynak.astype(str)) == ["allocation", "planlama", "tedarik", "lojistik"]


def test_duz_metin_kimlikler_ayni_sonuc(ag_con):
    girdiler = [("2025-01-15", "M001", "AG-ALL"), ("2025-01-15", "ONL", "AG-ONLT"),
                ("2025-01-15", "M001", "AG-TED")]
    a = agac.kaynak_ata(satirlar(*girdiler, kategori=True), ag_con)
    b = agac.kaynak_ata(satirlar(*girdiler, kategori=False), ag_con)
    assert list(a.kaynak.astype(str)) == list(b.kaynak.astype(str))
    assert list(a.firsat) == list(b.firsat)


def test_bos_girdi(ag_con):
    s = agac.kaynak_ata(satirlar(), ag_con)
    assert len(s) == 0
    assert list(s.kaynak.cat.categories) == list(agac.DALLAR)
    assert s.firsat.dtype == np.dtype("datetime64[ns]")


def test_yol_suresi_bilinmeyen_magaza_medyan_kullanir(ag_con):
    # M099 hiç depo sevki almamış; bilinen yolların (1, 1, 2) üst medyanı 1 kullanılır
    assert "M099" not in ozellikler.yol_suresi(ag_con)
    s = agac.kaynak_ata(satirlar(("2025-01-14", "M099", "AG-PLN")), ag_con)
    assert s.firsat.iloc[0] == T("2025-01-13")


# ------------------------------------------------- yavaş referansla rastgele eşleşme

def _referans(con, d, m, u) -> tuple[str, pd.Timestamp | None]:
    """Spec §4.6'nın satır satır, düz Python karşılığı."""
    yol = ozellikler.yol_suresi(con)
    ay = sorted(yol.values())[len(yol) // 2]
    sevk = con.execute("select tarih, varis_tarihi, kaynak from sevkiyat where hedef = ? "
                       "and urun_id = ?", [m, u]).fetchall()
    y = yol.get(m, ay)
    if m != "ONL":
        for tarih, varis, kay in sevk:
            if varis is None:
                continue
            sureler = con.execute(
                "select date_diff('day', tarih::date, varis_tarihi::date) g from sevkiyat "
                "where kaynak = ? and hedef = ? and varis_tarihi is not null "
                "group by g order by count(*) desc, g", [kay, m]).fetchone()
            beklenen = sureler[0] if sureler else y
            if tarih + pd.Timedelta(days=beklenen) <= d < varis:
                return "lojistik", None
    x = d if m == "ONL" else d - pd.Timedelta(days=y)
    f = x if m == "ONL" else x - pd.Timedelta(days=x.weekday())
    if f < T("2023-01-01"):
        return "bilinmiyor", f
    if m != "ONL":
        dep = con.execute("select coalesce(sum(adet), 0) from depo_stok where urun_id = ? "
                          "and tarih = ?", [u, f]).fetchone()[0]
        gel = con.execute("select coalesce(sum(adet), 0) from siparis where urun_id = ? "
                          "and gerceklesen_teslim = ?", [u, f]).fetchone()[0]
        if dep + gel > 0:
            return "allocation", f
    n = con.execute("select count(*) from siparis where urun_id = ? and planlanan_teslim <= ? "
                    "and (gerceklesen_teslim is null or gerceklesen_teslim > ?)",
                    [u, f, f]).fetchone()[0]
    return ("tedarik" if n else "planlama"), f


def test_rastgele_satirlar_referansla_ayni(ag_con):
    rng = np.random.default_rng(7)
    magazalar = ["M001", "M002", "M008", "ONL"]
    urunler = ["AG-TED", "AG-ALL", "AG-AYNI", "AG-PLN", "AG-NULL", "AG-SONRA", "AG-ONCE",
               "AG-LOJ", "AG-ELLE", "AG-ONL", "AG-ONLT", "AG-R3", "AG-R5"]
    gunler = list(pd.date_range("2025-01-06", "2025-01-26")) + [T("2023-01-01"), T("2023-01-03")]
    girdiler = [(gunler[rng.integers(len(gunler))], magazalar[rng.integers(4)],
                 urunler[rng.integers(len(urunler))]) for _ in range(600)]
    s = agac.kaynak_ata(satirlar(*girdiler), ag_con)
    for (d, m, u), k, f in zip(girdiler, s.kaynak.astype(str), s.firsat):
        kk, ff = _referans(ag_con, d, m, u)
        assert k == kk, (d, m, u)
        if kk != "lojistik":
            assert f == ff, (d, m, u)


# ------------------------------------------------------------------ gerçek veri

@pytest.mark.veri
def test_gercek_v4_bir_gun_dagilimi(v4_con):
    gun = pd.Timestamp("2025-03-05").date()
    g = stok.gunluk_magaza(v4_con, gun, gun)
    g = g[g["durum"] != "stoklu"].head(50_000).copy()
    g["tahmini_talep"] = 1.0
    g["kayip"] = 1.0
    g["kayip_saf"] = 1.0
    g["satis"] = g["brut_satis"]
    s = agac.kaynak_ata(g, v4_con)
    dag = s.kaynak.value_counts()
    assert dag.get("magaza", 0) == 0 and dag.get("lojistik", 0) == 0
    assert dag.sum() == len(g)
    assert (s.firsat <= s.tarih).all()
