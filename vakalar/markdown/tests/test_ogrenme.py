"""`markdown.ogrenme`: esneklik, yaşam eğrisi, kalıntı, iade, işlem indirimi, saf ε, önbellek.

**Öğrenme oyuncağı** (bu dosyaya özgü; `conftest`in tahmin oyuncağı ortak paketin günlük tablosunu
kuramaz). Altı fiziksel mağaza (S1–S3 Marmara, S4 Ege, S5 Akdeniz, S6 Karadeniz), bir outlet (OUT1)
ve ONL. Beş Collection sezonu (SS23, AW23, SS24 kapanmış; AW24, SS25 test), her sezonda dört
option, her option'da üç beden:

    a  Üst Giyim / Tişört   dalga 1   L(w) = 1 (w < 3), sonra 0,92^(w−2)    500 TL
    b  Alt Giyim / Pantolon dalga 1   L(w) = 0,95^w; indirimden 28 gün önce %20 ("zayıf")   800 TL
    c  Üst Giyim / Gömlek   dalga 1   seyrek: yalnız S1 × S bedeni (ONL'de depo yok)     600 TL
    d  Üst Giyim / Tişört   dalga 2   L(w) = 0,9^w                                      400 TL

Satış belirlenimcidir: adet = round(λ × L(w) × (1 − max(md, kampanya))^(−ε)), ε = 1,8 her yerde,
λ = 20 × mağaza çarpanı × beden çarpanı (ONL 40 × beden çarpanı). Markdown indirimden çıkışa %30
(fiyat paneli haftalık; günün oranı haftasının pazartesisinin satırı). İki bölgesel kampanya
(fark içinde fark): SS24'te Üst Giyim Marmara %20 (2024-04-08…14), AW23'te Alt Giyim Ege + Akdeniz %30
(2023-10-16…22). Raf her pazartesi 1.000 adet (stok hiç bitmez), depo 3.000 (a, b, d); çıkıştan sonra
OUT1'de 84 gün günde 40 adet yarı fiyatına satış (+1 iade satırı; 84. günden sonraki satırlar
pencere dışı). İade: fiziksel mağazada pazartesi, önceki haftanın satışının %6'sı; ONL'de %27.
İşlem indirimi: kampanyasız tam fiyat satırlarının bir kısmında %30 (S2, gün indisi 13'e bölünen).
"""

import dataclasses
import json
import pickle
from datetime import date

import duckdb
import numpy as np
import pandas as pd
import pytest

from markdown import ogrenme

_T = "datetime64[ns]"
EPS = 1.8
SON_GUN = pd.Timestamp("2025-06-01")        # verinin son günü (bitişten sonrası bozma testi için)
VERI_BASI = pd.Timestamp("2023-01-01")

MAGAZALAR = [   # magaza_id, bolge, tip, çarpan
    ("S1", "Marmara", "AVM", 1.5), ("S2", "Marmara", "Cadde", 1.0), ("S3", "Marmara", "AVM", 1.2),
    ("S4", "Ege", "AVM", 0.8), ("S5", "Akdeniz", "AVM", 1.0), ("S6", "Karadeniz", "Cadde", 0.7),
    ("OUT1", "Marmara", "Outlet", 0.0), ("ONL", "Marmara", "Online", 0.0),
]
FIZIKSEL = [m[0] for m in MAGAZALAR if m[2] not in ("Outlet", "Online")]
BEDENLER = (("S", 0.9), ("M", 1.2), ("L", 0.9))
SEZONLAR = {   # sezon -> (dalga 1 lansman, indirim, çıkış); dalga 2 = dalga 1 + 35 gün
    "SS23": ("2023-02-13", "2023-07-03", "2023-08-28"),
    "AW23": ("2023-08-21", "2024-01-02", "2024-02-26"),
    "SS24": ("2024-02-12", "2024-07-01", "2024-08-26"),
    "AW24": ("2024-08-19", "2025-01-02", "2025-02-24"),
    "SS25": ("2025-02-10", "2025-06-30", "2025-08-25"),
}
OPTIONLAR = {   # harf -> (ust, alt, dalga, liste)
    "a": ("Üst Giyim", "Tişört", 1, 500.0),
    "b": ("Alt Giyim", "Pantolon", 1, 800.0),
    "c": ("Üst Giyim", "Gömlek", 1, 600.0),
    "d": ("Üst Giyim", "Tişört", 2, 400.0),
}
KAMPANYALAR = [   # id, tip, bas, bit, ust, line, bolge, oran
    ("KMP_A", "kategori", "2024-04-08", "2024-04-14", "Üst Giyim", "", "Marmara", 0.2),
    ("KMP_B", "kategori", "2023-10-16", "2023-10-22", "Alt Giyim", "", "Ege,Akdeniz", 0.3),
]
OUTLET_GUNLUK, OUTLET_IADE, RAF, DEPO = 40, 10, 1000, 3000
IADE_MAGAZA, IADE_ONLINE = 0.06, 0.27


def egri(harf: str, w: np.ndarray) -> np.ndarray:
    w = np.asarray(w, float)
    if harf in "ac":
        return np.where(w < 3, 1.0, 0.92 ** (w - 2))
    if harf == "b":
        return 0.95 ** w
    return 0.9 ** w


def _lansman(sezon: str, dalga: int) -> pd.Timestamp:
    return pd.Timestamp(SEZONLAR[sezon][0]) + pd.Timedelta(days=35 * (dalga - 1))


def _pazartesi(t: pd.Timestamp) -> pd.Timestamp:
    return t - pd.Timedelta(days=t.dayofweek)


def _kampanya_orani(magaza_bolge: str, tip: str, ust: str, t: pd.Timestamp) -> float:
    if tip == "Online":
        return 0.0
    oran = 0.0
    for _k, _tip, bas, bit, kust, _line, bolge, r in KAMPANYALAR:
        if pd.Timestamp(bas) <= t <= pd.Timestamp(bit) and ust == kust and magaza_bolge in bolge.split(","):
            oran = max(oran, r)
    return oran


def oyuncak() -> dict[str, pd.DataFrame]:
    urun, fiyat, satis, stok, depo = [], [], [], [], []
    for sezon, (_l, indirim, cikis) in SEZONLAR.items():
        indirim, cikis = pd.Timestamp(indirim), pd.Timestamp(cikis)
        for harf, (ust, alt, dalga, liste) in OPTIONLAR.items():
            o = f"{sezon}-{harf}"
            lansman = _lansman(sezon, dalga)
            for i, (b, _f) in enumerate(BEDENLER):
                urun.append((f"{o}-{b}", o, "Collection", sezon, dalga, ust, alt, b, i + 1, "orta",
                             0.4 * liste, liste, lansman, cikis))
            # fiyat paneli: haftalık, lansman haftasından çıkışa
            md_bas = indirim - pd.Timedelta(days=28) if harf == "b" else indirim
            for p in pd.date_range(_pazartesi(lansman), cikis - pd.Timedelta(days=1), freq="7D"):
                oran = 0.3 if p >= _pazartesi(indirim) else (0.2 if p >= _pazartesi(md_bas) else 0.0)
                fiyat += [(p, o, hat, oran) for hat in ("normal", "online")]
            md = {p: r for p, _o, h, r in fiyat if _o == o and h == "normal"}
            gunler = pd.date_range(lansman, min(cikis - pd.Timedelta(days=1), SON_GUN))
            w = ((gunler - lansman).days // 7).to_numpy()
            L = egri(harf, w)
            for m, bolge, tip, carpan in MAGAZALAR:
                if tip == "Outlet":
                    continue
                for b, bf in BEDENLER:
                    if harf == "c" and (m != "S1" or b != "S"):
                        continue
                    u = f"{o}-{b}"
                    lam = (40.0 if tip == "Online" else 20.0 * carpan) * bf
                    adetler = []
                    for t, l in zip(gunler, L):
                        r_md = md[_pazartesi(t)]
                        r_k = _kampanya_orani(bolge, tip, ust, t)
                        r = max(r_md, r_k)
                        a = int(round(lam * l * (1 - r) ** (-EPS)))
                        adetler.append(a)
                        if a <= 0:
                            continue
                        gi = (t - pd.Timestamp("2022-07-04")).days
                        islem = r == 0 and m == "S2" and gi % 13 == 0
                        etiket = 0.3 if islem else r
                        satis.append((t, m, u, a, round(a * liste * (1 - etiket), 2),
                                      round(a * liste * etiket, 2), "KMP_A" if r_k > r_md and ust == "Üst Giyim"
                                      else ("KMP_B" if r_k > r_md else None)))
                    # iade: pazartesi (fiziksel, önceki 7 gün) / her 10 günde (ONL, önceki 10 gün)
                    adetler = np.array(adetler)
                    adim, pay = (10, IADE_ONLINE) if tip == "Online" else (7, IADE_MAGAZA)
                    for j in range(adim, len(gunler), adim):
                        n = int(round(pay * adetler[j - adim:j].sum()))
                        if n:
                            satis.append((gunler[j], m, u, -n, -round(n * liste * 0.9, 2),
                                          -round(n * liste * 0.1, 2), None))
                    if tip == "Online":
                        continue
                    for p in pd.date_range(_pazartesi(lansman), min(cikis, SON_GUN), freq="7D"):
                        if p >= lansman - pd.Timedelta(days=6):
                            stok.append((p, m, u, RAF, 7))
            if harf != "c":
                for b, _bf in BEDENLER:
                    u = f"{o}-{b}"
                    for t in pd.date_range(lansman, min(cikis + pd.Timedelta(days=90), SON_GUN)):
                        depo.append((t, u, DEPO))
                    # outlet penceresi: çıkıştan 84 gün + pencere dışı 6 gün
                    for k in range(90):
                        t = cikis + pd.Timedelta(days=k)
                        if t > SON_GUN:
                            break
                        satis.append((t, "OUT1", u, OUTLET_GUNLUK, OUTLET_GUNLUK * liste * 0.5,
                                      OUTLET_GUNLUK * liste * 0.5, None))
                    t = cikis + pd.Timedelta(days=30)
                    if t <= SON_GUN:
                        satis.append((t, "OUT1", u, -OUTLET_IADE, -OUTLET_IADE * liste * 0.5,
                                      -OUTLET_IADE * liste * 0.5, None))

    def df(satir, sutunlar, tarihler=()):
        d = pd.DataFrame(satir, columns=sutunlar)
        for s in tarihler:
            d[s] = pd.to_datetime(d[s]).astype(_T)
        return d

    satis_df = df(satis, ["tarih", "magaza_id", "urun_id", "adet", "tutar", "indirim_tutari",
                          "kampanya_id"], ["tarih"])
    satis_df = satis_df[satis_df["tarih"] >= VERI_BASI].reset_index(drop=True)
    satis_df["adet"] = satis_df["adet"].astype("int32")
    stok_df = df(stok, ["tarih", "magaza_id", "urun_id", "adet", "stoklu_gun"], ["tarih"])
    stok_df = stok_df[stok_df["tarih"] >= VERI_BASI].reset_index(drop=True)
    depo_df = df(depo, ["tarih", "urun_id", "adet"], ["tarih"])
    depo_df = depo_df[depo_df["tarih"] >= VERI_BASI].reset_index(drop=True)
    sezon = [(s, dl, _lansman(s, dl), pd.Timestamp(v[1]), pd.Timestamp(v[2]))
             for s, v in SEZONLAR.items() for dl in (1, 2)]
    return {
        "magaza": df([(m, m, "İstanbul", b, tip, 500, pd.Timestamp("2020-01-01"), None)
                      for m, b, tip, _c in MAGAZALAR],
                     ["magaza_id", "ad", "sehir", "bolge", "tip", "metrekare", "acilis_tarihi",
                      "kapanis_tarihi"], ["acilis_tarihi", "kapanis_tarihi"]),
        "magaza_olay": df([], ["magaza_id", "olay", "karar_tarihi", "olay_tarihi", "bitis_tarihi"],
                          ["karar_tarihi", "olay_tarihi", "bitis_tarihi"]).astype(
                              {"magaza_id": "string", "olay": "string"}),
        "urun": df(urun, ["urun_id", "option_id", "line", "sezon_kodu", "dalga", "ust_kategori",
                          "alt_kategori", "beden", "beden_sira", "fiyat_segmenti", "alis_fiyati",
                          "liste_fiyati", "lansman_tarihi", "cikis_tarihi"],
                   ["lansman_tarihi", "cikis_tarihi"]),
        "satis": satis_df,
        "stok": stok_df,
        "depo_stok": depo_df,
        "sevkiyat": df([], ["tarih", "varis_tarihi", "kaynak", "hedef", "urun_id", "adet", "tip"],
                       ["tarih", "varis_tarihi"]).astype(
                           {"kaynak": "string", "hedef": "string", "urun_id": "string",
                            "adet": "int32", "tip": "string"}),
        "siparis": df([], ["siparis_id", "tip", "option_id", "urun_id", "siparis_tarihi",
                           "planlanan_teslim", "gerceklesen_teslim", "adet"],
                      ["siparis_tarihi", "planlanan_teslim", "gerceklesen_teslim"]).astype(
                          {"siparis_id": "string", "tip": "string", "option_id": "string",
                           "urun_id": "string", "adet": "int32"}),
        "fiyat": df(fiyat, ["hafta_baslangic", "option_id", "hat", "indirim_orani"],
                    ["hafta_baslangic"]),
        "kampanya": df([(k, tip, pd.Timestamp(b), pd.Timestamp(e), u, line, bl, r)
                        for k, tip, b, e, u, line, bl, r in KAMPANYALAR],
                       ["kampanya_id", "tip", "baslangic", "bitis", "kapsam_ust_kategori",
                        "kapsam_line", "kapsam_bolge", "oran"], ["baslangic", "bitis"]),
        "sezon": df(sezon, ["sezon_kodu", "dalga", "lansman_tarihi", "indirim_baslangic",
                            "cikis_tarihi"], ["lansman_tarihi", "indirim_baslangic", "cikis_tarihi"]),
        "takvim": df([(t, False) for t in pd.date_range("2022-07-04", "2025-12-31")],
                     ["tarih", "tatil_mi"], ["tarih"]),
    }


def baglan(t: dict[str, pd.DataFrame]) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    for ad, d in t.items():
        con.register("_g", d)
        con.execute(f"create table {ad} as select * from _g")
        con.unregister("_g")
    return con


BITIS = {"SS25": date(2025, 5, 5), "AW24": date(2024, 11, 11)}


@pytest.fixture(scope="module")
def tablolar():
    return oyuncak()


@pytest.fixture(scope="module")
def ogrenilen(tablolar, tmp_path_factory):
    con = baglan(tablolar)
    try:
        return ogrenme.ogren(con, "SS25", BITIS["SS25"],
                             onbellek=tmp_path_factory.mktemp("onbellek"), kaynak_kimligi="oyuncak")
    finally:
        con.close()


@pytest.fixture(scope="module")
def ogrenilen_aw(tablolar):
    con = baglan(tablolar)
    try:
        return ogrenme.ogren(con, "AW24", BITIS["AW24"])
    finally:
        con.close()


# ----------------------------------------------------------------- esneklik


def test_eps_kampanya_oyuncak(ogrenilen):
    e = ogrenilen.eps_kampanya
    assert e["*"] == pytest.approx(EPS, rel=0.10)
    assert e["Üst Giyim"] == pytest.approx(EPS, rel=0.10)
    assert e["Alt Giyim"] == pytest.approx(EPS, rel=0.10)


def test_eps_markdown_yanli(ogrenilen):
    """Markdown yaşam eğrisinin sönen ucuna gelir: indirim adımından önceki ve sonraki iki hafta
    arasındaki düşüş fiyat etkisine yazılır, ε̂ markdown kampanyanınkinden belirgin küçük."""
    assert ogrenilen.eps_markdown["*"] < ogrenilen.eps_kampanya["*"] - 0.2


def _eps_saf_bagimsiz(t: dict, bitis) -> float:
    """`veri/tests/v4/test_ogrenilebilirlik.py::esneklik_saf`in yayımlanan veri kısmı (gizli ε hariç)."""
    b = pd.Timestamp(bitis)
    s = t["satis"][(t["satis"]["adet"] > 0) & (t["satis"]["tarih"] < b)].copy()
    u = t["urun"].drop_duplicates("option_id").set_index("option_id")
    s["option_id"] = t["urun"].set_index("urun_id")["option_id"].reindex(s["urun_id"]).to_numpy()
    cikis = pd.to_datetime(u["cikis_tarihi"]).reindex(s["option_id"]).to_numpy()
    s = s[~pd.isna(cikis) & (s["tarih"].to_numpy() < cikis)]
    m = t["magaza"]
    s = s[~s["magaza_id"].isin(m.loc[m["tip"] == "Outlet", "magaza_id"])].copy()
    s["hafta"] = (s["tarih"] - pd.to_timedelta(s["tarih"].dt.dayofweek, unit="D")).dt.normalize()
    s["hat"] = np.where(s["magaza_id"] == "ONL", "online", "normal")
    h = s.groupby(["hafta", "option_id", "magaza_id", "hat"])["adet"].sum().reset_index()
    f = t["fiyat"][(t["fiyat"]["indirim_orani"] > 0) & (t["fiyat"]["hafta_baslangic"] < b)]
    f = f.rename(columns={"hafta_baslangic": "hafta", "indirim_orani": "oran"})
    h = h.merge(f, on=["hafta", "option_id", "hat"], how="inner")
    return float(-np.polyfit(np.log(1.0 - h["oran"]), np.log(h["adet"]), 1)[0])


def test_eps_saf_veri_testinin_tanimi(ogrenilen, tablolar):
    assert ogrenilen.eps_saf == pytest.approx(_eps_saf_bagimsiz(tablolar, BITIS["SS25"]), rel=1e-9)
    assert ogrenilen.eps_saf < ogrenilen.eps_kampanya["*"]


# ------------------------------------------------------------------- yaşam


def test_yasam_fiyat_ve_kampanya_duzeltilmis(ogrenilen):
    """Tişört dalga 1 (a, SS23 + SS24): eğri L(w)/L(0)'ı bulur; indirim haftalarında fiyat
    çarpanı ε̂_kampanya ile çıkarılmıştır (ham satış indirimde ~1,9 kat sıçrar)."""
    e = ogrenilen.yasam_egrisi("Tişört", "Üst Giyim", 1)
    y = ogrenilen.yasam
    satir = y[(y["duzey"] == "alt_kategori") & (y["grup"] == "Tişört") & (y["dalga"] == 1)]
    assert (satir["kaynak"].iloc[1:] == "alt_kategori").all()
    w = np.arange(min(len(e), 28))
    assert e[0] == 1.0
    np.testing.assert_allclose(e[w], egri("a", w) / egri("a", 0), rtol=0.05)
    assert set(y["sezon_tipi"]) == {"SS"}


def test_yasam_geri_dusus(ogrenilen, ogrenilen_aw):
    y = ogrenilen.yasam
    # Gömlek dalga 1 tek hücre: her bağ üst kategoriden (Üst Giyim dalga 1)
    gomlek = y[(y["duzey"] == "alt_kategori") & (y["grup"] == "Gömlek") & (y["dalga"] == 1)]
    assert len(gomlek) > 10 and (gomlek["kaynak"].iloc[1:] == "ust_kategori").all()
    np.testing.assert_allclose(ogrenilen.yasam_egrisi("Gömlek", "Üst Giyim", 1),
                               ogrenilen.yasam_egrisi("__yok__", "Üst Giyim", 1))
    # hiç görülmemiş alt ve üst kategori: line eğrisi
    line = y[(y["duzey"] == "line") & (y["dalga"] == 1)].sort_values("hafta")["carpan"].to_numpy()
    np.testing.assert_allclose(ogrenilen.yasam_egrisi("Etek", "Elbise", 1), line)
    # hiç görülmemiş dalga: düz eğri
    np.testing.assert_allclose(ogrenilen.yasam_egrisi("Tişört", "Üst Giyim", 9), [1.0])
    # AW24 yalnız AW23'ten: Tişört dalga 1 tek sezonda eşik altı, üst kategori de; line'a düşer
    aw = ogrenilen_aw.yasam
    tis = aw[(aw["duzey"] == "alt_kategori") & (aw["grup"] == "Tişört") & (aw["dalga"] == 1)]
    assert (tis["kaynak"].iloc[1:] == "line").all()
    assert set(aw["sezon_tipi"]) == {"AW"} and ogrenilen_aw.sezonlar == ("AW23",)
    assert ogrenilen.sezonlar == ("SS23", "SS24")


def test_yasam_ogrenilen_araligin_otesi_son_deger(ogrenilen):
    e = ogrenilen.yasam_egrisi("Tişört", "Üst Giyim", 1)
    assert ogrenme.yasam_orani(e, np.array([len(e) - 1, len(e) + 5, 10**4])).tolist() == [e[-1]] * 3
    assert ogrenme.yasam_orani(e, np.array([-3, 0]))[1] == 1.0


# ------------------------------------------------------- kalıntı, iade, işlem


def test_kalinti_tanim(ogrenilen, tablolar):
    """Outlet penceresinin (çıkış, çıkış + 84) outlet mağazalarındaki net cirosu ÷ (çıkıştan 7 gün
    önceki mağaza + depo stoğu × liste), SS23 + SS24 birlikte. Elle: option başına bir sezonda
    3 beden × (84 × 40 − 10) × 0,5 × liste ÷ (3 × (6 × 1.000 + 3.000) × liste + c'nin 1.000 × 600)."""
    liste_abd = sum(v[3] for k, v in OPTIONLAR.items() if k != "c")
    elle = 3 * (84 * OUTLET_GUNLUK - OUTLET_IADE) * 0.5 * liste_abd / (
        3 * (6 * RAF + DEPO) * liste_abd + RAF * OPTIONLAR["c"][3])
    assert ogrenilen.kalinti == pytest.approx(elle, rel=1e-9)
    assert 0.15 < ogrenilen.kalinti < 0.25


def test_iade_kanal_basina(ogrenilen, tablolar):
    s = tablolar["satis"]
    u = tablolar["urun"].set_index("urun_id")
    s = s[u["sezon_kodu"].reindex(s["urun_id"]).isin(["SS23", "SS24"]).to_numpy() & (s["magaza_id"] != "OUT1")]
    for kanal, maske in (("online", s["magaza_id"] == "ONL"), ("magaza", s["magaza_id"] != "ONL")):
        x = s[maske]["adet"]
        assert ogrenilen.iade[kanal] == pytest.approx(-x[x < 0].sum() / x[x > 0].sum(), rel=1e-12)
    assert ogrenilen.iade["magaza"] == pytest.approx(IADE_MAGAZA, rel=0.1)
    assert ogrenilen.iade["online"] == pytest.approx(IADE_ONLINE, rel=0.1)


def test_islem_indirimi(ogrenilen, tablolar):
    """Kampanyasız ve markdown'sız satış satırlarında indirim payı (Σ indirim ÷ Σ (tutar + indirim))."""
    s = tablolar["satis"]
    s = s[(s["tarih"] < pd.Timestamp(BITIS["SS25"])) & (s["adet"] > 0) & s["kampanya_id"].isna()
          & (s["magaza_id"] != "OUT1")]
    u = tablolar["urun"].set_index("urun_id")
    s = s.assign(option_id=u["option_id"].reindex(s["urun_id"]).to_numpy(),
                 cikis=u["cikis_tarihi"].reindex(s["urun_id"]).to_numpy(),
                 hafta=s["tarih"] - pd.to_timedelta(s["tarih"].dt.dayofweek, unit="D"),
                 hat=np.where(s["magaza_id"] == "ONL", "online", "normal"))
    s = s[s["tarih"] < s["cikis"]]
    f = tablolar["fiyat"].rename(columns={"hafta_baslangic": "hafta"})
    s = s.merge(f, on=["hafta", "option_id", "hat"], how="left")
    s = s[s["indirim_orani"].fillna(0) == 0]
    beklenen = s["indirim_tutari"].sum() / (s["tutar"] + s["indirim_tutari"]).sum()
    assert ogrenilen.islem == pytest.approx(beklenen, rel=1e-9)
    assert 0 < ogrenilen.islem < 0.3


def test_ortak_carpanlar_tasinir(ogrenilen):
    assert set(ogrenilen.hafta_gunu) == {(k, g) for k in ("magaza", "online") for g in range(7)}
    assert ogrenilen.hafta_gunu[("magaza", 0)] == pytest.approx(1.0, abs=0.05)
    assert {"magaza_id", "option_id", "urun_id", "pay"} <= set(ogrenilen.beden_payi.columns)
    # SS25 (test sezonu) option'ları bitişten önceki satışlarıyla beden payında
    assert (ogrenilen.beden_payi["option_id"] == "SS25-a").any()


# ------------------------------------------------------------ sızıntı, kimlik


def _boz(t: dict[str, pd.DataFrame], bitis) -> dict[str, pd.DataFrame]:
    """Bitiş günü ve sonrasındaki gözlenen satırları değiştirir (adet, stok, depo, fiyat)."""
    b = pd.Timestamp(bitis)
    t = {k: v.copy() for k, v in t.items()}
    for ad, sutun in (("satis", "tarih"), ("stok", "tarih"), ("depo_stok", "tarih")):
        m = t[ad][sutun] >= b
        assert m.any(), ad
        t[ad].loc[m, "adet"] = (t[ad].loc[m, "adet"] * 3 + 7).astype(t[ad]["adet"].dtype)
    m = t["fiyat"]["hafta_baslangic"] >= b
    t["fiyat"].loc[m, "indirim_orani"] = 0.7
    ek = t["satis"][t["satis"]["tarih"] >= b].head(50).copy()
    ek["adet"] = 999
    t["satis"] = pd.concat([t["satis"], ek], ignore_index=True)
    return t


def test_ogrenme_bitis_sonrasini_gormez(ogrenilen, tablolar):
    con = baglan(_boz(tablolar, BITIS["SS25"]))
    try:
        bozuk = ogrenme.ogren(con, "SS25", BITIS["SS25"])
    finally:
        con.close()
    assert bozuk.kimlik() == ogrenilen.kimlik()


def test_kimlik_icerik_ozeti(ogrenilen):
    assert ogrenilen.kimlik() == ogrenilen.kimlik()
    kopya = pickle.loads(pickle.dumps(ogrenilen))
    assert kopya.kimlik() == ogrenilen.kimlik()
    degisik = dataclasses.replace(ogrenilen, kalinti=ogrenilen.kalinti + 1e-9)
    assert degisik.kimlik() != ogrenilen.kimlik()
    y = ogrenilen.yasam.copy()
    y.loc[y.index[3], "carpan"] *= 1.0000001
    assert dataclasses.replace(ogrenilen, yasam=y).kimlik() != ogrenilen.kimlik()


def test_onbellek_yeniden_kullanilir_ve_anahtarli(tablolar, tmp_path, monkeypatch):
    con = baglan(tablolar)
    try:
        ilk = ogrenme.ogren(con, "SS25", BITIS["SS25"], onbellek=tmp_path, kaynak_kimligi="k1")
        dizinler = sorted(p.name for p in tmp_path.iterdir())
        assert len(dizinler) == 1 and dizinler[0].endswith("_SS25")
        kayit = json.loads((tmp_path / dizinler[0] / "kimlik.json").read_text(encoding="utf-8"))
        assert kayit["kaynak"] == "k1" and kayit["test_sezonu"] == "SS25"

        def yasak(*a, **k):
            raise AssertionError("önbellek varken günlük tablo yeniden kurulmamalı")

        monkeypatch.setattr(ogrenme.hazirlik, "gunluk_yaz", yasak)
        monkeypatch.setattr(ogrenme.hazirlik, "carpanlar_yaz", yasak)
        ikinci = ogrenme.ogren(con, "SS25", BITIS["SS25"], onbellek=tmp_path, kaynak_kimligi="k1")
        assert ikinci.kimlik() == ilk.kimlik()
        with pytest.raises(AssertionError, match="yeniden"):     # başka kaynak: yeni anahtar
            ogrenme.ogren(con, "SS25", BITIS["SS25"], onbellek=tmp_path, kaynak_kimligi="k2")
        with pytest.raises(ValueError, match="kaynak_kimligi"):  # bellek içi, kimliksiz
            ogrenme.ogren(con, "SS25", BITIS["SS25"], onbellek=tmp_path)
    finally:
        con.close()


def test_ayni_tip_kapanmis_sezon_yoksa_hata(tablolar):
    con = baglan(tablolar)
    try:
        with pytest.raises(ValueError, match="kapanmış"):
            ogrenme.ogren(con, "SS25", date(2023, 9, 1))
        with pytest.raises(ValueError, match="sezon"):
            ogrenme.ogren(con, "XX25", BITIS["SS25"])
    finally:
        con.close()


# ------------------------------------------------------------ gerçek veri


@pytest.mark.veri
def test_ogren_ss25():
    """Yayımlanan v4, SS25 (bitiş 2025-05-05). Bantlar keşiften (R3): ε̂ kampanya "*" 1,5–2,0,
    ε̂ markdown < ε̂ kampanya, kalıntı 0,05–0,30. Önbellek `cikti/ogrenme/`."""
    from pathlib import Path

    from markdown import kaynak, sabitler
    con = kaynak.baglan()
    try:
        o = ogrenme.ogren(con, "SS25", date.fromisoformat(sabitler.OGRENME_BITIS["SS25"]),
                          onbellek=Path(__file__).resolve().parents[1] / "cikti" / "ogrenme")
    finally:
        con.close()
    print(f"\nε̂ kampanya {o.eps_kampanya}\nε̂ markdown {o.eps_markdown}\nε̂ saf {o.eps_saf:.4f}"
          f"\nkalıntı {o.kalinti:.4f} iade {o.iade} işlem {o.islem:.4f} sezonlar {o.sezonlar}")
    assert 1.5 <= o.eps_kampanya["*"] <= 2.0
    assert o.eps_markdown["*"] < o.eps_kampanya["*"]
    assert 0.05 <= o.kalinti <= 0.30
    assert o.sezonlar == ("SS23", "SS24")
    assert o.eps_saf < 1.0
    assert 0.03 < o.iade["magaza"] < 0.12 and 0.15 < o.iade["online"] < 0.40
