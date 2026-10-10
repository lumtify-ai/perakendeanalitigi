"""`replenishment.ihtiyac`: kural öngörüsü, güvenlik stoku, özel gün katsayıları,
beden payı ve bedene bölme (v4: `[gun, C]` matris + `kaynak.Harita`).

Oyuncak dünya (`_dunya`): iki fiziksel mağaza (M0, M1) ve ONL. Dört option:
o0 Üst Giyim 5 beden, o1 Alt Giyim 5 beden, o2 Aksesuar tek beden (STD),
o3 Üst Giyim 5 beden (o0 ile aynı beden seti). M1'de o0'ın 5. bedeni çeşit
dışıdır (hücresi yok). Hücreler mağaza, SKU sırasıyla; gerçek (küçük ölçekli)
v4 dünyası da birkaç testte kullanılır.
"""

import dataclasses
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from replenishment import ihtiyac, kaynak
from replenishment.ihtiyac import GuvenlikStoku

EGRI = np.array([0.1, 0.2, 0.4, 0.2, 0.1])
OPTION_BEDEN = [5, 5, 1, 5]                       # o0..o3
KATEGORI = ["Üst Giyim", "Alt Giyim", "Aksesuar", "Üst Giyim"]
SET = ["Kadın Harf", "Kadın Numara", "Standart", "Kadın Harf"]

BAS = pd.Timestamp("2025-01-06")                   # pazartesi = satır 0
N = 400


def _dunya():
    sku_option = np.repeat(np.arange(4), OPTION_BEDEN)
    sku_beden = np.concatenate([np.arange(1, b + 1) for b in OPTION_BEDEN])
    sku_payi = np.concatenate([EGRI if b == 5 else np.ones(1) for b in OPTION_BEDEN])
    hm, hs = [], []
    for m in (0, 1, 2):                            # 2 = ONL
        for s in range(len(sku_option)):
            if m == 1 and s == 4:                  # M1'de o0'ın 5. bedeni yok
                continue
            hm.append(m)
            hs.append(s)
    hm, hs = np.array(hm), np.array(hs)
    return SimpleNamespace(
        hucre_magaza=hm, hucre_sku=hs, hucre_option=sku_option[hs], hucre_online=hm == 2,
        sku_option=sku_option, sku_beden_payi=sku_payi,
        optionlar=pd.DataFrame({"line": ["Collection"] * 4, "ust_kategori": KATEGORI, "beden_seti": SET}),
        urunler=pd.DataFrame({"beden_sira": sku_beden}),
    )


@pytest.fixture(scope="module")
def d():
    w = _dunya()
    return w, kaynak.harita_kur(w)


def takvim(tatiller=(), n=N, bas=BAS, bf=()):
    """`bf` günleri de `tatil_mi`dir (v4 takvimi: BF cuması tatil sayılır)."""
    t = pd.DataFrame({"tarih": pd.date_range(bas, periods=n, freq="D")})
    gunler = t["tarih"].dt.strftime("%Y-%m-%d")
    t["tatil_mi"] = gunler.isin(list(tatiller) + list(bf)).to_numpy()
    t["black_friday_mi"] = gunler.isin(list(bf)).to_numpy()
    return t


def gun(t, tarih):
    return int(np.flatnonzero(t["tarih"] == pd.Timestamp(tarih))[0])


def oc(h, magaza, option):
    return int(np.flatnonzero((h.oc_magaza == magaza) & (h.oc_option == option))[0])


def hucreler(h, magaza, option):
    return np.flatnonzero((h.hucre_magaza == magaza) & (h.hucre_option == option))


def sifir(h):
    return np.zeros((N, len(h.oc)), dtype=np.int32)


# ------------------------------------------------------------ hafta katsayısı


def test_hafta_katsayisi_oran_olarak():
    t = takvim(["2025-10-29"])                     # çarşamba tatil
    k = gun(t, "2025-10-27")                       # pazartesi
    assert ihtiyac.hafta_katsayisi(t, k, 1.35) == pytest.approx((6 + 1.35) / 7)


def test_hafta_katsayisi_gecen_haftada_tatil_varsa_duser():
    t = takvim(["2025-10-29"])
    k = gun(t, "2025-11-03")                       # gözlem haftası (27 Eki–2 Kas) 29 Ekim'i içerir
    assert ihtiyac.hafta_katsayisi(t, k, 1.35) == pytest.approx(7 / (6 + 1.35))


def test_hafta_katsayisi_karar_gununun_kendisi_gozlem_haftasina_girmez():
    t = takvim(["2025-10-27"])                     # tatil tam karar günü
    k = gun(t, "2025-10-27")
    assert ihtiyac.hafta_katsayisi(t, k, 1.35) == 1.0       # ne payda ne paydır


def test_hafta_katsayisi_black_friday_ayri_katsayi():
    t = takvim(["2025-11-26"], bf=["2025-11-28"])  # çarşamba tatil, cuma BF
    k = gun(t, "2025-11-24")
    assert ihtiyac.hafta_katsayisi(t, k, 0.6, 3.5) == pytest.approx((5 + 0.6 + 3.5) / 7)
    assert ihtiyac.hafta_katsayisi(t, k, 0.6) == pytest.approx((6 + 0.6) / 7)   # BF katsayısı yoksa 1


def test_hafta_katsayisi_takvim_yetmezse_hata():
    t = takvim(n=100)
    with pytest.raises(ValueError, match="takvim"):
        ihtiyac.hafta_katsayisi(t, 95, 1.0)


# ----------------------------------------------------------- haftalık bloklar


def test_haftalik_bloklari_dogru_toplar(d):
    _, h = d
    satis = sifir(h)
    k = gun(takvim(), "2025-09-08")
    satis[k - 7 : k, hucreler(h, 0, 0)] = 1       # [k−7, k−1]: 5 beden × 7 gün
    sonuc = ihtiyac.haftalik(satis, h, k, hafta=2)
    assert sonuc.shape == (2, len(h.oc_magaza))
    assert sonuc[1, oc(h, 0, 0)] == 35
    assert sonuc[0, oc(h, 0, 0)] == 0
    assert sonuc[1, oc(h, 1, 0)] == 0              # başka OC


def test_haftalik_karar_gunu_ve_sonrasi_sayilmaz(d):
    _, h = d
    satis = sifir(h)
    satis[100:, :] = 7
    assert (ihtiyac.haftalik(satis, h, 100, hafta=3) == 0).all()


def test_haftalik_veri_basindan_once_sifir(d):
    _, h = d
    satis = sifir(h)
    satis[360:, :] = 100                           # yıl sonuna sahte büyük satış
    sonuc = ihtiyac.haftalik(satis, h, 12, hafta=3)
    assert (sonuc[0] == 0).all()                   # en eski blok veri başından önceye taşar; sondan sızmaz


# ------------------------------------------------------------ özel gün katsayısı


def _tatilli(h_gun=200):
    t = takvim()
    t["tatil_mi"] = False
    t.loc[h_gun, "tatil_mi"] = True
    return t


def test_ozel_gun_katsayisi_oran_hesaplar(d):
    _, h = d
    t = _tatilli()
    satis = sifir(h)
    hg = t["tarih"].dt.weekday.to_numpy()
    aday = np.flatnonzero((hg == hg[200]) & (np.abs(np.arange(N) - 200) <= 14) & ~t["tatil_mi"].to_numpy())
    c = hucreler(h, 0, 0)[0]                       # tek hücre, Üst Giyim
    satis[aday, c] = 10
    satis[200, c] = 40
    k = ihtiyac.ozel_gun_katsayilari(satis, h, t, bit_gunu=300)
    assert k["Üst Giyim"] == pytest.approx(4.0)
    assert set(k) == {"Üst Giyim"}                 # satışsız kategoriler (payda 0) yok


def test_ozel_gun_katsayisi_black_friday_tatile_karismaz(d):
    _, h = d
    t = takvim(bf=[])
    t.loc[[200, 270], "tatil_mi"] = True           # 200 resmî tatil, 270 BF
    t.loc[270, "black_friday_mi"] = True
    hg = t["tarih"].dt.weekday.to_numpy()
    ozel = t["tatil_mi"].to_numpy()
    c = hucreler(h, 0, 0)[0]
    satis = sifir(h)
    for olay, oran in ((200, 0.6), (270, 3.5)):
        aday = [g for g in range(olay - 14, olay + 15) if hg[g] == hg[olay] and not ozel[g]]
        satis[aday, c], satis[olay, c] = 10, 10 * oran
    k = ihtiyac.ozel_gun_katsayilari(satis, h, t, 330)
    assert k["Üst Giyim"] == pytest.approx(0.6) and k["Üst Giyim" + ihtiyac.BF_SONEKI] == pytest.approx(3.5)
    assert all(type(a) is str for a in k)


def test_ozel_gun_katsayisi_yalniz_fiziksel(d):
    _, h = d
    t = _tatilli()
    satis = sifir(h)
    hg = t["tarih"].dt.weekday.to_numpy()
    aday = np.flatnonzero((hg == hg[200]) & (np.abs(np.arange(N) - 200) <= 14) & ~t["tatil_mi"].to_numpy())
    c, onl = hucreler(h, 0, 0)[0], hucreler(h, 2, 0)[0]
    satis[aday, c], satis[200, c] = 10, 40
    satis[aday, onl], satis[200, onl] = 10, 1000   # online tatil günü patlar; katsayıya girmez
    assert ihtiyac.ozel_gun_katsayilari(satis, h, t, 300)["Üst Giyim"] == pytest.approx(4.0)


def test_ozel_gun_katsayisi_gelecekteki_tatili_yoksayar(d):
    _, h = d
    satis = sifir(h)
    satis[200, hucreler(h, 0, 0)[0]] = 999
    assert ihtiyac.ozel_gun_katsayilari(satis, h, _tatilli(), bit_gunu=200) == {}


def test_ozel_gun_katsayisi_pencere_bit_gununu_asmaz(d):
    _, h = d
    t = _tatilli()
    satis = sifir(h)
    bit = 205                                       # h'nin +14 penceresi (214'e kadar) bit_gunu'nü aşar
    hg = t["tarih"].dt.weekday.to_numpy()
    tum = np.arange(186, 215)
    aday = tum[(hg[tum] == hg[200]) & ~t["tatil_mi"].to_numpy()[tum]]
    gecmis, gelecek = aday[aday < bit], aday[aday >= bit]
    assert gecmis.size > 0 and gelecek.size > 0
    c = hucreler(h, 0, 0)[0]
    satis[gecmis, c], satis[gelecek, c], satis[200, c] = 10, 1000, 40
    assert ihtiyac.ozel_gun_katsayilari(satis, h, t, bit)["Üst Giyim"] == pytest.approx(4.0)


def test_ozel_gun_katsayisi_pencere_bossa_kategori_yok(d):
    _, h = d
    t = _tatilli(5)
    satis = sifir(h)
    satis[5, hucreler(h, 0, 0)[0]] = 999
    assert ihtiyac.ozel_gun_katsayilari(satis, h, t, bit_gunu=6) == {}


def test_ozel_gun_katsayisi_bit_gunu_veriyi_asarsa_hata(d):
    _, h = d
    with pytest.raises(ValueError, match="bit_gunu"):
        ihtiyac.ozel_gun_katsayilari(sifir(h), h, takvim(), bit_gunu=N + 1)


# ----------------------------------------------------------- güvenlik stoku


def test_sabit_ailesi_degeri_sabit_dondurur(d):
    _, h = d
    ss = ihtiyac.guvenlik_stoku(sifir(h), h, 250, GuvenlikStoku("sabit", 3.0))
    assert (ss == 3.0).all() and ss.shape == (len(h.oc_magaza),)


def test_ros_ailesi_son_28_gun_ortalamasi_carpi_gun(d):
    _, h = d
    satis = sifir(h)
    k = 250
    satis[k - 28 : k, hucreler(h, 0, 0)] = 1       # 28 gün × 5 beden × 1
    ss = ihtiyac.guvenlik_stoku(satis, h, k, GuvenlikStoku("ros", 4.0))
    assert ss[oc(h, 0, 0)] == pytest.approx(20.0)  # (140/28) × 4
    assert ss[oc(h, 1, 0)] == 0


def test_ros_ailesi_stoklu_gune_bolunur(d):
    _, h = d
    k = 250
    satis = sifir(h)
    satis[k - 1, hucreler(h, 0, 0)[2]] = 14
    stoklu = np.zeros(satis.shape, bool)
    stoklu[k - 7 : k] = True                       # 28 günün 7'si stoklu
    ayar = GuvenlikStoku("ros", 2)
    i = oc(h, 0, 0)
    assert ihtiyac.guvenlik_stoku(satis, h, k, ayar)[i] == pytest.approx(14 / 28 * 2)
    assert ihtiyac.guvenlik_stoku(satis, h, k, ayar, stoklu)[i] == pytest.approx(14 / 7 * 2)


def test_istatistik_ailesi_sifir_gecmiste_sifir(d):
    _, h = d
    ss = ihtiyac.guvenlik_stoku(sifir(h), h, 243, GuvenlikStoku("istatistik"))
    assert (ss == 0).all() and not np.isnan(ss).any()


def test_istatistik_ailesi_haftalik_toplamin_std_si(d):
    _, h = d
    satis = sifir(h)
    k = 250
    haftalar = [3, 5, 4, 8, 2, 6, 7, 1]            # en eskiden en yeniye, tek hücrede
    c = hucreler(h, 1, 1)[0]
    for i, v in enumerate(haftalar):
        satis[k - 7 * (8 - i), c] = v
    ss = ihtiyac.guvenlik_stoku(satis, h, k, GuvenlikStoku("istatistik"))
    assert ss[oc(h, 1, 1)] == pytest.approx(1.65 * np.std(haftalar, ddof=1))


def test_bilinmeyen_aile_hata(d):
    _, h = d
    with pytest.raises(ValueError, match="Bilinmeyen"):
        ihtiyac.guvenlik_stoku(sifir(h), h, 250, GuvenlikStoku("x"))   # type: ignore[arg-type]


# ------------------------------------------------------------- kural öngörüsü


def test_kural_ongorusu_son_hafta_carpi_katsayi(d):
    _, h = d
    t = takvim(["2025-10-29"])
    k = gun(t, "2025-10-27")
    satis = sifir(h)
    satis[k - 7 : k, hucreler(h, 0, 0)] = 2        # 5 beden × 7 gün × 2 = 70
    o = ihtiyac.kural_ongorusu(satis, h, k, {"Üst Giyim": 1.2}, takvim=t)
    assert o[oc(h, 0, 0)] == pytest.approx(70 * ihtiyac.hafta_katsayisi(t, k, 1.2))
    assert o[oc(h, 1, 0)] == 0


def test_kural_ongorusu_black_friday_katsayisi(d):
    _, h = d
    t = takvim(bf=["2025-11-28"])
    k = gun(t, "2025-11-24")
    satis = sifir(h)
    satis[k - 7 : k, hucreler(h, 0, 0)] = 2
    o = ihtiyac.kural_ongorusu(satis, h, k, {"Üst Giyim|black_friday": 3.0}, takvim=t)
    assert o[oc(h, 0, 0)] == pytest.approx(70 * (6 + 3.0) / 7)


def test_kural_ongorusu_kategori_katsayisi_uygulanir_yoksa_bir(d):
    _, h = d
    t = takvim(["2025-10-29"])
    k = gun(t, "2025-10-27")
    satis = sifir(h)
    for opt in (0, 1):                             # Üst Giyim ve Alt Giyim, aynı satış
        satis[k - 7 : k, hucreler(h, 0, opt)] = 2
    o = ihtiyac.kural_ongorusu(satis, h, k, {"Üst Giyim": 1.2}, takvim=t)
    assert o[oc(h, 0, 0)] == pytest.approx(70 * (6 + 1.2) / 7)
    assert o[oc(h, 0, 1)] == pytest.approx(70.0)   # katsayısı yok: 1 (hafta katsayısı da 1)


def test_oc_hafta_katsayisi_kural_ongorusunun_carpani(d):
    """Çiftin hafta katsayısı kategorisinden; kural öngörüsü = son 7 gün × bu çarpan
    (karar anı Basit'inin ham 7 gününü aynı haftaya taşımak için de kullanılır)."""
    _, h = d
    t = takvim(["2025-10-29"], bf=["2025-11-28"])
    k = gun(t, "2025-10-27")
    kat = {"Üst Giyim": 1.2, "Alt Giyim|black_friday": 3.0}
    c = ihtiyac.oc_hafta_katsayisi(h, t, k, kat)
    assert c.shape == (len(h.oc_magaza),)
    assert c[oc(h, 0, 0)] == pytest.approx(ihtiyac.hafta_katsayisi(t, k, 1.2))
    assert c[oc(h, 1, 3)] == pytest.approx(ihtiyac.hafta_katsayisi(t, k, 1.2))   # aynı kategori
    assert c[oc(h, 0, 1)] == pytest.approx(1.0)                                   # BF bu hafta değil
    satis = sifir(h)
    satis[k - 7 : k] = 1
    assert np.allclose(ihtiyac.kural_ongorusu(satis, h, k, kat, takvim=t),
                       ihtiyac.haftalik(satis, h, k, 1)[0] * c)


def test_kural_ongorusu_karar_gunu_dahil_degil(d):
    _, h = d
    satis = sifir(h)
    satis[250, :] = 5                              # yalnız karar günü
    assert (ihtiyac.kural_ongorusu(satis, h, 250, {}, takvim=takvim()) == 0).all()


def test_sansur_duzeltmesi_stoklu_gunle(d):
    _, h = d
    k = 250
    satis = sifir(h)
    c = hucreler(h, 0, 0)[2]
    satis[[k - 3, k - 2, k - 1], c] = 2            # 3 stoklu günde 6 adet
    stoklu = np.zeros(satis.shape, bool)
    stoklu[k - 3 : k] = True
    o = ihtiyac.kural_ongorusu(satis, h, k, {}, stoklu, takvim=takvim())
    duz = ihtiyac.kural_ongorusu(satis, h, k, {}, takvim=takvim())
    assert duz[oc(h, 0, 0)] == pytest.approx(6.0)  # takvim haftası
    assert o[oc(h, 0, 0)] == pytest.approx(14.0)   # günlük 2 × 7
    assert o[oc(h, 0, 3)] == 0                     # satmayan OC yine 0


def test_stoklu_gun_oc_icin_en_az_bir_bedenin_stoklu_oldugu_gundur(d):
    _, h = d
    k = 250
    stoklu = np.zeros((N, len(h.oc)), bool)
    c = hucreler(h, 0, 0)
    stoklu[k - 1, c[0]] = True                     # yalnız 1. beden
    stoklu[k - 2, c[3]] = True                     # yalnız 4. beden
    stoklu[k - 2, c[4]] = True                     # aynı gün ikinci beden: tek gün
    stoklu[k, c[1]] = True                         # karar günü: sayılmaz
    g = ihtiyac.stoklu_gun(stoklu, sifir(h), h, k, 7)
    assert g[oc(h, 0, 0)] == 2 and g[oc(h, 1, 0)] == 0


def test_stoklu_matris_satisi_kacirirsa_satis_gunu_stoklu_sayilir(d):
    _, h = d
    k = 250
    satis = sifir(h)
    satis[k - 2, hucreler(h, 0, 0)[1]] = 4         # satış var, matris "stoksuz" diyor
    stoklu = np.zeros(satis.shape, bool)
    o = ihtiyac.kural_ongorusu(satis, h, k, {}, stoklu, takvim=takvim())
    assert o[oc(h, 0, 0)] == pytest.approx(4 / 1 * 7)


def test_stoklu_gun_sifirken_sifir_doner(d):
    _, h = d
    k = 250
    stoklu = np.zeros((N, len(h.oc)), bool)
    for f in (lambda: ihtiyac.kural_ongorusu(sifir(h), h, k, {}, stoklu, takvim=takvim()),
              lambda: ihtiyac.guvenlik_stoku(sifir(h), h, k, GuvenlikStoku("ros", 2), stoklu)):
        with np.errstate(all="raise"):             # sıfıra bölme uyarısı bile hata olur
            o = f()
        assert (o == 0).all() and not np.isnan(o).any()


# ------------------------------------------------------------- beden payları


def test_magaza_beden_paylari_option_ve_kategori_havuzlanir(d):
    _, h = d
    satis = sifir(h)
    satis[100, hucreler(h, 0, 0)[0]] = 10          # M0, o0, beden 1
    satis[100, hucreler(h, 0, 3)[2]] = 30          # M0, o3 (aynı kategori ve set), beden 3
    p = ihtiyac.magaza_beden_paylari(satis, h, bit_gunu=200)
    assert p.shape == (len(h.oc),)
    for opt in (0, 3):                             # iki option aynı havuz payını alır
        assert p[hucreler(h, 0, opt)].tolist() == pytest.approx([0.25, 0, 0.75, 0, 0])
    # satışı olmayan mağaza zincir eğrisine düşer
    assert p[hucreler(h, 1, 0)] == pytest.approx(EGRI[:4] / EGRI[:4].sum())


def test_magaza_beden_paylari_oc_icinde_toplam_bir_degisken_beden(d):
    _, h = d
    rng = np.random.default_rng(1)
    satis = rng.poisson(0.3, (N, len(h.oc))).astype(np.int32)
    p = ihtiyac.magaza_beden_paylari(satis, h, bit_gunu=300)
    toplam = np.bincount(h.oc, weights=p)
    assert np.allclose(toplam, 1.0)
    assert p[hucreler(h, 0, 2)].tolist() == [1.0]  # tek bedenli (STD) option


def test_magaza_beden_paylari_kategori_ayri_havuz(d):
    _, h = d
    satis = sifir(h)
    satis[100, hucreler(h, 0, 0)[0]] = 10          # Üst Giyim
    satis[100, hucreler(h, 0, 1)[4]] = 10          # Alt Giyim (başka beden seti)
    p = ihtiyac.magaza_beden_paylari(satis, h, bit_gunu=200)
    assert p[hucreler(h, 0, 0)].tolist() == pytest.approx([1, 0, 0, 0, 0])
    assert p[hucreler(h, 0, 1)].tolist() == pytest.approx([0, 0, 0, 0, 1])


def test_magaza_beden_paylari_satis_yoksa_zincir_payi(d):
    _, h = d
    p = ihtiyac.magaza_beden_paylari(sifir(h), h, bit_gunu=200)
    assert p[hucreler(h, 0, 0)] == pytest.approx(EGRI)


def test_magaza_beden_paylari_oc_bedenleri_hic_satmadiysa_zincir_payi(d):
    """Grup satmış ama OC'nin bedenlerinin hiçbiri satmamış (M1'de o0'ın 5. bedeni
    çeşit dışı; grup yalnız o3'ün 5. bedenini satmış): havuz payı o0@M1'de tümüyle 0
    olurdu, hedefi olan çift hiç almazdı. Zincir eğrisine düşer; o3@M1 havuzda kalır."""
    _, h = d
    satis = sifir(h)
    satis[100, hucreler(h, 1, 3)[4]] = 10          # M1, o3, beden 5 (o0@M1'de yok)
    p = ihtiyac.magaza_beden_paylari(satis, h, bit_gunu=200)
    assert p[hucreler(h, 1, 0)] == pytest.approx(EGRI[:4] / EGRI[:4].sum())
    assert p[hucreler(h, 1, 3)].tolist() == pytest.approx([0, 0, 0, 0, 1])
    assert np.allclose(np.bincount(h.oc, weights=p), 1.0)


def test_magaza_beden_paylari_zincir_payi_da_sifirsa_esit(d):
    w, _ = d
    w0 = SimpleNamespace(**{**vars(w), "sku_beden_payi": np.where(np.asarray(w.sku_option) == 0, 0.0,
                                                                   w.sku_beden_payi)})
    h0 = kaynak.harita_kur(w0)
    satis = sifir(h0)
    satis[100, hucreler(h0, 1, 3)[4]] = 10
    p = ihtiyac.magaza_beden_paylari(satis, h0, bit_gunu=200)
    assert p[hucreler(h0, 1, 0)] == pytest.approx([0.25] * 4)
    assert np.allclose(np.bincount(h0.oc, weights=p), 1.0)


# ------------------------------------------------------------- bedene bölme


def _bol(h, hedef, paylar, stok=None, yolda=None):
    z = np.zeros(len(h.oc), dtype=np.int64)
    return ihtiyac.bedene_bol(hedef, paylar, z if stok is None else stok, z if yolda is None else yolda, h)


def _paylar(h):
    return ihtiyac.magaza_beden_paylari(sifir(h), h, 200)      # zincir eğrisi (satış yok)


def test_bedene_bol_hedefi_paya_gore_boler(d):
    _, h = d
    hedef = np.zeros(len(h.oc_magaza))
    hedef[oc(h, 0, 0)] = 10
    n = _bol(h, hedef, _paylar(h))
    assert n[hucreler(h, 0, 0)].tolist() == [1, 2, 4, 2, 1]
    assert n.sum() == 10 and n.dtype == np.int64


def test_bedene_bol_stoku_dusur_negatife_inme(d):
    _, h = d
    hedef = np.zeros(len(h.oc_magaza))
    hedef[oc(h, 0, 0)] = 10
    stok = np.zeros(len(h.oc), dtype=np.int64)
    stok[hucreler(h, 0, 0)] = [0, 5, 0, 0, 0]
    assert _bol(h, hedef, _paylar(h), stok)[hucreler(h, 0, 0)].tolist() == [1, 0, 4, 2, 1]


def test_yolda_sayilir(d):
    _, h = d
    hedef = np.zeros(len(h.oc_magaza))
    hedef[oc(h, 0, 0)] = 10
    stok = np.zeros(len(h.oc), dtype=np.int64)
    yolda = np.zeros(len(h.oc), dtype=np.int64)
    stok[hucreler(h, 0, 0)[2]] = 1
    yolda[hucreler(h, 0, 0)[2]] = 2                # 4 gereken bedenin 3'ü raf + yolda
    yolda[hucreler(h, 0, 0)[0]] = 5                # ihtiyaçtan fazla yolda: 0'a iner
    n = _bol(h, hedef, _paylar(h), stok, yolda)[hucreler(h, 0, 0)]
    assert n.tolist() == [0, 2, 1, 2, 1]


def test_bedene_bol_tek_bedenli_ve_cesit_disi(d):
    _, h = d
    hedef = np.zeros(len(h.oc_magaza))
    hedef[oc(h, 0, 2)] = 3                         # STD, tek hücre
    hedef[oc(h, 1, 0)] = 10                        # M1'de 4 bedenli (5. beden çeşit dışı)
    n = _bol(h, hedef, _paylar(h))
    assert n[hucreler(h, 0, 2)].tolist() == [3]
    # çeşit dışı beden payını taşımaz: 10 × [1,2,4,2]/9 = [1,11, 2,22, 4,44, 2,22] yuvarlanır
    assert n[hucreler(h, 1, 0)].tolist() == [1, 2, 4, 2]


def test_bedene_bol_hedef_sifirsa_sifir(d):
    _, h = d
    stok = np.full(len(h.oc), 3, dtype=np.int64)
    assert (_bol(h, np.zeros(len(h.oc_magaza)), _paylar(h), stok) == 0).all()


# --------------------------------------------------- geleceği görmeme (sızıntı)


def _bozuk(a, bas, deger):
    b = a.copy()
    b[bas:] = deger
    return b


def test_ongoru_gelecegi_gormez(d):
    """`karar_gunu` ve sonrasının satış / stoklu satırlarını boz → hiçbir karar çıktısı değişmez."""
    _, h = d
    rng = np.random.default_rng(7)
    t = takvim(["2025-10-29", "2025-11-11"])
    k = gun(t, "2025-10-27")
    satis = rng.poisson(0.4, (N, len(h.oc))).astype(np.int32)
    stoklu = rng.random((N, len(h.oc))) < 0.7
    s2, st2 = _bozuk(satis, k, 9999), _bozuk(stoklu, k, True)
    kat = {"Üst Giyim": 1.3, "Alt Giyim": 0.8}
    for kw in ({}, {"stoklu": True}):
        a = ihtiyac.kural_ongorusu(satis, h, k, kat, stoklu if kw else None, takvim=t)
        b = ihtiyac.kural_ongorusu(s2, h, k, kat, st2 if kw else None, takvim=t)
        assert np.array_equal(a, b)
        for ayar in (GuvenlikStoku("ros", 3), GuvenlikStoku("istatistik"), GuvenlikStoku("sabit", 2)):
            assert np.array_equal(
                ihtiyac.guvenlik_stoku(satis, h, k, ayar, stoklu if kw else None),
                ihtiyac.guvenlik_stoku(s2, h, k, ayar, st2 if kw else None))
    assert np.array_equal(ihtiyac.haftalik(satis, h, k, 8), ihtiyac.haftalik(s2, h, k, 8))
    assert np.array_equal(ihtiyac.stoklu_gun(stoklu, satis, h, k, 28), ihtiyac.stoklu_gun(st2, s2, h, k, 28))
    # tam geçmiş fonksiyonları `bit_gunu` ile sınırlı
    assert ihtiyac.ozel_gun_katsayilari(satis, h, t, k) == ihtiyac.ozel_gun_katsayilari(s2, h, t, k)
    assert np.array_equal(ihtiyac.magaza_beden_paylari(satis, h, k), ihtiyac.magaza_beden_paylari(s2, h, k))


# -------------------------------------------------- gerçek (küçük) v4 dünyası


@pytest.fixture(scope="module")
def kucuk():
    from perakende_veri.v4.dunya import dunya_kur
    from perakende_veri.v4.magaza import Olcek

    w = dunya_kur(Olcek.KUCUK)
    return w, kaynak.harita_kur(w)


def test_gercek_dunya_oc_toplamlari_ve_paylar(kucuk):
    w, h = kucuk
    C, OC = len(h.oc), len(h.oc_magaza)
    rng = np.random.default_rng(3)
    satis = rng.poisson(0.2, (60, C)).astype(np.int16)
    k = 50
    # OC toplamı: pandas ile bire bir
    beklenen = pd.Series(satis[k - 7 : k].sum(axis=0, dtype=np.int64)).groupby(h.oc).sum().to_numpy()
    kat = {kat: 1.0 for kat in np.unique(h.option_kategori)}
    t = w.takvim
    o = ihtiyac.kural_ongorusu(satis, h, k, kat, takvim=t)
    assert o.shape == (OC,)
    assert np.allclose(o / np.array([ihtiyac.hafta_katsayisi(t, k, 1.0)] * OC), beklenen)
    # paylar: her OC'de toplam 1; tek bedenli option (STD) payı 1
    p = ihtiyac.magaza_beden_paylari(satis, h, k)
    assert np.allclose(np.bincount(h.oc, weights=p, minlength=OC), 1.0)
    tek = np.bincount(h.oc, minlength=OC) == 1
    assert tek.any() and np.allclose(p[np.isin(h.oc, np.flatnonzero(tek))], 1.0)
    # bedene bölme: hedefi toplamı ≈ hedef, stok+yolda düşülür
    hedef = np.full(OC, 12.0)
    z = np.zeros(C, dtype=np.int64)
    n = ihtiyac.bedene_bol(hedef, p, z, z, h)
    assert n.shape == (C,) and (n >= 0).all()
    assert abs(np.bincount(h.oc, weights=n, minlength=OC) - 12).max() <= 3     # beden başına yuvarlama
    assert (ihtiyac.bedene_bol(hedef, p, n, z, h) == 0).all()
    assert (ihtiyac.bedene_bol(hedef, p, z, n, h) == 0).all()


def test_gercek_takvim_ozel_gun_katsayilari(kucuk):
    w, h = kucuk
    satis = np.random.default_rng(5).poisson(0.3, (400, len(h.oc))).astype(np.int16)
    k = ihtiyac.ozel_gun_katsayilari(satis, h, w.takvim, 380)
    assert k and all(v > 0 and np.isfinite(v) for v in k.values())
    assert {a.removesuffix(ihtiyac.BF_SONEKI) for a in k} <= set(np.unique(h.option_kategori))
    assert any(a.endswith(ihtiyac.BF_SONEKI) for a in k) and any(not a.endswith(ihtiyac.BF_SONEKI) for a in k)


# ------------------------------------------------------------------- kapsam


def test_ihtiyac_gizli_gercegi_ice_aktarmaz():
    """Sızıntı kilidinin tamamlayıcısı: modül motoru, v4 üretecini ve hakemi içe aktarmaz."""
    import ast
    from pathlib import Path

    ag = ast.parse(Path(ihtiyac.__file__).read_text(encoding="utf-8"))
    ice = []
    for n in ast.walk(ag):
        if isinstance(n, ast.Import):
            ice += [a.name for a in n.names]
        elif isinstance(n, ast.ImportFrom):
            ice.append(("." * n.level) + (n.module or ""))
    assert not [i for i in ice if "perakende_veri" in i or "motor" in i or "hakem" in i], ice


def test_guvenlik_stoku_dondurulmus_dataclass():
    ayar = GuvenlikStoku("ros", 2.0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        ayar.deger = 3.0   # type: ignore[misc]
