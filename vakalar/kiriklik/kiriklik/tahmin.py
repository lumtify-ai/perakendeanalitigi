"""Ufuk talebi tahmini (tasarım §0, K9; Ruling R8, R33). Karar modülü: yalnız açık bilgi, karar gününden sonrasına bakmaz.

    ogrenilen(con, sezon, onbellek=None, kaynak_kimligi=None) -> Ogrenilen
    ufuk_talebi(g: KararGirdisi, og: Ogrenilen) -> DataFrame [magaza_id, urun_id, mu_tam, mu_ind, fiyat_tam, fiyat_ind]
    kampanya_oranlari(kampanya, bolge, tip, ust_kategori, line, gunler) -> [P, D] (mağaza, option) çifti × gün oranı

**Çarpanlar** `markdown.ogrenme.ogren`den gelir (İndirim Takvimi'nin sınanmış karar modülü; `bitis` = karar günü,
yani karardan sonraki satır öğrenmeye girmez): ε̂ kampanya, hafta günü, özel gün, beden payı, yaşam eğrisi, işlem
indirimi, iade. Öğrenme gerçek veride dakikalar sürer; `onbellek` verilirse günlük tablo ve ortak çarpanlar orada tutulur.

**Hücreler (R10).** Uygun aday kırık çifti (`uygunluk.adaylar(g).uygun`) olan her option'ın, o option'dan karar günü
stoğu olan (`g.hucre` option × mağaza toplamı > 0) `uygun` mağazalardaki bütün SKU satırları: kırık bedenin kendi
satışı ve stoğu sıfır olsa da hücre vardır. Option'ı hiç stoklamayan mağaza ne alıcı ne verici olabilir, çıkmaz. Hız
ve zincir payı yine bütün uygun mağazaların kanıtından kurulur (satıp tükenmiş mağaza kanıt verir), süzme en sondadır.

**Kampanya oranı (R33).** `g.kampanya` yayımlanan `kampanya` tablosunun bütün satırlarıdır (Black Friday, kategori,
ikinci ürün; açık plan bilgisi, karardan sonrası kesilmez). (mağaza, option, gün) oranı v4 motorunun kuralıyla
kurulur (`perakende_veri.v4.kampanya.kampanya_orani`; içe aktarılmaz, kural `kampanya_oranlari`nda yeniden yazılır
ve `test_kampanya_eslemesi_v4_ile_ayni` KÜÇÜK dünyada motorunkiyle gün gün eşitler): `baslangic ≤ gün ≤ bitis`
ise kampanya etkindir; boş kapsam hepsi, dolu kapsam virgüllü listeye üyeliktir (`kapsam_ust_kategori` option'ın
üst kategorisi; `kapsam_line` line'ı, kararın option'ları hep `sabitler.LINE` olduğundan `Basic,NOS` kampanyaları
onlara dokunmaz; `kapsam_bolge` mağazanın bölgesi, bölge kapsamı Online'ı dışarıda bırakır); çakışan kampanyalarda
en yüksek oran. Black Friday bunun bir örneğidir (kapsamsız, %30).

**Gün çarpanı (R12, R33).** (option, mağaza) çiftinin günlük karakteri

    c(gün) = hafta_gunu("magaza", haftanın günü) × özel gün × yaşam(lansmandan hafta) × (1 − oran)^(−ε̂_kampanya[üst])

oran pencerede ve evre 1'de günün kampanya oranı, evre 2'de `max(INDIRIM_ORANI, kampanya)` (motorun
`oran_talep = max(md, kampanya)`; md Lumoda'nın açık politikası, indirim günü en az %30). Özel gün türü tek ve
`perakende_analitik.carpanlar.ozel_turleri` önceliğiyle (Black Friday cuması, Black Friday devamı, tatil, indirim
başlangıcı); tatiller `g.takvim`, Black Friday dönemleri `g.kampanya`nın `tip = 'black_friday'` satırları. Çift başına
`F` = pencerenin 28 günlük karakter ortalaması, `S1`, `S2` = evre 1 ve evre 2'nin karakter toplamı. `takvim` pencereyi
ve ufku kapsamıyorsa `ValueError`.

**Taban hız.** Option × mağaza düzeyinde, stoklu gün düzeltmeli, karardan önceki son 28 günde

    r = Σ_s (satış_s ÷ F) ÷ Σ_s (stoklu_gün_s × pay_s)          (s: option'ın mağazadaki SKU'ları)

Satış önce çiftin `F`'ine bölünür: pencerenin kampanyaları (kapsadıkları çiftlerde), Black Friday, hafta günü ve yaşam
tabanı şişirmez (`markdown.tahmin` gün gün bölmesinin ortalama karakterle yapılanı); bölgeli kampanya yalnız kapsadığı
mağazaların kanıtını arındırır, zincir hızı da arındırılmış satışla kurulur. `pay_s` beden payı (mağazaya özgü satır
varsa o, yoksa zincir `"*"`; mağaza × option içinde toplamı 1'e normalize); `stoklu_gün` `g.stoklu`daki pazartesi
fotoğraflarının (önceki 7 günde rafta olunan gün sayısı) pencereye düşen toplamı, yani sansürlü günler paydadan çıkar.
Hücre hızı `r × pay_s`: kırık bedenin satışı olmasa da beden payı kadar talebi vardır. Payda `HIZ_ESIGI`nden (7
option-gün) azsa kanıt yetersizdir; mağaza o option'ın **zincir hızına** düşer. Zincir hızı uygun mağazalar üstünde
aynı formüldür (Σ satış ÷ Σ payda) ve payda ağırlıklı ortalama mağazanın hızıdır; mağaza, sezon başından beri option
satışındaki payının o ortalama mağazanın payına oranı kadar büyüktür (pay eşitse zincir hızına eşit; sezonda hiç satış
yoksa pay eşit). Oranın paydası mağaza sayısı (1/n) değil ortalama mağazanın payıdır: option'ı yalnız birkaç mağaza
satıyorsa 1/n ölçeği yedek hızı mağaza sayısı kadar şişirir.

**Ufuk.** Evre 1 [karar + VARIS_GUN, indirim), evre 2 [indirim, çıkış): `mu_tam = r × pay × S1`, `mu_ind = r × pay ×
S2` (beklenen talep). Fiyatlar iade payı düşülmüş net fiyattır, evrenin günlük karakteriyle (beklenen talebiyle)
ağırlıklı ortalama:

    fiyat_tam = liste × Σ_evre1 c × (1 − kampanya; kampanyasız günde 1 − işlem) ÷ Σ_evre1 c × (1 − iade["magaza"])
    fiyat_ind = liste × Σ_evre2 c × (1 − max(0,30; kampanya)) ÷ Σ_evre2 c × (1 − iade["magaza"])

Kampanyalı gün kampanya fiyatından satar (işlem indirimi motorda yalnız oranı 0 olan günde vardır); kampanyasız evrede
`fiyat_tam = liste × (1 − işlem) × (1 − iade)`, `fiyat_ind = liste × 0,70 × (1 − iade)`. Evrenin karakteri 0 ise
ağırlıksız gün ortalaması, evre boşsa kampanyasız fiyat (`hakem.kahin_girdisi` ile aynı sözleşme).

**Model sınırları (bilerek düzeltilmedi; R33).** Kahine göre yanlılığın kampanya dışındaki asıl kaynakları:
(1) **İkame.** Motor karşılanmayan talebin bir kısmını aynı (mağaza, alt kategori, fiyat segmenti) grubunda stoklu
option'lara aktarır; yayımlanan `satis` bunu alıcı hücrenin normal satışı olarak taşır, ayıramaz. Taban hız bu yüzden
stoklu hücrenin satış potansiyelini ölçer, kahin ise hücrenin kendi talebini sayar: penceredeki ikame girişi tabanı
~%10 şişirir (tanıda satış ÷ kendi satış AW24'te 1,117, SS25'te 1,103). Kırık bedeni tamamlayan transfer tükenmeyi,
dolayısıyla ikameyi de azaltır; tahmin transferin değerini bu payla fazla sayar. (2) **Yaşam eğrisi.**
`markdown.ogrenme`nin eşleşmiş stoklu hücre zinciri, sezon ilerleyip kardeş option'lar tükendikçe stokta kalanlara
giden ikameyi her bağda taşır; yanlılık bağdan bağa çarpılır. Kazak ve Mont (daha az Trençkot) eğrileri gerçekte
olması gerekenden çok daha yavaş düşer: AW24'te evre 1 talebi ×1,24, evre 2 ×1,61 eğilim yanlılığı (tanı §4).
Düzeltme ortak öğrenme modülünün işidir (salt okunur kardeş vaka).

**Öteki sadeleştirmeler.** (1) Evre 2'de indirim sabit %30 (Lumoda'nın açık politikasının alt sınırı); gerçek yol biraz
daha derin ve option'lar arasında dağınık (fiyat çarpanı ×0,93–0,95); evre 1'de Lumoda'nın indirim gününden önceki
indirimleri bilinmez (×0,97–0,98). Fiyat yolu açık bilgi değildir; bu ikisi tahmini biraz aşağı çeker. (2) Talep tek ε̂
ile ölçeklenir (option'ın üst kategorisi). (3) Ufuk Poisson ortalamasıdır; dağılım optimizasyonun işi. (4) Talep
stoktan bağımsızdır (stoksuz hücre de talep taşır): Σ mu, stokla kısıtlı yayımlanan satıştan büyüktür; kıyas
`min(mu, stok)` ile yapılmalıdır.

**Bilinen sapma.** Gerçek veride stoklu hücrelerde Σ min(mu_tam, stok) ÷ yayımlanan satış AW24'te 1,00, SS25'te 0,96;
veri testi bunu [0,75; 1,35] içinde sınar. Bu sağlama yanlılığı göremez, çünkü satış da ikameyi içerir. Kahine göre
yanlılık (yol 0, bütün hücreler; R27) mu_tam / mu_ind AW24'te +%33 / +%66 (yukarıdaki iki model sınırı), SS25'te
+%14 / +%18 (kampanya arındırılmadan +%62 / +%67 idi; kalanı ikame).

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
_CUMA = 4
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
    """(option, mağaza) başına taban hız `r`; `h` sütunları: option_id, magaza_id, sat (çiftin pencere karakterine
    bölünmüş), gun, sezon, pay. Hücre sırasıyla döner (her hücreye kendi çiftinin hızı)."""
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


def _gun_tablolari(g: KararGirdisi, og: Ogrenilen) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Pencere, evre 1 ve evre 2 için (günler, hafta günü × özel gün çarpanı).

    Özel gün türü tek ve öncelikli (`perakende_analitik.carpanlar.ozel_turleri` ile aynı): Black Friday dönemindeki
    cuma `black_friday`, dönemin öteki günleri `black_friday_devami`, öteki tatiller `tatil`, indirim gününden itibaren
    7 gün `indirim_baslangici`. Black Friday dönemleri `g.kampanya`nın `tip = 'black_friday'` satırlarıdır; fiyat
    etkileri burada değil, öteki kampanyalarla birlikte `kampanya_oranlari`ndadır."""
    karar, indirim = g.karar, g.indirim
    gunler = {"pencere": _gunler(karar - timedelta(days=HIZ_PENCERE_GUN), karar),
              "evre1": _gunler(karar + timedelta(days=sabitler.VARIS_GUN), indirim),
              "evre2": _gunler(indirim, g.cikis)}
    takvim = g.takvim["tarih"].to_numpy().astype("datetime64[D]")
    ilk, son = min(d[0] for d in gunler.values() if len(d)), max(d[-1] for d in gunler.values() if len(d))
    if len(takvim) == 0 or takvim.min() > ilk or takvim.max() < son:
        raise ValueError(f"takvim [{ilk}, {son}] günlerini kapsamıyor (karar girdisi `takvim` tablosuyla kurulmalı)")
    tatil_gunleri = takvim[g.takvim["tatil_mi"].to_numpy(bool)]
    hg_tablo = np.array([float(og.hafta_gunu.get((KANAL, w), 1.0)) for w in range(7)])
    ozel = {t: float(og.ozel_gun.get(t, 1.0)) for t in ("black_friday", "black_friday_devami", "tatil",
                                                           "indirim_baslangici")}
    bf_donemleri = g.kampanya[g.kampanya["tip"] == "black_friday"]
    sonuc = {}
    for ad, d in gunler.items():
        hafta_gunu = _hafta_gunu(d)
        bf = np.zeros(len(d), dtype=bool)
        for b in bf_donemleri.itertuples(index=False):
            bf |= (d >= np.datetime64(pd.Timestamp(b.baslangic).date(), "D")) \
                & (d <= np.datetime64(pd.Timestamp(b.bitis).date(), "D"))
        ib = (d >= np.datetime64(indirim, "D")) & (d < np.datetime64(indirim, "D") + np.timedelta64(7, "D"))
        turler = (("black_friday", bf & (hafta_gunu == _CUMA)), ("black_friday_devami", bf),
                  ("tatil", np.isin(d, tatil_gunleri)), ("indirim_baslangici", ib))
        f, alindi = np.ones(len(d)), np.zeros(len(d), dtype=bool)
        for tur, maske in turler:
            maske = maske & ~alindi
            f[maske] *= ozel[tur]
            alindi |= maske
        sonuc[ad] = (d, hg_tablo[hafta_gunu] * f)
    return sonuc


def _dolu(kapsam) -> bool:
    """Kapsam dizgesi dolu mu (boş, None ya da NaN: hepsi)."""
    return not (kapsam is None or (isinstance(kapsam, float) and np.isnan(kapsam)) or not str(kapsam))


def _kapsam(degerler: np.ndarray, kapsam) -> np.ndarray:
    """Boş kapsam = hepsi; aksi halde virgülle ayrılmış kümeye üyelik (v4 motorunun `_kapsam_maskesi`)."""
    if not _dolu(kapsam):
        return np.ones(len(degerler), dtype=bool)
    return np.isin(degerler, str(kapsam).split(","))


def kampanya_oranlari(kampanya: pd.DataFrame, bolge, tip, ust_kategori, line, gunler: np.ndarray) -> np.ndarray:
    """[P, D] (mağaza, option) çifti × gün kampanya oranı (modül notu "Kampanya oranı"). `bolge`, `tip` çiftin
    mağazasının, `ust_kategori`, `line` option'ının [P] değerleri; `gunler` takvim günleri (datetime64). Gün
    `baslangic ≤ gün ≤ bitis` ise kampanya etkindir; boş kapsam hepsi; bölge kapsamı Online'ı dışarıda bırakır;
    çakışan kampanyalarda en yüksek oran (v4 `kampanya.kampanya_orani` kuralı, yayımlanan tablodan)."""
    bolge, tip, ust, line_ = (np.asarray(x).astype(str) for x in (bolge, tip, ust_kategori, line))
    gun = np.asarray(gunler).astype("datetime64[D]").astype("datetime64[ns]")
    online = tip == "Online"
    oran = np.zeros((len(bolge), len(gun)))
    for k in kampanya.itertuples(index=False):
        aktif = (gun >= pd.Timestamp(k.baslangic).to_datetime64()) & (gun <= pd.Timestamp(k.bitis).to_datetime64())
        if not aktif.any():
            continue
        cift = _kapsam(ust, k.kapsam_ust_kategori) & _kapsam(line_, k.kapsam_line)
        if _dolu(k.kapsam_bolge):
            cift &= _kapsam(bolge, k.kapsam_bolge) & ~online
        if cift.any():
            ix = np.ix_(cift, aktif)
            oran[ix] = np.maximum(oran[ix], float(k.oran))
    return oran


def _agirlikli(c: np.ndarray, fiyat: np.ndarray, bos: float) -> np.ndarray:
    """[P] çift başına `c` (günlük karakter, beklenen talebe orantılı) ağırlıklı ortalama fiyat oranı; çiftin evre
    karakteri 0 ise ağırlıksız gün ortalaması, evre boşsa `bos`."""
    if c.shape[1] == 0:
        return np.full(len(c), bos)
    toplam = c.sum(axis=1)
    return np.where(toplam > 0, (c * fiyat).sum(axis=1) / np.where(toplam > 0, toplam, 1.0), fiyat.mean(axis=1))


def _cift_carpanlari(g: KararGirdisi, og: Ogrenilen, cift: pd.DataFrame, gun: dict) -> dict[str, np.ndarray]:
    """(option, mağaza) çifti başına [P]: `F` pencerenin günlük karakter ortalaması, `S1`, `S2` evre 1 ve evre 2'nin
    karakter toplamı, `p1`, `p2` evrelerin talep ağırlıklı fiyat oranı (liste fiyatına, iade öncesi). Günlük karakter
    = hafta günü × özel gün × yaşam × (1 − oran)^(−ε̂_kampanya[üst]); oran pencerede ve evre 1'de günün kampanya
    oranı, evre 2'de max(`INDIRIM_ORANI`, kampanya). Fiyat oranı evre 1'de kampanyalı gün 1 − kampanya, kampanyasız
    gün 1 − işlem; evre 2'de 1 − max(`INDIRIM_ORANI`, kampanya)."""
    o_kod, o_ad = pd.factorize(cift["option_id"])
    opt = g.optionlar.set_index("option_id").loc[o_ad]
    mag = g.magaza.set_index("magaza_id").loc[cift["magaza_id"]]
    eps = np.array([og.eps(u, "kampanya") for u in opt["ust_kategori"]], dtype=float)[o_kod][:, None]
    egriler = [og.yasam_egrisi(o["alt_kategori"], o["ust_kategori"], o["dalga"]) for _, o in opt.iterrows()]
    lansman = [None if pd.isna(t) else np.datetime64(pd.Timestamp(t).date(), "D") for t in opt["lansman_tarihi"]]
    kapsam = dict(bolge=mag["bolge"].to_numpy(), tip=mag["tip"].to_numpy(),
                  ust_kategori=opt["ust_kategori"].to_numpy()[o_kod], line=np.full(len(cift), sabitler.LINE))

    def yasam(j: int, d: np.ndarray) -> np.ndarray:
        if lansman[j] is None:
            return np.ones(len(d))
        return yasam_orani(egriler[j], (d - lansman[j]).astype("timedelta64[D]").astype(np.int64) // 7)

    c, fiyat = {}, {}
    for ad, (d, f) in gun.items():
        taban = np.stack([f * yasam(j, d) for j in range(len(o_ad))])[o_kod]                  # [P, D]
        oran = kampanya_oranlari(g.kampanya, gunler=d, **kapsam)
        if ad == "evre2":
            oran = np.maximum(oran, INDIRIM_ORANI)
        c[ad] = taban * (1.0 - oran) ** (-eps)
        fiyat[ad] = np.where(oran > 0, 1.0 - oran, 1.0 - og.islem) if ad == "evre1" else 1.0 - oran
    return {"F": c["pencere"].mean(axis=1), "S1": c["evre1"].sum(axis=1), "S2": c["evre2"].sum(axis=1),
            "p1": _agirlikli(c["evre1"], fiyat["evre1"], 1.0 - og.islem),
            "p2": _agirlikli(c["evre2"], fiyat["evre2"], 1.0 - INDIRIM_ORANI)}


def ufuk_talebi(g: KararGirdisi, og: Ogrenilen) -> pd.DataFrame:
    """Hücre (mağaza × SKU) başına ufuk talebi ve net fiyatlar: [magaza_id, urun_id, mu_tam, mu_ind, fiyat_tam,
    fiyat_ind] (modül docstring'i); satır sırası `g.hucre`nin. Yalnız uygun adayı olan option'ların, karar günü
    o option'dan stoğu olan uygun mağazalardaki hücreleri çıkar."""
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

    # Çift başına karakter (kampanya dahil); her hücre kendi çiftinin değerini alır.
    anahtar = hucre[["option_id", "magaza_id"]]
    cift = anahtar.drop_duplicates().reset_index(drop=True)
    cc = _cift_carpanlari(g, og, cift, _gun_tablolari(g, og))
    ci = pd.MultiIndex.from_frame(cift).get_indexer(pd.MultiIndex.from_frame(anahtar))

    # Hız, zincir hızı ve pay stoksuz (satıp tükenmiş) mağazaların kanıtını da kullanır; çıktı sonra süzülür. Satış
    # önce çiftin pencere karakterine bölünür (kampanya, Black Friday, hafta günü, yaşam arındırılır).
    h = pd.concat([anahtar, _kanit(g, hucre)], axis=1)
    F = cc["F"][ci]
    h["sat"] = np.divide(h["sat"].to_numpy(float), F, out=np.zeros(len(hucre)), where=F > 0)
    h["pay"] = _beden_payi(hucre, og.beden_payi)
    taban = _hizlar(h).to_numpy(float) * h["pay"].to_numpy()
    net = 1.0 - float(og.iade.get(KANAL, 0.0))
    liste = hucre["liste_fiyati"].to_numpy(float)
    t = pd.DataFrame({
        "magaza_id": hucre["magaza_id"].to_numpy(), "urun_id": hucre["urun_id"].to_numpy(),
        "mu_tam": taban * cc["S1"][ci], "mu_ind": taban * cc["S2"][ci],
        "fiyat_tam": liste * cc["p1"][ci] * net, "fiyat_ind": liste * cc["p2"][ci] * net})[KOLONLAR]
    stoklu_cift = hucre.groupby(["option_id", "magaza_id"])["stok"].transform("sum").to_numpy() > 0
    return t[stoklu_cift].reset_index(drop=True)
