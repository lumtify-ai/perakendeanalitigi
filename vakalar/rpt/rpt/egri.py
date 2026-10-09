"""Yaşam eğrisinin ŞEKLİ: lansmandan h hafta sonra sezon talebinin ne kadarı
geçmiş olur (birikimli pay k_h).

RPT kararının bilgisi içinde bulunulan sezondan gelir (kullanıcının cümlesi:
"RPT geçmişe değil bu sezona bakar"). Ama ilk haftaların satışını sezona
taşımak için eğrinin şekli gerekir; şekil ürüne değil takvime ve kategoriye
bağlıdır ve **geçmiş sezonlardan** öğrenilir. Seviye (ürünün kendisi ne
kadar tutuyor) bu sezonun erken haftalarından gelir — `sansur.py`.

ÜÇ YÖNTEM

    ham          geçmiş sezonların SATIŞI (brüt), grup içinde toplanıp haftalara
                 paylaştırılır (FRR 2001'in perakendecisinin yaptığı). Satış
                 sansürlüdür: tutan ürün üçüncü haftada bitince eğrinin
                 kuyruğu yapay olarak incelir ve erken haftalar şişer.
    duzeltilmis  satış + ortak Basit'in kaybı (`sansur.karar_ani_talep`): stoksuz
                 ve tükenen günlerin talebi aynı hücrenin ve option'ın stoklu
                 günlerinden kurulur. Basit karar anı modundadır (Ruling R4): karar
                 anı oyun sezonunun ilk lansman sabahı, çarpanlar o anda kapanmış
                 sezonlardan (`hazirlik.carpanlar_kapanmis`); geçmiş sezonlar o
                 sabah bilinen veriyle düzeltilir.
    gercek       gerçek talep. Yalnız argüman olarak verilen gerçek tablosuyla
                 (`gercek=`; raporda hakemden) ve yalnız rapor / test içindir;
                 hiçbir karar bu eğriyi kullanmaz. Modül hakemi okumaz.

HEDEF. `indirim`: sezon talebi = lansman → indirim başı (FRR'nin "sezon"u;
tam fiyat dönemi). `cikis`: lansman → çıkış, indirim dönemi dahil (RPT'nin
indirimde satacağı payı görmek için).

KAPSAM. Mağaza ve online hücreleri (`sansur` ile aynı kapsam).

SIZINTI KALKANI. `oyun_egrisi` / `oyun_egrileri` yalnız oyun sezonundan önce
eksiksiz kapanmış sezonları (`kaynak.gecmis_sezonlar`: AW24 ← SS23, AW23, SS24;
SS25 ← + AW24) ve yalnız oyunun ilk lansman sabahından önceki satırları kullanır
(`karar_ani_talep(…, t0, …)`). `cikis` eğrisi, geçmiş sezonun çıkışı oyun
başlangıcından sonraysa (SS24 çıkışı 2024-08-26, AW24 lansmanı 2024-08-19; AW24
çıkışı 2025-02-24, SS25 lansmanı 2025-02-10) o sezonun son haftalarını göremez;
kırpılmış veriyle ne görünüyorsa o.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import kaynak

YONTEMLER = ("ham", "duzeltilmis", "gercek")
HEDEFLER = ("indirim", "cikis")


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


def _haftalik(tablo: pd.DataFrame, deger: str, opt: pd.DataFrame, grup: tuple,
              hedef: str) -> pd.DataFrame:
    """Hücre-gün tablosunu (tarih, option_id, `deger`) grup × lansmandan hafta
    toplamına indirir; yalnız hedef penceresi (lansman ≤ tarih < indirim / çıkış)."""
    if hedef not in HEDEFLER:
        raise ValueError(hedef)
    son = "indirim_baslangic" if hedef == "indirim" else "cikis_tarihi"
    o = opt[["option_id", "lansman_tarihi", son, *grup]].drop_duplicates("option_id").copy()
    o["option_id"] = o["option_id"].astype(str)
    d = pd.DataFrame({"option_id": tablo["option_id"].astype(str).to_numpy(),
                      "tarih": tablo["tarih"].to_numpy("datetime64[ns]"),
                      "w": tablo[deger].to_numpy(np.float64)})
    d = d.merge(o, on="option_id")
    d = d[(d["tarih"] >= d["lansman_tarihi"]) & (d["tarih"] < d[son])]
    d["h"] = (d["tarih"] - d["lansman_tarihi"]).dt.days // 7
    d["_g"] = list(zip(*[d[g] for g in grup]))
    return d.groupby(["_g", "h"])["w"].sum().reset_index()


def egri_ogren(tablo: pd.DataFrame | None, opt: pd.DataFrame, sezonlar, yontem: str = "duzeltilmis",
               grup: tuple = ("dalga",), hedef: str = "indirim", line: str = "Collection",
               gercek: pd.DataFrame | None = None) -> Egri:
    """Verilen sezonların `line` option'larından eğri.

    tablo   `sansur.karar_ani_talep` çıktısı (hücre-gün; `brut_satis`, `talep`):
            ham → brut_satis, duzeltilmis → talep
    gercek  yalnız `yontem="gercek"`: hücre-gün gerçek talep (tarih, option_id,
            talep); bu yöntem `tablo`yu okumaz
    """
    if yontem not in YONTEMLER:
        raise ValueError(yontem)
    if yontem == "gercek":
        if gercek is None:
            raise ValueError("egri_ogren: 'gercek' yöntemi gerçek tabloyu argüman ister (gercek=)")
        tablo, deger = gercek, "talep"
    else:
        deger = "brut_satis" if yontem == "ham" else "talep"
    sezonlar = tuple(sezonlar)
    o = opt[opt["sezon_kodu"].isin(sezonlar) & (opt["line"] == line)]
    tablo = tablo[tablo["option_id"].astype(str).isin(set(o["option_id"].astype(str)))]
    w = _haftalik(tablo, deger, o, tuple(grup), hedef)

    satirlar = {}
    for g, wg in w.groupby("_g", sort=True):
        H = int(wg["h"].max()) + 1
        v = wg.set_index("h")["w"].reindex(range(H), fill_value=0.0).to_numpy(float)
        satirlar[g] = v / v.sum() if v.sum() > 0 else v

    yedek = None
    if tuple(grup) != ("dalga",) and "dalga" in grup:
        yedek = egri_ogren(tablo if yontem != "gercek" else None, opt, sezonlar, yontem,
                           ("dalga",), hedef, line, gercek)
    return Egri(paylar=satirlar, grup=tuple(grup), yontem=yontem, hedef=hedef,
                sezonlar=sezonlar, yedek=yedek)


# ------------------------------------------------------------ oyun sezonu


def gecmis_sezonlar(oyun_sezonu: str) -> tuple:
    """Oyun sezonundan önce eksiksiz kapanmış sezonlar (`kaynak.gecmis_sezonlar`)."""
    return kaynak.gecmis_sezonlar(oyun_sezonu)


def oyun_baslangici(opt: pd.DataFrame, oyun_sezonu: str) -> pd.Timestamp:
    """Oyun sezonunun ilk lansman sabahı (öğrenmenin karar anı, Ruling R4)."""
    s = opt.loc[opt["sezon_kodu"] == oyun_sezonu, "lansman_tarihi"]
    if s.empty:
        raise ValueError(f"{oyun_sezonu} option'ı yok")
    return pd.Timestamp(s.min()).normalize()


def gecmis_havuzu(opt: pd.DataFrame, sezonlar, line: str = "Collection") -> pd.DataFrame:
    """Geçmiş sezonların `line` option'ları, lansmandan çıkışa (eğrinin karar havuzu)."""
    o = opt[opt["sezon_kodu"].isin(tuple(sezonlar)) & (opt["line"] == line)]
    return pd.DataFrame({"option_id": o["option_id"].astype(str).to_numpy(),
                         "bas": pd.to_datetime(o["lansman_tarihi"]).to_numpy(),
                         "son": pd.to_datetime(o["cikis_tarihi"]).to_numpy()})


def gecmis_talep(gunluk: pd.DataFrame, opt: pd.DataFrame, oyun_sezonu: str, carpanlar,
                 line: str = "Collection") -> pd.DataFrame:
    """Geçmiş sezonların hücre-gün talebi, oyunun ilk lansman sabahında bilinenle
    (`sansur.karar_ani_talep(gunluk, t0, carpanlar, gecmis_havuzu)`). `carpanlar`
    t0'da kapanmış sezonlardan (`hazirlik.carpanlar_kapanmis(…, t0)`)."""
    from .sansur import karar_ani_talep

    gecmis = gecmis_sezonlar(oyun_sezonu)
    t0 = oyun_baslangici(opt, oyun_sezonu)
    return karar_ani_talep(gunluk, t0, carpanlar, gecmis_havuzu(opt, gecmis, line))


def oyun_egrisi(gunluk: pd.DataFrame, opt: pd.DataFrame, oyun_sezonu: str, carpanlar,
                yontem: str = "duzeltilmis", grup: tuple = ("dalga",),
                hedef: str = "indirim") -> Egri:
    """Oyun sezonu için eğri: geçmiş sezonlar, oyunun ilk lansman sabahına dek
    bilinen veriyle (sızıntı kalkanı). `yontem` ham ya da duzeltilmis."""
    if yontem == "gercek":
        raise ValueError("oyun_egrisi: 'gercek' karar eğrisi değildir; egri_ogren(gercek=…)")
    talep = gecmis_talep(gunluk, opt, oyun_sezonu, carpanlar)
    return egri_ogren(talep, opt, gecmis_sezonlar(oyun_sezonu), yontem, grup, hedef)


def oyun_egrileri(gunluk: pd.DataFrame, opt: pd.DataFrame, oyun_sezonu: str, carpanlar) -> dict:
    """Oyun sezonunun dört eğrisi {(yöntem, hedef): Egri}, tek kestirimle."""
    talep = gecmis_talep(gunluk, opt, oyun_sezonu, carpanlar)
    gecmis = gecmis_sezonlar(oyun_sezonu)
    return {(y, h): egri_ogren(talep, opt, gecmis, y, ("dalga",), h)
            for y in ("ham", "duzeltilmis") for h in HEDEFLER}
