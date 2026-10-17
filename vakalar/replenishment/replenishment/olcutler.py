"""Koşu ölçütleri (spec §4.5; v2 `olcutler.hesapla`'nın tanımları v4 koşularına).

Her ölçüt bir koşunun (`motor.Kosu` ya da tembel `KosuKaydi`) gizli gerçeğinden,
tablolarından ve kolun kaydından, bir pencerede (`[bas, bit]`, iki ucu dahil),
**fiziksel mağazalarda** (online `ONL` hariç) hesaplanır. Bu modül motoru içe
aktarmaz; koşu nesnesini (`tablo(ad, sutunlar)`, `kayitlar`) ve dünyayı (yalnız açık
alanları: `hucre_*`, `optionlar`, `urunler`, `magazalar`, `takvim`, `sku_*`)
çağıran verir. Oranlar yüzde; payda 0 ise 0.

    hesapla(kosu, w, bas, bit, tavan_ref=...)   dict[str, float] (aşağıdaki ölçütler)
    line_kirilimi(kosu, w, bas, bit)            line başına talep, satış, kayıp, bulunabilirlik, stok
    denetle(kosu)                               korunum denetimleri (bozuksa AssertionError)

**Müşteri** (`gercek`: hücre-gün gizli gerçek, hakem tanımı):

    bulunabilirlik      |talep > 0 ∧ kendi_satis > 0| / |talep > 0| (Ruling R22; v2'nin
                        "satış öncesi stoklu talepli gün / talepli gün"üne eşdeğer).
                        Küçük yanlılık (R27): hücreye gelen ikame müşterisi son adedi
                        alırsa o hücrenin kendi talebi o gün "stoksuz" sayılır.
    talep_adet, satis_adet   Σ talep, Σ kendi_satis (ikame satışı hariç)
    kayip_orani         Σ karsilanmayan / Σ talep
    ikame_payi          Σ ikameye_giden / Σ karsilanmayan (karşılanmayanın başka
                        hücreye giden kısmı; kalanı kalıcı kayıp)
    kalici_kayip_orani  Σ kalici_kayip / Σ talep

**Depo ve toplama** (kolun hafta tablosundan, `politika.hafta_tablosu`; kolun pencere
pazartesileri. Kayıt kol kaydı değilse, ör. eşdeğerlik koşusunun Lumoda'sı, `sevkiyat`'ın
penceredeki `replenishment` satırlarından: hepsi tek adet, koli yok):

    gonderilen_adet, acik_adet, koli_sayisi, koli_adet
    toplama_maliyeti_tl acik × `ACIK_TL_ADET` + koli × `KOLI_TL` (anlatı varsayımı)
    acik_doluluk_ort, acik_doluluk_tepe
                        haftalık açık adet / tavan (ortalama, en yüksek hafta). Tavan
                        kolun sonlu tavanı; sonsuzsa `tavan_ref` (oyunda kalibrasyonun
                        referans tavanı: kısıtsız kolun ne kadar toplama isteyeceği)
    kesilen_pay_yuzde   Σ karşılanmayan istek / Σ maskedeki istek (kolun kendi
                        hedefinden; tavan, koli kuralı ve depo stoğu birlikte). Net bir
                        oran: kolinin istenenden fazla getirdiği bedenler düşülür, kolili
                        kolda negatif olabilir. Kısıtsız kolda (koli yok, tavan yok) yalnız
                        depo stoğudur: kıtlık göstergesi olarak orada okunur. Lumoda
                        kaydında istek ham (maskeden önce), gönderim `sevkiyat`'tan
    tavan_bagli_hafta_yuzde   açık adedi tavana dayanan hafta / hafta (sonlu tavan)
    depo_bos_kayip_pay_yuzde  Σ karşılanmayan talep, SKU'nun depo stoğu o gün 0 iken /
                        Σ karşılanmayan talep. Kıtlık göstergesi: depo boşken hiçbir
                        öncelik kuralı kaybı kurtaramaz; büyüdükçe kıtlık bağlar

**Mağaza stoğu** (`stok`: pazartesi sabahı fotoğrafı, önceki gün sonu):

    magaza_stok_son     pencere sonundan önceki son fotoğrafın fiziksel stoğu
    stoklu_cift, bos_cift, kirik_cift, kirik_cift_pay_yuzde
                        aynı fotoğrafta, sorumlu çift evreninde (fiziksel mağaza–option;
                        option yaşıyor: lansman ≤ gün < çıkış; mağaza açık; hücre outlet
                        akışında değil; çiftin en az iki bedeni var). Stoklu: bedenler
                        toplamı > 0. **Kırık** (önerilen kural): stoklu çiftin çekirdek
                        bedenlerinden (`CEKIRDEK_BEDENLER`, beden sırası 2–4: beş bedenli
                        setlerin ortadaki üçü, zincir eğrisinde %22 + %32 + %24 = %78;
                        v2'nin [1, 2, 3] indisleri) çiftin çeşidinde olan herhangi biri 0.
                        Tek bedenli (`Standart`) çift evrende değil. Pay = kırık / stoklu.
    beden_sapmasi       stoklu çiftlerde stoğun beden dağılımı ile kolun beden payı
                        (`ihtiyac.magaza_beden_paylari`, pencere başına dek koşunun kendi
                        satışından; kolun kullandığıyla aynı) arasındaki toplam değişim
                        uzaklığı (TVD) ortalaması × 100

**Akış** (FIFO, `satisa_donme`):

    satisa_donme_gun    kolun penceredeki `replenishment` sevkiyatının (çıkışı ve varışı
                        pencerede) mağazaya varıştan satışa ortalama günü (adet ağırlıklı).
                        Hücre başına FIFO: pencere başı fotoğrafı (en eski parti), sonra
                        varış gününe göre bütün girişler (her tipten sevk, iade); çıkışlar
                        gününe göre satış ve mağazadan giden sevkler. Satılan birimin
                        partisi FIFO sırası; mağazadan sevkle giden birim satılmış sayılmaz
    satilan_gonderilen, satilmayan_gonderilen
                        kol sevkiyatının pencerede satılan / pencere sonunda hâlâ duran adedi
    fifo_negatif_adet   FIFO'da çıkış günü partinin varışından önce düşen birim (kolun hücrelerinde,
                        her parti ve çıkış türü): akışlar fotoğrafla tutarlıysa 0. Ortalamada bu
                        birimlerin süresi 0'a kırpılır; sayı tutarsızlığın büyüklüğünü gösterir
    str                 penceredeki fiziksel satış (iade hariç, ikame dahil) / (pencere
                        başı mağaza stoğu + penceredeki mağaza girişleri)

`hesapla` her değeri `float` döndürür (JSON'a gider).
"""

from datetime import date

import numpy as np
import pandas as pd

from .ihtiyac import magaza_beden_paylari
from .kaynak import ONLINE, _HucreIndisi, harita_kur, hucre_anahtari
from .politika import hafta_tablosu
from .sabitler import ACIK_TL_ADET, KOLI_TL, OYUN_BAS, OYUN_BIT

CEKIRDEK_BEDENLER = (2, 3, 4)       # beden sırası (önerilen kural; modül notu)
REPL = "replenishment"


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------


def _oran(pay: float, payda: float) -> float:
    return 100.0 * float(pay) / float(payda) if payda > 0 else 0.0


def _ts(d) -> pd.Timestamp:
    return pd.Timestamp(d).normalize()


def _pencerede(df: pd.DataFrame, bas: date, bit: date, sutun: str = "tarih") -> np.ndarray:
    t = pd.to_datetime(df[sutun]).dt.normalize()
    return ((t >= _ts(bas)) & (t <= _ts(bit))).to_numpy()


def _fiziksel(df: pd.DataFrame, sutun: str = "magaza_id") -> np.ndarray:
    return (df[sutun].astype(str) != ONLINE).to_numpy()


def _tablo(kosu, ad: str, sutunlar, bas=None, bit=None, sutun: str = "tarih") -> pd.DataFrame:
    """Koşunun tablosu, yalnız `sutunlar`; `bas`/`bit` verilirse `sutun` o aralıkta.
    Tembel koşu kaydında (dizini olan) aralık Parquet süzgeciyle okunur (bütün tablo
    belleğe gelmez); öteki koşularda tablo okunup süzülür."""
    sutunlar = list(dict.fromkeys(list(sutunlar) + ([sutun] if bas is not None or bit is not None else [])))
    yol = getattr(kosu, "_yol", None)
    if callable(yol) and getattr(kosu, "dizin", None) is not None:
        suzgec = []
        if bas is not None:
            suzgec.append((sutun, ">=", _ts(bas)))
        if bit is not None:
            suzgec.append((sutun, "<", _ts(bit) + pd.Timedelta(days=1)))
        return pd.read_parquet(yol(ad), columns=sutunlar, filters=suzgec or None).reset_index(drop=True)
    df = kosu.tablo(ad, sutunlar)
    if bas is not None or bit is not None:
        t = pd.to_datetime(df[sutun])
        m = np.ones(len(df), dtype=bool)
        if bas is not None:
            m &= (t >= _ts(bas)).to_numpy()
        if bit is not None:
            m &= (t < _ts(bit) + pd.Timedelta(days=1)).to_numpy()
        df = df[m]
    return df.reset_index(drop=True)


def _kol_kaydi_mi(kosu) -> bool:
    k = getattr(kosu, "kayitlar", {}).get("replenishment")
    return k is not None and "kalem" in k.columns


def _hucre(idx: _HucreIndisi, magaza: pd.Series, urun: pd.Series) -> np.ndarray:
    """Tablo sütunlarından (kategorik ya da dizgi) dünyanın hücre indisi; evren dışı −1."""
    if isinstance(magaza.dtype, pd.CategoricalDtype) and isinstance(urun.dtype, pd.CategoricalDtype):
        return idx.kategorik(magaza.array, urun.array)
    return idx.hucre(magaza.astype(str).to_numpy(), urun.astype(str).to_numpy())


# ---------------------------------------------------------------------------
# Asgari ölçütler (Ruling R22; kalibrasyon da kullanır)
# ---------------------------------------------------------------------------


def bulunabilirlik(gercek: pd.DataFrame, bas: date, bit: date) -> float:
    """Yüzde (modül notu); pencerede talepli fiziksel hücre-gün yoksa 0."""
    s = _pencerede(gercek, bas, bit) & _fiziksel(gercek) & (gercek["talep"].to_numpy() > 0)
    payda = int(s.sum())
    if payda == 0:
        return 0.0
    return 100.0 * int((s & (gercek["kendi_satis"].to_numpy() > 0)).sum()) / payda


def toplama_maliyeti(hafta: pd.DataFrame) -> float:
    """TL; `hafta` = `politika.hafta_tablosu(kosu)` (boşsa 0)."""
    acik = float(hafta["acik_adet"].sum()) if "acik_adet" in hafta else 0.0
    koli = float(hafta["koli_sayisi"].sum()) if "koli_sayisi" in hafta else 0.0
    return acik * ACIK_TL_ADET + koli * KOLI_TL


def _son_fotograf(stok: pd.DataFrame, bit: date) -> pd.Timestamp:
    t = pd.to_datetime(stok["tarih"]).dt.normalize()
    once = (t <= _ts(bit)).to_numpy()
    if not once.any():
        raise ValueError(f"{bit} ya da öncesinde stok fotoğrafı yok")
    return t[once].max()


def magaza_stok_son(stok: pd.DataFrame, bit: date) -> float:
    """Adet: `bit` ya da öncesindeki son fotoğrafın (tarih ≤ bit) fiziksel stoğu.
    Fotoğraf o sabah, hareketlerden önce çekilir (önceki gün sonu stoğu); oyun
    penceresinin sonundan sonra fotoğraf olmadığı için ölçü iki pencerede aynı
    tanımla alınsın diye son fotoğraf. Fotoğraf yoksa `ValueError`."""
    son = _son_fotograf(stok, bit)
    t = pd.to_datetime(stok["tarih"]).dt.normalize()
    s = (t == son).to_numpy() & _fiziksel(stok)
    return float(stok["adet"].to_numpy()[s].sum(dtype=np.int64))


def temel_olcutler(kosu, bas: date, bit: date) -> dict[str, float]:
    """Kalibrasyonun ölçütleri: `bulunabilirlik`, `toplama_maliyeti_tl`,
    `magaza_stok_son` ve haftalık toplamlar (`acik_adet`, `koli_sayisi`, `koli_adet`,
    `gonderilen_adet`; kolun pencere pazartesileri)."""
    hafta = hafta_tablosu(kosu)
    toplam = {a: float(hafta[a].sum()) if a in hafta else 0.0
              for a in ("acik_adet", "koli_sayisi", "koli_adet", "gonderilen_adet")}
    return {
        "bulunabilirlik": bulunabilirlik(kosu.tablo("gercek", ["tarih", "magaza_id", "talep", "kendi_satis"]),
                                         bas, bit),
        "toplama_maliyeti_tl": toplama_maliyeti(hafta),
        "magaza_stok_son": magaza_stok_son(kosu.tablo("stok", ["tarih", "magaza_id", "adet"]), bit),
        **toplam,
    }


# ---------------------------------------------------------------------------
# Müşteri
# ---------------------------------------------------------------------------

_GERCEK = ["tarih", "magaza_id", "urun_id", "talep", "kendi_satis", "karsilanmayan", "ikameye_giden",
           "kalici_kayip"]


def musteri_olcutleri(gercek: pd.DataFrame) -> dict[str, float]:
    """`gercek` pencerede ve fiziksel (çağıran süzer): bulunabilirlik, kayıp oranları."""
    talep = gercek["talep"].to_numpy(dtype=np.int64)
    kendi = gercek["kendi_satis"].to_numpy(dtype=np.int64)
    kars = gercek["karsilanmayan"].to_numpy(dtype=np.int64)
    talepli = talep > 0
    T, K = float(talep.sum()), float(kars.sum())
    return {
        "bulunabilirlik": _oran(int((talepli & (kendi > 0)).sum()), int(talepli.sum())),
        "talep_adet": T,
        "satis_adet": float(kendi.sum()),
        "kayip_orani": _oran(K, T),
        "ikame_payi": _oran(float(gercek["ikameye_giden"].to_numpy(dtype=np.int64).sum()), K),
        "kalici_kayip_orani": _oran(float(gercek["kalici_kayip"].to_numpy(dtype=np.int64).sum()), T),
    }


# ---------------------------------------------------------------------------
# Hafta tablosu: toplama, doluluk, kesilen istek
# ---------------------------------------------------------------------------


def _lumoda_haftasi(kosu, w, bas: date, bit: date) -> pd.DataFrame:
    """Kol kaydı olmayan koşu (eşdeğerlik koşusunun Lumoda'sı): penceredeki çıkış
    pazartesileri başına `replenishment` sevki (hepsi açık adet, koli yok) ve varsa
    kaydın ham isteği (`Kaydedici`: `gun, indis, deger`; gün motor günü)."""
    sv = _tablo(kosu, "sevkiyat", ["hedef", "adet", "tip"], bas, bit)
    sv = sv[(sv["tip"].astype(str) == REPL).to_numpy() & _fiziksel(sv, "hedef")]
    t = pd.to_datetime(sv["tarih"]).dt.normalize()
    g = sv["adet"].groupby(t.to_numpy()).sum()
    hafta = pd.DataFrame({"tarih": pd.to_datetime(g.index), "gonderilen_adet": g.to_numpy(dtype=float)})
    hafta["acik_adet"] = hafta["gonderilen_adet"]
    hafta["koli_sayisi"] = 0.0
    hafta["koli_adet"] = 0.0
    k = getattr(kosu, "kayitlar", {}).get("replenishment")
    if k is not None and {"gun", "indis", "deger"} <= set(k.columns):
        takvim = pd.to_datetime(w.takvim["tarih"]).dt.normalize().to_numpy()
        istek = k.groupby("gun")["deger"].sum()
        tarih = pd.to_datetime(takvim[istek.index.to_numpy(dtype=np.int64)])
        istek = pd.Series(istek.to_numpy(dtype=float), index=tarih)
        istek = istek[(istek.index >= _ts(bas)) & (istek.index <= _ts(bit))]
        hafta = hafta.merge(pd.DataFrame({"tarih": istek.index, "istek_adet": istek.to_numpy()}),
                            on="tarih", how="outer").fillna(0.0).sort_values("tarih", ignore_index=True)
    return hafta


def hafta_olcutleri(hafta: pd.DataFrame, tavan: float, tavan_ref: float | None) -> dict[str, float]:
    """Toplama, doluluk ve kesilen istek (modül notu). `tavan` kolun tavanı (∞ olabilir)."""
    def top(a):
        return float(hafta[a].sum()) if a in hafta else 0.0

    acik = hafta["acik_adet"].to_numpy(dtype=float) if "acik_adet" in hafta else np.zeros(0)
    payda_tavan = tavan if np.isfinite(tavan) else (tavan_ref if tavan_ref else np.nan)
    if len(acik) and np.isfinite(payda_tavan) and payda_tavan > 0:
        doluluk = acik / float(np.floor(payda_tavan))
        dol_ort, dol_tepe = 100.0 * float(doluluk.mean()), 100.0 * float(doluluk.max())
    else:
        dol_ort = dol_tepe = 0.0
    if np.isfinite(tavan) and len(acik):
        bagli = _oran(int((acik >= np.floor(tavan)).sum()), len(acik))
    else:
        bagli = 0.0
    if "karsilanmayan_adet" in hafta:
        maskede = top("istek_adet") - top("maske_disi_adet")
        kesilen = _oran(top("karsilanmayan_adet"), maskede)
    elif "istek_adet" in hafta:
        kesilen = _oran(max(top("istek_adet") - top("gonderilen_adet"), 0.0), top("istek_adet"))
    else:
        kesilen = 0.0
    return {
        "gonderilen_adet": top("gonderilen_adet"),
        "acik_adet": top("acik_adet"),
        "koli_sayisi": top("koli_sayisi"),
        "koli_adet": top("koli_adet"),
        "toplama_maliyeti_tl": toplama_maliyeti(hafta),
        "acik_doluluk_ort": dol_ort,
        "acik_doluluk_tepe": dol_tepe,
        "kesilen_pay_yuzde": kesilen,
        "tavan_bagli_hafta_yuzde": bagli,
        "hafta_sayisi": float(len(hafta)),
    }


def depo_bos_kayip_payi(gercek: pd.DataFrame, depo: pd.DataFrame) -> float:
    """`gercek` (pencere, fiziksel) karşılanmayanının, SKU'nun depo stoğu o gün 0 (ya da
    satırı yok) iken olan payı, yüzde."""
    kg = gercek[gercek["karsilanmayan"].to_numpy() > 0]
    K = float(kg["karsilanmayan"].sum())
    if K <= 0:
        return 0.0
    d = depo[depo["adet"].to_numpy() > 0]
    dolu = pd.MultiIndex.from_arrays([pd.to_datetime(d["tarih"]).dt.normalize().to_numpy(),
                                      d["urun_id"].astype(str).to_numpy()])
    ara = pd.MultiIndex.from_arrays([pd.to_datetime(kg["tarih"]).dt.normalize().to_numpy(),
                                     kg["urun_id"].astype(str).to_numpy()])
    bos = ~ara.isin(dolu)
    return _oran(float(kg["karsilanmayan"].to_numpy()[bos].sum()), K)


# ---------------------------------------------------------------------------
# Mağaza stoğu: kırık çift, beden sapması
# ---------------------------------------------------------------------------


def _stok_c(stok: pd.DataFrame, idx: _HucreIndisi, C: int) -> np.ndarray:
    h = _hucre(idx, stok["magaza_id"], stok["urun_id"])
    var = h >= 0
    return np.bincount(h[var], stok["adet"].to_numpy(dtype=np.int64)[var], minlength=C).astype(np.int64)


def cift_evreni(w, harita, tarih) -> np.ndarray:
    """bool[C]: sorumlu çift evrenindeki hücreler (modül notu) `tarih` günü."""
    t = _ts(tarih)
    d = int((t - _ts(w.takvim["tarih"].iloc[0])).days)
    o = harita.hucre_option
    lans = w.optionlar["lansman_gun"].to_numpy()[o]
    cik = w.optionlar["cikis_gun"].to_numpy()[o]
    mag = w.magazalar
    acilis = pd.to_datetime(mag["acilis_tarihi"]).to_numpy()
    kapanis = pd.to_datetime(mag["kapanis_tarihi"]).to_numpy()
    acik_m = (np.isnat(acilis) | (acilis <= t.to_datetime64())) & (np.isnat(kapanis) | (kapanis > t.to_datetime64()))
    outlet = np.asarray(w.hucre_outlet_akisi, dtype=bool)
    hucre = (~harita.hucre_online) & ~outlet & (lans <= d) & (d < cik) & acik_m[harita.hucre_magaza]
    beden_say = np.bincount(harita.oc, hucre, minlength=len(harita.oc_magaza))
    return hucre & (beden_say[harita.oc] >= 2)


def kirik_ciftler(stok_c: np.ndarray, harita, evren_c: np.ndarray) -> dict[str, float]:
    """Kırık çift sayımı paydalarıyla (modül notu). `stok_c` [C] fotoğraf adedi."""
    OC = len(harita.oc_magaza)
    cift = np.bincount(harita.oc, evren_c, minlength=OC) > 0
    toplam = np.bincount(harita.oc, np.where(evren_c, stok_c, 0), minlength=OC)
    stoklu = cift & (toplam > 0)
    cekirdek = evren_c & np.isin(harita.sku_beden[harita.hucre_sku], CEKIRDEK_BEDENLER)
    eksik = np.bincount(harita.oc, cekirdek & (stok_c <= 0), minlength=OC) > 0
    kirik = stoklu & eksik
    n_stoklu = int(stoklu.sum())
    return {
        "stoklu_cift": float(n_stoklu),
        "bos_cift": float(int(cift.sum()) - n_stoklu),
        "kirik_cift": float(int(kirik.sum())),
        "kirik_cift_pay_yuzde": _oran(int(kirik.sum()), n_stoklu),
    }


def beden_sapmasi(stok_c: np.ndarray, paylar_c: np.ndarray, harita, evren_c: np.ndarray) -> float:
    """Stoklu çiftlerde TVD(stok dağılımı, beden payı) ortalaması × 100."""
    OC = len(harita.oc_magaza)
    s = np.where(evren_c, stok_c, 0).astype(float)
    p = np.where(evren_c, paylar_c, 0.0)
    st = np.bincount(harita.oc, s, minlength=OC)
    pt = np.bincount(harita.oc, p, minlength=OC)
    stoklu = st > 0
    if not stoklu.any():
        return 0.0
    dag = np.divide(s, st[harita.oc], out=np.zeros_like(s), where=st[harita.oc] > 0)
    pay = np.divide(p, pt[harita.oc], out=np.zeros_like(p), where=pt[harita.oc] > 0)
    tvd = 0.5 * np.bincount(harita.oc, np.where(evren_c, np.abs(dag - pay), 0.0), minlength=OC)
    return 100.0 * float(tvd[stoklu].mean())


# ---------------------------------------------------------------------------
# FIFO: satışa dönme süresi
# ---------------------------------------------------------------------------


def _hucre_ici_kumulatif(h: np.ndarray, a: np.ndarray) -> np.ndarray:
    """Hücreye göre sıralı `h` için hücre içi kümülatif `a` toplamı."""
    if not len(h):
        return np.zeros(0, dtype=np.int64)
    tum = a.cumsum()
    bas_i = np.r_[0, np.flatnonzero(h[1:] != h[:-1]) + 1]
    once = np.r_[0, tum[:-1]][bas_i]
    return tum - np.repeat(once, np.diff(np.r_[bas_i, len(h)]))


def fifo_eslestir(giris: pd.DataFrame, cikis: pd.DataFrame) -> pd.DataFrame:
    """Hücre başına FIFO eşlemesi.

    giris  `hucre, gun, adet, tur` (tur: str; sıralama hücre, gün, sonra verilen sıra)
    cikis  `hucre, gun, adet, tur`
    Döner: parça başına `hucre, giris_gun, giris_tur, cikis_gun, cikis_tur, adet`;
    çıkışı olmayan (pencere sonunda duran) parçada `cikis_tur` = "" ve `cikis_gun` = −1.
    Girişten fazla çıkış (tutarsız veri) eşlenmez."""
    gi = giris[giris["adet"] > 0].sort_values(["hucre", "gun"], kind="stable").reset_index(drop=True)
    ci = cikis[cikis["adet"] > 0].sort_values(["hucre", "gun"], kind="stable").reset_index(drop=True)
    if gi.empty:
        return pd.DataFrame({"hucre": [], "giris_gun": [], "giris_tur": [], "cikis_gun": [], "cikis_tur": [],
                             "adet": []})
    K = np.int64(1) << 40
    g_h = gi["hucre"].to_numpy(dtype=np.int64)
    g_a = gi["adet"].to_numpy(dtype=np.int64)
    g_cum = _hucre_ici_kumulatif(g_h, g_a)
    g_key = g_h * K + g_cum
    toplam_giris = pd.Series(g_cum, index=g_h).groupby(level=0).max()

    c_h = ci["hucre"].to_numpy(dtype=np.int64)
    c_a = ci["adet"].to_numpy(dtype=np.int64)
    c_cum = _hucre_ici_kumulatif(c_h, c_a)
    c_cum_kirp = np.minimum(c_cum, toplam_giris.reindex(c_h).fillna(0).to_numpy(dtype=np.int64))
    c_key = c_h * K + c_cum

    nokta = np.unique(np.concatenate([g_key, c_h * K + c_cum_kirp]))
    nokta = nokta[nokta % K > 0]
    h = nokta // K
    onceki = np.r_[np.int64(-1), nokta[:-1]]
    onceki = np.where(np.r_[True, h[1:] != h[:-1]], h * K, onceki)
    adet = nokta - onceki
    gi_i = np.searchsorted(g_key, nokta, side="left")
    ci_i = np.searchsorted(c_key, nokta, side="left")
    ci_var = ci_i < len(c_key)
    ci_var[ci_var] &= (c_key[ci_i[ci_var]] // K) == h[ci_var]
    ci_s = np.where(ci_var, ci_i, 0)
    return pd.DataFrame({
        "hucre": h,
        "giris_gun": gi["gun"].to_numpy()[gi_i],
        "giris_tur": gi["tur"].to_numpy()[gi_i],
        "cikis_gun": np.where(ci_var, ci["gun"].to_numpy()[ci_s] if len(ci) else -1, -1),
        "cikis_tur": np.where(ci_var, ci["tur"].to_numpy()[ci_s] if len(ci) else "", ""),
        "adet": adet,
    })


def satisa_donme(kosu, w, bas: date, bit: date) -> dict[str, float]:
    """`satisa_donme_gun`, `satilan_gonderilen`, `satilmayan_gonderilen` (modül notu)."""
    stok = _tablo(kosu, "stok", ["magaza_id", "urun_id", "adet"], None, bit)
    t0 = _son_fotograf(stok, bas)
    gun0 = _ts(w.takvim["tarih"].iloc[0])
    idx = _HucreIndisi(hucre_anahtari(w))

    def gun(s):
        return ((pd.to_datetime(s).dt.normalize() - gun0).dt.days).to_numpy(dtype=np.int64)

    sv = _tablo(kosu, "sevkiyat", ["varis_tarihi", "kaynak", "hedef", "urun_id", "adet", "tip"], t0, bit,
                sutun="tarih")
    # Kolun sevkleri: penceredeki çıkış, pencerede varış, hedef fiziksel
    var = _pencerede(sv, t0, bit, "varis_tarihi")          # varışı pencerede (yolda kalan NaT dışarıda)
    kol = (sv["tip"].astype(str) == REPL).to_numpy() & _pencerede(sv, bas, bit) & var
    h_hedef = _hucre(idx, sv["hedef"], sv["urun_id"])
    kol_hucre = np.unique(h_hedef[kol & (h_hedef >= 0)])
    if not len(kol_hucre):
        return {"satisa_donme_gun": 0.0, "satilan_gonderilen": 0.0, "satilmayan_gonderilen": 0.0}

    def ilgili(h):
        return np.isin(h, kol_hucre)

    # Girişler: fotoğraf, varışlar (sevk tarihi t0'dan önce olsa da varışı pencerede olanlar ayrıca)
    sv_once = _tablo(kosu, "sevkiyat", ["tarih", "hedef", "urun_id", "adet", "tip"], t0, bit,
                     sutun="varis_tarihi")
    sv_once = sv_once[(pd.to_datetime(sv_once["tarih"]).dt.normalize() < t0).to_numpy()]
    st = stok[(pd.to_datetime(stok["tarih"]).dt.normalize() == t0).to_numpy()]
    h_st = _hucre(idx, st["magaza_id"], st["urun_id"])
    h_once = _hucre(idx, sv_once["hedef"], sv_once["urun_id"])
    satis = _tablo(kosu, "satis", ["magaza_id", "urun_id", "adet"], t0, bit)
    h_sa = _hucre(idx, satis["magaza_id"], satis["urun_id"])
    a_sa = satis["adet"].to_numpy(dtype=np.int64)
    h_kaynak = _hucre(idx, sv["kaynak"], sv["urun_id"])
    d0 = int((t0 - gun0).days)

    giris = pd.concat([
        pd.DataFrame({"hucre": h_st, "gun": d0 - 1, "adet": st["adet"].to_numpy(dtype=np.int64),
                      "tur": "baslangic"})[ilgili(h_st)],
        pd.DataFrame({"hucre": h_once, "gun": gun(sv_once["varis_tarihi"]),
                      "adet": sv_once["adet"].to_numpy(dtype=np.int64), "tur": "diger"})[ilgili(h_once)],
        pd.DataFrame({"hucre": h_hedef, "gun": gun(sv["varis_tarihi"].fillna(t0)),
                      "adet": sv["adet"].to_numpy(dtype=np.int64),
                      "tur": np.where(kol, "kol", "diger")})[ilgili(h_hedef) & var],
        pd.DataFrame({"hucre": h_sa, "gun": gun(satis["tarih"]), "adet": -a_sa, "tur": "iade"})[
            ilgili(h_sa) & (a_sa < 0)],
    ], ignore_index=True)
    cikis = pd.concat([
        pd.DataFrame({"hucre": h_sa, "gun": gun(satis["tarih"]), "adet": a_sa, "tur": "satis"})[
            ilgili(h_sa) & (a_sa > 0)],
        pd.DataFrame({"hucre": h_kaynak, "gun": gun(sv["tarih"]),
                      "adet": sv["adet"].to_numpy(dtype=np.int64), "tur": "sevk"})[ilgili(h_kaynak)],
    ], ignore_index=True)
    p = fifo_eslestir(giris, cikis)
    k = p[p["giris_tur"] == "kol"]
    satilan = k[k["cikis_tur"] == "satis"]
    n = float(satilan["adet"].sum())
    gun_ort = float(((satilan["cikis_gun"] - satilan["giris_gun"]).clip(lower=0) * satilan["adet"]).sum()) / n \
        if n > 0 else 0.0
    eslesen = p[p["cikis_tur"] != ""]
    negatif = float(eslesen.loc[(eslesen["cikis_gun"] < eslesen["giris_gun"]).to_numpy(), "adet"].sum())
    return {"satisa_donme_gun": gun_ort, "satilan_gonderilen": n,
            "satilmayan_gonderilen": float(k.loc[k["cikis_tur"] == "", "adet"].sum()),
            "fifo_negatif_adet": negatif}


# ---------------------------------------------------------------------------
# Hepsi
# ---------------------------------------------------------------------------


def _paylar(kosu, w, harita, bas: date) -> np.ndarray:
    """Kolun beden payları: koşunun pencere başına dek fiziksel brüt satışından."""
    satis = _tablo(kosu, "satis", ["magaza_id", "urun_id", "adet"], None, _ts(bas) - pd.Timedelta(days=1))
    satis = satis[satis["adet"].to_numpy() > 0]
    idx = _HucreIndisi(hucre_anahtari(w))
    C = len(harita.hucre_sku)
    toplam = _stok_c(satis, idx, C)
    return magaza_beden_paylari(toplam[None, :], harita, 1)


def _kol_tavani(kosu) -> float:
    k = kosu.kayitlar.get("replenishment")
    t = k.loc[k["kalem"] == "tavan", "deger"] if _kol_kaydi_mi(kosu) else pd.Series(dtype=float)
    return float(t.iloc[0]) if len(t) else np.inf


def hesapla(kosu, w, bas: date = OYUN_BAS, bit: date = OYUN_BIT, *,
            tavan_ref: float | None = None) -> dict[str, float]:
    """Koşunun pencere ölçütleri (modül notu). `w` koşunun dünyası (yalnız açık
    alanlar); `tavan_ref` sonsuz tavanlı kolun doluluk paydası."""
    harita = harita_kur(w)
    idx = _HucreIndisi(hucre_anahtari(w))
    C = len(harita.hucre_sku)

    gercek = _tablo(kosu, "gercek", _GERCEK, bas, bit)
    gercek = gercek[_fiziksel(gercek)].reset_index(drop=True)
    sonuc = musteri_olcutleri(gercek)

    if _kol_kaydi_mi(kosu):
        hafta = hafta_tablosu(kosu)
        hafta = hafta[_pencerede(hafta, bas, bit)] if len(hafta) else hafta
    else:
        hafta = _lumoda_haftasi(kosu, w, bas, bit)
    sonuc |= hafta_olcutleri(hafta, _kol_tavani(kosu), tavan_ref)
    depo = _tablo(kosu, "depo_stok", ["urun_id", "adet"], bas, bit)
    sonuc["depo_bos_kayip_pay_yuzde"] = depo_bos_kayip_payi(gercek, depo)
    del gercek, depo

    stok = _tablo(kosu, "stok", ["magaza_id", "urun_id", "adet"], None, bit)
    son = _son_fotograf(stok, bit)
    st_son = stok[(pd.to_datetime(stok["tarih"]).dt.normalize() == son).to_numpy()]
    sonuc["magaza_stok_son"] = float(st_son["adet"].to_numpy()[_fiziksel(st_son)].sum(dtype=np.int64))
    stok_c = _stok_c(st_son, idx, C)
    evren = cift_evreni(w, harita, son)
    sonuc |= kirik_ciftler(stok_c, harita, evren)
    sonuc["beden_sapmasi"] = beden_sapmasi(stok_c, _paylar(kosu, w, harita, bas), harita, evren)

    sonuc |= satisa_donme(kosu, w, bas, bit)

    # STR: penceredeki fiziksel satış / (pencere başı stoğu + penceredeki girişler)
    bas_foto = _son_fotograf(stok, bas)
    st_bas = stok[(pd.to_datetime(stok["tarih"]).dt.normalize() == bas_foto).to_numpy()]
    stok_bas = float(st_bas["adet"].to_numpy()[_fiziksel(st_bas)].sum(dtype=np.int64))
    del stok
    sv = _tablo(kosu, "sevkiyat", ["hedef", "adet"], bas_foto, bit, sutun="varis_tarihi")
    giris = float(sv["adet"].to_numpy()[_fiziksel(sv, "hedef") & (sv["hedef"].astype(str) != "DEPO").to_numpy()]
                  .sum(dtype=np.int64))
    sa = _tablo(kosu, "satis", ["magaza_id", "adet"], bas, bit)
    satis = float(sa["adet"].to_numpy()[_fiziksel(sa) & (sa["adet"].to_numpy() > 0)].sum(dtype=np.int64))
    sonuc["satis_fiziksel_adet"] = satis
    sonuc["str"] = _oran(satis, stok_bas + giris)
    return {a: float(v) for a, v in sonuc.items()}


def line_kirilimi(kosu, w, bas: date = OYUN_BAS, bit: date = OYUN_BIT) -> pd.DataFrame:
    """line başına: `talep_adet, satis_adet, kayip_orani, bulunabilirlik, magaza_stok_son,
    gonderilen_adet` (fiziksel, pencere). Toplam NOS ile Collection'ı karıştırır; aynı
    kuralın ikisine ne yaptığı burada görülür."""
    u_line = pd.Series(w.optionlar["line"].to_numpy().astype(str)[np.asarray(w.sku_option)],
                       index=w.urunler["urun_id"].astype(str).to_numpy())
    gercek = _tablo(kosu, "gercek", ["magaza_id", "urun_id", "talep", "kendi_satis", "karsilanmayan",
                                     "ikameye_giden", "kalici_kayip"], bas, bit)
    gercek = gercek[_fiziksel(gercek)]
    gl = gercek["urun_id"].astype(str).map(u_line).to_numpy()
    stok = _tablo(kosu, "stok", ["magaza_id", "urun_id", "adet"], None, bit)
    son = _son_fotograf(stok, bit)
    st = stok[(pd.to_datetime(stok["tarih"]).dt.normalize() == son).to_numpy() & _fiziksel(stok)]
    sl = st["urun_id"].astype(str).map(u_line).to_numpy()
    sv = _tablo(kosu, "sevkiyat", ["hedef", "urun_id", "adet", "tip"], bas, bit)
    sv = sv[(sv["tip"].astype(str) == REPL).to_numpy() & _fiziksel(sv, "hedef")]
    vl = sv["urun_id"].astype(str).map(u_line).to_numpy()
    satirlar = []
    for line in sorted(set(u_line.unique())):
        m = gl == line
        o = musteri_olcutleri(gercek[m])
        satirlar.append({"line": line, "talep_adet": o["talep_adet"], "satis_adet": o["satis_adet"],
                         "kayip_orani": o["kayip_orani"], "bulunabilirlik": o["bulunabilirlik"],
                         "magaza_stok_son": float(st["adet"].to_numpy()[sl == line].sum(dtype=np.int64)),
                         "gonderilen_adet": float(sv["adet"].to_numpy()[vl == line].sum(dtype=np.int64))})
    return pd.DataFrame(satirlar)


# ---------------------------------------------------------------------------
# Korunum
# ---------------------------------------------------------------------------


def _defter_tutar(kosu) -> bool:
    """Meta'ya göre kol gölge defter tutuyor mu (kısıtsız Lumoda kolu tutmaz)."""
    p = getattr(kosu, "meta", {}).get("politikalar", {}).get("replenishment", {}).get("parametreler", {})
    kol = p.get("kol") if isinstance(p, dict) else None
    if kol is None:
        return False
    return not (kol == "lumoda" and p.get("ayar", {}).get("kisitsiz"))


def denetle(kosu) -> None:
    """Korunum: gizli gerçekte kendi satış ≤ talep, karşılanmayan = talep − kendi satış,
    0 ≤ kalıcı kayıp ≤ karşılanmayan; kol kaydında her pazartesi gölge defter
    (uzlaştırma sonrası kapalı + açık) − gönderilen = gönderim sonrası kapalı + açık.
    (Defterin depoyla değişmezi koşu içinde her uzlaştırmada denetlenir; bozulursa
    koşu `AssertionError` ile durur.) Defter tutan kolun (kaydında `gonderilen_adet` olan, ya
    da meta'sına göre kısıtsız Lumoda dışındaki her kol) kaydında `uzl_*` / `defter_*`
    kalemleri yoksa da `AssertionError`. `sevkiyatla_karsilastir` çağıranın işidir."""
    g = kosu.tablo("gercek", ["talep", "kendi_satis", "karsilanmayan", "kalici_kayip"])
    t, k = g["talep"].to_numpy(np.int64), g["kendi_satis"].to_numpy(np.int64)
    kr, kk = g["karsilanmayan"].to_numpy(np.int64), g["kalici_kayip"].to_numpy(np.int64)
    if (k > t).any() or (k < 0).any():
        raise AssertionError(f"satış talebi aşıyor: {int(((k > t) | (k < 0)).sum())} hücre-gün")
    if (kr != t - k).any():
        raise AssertionError("karşılanmayan ≠ talep − kendi satış")
    if (kk < 0).any() or (kk > kr).any():
        raise AssertionError("kalıcı kayıp karşılanmayanın dışında")
    del g
    if _kol_kaydi_mi(kosu):
        h = hafta_tablosu(kosu)
        gereken = {"uzl_kapali_adet", "uzl_acik_adet", "defter_kapali_adet", "defter_acik_adet", "gonderilen_adet"}
        if "gonderilen_adet" in h.columns or _defter_tutar(kosu):
            eksik = gereken - set(h.columns)
            if eksik:
                raise AssertionError(f"defter tutan kolun kaydında kalem eksik: {sorted(eksik)}")
            once = h["uzl_kapali_adet"] + h["uzl_acik_adet"] - h["gonderilen_adet"]
            sonra = h["defter_kapali_adet"] + h["defter_acik_adet"]
            if not np.allclose(once.to_numpy(float), sonra.to_numpy(float)):
                raise AssertionError("gölge defter kaydı: uzlaştırma − gönderim ≠ gönderim sonrası")
