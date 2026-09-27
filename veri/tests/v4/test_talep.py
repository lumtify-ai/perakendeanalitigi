"""Testler: Görev 8 talep bileşenleri (λ).

Spec: docs/superpowers/specs/2026-09-27-veri-v4-cekirdek-design.md §2.3, §3.3, §5.1, §5.5
Brief: .superpowers/sdd/2026-09-27-veri-v4-cekirdek/task-8-brief.md

`dw` yerel fixture'dır: bileşenleri `Olcek.KUCUK` ile doğrudan kurar
(Görev 11 ortak `kucuk_dunya` fixture'ını ekleyince ona döner).
"""

import dataclasses
import time

import numpy as np
import pandas as pd
import pytest

from perakende_veri.v4 import sabitler
from perakende_veri.v4.cesit import cesit_ata, hucreleri_kur, kanibalizasyon_payi
from perakende_veri.v4.magaza import Olcek, alt_kume, magazalari_uret, olaylari_uret
from perakende_veri.v4.rastgele import dunya_akisi
from perakende_veri.v4.takvim import gun_indisi
from perakende_veri.v4.talep import (
    IKLIMLER,
    ALT_KATEGORILER,
    SEZON_KODLARI,
    lambda_kur,
    magaza_gun_carpani,
    mevsim_tablosu_kur,
    oznitelik_etkisi,
    yasam_egrisi,
)
from perakende_veri.v4.urun import urunleri_uret


def _dunya(olcek: Olcek) -> dict:
    """Bileşenleri tek dünya akışıyla sırayla kurar (Görev 11 sırası değil;
    burada yalnız tutarlı bir dünya gerekir)."""
    rng = dunya_akisi()
    magazalar, gizli = magazalari_uret(rng)
    olaylar = olaylari_uret(rng, magazalar, gizli)
    maske = alt_kume(magazalar, gizli, olaylar, olcek)
    magazalar = magazalar[maske].reset_index(drop=True)
    gizli = gizli[maske].reset_index(drop=True)
    olaylar = olaylar[olaylar.magaza_id.isin(magazalar.magaza_id)].reset_index(drop=True)
    urunler, optionlar = urunleri_uret(rng, olcek)
    cesit_opt = cesit_ata(rng, magazalar, gizli, optionlar)
    hucre = hucreleri_kur(cesit_opt, urunler)
    lam, gizli_talep = lambda_kur(rng, magazalar, gizli, olaylar, optionlar, urunler, hucre)
    return {
        "magazalar": magazalar,
        "gizli": gizli,
        "olaylar": olaylar,
        "urunler": urunler,
        "optionlar": optionlar,
        "hucre": hucre,
        "lam": lam,
        "gizli_talep": gizli_talep,
    }


@pytest.fixture(scope="module")
def dw():
    return _dunya(Olcek.KUCUK)


@pytest.fixture(scope="module")
def optionlar_kucuk():
    _, optionlar = urunleri_uret(dunya_akisi(), Olcek.KUCUK)
    return optionlar


OUTLET_MAGAZA_YUZDELIK = 10


def _magaza_idx(dw, magaza_id: str) -> int:
    return int(dw["magazalar"].index[dw["magazalar"].magaza_id == magaza_id][0])


# ---------------------------------------------------------------------------
# Kapalılık, kayma
# ---------------------------------------------------------------------------


def test_kapali_magazada_lambda_sifir(dw):
    """Açılış öncesi, kapanış sonrası, tadilat arası λ = 0 (fiziksel)."""
    lam, olaylar, hucre = dw["lam"], dw["olaylar"], dw["hucre"]
    kontrol = 0
    for _, r in olaylar.iterrows():
        m = _magaza_idx(dw, r.magaza_id)
        hucreler = (hucre.magaza_idx == m).to_numpy()
        o = gun_indisi(r.olay_tarihi)
        if r.olay == "acilis":
            gunler = [o - 30, o - 1]
            acik_gun = o + 10
        elif r.olay == "kapanis":
            gunler = [o, o + 30]
            acik_gun = o - 10
        else:
            b = gun_indisi(r.bitis_tarihi)
            gunler = [o, (o + b) // 2, b - 1]
            acik_gun = b + 1
        for d in gunler:
            if 0 <= d < lam.gun_sayisi:
                assert lam.gun(d)[hucreler].sum() == 0.0, (r.olay, r.magaza_id, d)
                kontrol += 1
        # açıkken gerçekten talep var (sıfırlık tesadüf değil)
        if 0 <= acik_gun < lam.gun_sayisi:
            assert lam.gun(acik_gun)[hucreler].sum() > 0.0, (r.olay, r.magaza_id, acik_gun)
    assert kontrol >= 10


def test_tadilat_kaymasi(dw):
    """Tadilat günlerinde en yakın iki mağazanın ve ONL'nin toplam λ'sı,
    tadilattaki mağazanın (karşı-olgusal) λ'sının %40'ı kadar artar (±%1).

    Artış yalnız bu olaya atfedilir: karşılaştırma, aynı mağaza-gün
    çarpanının bu tadilat olmadan kurulmuş hâliyle yapılır (alıcılar —
    özellikle ONL — kapanışlardan da kalıcı kayma alır)."""
    lam, olaylar, hucre = dw["lam"], dw["olaylar"], dw["hucre"]
    gizli_talep = dw["gizli_talep"]
    karsi = magaza_gun_carpani(
        dw["magazalar"], dw["gizli"], olaylar, magaza_toplam=None, kapalilik=False
    )
    lam_karsi = dataclasses.replace(lam, magaza_gun=karsi)
    magaza_c = hucre.magaza_idx.to_numpy()
    tadilatlar = olaylar[olaylar.olay == "tadilat"]
    assert len(tadilatlar) == 2
    for i, r in tadilatlar.iterrows():
        m = _magaza_idx(dw, r.magaza_id)
        alicilar = gizli_talep["kayma_alicilari"][r.magaza_id]
        assert len(alicilar) == 3 and alicilar[-1] == len(dw["magazalar"]) - 1  # ONL son
        assert m not in alicilar
        olaysiz = magaza_gun_carpani(
            dw["magazalar"], dw["gizli"], olaylar.drop(index=i),
            magaza_toplam=gizli_talep["gunluk_magaza_toplami"],
        )
        lam_olaysiz = dataclasses.replace(lam, magaza_gun=olaysiz)
        o, b = gun_indisi(r.olay_tarihi), gun_indisi(r.bitis_tarihi)
        for d in range(o, b, 5):
            gercek = lam.gun(d)
            onceki = lam_olaysiz.gun(d)
            kapanan = lam_karsi.gun(d)[magaza_c == m].sum()
            artis = sum(
                gercek[magaza_c == a].sum() - onceki[magaza_c == a].sum() for a in alicilar
            )
            assert kapanan > 0
            assert artis / kapanan == pytest.approx(0.40, abs=0.01 * 0.40), (r.magaza_id, d)


def test_kapanis_kaymasi(dw):
    """Kapanan mağazanın karşı-olgusal λ'sının %30'u kalıcı olarak en yakın
    iki mağazaya ve ONL'ye kayar."""
    lam, olaylar, hucre = dw["lam"], dw["olaylar"], dw["hucre"]
    gt = dw["gizli_talep"]
    karsi = magaza_gun_carpani(dw["magazalar"], dw["gizli"], olaylar, kapalilik=False)
    lam_karsi = dataclasses.replace(lam, magaza_gun=karsi)
    magaza_c = hucre.magaza_idx.to_numpy()
    kapanislar = olaylar[olaylar.olay == "kapanis"]
    assert len(kapanislar) >= 1
    karsilastirma = 0
    for i, r in kapanislar.iterrows():
        m = _magaza_idx(dw, r.magaza_id)
        alicilar = gt["kayma_alicilari"][r.magaza_id]
        olaysiz = magaza_gun_carpani(
            dw["magazalar"], dw["gizli"], olaylar.drop(index=i),
            magaza_toplam=gt["gunluk_magaza_toplami"],
        )
        lam_olaysiz = dataclasses.replace(lam, magaza_gun=olaysiz)
        o = gun_indisi(r.olay_tarihi)
        for d in (o, o + 100, o + 300):
            if d >= gun_indisi("2025-12-31"):
                continue
            gercek, onceki = lam.gun(d), lam_olaysiz.gun(d)
            kapanan = lam_karsi.gun(d)[magaza_c == m].sum()
            artis = sum(
                gercek[magaza_c == a].sum() - onceki[magaza_c == a].sum() for a in alicilar
            )
            if kapanan > 0:
                assert artis / kapanan == pytest.approx(0.30, rel=0.01), (r.magaza_id, d)
                karsilastirma += 1
    assert karsilastirma >= 3


# ---------------------------------------------------------------------------
# Mevsim, trend, yaşam eğrisi
# ---------------------------------------------------------------------------


def test_iklim_kaymasi():
    """Soğuk iklimde Mont'un Ocak/Ekim oranı ılımandakinden büyük."""
    tablo = mevsim_tablosu_kur()
    mont = ALT_KATEGORILER.index("Mont")
    ocak = gun_indisi("2024-01-15")
    ekim = gun_indisi("2024-10-15")
    ilik = IKLIMLER.index("ılıman")
    soguk = IKLIMLER.index("soguk")
    oran_ilik = tablo[ocak, ilik, mont] / tablo[ekim, ilik, mont]
    oran_soguk = tablo[ocak, soguk, mont] / tablo[ekim, soguk, mont]
    assert oran_soguk > oran_ilik > 1.0
    # sıcak sahilde yaz ürünü (Şort) tepesi daha erken: Mayıs/Ağustos oranı büyür
    sort = ALT_KATEGORILER.index("Şort")
    sicak = IKLIMLER.index("sicak_sahil")
    mayis, agustos = gun_indisi("2024-05-15"), gun_indisi("2024-08-15")
    assert (tablo[mayis, sicak, sort] / tablo[agustos, sicak, sort]) > (
        tablo[mayis, ilik, sort] / tablo[agustos, ilik, sort]
    )
    # yıllık ortalama ~1 (her iklim, her alt kategori)
    yil = slice(gun_indisi("2024-01-01"), gun_indisi("2025-01-01"))
    assert np.allclose(tablo[yil].mean(axis=0), 1.0, atol=0.03)


def test_trend_yonu(optionlar_kucuk):
    """Oversize etkisi SS23 → AW25 artıyor, slim azalıyor (bütün segmentlerde)."""
    etki, trend = oznitelik_etkisi(np.random.default_rng(7), optionlar_kucuk, sabitler.SEGMENTLER)
    assert etki.shape == (len(SEZON_KODLARI), len(sabitler.SEGMENTLER), len(optionlar_kucuk))
    assert {"sezon_kodu", "segment", "anahtar", "katsayi"} <= set(trend.columns)
    log = np.log(etki)
    kalip = optionlar_kucuk.kalip.to_numpy()
    ss23, aw25 = SEZON_KODLARI.index("SS23"), SEZON_KODLARI.index("AW25")
    for g in range(len(sabitler.SEGMENTLER)):
        def fark(s, deger):
            return log[s, g, kalip == deger].mean() - log[s, g].mean()

        assert fark(aw25, "oversize") > fark(ss23, "oversize") + 0.3
        assert fark(aw25, "slim") < fark(ss23, "slim") - 0.3


def test_yasam_egrisi_tepe():
    """Tepe h=3 (4. hafta); lansmandan 12 hafta sonra tepenin %30–40'ı."""
    opt = pd.DataFrame(
        {
            "alt_kategori": ["Tişört"],
            "sezon_kodu": ["SS24"],
            "lansman_gun": [100],
        }
    )
    egri = yasam_egrisi(opt, {"Tişört": 1.0})[:, 0]
    haftalik = egri[100::7][:20]
    assert int(np.argmax(haftalik)) == 3
    assert haftalik[3] == pytest.approx(1.0)
    assert 0.30 <= haftalik[12] <= 0.40
    assert (egri[:100] == 0).all()


# ---------------------------------------------------------------------------
# λ genel
# ---------------------------------------------------------------------------


def test_lambda_negatif_degil_sonlu(dw):
    lam = dw["lam"]
    for d in range(0, lam.gun_sayisi, 37):
        v = lam.gun(d)
        assert v.dtype == np.float64
        assert v.shape == (len(dw["hucre"]),)
        assert np.isfinite(v).all()
        assert (v >= 0).all()
    # pencere içinde anlamlı toplam talep var
    assert lam.gun(gun_indisi("2024-05-15")).sum() > 0


def test_online_payi_kaba(dw):
    """ONL λ toplamı / toplam λ, bir yıl üzerinden %12–25."""
    lam = dw["lam"]
    onl = len(dw["magazalar"]) - 1
    onl_hucre = (dw["hucre"].magaza_idx == onl).to_numpy()
    toplam = onl_top = 0.0
    for d in range(gun_indisi("2024-01-01"), gun_indisi("2025-01-01")):
        v = lam.gun(d)
        toplam += v.sum()
        onl_top += v[onl_hucre].sum()
    assert 0.12 <= onl_top / toplam <= 0.25


def _yillik(dw, yil: str = "2024"):
    """Bir yılın gün indisleri (yardımcı)."""
    return range(gun_indisi(f"{yil}-01-01"), gun_indisi(f"{int(yil) + 1}-01-01"))


def test_online_payi_kategori(dw):
    """Her üst kategoride ONL'nin yıllık λ payı %12–25."""
    lam, hucre, optionlar = dw["lam"], dw["hucre"], dw["optionlar"]
    onl = (hucre.magaza_idx == len(dw["magazalar"]) - 1).to_numpy()
    ust = optionlar.ust_kategori.to_numpy()[hucre.option_idx.to_numpy()]
    kod, kategoriler = pd.factorize(ust)
    top = np.zeros(len(kategoriler))
    onl_top = np.zeros(len(kategoriler))
    for d in _yillik(dw):
        v = lam.gun(d)
        top += np.bincount(kod, weights=v, minlength=len(kategoriler))
        onl_top += np.bincount(kod[onl], weights=v[onl], minlength=len(kategoriler))
    pay = dict(zip(kategoriler, onl_top / top))
    assert all(0.12 <= p <= 0.25 for p in pay.values()), pay


def outlet_akisi_talebi(w, D: int) -> tuple[float, np.ndarray]:
    """(Beklenen outlet akışı talebi, sayılan option maskesi [O]): penceresi
    [cikis, cikis+84) D içinde biten Collection option'larının outlet akışı
    hücrelerinde Σ λ × (1 − md)^(−ε), md Lumoda'nın outlet hattı takvimi
    (çıkışta %50, 28 günde bir kademe, en çok %70), ε hücrenin esnekliği
    (outlet segmenti dahil). Kampanya oranı ≤ %40 < md: fiyatı md belirler."""
    opt = w.optionlar
    cik = opt["cikis_gun"].to_numpy()
    sayilan = (opt["line"] == "Collection").to_numpy() & (cik + sabitler.OUTLET_OMRU_GUN <= D)
    oc = np.flatnonzero(w.hucre_outlet_akisi & sayilan[w.hucre_option])
    eps = np.asarray(w.esneklik_hucre)[oc]
    ci = cik[w.hucre_option[oc]]
    k = np.asarray(sabitler.MARKDOWN_KADEMELERI)
    bas = int(np.searchsorted(k, sabitler.OUTLET_MARKDOWN_BASLANGIC - 1e-9))
    toplam = 0.0
    for d in range(max(int(ci.min()), 0), D):
        t = d - ci
        m = (t >= 0) & (t < sabitler.OUTLET_OMRU_GUN)
        if not m.any():
            continue
        md = k[np.minimum(bas + t[m] // sabitler.OUTLET_MARKDOWN_ARALIK_GUN, len(k) - 1)]
        toplam += float((w.lam.gun(d)[oc[m]] * (1.0 - md) ** (-eps[m])).sum())
    return toplam, sayilan


def test_outlet_akisi_canli(kucuk_dunya, kucuk_kosu):
    """Outlet akışı talebi indirimli fiyatta kalibre (Görev 13 fix):
    tam KÜÇÜK koşuda pencerelerdeki fiyat etkili outlet akışı talebi,
    `outlet_akisi` ile gelen adedin 0,8–1,2 katı (liste fiyatında
    kalibre edilseydi outlet hattının %50–70 indirimi talebi ~10 kat
    şişirirdi)."""
    w, k = kucuk_dunya, kucuk_kosu
    talep, sayilan = outlet_akisi_talebi(w, k["gun_sayisi"])
    sev = k["sevkiyat"]
    oa = sev[sev.tip == "outlet_akisi"]
    gelen = oa.adet[sayilan[w.sku_option[oa.sku.to_numpy()]]].sum()
    assert gelen > 0
    assert 0.8 <= talep / gelen <= 1.2, (talep, gelen)


def test_outlet_magaza_hacmi(dw):
    """Hiçbir outlet mağazasının yıllık (liste fiyatı) λ'sı fiziksel
    mağazaların OUTLET_MAGAZA_YUZDELIK. yüzdeliğinin altında değil."""
    lam, hucre, magazalar = dw["lam"], dw["hucre"], dw["magazalar"]
    m_c = hucre.magaza_idx.to_numpy()
    outlet_m = magazalar.index[magazalar.tip == "Outlet"].to_numpy()
    assert len(outlet_m)
    M = len(magazalar)
    magaza_yil = np.zeros(M)
    for d in _yillik(dw):
        magaza_yil += np.bincount(m_c, weights=lam.gun(d), minlength=M)
    fiziksel = (magazalar.tip != "Online").to_numpy()
    tam_yil = fiziksel & (magaza_yil > 0)
    esik = np.percentile(magaza_yil[tam_yil], OUTLET_MAGAZA_YUZDELIK)
    assert (magaza_yil[outlet_m] >= esik).all(), (magaza_yil[outlet_m], esik)


def test_mevsim_line_ussu():
    """Basic/NOS'un mevsim genliği Collection'ınkinden küçük; ortalama 1."""
    yil = slice(gun_indisi("2024-01-01"), gun_indisi("2025-01-01"))
    mont = ALT_KATEGORILER.index("Mont")
    ilik = IKLIMLER.index("ılıman")
    tam = mevsim_tablosu_kur(sabitler.MEVSIM_LINE_USSU["Collection"])[yil, ilik, mont]
    nos = mevsim_tablosu_kur(sabitler.MEVSIM_LINE_USSU["NOS"])[yil, ilik, mont]
    assert nos.max() / nos.min() < tam.max() / tam.min()
    assert nos.mean() == pytest.approx(1.0, abs=0.03)


def test_deterministik(dw):
    """Aynı tohum aynı λ'yı verir (çekiliş sırası sabit)."""
    ikinci = _dunya(Olcek.KUCUK)
    for d in (50, 600, 1200):
        np.testing.assert_array_equal(dw["lam"].gun(d), ikinci["lam"].gun(d))


def test_kanib_cekiciliksiz(dw):
    """Kanibalizasyon payı yalnız n^β/n: `lam.kanib(d)`, çekicilik 1 ile
    kurulmuş `kanibalizasyon_payi`'yla birebir (sürpriz × öznitelik payda
    ikinci kez sayılmaz)."""
    assert "cekicilik" not in dw["gizli_talep"]
    O = len(dw["optionlar"])
    beklenen = kanibalizasyon_payi(dw["hucre"], dw["optionlar"], np.ones(O))
    for d in (60, 250, 480, 700, 900, 1150, 1300):
        np.testing.assert_array_equal(dw["lam"].kanib(d), beklenen(d))


def test_surpriz_bir_kez_sayilir(dw, monkeypatch):
    """Bir option'ın sürprizi 2 katına çıkarılıp dünya yeniden kurulunca
    aynı (mağaza, alt kategori) grubundaki DİĞER option'ların λ'sı
    değişmez (eski çift sayımda grup payı sürprizin ortalamasına bölünüyor,
    komşular düşüyordu); option'ın kendi λ'sı tam 2 katına çıkar.

    Yalnız olay kayması almayan/vermeyen fiziksel mağazalara bakılır: ONL
    kalibrasyonu ve kayma oranları λ toplamlarından türer, orada ikinci
    dereceden oynar."""
    from perakende_veri.v4 import talep

    opt, hucre, lam = dw["optionlar"], dw["hucre"], dw["lam"]
    olayli = set(dw["gizli_talep"]["kayma_alicilari"])
    for alicilar in dw["gizli_talep"]["kayma_alicilari"].values():
        olayli |= {dw["magazalar"].magaza_id.iloc[a] for a in alicilar}
    temiz_m = np.flatnonzero(
        (~dw["magazalar"].magaza_id.isin(olayli) & (dw["magazalar"].tip != "Online")).to_numpy()
    )
    alt = opt["alt_kategori"].to_numpy()
    m_c, o_c = hucre.magaza_idx.to_numpy(), hucre.option_idx.to_numpy()
    temiz_c = np.isin(m_c, temiz_m)

    # Temiz bir mağazada o gün kendisi ve grup komşuları talep gören ilk
    # Collection option'ı seç (dünya yeniden kurulmadan önce).
    secim = None
    for o in np.flatnonzero((opt["line"] == "Collection").to_numpy()):
        d = int(opt.at[o, "lansman_gun"]) + 10
        v = lam.gun(d)
        magazalar_o = np.unique(m_c[(o_c == o) & temiz_c & (v > 0)])
        grup = np.isin(m_c, magazalar_o) & (alt[o_c] == alt[o])
        kendi, komsu = grup & (o_c == o), grup & (o_c != o) & (v > 0)
        if kendi.any() and komsu.any():
            secim = (int(o), d, kendi, komsu)
            break
    assert secim is not None
    o, d, kendi, komsu = secim
    orijinal = talep.surpriz

    def iki_kat(rng, optionlar):
        s = orijinal(rng, optionlar)
        s[o] *= 2.0
        return s

    monkeypatch.setattr(talep, "surpriz", iki_kat)
    ikinci = _dunya(Olcek.KUCUK)
    assert ikinci["gizli_talep"]["surpriz"][o] == 2.0 * dw["gizli_talep"]["surpriz"][o]
    a, b = lam.gun(d), ikinci["lam"].gun(d)
    np.testing.assert_allclose(b[kendi], 2.0 * a[kendi], rtol=1e-12)
    np.testing.assert_allclose(b[komsu], a[komsu], rtol=1e-12)


# ---------------------------------------------------------------------------
# Hız (tam ölçek)
# ---------------------------------------------------------------------------


@pytest.mark.yavas
def test_gun_hizi_tam():
    """`gun(d)` tam ölçek hücre sayısında 50 gün ortalaması < 15 ms."""
    tam = _dunya(Olcek.TAM)
    lam = tam["lam"]
    gunler = list(range(gun_indisi("2024-03-01"), gun_indisi("2024-03-01") + 50))
    lam.gun(gunler[0] - 1)  # ısınma
    bas = time.perf_counter()
    for d in gunler:
        lam.gun(d)
    ort_ms = (time.perf_counter() - bas) / len(gunler) * 1000
    print(f"\nC={len(tam['hucre'])}, gun(d) ort {ort_ms:.2f} ms")
    assert ort_ms < 15.0
