"""Testler: Görev 18 — öğrenilebilirlik (tam ölçek, spec §8.3).

Spec: docs/superpowers/specs/2026-09-27-veri-v4-cekirdek-design.md §8.3
(ve §2.3, §3.3, §4.1, §5.2, §6.3)
Brief: .superpowers/sdd/2026-09-27-veri-v4-cekirdek/task-18-brief.md

Veri "çözülebilir ama önemsiz değil" olmalı. Her test iki parçadır:
**öğrenen** yalnız yayımlanan tabloları okur (gerçek bir analistin
elindeki `satis`, `fiyat`, `kampanya`, `urun`, `magaza`, `siparis`,
`kalite_kontrol`, `depo_stok`, `sevkiyat`); **gizli gerçek**
(`gizli_gercek`) yalnız puanlamada kullanılır. Tablolar kirli yayımdır
(mükerrer / bedelsiz kayıtlar analistin gördüğü gibi içeride kalır).

Bütün testler `yavas` işaretli ve oturum fixture'ı `tam_kosu`'yu paylaşır;
ölçümler modül fixture'ı `olcum`'de bir kez yapılır ve `-s` ile basılır.

**Kestiriciler** (controller kararları):

kümeleme
    Pencerede en az bir yıl açık kalan her fiziksel mağaza için (ONL
    hariç, outlet dahil) satış karışımı: alt kategori adet payı (17),
    takvim ayı adet payı (12), fiyat segmenti adet payı (3) ve ortalama
    indirim derinliği (Σ indirim_tutari ÷ Σ (tutar + indirim_tutari));
    hepsi brüt satış (adet > 0) satırlarından, mağazanın pencere içi bütün
    satışı. Sütunlar standardize, `KMeans(6, n_init=20, random_state=0)`;
    ARI gizli segmente karşı; bant 0,4–0,8.

esneklik tuzağı
    *Saf:* haftalık (pazartesi başlangıçlı) option × mağaza brüt satış
    adedi, yalnız markdown haftalarında (option'ın hattında `fiyat.
    indirim_orani` > 0; fiziksel mağaza → `normal`, ONL → `online`,
    çıkıştan önceki haftalar; outlet mağazaları hariç — outlet akışı
    satışları `outlet` hattının fiyatındadır) ve satışı olan hücrelerde; havuzlanmış OLS
    log(adet) = a + b · log(1 − oran), sabit etki yok; ε̂ = −b. Markdown
    Lumoda kuralıyla satışı zayıf option'a gelir (içsel) ve yaşam
    eğrisinin sönen ucuna düşer; saf kestirim bu yüzden belirgin
    yanlıştır: |ε̂ − ε| ÷ ε > 0,4, ε = aynı satırların gizli ε ortalaması.

    *Kampanya (fark içinde fark):* her `kategori` kampanyası (bölgesel,
    dışsal) için: kapsamdaki option'lar (üst kategori + `kapsam_line`;
    lansmanı ön dönemden önce, çıkışı kampanyadan sonra, ön ve kampanya
    dönemlerine değen hiçbir hafta markdown'da değil); kapsanan grup =
    kampanya bölgelerindeki, dışarıda kalan grup = diğer bölgelerdeki
    fiziksel, outlet olmayan ve iki dönem boyunca açık mağazalar (ONL
    bölgesel kampanyaya girmez, dışarıda). Kampanya dönemi [b, b+L), ön
    dönem aynı haftagünü dizilişiyle 7·⌈L/7⌉ gün geri. Başka bir
    kampanyanın (kategori, ikinci ürün, Black Friday) aynı option'lara
    değdiği pencereler atılır. Kampanya başına, kapsamdaki option'lar
    toplamında
        y = log(K_kamp ÷ K_ön) − log(D_kamp ÷ D_ön),  x = −log(1 − oran)
    ve ε̂_k = y ÷ x. Havuz: ε̂ = Σ w·y ÷ Σ w·x, w = 1 ÷ (1/K_kamp + 1/K_ön
    + 1/D_kamp + 1/D_ön) (Poisson varyansının tersi). Gizli karşılık: aynı
    kapsanan (mağaza, option) hücrelerinin ön dönem satışıyla ağırlıklı
    ε ortalaması, havuzda aynı w·x ağırlıklarıyla. Üst kategori başına da
    raporlanır; iddia havuzlanmış kestirimdedir: |ε̂ − ε| ÷ ε ≤ 0,2.

trend
    SS25 Collection option'ları, sezon satışı: çıkıştan önceki brüt satış
    adedi (bütün kanallar). Plan referansı yayımlanan `range_plan`: option'ın
    (sezon × alt kategori × fiyat segmenti × line) satırındaki `derinlik`
    (option başına planlanan ilk alım). "Plan-üstü satış oranı" = option
    satışı ÷ derinlik — planın kaçırdığı. Tek yanlı Welch t-testi
    log(oran): oversize > slim, p < 0,05.

tedarikçi
    `siparis` (sipariş başına bir kez: gerçekleşen − planlanan teslim, gün;
    teslimi pencerede olan siparişler) → tedarikçi ortalama gecikmesi;
    `kalite_kontrol` Σ hatalı ÷ Σ numune → hatalı oranı. Skor = z(gecikme)
    + z(hatalı); gizli skor aynı birleşim `gecikme_beklenen_gun` ve
    `hatali_orani` üzerinde; Spearman ≥ 0,5.

açılış (§8.3; eski KÜÇÜK xfail testinin tam ölçek yerine geçeni)
    Karar günü = mağazanın `acilis_transferi` sevkinin günü (açılış −
    yolda süre). İkiz = aynı **gizli** segmentteki, karar günü açık en yakın
    (haversine) fiziksel mağaza — onaylı istisna: bu test bir öğrenme
    değil, bir dünya özelliğini ("depo ince") denetler, bu yüzden segment
    yalnız ikiz seçiminde kullanılır. İhtiyaç = ikizin karar gününden önceki
    28 günlük brüt satışının SKU karışımı × yeni mağazanın açılıştan
    itibaren 28 günlük plan toplamı; bu toplam şirketin yayımlanan
    tablolardan daha ince plan bilgisinden gelir (`w.ileri_plan`, Lumoda'nın
    plan λ'sı: Lumoda'nın kendi bilgisi, gizli gerçek değil). Sezon başı /
    ortası ayrımı yayımlanan `sezon` tablosunun dalga 1 lansmanlarıyla. Kapsama = Σ_sku min(depo_stok[karar günü, sku],
    ihtiyaç[sku]) ÷ Σ ihtiyaç, **yalnız sezonluk (Collection + Outlet line)
    SKU'lar üzerinden** (controller kararı): spec §6.3'ün "sezon ortasında
    ilk alımın büyük kısmı dağıtılmış, depo ince" iddiası sezon malı
    içindir; Basic/NOS sürekli tedarikle hep yenilenir ve depo inceliği
    sorusunun konusu değildir (tüm line'lı kapsamada ihtiyacın %71–83'ü
    Basic/NOS'tur ve depo onu ~%95 karşılar). Sezon ortası (dalga 1
    lansmanına denk gelmeyen) 4 açılışın her birinde < 0,60.
    Tüm line'lı kapsama ve iki sezon başı açılış yalnız tanı olarak basılır;
    sezon başı/ortası karşıtlığı iddia edilmez: sezon başında ikizin son 28
    günlük karışımı hâlâ biten sezonun malını yansıtır (yeni sezon henüz
    satılmadı), bu kestiriciyle o karşılaştırma anlamlı değildir.
"""

import numpy as np
import pandas as pd
import pytest
from scipy import stats
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score
from sklearn.preprocessing import StandardScaler

from perakende_veri.v4 import sabitler
from perakende_veri.v4.takvim import gun_indisi

pytestmark = pytest.mark.yavas

BAS = pd.Timestamp(sabitler.BASLANGIC)
SON = pd.Timestamp(sabitler.BITIS)
GUN = pd.Timedelta(days=1)


# ---------------------------------------------------------------------------
# Ortak
# ---------------------------------------------------------------------------


def _brut_satis(t: dict) -> pd.DataFrame:
    """`satis`in brüt (adet > 0) satırları + urun sütunları."""
    s = t["satis"]
    s = s[s["adet"].to_numpy() > 0]
    u = t["urun"].set_index("urun_id")
    uid = s["urun_id"].astype(str)
    df = pd.DataFrame(
        {
            "tarih": s["tarih"].to_numpy(),
            "magaza_id": s["magaza_id"].astype(str).to_numpy(),
            "urun_id": uid.to_numpy(),
            "adet": s["adet"].to_numpy().astype(np.int64),
            "tutar": s["tutar"].to_numpy(),
            "indirim_tutari": s["indirim_tutari"].to_numpy(),
        }
    )
    for k in ("option_id", "alt_kategori", "ust_kategori", "fiyat_segmenti", "line", "sezon_kodu", "kalip"):
        df[k] = u[k].reindex(uid).to_numpy()
    return df


def _fiziksel(t: dict) -> pd.DataFrame:
    m = t["magaza"]
    return m[m["tip"] != "Online"].set_index("magaza_id")


# ---------------------------------------------------------------------------
# Kümeleme
# ---------------------------------------------------------------------------


def kumeleme(t: dict, s: pd.DataFrame, gizli: dict) -> dict:
    m = _fiziksel(t)
    acilis = pd.to_datetime(m["acilis_tarihi"]).clip(lower=BAS)
    kapanis = pd.to_datetime(m["kapanis_tarihi"]).fillna(SON + GUN).clip(upper=SON + GUN)
    uygun = m.index[(kapanis - acilis) >= pd.Timedelta(days=365)]

    s = s[s["magaza_id"].isin(uygun)]
    adet = s["adet"].to_numpy()

    def pay(anahtar) -> pd.DataFrame:
        p = pd.crosstab(s["magaza_id"], anahtar, values=adet, aggfunc="sum").fillna(0.0)
        return p.div(p.sum(axis=1), axis=0)

    ay = pd.DatetimeIndex(s["tarih"]).month.to_numpy()
    derinlik = s.groupby("magaza_id")[["indirim_tutari", "tutar"]].sum()
    X = pd.concat(
        [
            pay(s["alt_kategori"].to_numpy()).add_prefix("alt_"),
            pay(ay).add_prefix("ay_"),
            pay(s["fiyat_segmenti"].to_numpy()).add_prefix("fs_"),
            (derinlik["indirim_tutari"] / (derinlik["indirim_tutari"] + derinlik["tutar"])).rename("derinlik"),
        ],
        axis=1,
    ).loc[list(uygun)]
    Z = StandardScaler().fit_transform(X.to_numpy())
    km = KMeans(6, n_init=20, random_state=0).fit(Z)
    seg = gizli["segment"].set_index("magaza_id")["segment"].reindex(X.index)
    return {
        "ari": float(adjusted_rand_score(seg.to_numpy(), km.labels_)),
        "magaza_sayisi": len(X),
        "capraz": pd.crosstab(seg.to_numpy(), km.labels_),
    }


# ---------------------------------------------------------------------------
# Esneklik tuzağı
# ---------------------------------------------------------------------------


def _hafta(tarih) -> np.ndarray:
    t = pd.DatetimeIndex(tarih)
    return (t - pd.to_timedelta(t.dayofweek, unit="D")).normalize().to_numpy()


def _gizli_eps(gizli: dict) -> pd.Series:
    e = gizli["esneklik"]
    return pd.Series(
        e["esneklik"].to_numpy(),
        index=pd.MultiIndex.from_arrays([e["magaza_id"].astype(str), e["option_id"].astype(str)]),
    )


def esneklik_saf(t: dict, s: pd.DataFrame, gizli: dict) -> dict:
    u = t["urun"].drop_duplicates("option_id").set_index("option_id")
    cikis = pd.to_datetime(u["cikis_tarihi"]).reindex(s["option_id"]).to_numpy()
    s = s[~pd.isna(cikis) & (s["tarih"].to_numpy() < cikis)]
    m = t["magaza"]
    s = s[~s["magaza_id"].isin(m.loc[m["tip"] == "Outlet", "magaza_id"].astype(str))].copy()
    s["hafta"] = _hafta(s["tarih"])
    s["hat"] = np.where(s["magaza_id"] == "ONL", "online", "normal")
    h = s.groupby(["hafta", "option_id", "magaza_id", "hat"], observed=True)["adet"].sum().reset_index()
    f = t["fiyat"]
    f = f[f["indirim_orani"] > 0]
    f = pd.DataFrame(
        {
            "hafta": f["hafta_baslangic"].to_numpy(),
            "option_id": f["option_id"].astype(str).to_numpy(),
            "hat": f["hat"].astype(str).to_numpy(),
            "oran": f["indirim_orani"].to_numpy(),
        }
    )
    h = h.merge(f, on=["hafta", "option_id", "hat"], how="inner")
    x = np.log(1.0 - h["oran"].to_numpy())
    y = np.log(h["adet"].to_numpy())
    b = float(np.polyfit(x, y, 1)[0])
    eps = _gizli_eps(gizli).reindex(pd.MultiIndex.from_arrays([h["magaza_id"], h["option_id"]])).to_numpy()
    gercek = float(np.nanmean(eps))
    return {"eps_hat": -b, "eps": gercek, "goreli_hata": abs(-b - gercek) / gercek, "n": len(h)}


def esneklik_kampanya(t: dict, s: pd.DataFrame, gizli: dict) -> dict:
    kamp = t["kampanya"].copy()
    kamp["baslangic"] = pd.to_datetime(kamp["baslangic"])
    kamp["bitis"] = pd.to_datetime(kamp["bitis"])
    m = _fiziksel(t)
    m = m[m["tip"] != "Outlet"]
    acilis = pd.to_datetime(m["acilis_tarihi"])
    kapanis = pd.to_datetime(m["kapanis_tarihi"]).fillna(pd.Timestamp("2100-01-01"))
    tad = t["magaza_olay"]
    tad = tad[tad["olay"] == "tadilat"]

    u = t["urun"].drop_duplicates("option_id").set_index("option_id")
    lansman = pd.to_datetime(u["lansman_tarihi"])
    cikis = pd.to_datetime(u["cikis_tarihi"]).fillna(pd.Timestamp("2100-01-01"))
    f = t["fiyat"]
    f = f[(f["indirim_orani"] > 0) & (f["hat"] == "normal")]
    md_hafta = pd.DataFrame(
        {"option_id": f["option_id"].astype(str).to_numpy(), "hafta": f["hafta_baslangic"].to_numpy()}
    )

    s = s[s["magaza_id"].isin(m.index)]
    s_tarih = s["tarih"].to_numpy()
    eps = _gizli_eps(gizli)

    satirlar = []
    for k in kamp[kamp["tip"] == "kategori"].itertuples():
        L = (k.bitis - k.baslangic).days + 1
        on_bas = k.baslangic - pd.Timedelta(days=7 * int(np.ceil(L / 7)))
        on_bit = on_bas + pd.Timedelta(days=L)
        kamp_bit = k.bitis + GUN
        if on_bas < BAS or kamp_bit > SON + GUN:
            continue
        # Kapsamdaki option'lar
        o_mask = (u["ust_kategori"] == k.kapsam_ust_kategori).to_numpy()
        if k.kapsam_line:
            o_mask &= u["line"].isin(k.kapsam_line.split(",")).to_numpy()
        o_mask &= (lansman <= on_bas).to_numpy() & (cikis >= kamp_bit).to_numpy()
        # Aynı option'lara değen başka kampanya → bu option'lar düşer
        diger = kamp[(kamp["kampanya_id"] != k.kampanya_id) & (kamp["baslangic"] < kamp_bit)
                     & (kamp["bitis"] >= on_bas)]
        for d in diger.itertuples():
            dm = np.ones(len(u), dtype=bool)
            if d.kapsam_ust_kategori:
                dm &= (u["ust_kategori"] == d.kapsam_ust_kategori).to_numpy()
            if d.kapsam_line:
                dm &= u["line"].isin(d.kapsam_line.split(",")).to_numpy()
            o_mask &= ~dm
        # Markdown haftası değen option'lar düşer
        hw = md_hafta[(md_hafta["hafta"] > on_bas - pd.Timedelta(days=7)) & (md_hafta["hafta"] < kamp_bit)]
        o_mask &= ~u.index.isin(hw["option_id"].unique())
        optionlar = u.index[o_mask]
        if len(optionlar) == 0:
            continue
        # Mağaza grupları: iki dönem boyunca açık
        acik = (acilis <= on_bas) & (kapanis >= kamp_bit)
        for r in tad.itertuples():
            if pd.Timestamp(r.olay_tarihi) < kamp_bit and pd.Timestamp(r.bitis_tarihi) > on_bas:
                acik[r.magaza_id] = False
        bolgeler = set(k.kapsam_bolge.split(","))
        kapsanan = m.index[acik & m["bolge"].isin(bolgeler)]
        disarida = m.index[acik & ~m["bolge"].isin(bolgeler)]

        ss = s[((s_tarih >= on_bas) & (s_tarih < on_bit)) | ((s_tarih >= k.baslangic) & (s_tarih < kamp_bit))]
        ss = ss[ss["option_id"].isin(optionlar)]
        donem = np.where(ss["tarih"].to_numpy() >= k.baslangic, "kamp", "on")
        grup = np.where(ss["magaza_id"].isin(kapsanan), "K", np.where(ss["magaza_id"].isin(disarida), "D", ""))
        tab = pd.Series(ss["adet"].to_numpy()).groupby([grup, donem]).sum()
        try:
            K_k, K_o, D_k, D_o = (float(tab[(g, d)]) for g, d in (("K", "kamp"), ("K", "on"), ("D", "kamp"), ("D", "on")))
        except KeyError:
            continue
        y = np.log(K_k / K_o) - np.log(D_k / D_o)
        x = -np.log(1.0 - k.oran)
        w = 1.0 / (1 / K_k + 1 / K_o + 1 / D_k + 1 / D_o)
        # Gizli ε: kapsanan hücrelerin ön dönem satışıyla ağırlıklı
        on_k = ss[(donem == "on") & (grup == "K")].groupby(["magaza_id", "option_id"])["adet"].sum()
        e = eps.reindex(on_k.index).to_numpy()
        satirlar.append(
            {
                "kampanya_id": k.kampanya_id, "ust": k.kapsam_ust_kategori, "line": k.kapsam_line,
                "oran": k.oran, "option": len(optionlar), "K_kamp": K_k, "K_on": K_o,
                "D_kamp": D_k, "D_on": D_o, "y": y, "x": x, "w": w,
                "eps_hat": y / x, "eps": float(np.average(e, weights=on_k.to_numpy())),
            }
        )
    df = pd.DataFrame(satirlar)

    def havuz(d: pd.DataFrame) -> tuple[float, float]:
        ww = d["w"] * d["x"]
        return float((d["w"] * d["y"]).sum() / (d["w"] * d["x"]).sum()), float(np.average(d["eps"], weights=ww))

    e_hat, e = havuz(df)
    ust = {}
    for g, d in df.groupby("ust"):
        a, b = havuz(d)
        ust[g] = {"eps_hat": a, "eps": b, "goreli_hata": abs(a - b) / b, "kampanya": len(d)}
    return {"eps_hat": e_hat, "eps": e, "goreli_hata": abs(e_hat - e) / e, "ust": ust,
            "kampanya_sayisi": len(df), "tablo": df}


# ---------------------------------------------------------------------------
# Trend
# ---------------------------------------------------------------------------


def trend(t: dict, s: pd.DataFrame, sezon: str = "SS25") -> dict:
    u = t["urun"].drop_duplicates("option_id").set_index("option_id")
    sec = u[(u["sezon_kodu"] == sezon) & (u["line"] == "Collection")]
    cikis = pd.to_datetime(sec["cikis_tarihi"])
    ss = s[s["option_id"].isin(sec.index)]
    ss = ss[ss["tarih"].to_numpy() < cikis.reindex(ss["option_id"]).to_numpy()]
    satis = ss.groupby("option_id")["adet"].sum().reindex(sec.index).fillna(0.0)
    rp = t["range_plan"].set_index(["sezon_kodu", "alt_kategori", "fiyat_segmenti", "line"])["derinlik"]
    derinlik = rp.reindex(pd.MultiIndex.from_arrays(
        [sec["sezon_kodu"], sec["alt_kategori"], sec["fiyat_segmenti"], sec["line"]])).to_numpy(dtype=float)
    assert np.isfinite(derinlik).all() and (derinlik > 0).all(), "her option'ın range_plan satırı olmalı"
    oran = pd.Series(np.log((satis.to_numpy() + 1.0) / derinlik), index=sec.index)
    ov = oran[sec["kalip"] == "oversize"].to_numpy()
    sl = oran[sec["kalip"] == "slim"].to_numpy()
    r = stats.ttest_ind(ov, sl, equal_var=False, alternative="greater")
    return {"p": float(r.pvalue), "t": float(r.statistic), "fark": float(ov.mean() - sl.mean()),
            "n_oversize": len(ov), "n_slim": len(sl)}


# ---------------------------------------------------------------------------
# Tedarikçi
# ---------------------------------------------------------------------------


def _z(x: pd.Series) -> pd.Series:
    return (x - x.mean()) / x.std(ddof=0)


def tedarikci(t: dict, gizli: dict) -> dict:
    sp = t["siparis"].drop_duplicates("siparis_id")
    sp = sp[sp["gerceklesen_teslim"].notna()]
    gec = ((sp["gerceklesen_teslim"] - sp["planlanan_teslim"]).dt.days).groupby(sp["tedarikci_id"]).mean()
    kk = t["kalite_kontrol"].merge(sp[["siparis_id", "tedarikci_id"]], on="siparis_id")
    h = kk.groupby("tedarikci_id")[["hatali", "numune"]].sum()
    hat = h["hatali"] / h["numune"]
    skor = (_z(gec) + _z(hat.reindex(gec.index))).dropna()
    p = gizli["tedarikci_profili"].set_index("tedarikci_id")
    g_skor = _z(p["gecikme_beklenen_gun"]) + _z(p["hatali_orani"])
    g_skor = g_skor.reindex(skor.index)
    return {
        "spearman": float(stats.spearmanr(skor.to_numpy(), g_skor.to_numpy()).statistic),
        "spearman_gecikme": float(stats.spearmanr(gec, p["gecikme_beklenen_gun"].reindex(gec.index)).statistic),
        "spearman_hatali": float(stats.spearmanr(hat, p["hatali_orani"].reindex(hat.index)).statistic),
        "tedarikci": len(skor),
    }


# ---------------------------------------------------------------------------
# Açılış
# ---------------------------------------------------------------------------


def _haversine(lat1, lon1, lat2, lon2) -> np.ndarray:
    r = np.radians
    a = np.sin(r(lat2 - lat1) / 2) ** 2 + np.cos(r(lat1)) * np.cos(r(lat2)) * np.sin(r(lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * np.arcsin(np.sqrt(a))


def acilis(t: dict, s: pd.DataFrame, gizli: dict, plan28: dict, lansmanlar: set) -> dict:
    """`plan28`: magaza_id → yeni mağazanın açılıştan itibaren 28 günlük plan
    toplamı (Lumoda plan λ'sı). {magaza_id: {...}}."""
    m = _fiziksel(t)
    seg = gizli["segment"].set_index("magaza_id")["segment"]
    sv = t["sevkiyat"]
    at = sv[sv["tip"] == "acilis_transferi"]
    ds = t["depo_stok"]
    u_line = t["urun"].set_index("urun_id")["line"]
    sonuc = {}
    for r in t["magaza_olay"][t["magaza_olay"]["olay"] == "acilis"].itertuples():
        mid = r.magaza_id
        karar = at.loc[at["hedef"].astype(str) == mid, "tarih"].min()
        adaylar = m[(seg.reindex(m.index) == seg[mid]).to_numpy()
                    & (pd.to_datetime(m["acilis_tarihi"]) <= karar - pd.Timedelta(days=28)).to_numpy()
                    & (pd.to_datetime(m["kapanis_tarihi"]).fillna(pd.Timestamp("2100-01-01")) > karar).to_numpy()]
        adaylar = adaylar.drop(index=mid, errors="ignore")
        uz = _haversine(m.at[mid, "enlem"], m.at[mid, "boylam"], adaylar["enlem"].to_numpy(), adaylar["boylam"].to_numpy())
        ikiz = adaylar.index[int(np.argmin(uz))]
        pen = s[(s["magaza_id"] == ikiz) & (s["tarih"] >= karar - pd.Timedelta(days=28)) & (s["tarih"] < karar)]
        karisim = pen.groupby("urun_id")["adet"].sum()
        ihtiyac = karisim / karisim.sum() * plan28[mid]
        d = ds[ds["tarih"] == karar]
        depo = d.groupby(d["urun_id"].astype(str))["adet"].sum().reindex(ihtiyac.index).fillna(0).clip(lower=0)
        karsilanan = np.minimum(depo.to_numpy(), ihtiyac.to_numpy())
        # İddia sezonluk (Collection + Outlet) SKU'larda: "ilk alım dağıtılmış"
        # (spec §6.3) sezon malıdır; Basic/NOS deposu sürekli tedarikle hep
        # dolu (tüm line'lı kapsama yalnız tanı).
        sez = ~u_line.reindex(ihtiyac.index).isin(["Basic", "NOS"]).to_numpy()
        sonuc[mid] = {
            "sezon_ortasi": pd.Timestamp(r.olay_tarihi) not in lansmanlar,
            "acilis": pd.Timestamp(r.olay_tarihi).date(), "karar": karar.date(), "ikiz": ikiz,
            "kapsama": float(karsilanan[sez].sum() / ihtiyac.to_numpy()[sez].sum()),
            "tum_line_kapsama": float(karsilanan.sum() / ihtiyac.sum()),
            "sezonluk_pay": float(ihtiyac.to_numpy()[sez].sum() / ihtiyac.sum()),
        }
    return sonuc


def plan28_hesapla(w) -> dict:
    """Yeni mağazanın açılış gününden itibaren 28 günlük plan λ toplamı
    (açılış günü penceresi açık fiziksel, outlet akışı olmayan hücreler)."""
    out = {}
    for r in w.magaza_olay[w.magaza_olay.olay == "acilis"].itertuples():
        m = int(np.flatnonzero(w.magazalar["magaza_id"].to_numpy() == r.magaza_id)[0])
        a = gun_indisi(r.olay_tarihi)
        c = np.flatnonzero((w.hucre_magaza == m) & ~w.hucre_online & ~w.hucre_outlet_akisi
                           & (w.hucre_acilis <= a) & (a < w.hucre_kapanis))
        out[r.magaza_id] = float(w.ileri_plan(a, sabitler.REPL_HEDEF_GUN)[c].sum())
    return out


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


def olcumler(t: dict, gizli: dict, plan28: dict, lansmanlar: set) -> dict:
    s = _brut_satis(t)
    return {
        "kumeleme": kumeleme(t, s, gizli),
        "saf": esneklik_saf(t, s, gizli),
        "kampanya": esneklik_kampanya(t, s, gizli),
        "trend": trend(t, s),
        "tedarikci": tedarikci(t, gizli),
        "acilis": acilis(t, s, gizli, plan28, lansmanlar),
    }


def yazdir(o: dict) -> None:
    print("\nÖĞRENİLEBİLİRLİK ÖLÇÜMLERİ (TAM)")
    k = o["kumeleme"]
    print(f"  kümeleme ARI {k['ari']:.4f} ({k['magaza_sayisi']} mağaza)")
    print(k["capraz"].to_string())
    sf, kp = o["saf"], o["kampanya"]
    print(f"  saf esneklik  ε̂ {sf['eps_hat']:.3f}  ε {sf['eps']:.3f}  göreli hata {sf['goreli_hata']:.3f}  (n {sf['n']})")
    print(f"  kampanya DiD  ε̂ {kp['eps_hat']:.3f}  ε {kp['eps']:.3f}  göreli hata {kp['goreli_hata']:.3f}"
          f"  ({kp['kampanya_sayisi']} kampanya)")
    for g, v in kp["ust"].items():
        print(f"    {g:16s} ε̂ {v['eps_hat']:.3f}  ε {v['eps']:.3f}  göreli hata {v['goreli_hata']:.3f}  ({v['kampanya']})")
    tr = o["trend"]
    print(f"  trend SS25 oversize − slim log fark {tr['fark']:.3f}  t {tr['t']:.2f}  p {tr['p']:.2e}"
          f"  (n {tr['n_oversize']} / {tr['n_slim']})")
    td = o["tedarikci"]
    print(f"  tedarikçi Spearman {td['spearman']:.3f} (gecikme {td['spearman_gecikme']:.3f},"
          f" hatalı {td['spearman_hatali']:.3f}; {td['tedarikci']} tedarikçi)")
    for mid, v in o["acilis"].items():
        print(f"  açılış {mid} {v['acilis']} karar {v['karar']} ikiz {v['ikiz']}"
              f" {'orta' if v['sezon_ortasi'] else 'baş '} sezonluk kapsama {v['kapsama']:.3f}"
              f"  (tanı: tüm line {v['tum_line_kapsama']:.3f}, sezonluk ihtiyaç payı {v['sezonluk_pay']:.3f})")


@pytest.fixture(scope="module")
def olcum(tam_kosu):
    w, t, gizli = tam_kosu["dunya"], tam_kosu["tablolar"], tam_kosu["gizli"]
    sz = t["sezon"]
    lansmanlar = set(pd.to_datetime(sz.loc[sz["dalga"] == 1, "lansman_tarihi"]))
    o = olcumler(t, gizli, plan28_hesapla(w), lansmanlar)
    yazdir(o)
    return o


# ---------------------------------------------------------------------------
# Testler (spec §8.3)
# ---------------------------------------------------------------------------


def test_kumeleme_kismen_bulunur(olcum):
    ari = olcum["kumeleme"]["ari"]
    assert 0.4 <= ari <= 0.8, ari


def test_esneklik_tuzagi(olcum):
    saf, kamp = olcum["saf"], olcum["kampanya"]
    assert saf["goreli_hata"] > 0.4, saf
    assert kamp["goreli_hata"] <= 0.2, (kamp["eps_hat"], kamp["eps"], kamp["ust"])


def test_trend_gorunur(olcum):
    assert olcum["trend"]["p"] < 0.05, olcum["trend"]


def test_acilis_depo_yetersiz(olcum):
    orta = {m: v["kapsama"] for m, v in olcum["acilis"].items() if v["sezon_ortasi"]}
    assert len(orta) == 4, olcum["acilis"]
    assert all(k < 0.60 for k in orta.values()), orta


def test_tedarikci_siralamasi(olcum):
    assert olcum["tedarikci"]["spearman"] >= 0.5, olcum["tedarikci"]
