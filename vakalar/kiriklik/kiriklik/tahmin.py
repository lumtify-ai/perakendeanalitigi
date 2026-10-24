"""Ufuk talebi tahmini (tasarım §0, K9; Ruling R8). Karar modülü: yalnız açık bilgi, karar gününden sonrasına bakmaz.

    ogrenilen(con, sezon, onbellek=None, kaynak_kimligi=None) -> Ogrenilen
    ufuk_talebi(g: KararGirdisi, og: Ogrenilen) -> DataFrame [magaza_id, urun_id, mu_tam, mu_ind, fiyat_tam, fiyat_ind]

**Çarpanlar** `markdown.ogrenme.ogren`den gelir (İndirim Takvimi'nin sınanmış karar modülü; `bitis` = karar günü,
yani karardan sonraki satır öğrenmeye girmez): ε̂ kampanya, hafta günü, özel gün, beden payı, yaşam eğrisi, işlem
indirimi, iade. Öğrenme gerçek veride dakikalar sürer; `onbellek` verilirse günlük tablo ve ortak çarpanlar orada tutulur.

**Hücreler.** Uygun aday kırık çifti (`uygunluk.adaylar(g).uygun`) olan her option'ın, `uygun` mağazalardaki bütün
SKU satırları (`g.hucre`): kırık bedenin kendi satışı sıfır olsa da hücre vardır. Bunlar olası alıcı ve vericilerin
hepsidir.

**Taban hız.** Option × mağaza düzeyinde, stoklu gün düzeltmeli, karardan önceki son 28 günde

    r = Σ_s satış_s ÷ Σ_s (stoklu_gün_s × pay_s)          (s: option'ın mağazadaki SKU'ları)

`pay_s` beden payı (mağazaya özgü satır varsa o, yoksa zincir `"*"`; mağaza × option içinde toplamı 1'e
normalize); `stoklu_gün` `g.stoklu`daki pazartesi fotoğraflarının (önceki 7 günde rafta olunan gün sayısı) pencereye
düşen toplamı, yani sansürlü günler paydadan çıkar. Hücre hızı `r × pay_s`: kırık bedenin satışı olmasa da beden
payı kadar talebi vardır. Payda `HIZ_ESIGI`nden (7 option-gün) azsa kanıt yetersizdir; mağaza o option'ın
**zincir hızına** düşer. Zincir hızı uygun mağazalar üstünde aynı formüldür (Σ satış ÷ Σ payda) ve payda ağırlıklı
ortalama mağazanın hızıdır; mağaza, sezon başından beri option satışındaki payının o ortalama mağazanın payına
oranı kadar büyüktür (pay eşitse zincir hızına eşit; sezonda hiç satış yoksa pay eşit). Oranın paydası mağaza
sayısı (1/n) değil ortalama mağazanın payıdır: option'ı yalnız birkaç mağaza satıyorsa 1/n ölçeği yedek hızı mağaza
sayısı kadar şişirir.

**Gün çarpanı.** `hafta_gunu("magaza", haftanın günü) × yaşam(lansmandan hafta) × özel gün`. Hız penceresinin
günlük `hafta_gunu × yaşam` ortalamasına bölünür, ufuk günlerine yeniden uygulanır (yaşam oranı =
I(gelecek hafta) ÷ I(pencerenin haftaları): `markdown.tahmin` gün gün bölmesiyle aynı fikir). Özel gün olarak
yalnız indirim başlangıcı (indirim gününden itibaren 7 gün) uygulanır; bu `g.indirim`den bilinir.

**Ufuk.** Evre 1 [karar + VARIS_GUN, indirim) tam fiyat; evre 2 [indirim, çıkış) indirimli: indirim günü
`INDIRIM_ORANI` (Lumoda'nın açık politikası, en az %30), talep `(1 − 0,30)^(−ε̂_kampanya[üst kategori])` ile
çarpılır. `mu_tam`, `mu_ind` bu iki evrenin beklenen talebidir. Fiyatlar iade payı düşülmüş net fiyattır:

    fiyat_tam = liste × (1 − işlem) × (1 − iade["magaza"])        fiyat_ind = liste × 0,70 × (1 − iade["magaza"])

**Bilinen sadeleştirmeler.** (1) Kampanyalar (Black Friday dahil) yok sayılır; hız penceresindeki kampanya
satışı hızı şişirebilir. (2) Tatil ve Black Friday özel günleri uygulanmaz: `KararGirdisi` takvimi taşımaz, bu yüzden ne
pencerede ne ufukta ayrılır. (3) Evre 2'de talep tek ε̂ ile ölçeklenir (option'ın üst kategorisi). (4) Ufuk
Poisson ortalamasıdır; dağılım optimizasyonun işi. (5) Talep stoktan bağımsızdır (stoksuz hücre de talep taşır): Σ mu,
stokla kısıtlı yayımlanan satıştan büyüktür; kıyas `min(mu, stok)` ile yapılmalıdır.

Karar anı kilidi iki yerde: `kaynak.karar_girdisi` karardan sonrasını kesmiştir; bu modül de pencereyi
`[karar − 28, karar)` (satış) ve `(karar − 28, karar]` (fotoğraf) ile kendisi kısar ve `og.bitis > karar` ise
`ValueError` verir (karardan sonrasını görmüş bir öğrenme kullanılmaz).
"""

from datetime import date, timedelta
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from markdown import ogrenme
from markdown.ogrenme import Ogrenilen, yasam_orani

from kiriklik import sabitler, uygunluk
from kiriklik.kaynak import KararGirdisi

HIZ_PENCERE_GUN = 28        # taban hız penceresi (gün)
HIZ_ESIGI = 7.0             # bir (option, mağaza) hızı için en az Σ stoklu gün × pay (option-gün eşdeğeri)
INDIRIM_ORANI = 0.30        # indirim gününden sonraki oran (Lumoda'nın açık politikası: en az %30)
KANAL = "magaza"            # fiziksel mağaza kanalı (hafta günü ve iade tablolarının anahtarı)
KOLONLAR = ["magaza_id", "urun_id", "mu_tam", "mu_ind", "fiyat_tam", "fiyat_ind"]


def ogrenilen(con: duckdb.DuckDBPyConnection, sezon: str, onbellek: Path | None = None,
              kaynak_kimligi: str | None = None) -> Ogrenilen:
    """`sezon`un karar günü öncesi satırlarından öğrenilenler (`markdown.ogrenme.ogren`; bitiş = karar günü).
    Test sezonu dışı `ValueError`. `onbellek`/`kaynak_kimligi`: öğrenmenin önbelleği (bellek içi bağlantıda
    kimlik zorunlu)."""
    if sezon not in sabitler.KARAR:
        raise ValueError(f"test sezonu değil: {sezon!r} (geçerli: {sabitler.TEST_SEZONLARI})")
    return ogrenme.ogren(con, sezon, sabitler.KARAR[sezon], onbellek=onbellek, kaynak_kimligi=kaynak_kimligi)


def _bos() -> pd.DataFrame:
    return pd.DataFrame({"magaza_id": pd.Series(dtype=object), "urun_id": pd.Series(dtype=object),
                         "mu_tam": pd.Series(dtype=float), "mu_ind": pd.Series(dtype=float),
                         "fiyat_tam": pd.Series(dtype=float), "fiyat_ind": pd.Series(dtype=float)})


def _gunler(bas: date, son: date) -> np.ndarray:
    """[bas, son) günleri (datetime64[D])."""
    return np.arange(np.datetime64(bas, "D"), np.datetime64(son, "D"))


def _hafta_gunu(gunler: np.ndarray) -> np.ndarray:
    """Pazartesi 0 ... pazar 6 (1970-01-01 perşembedir)."""
    return (gunler.astype("datetime64[D]").astype(np.int64) + 3) % 7


def _beden_payi(hucre: pd.DataFrame, bp: pd.DataFrame) -> np.ndarray:
    """Hücre başına beden payı: mağazaya özgü satır, yoksa zincir (`"*"`); mağaza × option içinde 1'e
    normalize (hepsi 0 ya da bilinmiyorsa eşit). `hucre` sırasıyla."""
    mag = bp["magaza_id"].astype(str)
    urun = bp["urun_id"].astype(str)
    zincir = pd.Series(bp["pay"].to_numpy(float)[(mag == "*").to_numpy()],
                       index=urun[mag == "*"].to_numpy()).groupby(level=0).first()
    ozel_ = bp[mag != "*"]
    ozel = pd.Series(ozel_["pay"].to_numpy(float),
                     index=pd.MultiIndex.from_arrays([mag[mag != "*"].to_numpy(), urun[mag != "*"].to_numpy()]))
    ozel = ozel.groupby(level=[0, 1]).first()
    m, u = hucre["magaza_id"].astype(str), hucre["urun_id"].astype(str)
    a = ozel.reindex(pd.MultiIndex.from_arrays([m.to_numpy(), u.to_numpy()])).to_numpy(float) \
        if len(ozel) else np.full(len(hucre), np.nan)
    z = zincir.reindex(u.to_numpy()).to_numpy(float)
    pay = np.where(np.isfinite(a), a, z)
    pay = np.where(np.isfinite(pay) & (pay > 0), pay, 0.0)
    anahtar = pd.MultiIndex.from_arrays([m.to_numpy(), hucre["option_id"].astype(str).to_numpy()])
    seri = pd.Series(pay, index=anahtar)
    toplam = seri.groupby(level=[0, 1]).transform("sum").to_numpy()
    sayi = seri.groupby(level=[0, 1]).transform("size").to_numpy()
    return np.where(toplam > 0, pay / np.where(toplam > 0, toplam, 1.0), 1.0 / sayi)


def _kanit(g: KararGirdisi, hucre: pd.DataFrame) -> pd.DataFrame:
    """Hücre başına son `HIZ_PENCERE_GUN` günün brüt satışı (`sat`), stoklu günü (`gun`) ve sezon başından
    beri brüt satışı (`sezon`); yalnız `tarih < karar` (satış), `tarih <= karar` (fotoğraf)."""
    karar = pd.Timestamp(g.karar)
    bas = karar - timedelta(days=HIZ_PENCERE_GUN)
    s = g.satis[(g.satis["tarih"] < karar) & (g.satis["adet"] > 0)]
    sat = s[s["tarih"] >= bas].groupby(["magaza_id", "urun_id"], observed=True)["adet"].sum()
    sezon = s.groupby(["magaza_id", "urun_id"], observed=True)["adet"].sum()
    f = g.stoklu[(g.stoklu["tarih"] > bas) & (g.stoklu["tarih"] <= karar)]
    gun = f.groupby(["magaza_id", "urun_id"], observed=True)["stoklu_gun"].sum()
    anahtar = pd.MultiIndex.from_frame(hucre[["magaza_id", "urun_id"]])
    return pd.DataFrame({"sat": sat.reindex(anahtar, fill_value=0).to_numpy(float),
                         "gun": gun.reindex(anahtar, fill_value=0).to_numpy(float),
                         "sezon": sezon.reindex(anahtar, fill_value=0).to_numpy(float)}, index=hucre.index)


def _hizlar(h: pd.DataFrame) -> pd.Series:
    """(option, mağaza) başına taban hız `r`; `h` sütunları: option_id, magaza_id, sat, gun, sezon, pay.
    Hücre sırasıyla döner (her hücreye kendi çiftinin hızı)."""
    h = h.assign(pay_gun=h["gun"] * h["pay"])
    cift = h.groupby(["option_id", "magaza_id"], sort=False)[["sat", "pay_gun", "sezon"]].sum()
    o = cift.index.get_level_values("option_id")
    top = {k: cift[k].groupby(o).transform("sum") for k in ("sat", "pay_gun", "sezon")}
    n = cift["sat"].groupby(o).transform("size")
    pay_m = (cift["sezon"] / top["sezon"].where(top["sezon"] > 0, 1.0)).where(top["sezon"] > 0, 1.0 / n)
    # Yedek hız: zincir hızı (Σ satış ÷ Σ payda) payda ağırlıklı ortalama mağazanın hızıdır; mağaza, kendi sezon payının
    # o ortalama mağazanın payına oranı kadar büyüktür (pay eşitse = zincir hızı).
    payda = top["pay_gun"].where(top["pay_gun"] > 0, 1.0)
    ortalama_pay = (cift["pay_gun"] * pay_m).groupby(o).transform("sum") / payda
    yedek = (top["sat"] / payda * pay_m / ortalama_pay.where(ortalama_pay > 0, 1.0)).where(
        (top["pay_gun"] > 0) & (ortalama_pay > 0), 0.0)
    kendi = (cift["sat"] / cift["pay_gun"].where(cift["pay_gun"] > 0, 1.0)).where(cift["pay_gun"] > 0, 0.0)
    r = kendi.where(cift["pay_gun"] >= HIZ_ESIGI, yedek)
    return r.reindex(pd.MultiIndex.from_frame(h[["option_id", "magaza_id"]])).set_axis(h.index)


def _option_carpanlari(g: KararGirdisi, og: Ogrenilen, opt: pd.Series) -> tuple[float, float, float, float]:
    """(F_pencere, S1, S2, ε): pencerenin günlük `hafta_gunu × yaşam` ortalaması, evre 1 ve evre 2'nin
    toplam gün çarpanı (evre 2 özel gün dahil, fiyat hariç) ve option'ın ε̂_kampanya'sı."""
    egri = og.yasam_egrisi(opt["alt_kategori"], opt["ust_kategori"], opt["dalga"])
    lansman = None if pd.isna(opt["lansman_tarihi"]) else np.datetime64(pd.Timestamp(opt["lansman_tarihi"]).date(), "D")

    def carpan(gunler: np.ndarray) -> np.ndarray:
        hg = np.array([float(og.hafta_gunu.get((KANAL, int(w)), 1.0)) for w in range(7)])[_hafta_gunu(gunler)]
        if lansman is None:
            return hg
        hafta = (gunler - lansman).astype("timedelta64[D]").astype(np.int64) // 7
        return hg * yasam_orani(egri, hafta)

    karar, indirim = g.karar, g.indirim
    pencere = carpan(_gunler(karar - timedelta(days=HIZ_PENCERE_GUN), karar))
    g1 = _gunler(karar + timedelta(days=sabitler.VARIS_GUN), indirim)
    g2 = _gunler(indirim, g.cikis)
    ozel = np.where((g2 - np.datetime64(indirim, "D")).astype(np.int64) < 7,
                    float(og.ozel_gun.get("indirim_baslangici", 1.0)), 1.0)
    return (float(pencere.mean()) if len(pencere) else 1.0, float(carpan(g1).sum()), float((carpan(g2) * ozel).sum()),
            og.eps(opt["ust_kategori"], "kampanya"))


def ufuk_talebi(g: KararGirdisi, og: Ogrenilen) -> pd.DataFrame:
    """Hücre (mağaza × SKU) başına ufuk talebi ve net fiyatlar: [magaza_id, urun_id, mu_tam, mu_ind, fiyat_tam,
    fiyat_ind] (modül docstring'i); satır sırası `g.hucre`nin. Uygun adayı olmayan option ya da uygun olmayan
    mağaza çıkmaz."""
    if og.test_sezonu != g.sezon:
        raise ValueError(f"öğrenilen sezon {og.test_sezonu!r}, karar girdisi {g.sezon!r}")
    if pd.Timestamp(og.bitis) > pd.Timestamp(g.karar):
        raise ValueError(f"öğrenme karar gününden sonrasını görmüş: bitiş {og.bitis} > karar {g.karar}")
    ad = uygunluk.adaylar(g)
    opt_uygun = set(ad.loc[ad["uygun"].astype(bool), "option_id"])
    mag_uygun = set(g.magaza.loc[g.magaza["uygun"].astype(bool), "magaza_id"])
    hucre = g.hucre[g.hucre["option_id"].isin(opt_uygun) & g.hucre["magaza_id"].isin(mag_uygun)]
    if hucre.empty:
        return _bos()
    hucre = hucre.reset_index(drop=True)

    h = pd.concat([hucre[["option_id", "magaza_id"]], _kanit(g, hucre)], axis=1)
    h["pay"] = _beden_payi(hucre, og.beden_payi)
    r = _hizlar(h).to_numpy(float)

    optionlar = g.optionlar.set_index("option_id")
    carp = {o: _option_carpanlari(g, og, optionlar.loc[o]) for o in hucre["option_id"].unique()}
    oc = np.array([carp[o] for o in hucre["option_id"]])        # [N, 4]: F, S1, S2, ε
    taban = np.divide(r * h["pay"].to_numpy(), oc[:, 0], out=np.zeros(len(hucre)), where=oc[:, 0] > 0)
    fiyat_carpani = (1.0 - INDIRIM_ORANI) ** (-oc[:, 3])
    iade = float(og.iade.get(KANAL, 0.0))
    liste = hucre["liste_fiyati"].to_numpy(float)
    return pd.DataFrame({
        "magaza_id": hucre["magaza_id"].to_numpy(), "urun_id": hucre["urun_id"].to_numpy(),
        "mu_tam": taban * oc[:, 1], "mu_ind": taban * oc[:, 2] * fiyat_carpani,
        "fiyat_tam": liste * (1.0 - og.islem) * (1.0 - iade),
        "fiyat_ind": liste * (1.0 - INDIRIM_ORANI) * (1.0 - iade)})[KOLONLAR]
