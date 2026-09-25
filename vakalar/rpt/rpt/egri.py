"""Yaşam eğrisinin ŞEKLİ: lansmandan h hafta sonra sezon talebinin ne kadarı
geçmiş olur (birikimli pay k_h).

RPT kararının bilgisi içinde bulunulan sezondan gelir (kullanıcının cümlesi:
"RPT geçmişe değil bu sezona bakar"). Ama ilk üç haftanın satışını sezona
taşımak için eğrinin şekli gerekir; şekil ürüne değil takvime ve kategoriye
bağlıdır ve **geçmiş sezonlardan** öğrenilir. Seviye (ürünün kendisi ne
kadar tutuyor) bu sezonun erken haftalarından gelir — `sansur.py`.

ÜÇ YÖNTEM

    ham          geçmiş sezonların SATIŞI, grup içinde toplanıp haftalara
                 paylaştırılır (FRR 2001'in perakendecisinin yaptığı). Satış
                 sansürlüdür: tutan ürün üçüncü haftada bitince eğrinin
                 kuyruğu yapay olarak incelir ve erken haftalar şişer.
    duzeltilmis  stoklu gün düzeltmesi: hücre-hafta satışı ~ Poisson(a_c ·
                 b_h · stoklu gün). a_c hücrenin (mağaza × SKU) seviyesi,
                 b_h haftanın göreli günlük hızı; ikisi dönüşümlü orantılı
                 uydurmayla (IPF) bulunur. Stoksuz günler denkleme girmez,
                 stoksuz kalan hücrenin seviyesi stoklu günlerinden gelir.
                 Haftalık talep ∝ b_h · (o haftanın açık günü).
    gercek       satış + kayıp satış. Yalnız rapor ve test içindir (kâhin);
                 hiçbir karar bu eğriyi kullanmaz.

HEDEF. `indirim`: sezon talebi = lansman → indirim başı (FRR'nin "sezon"u;
tam fiyat dönemi). `cikis`: lansman → çıkış, indirim dönemi dahil (RPT'nin
indirimde satacağı payı görmek için).

SIZINTI KALKANI. `oyun_egrisi` tabloları oyun sezonunun ilk lansman
sabahına kırpar ve yalnız o güne kadar indirimi başlamış TAM sezonları
kullanır (AW24 için SS24; SS25 için SS24 + AW24). AW23 pencerede indirim
öncesine yalnız bir günle göründüğü için kullanılmaz.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import kaynak

YONTEMLER = ("ham", "duzeltilmis", "gercek")
IPF_TUR = 60


@dataclass(frozen=True)
class Egri:
    """Grup başına haftalık pay tablosu.

    paylar      {grup anahtarı (tuple): dizi}; dizinin h. elemanı h. haftanın
                sezon talebindeki payı (toplamı 1)
    grup        grup kolonları, örn. ("dalga",) ya da ("ust_kategori", "dalga")
    yedek       grup bulunamazsa kullanılan daha kaba eğri (yoksa None)
    """

    paylar: dict
    grup: tuple
    yontem: str
    hedef: str
    sezonlar: tuple
    yedek: "Egri | None" = None

    def _satir(self, anahtar) -> np.ndarray:
        anahtar = anahtar if isinstance(anahtar, tuple) else (anahtar,)
        if anahtar in self.paylar:
            return self.paylar[anahtar]
        if self.yedek is not None:
            return self.yedek._satir(anahtar[-1:])
        raise KeyError(f"eğride {anahtar} yok")

    def k(self, anahtar, h: float) -> float:
        """İlk h haftanın (h. haftanın başına kadar) birikimli payı."""
        pay = self._satir(anahtar)
        tam = int(np.floor(h))
        k = pay[:tam].sum()
        if tam < len(pay):
            k += (h - tam) * pay[tam]
        return float(min(k, 1.0))

    def kalan(self, anahtar, h: float) -> float:
        """h. haftanın başından sezon sonuna kalan pay."""
        return 1.0 - self.k(anahtar, h)

    def tablo(self) -> pd.DataFrame:
        """Paylar tablo olarak (satır: grup, kolon: h)."""
        H = max(len(v) for v in self.paylar.values())
        return pd.DataFrame({k: np.pad(v, (0, H - len(v))) for k, v in self.paylar.items()}).T

    def birikimli(self, anahtar) -> np.ndarray:
        """k_0 = 0, k_1, …, k_H = 1."""
        return np.concatenate([[0.0], np.cumsum(self._satir(anahtar))])


def _anahtar_kolonu(df: pd.DataFrame, grup: tuple) -> pd.Series:
    return pd.Series(list(zip(*[df[g] for g in grup])), index=df.index)


def _hucre_verisi(hh: pd.DataFrame, hedef: str) -> pd.DataFrame:
    """Hedef penceresine göre satış, gerçek talep, açık gün ve maruz kalma."""
    if hedef == "indirim":
        s, k, acik = hh["satis_io"], hh["kayip_io"], hh["acik_io"]
    elif hedef == "cikis":
        s, k, acik = hh["satis"], hh["kayip"], hh["acik_gun"]
    else:
        raise ValueError(hedef)
    # Stoklu gün haftalıktır; indirimin bölündüğü haftada açık güne orantılı
    maruz = hh["stoklu_gun"] * np.divide(acik, hh["acik_gun"], out=np.zeros(len(hh)),
                                         where=hh["acik_gun"] > 0)
    d = hh[["magaza_id", "urun_id", "option_id", "h"]].copy()
    d["s"], d["talep"], d["acik"], d["maruz"] = s.to_numpy(), (s + k).to_numpy(), acik.to_numpy(), maruz.to_numpy()
    return d[d["acik"] > 0]


def ipf_hafta_hizi(d: pd.DataFrame, tur: int = IPF_TUR) -> pd.Series:
    """Satış ~ Poisson(a_c · b_h · maruz) modelinde b_h (göreli günlük hız).

    d kolonları: hucre (herhangi bir anahtar), h, s, maruz. Maruziyeti
    sıfır olan hücre-haftalar bilgi taşımaz ve kendiliğinden düşer. b ölçeği
    keyfîdir (ortalaması 1'e çekilir).
    """
    hucre = pd.factorize(d["hucre"])[0]
    hafta = d["h"].to_numpy().astype(int)
    s = d["s"].to_numpy(dtype=float)
    e = d["maruz"].to_numpy(dtype=float)
    C, H = hucre.max() + 1, hafta.max() + 1
    a, b = np.ones(C), np.ones(H)
    s_c = np.bincount(hucre, s, C)
    s_h = np.bincount(hafta, s, H)
    for _ in range(tur):
        payda = np.bincount(hafta, a[hucre] * e, H)
        b = np.divide(s_h, payda, out=np.zeros(H), where=payda > 0)
        payda = np.bincount(hucre, b[hafta] * e, C)
        a = np.divide(s_c, payda, out=np.zeros(C), where=payda > 0)
        olcek = b[b > 0].mean() if (b > 0).any() else 1.0
        b, a = b / olcek, a * olcek
    return pd.Series(b, index=np.arange(H))


def egri_ogren(hh: pd.DataFrame, opt: pd.DataFrame, sezonlar, yontem: str = "duzeltilmis",
               grup: tuple = ("dalga",), hedef: str = "indirim", line: str = "Collection") -> Egri:
    """Verilen sezonların hücre-hafta panelinden eğri öğrenir."""
    if yontem not in YONTEMLER:
        raise ValueError(yontem)
    sezonlar = tuple(sezonlar)
    o = opt[opt["sezon_kodu"].isin(sezonlar) & (opt["line"] == line)]
    d = _hucre_verisi(hh[hh["option_id"].isin(o["option_id"])], hedef)
    d = d.merge(o[["option_id", *grup]].drop_duplicates(), on="option_id")
    d["_g"] = _anahtar_kolonu(d, grup)

    satirlar = {}
    for g, dg in d.groupby("_g", sort=True):
        H = int(dg["h"].max()) + 1
        # Haftanın ortalama açık günü (hücre başına): son hafta kısmi
        acik = dg.groupby("h")["acik"].sum() / dg.groupby("h")["acik"].size()
        if yontem == "ham":
            w = dg.groupby("h")["s"].sum()
        elif yontem == "gercek":
            w = dg.groupby("h")["talep"].sum()
        else:
            dg = dg.assign(hucre=list(zip(dg["magaza_id"], dg["urun_id"])))
            b = ipf_hafta_hizi(dg)
            w = b.reindex(acik.index).fillna(0) * acik
        w = w.reindex(range(H), fill_value=0.0).astype(float)
        satirlar[g] = (w / w.sum()).to_numpy() if w.sum() > 0 else w.to_numpy()

    yedek = None
    if tuple(grup) != ("dalga",) and "dalga" in grup:
        yedek = egri_ogren(hh, opt, sezonlar, yontem, ("dalga",), hedef, line)
    return Egri(paylar=satirlar, grup=tuple(grup), yontem=yontem, hedef=hedef,
                sezonlar=sezonlar, yedek=yedek)


def gecmis_sezonlar(t: dict, oyun_sezonu: str) -> tuple:
    """Oyun sezonunun ilk lansmanından önce indirimi başlamış tam sezonlar."""
    bas = kaynak.sezon_baslangici(t, oyun_sezonu)
    s = t["sezon"].drop_duplicates("sezon_kodu")
    once = s[pd.to_datetime(s["indirim_baslangic"]) < bas]["sezon_kodu"]
    return tuple(k for k in kaynak.TAM_SEZONLAR if k in set(once))


def oyun_egrisi(t: dict, opt: pd.DataFrame, oyun_sezonu: str, yontem: str = "duzeltilmis",
                grup: tuple = ("dalga",), hedef: str = "indirim") -> Egri:
    """Oyun sezonu için eğri: tablolar oyunun ilk lansman sabahına kırpılır.

    `hedef="cikis"` eğrisi, geçmiş sezonun çıkışı oyun başlangıcından
    sonraysa (SS24 çıkışı 2024-08-26, AW24 lansmanı 2024-08-19) o sezonun
    son haftasını göremez; kırpılmış veriyle ne görünüyorsa o.
    """
    bas = kaynak.sezon_baslangici(t, oyun_sezonu)
    gecmis = gecmis_sezonlar(t, oyun_sezonu)
    if not gecmis:
        raise ValueError(f"{oyun_sezonu} için geçmiş tam sezon yok")
    kirpik = kaynak.tarihten_once(t, bas)
    hh = kaynak.hucre_hafta(kirpik, opt, gecmis)
    return egri_ogren(hh, opt, gecmis, yontem, grup, hedef)
