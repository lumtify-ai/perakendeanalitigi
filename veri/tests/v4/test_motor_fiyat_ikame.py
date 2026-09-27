"""Testler: Görev 13 — markdown, fiyat kaydı, ikame, RPT, çıkış ve outlet akışı.

Spec: docs/superpowers/specs/2026-09-27-veri-v4-cekirdek-design.md §5.2, §5.4, §6
Brief: .superpowers/sdd/2026-09-27-veri-v4-cekirdek/task-13-brief.md
"""

import numpy as np
import pandas as pd

from perakende_veri.v4 import sabitler
from perakende_veri.v4.dunya import yolda_gun
from perakende_veri.v4.motor import simule_et
from perakende_veri.v4.motor.satis import ikame, talep_cek
from perakende_veri.v4.rastgele import sayac_uretici

KADEMELER = set(sabitler.MARKDOWN_KADEMELERI) | {0.0}


def _hat(w) -> np.ndarray:
    """[C] motorun hat eşlemesi: ONL 2, outlet akışı hücresi 1, diğerleri 0."""
    return np.where(w.hucre_online, 2, np.where(w.hucre_outlet_akisi, 1, 0))


def _gunun_md(fiyat: pd.DataFrame, gun: np.ndarray, option: np.ndarray, hat: np.ndarray) -> np.ndarray:
    """Her (gün, option, hat) için o gün geçerli markdown oranı (fiyat
    kaydının son satırı ≤ gün; kayıt yoksa 0)."""
    sorgu = pd.DataFrame({"gun": gun, "option": option, "hat": hat, "_i": np.arange(len(gun))})
    f = fiyat.sort_values("gun")[["gun", "option", "hat", "oran"]].astype({"gun": np.int64})
    sorgu = sorgu.astype({"gun": np.int64}).sort_values("gun")
    b = pd.merge_asof(sorgu, f, on="gun", by=["option", "hat"], direction="backward")
    return b.sort_values("_i")["oran"].fillna(0.0).to_numpy()


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------


def test_markdown_sigmaz(kucuk_dunya, kucuk_kosu):
    """option × hat oranı zamanla azalmaz; oranlar kademelerdendir; devamlı
    option hiç indirilmez; lansmanda başlangıç satırı (oran 0) vardır."""
    w, f = kucuk_dunya, kucuk_kosu["fiyat"]
    D = kucuk_kosu["gun_sayisi"]
    assert len(f) > 0 and (f.oran > 0).any()
    assert set(np.round(f.oran, 6)) <= KADEMELER
    f = f.sort_values(["option", "hat", "gun"], kind="stable")
    fark = f.groupby(["option", "hat"])["oran"].diff().dropna()
    assert (fark >= 0).all(), "markdown sığlaştı"
    assert (fark > 0).all(), "değişmeyen oran kaydedilmemeli"
    opt = w.optionlar
    sezonluk = opt["sezonluk"].to_numpy(dtype=bool)
    assert (f[~sezonluk[f.option.to_numpy()]].oran == 0).all()
    # Başlangıç satırları: lansman günü, hat 0 (normal) ve 2 (online), oran 0.
    lansman = opt["lansman_gun"].to_numpy()
    bas = f.groupby(["option", "hat"]).first().reset_index()
    for h in (0, 2):
        b = bas[bas.hat == h]
        hatta = np.isin(np.arange(len(opt)), w.hucre_option[_hat(w) == h])
        assert set(b.option) == set(np.flatnonzero(hatta & (lansman < D)))
        np.testing.assert_array_equal(b.gun.to_numpy(), np.maximum(lansman[b.option.to_numpy()], 0))
        assert (b.oran == 0).all()


def test_markdown_indirimde_en_az_otuz(kucuk_dunya, kucuk_kosu):
    """indirim_gun'den sonraki ilk pazartesi normal ve online hatta ≥ %30;
    iki hat aynı; indirimden 28 günden önce hiç markdown yok; düşük STR'li
    option'ların bir kısmı indirimden önce indirilir."""
    w, f = kucuk_dunya, kucuk_kosu["fiyat"]
    D = kucuk_kosu["gun_sayisi"]
    opt = w.optionlar
    ind, cik = (opt[c].to_numpy() for c in ("indirim_gun", "cikis_gun"))
    os_ = np.flatnonzero(opt["sezonluk"].to_numpy(dtype=bool))
    pzt = ind[os_] + (-ind[os_]) % 7
    ok = (pzt < cik[os_]) & (pzt < D)
    os_, pzt = os_[ok], pzt[ok]
    assert len(os_) > 20
    md0 = _gunun_md(f, pzt, os_, np.zeros(len(os_), dtype=int))
    md2 = _gunun_md(f, pzt, os_, np.full(len(os_), 2))
    assert (md0 >= 0.30 - 1e-9).all()
    np.testing.assert_array_equal(md0, md2)
    # İndirimden 28 günden önce (normal/online hat) hiç markdown yok.
    n = f[(f.hat != 1) & (f.oran > 0)]
    assert (n.gun.to_numpy() >= ind[n.option.to_numpy()] - sabitler.MARKDOWN_ONCE_GUN).all()
    # Erken indirim (indirim_gun'den önce) var ama hepsi değil (içsel kural).
    erken = n[n.gun.to_numpy() < ind[n.option.to_numpy()]].option.unique()
    assert 0 < len(erken) < len(os_)
    # Haftada en fazla bir kademe (≥ %30 tabanına sıçrama hariç).
    k = np.array(sorted(KADEMELER))
    f = f.sort_values(["option", "hat", "gun"], kind="stable")
    onceki = f.groupby(["option", "hat"])["oran"].shift().fillna(0.0).to_numpy()
    adim = np.searchsorted(k, np.round(f.oran.to_numpy(), 6)) - np.searchsorted(k, np.round(onceki, 6))
    taban = np.isclose(f.oran.to_numpy(), 0.30) | (f.hat.to_numpy() == 1)
    assert (adim[~taban] <= 1).all()


def test_outlet_hatti(kucuk_dunya, kucuk_kosu):
    """Outlet hattı: Collection option'da çıkışta %50, 4 hafta sonra %70."""
    w, f = kucuk_dunya, kucuk_kosu["fiyat"]
    opt = w.optionlar
    o1 = f[f.hat == 1]
    assert len(o1) > 0
    assert (opt["line"].to_numpy()[o1.option.to_numpy()] == "Collection").all()
    cik = opt["cikis_gun"].to_numpy()[o1.option.to_numpy()]
    t = o1.gun.to_numpy() - cik
    oran = o1.oran.to_numpy()
    assert ((t == 0) == np.isclose(oran, 0.50)).all()
    assert (np.isclose(oran[t > 0], 0.70) & (t[t > 0] == sabitler.OUTLET_MARKDOWN_ARALIK_GUN)).all()


def test_fiyat_monotonlugu(kucuk_dunya):
    """Tek gün, aynı u: oran artınca talep hiçbir hücrede azalmaz."""
    w = kucuk_dunya
    d = 400
    C = len(w.cesit)
    u = sayac_uretici(d, "talep", w.tohum).random(C)
    lam = w.lam.gun(d)
    eps = np.asarray(w.esneklik_hucre, dtype=float)
    rng = np.random.default_rng(1)
    onceki = talep_cek(u, lam, np.zeros(C), eps)
    oran = np.zeros(C)
    for _ in range(5):
        oran = np.minimum(oran + rng.choice([0.0, 0.1, 0.2], C), 0.7)
        t = talep_cek(u, lam, oran, eps)
        assert (t >= onceki).all()
        onceki = t
    assert onceki.sum() > talep_cek(u, lam, np.zeros(C), eps).sum()


# ---------------------------------------------------------------------------
# İkame
# ---------------------------------------------------------------------------


def _kayipli_gun(w, d=400):
    C = len(w.cesit)
    lam = w.lam.gun(d)
    kayip = np.where(lam > 0.2, sayac_uretici(d, "elle", 99).integers(0, 4, C), 0)
    return kayip.astype(np.int64)


def test_ikame_alici_yoksa_kayip(kucuk_dunya):
    """Bütün stok 0 → hiç ikame satışı yok, gizli kayıp = kayıp (Review Focus 2)."""
    w = kucuk_dunya
    d = 400
    C = len(w.cesit)
    kayip = _kayipli_gun(w, d)
    assert kayip.sum() > 0
    satis, gizli = ikame(np.zeros(C, dtype=np.int64), kayip, w, d)
    assert satis.sum() == 0
    np.testing.assert_array_equal(gizli, kayip)
    # Yapay grup: tek bir mağaza × alt kategori × segment grubunda stok 0,
    # başka yerde bol stok → o grubun kaybı aynen kalır.
    opt = w.optionlar
    ak = opt["alt_kategori"].to_numpy()[w.hucre_option]
    sg = opt["fiyat_segmenti"].to_numpy()[w.hucre_option]
    c0 = int(np.flatnonzero(kayip > 0)[0])
    grup = (w.hucre_magaza == w.hucre_magaza[c0]) & (ak == ak[c0]) & (sg == sg[c0])
    stok = np.where(grup, 0, 50).astype(np.int64)
    k2 = np.where(grup, kayip, 0)
    satis, gizli = ikame(stok, k2, w, d)
    assert satis.sum() == 0
    np.testing.assert_array_equal(gizli, k2)


def test_ikame_birim(kucuk_dunya):
    """Fonksiyon düzeyinde: ikame alıcının stoğunu aşmaz, alıcı stoklu, toplam
    korunur, çekiliş sayısı sabit (aynı girdi aynı sonuç)."""
    w = kucuk_dunya
    d = 400
    C = len(w.cesit)
    kayip = _kayipli_gun(w, d)
    stok = np.where(kayip > 0, 0, sayac_uretici(d, "elle", 7).integers(0, 3, C)).astype(np.int64)
    satis, gizli = ikame(stok, kayip, w, d)
    assert satis.sum() > 0
    assert (satis <= stok).all()
    assert (satis[stok == 0] == 0).all()
    assert (gizli >= 0).all() and (gizli <= kayip).all()
    assert satis.sum() + gizli.sum() == kayip.sum()
    s2, g2 = ikame(stok, kayip, w, d)
    np.testing.assert_array_equal(satis, s2)
    np.testing.assert_array_equal(gizli, g2)


def test_ikame_tek_tur_ve_stok_siniri(kucuk_dunya, kucuk_kosu):
    """Motor koşusunda: ikame alan hücre o gün kendi talebini tamamen
    karşılamıştır (stoğu kalmıştı), bu yüzden aynı (gün, hücre) hem ikame hem
    gizli kayıp taşımaz; ikame satışı satış satırına dahildir; günlük toplam
    satış + gizli kayıp = talep; hücrede satış − ikame + kayıp ≤ talep."""
    w = kucuk_dunya
    D = 420
    k = simule_et(w, gun_sayisi=D, kayit_talep=True)
    ik, kay, sat = k["ikame_satis"], k["gizli_kayip"], k["satis"]
    assert len(ik) > 0 and (ik.adet > 0).all()
    anahtar = lambda t: set(zip(t.gun.to_numpy().tolist(), t.hucre.to_numpy().tolist()))  # noqa: E731
    assert not (anahtar(ik) & anahtar(kay))
    talep = k["talep"].astype(np.int64)
    s = np.zeros_like(talep)
    ps = sat[sat.adet > 0]
    np.add.at(s, (ps.gun.to_numpy(), ps.hucre.to_numpy()), ps.adet.to_numpy())
    i = np.zeros_like(talep)
    np.add.at(i, (ik.gun.to_numpy(), ik.hucre.to_numpy()), ik.adet.to_numpy())
    g = np.zeros_like(talep)
    np.add.at(g, (kay.gun.to_numpy(), kay.hucre.to_numpy()), kay.adet.to_numpy())
    assert (s - i >= 0).all()
    assert (s - i + g <= talep).all()
    np.testing.assert_array_equal((s - i)[i > 0], talep[i > 0])
    np.testing.assert_array_equal(s.sum(axis=1) + g.sum(axis=1), talep.sum(axis=1))
    # Önek: ikame kaydı tam koşunun öneki.
    t = kucuk_kosu["ikame_satis"]
    pd.testing.assert_frame_equal(ik.reset_index(drop=True), t[t.gun < D].reset_index(drop=True))


def test_ikame_payi_bandi(kucuk_dunya, kucuk_kosu):
    """Zincir genelinde ikame ÷ (ikame + gizli kayıp) = ikame satışı ÷ ikame
    öncesi karşılanmamış talep, %10–50 (küçük ölçek geniş bant; TAM %20–40
    Görev 17). Tanı: outlet mağazaları dışındaki pay da aynı bantta."""
    w = kucuk_dunya
    ik, kay = kucuk_kosu["ikame_satis"], kucuk_kosu["gizli_kayip"]
    zincir = ik.adet.sum() / (ik.adet.sum() + kay.adet.sum())
    assert 0.10 <= zincir <= 0.50, zincir
    tip = w.magazalar["tip"].to_numpy()
    oi = tip[w.hucre_magaza[ik.hucre.to_numpy()]] == "Outlet"
    ok = tip[w.hucre_magaza[kay.hucre.to_numpy()]] == "Outlet"
    a, b = ik.adet[~oi].sum(), kay.adet[~ok].sum()
    assert 0.10 <= a / (a + b) <= 0.50, a / (a + b)


def test_ikame_sayac_bagimsizligi(kucuk_dunya):
    """Bir mağazanın stoğu değişince diğer mağazaların ikame satışı ve gizli
    kaybı bit bit aynı (grup mağaza içinde, çekiliş hücre başına)."""
    w = kucuk_dunya
    d = 400
    C = len(w.cesit)
    kayip = _kayipli_gun(w, d)
    stok = np.where(kayip > 0, 0, sayac_uretici(d, "elle", 7).integers(0, 3, C)).astype(np.int64)
    m0 = int(w.hucre_magaza[np.flatnonzero(kayip > 0)[0]])
    bu = w.hucre_magaza == m0
    stok2 = stok.copy()
    stok2[bu & (kayip == 0)] += 5
    kayip2 = np.where(bu, kayip + 1, kayip)
    s1, g1 = ikame(stok, kayip, w, d)
    s2, g2 = ikame(stok2, kayip2, w, d)
    assert not np.array_equal(s1[bu], s2[bu])
    np.testing.assert_array_equal(s1[~bu], s2[~bu])
    np.testing.assert_array_equal(g1[~bu], g2[~bu])


# ---------------------------------------------------------------------------
# Çıkış, outlet akışı
# ---------------------------------------------------------------------------


def test_outlet_akisi(kucuk_dunya, kucuk_kosu):
    """Çıkış günü normal mağaza stoğu 0; outlet mağazalarında pencere
    boyunca satış var, pencere sonrası satış yok ve stok depoya devredilir;
    çıkmış option'a depodan bir daha mal gitmez."""
    w, k = kucuk_dunya, kucuk_kosu
    D = k["gun_sayisi"]
    opt = w.optionlar
    cik = opt["cikis_gun"].to_numpy()
    col = np.flatnonzero((opt["line"] == "Collection").to_numpy() & (cik + 90 < D))
    assert len(col) > 20
    sev, sat = k["sevkiyat"], k["satis"]
    tip_m = w.magazalar["tip"].to_numpy()

    oa = sev[sev.tip == "outlet_akisi"]
    assert len(oa) > 0
    assert (oa.gun.to_numpy() == cik[w.sku_option[oa.sku.to_numpy()]]).all()
    assert (tip_m[oa.hedef.to_numpy()] == "Outlet").all()
    assert w.hucre_outlet_akisi[oa.hedef_hucre.to_numpy()].all()
    ms = oa[oa.kaynak >= 0]
    assert len(ms) > 0 and (oa.kaynak == -1).any()
    beklenen = yolda_gun(w.mesafe_km[ms.kaynak.to_numpy(), ms.hedef.to_numpy()], depo=False)
    np.testing.assert_array_equal(ms.varis_gun - ms.gun, beklenen)

    # Çıkış günü normal mağaza stoğu 0: bir çıkış gününde kesilen koşu. Raf
    # yalnız o günün müşteri iadesini taşır (ertesi gün stok devriyle depoya).
    d0 = int(np.bincount(cik[col]).argmax())
    kisa = simule_et(w, gun_sayisi=d0 + 1)
    os0 = np.flatnonzero(cik == d0)
    normal = np.isin(w.hucre_option, os0) & ~w.hucre_online & ~w.hucre_outlet_akisi
    ks = kisa["satis"]
    iade = ks[(ks.gun == d0) & (ks.adet < 0) & normal[ks.hucre.to_numpy()]]
    kalan = kisa["son_durum"]["magaza_stok"][normal]
    assert kalan.sum() == -iade.adet.sum()
    ks_sev = kisa["sevkiyat"]
    assert (ks_sev.tip == "outlet_akisi").sum() > 0
    # Ertesi gün iadeler de devredilir (stok_devri).
    kisa2 = simule_et(w, gun_sayisi=d0 + 2)
    ks2 = kisa2["satis"]
    iade2 = ks2[(ks2.gun == d0 + 1) & (ks2.adet < 0) & normal[ks2.hucre.to_numpy()]]
    assert kisa2["son_durum"]["magaza_stok"][normal].sum() == -iade2.adet.sum()
    dv = kisa2["sevkiyat"]
    dv = dv[(dv.tip == "stok_devri") & (dv.gun == d0 + 1)]
    assert dv.adet.sum() >= -iade.adet.sum()

    # Outlet penceresinde satış var, sonra yok; pencere sonunda stok 0.
    oc = w.hucre_outlet_akisi[sat.hucre.to_numpy()]
    so = sat[oc & (sat.adet > 0)]
    t = so.gun.to_numpy() - cik[w.hucre_option[so.hucre.to_numpy()]]
    assert len(so) > 0 and (t >= 0).all() and (t < sabitler.OUTLET_OMRU_GUN).all()
    bitmis = w.hucre_outlet_akisi & (cik[w.hucre_option] + sabitler.OUTLET_OMRU_GUN + 7 < D)
    assert k["son_durum"]["magaza_stok"][bitmis].sum() == 0
    devir = sev[sev.tip == "stok_devri"]
    assert len(devir) > 0 and (devir.hedef == -1).all()
    assert w.hucre_outlet_akisi[devir.kaynak_hucre.to_numpy()].any()
    # Depodan çıkmış option'a mal gitmez (outlet akışı hariç).
    depodan = sev[(sev.kaynak == -1) & (sev.hedef >= 0) & (sev.tip != "outlet_akisi")]
    assert (depodan.gun.to_numpy() < cik[w.sku_option[depodan.sku.to_numpy()]]).all()
    # ONL çıkıştan sonra satmaz.
    onl = sat[w.hucre_online[sat.hucre.to_numpy()] & (sat.adet > 0)]
    assert (onl.gun.to_numpy() < cik[w.hucre_option[onl.hucre.to_numpy()]]).all()


def test_outlet_birimleri_payi(kucuk_dunya, kucuk_kosu):
    """Outlet mağazaları hem Outlet line hem outlet akışıyla satar."""
    w, sat = kucuk_dunya, kucuk_kosu["satis"]
    s = sat[sat.adet > 0]
    tip = w.magazalar["tip"].to_numpy()[w.hucre_magaza[s.hucre.to_numpy()]]
    pay = s.adet[tip == "Outlet"].sum() / s.adet.sum()
    assert 0.02 < pay < 0.30, pay


# ---------------------------------------------------------------------------
# RPT
# ---------------------------------------------------------------------------


def test_rpt_v3_kurali(kucuk_dunya, kucuk_kosu):
    """RPT siparişleri yalnız Collection, lansman+21..42 gün arasında,
    pazartesi, option başına ≤ 1; miktar ilk alımın %50'si (MOQ, 10'un
    katı); teslim = plan + sapma_rpt[o, 0]; tedarikçi option'ınki."""
    w = kucuk_dunya
    opt = w.optionlar
    rpt = [s for s in kucuk_kosu["siparis"] if s["tip"] == "rpt"]
    assert len(rpt) > 0
    o = np.array([s["option"] for s in rpt])
    assert len(np.unique(o)) == len(o)
    assert (opt["line"].to_numpy()[o] == "Collection").all()
    h = np.array([s["siparis_gun"] for s in rpt]) - opt["lansman_gun"].to_numpy()[o]
    assert ((h >= 21) & (h <= 42)).all()
    assert all(s["siparis_gun"] % 7 == 0 for s in rpt)
    ted = np.asarray(w.tedarikci_idx)
    L = w.tedarikciler["rpt_hafta"].to_numpy()
    moq = w.tedarikciler["moq_option"].to_numpy()
    for s in rpt:
        oo = s["option"]
        assert s["tedarikci"] == ted[oo]
        assert s["planlanan_gun"] == s["siparis_gun"] + 7 * L[ted[oo]]
        assert s["gerceklesen_gun"] == s["planlanan_gun"] + int(w.sapma_rpt[oo, 0])
        miktar = int(np.sum(s["adetler"]))
        assert miktar == max(int(moq[ted[oo]]), int(np.ceil(0.5 * w.ilk_alim[oo] / 10 - 1e-9) * 10))
    # RPT teslimi kalite kaydında.
    assert (kucuk_kosu["kalite"].tip == "rpt").any()


# ---------------------------------------------------------------------------
# Kampanya markdown'ın üstünde
# ---------------------------------------------------------------------------


def test_kampanya_markdown_ustune(kucuk_dunya, kucuk_kosu):
    """Satışın indirim oranı = max(md(hücrenin hattı), kampanya) (Review Focus 5)."""
    w, sat = kucuk_dunya, kucuk_kosu["satis"]
    s = sat[sat.adet > 0]
    c = s.hucre.to_numpy()
    md = _gunun_md(kucuk_kosu["fiyat"], s.gun.to_numpy(), w.hucre_option[c], _hat(w)[c])
    s = s[md > 0]
    md = md[md > 0]
    assert len(s) > 0
    c, gun = s.hucre.to_numpy(), s.gun.to_numpy()
    kamp = np.empty(len(s))
    for d in np.unique(gun):
        m = gun == d
        kamp[m] = w.kampanya_takvimi(int(d))[w.hucre_magaza[c[m]], w.hucre_option[c[m]]]
    liste = w.urunler["liste_fiyati"].to_numpy()[w.hucre_sku[c]]
    oran = s.indirim_tutari.to_numpy() / (liste * s.adet.to_numpy())
    np.testing.assert_allclose(oran, np.maximum(md, kamp), atol=1e-3)
    ikisi = kamp > 0
    assert ikisi.any() and (kamp > md).any() and (md[ikisi] > kamp[ikisi]).any()
    # Kampanya kimliği yalnız kampanya markdown'ı aşınca.
    kid = s.kampanya_id.to_numpy()
    assert ((kid >= 0) == (kamp > md)).all()
