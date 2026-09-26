"""v3 motoru: özdeşlik, ilk dağıtım, kapı, RPT kuralı, politika arayüzü."""

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from perakende_veri.v3.politika import LumodaRPT, mevcut_dagitim
from perakende_veri.v3.simulasyon import orantili_kes, simule_et
from perakende_veri.v3.tedarik import moq_yuvarla


@pytest.fixture(scope="module")
def k(v3_kosu):
    return SimpleNamespace(**v3_kosu)


def _matris(k, tablo, kolon):
    m = np.zeros(k.talep.shape, dtype=np.int64)
    np.add.at(m, (tablo["gun"].to_numpy(), tablo["hucre"].to_numpy()), tablo[kolon].to_numpy())
    return m


# --- Özdeşlik: gerçek talep = satış + kayıp ----------------------------

def test_talep_satis_arti_kayip(k):
    s = k.ham["satis"]
    satis = _matris(k, s[s["adet"] > 0], "adet")
    kayip = _matris(k, k.ham["kayip_satis"], "kayip_adet")
    assert np.array_equal(satis + kayip, k.talep.astype(np.int64))


def test_stok_ve_depo_negatif_degil(k):
    assert (k.ham["stok"]["adet"] >= 0).all()
    assert (k.ham["depo_stok"]["adet"] >= 0).all()
    assert (k.ham["son_durum"]["magaza_stok"] >= 0).all()
    assert (k.ham["son_durum"]["depo"] >= 0).all()


# --- Stok akışının kapanışı ---------------------------------------------

def test_depo_akisi_kapanir(k):
    """Son depo = başlangıç + gelen siparişler − net sevkiyat."""
    w = k.dunya
    D = w.gun_sayisi
    gelen = np.zeros(len(w.urunler), dtype=np.int64)
    for s in k.ham["siparis"]:
        if s["gerceklesen_gun"] < D:
            np.add.at(gelen, s["skular"], s["adetler"])
    sv = k.ham["sevkiyat"]
    sv = sv[sv["gun"] > 0]   # 0. günün devamlı ilk dağıtımı başlangıç stoğundan
    net = np.bincount(w.hucre_sku[sv["hucre"].to_numpy()], sv["adet"].to_numpy(),
                      minlength=len(w.urunler)).astype(np.int64)
    ilk = k.ham["depo_stok"]
    baslangic = ilk[ilk["gun"] == 0].set_index("sku")["adet"].reindex(range(len(w.urunler)), fill_value=0).to_numpy()
    assert np.array_equal(k.ham["son_durum"]["depo"], baslangic + gelen - net)


def test_magaza_akisi_kapanir(k):
    w = k.dunya
    sv = k.ham["sevkiyat"]
    s = k.ham["satis"]
    giren = np.bincount(sv["hucre"], sv["adet"], minlength=len(w.cesit))
    satilan = np.bincount(s["hucre"], s["adet"], minlength=len(w.cesit))   # iade negatif
    assert np.array_equal(k.ham["son_durum"]["magaza_stok"], (giren - satilan).astype(np.int64))


# --- İlk dağıtım, çıkış ------------------------------------------------

def test_ilk_dagitim_gununde_ve_dunyadaki_adetlerle(k):
    w = k.dunya
    sv = k.ham["sevkiyat"]
    ilk = sv[(sv["tip"] == "ilk_dagitim") & (sv["gun"] > 0)]
    beklenen_gun = w.optionlar["ilk_dagitim_gun"].to_numpy()[w.hucre_option[ilk["hucre"].to_numpy()]]
    assert (ilk["gun"].to_numpy() == beklenen_gun).all()
    assert np.array_equal(ilk["adet"].to_numpy(), w.ilk_dagitim_hucre[ilk["hucre"].to_numpy()])
    assert ilk["adet"].sum() == w.ilk_dagitim_hucre.sum()


def test_replenishment_ilk_dagitimdan_sonra_cikistan_once(k):
    w = k.dunya
    sv = k.ham["sevkiyat"]
    r = sv[sv["tip"] == "replenishment"]
    o = w.hucre_option[r["hucre"].to_numpy()]
    assert (r["gun"].to_numpy() > w.optionlar["ilk_dagitim_gun"].to_numpy()[o]).all()
    assert (r["gun"].to_numpy() < w.optionlar["cikis_gun"].to_numpy()[o]).all()
    assert (k.dunya.takvim["tarih"].to_numpy()[r["gun"].to_numpy()].astype("datetime64[D]").view("int64") % 7 == 4).all()  # pazartesi


def test_geri_toplama_cikis_gununde_negatif(k):
    w = k.dunya
    sv = k.ham["sevkiyat"]
    g = sv[sv["tip"] == "geri_toplama"]
    assert len(g) > 0 and (g["adet"] < 0).all()
    o = w.hucre_option[g["hucre"].to_numpy()]
    assert (g["gun"].to_numpy() == w.optionlar["cikis_gun"].to_numpy()[o]).all()
    # Çıkıştan sonra hücre fotoğrafta görünmez, satışı yoktur
    st = k.ham["stok"]
    assert (st["gun"].to_numpy() <= w.optionlar["cikis_gun"].to_numpy()[w.hucre_option[st["hucre"].to_numpy()]]).all()


# --- Stoklu gün ---------------------------------------------------------

def test_stoklu_gun_gunluk_defterle_tutarli(k):
    """Satış olan gün stokludur; satışsız kayıp olan gün stoksuzdur."""
    s = k.ham["satis"]
    satis = _matris(k, s[s["adet"] > 0], "adet") > 0
    kayip = _matris(k, k.ham["kayip_satis"], "kayip_adet") > 0
    st = k.ham["stok"]
    st = st[st["gun"] >= 7]
    gun, hucre = st["gun"].to_numpy(), st["hucre"].to_numpy()
    satis_gunu = np.zeros(len(st), dtype=np.int64)
    bos_gun = np.zeros(len(st), dtype=np.int64)
    for i in range(1, 8):
        satis_gunu += satis[gun - i, hucre]
        bos_gun += kayip[gun - i, hucre] & ~satis[gun - i, hucre]
    sg = st["stoklu_gun"].to_numpy()
    assert ((sg >= 0) & (sg <= 7)).all()
    assert (sg >= satis_gunu).all()
    assert (sg <= 7 - bos_gun).all()
    # Pazartesi açılış stoğu > 0 ise pazar günü de stokluydu
    assert (sg[st["adet"].to_numpy() > 0] >= 1).all()


# --- RPT kuralı ---------------------------------------------------------

def test_rpt_siparisleri_kurala_uyar(k):
    w = k.dunya
    opt = w.optionlar
    rpt = [s for s in k.ham["siparis"] if s["tip"] == "rpt"]
    assert len(rpt) > 50
    optionlar = [s["option"] for s in rpt]
    assert len(optionlar) == len(set(optionlar))            # option başına en fazla bir
    for s in rpt:
        o = s["option"]
        h = s["siparis_gun"] - opt.at[o, "lansman_gun"]
        assert opt.at[o, "line"] == "Collection"
        assert h in (21, 28, 35, 42)
        assert opt.at[o, "lansman_gun"] + 21 + 7 * opt.at[o, "rpt_hafta"] < opt.at[o, "indirim_gun"]
        assert s["adetler"].sum() == moq_yuvarla(0.5 * w.ilk_alim[o], int(opt.at[o, "moq_option"]))
        assert s["planlanan_gun"] == s["siparis_gun"] + 7 * opt.at[o, "rpt_hafta"]


def _sahte_rpt_gorunum(line="Collection", h=21, satilan=60, gonderilen=100, rpt=0, rpt_hafta=5, indirim=200):
    opt = pd.DataFrame({
        "line": [line], "lansman_gun": [0], "rpt_hafta": [rpt_hafta],
        "indirim_gun": [indirim], "moq_option": [300],
    })
    return SimpleNamespace(
        dunya=SimpleNamespace(optionlar=opt, ilk_alim=np.array([1000])), gun=h,
        satilan_option=np.array([satilan]), gonderilen_option=np.array([gonderilen]),
        rpt_sayisi=np.array([rpt]),
    )


@pytest.mark.parametrize("ayar, beklenen", [
    ({}, {0: 500}),
    ({"satilan": 54}, {}),                 # STR %54 < %55
    ({"h": 14}, {}),                       # 2. hafta: erken
    ({"h": 49}, {}),                       # 7. hafta: geç
    ({"rpt": 1}, {}),                      # zaten verilmiş
    ({"line": "Outlet"}, {}),
    ({"rpt_hafta": 15, "indirim": 120}, {}),   # 21 + 105 ≥ 120: yetişmez
    ({"h": 42}, {0: 500}),
])
def test_lumoda_rpt_kurali(ayar, beklenen):
    assert LumodaRPT()(_sahte_rpt_gorunum(**ayar)) == beklenen


def test_rpt_miktari_moq_alt_siniri():
    g = _sahte_rpt_gorunum()
    g.dunya.ilk_alim = np.array([400])
    assert LumodaRPT()(g) == {0: 300}


# --- Ölü stok kapısı ----------------------------------------------------

def test_olu_stok_kapisi():
    # 4 hücre, hepsi hedef 20: yeni/sıfır hız, eski/sıfır hız, eski/hızlı, eski/yavaş-dolu
    dunya = SimpleNamespace(
        ileri_plan=lambda d, n: np.full(4, 20.0),
        optionlar=pd.DataFrame({"ilk_dagitim_gun": [90, 0]}),
        hucre_option=np.array([0, 1, 1, 1]),
    )
    g = SimpleNamespace(
        dunya=dunya, gun=100,
        magaza_stok=np.array([0, 0, 2, 12]),
        satis_28=np.array([0, 0, 28, 8]),       # haftalık hız 0, 0, 7, 2
    )
    istek = mevcut_dagitim(g)
    assert list(istek) == [20, 0, 18, 0]
    # 12 ≥ 2 × 4 → mal gitmez; sıfır hız → yeni değilse hiç gitmez


# --- Orantılı kesme -----------------------------------------------------

def test_orantili_kes_kisit_yoksa_aynen():
    istek = np.array([3, 4, 5])
    assert list(orantili_kes(istek, np.array([0, 0, 1]), np.array([10, 10]))) == [3, 4, 5]


def test_orantili_kes_depoyu_asmaz():
    rng = np.random.default_rng(3)
    istek = rng.integers(0, 9, size=200)
    sku = rng.integers(0, 7, size=200)
    depo = rng.integers(0, 60, size=7)
    g = orantili_kes(istek, sku, depo)
    toplam = np.bincount(sku, g, minlength=7)
    istenen = np.bincount(sku, istek, minlength=7)
    assert (g <= istek).all() and (g >= 0).all()
    assert (toplam == np.minimum(depo, istenen)).all()
    oran = np.where(istenen > depo, depo / np.maximum(istenen, 1), 1.0)[sku]
    assert (np.abs(g - istek * oran) < 1.0 + 1e-9).all()


# --- Politika arayüzü ----------------------------------------------------

def test_politikalar_enjekte_edilir_ve_gorunum_salt_okunur(k):
    kayit = []

    def dagitim(g):
        kayit.append((g.gun, g.satis_gecmisi.shape[0], g.stoklu_gecmisi.shape[0]))
        with pytest.raises(ValueError):
            g.magaza_stok[0] = 99
        with pytest.raises(ValueError):
            g.depo[0] = 99
        return np.zeros(len(g.magaza_stok), dtype=np.int64)

    sonuc = simule_et(k.dunya, k.talep[:120], dagitim_politikasi=dagitim, varsayilan_rpt=False,
                      gun_sayisi=120)
    assert all(gun == n1 == n2 for gun, n1, n2 in kayit)      # yalnız geçmiş satırlar
    assert not any(s["tip"] == "rpt" for s in sonuc["siparis"])
    assert (sonuc["sevkiyat"]["tip"] != "replenishment").all()


def test_verilen_talep_matrisiyle_ayni_sonuc(k):
    """Motor talebi yalnız matristen okur: aynı matris, aynı çıktı."""
    kisa = simule_et(k.dunya, k.talep, gun_sayisi=200)
    for ad in ("satis", "kayip_satis", "sevkiyat", "stok"):
        tam = k.ham[ad]
        pd.testing.assert_frame_equal(
            kisa[ad].reset_index(drop=True), tam[tam["gun"] < 200].reset_index(drop=True)
        )


# --- Operasyon rastgeleliği politikadan bağımsız ------------------------

def test_binom_ters_cdf_kesin():
    import math

    from perakende_veri.v3.dunya import binom_ters_cdf

    u = (np.arange(200_000) + 0.5) / 200_000
    for n in (1, 4, 12):
        k = binom_ters_cdf(u, np.full(u.size, n), 0.06)
        assert k.max() <= n
        frekans = np.bincount(k, minlength=n + 1) / u.size
        kesin = [math.comb(n, j) * 0.06**j * 0.94 ** (n - j) for j in range(n + 1)]
        assert np.allclose(frekans, kesin, atol=1e-4)
    assert binom_ters_cdf(np.array([0.99]), np.array([0]), 0.06)[0] == 0


def test_operasyon_uretici_gun_anahtarli():
    from perakende_veri.v3.dunya import operasyon_uretici

    a = operasyon_uretici(100).random(5)
    operasyon_uretici(99).random(1000)          # başka günün tüketimi etkilemez
    assert np.array_equal(a, operasyon_uretici(100).random(5))
    assert not np.array_equal(a, operasyon_uretici(101).random(5))


def test_rpt_degisince_diger_optionlar_birebir_ayni(k):
    """Tek bir option'ın RPT'si kaldırıldığında yalnız o option'ın hücreleri
    değişir: diğer bütün hücrelerin satışı, iadesi, tutarı ve kayıp satışı
    varsayılan koşuyla birebir aynıdır (iade ve işlem indirimi hücre × gün
    tekdüzesinden gelir, paylaşılan bir akıştan değil)."""
    rpt = [s for s in k.ham["siparis"] if s["tip"] == "rpt"]
    hedef = rpt[len(rpt) // 2]["option"]
    varsayilan = LumodaRPT()

    def bir_eksik(g):
        return {o: q for o, q in varsayilan(g).items() if o != hedef}

    alt = simule_et(k.dunya, k.talep, rpt_politikasi=bir_eksik)
    assert sum(s["tip"] == "rpt" for s in alt["siparis"]) == len(rpt) - 1

    diger = k.dunya.hucre_option != hedef
    for ad in ("satis", "kayip_satis"):
        a, b = k.ham[ad], alt[ad]
        a_d = a[diger[a["hucre"].to_numpy()]].reset_index(drop=True)
        b_d = b[diger[b["hucre"].to_numpy()]].reset_index(drop=True)
        pd.testing.assert_frame_equal(a_d, b_d)
    # Hedef option'ın kendisi gerçekten değişti (test boş değil)
    s_a = k.ham["satis"]
    s_b = alt["satis"]
    hedef_a = s_a[~diger[s_a["hucre"].to_numpy()]]["adet"].sum()
    hedef_b = s_b[~diger[s_b["hucre"].to_numpy()]]["adet"].sum()
    assert hedef_a != hedef_b
