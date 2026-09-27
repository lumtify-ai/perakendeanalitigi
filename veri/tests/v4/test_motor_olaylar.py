"""Testler: Görev 14 — mağaza olayları (açılış, kapanış, tadilat) ve bölge
müdürünün elle transferleri.

Spec: docs/superpowers/specs/2026-09-27-veri-v4-cekirdek-design.md §6.2, §6.3, §8.3
Brief: .superpowers/sdd/2026-09-27-veri-v4-cekirdek/task-14-brief.md
"""

import dataclasses

import numpy as np
import pandas as pd

from perakende_veri.v4 import sabitler
from perakende_veri.v4.dunya import yolda_gun
from perakende_veri.v4.motor import simule_et
from perakende_veri.v4.motor.durum import magaza_takvimi
from perakende_veri.v4.politika import LumodaElleTransfer, Politikalar, lumoda_politikalari
from perakende_veri.v4.takvim import gun_indisi

from .test_motor_iskelet import _defter_dogrula, _onek_esit


def _indis(w, mid: str) -> int:
    return int(np.flatnonzero(w.magazalar["magaza_id"].to_numpy() == mid)[0])


def _olaylar(w, olay: str):
    return w.magaza_olay[w.magaza_olay.olay == olay]


# ---------------------------------------------------------------------------
# Kapalı mağaza
# ---------------------------------------------------------------------------


def test_kapali_magazada_satis_yok(kucuk_dunya, kucuk_kosu):
    """Açılış öncesi, kapanış sonrası ve tadilat arasında satış ve talep 0
    (pozitif satış satırı da kayıp satırı da yok; iade negatif satırdır ve
    kapalı mağazada depoya döner)."""
    w, k = kucuk_dunya, kucuk_kosu
    D = k["gun_sayisi"]
    acik, _ = magaza_takvimi(w, D)
    hm = w.hucre_magaza
    sat = k["satis"]
    pozitif = sat[sat.adet > 0]
    assert not (~acik[pozitif.gun.to_numpy(), hm[pozitif.hucre.to_numpy()]]).any()
    kay = k["gizli_kayip"]
    assert not (~acik[kay.gun.to_numpy(), hm[kay.hucre.to_numpy()]]).any()
    # Takvimde gerçekten kapalı günler var (açılış, kapanış, tadilat)
    for olay in ("acilis", "kapanis", "tadilat"):
        assert len(_olaylar(w, olay)) > 0
    # Kapalı mağazanın iadesi rafa değil depoya
    iade = sat[sat.adet < 0]
    kapali_iade = iade[~acik[iade.gun.to_numpy(), hm[iade.hucre.to_numpy()]]]
    if len(kapali_iade):
        sev = k["sevkiyat"]
        assert (sev.tip == "iade_depoya").sum() > 0


# ---------------------------------------------------------------------------
# Kapanış
# ---------------------------------------------------------------------------


def test_kapanis_sonrasi_stok_sifir(kucuk_dunya, kucuk_kosu):
    """Kapanış gününden sonra mağazanın raf stoğu her fotoğrafta 0 (Review
    Focus 1); bütün stok kapanış günü `kapanis_transferi` ile depoya gider,
    günlük `stok_devri` taraması kapanan mağazayı hiç yakalamaz."""
    w, k = kucuk_dunya, kucuk_kosu
    D = k["gun_sayisi"]
    sev, stok = k["sevkiyat"], k["stok"]
    hm = w.hucre_magaza
    y_m = yolda_gun(w.depo_mesafe_km, depo=True)
    for r in _olaylar(w, "kapanis").itertuples():
        m, kg = _indis(w, r.magaza_id), gun_indisi(r.olay_tarihi)
        if kg >= D:
            continue
        # Kapanış günü öncesinde stok vardı; kapanış transferi onu taşır.
        once = stok[(stok.gun < kg) & (hm[stok.hucre.to_numpy()] == m)]
        assert once.adet.sum() > 0
        kt = sev[(sev.tip == "kapanis_transferi") & (sev.kaynak == m)]
        assert len(kt) > 0
        assert (kt.gun == kg).all() and (kt.hedef == -1).all()
        assert (kt.varis_gun - kt.gun == y_m[m]).all()
        # Kapanış gününden sonra her fotoğrafta 0
        sonra = stok[(stok.gun > kg) & (hm[stok.hucre.to_numpy()] == m)]
        assert (sonra.adet == 0).all()
        assert k["son_durum"]["magaza_stok"][hm == m].sum() == 0
        assert k["son_durum"]["yolda_hucre"][hm == m].sum() == 0
        # Kapanıştan sonra mağazadan yalnız aynı gün depoya dönüşler çıkar
        cikan = sev[(sev.kaynak == m) & (sev.gun >= kg)]
        assert set(cikan.tip) <= {"kapanis_transferi", "geri_yonlendirme", "iade_depoya"}
        # Mağazaya kapanıştan sonra hiçbir sevk yola çıkmaz
        assert len(sev[(sev.hedef == m) & (sev.gun >= kg)]) == 0


def _tasinmis_kapanis(w, mid: str, gun: pd.Timestamp):
    """Dünyanın kopyası: `mid` kapanışı `gun`e taşınır, karar aynı gün
    (karardan önceki pazartesi replenishment'ı hâlâ gider)."""
    mag = w.magazalar.copy()
    mag.loc[mag.magaza_id == mid, "kapanis_tarihi"] = gun
    olay = w.magaza_olay.copy()
    sec = (olay.magaza_id == mid) & (olay.olay == "kapanis")
    olay.loc[sec, "olay_tarihi"] = gun
    olay.loc[sec, "karar_tarihi"] = gun
    return dataclasses.replace(w, magazalar=mag, magaza_olay=olay)


def test_kapanan_magazaya_yolda_mal_depoya(kucuk_dunya):
    """Yapay: kapanıştan 1 gün önce (pazartesi, karar henüz verilmemiş) yola
    çıkan replenishment kapanış günü varır → aynı gün depoya
    (`geri_yonlendirme`); raf stoğu kapanıştan sonra 0, defter tutar."""
    w0 = kucuk_dunya
    mid = "M004"
    m = _indis(w0, mid)
    y = int(yolda_gun(w0.depo_mesafe_km, depo=True)[m])
    gercek = gun_indisi(_olaylar(w0, "kapanis").set_index("magaza_id").at[mid, "olay_tarihi"])
    pazartesi = gercek - 7                       # gerçek kapanış pazartesi
    assert pd.Timestamp(w0.takvim["tarih"].iloc[pazartesi]).dayofweek == 0
    kg = pazartesi + y
    w = _tasinmis_kapanis(w0, mid, w0.takvim["tarih"].iloc[kg])
    k = simule_et(w, gun_sayisi=kg + 10)
    sev = k["sevkiyat"]
    rep = sev[(sev.tip == "replenishment") & (sev.hedef == m) & (sev.gun == pazartesi)]
    assert len(rep) > 0 and (rep.varis_gun == kg).all()
    geri = sev[(sev.tip == "geri_yonlendirme") & (sev.kaynak == m) & (sev.gun == kg)]
    rep_h = rep.groupby("hedef_hucre").adet.sum()
    geri_h = geri.groupby("kaynak_hucre").adet.sum()
    assert (geri_h.reindex(rep_h.index).fillna(0) >= rep_h).all()
    assert (geri.hedef == -1).all() and (geri.varis_gun == kg).all()
    kt = sev[(sev.tip == "kapanis_transferi") & (sev.kaynak == m)]
    assert len(kt) > 0 and (kt.gun == kg).all()
    hm = w.hucre_magaza
    stok = k["stok"]
    assert (stok[(stok.gun > kg) & (hm[stok.hucre.to_numpy()] == m)].adet == 0).all()
    assert k["son_durum"]["magaza_stok"][hm == m].sum() == 0
    _defter_dogrula(w, k)


def test_kapanacaga_replenishment_yok(kucuk_dunya, kucuk_kosu):
    """Karar gününden itibaren kapanacak mağazaya replenishment, ilk dağıtım,
    açılış ve elle transfer gitmez; o mağaza elle transfer kaynağı da olmaz."""
    w, sev = kucuk_dunya, kucuk_kosu["sevkiyat"]
    for r in _olaylar(w, "kapanis").itertuples():
        m, karar = _indis(w, r.magaza_id), gun_indisi(r.karar_tarihi)
        once = sev[(sev.hedef == m) & (sev.gun < karar) & (sev.tip == "replenishment")]
        assert len(once) > 0
        sonra = sev[(sev.hedef == m) & (sev.gun >= karar)]
        assert not sonra.tip.isin(
            ["replenishment", "ilk_dagitim", "acilis_transferi", "elle_transfer", "outlet_akisi"]
        ).any()
        assert len(sev[(sev.kaynak == m) & (sev.gun >= karar) & (sev.tip == "elle_transfer")]) == 0


# ---------------------------------------------------------------------------
# Açılış
# ---------------------------------------------------------------------------


def _acilis_orani(w, k, m: int, a: int) -> float:
    """Açılışın ilk haftasında mağazaya varan mal ÷ açılış gününün 28 günlük
    plan hedefi (mağazanın o gün penceresi açık fiziksel hücreleri)."""
    sev = k["sevkiyat"]
    varan = sev[(sev.hedef == m) & (sev.varis_gun >= a) & (sev.varis_gun < a + 7)].adet.sum()
    c = (w.hucre_magaza == m) & (w.hucre_acilis <= a) & (a < w.hucre_kapanis)
    hedef = w.ileri_plan(a, sabitler.REPL_HEDEF_GUN)[c].sum()
    return float(varan / hedef)


def test_acilis_transferi(kucuk_dunya, kucuk_kosu):
    """Açılış transferi yalnız depodan, açılıştan yolda süre kadar önce yola
    çıkar ve açılış günü varır; mağazalardan hiçbir şey almaz."""
    w, k = kucuk_dunya, kucuk_kosu
    sev = k["sevkiyat"]
    y_m = yolda_gun(w.depo_mesafe_km, depo=True)
    at = sev[sev.tip == "acilis_transferi"]
    assert (at.kaynak == -1).all()
    for r in _olaylar(w, "acilis").itertuples():
        m, a = _indis(w, r.magaza_id), gun_indisi(r.olay_tarihi)
        if a >= k["gun_sayisi"]:
            continue
        bu = at[at.hedef == m]
        assert len(bu) > 0, r.magaza_id
        assert (bu.gun == a - y_m[m]).all() and (bu.varis_gun == a).all()
        # Açılıştan önce mağazaya mal varmaz (varsa depoya döner)
        assert len(sev[(sev.hedef == m) & (sev.varis_gun < a)]) == 0
    assert len(sev[(sev.tip == "acilis_transferi") & (sev.kaynak >= 0)]) == 0


def test_sezon_ortasi_acilis_ince(kucuk_dunya, kucuk_kosu):
    """Sezon ortası açılışta ilk hafta varan mal ÷ plan hedefi, sezon başı
    açılıştakinden küçük (depo ince: ilk alım dağıtılmış)."""
    w, k = kucuk_dunya, kucuk_kosu
    lansmanlar = set(pd.to_datetime(w.sezon.loc[w.sezon.dalga == 1, "lansman_tarihi"]))
    bas, orta = [], []
    for r in _olaylar(w, "acilis").itertuples():
        m, a = _indis(w, r.magaza_id), gun_indisi(r.olay_tarihi)
        if a + 7 > k["gun_sayisi"]:
            continue
        (bas if pd.Timestamp(r.olay_tarihi) in lansmanlar else orta).append(_acilis_orani(w, k, m, a))
    assert len(bas) >= 1 and len(orta) >= 2, (bas, orta)
    assert np.mean(orta) < np.mean(bas), (bas, orta)


def test_yeni_magaza_replenishment_alir(kucuk_dunya, kucuk_kosu):
    """Açılıştan sonraki 28 gün hücreler "yeni" sayılır: yeni mağazanın
    devamlı (Basic/NOS) hücreleri satış hızı 0 iken de replenishment alır."""
    w, k = kucuk_dunya, kucuk_kosu
    sev = k["sevkiyat"]
    sezonluk = w.optionlar["sezonluk"].to_numpy(dtype=bool)
    for r in _olaylar(w, "acilis").itertuples():
        m, a = _indis(w, r.magaza_id), gun_indisi(r.olay_tarihi)
        if a + 28 > k["gun_sayisi"]:
            continue
        rep = sev[(sev.tip == "replenishment") & (sev.hedef == m) & (sev.gun >= a) & (sev.gun < a + 28)]
        assert len(rep) > 0, r.magaza_id
        assert (~sezonluk[w.hucre_option[rep.hedef_hucre.to_numpy()]]).any(), r.magaza_id


# ---------------------------------------------------------------------------
# Tadilat
# ---------------------------------------------------------------------------


def test_tadilat_stok_bekler(kucuk_dunya, kucuk_kosu):
    """Tadilat başı ve sonu (pazartesi fotoğrafları) raf stoğu eşit: satış,
    varış, iade ve transfer yok (penceresi tadilat boyunca açık hücreler)."""
    w, k = kucuk_dunya, kucuk_kosu
    stok, sev = k["stok"], k["sevkiyat"]
    hm = w.hucre_magaza
    for r in _olaylar(w, "tadilat").itertuples():
        m, bas, bit = _indis(w, r.magaza_id), gun_indisi(r.olay_tarihi), gun_indisi(r.bitis_tarihi)
        if bit >= k["gun_sayisi"]:
            continue
        c = np.flatnonzero((hm == m) & (w.hucre_acilis <= bas) & (bit < w.hucre_kapanis))
        s0 = stok[stok.gun == bas].set_index("hucre").adet.reindex(c).fillna(0).astype(np.int64)
        s1 = stok[stok.gun == bit].set_index("hucre").adet.reindex(c).fillna(0).astype(np.int64)
        assert s0.sum() > 0
        pd.testing.assert_series_equal(s0, s1, check_names=False)
        # Tadilat süresince mağazadan transfer çıkmaz (yalnız aynı gün depoya dönüşler)
        ara = sev[(sev.kaynak == m) & (sev.gun >= bas) & (sev.gun < bit)]
        assert set(ara.tip) <= {"geri_yonlendirme", "iade_depoya"}
        assert len(sev[(sev.hedef == m) & (sev.gun >= bas) & (sev.gun < bit)
                       & (sev.tip != "outlet_akisi")]) == 0
        # Bitişten sonra replenishment yeniden başlar
        assert len(sev[(sev.hedef == m) & (sev.gun >= bit) & (sev.tip == "replenishment")]) > 0


# ---------------------------------------------------------------------------
# Elle transfer
# ---------------------------------------------------------------------------


def test_elle_transfer_ayni_bolge(kucuk_dunya, kucuk_kosu):
    """Pazartesi, aynı bölgede iki farklı açık, kapanış kararsız mağaza
    arasında; bölge × hafta başına en çok 3 (kaynak, option); kaynak
    option'ın bütün bedenlerini gönderir."""
    w, k = kucuk_dunya, kucuk_kosu
    sev = k["sevkiyat"]
    el = sev[sev.tip == "elle_transfer"].copy()
    assert len(el) > 0
    bolge = w.magazalar["bolge"].to_numpy()
    assert (el.kaynak >= 0).all() and (el.hedef >= 0).all() and (el.kaynak != el.hedef).all()
    assert (bolge[el.kaynak] == bolge[el.hedef]).all()
    tarih = pd.DatetimeIndex(w.takvim["tarih"].iloc[el.gun.to_numpy()])
    assert (tarih.dayofweek == 0).all()
    acik, kapanacak = magaza_takvimi(w, k["gun_sayisi"])
    for sut in ("kaynak", "hedef"):
        assert acik[el.gun, el[sut]].all() and not kapanacak[el.gun, el[sut]].any()
    el["option"] = w.sku_option[el.sku.to_numpy()]
    el["bolge"] = bolge[el.kaynak]
    secim = el.groupby(["gun", "bolge"])[["kaynak", "option"]].apply(
        lambda x: len(x.drop_duplicates()))
    assert secim.max() <= sabitler.ELLE_TRANSFER_MAKS
    # Seçilen (kaynak, option) o gün stoğunun tamamını gönderdi: kaynak
    # hücre, transferden sonra 0 (pazartesi fotoğrafı transferden önce).
    # Kaynağın son 28 günde satışı 0 ve stoğu ≥ 3.
    sat = k["satis"]
    ho = w.hucre_option
    for (gun, m, o), grup in el.groupby(["gun", "kaynak", "option"]):
        assert grup.adet.sum() >= sabitler.ELLE_STOK_ESIGI
        c = np.flatnonzero((w.hucre_magaza == m) & (ho == o))
        s = sat[sat.hucre.isin(c) & (sat.gun >= gun - 28) & (sat.gun < gun) & (sat.adet > 0)]
        assert len(s) == 0


def test_elle_transfer_deterministik(kucuk_dunya):
    """Aynı çekilişlerle aynı seçim; politika varsayılandır ve sınıf örneğidir."""
    assert isinstance(lumoda_politikalari()["elle_transfer"], LumodaElleTransfer)
    w = kucuk_dunya
    n = 200
    a = simule_et(w, gun_sayisi=n)
    b = simule_et(w, Politikalar(elle_transfer=LumodaElleTransfer()), gun_sayisi=n)
    pd.testing.assert_frame_equal(a["sevkiyat"], b["sevkiyat"])
    assert (a["sevkiyat"].tip == "elle_transfer").sum() > 0


# ---------------------------------------------------------------------------
# Önek ve defter
# ---------------------------------------------------------------------------


def test_olay_sinirlarinda_onek(kucuk_dunya, kucuk_kosu):
    """Kapanış günü ve tadilat sınırlarında kesilen koşu tam koşunun öneki."""
    w = kucuk_dunya
    kesimler = set()
    for r in _olaylar(w, "kapanis").itertuples():
        g = gun_indisi(r.olay_tarihi)
        kesimler |= {g, g + 1}
    for r in _olaylar(w, "tadilat").itertuples():
        kesimler |= {gun_indisi(r.olay_tarihi), gun_indisi(r.bitis_tarihi) + 1}
    for n in sorted(kesimler)[:6]:
        if 0 < n <= w.gun_sayisi:
            _onek_esit(simule_et(w, gun_sayisi=n), kucuk_kosu, n, ("satis", "sevkiyat", "depo_stok", "stok"))


def test_olaylarla_defter(kucuk_dunya, kucuk_kosu):
    """Yeni sevkiyat tipleri (açılış, kapanış, elle transfer) deftere girer."""
    tipler = set(kucuk_kosu["sevkiyat"].tip)
    assert {"acilis_transferi", "kapanis_transferi", "elle_transfer"} <= tipler
    _defter_dogrula(kucuk_dunya, kucuk_kosu)
