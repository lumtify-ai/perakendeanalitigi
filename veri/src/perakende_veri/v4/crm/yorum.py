"""Görev 12: yorumların online sipariş satırlarına atanması (spec §6).

**Aday.** Pencere (2023-01-01 – 2025-12-31) içindeki ONL satış fiş
satırları (sonradan iade edilenler dahil). Isınmadaki satırlar yayımlanmaz,
kütüphane kapasitesini tüketmesinler diye aday değildir.

**Hediye alımı yazmaz.** Müşteri cinsiyeti ürün cinsiyetinden farklıysa
(ürün Unisex ya da Aksesuar değilse) satır hediye alımı sayılır (`hediye`
bayrağı; Görev 5b'nin çapraz alımları, ~%8–15) ve yorum yazmaz. Kontrolcü
kararı: kütüphane metinleri ürünü kendi üstünde anlatır ya da cinsiyetli bir
alıcı ağzından yazılmıştır; yalnız cinsiyeti uyan alıcıya bağlanınca hep
tutarlı olur. Hediye satırları adaydır (oranın paydası) ama olasılıkları 0.

**Kim yazar.** Hediye olmayan satır başına olasılık `TEMEL_OLASILIK` ×
etkin nedenlerin çarpanı (`CARPANLAR`). Gizli nedenler (satır bayrakları):

    kalite  tedarikçinin `hatali_orani` tedarikçilerin üst çeyreğinde     ×1,5
            (> `KALITE_ESIK_CEYREK` = 0,75 çeyreği; kontrolcü kararı: medyan
            satırların ~%54'ünü işaretliyor, olumsuz yorum payını şişiriyordu)
    beden   satır beden uyumsuz (`beden_uyumsuz_adet` > 0; Aksesuar yok) ×2
    kargo   teslimat gecikti (Görev 8, `kargo_tablosu` `gecikme`)        ×1,8
    fiyat   satırın indirim oranı ≥ %50                                    ×1,2

Yazan satırda etkin bir neden i, yorumun nedenlerine `(m_i − 1) / m_i`
olasılıkla girer (çarpımsal modelde nedene atfedilebilir pay): tek nedenli
satırda nedensiz yorum olasılığı yine `TEMEL_OLASILIK`, fazlası nedenlidir.
Nedeni olmayan yorum "genel beğeni"dir.

**Puan.** Olumsuz neden (kalite, beden, kargo) → 1–3; iade edilmiş satırda
beden → 1–2; yalnız fiyat → 4–5; nedensiz → 4–5 (ağırlıklı 5). Ağırlıklar
`PUAN_AGIRLIKLARI`.

**Konu.** Neden → konu: kalite → kumas_kalite, beden → beden_kalip (+
iade_sureci, satır iade edildiyse), kargo → kargo_teslimat, fiyat →
fiyat_deger. İzinli küme = neden konuları ∪ {genel_begeni}.

**Metin seçimi.** Kütüphane kaydı yalnız kendi kategori grubunun SKU'suna;
`alt_kategori` doluysa yalnız o alt kategoriye; `{beden}`'li kayıt beden
etiketi olan (STD olmayan) SKU'ya. Çelişki süzgeci (hiç gevşemez): iade_sureci
konulu metin yalnız iade edilmiş satıra, olumsuz/karışık kargo metni yalnız
geciken satıra, olumlu kargo metni ("ertesi gün kapıdaydı") yalnız
gecikmeyen satıra, indirimle aldığını anlatan metin (`INDIRIM_IDDIASI`) yalnız
indirimli satıra. Demografi süzgeci (hiç gevşemez, alt_kategori gibi):
`cinsiyet_ipucu` doluysa müşteri cinsiyetine eşit, `yas_ipucu` doluysa
müşterinin yaş grubu listede. Gevşetme basamakları (`GEVSEME_BASAMAKLARI`,
sırayla ilk boş olmayan):

    konu 0  konular ⊆ izinli ve (nedenliyse) en az bir neden konusu
    konu 1  konular ∩ (neden konuları; nedensizse {genel_begeni}) ≠ ∅
    konu 2  konu kısıtı yok (son çare: nedenin konusu kaybolur)

    sıra: (konu 0, puan), (konu 1, puan), (konu 0, puan ±1), (konu 1,
    puan ±1), (konu 2, puan), (konu 2, puan ±1) — brief'in "önce konu
    kümesini gevşet, sonra puanı ±1" sırası nedenin konusunu koruyan iki
    basamakta uygulanır; konu 2 düşmeden önceki son çaredir (kütüphanenin
    konuları dengeli olduğundan nedensiz yorumların çoğu buraya iner).

Bir metin en fazla `AZAMI_KULLANIM` kez kullanılır (sert); aday kalmazsa
yorum düşer (`dusen_kapasite`). Sıra: önce nedenli yorumlar (gizli sinyal
korunsun), sonra nedensizler; her grup içinde rastgele. Seçilen metnin
puanı ve duygusu kütüphanedendir (gevşetmede puan ±1 kayar).

**Yer tutucu.** `{renk}` → SKU rengi Türkçe küçük harf, `{beden}` → SKU beden
etiketi; metin başında (ya da cümle sonundan sonra) gelen değer büyük harfle
başlar (`yazim_hatali` üslupta değil).

**Tarih.** Fiş günü + teslim günü (Görev 8) + 1–10 gün (uniform); pencere
sonunu aşan yorum düşer (`dusen_tarih`).

**Gizli.** `gizli_df`: gerçek konular (kütüphane etiketi), duygu, nedenler
(virgülle; nedensizde boş), kütüphane kimliği, üslup, gevşeme basamağı.

Rastgelelik: verilen `rng`'nin `ADIMLAR` sırasıyla `spawn` edilmiş alt
akışları (bir adımın çekiliş sayısı değişince diğerleri kaymaz). `spawn`
üst üretecin spawn sayacını ilerletir: aynı `rng` ikinci kez verilirse farklı
alt akışlar çıkar; her çağrıya taze `crm_uretici(D, "yorum")` verilmelidir.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from ..tablolar import _gun_tarihi, pencere
from .kargo import kargo_tablosu
from .kutuphane import KATEGORI_GRUPLARI, KONULAR
from .sabitler import CINSIYETLER, YAS_GRUPLARI
from .tercih import urun_cinsiyet

KUTUPHANE_YOLU = Path(__file__).resolve().parent / "yorum_kutuphanesi.jsonl"

TEMEL_OLASILIK = 0.045
NEDENLER = ("kalite", "beden", "kargo", "fiyat")
CARPANLAR = {"kalite": 1.5, "beden": 2.0, "kargo": 1.8, "fiyat": 1.2}
NEDEN_KONUSU = {"kalite": "kumas_kalite", "beden": "beden_kalip", "kargo": "kargo_teslimat",
                "fiyat": "fiyat_deger"}
OLUMSUZ_NEDENLER = ("kalite", "beden", "kargo")
DERIN_INDIRIM = 0.50
# Satırın indirim oranı (indirim_tutari / (liste × adet)) bu eşiği aşarsa
# "indirimli" (indirim iddiası taşıyan metin alabilir); kuruş yuvarlamasını
# indirim saymamak için > 0 değil.
INDIRIMLI_ESIK = 0.005
ORAN_TOLERANSI = 1e-9      # %50'yi tam veren satır kayan noktada kaçmasın
AZAMI_KULLANIM = 25
# Hatalı tedarikçi eşiği: tedarikçi `hatali_orani` dağılımının bu çeyreği.
KALITE_ESIK_CEYREK = 0.75
# Beklenen yazar sayısının üst sınırı (temel olasılık bunu aşmayacak kadar
# küçülür). Kontrolcü kararı: hacim hedefi 60–80 bin yorum (TAM'da oran
# ~%1–1,3; spec'in %4–8 bandı 6,4 M online satırda kütüphaneyle
# karşılanamaz). 7.000 metinlik kütüphaneyle (Görev 12b, tohum 4242) TAM'da
# ~74,6 bin yorum, oran %1,17, kapasite düşüşü 0.
HEDEF_YORUM_UST = 75_000
TARIH_EK_ALT, TARIH_EK_UST = 1, 10          # teslimattan sonra, ikisi de dahil
BEDENSIZ_ETIKET = "STD"
AKSESUAR_GRUBU = "Aksesuar"
UNISEX_KODU = 2      # `tercih.urun_cinsiyet`: 0 Kadın, 1 Erkek, 2 Unisex

# Puan ağırlıkları (neden aralığı içinde). KALİBRASYON: hedef ortalama
# 4,0–4,4; 7.000 metinle TAM'da 4,11–4,13, KUCUK'ta 4,01–4,04 (Görev 12b,
# 5 tohum). Olumsuzda J biçimi korunur (1 ≥ 2, 3).
PUAN_AGIRLIKLARI = {
    "nedensiz": {4: 0.15, 5: 0.85},
    "fiyat": {4: 0.35, 5: 0.65},
    "olumsuz": {1: 0.30, 2: 0.30, 3: 0.40},
    "iade_beden": {1: 0.50, 2: 0.50},
}

# (konu basamağı, puan farkı) — sırayla denenir.
GEVSEME_BASAMAKLARI = ((0, 0), (1, 0), (0, 1), (1, 1), (2, 0), (2, 1))

INDIRIM_IDDIASI = re.compile(r"indirim|yar[ıi] fiyat|kampanya", re.IGNORECASE)

YORUM_SUTUNLARI = ("yorum_id", "fis_satir_id", "musteri_id", "urun_id", "tarih", "puan", "metin")
GIZLI_SUTUNLARI = ("yorum_id", "kutuphane_id", "konular", "duygu", "nedenler", "uslup", "gevseme")

ADIMLAR = ("yazar", "neden", "puan", "tarih", "sira", "secim")   # yeni adım SONA

_KONU_BIT = {k: 1 << i for i, k in enumerate(KONULAR)}
_GENEL = _KONU_BIT["genel_begeni"]
_IADE_KONU = _KONU_BIT["iade_sureci"]


# ---------------------------------------------------------------------------
# Kütüphane
# ---------------------------------------------------------------------------


def kutuphane_yukle(yol: Path | str = KUTUPHANE_YOLU) -> pd.DataFrame:
    """Kütüphane JSONL'ını DataFrame olarak okur (satır sırası korunur)."""
    with open(yol, encoding="utf-8") as f:
        kayitlar = [json.loads(s) for s in f if s.strip()]
    return pd.DataFrame(kayitlar)


@dataclass(frozen=True)
class _Kut:
    grup: np.ndarray        # KATEGORI_GRUPLARI indisi
    alt: np.ndarray         # alt kategori adı ya da None (object)
    alt_bos: np.ndarray     # alt_kategori null: grubun her SKU'suna
    puan: np.ndarray
    konu: np.ndarray        # bit maskesi
    beden_yt: np.ndarray    # {beden} yer tutucusu var
    olumsuz_kargo: np.ndarray
    olumlu_kargo: np.ndarray
    indirim_iddiasi: np.ndarray
    cins_ip: np.ndarray     # CINSIYETLER indisi, −1 = ipucu yok
    yas_ip: np.ndarray      # YAS_GRUPLARI bit maskesi, 0 = ipucu yok


def _kutuphane_dizileri(kut: pd.DataFrame) -> _Kut:
    konu = np.array([sum(_KONU_BIT[k] for k in ks) for ks in kut["konular"]], dtype=np.int64)
    kargo = (konu & _KONU_BIT["kargo_teslimat"]) != 0
    return _Kut(
        grup=np.array([KATEGORI_GRUPLARI.index(g) for g in kut["kategori_grubu"]], dtype=np.int64),
        alt=kut["alt_kategori"].to_numpy(dtype=object),
        alt_bos=pd.isna(kut["alt_kategori"]).to_numpy(),
        puan=kut["puan"].to_numpy(dtype=np.int64),
        konu=konu,
        beden_yt=np.array(["beden" in y for y in kut["yer_tutucu"]]),
        olumsuz_kargo=kargo & (kut["duygu"].to_numpy() != "olumlu"),
        olumlu_kargo=kargo & (kut["duygu"].to_numpy() == "olumlu"),
        indirim_iddiasi=kut["metin"].map(lambda m: bool(INDIRIM_IDDIASI.search(m))).to_numpy(),
        cins_ip=np.array([CINSIYETLER.index(c) if isinstance(c, str) else -1
                          for c in _sutun(kut, "cinsiyet_ipucu")], dtype=np.int64),
        yas_ip=np.array([sum(1 << YAS_GRUPLARI.index(g) for g in y) if isinstance(y, list) else 0
                         for y in _sutun(kut, "yas_ipucu")], dtype=np.int64),
    )


def _sutun(kut: pd.DataFrame, ad: str) -> np.ndarray:
    """Kütüphane sütunu; sütun yoksa (ipucusuz kütüphane) hep None."""
    if ad in kut.columns:
        return kut[ad].to_numpy(dtype=object)
    return np.full(len(kut), None, dtype=object)


# ---------------------------------------------------------------------------
# Adaylar
# ---------------------------------------------------------------------------


def _birlestir(parcalar, sutunlar):
    return {k: np.concatenate([p[k] for p in parcalar]) if parcalar else np.zeros(0, dtype=np.int64)
            for k in sutunlar}


def aday_satirlari(crm_ham, girdi, kargo: pd.DataFrame | None = None) -> pd.DataFrame:
    """Pencere içi ONL satış satırları ve gizli neden bayrakları:
    satir_id, fis_id, gun, musteri, sku, teslim_gun, iade, beden_uyumsuz,
    gecikme, hatali_tedarikci, derin_indirim, indirimli; müşteri demografisi
    musteri_cins (`CINSIYETLER`), musteri_yas (`YAS_GRUPLARI`) ve `hediye`
    (`hediye_bayragi`). `kargo` verilirse
    (`kargo_tablosu(crm_ham, girdi)`, en az ONL satış fişleri) yeniden
    hesaplanmaz."""
    kayit = crm_ham.kayit
    onl = crm_ham.nufus.magaza.onl
    bas, son = pencere()
    son = min(son, crm_ham.D - 1)
    parca, iade_orj = [], []
    for d in range(max(bas, 0), crm_ham.D):
        sat = _birlestir(kayit.gun_parcalari("fis_satir", d),
                         ("satir_id", "fis_id", "sku", "adet", "tutar", "indirim_tutari",
                          "beden_uyumsuz_adet", "orijinal_satir"))
        if not len(sat["satir_id"]):
            continue
        negatif = sat["adet"] < 0
        iade_orj.append(sat["orijinal_satir"][negatif])
        if d > son:
            continue
        fis = _birlestir(kayit.gun_parcalari("fis", d), ("fis_id", "magaza", "musteri", "tip"))
        o = np.argsort(fis["fis_id"])
        fid = fis["fis_id"][o]
        i = o[np.searchsorted(fid, sat["fis_id"])]
        sec = (fis["magaza"][i] == onl) & (fis["tip"][i] == 0) & ~negatif
        if not sec.any():
            continue
        parca.append({
            "satir_id": sat["satir_id"][sec], "fis_id": sat["fis_id"][sec],
            "gun": np.full(int(sec.sum()), d, dtype=np.int64), "musteri": fis["musteri"][i][sec],
            "sku": sat["sku"][sec], "adet": sat["adet"][sec], "indirim_tutari": sat["indirim_tutari"][sec],
            "beden_uyumsuz": sat["beden_uyumsuz_adet"][sec] > 0,
        })
    a = pd.DataFrame({k: np.concatenate([p[k] for p in parca]) for k in parca[0]}) if parca else None
    if a is None:
        raise ValueError("pencerede ONL satış satırı yok")
    iade_orj = np.unique(np.concatenate(iade_orj)) if iade_orj else np.zeros(0, dtype=np.int64)
    a["iade"] = np.isin(a["satir_id"].to_numpy(), iade_orj)

    if kargo is None:
        kargo = kargo_tablosu(crm_ham, girdi)
    k_o = np.argsort(kargo["fis_id"].to_numpy())
    k_fid = kargo["fis_id"].to_numpy()[k_o]
    j = k_o[np.searchsorted(k_fid, a["fis_id"].to_numpy())]
    assert (kargo["fis_id"].to_numpy()[j] == a["fis_id"].to_numpy()).all()
    a["teslim_gun"] = kargo["teslim_gun"].to_numpy()[j]
    a["gecikme"] = kargo["gecikme"].to_numpy()[j]
    mus = a["musteri"].to_numpy(dtype=np.int64)
    a["musteri_cins"] = crm_ham.nufus.cinsiyet[mus].astype(np.int8)
    a["musteri_yas"] = crm_ham.nufus.yas_grubu[mus].astype(np.int8)
    a = bayraklari_ekle(a, girdi.dunya.urunler, girdi.dunya.gizli_tedarikci)
    a["hediye"] = hediye_bayragi(a, girdi.dunya.urunler)
    return a


def hediye_bayragi(a: pd.DataFrame, u: pd.DataFrame) -> np.ndarray:
    """Müşteri cinsiyeti (`musteri_cins`) ≠ ürün cinsiyeti, ürün Unisex ya da
    Aksesuar değilse: hediye alımı, yorum yazmaz (modül docstring'i)."""
    sku = a["sku"].to_numpy(dtype=np.int64)
    uc = urun_cinsiyet(u)[sku]
    aksesuar = u["ust_kategori"].to_numpy()[sku] == AKSESUAR_GRUBU
    return (uc != UNISEX_KODU) & ~aksesuar & (a["musteri_cins"].to_numpy() != uc)


def bayraklari_ekle(a: pd.DataFrame, u: pd.DataFrame, gted: pd.DataFrame) -> pd.DataFrame:
    """Ham aday satırlarına (sku, adet, indirim_tutari, beden_uyumsuz)
    SKU'dan gelen neden bayrakları: hatali_tedarikci, indirimli,
    derin_indirim; Aksesuar'da beden_uyumsuz yok."""
    a = a.copy()
    sku = a["sku"].to_numpy(dtype=np.int64)
    hatali = gted.set_index("tedarikci_id")["hatali_orani"]
    esik = float(gted["hatali_orani"].quantile(KALITE_ESIK_CEYREK))
    sku_oran = hatali.reindex(u["tedarikci_id"]).to_numpy(dtype=float)
    assert not np.isnan(sku_oran).any(), "SKU'nun tedarikçisi gizli profilde yok"
    sku_hatali = sku_oran > esik
    a["hatali_tedarikci"] = sku_hatali[sku]
    liste = u["liste_fiyati"].to_numpy(dtype=float)[sku] * a["adet"].to_numpy()
    oran = a["indirim_tutari"].to_numpy(dtype=float) / liste
    a["indirimli"] = oran > INDIRIMLI_ESIK
    a["derin_indirim"] = oran >= DERIN_INDIRIM - ORAN_TOLERANSI
    aksesuar = u["ust_kategori"].to_numpy()[sku] == AKSESUAR_GRUBU
    a["beden_uyumsuz"] = a["beden_uyumsuz"].to_numpy() & ~aksesuar
    return a.drop(columns=["adet", "indirim_tutari"])


# ---------------------------------------------------------------------------
# Seçim
# ---------------------------------------------------------------------------


def metin_sec(adaylar, anahtar: np.ndarray, sira: np.ndarray, u: np.ndarray,
              n_metin: int, azami: int = AZAMI_KULLANIM) -> tuple[np.ndarray, np.ndarray]:
    """Yorum başına kütüphane indisi ve gevşeme basamağı (−1: düştü).

    `adaylar(k, b)` anahtar k'nin b. basamağındaki aday metin indisleri
    (sabit dizi; burada önbelleğe alınır ve tükenenler ayıklanır).
    `sira` işlem sırası; `u` [n] yorum başına uniform (aday içinden seçim).
    """
    n = len(anahtar)
    kalan = np.full(n_metin, azami, dtype=np.int64)
    secim = np.full(n, -1, dtype=np.int64)
    basamak = np.full(n, -1, dtype=np.int64)
    onbellek: dict = {}
    B = len(GEVSEME_BASAMAKLARI)
    for i in sira:
        k = int(anahtar[i])
        for b in range(B):
            c = onbellek.get((k, b))
            if c is None:
                c = np.asarray(adaylar(k, b), dtype=np.int64)
            if len(c):
                c = c[kalan[c] > 0]
            onbellek[(k, b)] = c
            if len(c):
                t = int(c[min(int(u[i] * len(c)), len(c) - 1)])
                kalan[t] -= 1
                secim[i] = t
                basamak[i] = b
                break
    return secim, basamak


def _turkce_kucuk(s: str) -> str:
    return s.replace("İ", "i").replace("I", "ı").lower()


def _turkce_bas_buyuk(s: str) -> str:
    if not s:
        return s
    ilk = {"i": "İ", "ı": "I"}.get(s[0], s[0].upper())
    return ilk + s[1:]


_YT = re.compile(r"\{(renk|beden)\}")


def yer_tutucu_doldur(metin: str, renk: str, beden: str | None, buyut: bool = True) -> str:
    """`{renk}` → renk (Türkçe küçük harf), `{beden}` → beden etiketi; metin
    ya da cümle başındaki değer (buyut ise) büyük harfle başlar."""
    def degis(m):
        deger = _turkce_kucuk(renk) if m.group(1) == "renk" else beden
        assert deger is not None, "beden etiketi olmayan SKU'ya {beden}"
        onu = metin[:m.start()].rstrip()
        if buyut and (not onu or onu[-1] in ".!?"):
            deger = _turkce_bas_buyuk(deger)
        return deger

    return _YT.sub(degis, metin)


# ---------------------------------------------------------------------------
# Ana akış
# ---------------------------------------------------------------------------


@dataclass
class YorumSonucu:
    """`yorum`, `gizli` (yayımlanan / gizli); `aday` pencere içi ONL satış
    satırları ve bayrakları; sayaçlar (ölçüm ve test için)."""

    yorum: pd.DataFrame
    gizli: pd.DataFrame
    aday: pd.DataFrame
    aday_sayisi: int
    yazar_sayisi: int
    temel: float
    yazarlar: pd.DataFrame      # yazar başına: satir_id, nedenler, hedef_puan, tarihte, gevseme (−1 düştü)
    dusen_tarih: int
    dusen_kapasite: int
    gevseme_sayilari: list[int]
    # Tarihteki yazarların basamak-0 havuzundan (kapasite öncesi) demografi
    # süzgecinin elediği metin payı (yazar ağırlıklı; ölçüm için).
    demografi_elenen: float = 0.0


def temel_olasilik(carpim: np.ndarray) -> float:
    """`TEMEL_OLASILIK`; beklenen yazar sayısı (Σ temel × çarpım)
    `HEDEF_YORUM_UST`'ü aşarsa temel orantılı küçülür (kütüphane kapasitesi,
    modül docstring'i)."""
    beklenen = TEMEL_OLASILIK * float(carpim.sum())
    return TEMEL_OLASILIK * min(1.0, HEDEF_YORUM_UST / beklenen) if beklenen > 0 else TEMEL_OLASILIK


def _agirlikli_puan(rng, agirlik: dict, n: int) -> np.ndarray:
    degerler = np.array(list(agirlik), dtype=np.int64)
    p = np.array(list(agirlik.values()), dtype=float)
    return degerler[rng.choice(len(degerler), size=n, p=p / p.sum())]


def yorum_uret_ayrintili(rng, crm_ham, girdi, kutuphane: pd.DataFrame) -> YorumSonucu:
    """`yorumlari_uret`'in ayrıntılı biçimi (modül docstring'i)."""
    a = aday_satirlari(crm_ham, girdi)
    son_gun = min(pencere()[1], crm_ham.D - 1)
    return yorumlari_ata(rng, a, girdi.dunya.urunler, kutuphane, son_gun)


def yorumlari_ata(rng, a: pd.DataFrame, u_df: pd.DataFrame, kutuphane: pd.DataFrame,
                  son_gun: int) -> YorumSonucu:
    """Aday satırlarından (`aday_satirlari`) yorumlar; `u_df` A'nın
    `urunler`'i, `son_gun` yorum tarihinin üst sınırı (dahil)."""
    akis = dict(zip(ADIMLAR, rng.spawn(len(ADIMLAR))))
    kut = kutuphane.reset_index(drop=True)
    K = _kutuphane_dizileri(kut)
    N = len(a)

    # 1. kim yazar (hediye satırı yazmaz), nedenler
    bayrak = np.column_stack([a["hatali_tedarikci"], a["beden_uyumsuz"], a["gecikme"], a["derin_indirim"]])
    carpan = np.array([CARPANLAR[n] for n in NEDENLER])
    carpim = np.prod(np.where(bayrak, carpan, 1.0), axis=1) * ~a["hediye"].to_numpy()
    temel = temel_olasilik(carpim)
    p = temel * carpim
    yazar = np.flatnonzero(akis["yazar"].random(N) < p)
    Y = len(yazar)
    atf = (carpan - 1.0) / carpan
    neden = bayrak[yazar] & (akis["neden"].random((Y, len(NEDENLER))) < atf)
    iade = a["iade"].to_numpy()[yazar]

    # 2. puan
    olumsuz = neden[:, :3].any(axis=1)
    iade_beden = neden[:, 1] & iade
    sadece_fiyat = neden[:, 3] & ~olumsuz
    r_p = akis["puan"]
    puan = _agirlikli_puan(r_p, PUAN_AGIRLIKLARI["nedensiz"], Y)
    for maske, ad in ((sadece_fiyat, "fiyat"), (olumsuz, "olumsuz"), (iade_beden, "iade_beden")):
        puan = np.where(maske, _agirlikli_puan(r_p, PUAN_AGIRLIKLARI[ad], Y), puan)

    # 3. tarih (pencere dışı düşer)
    gun_y = a["gun"].to_numpy()[yazar] + a["teslim_gun"].to_numpy()[yazar] \
        + akis["tarih"].integers(TARIH_EK_ALT, TARIH_EK_UST + 1, size=Y)
    tarihte = gun_y <= son_gun
    dusen_tarih = int((~tarihte).sum())

    # 4. anahtar: (sku öznitelikleri, neden maskesi, bayraklar, puan)
    sku = a["sku"].to_numpy(dtype=np.int64)[yazar]
    sku_grup = np.array([KATEGORI_GRUPLARI.index(g) for g in u_df["ust_kategori"]], dtype=np.int64)
    alt_adlar = sorted(u_df["alt_kategori"].unique())
    sku_alt = np.searchsorted(alt_adlar, u_df["alt_kategori"].to_numpy())
    sku_bedenli = u_df["beden"].to_numpy() != BEDENSIZ_ETIKET
    neden_kod = (neden * (1 << np.arange(len(NEDENLER)))).sum(axis=1)
    gec = a["gecikme"].to_numpy()[yazar]
    ind = a["indirimli"].to_numpy()[yazar]
    mc = a["musteri_cins"].to_numpy()[yazar]
    my = a["musteri_yas"].to_numpy()[yazar]
    alanlar = np.column_stack([sku_grup[sku], sku_alt[sku], sku_bedenli[sku], neden_kod,
                               iade, gec, ind, puan, mc, my])
    tekil, anahtar = np.unique(alanlar, axis=0, return_inverse=True)
    anahtar = anahtar.ravel()

    def adaylar(k: int, b: int, demografi: bool = True) -> np.ndarray:
        g, al, bedenli, nk, iad, gc, idl, pu, cins, yas = (int(x) for x in tekil[k])
        konu_b, puan_f = GEVSEME_BASAMAKLARI[b]
        m = (K.grup == g) & (K.alt_bos | (K.alt == alt_adlar[al]))
        if demografi:
            m &= (K.cins_ip < 0) | (K.cins_ip == cins)
            m &= (K.yas_ip == 0) | (((K.yas_ip >> yas) & 1) == 1)
        if not bedenli:
            m &= ~K.beden_yt
        if not iad:
            m &= (K.konu & _IADE_KONU) == 0
        m &= ~(K.olumlu_kargo if gc else K.olumsuz_kargo)
        if not idl:
            m &= ~K.indirim_iddiasi
        m &= (K.puan == pu) if puan_f == 0 else (np.abs(K.puan - pu) == 1)
        neden_konu = 0
        for j, n in enumerate(NEDENLER):
            if nk >> j & 1:
                neden_konu |= _KONU_BIT[NEDEN_KONUSU[n]]
                if n == "beden" and iad:
                    neden_konu |= _IADE_KONU
        izin = neden_konu | _GENEL
        if konu_b == 0:
            m &= (K.konu & ~izin) == 0
            if neden_konu:
                m &= (K.konu & neden_konu) != 0
        elif konu_b == 1:
            m &= (K.konu & (neden_konu or _GENEL)) != 0
        return np.flatnonzero(m)

    # 5. sıra: önce nedenliler, her grup içinde rastgele
    r_s = akis["sira"]
    aday_y = np.flatnonzero(tarihte)
    nedenli = neden_kod[aday_y] != 0
    sira = np.concatenate([r_s.permutation(aday_y[nedenli]), r_s.permutation(aday_y[~nedenli])])
    u_sec = akis["secim"].random(Y)
    secim, basamak = metin_sec(adaylar, anahtar, sira, u_sec, n_metin=len(kut))
    dusen_kapasite = int(((secim < 0) & tarihte).sum())

    # demografi süzgecinin payı (ölçüm): basamak-0 havuzu, kapasite öncesi
    k_say = np.bincount(anahtar[aday_y], minlength=len(tekil))
    tum = elenen = 0
    for k in np.flatnonzero(k_say):
        n0 = len(adaylar(int(k), 0, demografi=False))
        tum += int(k_say[k]) * n0
        elenen += int(k_say[k]) * (n0 - len(adaylar(int(k), 0)))
    demografi_elenen = elenen / tum if tum else 0.0

    # 6. tablolar
    v = np.flatnonzero(secim >= 0)
    s_v = secim[v]
    sku_v = sku[v]
    renk = u_df["renk"].to_numpy()
    beden = u_df["beden"].to_numpy()
    metin = kut["metin"].to_numpy()
    uslup = kut["uslup"].to_numpy()
    metinler = [
        yer_tutucu_doldur(metin[t], renk[s], beden[s] if beden[s] != BEDENSIZ_ETIKET else None,
                          buyut=uslup[t] != "yazim_hatali") if "{" in metin[t] else metin[t]
        for t, s in zip(s_v, sku_v)
    ]
    satir = yazar[v]
    tarih = _gun_tarihi(gun_y[v])
    yorum = pd.DataFrame({
        "fis_satir_id": a["satir_id"].to_numpy()[satir].astype(np.int64),
        "musteri_id": a["musteri"].to_numpy()[satir].astype(np.int64),
        "urun_id": u_df["urun_id"].to_numpy()[sku_v],
        "tarih": tarih,
        "puan": K.puan[s_v].astype(np.int8),
        "metin": metinler,
    })
    neden_adi = np.array([",".join(n for j, n in enumerate(NEDENLER) if kod >> j & 1)
                          for kod in range(1 << len(NEDENLER))], dtype=object)
    gizli = pd.DataFrame({
        "kutuphane_id": kut["id"].to_numpy()[s_v],
        "konular": [",".join(ks) for ks in kut["konular"].to_numpy()[s_v]],
        "duygu": kut["duygu"].to_numpy()[s_v],
        "nedenler": neden_adi[neden_kod[v]],
        "uslup": uslup[s_v],
        "gevseme": basamak[v].astype(np.int8),
    })
    o = np.lexsort((yorum["fis_satir_id"].to_numpy(), yorum["tarih"].to_numpy()))
    yorum = yorum.iloc[o].reset_index(drop=True)
    gizli = gizli.iloc[o].reset_index(drop=True)
    yorum.insert(0, "yorum_id", np.arange(len(yorum), dtype=np.int64))
    gizli.insert(0, "yorum_id", yorum["yorum_id"].to_numpy())

    sayilar = np.bincount(basamak[v], minlength=len(GEVSEME_BASAMAKLARI)).tolist()
    yazarlar = pd.DataFrame({
        "satir_id": a["satir_id"].to_numpy()[yazar], "nedenler": neden_adi[neden_kod],
        "hedef_puan": puan.astype(np.int8), "tarihte": tarihte, "gevseme": basamak.astype(np.int8),
    })
    return YorumSonucu(yorum=yorum, gizli=gizli, aday=a, aday_sayisi=N, yazar_sayisi=Y, temel=temel,
                       yazarlar=yazarlar,
                       dusen_tarih=dusen_tarih, dusen_kapasite=dusen_kapasite, gevseme_sayilari=sayilar,
                       demografi_elenen=demografi_elenen)


def yorumlari_uret(rng, crm_ham, girdi, kutuphane: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(yorum_df, gizli_df): modül docstring'i. `rng` çağıranın akışı
    (`crm_uretici(D, "yorum")`); A değişmez."""
    s = yorum_uret_ayrintili(rng, crm_ham, girdi, kutuphane)
    return s.yorum, s.gizli
