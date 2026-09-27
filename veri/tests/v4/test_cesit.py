"""Testler: Görev 7 çeşit ataması, hücre tablosu, kanibalizasyon payı.

Spec: docs/superpowers/specs/2026-09-27-veri-v4-cekirdek-design.md §5.3
Brief: .superpowers/sdd/2026-09-27-veri-v4-cekirdek/task-7-brief.md
"""

import numpy as np
import pandas as pd
import pytest

from perakende_veri.v4.cesit import (
    KANIBALIZASYON_BETA,
    cesit_ata,
    hucreleri_kur,
    kanibalizasyon_payi,
)
from perakende_veri.v4.magaza import Olcek, magazalari_uret
from perakende_veri.v4.rastgele import dunya_akisi
from perakende_veri.v4.urun import urunleri_uret


def _spearman(x, y) -> float:
    """Bağımlılıksız (scipy'siz) Spearman rho: sıralar üzerinde Pearson."""
    rx = pd.Series(x).rank().to_numpy()
    ry = pd.Series(y).rank().to_numpy()
    return float(np.corrcoef(rx, ry)[0, 1])


@pytest.fixture(scope="module")
def c():
    """Küçük ölçekte mağaza/ürün dünyası + çeşit ataması + hücre tablosu.

    Atama kendi rng'siyle çekilir (gerçek boru hattındaki çekiliş sırası
    Görev 11'de sabitlenir, burada önemli değil).
    """
    magazalar, gizli = magazalari_uret(dunya_akisi())
    urunler, optionlar = urunleri_uret(dunya_akisi(), Olcek.KUCUK)
    rng = np.random.default_rng(999)
    cesit_opt = cesit_ata(rng, magazalar, gizli, optionlar)
    cesit_hucre = hucreleri_kur(cesit_opt, urunler)
    return {
        "magazalar": magazalar,
        "gizli": gizli,
        "optionlar": optionlar,
        "urunler": urunler,
        "cesit_opt": cesit_opt,
        "cesit_hucre": cesit_hucre,
    }


# ---------------------------------------------------------------------------
# cesit_ata
# ---------------------------------------------------------------------------


def test_onl_her_seyi_tasir(c):
    magazalar, optionlar, cesit_opt = c["magazalar"], c["optionlar"], c["cesit_opt"]
    onl_idx = int(magazalar.index[magazalar.tip == "Online"][0])
    onl_satirlar = cesit_opt[cesit_opt.magaza_idx == onl_idx]
    assert set(onl_satirlar.option_idx) == set(range(len(optionlar)))
    assert not onl_satirlar.outlet_akisi.any()


def test_outlet_line_yalniz_outlet(c):
    magazalar, optionlar, cesit_opt = c["magazalar"], c["optionlar"], c["cesit_opt"]
    outlet_line_idx = set(optionlar.index[optionlar.line == "Outlet"])
    tasiyanlar = set(cesit_opt[cesit_opt.option_idx.isin(outlet_line_idx)].magaza_idx)
    izinli = set(magazalar.index[magazalar.tip.isin(["Outlet", "Online"])])
    assert tasiyanlar
    assert tasiyanlar <= izinli
    # gerçekten en az bir outlet fiziksel mağaza taşıyor (yalnız ONL değil)
    outlet_fiziksel = set(magazalar.index[magazalar.tip == "Outlet"])
    assert tasiyanlar & outlet_fiziksel


def test_outlet_magaza_collection_yalniz_outlet_akisiyla(c):
    """Outlet mağazalar Collection'ı yalnız outlet_akisi=True ile taşır."""
    magazalar, optionlar, cesit_opt = c["magazalar"], c["optionlar"], c["cesit_opt"]
    outlet_fiziksel = set(magazalar.index[magazalar.tip == "Outlet"])
    collection_idx = set(optionlar.index[optionlar.line == "Collection"])
    satirlar = cesit_opt[
        cesit_opt.magaza_idx.isin(outlet_fiziksel) & cesit_opt.option_idx.isin(collection_idx)
    ]
    assert len(satirlar)
    assert satirlar.outlet_akisi.all()
    # her outlet mağaza bütün Collection option'larını taşır
    for m in outlet_fiziksel:
        assert set(satirlar[satirlar.magaza_idx == m].option_idx) == collection_idx


def test_genislik_m2_ile_artar(c):
    magazalar, optionlar, cesit_opt = c["magazalar"], c["optionlar"], c["cesit_opt"]
    fiziksel = magazalar[(magazalar.tip != "Online") & (magazalar.tip != "Outlet")]
    collection_idx = set(optionlar.index[optionlar.line == "Collection"])

    m2ler, sayimlar = [], []
    for idx, satir in fiziksel.iterrows():
        n = int(
            (
                (cesit_opt.magaza_idx == idx) & cesit_opt.option_idx.isin(collection_idx)
            ).sum()
        )
        m2ler.append(satir.metrekare)
        sayimlar.append(n)

    rho = _spearman(m2ler, sayimlar)
    assert rho > 0.7, rho


def test_basic_kucuk_magazada_kismi(c):
    """m² < 250 mağazalar Basic'i tam almaz (rastgele ~%70); m² >= 250 tam alır."""
    magazalar, optionlar, cesit_opt = c["magazalar"], c["optionlar"], c["cesit_opt"]
    fiziksel = magazalar[(magazalar.tip != "Online") & (magazalar.tip != "Outlet")]
    basic_idx = set(optionlar.index[optionlar.line == "Basic"])
    n_basic = len(basic_idx)

    kucukler = fiziksel[fiziksel.metrekare < 250]
    genisler = fiziksel[fiziksel.metrekare >= 250]
    assert len(kucukler) and len(genisler)

    for idx in genisler.index:
        n = int(((cesit_opt.magaza_idx == idx) & cesit_opt.option_idx.isin(basic_idx)).sum())
        assert n == n_basic

    kucuk_oranlar = [
        int(((cesit_opt.magaza_idx == idx) & cesit_opt.option_idx.isin(basic_idx)).sum())
        / n_basic
        for idx in kucukler.index
    ]
    assert 0.55 < float(np.mean(kucuk_oranlar)) < 0.85


def test_nos_her_fiziksel_magazada(c):
    magazalar, optionlar, cesit_opt = c["magazalar"], c["optionlar"], c["cesit_opt"]
    fiziksel = magazalar[(magazalar.tip != "Online") & (magazalar.tip != "Outlet")]
    nos_idx = set(optionlar.index[optionlar.line == "NOS"])
    n_nos = len(nos_idx)
    for idx in fiziksel.index:
        n = int(((cesit_opt.magaza_idx == idx) & cesit_opt.option_idx.isin(nos_idx)).sum())
        assert n == n_nos


def test_outlet_magaza_basic_nos_almaz(c):
    magazalar, optionlar, cesit_opt = c["magazalar"], c["optionlar"], c["cesit_opt"]
    outlet_fiziksel = set(magazalar.index[magazalar.tip == "Outlet"])
    devamli_idx = set(optionlar.index[optionlar.line.isin(["Basic", "NOS"])])
    satirlar = cesit_opt[
        cesit_opt.magaza_idx.isin(outlet_fiziksel) & cesit_opt.option_idx.isin(devamli_idx)
    ]
    assert satirlar.empty


# ---------------------------------------------------------------------------
# hucreleri_kur
# ---------------------------------------------------------------------------


def test_hucre_sku_sayisi_dogru(c):
    """Her (mağaza, option) satırı option'ın bütün SKU'larına genişler."""
    urunler, cesit_opt, cesit_hucre = c["urunler"], c["cesit_opt"], c["cesit_hucre"]
    sku_sayisi_option_basina = urunler.groupby("option_id").size()
    option_ids_sirali = urunler["option_id"].drop_duplicates().to_numpy()
    beklenen = sum(sku_sayisi_option_basina[oid] for oid in option_ids_sirali[cesit_opt.option_idx])
    assert len(cesit_hucre) == beklenen


def test_outlet_akisi_penceresi_cikis_artı_84(c):
    """Outlet akışı hücreleri [çıkış, çıkış+84) penceresinde açık."""
    cesit_hucre = c["cesit_hucre"]
    outlet_satirlar = cesit_hucre[cesit_hucre.outlet_akisi]
    assert len(outlet_satirlar)
    assert np.all(outlet_satirlar.kapanis_gun == outlet_satirlar.acilis_gun + 84)


def test_normal_hucre_penceresi_lansman_cikis(c):
    urunler, cesit_hucre = c["urunler"], c["cesit_hucre"]
    normal = cesit_hucre[~cesit_hucre.outlet_akisi]
    assert len(normal)
    assert np.all(normal.acilis_gun <= normal.kapanis_gun)


# ---------------------------------------------------------------------------
# kanibalizasyon_payi
# ---------------------------------------------------------------------------


def _sahte_optionlar(n: int, alt_kategori="Tişört") -> pd.DataFrame:
    return pd.DataFrame({"alt_kategori": [alt_kategori] * n})


def _sahte_hucre(n_option: int, acilis=0, kapanis=100, magaza_idx=0) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "magaza_idx": [magaza_idx] * n_option,
            "sku_idx": list(range(n_option)),
            "option_idx": list(range(n_option)),
            "outlet_akisi": [False] * n_option,
            "acilis_gun": [acilis] * n_option,
            "kapanis_gun": [kapanis] * n_option,
        }
    )


@pytest.fixture
def k():
    """4 option'lık tek mağaza/alt kategori grubu, eşit çekicilik."""
    optionlar = _sahte_optionlar(4)
    cesit_hucre = _sahte_hucre(4)
    cekicilik = np.ones(4)
    return {"cesit_hucre": cesit_hucre, "optionlar": optionlar, "cekicilik": cekicilik}


def test_kanibalizasyon_toplam(k):
    """Grupta toplam çarpan = n^β (çekicilik eşitken birebir)."""
    payi = kanibalizasyon_payi(k["cesit_hucre"], k["optionlar"], k["cekicilik"])
    carpanlar = payi(10)
    n = 4
    assert np.isclose(carpanlar.sum(), n**KANIBALIZASYON_BETA)


def test_kanibalizasyon_stoktan_bagimsiz():
    """Fonksiyon imzasında stok yok; aynı d için aynı sonuç döner."""
    optionlar = _sahte_optionlar(3)
    cesit_hucre = _sahte_hucre(3)
    cekicilik = np.array([1.0, 2.0, 0.5])

    payi = kanibalizasyon_payi(cesit_hucre, optionlar, cekicilik)
    sonuc1 = payi(5)
    sonuc2 = payi(5)
    assert np.array_equal(sonuc1, sonuc2)


def test_n_artinca_option_basi_azalir():
    """n=1 → 1; n=4 → 4^0.6 / 4 (çekicilik eşitken)."""
    optionlar1 = _sahte_optionlar(1)
    cesit1 = _sahte_hucre(1)
    payi1 = kanibalizasyon_payi(cesit1, optionlar1, np.ones(1))
    assert np.isclose(payi1(0)[0], 1.0)

    optionlar4 = _sahte_optionlar(4)
    cesit4 = _sahte_hucre(4)
    payi4 = kanibalizasyon_payi(cesit4, optionlar4, np.ones(4))
    assert np.isclose(payi4(0)[0], 4**0.6 / 4)


def test_kanibalizasyon_pencere_disi_sifir():
    """Pencere dışındaki (henüz lansman olmamış / çıkmış) hücre çarpanı 0."""
    optionlar = _sahte_optionlar(2)
    cesit_hucre = pd.DataFrame(
        {
            "magaza_idx": [0, 0],
            "sku_idx": [0, 1],
            "option_idx": [0, 1],
            "outlet_akisi": [False, False],
            "acilis_gun": [0, 50],
            "kapanis_gun": [100, 150],
        }
    )
    cekicilik = np.ones(2)
    payi = kanibalizasyon_payi(cesit_hucre, optionlar, cekicilik)
    carpanlar = payi(10)  # yalnız option 0 açık
    assert carpanlar[1] == 0.0
    assert carpanlar[0] == 1.0  # n=1


def test_kanibalizasyon_cekicilik_orantili():
    """Çekiciliği yüksek option, aynı n'de daha büyük pay alır."""
    optionlar = _sahte_optionlar(2)
    cesit_hucre = _sahte_hucre(2)
    cekicilik = np.array([1.0, 3.0])
    payi = kanibalizasyon_payi(cesit_hucre, optionlar, cekicilik)
    carpanlar = payi(0)
    assert carpanlar[1] > carpanlar[0]


def test_kanibalizasyon_farkli_magaza_ayri_grup():
    """Farklı mağazadaki aynı alt kategori ayrı grup sayılır (n karışmaz)."""
    optionlar = _sahte_optionlar(2)
    cesit_hucre = pd.DataFrame(
        {
            "magaza_idx": [0, 1],
            "sku_idx": [0, 1],
            "option_idx": [0, 1],
            "outlet_akisi": [False, False],
            "acilis_gun": [0, 0],
            "kapanis_gun": [100, 100],
        }
    )
    cekicilik = np.ones(2)
    payi = kanibalizasyon_payi(cesit_hucre, optionlar, cekicilik)
    carpanlar = payi(10)
    assert np.allclose(carpanlar, [1.0, 1.0])  # her grupta n=1


def test_kanibalizasyon_okunamaz_dizi(k):
    payi = kanibalizasyon_payi(k["cesit_hucre"], k["optionlar"], k["cekicilik"])
    sonuc = payi(0)
    with pytest.raises(ValueError):
        sonuc[0] = 99.0
