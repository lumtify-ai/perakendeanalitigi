"""Testler: Görev 11 dünya montajı, ölçek, yolda süre.

Spec: docs/superpowers/specs/2026-09-27-veri-v4-cekirdek-design.md §6, §7.2
Brief: .superpowers/sdd/2026-09-27-veri-v4-cekirdek/task-11-brief.md
"""

import hashlib

import numpy as np
import pandas as pd
import pytest

from perakende_veri.v4 import sabitler
from perakende_veri.v4.dunya import Dunya, akislar, dunya_kur, yolda_gun
from perakende_veri.v4.kampanya import esneklik
from perakende_veri.v4.magaza import Olcek, magazalari_uret
from perakende_veri.v4.tedarik import lumoda_tedarikci_secimi
from perakende_veri.v4.urun import liste_fiyati, urunleri_uret


def _sha(df: pd.DataFrame) -> str:
    return hashlib.sha256(pd.util.hash_pandas_object(df, index=True).to_numpy().tobytes()).hexdigest()


def _yayimlanan(w: Dunya) -> dict[str, pd.DataFrame]:
    """Görev 15'in yayımlayacağı (ya da yayımlanan tablolara kaynak olan)
    DataFrame'ler."""
    tablolar = {
        "magazalar": w.magazalar,
        "magaza_olay": w.magaza_olay,
        "urunler": w.urunler,
        "optionlar": w.optionlar,
        "paketler": w.paketler,
        "tedarikciler": w.tedarikciler,
        "kampanya": w.kampanya,
        "sezon": w.sezon,
        "takvim": w.takvim,
    }
    tablolar.update(w.plan_tablolari)
    return tablolar


# ---------------------------------------------------------------------------
# Brief testleri
# ---------------------------------------------------------------------------


def test_kucuk_olcek_ayni_magazalar(kucuk_dunya):
    """KÜÇÜK dünyanın mağaza satırları TAM dünyadaki aynı id'li satırlarla
    birebir (mağaza akışı ölçekten bağımsız çekilir, alt küme sonra)."""
    w = kucuk_dunya
    tam_magaza, tam_gizli = magazalari_uret(akislar()["magaza"])
    assert len(tam_magaza) == 85
    assert len(w.magazalar) == Olcek.KUCUK.magaza + 1
    beklenen = tam_magaza.set_index("magaza_id").loc[w.magazalar.magaza_id].reset_index()
    pd.testing.assert_frame_equal(w.magazalar.reset_index(drop=True), beklenen)
    beklenen_g = tam_gizli.set_index("magaza_id").loc[w.gizli_magaza.magaza_id].reset_index()
    pd.testing.assert_frame_equal(w.gizli_magaza.reset_index(drop=True), beklenen_g)
    assert w.magazalar.magaza_id.iloc[-1] == "ONL"


def test_akis_sirasi_sabit(kucuk_dunya):
    """İki kez kur → aynı sha256 (mağazalar, ürünler, çeşit, kampanya) ve
    aynı λ."""
    w2 = dunya_kur(Olcek.KUCUK)
    w1 = kucuk_dunya
    for ad in ("magazalar", "urunler", "optionlar", "cesit", "kampanya", "tedarikciler"):
        assert _sha(getattr(w1, ad)) == _sha(getattr(w2, ad)), ad
    for d in (0, 300, 900):
        assert np.array_equal(w1.lam.gun(d), w2.lam.gun(d))
    assert np.array_equal(w1.ilk_alim, w2.ilk_alim)
    assert np.array_equal(w1.sapma_surekli, w2.sapma_surekli)


def test_hucre_indis_sozlesmesi(kucuk_dunya):
    """hucre_* uzunlukları C; ONL (son mağaza satırı) hücreleri hucre_online;
    option_id'ler hücre, SKU ve option düzeyinde tutarlı."""
    w = kucuk_dunya
    C = len(w.cesit)
    for ad in (
        "hucre_magaza", "hucre_sku", "hucre_option", "hucre_online",
        "hucre_acilis", "hucre_kapanis", "hucre_outlet_akisi", "esneklik_hucre",
    ):
        assert len(getattr(w, ad)) == C, ad
    assert w.hucre_online.dtype == bool
    onl = len(w.magazalar) - 1
    assert np.array_equal(w.hucre_online, w.hucre_magaza == onl)
    assert w.hucre_online.any() and (~w.hucre_online).any()
    assert w.hucre_magaza.max() == onl

    assert np.array_equal(
        w.optionlar.option_id.to_numpy()[w.hucre_option],
        w.urunler.option_id.to_numpy()[w.hucre_sku],
    )
    assert np.array_equal(
        w.optionlar.option_id.to_numpy()[w.sku_option], w.urunler.option_id.to_numpy()
    )
    assert np.array_equal(w.lam.hucre_option, w.hucre_option)
    assert np.array_equal(w.plan.hucre_magaza, w.hucre_magaza)
    assert len(w.lam.gun(500)) == C


def test_gercek_gizli_ayri(kucuk_dunya):
    """gercek() anahtarları; hiçbiri (ne de gizli tabloların sütunları)
    yayımlanan DataFrame sütunu değil."""
    w = kucuk_dunya
    g = w.gercek()
    for anahtar in (
        "segment", "esneklik", "oznitelik_etkisi", "trend_tablosu", "surpriz",
        "suruklenme", "tedarikci_profili",
    ):
        assert anahtar in g, anahtar
    assert g["esneklik"].shape == (len(w.magazalar), len(w.optionlar))
    assert len(g["surpriz"]) == len(w.optionlar)
    assert {"segment", "gelir", "kadin_payi", "genc_egilim", "iklim"} <= set(g["segment"].columns)
    assert {"maliyet_carpani", "hatali_orani", "kapasite_sezon_adet"} <= set(
        g["tedarikci_profili"].columns
    )

    gizli_adlar = set(g) | (set(w.gizli_magaza.columns) - {"magaza_id"}) | (
        set(w.gizli_tedarikci.columns) - {"tedarikci_id", "mense"}
    )
    for ad, df in _yayimlanan(w).items():
        ortak = gizli_adlar & set(df.columns)
        assert not ortak, f"{ad}: gizli sütun {ortak}"


def test_yolda_gun_araliklari():
    km = np.array([0.0, 150.0, 150.1, 300.0, 300.1, 500.0, 500.1, 800.0, 800.1, 1000.0, 1000.1, 2000.0])
    depo = yolda_gun(km, depo=True)
    magaza = yolda_gun(km, depo=False)
    assert depo.tolist() == [1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3]
    assert magaza.tolist() == [1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 4, 4]
    assert np.issubdtype(depo.dtype, np.integer)
    assert depo.min() >= 1 and depo.max() <= 3
    assert magaza.min() >= 1 and magaza.max() <= 4


@pytest.mark.yavas
def test_tam_dunya_boyutu(kucuk_dunya, tam_kosu):
    """TAM dünyanın boyutu (oturum fixture'ı `tam_kosu`'nun dünyası)."""
    w = tam_kosu["dunya"]
    print(f"\nTAM: C={len(w.cesit)}, O={len(w.optionlar)}, S={len(w.urunler)}")
    assert 250_000 <= len(w.cesit) <= 350_000
    assert 1_820 <= len(w.optionlar) <= 1_920
    assert len(w.magazalar) == 85
    # KÜÇÜK dünyanın mağazaları TAM'dakilerle birebir
    k = kucuk_dunya.magazalar
    pd.testing.assert_frame_equal(
        k.reset_index(drop=True),
        w.magazalar.set_index("magaza_id").loc[k.magaza_id].reset_index(),
    )
    assert w.urunler.tedarikci_id.notna().all()
    assert w.depo_mesafe_km.shape == (85,)
    # kampanya takvimi ölçekten bağımsız (bütün zincirin bölgeleriyle çekilir)
    assert _sha(w.kampanya) == _sha(kucuk_dunya.kampanya)


# ---------------------------------------------------------------------------
# Ek testler
# ---------------------------------------------------------------------------


def test_tedarikci_id_dolu(kucuk_dunya):
    w = kucuk_dunya
    assert w.urunler.tedarikci_id.notna().all()
    assert w.optionlar.tedarikci_id.notna().all()
    assert set(w.optionlar.tedarikci_id) <= set(w.tedarikciler.tedarikci_id)
    # SKU'nun tedarikçisi option'ınınkiyle aynı
    assert np.array_equal(
        w.urunler.tedarikci_id.to_numpy(), w.optionlar.tedarikci_id.to_numpy()[w.sku_option]
    )
    assert np.array_equal(
        w.tedarikciler.tedarikci_id.to_numpy()[w.tedarikci_idx], w.optionlar.tedarikci_id.to_numpy()
    )


def test_liste_fiyati_tedarikci_maliyetinden_sonra(kucuk_dunya):
    """alış = ham alış × maliyet çarpanı × (0,93 uzmanlıkta); liste fiyatı
    bu alıştan yeniden hesaplanır (option ve SKU'da)."""
    w = kucuk_dunya
    _, ham_opt = urunleri_uret(akislar()["urun"], Olcek.KUCUK)
    assert (ham_opt.option_id.to_numpy() == w.optionlar.option_id.to_numpy()).all()
    t = w.tedarikci_idx
    carpan = w.gizli_tedarikci.maliyet_carpani.to_numpy()[t]
    alan = w.optionlar.alt_kategori.map(sabitler.ALT_KATEGORI_ALAN).to_numpy()
    uyum = alan == w.tedarikciler.uzmanlik.to_numpy()[t]
    beklenen = ham_opt.alis_fiyati.to_numpy() * carpan * np.where(uyum, sabitler.UZMANLIK_MALIYET_CARPANI, 1.0)
    assert np.allclose(w.optionlar.alis_fiyati.to_numpy(), beklenen, atol=0.006)
    assert not np.allclose(w.optionlar.alis_fiyati.to_numpy(), ham_opt.alis_fiyati.to_numpy())
    assert uyum.any()

    lf = liste_fiyati(w.optionlar.alis_fiyati.to_numpy(), w.optionlar.fiyat_segmenti.to_numpy())
    assert np.allclose(w.optionlar.liste_fiyati.to_numpy(), lf)
    assert np.allclose(w.urunler.liste_fiyati.to_numpy(), lf[w.sku_option])
    assert np.allclose(w.urunler.alis_fiyati.to_numpy(), w.optionlar.alis_fiyati.to_numpy()[w.sku_option])
    # plan tablolarındaki fiyat da yeni liste fiyatından
    rp = w.plan_tablolari["range_plan"]
    assert (rp.ortalama_fiyat > 0).all()


def test_politika_enjeksiyonu_diger_akislari_bozmaz(kucuk_dunya):
    """Farklı tedarikçi seçimi politikası yalnız tedarikçiye bağlı çıktıları
    değiştirir; mağaza, ürün kimliği, çeşit, λ ve kampanya aynı kalır.
    Varsayılan politikayı açıkça vermek birebir aynı dünyayı verir."""
    def hep_ilk(rng, optionlar, tedarikciler, gizli, talep_tahmini):
        return np.zeros(len(optionlar), dtype=np.int64)

    w = kucuk_dunya
    w2 = dunya_kur(Olcek.KUCUK, tedarikci_secimi=hep_ilk)
    assert (w2.optionlar.tedarikci_id == "T01").all()
    assert _sha(w.magazalar) == _sha(w2.magazalar)
    assert _sha(w.cesit) == _sha(w2.cesit)
    assert _sha(w.kampanya) == _sha(w2.kampanya)
    for d in (100, 700):
        assert np.array_equal(w.lam.gun(d), w2.lam.gun(d))
        assert np.array_equal(w.plan.gun(d), w2.plan.gun(d))

    w3 = dunya_kur(Olcek.KUCUK, tedarikci_secimi=lumoda_tedarikci_secimi)
    assert np.array_equal(w.tedarikci_idx, w3.tedarikci_idx)
    assert _sha(w.urunler) == _sha(w3.urunler)


def test_politika_yalniz_kapasite_gorunumunu_gorur(kucuk_dunya):
    """Enjekte edilen politika gizli profilin yalnız kapasite görünümünü
    alır (gecikme/hatalı/maliyet sızmaz); varsayılanı saran casus aynı
    dünyayı verir."""
    gorulen: list[set] = []

    def casus(rng, optionlar, tedarikciler, kapasite, talep_tahmini):
        gorulen.append(set(kapasite.columns))
        return lumoda_tedarikci_secimi(rng, optionlar, tedarikciler, kapasite, talep_tahmini)

    w2 = dunya_kur(Olcek.KUCUK, tedarikci_secimi=casus)
    assert gorulen == [{"tedarikci_id", "kapasite_sezon_adet"}]
    assert np.array_equal(w2.tedarikci_idx, kucuk_dunya.tedarikci_idx)
    assert _sha(w2.urunler) == _sha(kucuk_dunya.urunler)


def test_ileri_plan(kucuk_dunya):
    """ileri_plan = Σ plan λ [d, d+gun) (hafta hizalı ve hizasız); option
    düzeyindeki toplamla tutarlı."""
    w = kucuk_dunya
    O = len(w.optionlar)
    for d, gun in ((700, 28), (703, 10), (0, 7), (w.plan.gun_sayisi - 5, 20)):
        bit = min(d + gun, w.plan.gun_sayisi)
        beklenen = np.zeros(len(w.cesit))
        for x in range(d, bit):
            beklenen += w.plan.gun(x)
        ip = w.ileri_plan(d, gun)
        assert np.allclose(ip, beklenen, rtol=1e-9, atol=1e-9)
        ipo = w.ileri_plan_option(d, gun)
        assert ipo.shape == (O,)
        assert np.allclose(ipo, np.bincount(w.hucre_option, weights=ip, minlength=O), rtol=1e-8)
    # önbellekten ikinci çağrı aynı sonucu verir
    assert np.array_equal(w.ileri_plan(700, 28), w.ileri_plan(700, 28))


def test_esneklik_hucre(kucuk_dunya):
    w = kucuk_dunya
    E = esneklik(w.gizli_magaza, w.optionlar)
    assert np.array_equal(w.esneklik_hucre, E[w.hucre_magaza, w.hucre_option])
    assert (w.esneklik_hucre > 0).all()


def test_mesafeler(kucuk_dunya):
    w = kucuk_dunya
    M = len(w.magazalar)
    assert w.mesafe_km.shape == (M, M)
    assert np.allclose(w.mesafe_km, w.mesafe_km.T)
    assert np.allclose(np.diag(w.mesafe_km), 0.0)
    assert w.depo_mesafe_km[-1] == 0.0  # ONL = depo
    ist = w.magazalar.index[w.magazalar.sehir == "İstanbul"]
    assert (w.depo_mesafe_km[ist] < 100).all()
    assert w.depo_mesafe_km.max() > 300  # Anadolu mağazaları


def test_sapmalar_ve_siparisler(kucuk_dunya):
    w = kucuk_dunya
    O = len(w.optionlar)
    assert w.sapma_rpt.shape == (O, 4)
    assert w.sapma_surekli.shape == (O, 128)
    assert len(w.ilk_alim) == O
    assert len(w.ilk_siparisler) == int((w.ilk_alim > 0).sum())
    assert w.gun_sayisi == len(w.takvim) - sabitler.UZATMA_GUN
    assert w.lam.gun_sayisi == len(w.takvim)
    oran = w.kampanya_takvimi(500)
    assert oran.shape == (len(w.magazalar), O)


def test_diziler_salt_okunur(kucuk_dunya):
    w = kucuk_dunya
    with pytest.raises(ValueError):
        w.hucre_magaza[0] = 1
    with pytest.raises(ValueError):
        w.ilk_alim[0] = 1
    with pytest.raises(Exception):
        w.ilk_alim = None
