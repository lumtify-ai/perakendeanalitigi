"""Testler: Görev 17 kalibrasyon bantları (tam ölçek, spec §8.2, §8.4).

Spec: docs/superpowers/specs/2026-09-27-veri-v4-cekirdek-design.md §8.2, §8.4
Brief: .superpowers/sdd/2026-09-27-veri-v4-cekirdek/task-17-brief.md

Bütün testler `yavas` işaretli ve oturum fixture'ı `tam_kosu`'yu (conftest:
TAM `tablolari_uret(donus_ham=True)` bir kez) paylaşır. Ölçütler bir kez,
modül fixture'ı `olcut`'te hesaplanır ve `-s` ile tablo olarak basılır
(kalibrasyon günlüğü için).

**Ölçüt tanımları** (controller kararları; bantlar spec §8.2 birebir):

online payı
    ONL net cirosu (Σ `satis.tutar`, iade satırları dahil) ÷ zincirin net
    cirosu, 2023, 2024, 2025 her yıl ayrı; her yıl %15–20.

online iade
    ONL iade adedi (−adet satırları) ÷ ONL brüt satış adedi (+adet
    satırları), bütün pencere; %25–30.

Collection sezon sonu tam fiyat STR
    Tam sezonu pencerede olan SS23, AW23, SS24, AW24, SS25 Collection
    option'ları. Pay: bu option'ların fiziksel mağaza + ONL'deki, çıkış
    gününden önceki, tam fiyatlı brüt satış adedi. Tam fiyatlı satış =
    etiket fiyatından satış: o gün option'ın hattında markdown yok (fiyat
    tablosu: hattın o haftaki `indirim_orani` 0; markdown hiç sığlaşmaz,
    ilk markdown haftasından önce) ve kampanya yok. Rastgele işlem
    indirimi (`ISLEM_INDIRIM_OLASILIGI`) tam fiyat sayılır: sadakat /
    personel / kupon gibi işlem düzeyinde bir indirimdir, etiket fiyatını
    değiştirmez. Sektör kullanımında tam fiyat STR etiket fiyatındaki
    satışı markdown satışından ayırır; işlem indirimi bu ayrımın
    konusu değildir (controller kararı; `indirim_tutari == 0` tanımı
    işlem indirimli satışı da dışlıyordu, ~%8 — yalnız basılır). Payda: bu option'ların teslim
    alınmış ilk alım + RPT sipariş adedi (`siparis`, tip `ilk`/`rpt`,
    `gerceklesen_teslim` dolu) — "alınanın ne kadarı tam fiyata satıldı".
    Neden alınan: pay ONL'yi içerir, ONL depodan satar; "mağazalara
    gönderilen" paydası ONL'nin kaynağını (depoda kalan pay) saymaz ve
    oranı şişirir; ayrıca depoda kalıp outlet'e akan mal da (sezon sonu
    artığı) alınanın parçasıdır. Mağazalara gönderilen paydalı alternatif
    (fiziksel mağaza tam fiyat satışı ÷ depodan mağazalara giden ilk
    dağıtım + replenishment + açılış transferi) yalnız basılır. Bant
    %55–70 alınan paydalı tanıma uygulanır.

bulunabilirlik
    Pazartesi `stok` fotoğraflarından: Σ `stoklu_gun` ÷ Σ açık gün;
    açık gün = satırın kapsadığı d−7…d−1 günlerinden hücrenin kendi
    penceresinde [açılış, kapanış) ve mağazanın açık olduğu günler. Pay
    satır başına açık günle kırpılır — bu bir YAKLAŞIKLIKTIR: `stoklu_gun`
    günleri ayırmaz. Tadilat / kapanış haftalarında mağaza kapalıyken
    rafta mal varsa bayrak o günleri de stoklu sayar (açık gün 0 olduğu
    için kırpılır, ama kısmi haftada hangi günün stoklu olduğu
    bilinmez); pencere hafta ortasında biterse son kısmi hafta hiç
    fotoğraflanmaz (pazartesi satırı yok), ortasında başlayan ilk haftanın
    pencere öncesi günleri paydada yoktur. Etkisi küçüktür (2 tadilat, 4
    kapanış; pencere sınırları çoğunlukla pazartesi). Yalnız fiziksel mağaza hücreleri,
    line'a göre; Basic + NOS birlikte %85–95, Collection %70–85. Outlet
    akışı hücreleri (çıkıştan sonra outlet mağazasına akan Collection
    artığı) Collection'a girmez: bunlar mağazanın taşıması beklenen çeşit
    değil, artık stoğun tasfiyesidir (dahil hâli basılır). Kaynak: `ham`
    stok kaydı (yayımlanan `stok`un kirletilmemiş hâli; hayalet stok
    kayıtları ölçütü bozmasın diye).

ikame payı
    Gizli: ikame satışı ÷ ikame öncesi karşılanmamış talep = Σ ikame_satis
    ÷ (Σ ikame_satis + Σ kayip_satis) (`gizli_gercek`; kayıp ikameden
    sonra kalan kalıcı kayıptır), zincir, bütün pencere; %20–40.

plan hatası
    Option düzeyi (Collection, SS23…AW25): option'ın indirim öncesi sezon
    toplamı [lansman, indirim) üzerinden Lumoda'nın plan λ'sı ile gizli
    gerçek λ (ikisi de liste fiyatında; plan indirim inancı yalnız
    indirimden sonra devreye girer); MAPE = ortalama |plan − gerçek| ÷
    gerçek; %40–55. Kategori × ay (SS24 ve AW24, her biri ayrı bantta
    %10–20): sezonun sezonluk option'larının (Collection + Outlet) bütün
    ömrü, ikisi de planlanan indirim yolunda (plan λ inancıyla, gerçek λ ×
    aynı inanç çarpanı), üst kategori × takvim ayı toplamları; sezon
    toplamının %0,1'inden küçük hücreler atılır (Görev 10'un ölçüsü).

üretim süresi
    `tablolari_uret(Olcek.TAM)`'ın duvar saati süresi (yazma hariç) < 600 sn.
"""

import numpy as np
import pandas as pd
import pytest

from perakende_veri.v4 import sabitler
from perakende_veri.v4.motor.durum import magaza_takvimi
from perakende_veri.v4.plan import indirim_inanci
from perakende_veri.v4.takvim import gun_indisi

pytestmark = pytest.mark.yavas

YILLAR = (2023, 2024, 2025)
STR_SEZONLARI = ("SS23", "AW23", "SS24", "AW24", "SS25")
PLAN_SEZONLARI = ("SS23", "AW23", "SS24", "AW24", "SS25", "AW25")
KATEGORI_AY_SEZONLARI = ("SS24", "AW24")
HATLAR = ["normal", "outlet", "online"]  # yayımlanan `fiyat.hat` kategorileri


# ---------------------------------------------------------------------------
# Ölçütler
# ---------------------------------------------------------------------------


def online_payi(t: dict) -> dict[int, float]:
    s = t["satis"]
    yil = s["tarih"].dt.year.to_numpy()
    onl = (s["magaza_id"] == "ONL").to_numpy()
    tutar = s["tutar"].to_numpy()
    return {y: float(tutar[(yil == y) & onl].sum() / tutar[yil == y].sum()) for y in YILLAR}


def online_iade(t: dict) -> float:
    s = t["satis"]
    a = s["adet"].to_numpy()[(s["magaza_id"] == "ONL").to_numpy()]
    return float(-a[a < 0].sum() / a[a > 0].sum())


def _urun_cikis(w, urun_id: pd.Series, secili: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(option indisi, çıkış günü tarihi) satır başına; option `secili`
    değilse çıkış NaT."""
    u_idx = pd.Index(w.urunler["urun_id"].astype(str)).get_indexer(urun_id.astype(str))
    o_idx = np.asarray(w.sku_option)[u_idx]
    cik = pd.to_datetime(w.optionlar["cikis_tarihi"]).to_numpy().astype("datetime64[ns]")
    s_cik = np.where(secili[o_idx], cik[o_idx], np.datetime64("NaT", "ns"))
    return o_idx, s_cik


def _satis_hatti(w, s: pd.DataFrame, onl: np.ndarray) -> np.ndarray:
    """[satır] satışın fiyat hattı indisi (`HATLAR`): ONL → online, outlet
    akışı hücresi → outlet, diğerleri normal (`motor.satis.hat_indisi`)."""
    S = len(w.urunler)
    m_idx = pd.Index(w.magazalar["magaza_id"].astype(str)).get_indexer(s["magaza_id"].astype(str))
    u_idx = pd.Index(w.urunler["urun_id"].astype(str)).get_indexer(s["urun_id"].astype(str))
    anahtar = np.asarray(w.hucre_magaza, dtype=np.int64) * S + np.asarray(w.hucre_sku)
    sira = np.argsort(anahtar)
    k = m_idx.astype(np.int64) * S + u_idx
    i = np.minimum(np.searchsorted(anahtar[sira], k), len(sira) - 1)
    bulundu = (m_idx >= 0) & (u_idx >= 0) & (anahtar[sira][i] == k)
    outlet = bulundu & np.asarray(w.hucre_outlet_akisi)[sira][i]
    return np.where(onl, HATLAR.index("online"), np.where(outlet, HATLAR.index("outlet"), HATLAR.index("normal")))


def collection_str(w, t: dict) -> dict[str, float]:
    """Tam fiyat STR (alınan paydalı, bant) ve basılan alternatifler."""
    opt = w.optionlar
    secili = ((opt["line"] == "Collection") & opt["sezon_kodu"].isin(STR_SEZONLARI)).to_numpy()

    s = t["satis"]
    o_idx, s_cik = _urun_cikis(w, s["urun_id"], secili)
    tarih = s["tarih"].to_numpy()
    adet = s["adet"].to_numpy().astype(np.int64)
    kampanyasiz = s["kampanya_id"].isna().to_numpy()
    sezon_ici = ~np.isnat(s_cik) & (tarih < s_cik) & (adet > 0) & kampanyasiz
    onl = (s["magaza_id"] == "ONL").to_numpy()

    # Etiket fiyatı: hattın (ONL → online, diğerleri normal; çıkıştan önce
    # outlet hattı yok) ilk markdown haftasından önce. Markdown hiç
    # sığlaşmaz ve yalnız pazartesi değişir.
    f = t["fiyat"]
    f = f[f["indirim_orani"] > 0]
    f_o = pd.Index(opt["option_id"].astype(str)).get_indexer(f["option_id"].astype(str))
    f_h = pd.Index(HATLAR).get_indexer(f["hat"].astype(str))
    assert (f_h >= 0).all()
    YOK = np.iinfo(np.int64).max
    ilk_md = np.full((len(opt), len(HATLAR)), YOK, dtype=np.int64)
    np.minimum.at(ilk_md, (f_o, f_h), f["hafta_baslangic"].to_numpy().astype("datetime64[ns]").astype(np.int64))
    s_md = ilk_md[o_idx, _satis_hatti(w, s, onl)]
    etiket = sezon_ici & (tarih.astype("datetime64[ns]").astype(np.int64) < s_md)
    pay_etiket = float(adet[etiket].sum())
    pay_magaza = float(adet[etiket & ~onl].sum())
    # Eski tanım (yalnız basılır): indirim_tutari == 0 (işlem indirimli hariç).
    pay_sifir = float(adet[sezon_ici & (s["indirim_tutari"].to_numpy() == 0)].sum())

    sp = t["siparis"]
    alinan = float(
        sp["adet"][
            sp["tip"].isin(["ilk", "rpt"])
            & sp["option_id"].isin(opt["option_id"][secili])
            & sp["gerceklesen_teslim"].notna()
        ].sum()
    )
    sv = t["sevkiyat"]
    _, sv_cik = _urun_cikis(w, sv["urun_id"], secili)
    giden = float(
        sv["adet"].to_numpy()[
            (sv["kaynak"] == "DEPO").to_numpy()
            & sv["tip"].isin(["ilk_dagitim", "replenishment", "acilis_transferi"]).to_numpy()
            & ~np.isnat(sv_cik)
            & (sv["tarih"].to_numpy() < sv_cik)
        ].sum()
    )
    return {
        "str": pay_etiket / alinan,
        "str_indirim_tutari_sifir": pay_sifir / alinan,
        "str_magaza_gonderilen": pay_magaza / giden,
    }


def bulunabilirlik(w, ham: dict) -> dict[str, float]:
    bas, son = gun_indisi(sabitler.BASLANGIC), gun_indisi(sabitler.BITIS)
    st = ham["stok"]
    g_all = st["gun"].to_numpy()
    st = st[(g_all >= bas) & (g_all <= son)]
    g = st["gun"].to_numpy(dtype=np.int64)
    c = st["hucre"].to_numpy(dtype=np.int64)
    m = np.asarray(w.hucre_magaza)[c]
    a = np.asarray(w.hucre_acilis)[c]
    k = np.asarray(w.hucre_kapanis)[c]
    acik, _ = magaza_takvimi(w, w.gun_sayisi)
    acik_gun = np.zeros(len(c), dtype=np.int64)
    for j in range(1, 8):
        x = g - j
        acik_gun += (a <= x) & (x < k) & acik[x, m]
    stoklu = np.minimum(st["stoklu_gun"].to_numpy(dtype=np.int64), acik_gun)
    line = w.optionlar["line"].to_numpy()[np.asarray(w.hucre_option)[c]]
    oa = np.asarray(w.hucre_outlet_akisi)[c]

    def oran(maske):
        return float(stoklu[maske].sum() / acik_gun[maske].sum())

    return {
        "basic_nos": oran(np.isin(line, ["Basic", "NOS"])),
        "basic": oran(line == "Basic"),
        "nos": oran(line == "NOS"),
        "collection": oran((line == "Collection") & ~oa),
        "collection_outlet_akisi_dahil": oran(line == "Collection"),
        "outlet_line": oran(line == "Outlet"),
    }


def ikame_payi(gizli: dict) -> float:
    ik = float(gizli["ikame_satis"]["adet"].sum())
    kayip = float(gizli["kayip_satis"]["kayip_adet"].sum())
    return ik / (ik + kayip)


def _option_gunluk(lam, O: int) -> np.ndarray:
    """`[N, O]` λ'nın option başına günlük toplamı (bütün hücreler)."""
    N = lam.gun_sayisi
    ho = np.asarray(lam.hucre_option)
    out = np.empty((N, O))
    for d in range(N):
        out[d] = np.bincount(ho, weights=lam.gun(d), minlength=O)
    return out


def plan_hatasi(w) -> dict[str, float]:
    opt = w.optionlar.reset_index(drop=True)
    O = len(opt)
    plan = w.plan_ozeti.gunluk.sum(axis=1)       # [N, O] indirim inançlı
    gercek = _option_gunluk(w.lam, O)             # [N, O] liste fiyatında
    N = min(plan.shape[0], gercek.shape[0])
    plan, gercek = plan[:N], gercek[:N]
    idx = np.arange(O)

    def kum(x):
        return np.vstack([np.zeros((1, O)), np.cumsum(x, axis=0)])

    kp, kg = kum(plan), kum(gercek)
    lan = np.clip(opt["lansman_gun"].to_numpy(dtype=np.int64), 0, N)
    ind = np.clip(opt["indirim_gun"].to_numpy(dtype=np.int64), 0, N)
    p_s = kp[ind, idx] - kp[lan, idx]
    g_s = kg[ind, idx] - kg[lan, idx]
    col = ((opt["line"] == "Collection") & opt["sezon_kodu"].isin(PLAN_SEZONLARI)).to_numpy() & (g_s > 0)
    ape = np.abs(p_s[col] - g_s[col]) / g_s[col]
    sonuc = {
        "option_mape": float(ape.mean()),
        "option_medyan_ape": float(np.median(ape)),
        "option_plan_gercek": float(p_s[col].sum() / g_s[col].sum()),
    }

    carpan, _ = indirim_inanci(opt, N)
    gercek_md = gercek * carpan
    tarih = pd.Timestamp(sabitler.ISINMA_BASLANGIC) + pd.to_timedelta(np.arange(N), unit="D")
    ay = (tarih.year * 12 + tarih.month - 1).to_numpy()
    ust = opt["ust_kategori"].to_numpy()
    for sez in KATEGORI_AY_SEZONLARI:
        o_s = (opt["sezon_kodu"] == sez).to_numpy() & opt["sezonluk"].to_numpy(dtype=bool)
        p_df = pd.DataFrame(plan[:, o_s], index=ay).groupby(level=0).sum().T.groupby(ust[o_s]).sum()
        g_df = pd.DataFrame(gercek_md[:, o_s], index=ay).groupby(level=0).sum().T.groupby(ust[o_s]).sum()
        p_v, g_v = p_df.to_numpy().ravel(), g_df.to_numpy().ravel()
        tut = g_v > 0.001 * g_v.sum()
        sonuc[f"kategori_ay_mape_{sez}"] = float(np.mean(np.abs(p_v[tut] - g_v[tut]) / g_v[tut]))
        sonuc[f"kategori_ay_plan_gercek_{sez}"] = float(p_v.sum() / g_v.sum())
    return sonuc


# ---------------------------------------------------------------------------
# Fixture: bütün ölçütler bir kez
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def olcut(tam_kosu):
    w, ham, t, gizli = tam_kosu["dunya"], tam_kosu["ham"], tam_kosu["tablolar"], tam_kosu["gizli"]
    o = {
        "online_payi": online_payi(t),
        "online_iade": online_iade(t),
        **{k: v for k, v in collection_str(w, t).items()},
        **{f"bulunabilirlik_{k}": v for k, v in bulunabilirlik(w, ham).items()},
        "ikame_payi": ikame_payi(gizli),
        **{f"plan_{k}": v for k, v in plan_hatasi(w).items()},
        "sure_sn": tam_kosu["sure_sn"],
    }
    print("\nKALİBRASYON ÖLÇÜTLERİ (TAM)")
    for k, v in o.items():
        if isinstance(v, dict):
            print(f"  {k:40s} " + "  ".join(f"{y}: {x:.4f}" for y, x in v.items()))
        else:
            print(f"  {k:40s} {v:.4f}")
    return o


# ---------------------------------------------------------------------------
# Bantlar (spec §8.2 birebir)
# ---------------------------------------------------------------------------


def test_online_payi(olcut):
    assert all(0.15 <= p <= 0.20 for p in olcut["online_payi"].values()), olcut["online_payi"]


def test_online_iade(olcut):
    assert 0.25 <= olcut["online_iade"] <= 0.30, olcut["online_iade"]


def test_collection_tam_fiyat_str(olcut):
    assert 0.55 <= olcut["str"] <= 0.70, olcut["str"]


def test_bulunabilirlik(olcut):
    b, c = olcut["bulunabilirlik_basic_nos"], olcut["bulunabilirlik_collection"]
    assert 0.85 <= b <= 0.95 and 0.70 <= c <= 0.85, (b, c)


def test_ikame_payi(olcut):
    assert 0.20 <= olcut["ikame_payi"] <= 0.40, olcut["ikame_payi"]


def test_plan_hatasi(olcut):
    op = olcut["plan_option_mape"]
    ka = [olcut[f"plan_kategori_ay_mape_{s}"] for s in KATEGORI_AY_SEZONLARI]
    assert 0.40 <= op <= 0.55 and all(0.10 <= x <= 0.20 for x in ka), (op, ka)


def test_uretim_suresi(olcut):
    assert olcut["sure_sn"] < 600, olcut["sure_sn"]
