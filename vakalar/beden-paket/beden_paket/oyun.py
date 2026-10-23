"""Oyun: paket kollarını yollarda kurar, koşar ve ölçer (spec §4.2, Ruling R10–R14).

    .venv/Scripts/python -m beden_paket.oyun izgara                   # bütün bloklar: ana, ablasyon, yol
    .venv/Scripts/python -m beden_paket.oyun izgara --blok ana        # tek blok
    .venv/Scripts/python -m beden_paket.oyun izgara --blok yol --olcek KUCUK   # cikti/kucuk/oyun.json

Bu modül ölçüm tarafındadır (`tests/test_sizinti.py` izinli listesi; `simulasyon.SIMULASYON_DISI`):
simülasyonu `simulasyon.kos`'la yapar, ölçer, gizli gerçeği yalnız kahin denetiminde okur
(`kahin_ayni_mi`; kollar ve tasarımlar hakemi görmez, `test_kahin_yalniz_olcumde`).

**Kollar** (Ruling R10; `KOLLAR`, adlar tekil). Yol 0 (yayımlanan dünya) yedi kol, yollar 1–4 dört:

    dogrulama  L0 Lumoda: standart 1-2-2-1-1, Lumoda'nın kendi ilk dağıtımı (`kosucu dogrulama`'nın
               koşusu; İlk Sevkiyat'ın `lumoda`'sını birebir üretir)
    p1         en iyi tek 7'li desen (K = 1; tasarım 1-1-2-2-1 bekler)
    p2         iki 7'li desen (K = 2)
    p1_12      tek 12'li desen (K = 1)
    p3_12      üç 12'li desen (K = 3)
    pm_12      mağazaya özel 12'li desen
    p2_12      iki 12'li desen (K = 2; Ruling R21: demo'nun 2 | 12 bileşimi ölçülsün)
    p1_14      ayrıştırma kontrolü (Ruling R22; R20'nin l0_12'sinin yerine): P1'in 1-1-2-2-1'inin tam iki
               katı 2-2-4-4-2, her mağazaya, tasarım aranmaz; aynı beden payları, büyük paket. ns 14'lü
               dönüşüm, aşağı yuvarlamayla (`NS_YUVARLAMA`): p1_14 − p1 = aynı içerikte paket büyüklüğünün
               (yuvarlama, kabalık) etkisi
    p2_ham     ablasyon: P2, sansür düzeltmesiz (ham) eğriyle tasarlanmış

Bloklar: `ana` yol 0'ın dogrulama, p1, p2, p1_12, p3_12, pm_12, p2_12, p1_14'ü; `ablasyon` yol 0'ın
p2_ham'ı; `yol` yollar 1–4'ün dogrulama, p1, p2, p3_12'si (yol p'de koşu adı `y<p>_<kol>`). 25 kayıt; tasarımı
aynı yolda daha önceki bir kolunkiyle aynı olan kol (`ayni_kol`) ayrıca koşulmaz, kaydı `ayni` ile ona
bağlanır (`kos_hepsi`). **Koşulmayanlar** (`KOSULMAYAN`, Ruling R10): 7'li P3, P4, PM P2 ile aynı deseni
ve atamayı verir (`k_egrisi` her yolda hesaplar, `ayni` alanı); 7'li kahin (P2'nin desenleri gerçek
paya göre atanmış): `kahin_ayni_mi` profilin kaymaya ARI'sini ve kahin atamasının P2'ninkinden ayrıldığı
mağazaları hesaplar (eğrisi okunabilen mağazalarda ARI 1; ayrılık ancak yedek eğri alan mağazada).

**Yolun girdileri** (`YolGirdisi`, yol başına, tembel). Yolun Lumoda koşusu vakanın o yoldaki
doğrulama koludur (`simulasyon.kos_dogrulama(p)`). Bütün kararlar yalnız yolun yayımlanan
tablolarından ve karar gününe (`KARAR_GUNU`) kadarki veriyle kurulur (İlk Sevkiyat `oyun.Girdi`
kalıbı): yol 0 TAM'da yayımlanan DuckDB, başka her yolda (ve KÜÇÜK dünyada) doğrulama koşusunun
yayımlanan biçimi (`motor.yayimlanan_bicim`: satış, stok, sevkiyat kirletilir; öteki tablolar
olduğu gibi) bellek içi bir DuckDB'de. Eğri `egri.magaza_egrisi` (κ seçimi dahil, `egri.kappa_sec`
o yolun tablolarıyla; ayrı bir kalibrasyon komutu yoktur), kapsam `kaynak.kapsam`.

    ns(7)      Lumoda'nın giden paketi (`kosucu.lumoda_giden`, doğrulama koşusu), bütün oyun option'ları
    ns(12)     beş bedenli oyun option'larında giden adedin 12'liye dönüşümü (`kosucu.ns_donustur`:
               option toplamı ⌊Σ adet ÷ 12 + ½⌋, mağazalara en büyük kalanla); aksesuar ns(7)
    ns(14)     aynısı 14'lüye, option toplamı ⌊Σ adet ÷ 14⌋ (aşağı; `NS_YUVARLAMA`, R22): Σ adet = 7 ×
               Lumoda paketi olduğundan yakın yuvarlama tek paket sayılı option'da (TAM yol 0'da 193'ün
               103'ü) yarım paket fazla ister ve 1. bedende depoyu bir paket aşar; aşağı yuvarlamada aşım 0
    agirlik(a) tasarımın ağırlığı: mağazanın beş bedenli oyun option'larındaki ns(a) toplamı
               (kapsamın paket almayan mağazası 0)
    siparis_deposu  beş bedenli oyun option'ı × beden: ilk siparişin adedi (yayımlanan `siparis` tip
               `ilk`; bütün siparişler karar gününden önce verilmiştir). Tasarımın beklediği depo
               budur, karar anında bilinen (spec §0/11, Ruling R16)
    depo       aynı tablo, kalite kontrolde hatalı çıkanlar düşülmüş (`kalite_kontrol`; hatalı adet
               motorun kuralıyla SKU'lara en büyük kalanla, beden sırasıyla): ilk dağıtım anında
               motorun deposunun kendisi (yeni Collection option'ının depoda başka malı yoktur;
               Lumoda'nın giden paketini birebir üretir, `test_depo_lumodayi_uretir`). Hatalar
               teslimde, çoğu karar gününden sonra ortaya çıkar: yalnız ön denetimde ve korunumda
    depo_payi(a)  Σ_option siparis_deposu_b ÷ (a × Σ agirlik(a)), yani beklenen depo / kolun giden
               adedi (7'lide Lumoda'nın giden adedi). `paket_tasarim.tasarla`'nın kısıtı Σ_m w_m p_b ≤
               depo_payi_b × a × Σw böylece tam Σ_option siparis_deposu_b olur (toplamda; Ruling R11).
               `depo_payi(a, "depo")` hata düşülmüş depoyla; iki tanımla tasarımlar ve bağlar aynıdır
               (`depo_tanimlari_ayni`; TAM yol 0'da ve KÜÇÜK'te test)

**Tasarım** (`tasarim(kol)`): `paket_tasarim.tasarla(eğri, agirlik(a), K, depo_payi(a), adet=a)`;
p2_ham'da eğri `ham_egri` (okunabilen mağazada ham satış payı, okunamayanda ana eğrinin yedeği;
daraltma yok: bu veride w ≈ 1, Ruling R6). Tasarım koşmadan **option başına** sınanır
(`on_denetim`): beş bedenli her oyun option'ında Σ_m ns × desen_b ≤ depo_b mi; aşan option kolun
motorda kırpılacağı yerdir (R11: toplam kısıt option başına kırpmayı garanti etmez). Koşudan sonra
kırpma ölçülür (`kirpilan_adet`, `kirpilan_option`) ve kayıtta `ayni_mal`: kırpma 0 ve 7'lide
(option, mağaza) başına giden adet Lumoda'nınkine eşit (`kosucu.korunum`); 12'li ve 14'lüde
`ayni_mal` yalnız kırpma 0'dır, adet farkı `donusum`'da (aynı mal yaklaşık, R10): rapor bu kolları
"yaklaşık (±N adet)" basar ve giden adet farkını dönüşüm farkıyla denetler.

**Koşu ve ölçüm** (`kos_bir`; Ruling R14). Simülasyon önbelleği `cikti/kosular/`
(`simulasyon.kos`, anahtar yalnız simülasyonu değiştirenler). Ölçütler `cikti/oyun.json`'da kayıt
başına `anahtar` ve `olcum_kodu` (ölçüm kodunun özeti `OLCUM_OZETI`: `kosucu.py`, İlk Sevkiyat
`olcutler.py`, bu modülün ölçüm tarafı işlevleri `OLCUM_FONKSIYONLARI`, `OLCUM_SURUMU`; içe aktarma
anında bir kez kurulur, süreç sürerken dosya değişse de kayıt o sürecin koduyla adlanır) ile:
anahtar ve ölçüm kodu aynıysa yeniden ölçülmez; ölçüm kodu değiştiyse koşu önbellekten okunur,
yalnız ölçüm yeniden yapılır. Ölçümü değiştiren ama `OLCUM_FONKSIYONLARI` ve `kosucu.py` dışında
kalan bir düzeltmede `OLCUM_SURUMU` bir artırılır. Biten her
koşu `cikti/ilerleme.jsonl`'a bir JSON satırı (İlk Sevkiyat `oyun._ilerleme`). `oyun.json`:
`kosular` (ad → yol, kol, paket adedi, K, desenler, atama, eğri ve ns kaynağı, tasarım, ön
denetim, anahtar, ölçüm kodu, ölçütler, korunum), `yollar` (yol → girdilerin özeti).

**K eğrisi** (`k_egrisi`; koşusuz, Task 6'nın raporu için): K = 1..4 ve "magaza" için 7 ve 12'li
tasarımın uyumsuzluğu (gerçek ağırlık, karar öncesi depo), Lumoda paketinin uyumsuzluğu ve her satırda aynı
desen ve atamayı veren daha küçük K (`ayni`). **Kahin** (`kahin_ayni_mi`): tasarımın desenleri
gerçek beden payına göre atanırsa atama değişir mi; profilin etkin kaymaya ARI'si.
"""

import argparse
import functools
import hashlib
import inspect
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from allocation import motor
from allocation import olcutler as al_olcutler
from allocation import oyun as al_oyun
from perakende_veri.v4.plan import en_buyuk_kalan

from beden_paket import egri as egri_modulu
from beden_paket import hakem, kaynak, kosucu, olcutler_egri, paket_tasarim, politika, sabitler, simulasyon

ILERLEME = sabitler.CIKTI / "ilerleme.jsonl"
OYUN_JSON = sabitler.CIKTI / "oyun.json"
# Ölçüm sabitleri burada, `sabitler`'de değil (Ruling R18: `sabitler` simülasyon anahtarındadır).
# OLCUM_SURUMU: ölçümü değiştiren ama OLCUM_FONKSIYONLARI ve kosucu.py dışında kalan her düzeltmede
# bir artırılır (2: R16 düzeltme turu; özet içe aktarma anında, kapsamı genişledi; 3: R19 ilk 4 hafta
# beden ölçütleri; 4: R22 p1_14, 14'lü dönüşüm).
OLCUM_SURUMU = 4
OLCUM_FONKSIYONLARI = ("olcum_kaydi", "YolGirdisi._giden", "YolGirdisi.giden_adet", "YolGirdisi.bes_optionlar",
                       "YolGirdisi.oyun_ids")
OLCUM_ALANLARI = ("olcutler", "korunum", "donusum", "ayni_mal", "ilk_sevkiyat", "olcum_sn")
SUTUNLAR = list(paket_tasarim.SUTUNLAR)
DOGRULAMA = "dogrulama"
YOLLAR = tuple(range(1, sabitler.YOL_SAYISI))


@dataclass(frozen=True)
class Kol:
    ad: str
    K: int | str | None                 # None: doğrulama (Lumoda'nın standart paketi); "sabit": `desen`
    adet: int = sabitler.PAKET_ADET
    egri: str = "duzeltilmis"           # "duzeltilmis" | "ham"
    aciklama: str = ""
    desen: tuple | None = None          # sabit desen (tasarım aranmaz; her mağazaya)
    notu: str = ""                      # kayıtta kolun rolü


P1_14_DESEN = (2, 2, 4, 4, 2)           # Ruling R22: P1'in 1-1-2-2-1'inin tam iki katı
# ns dönüşümünün yuvarlaması paket adedine göre (verilmeyen "yakin"); 14'lü aşağı (modül notu, R22)
NS_YUVARLAMA = {14: "asagi"}


KOLLAR = {k.ad: k for k in (
    Kol(DOGRULAMA, None, aciklama="L0 Lumoda 1-2-2-1-1, Lumoda'nın ilk dağıtımı (doğrulama kolu)"),
    Kol("p1", 1, aciklama="en iyi tek 7'li desen"),
    Kol("p2", 2, aciklama="iki 7'li desen"),
    Kol("p1_12", 1, 12, aciklama="tek 12'li desen"),
    Kol("p3_12", 3, 12, aciklama="üç 12'li desen"),
    Kol("pm_12", "magaza", 12, aciklama="mağazaya özel 12'li desen"),
    Kol("p2_12", 2, 12, aciklama="iki 12'li desen (Ruling R21)"),
    Kol("p1_14", "sabit", 14, aciklama="P1'in iki katı 2-2-4-4-2, her mağazaya", desen=P1_14_DESEN,
        notu="ayrıştırma kontrolü (Ruling R22): p1_14 − p1 = aynı beden içeriğinde paket büyüklüğünün "
             "(yuvarlama, kabalık) etkisi; tasarım aranmaz; ns 14'lü dönüşüm aşağı yuvarlanır"),
    Kol("p2_ham", 2, egri="ham", aciklama="ablasyon: iki 7'li desen, sansür düzeltmesiz eğri"),
)}
YOL0_KOLLARI = (DOGRULAMA, "p1", "p2", "p1_12", "p3_12", "pm_12", "p2_12", "p1_14", "p2_ham")
YOL_KOLLARI = (DOGRULAMA, "p1", "p2", "p3_12")
BLOKLAR = {
    "ana": tuple((0, k) for k in YOL0_KOLLARI if k != "p2_ham"),
    "ablasyon": ((0, "p2_ham"),),
    "yol": tuple((p, k) for p in YOLLAR for k in YOL_KOLLARI),
}
BLOK_SIRASI = ("ana", "ablasyon", "yol")
KOSULMAYAN = {
    "p3": "7'li K = 3: P2 ile aynı desen ve atama (k_egrisi `ayni`; Ruling R10)",
    "p4": "7'li K = 4: P2 ile aynı desen ve atama (k_egrisi `ayni`; Ruling R10)",
    "pm": "7'li mağazaya özel: P2 ile aynı desen ve atama (k_egrisi `ayni`; Ruling R10)",
    "pk": "7'li kahin: profil kaymayla ARI 1 (okunabilen 68 mağaza); atama P2'den yalnız eğrisi okunamayan "
          "M027'de ayrılır (ağırlığın %2,1'i), fark koşusuz basılır (kahin_ayni_mi; Ruling R15)",
}


def kosu_adi(yol: int, kol: str) -> str:
    if kol not in KOLLAR:
        raise KeyError(f"bilinmeyen kol: {kol!r}")
    if kol == DOGRULAMA:
        return simulasyon.dogrulama_adi(yol)
    return kol if int(yol) == 0 else f"y{int(yol)}_{kol}"


def izgara_listesi(blok: str = "hepsi") -> list[tuple[int, str]]:
    """(yol, kol) sırası: bir blok ya da bütün bloklar `BLOK_SIRASI`'yla."""
    bloklar = BLOK_SIRASI if blok == "hepsi" else (blok,)
    return [s for b in bloklar for s in BLOKLAR[b]]


# ---------------------------------------------------------------------------
# Yolun girdileri
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Ortam:
    """Koşuların nerede ve nasıl yapıldığı (TAM varsayılan; testler KÜÇÜK dünyada, geçici dizinde)."""

    olcek: str = "tam"
    onbellek: Path = simulasyon.KOSU_DIZINI
    cikti: Path = sabitler.CIKTI
    gun_sayisi: int | None = None
    ilerleme: bool = True

    @property
    def ilerleme_yolu(self) -> Path | None:
        return Path(self.cikti) / "ilerleme.jsonl" if self.ilerleme else None

    @property
    def oyun_yolu(self) -> Path:
        return Path(self.cikti) / "oyun.json"

    def yayimlanan_mi(self, yol: int) -> bool:
        """Yol 0 TAM dünyada yayımlanan DuckDB'den öğrenir; başka her yol doğrulama koşusunun yayımlanan
        biçiminden."""
        return int(yol) == 0 and self.olcek == "tam" and self.gun_sayisi is None


EGRI_TABLOLARI = ("magaza", "magaza_olay", "urun", "satis", "stok")
DEPO_TABLOLARI = ("siparis", "kalite_kontrol", "urun")


def depo_tablosu(siparis: pd.DataFrame, kalite: pd.DataFrame, urun: pd.DataFrame, optionlar) -> pd.DataFrame:
    """Option × beden (b1..b5) ilk dağıtım anındaki depo: ilk siparişin adedi − hatalı (modül notu).
    `optionlar`: beş bedenli oyun option_id'leri. Bir option'ın ilk siparişi yoksa `ValueError`."""
    u = pd.DataFrame({"urun_id": urun["urun_id"].astype(str).to_numpy(),
                      "beden_sira": urun["beden_sira"].to_numpy(dtype=np.int64)})
    s = siparis[(siparis["tip"].astype(str) == "ilk").to_numpy()
                & siparis["option_id"].astype(str).isin(set(optionlar)).to_numpy()]
    s = pd.DataFrame({"siparis_id": s["siparis_id"].astype(str).to_numpy(),
                      "option_id": s["option_id"].astype(str).to_numpy(),
                      "urun_id": s["urun_id"].astype(str).to_numpy(),
                      "adet": s["adet"].to_numpy(dtype=np.int64)}).merge(u, on="urun_id", how="left")
    eksik = sorted(set(optionlar) - set(s["option_id"]))
    if eksik:
        raise ValueError(f"ilk siparişi olmayan oyun option'ı: {eksik[:5]}")
    hatali = kalite.assign(siparis_id=kalite["siparis_id"].astype(str)).groupby("siparis_id")["hatali"].sum()
    s = s.sort_values(["siparis_id", "beden_sira"], kind="stable").reset_index(drop=True)
    h = np.zeros(len(s), dtype=np.int64)
    for sid, idx in s.groupby("siparis_id", sort=False).indices.items():
        n = int(hatali.get(sid, 0))
        if n > 0:
            h[idx] = en_buyuk_kalan(n, s["adet"].to_numpy(dtype=float)[idx])
    s["depo"] = s["adet"].to_numpy() - h
    t = s.pivot_table(index="option_id", columns="beden_sira", values="depo", aggfunc="sum", fill_value=0)
    t = t.reindex(columns=range(1, len(SUTUNLAR) + 1), fill_value=0)
    t.columns = SUTUNLAR
    return t.sort_index().astype(np.int64)


def ham_egri(e: egri_modulu.Egri, ham: pd.DataFrame) -> pd.DataFrame:
    """Sansür düzeltmesiz eğri (p2_ham): okunabilen mağazada (`kaynak` "magaza") ham satış payı,
    okunamayanda ana eğrinin yedeği (modül notu)."""
    E = e.magaza.copy()
    okunur = [m for m, k in e.kaynak.items() if k == "magaza"]
    E.loc[okunur] = ham.loc[okunur, SUTUNLAR].to_numpy()
    if E.isna().to_numpy().any() or not np.allclose(E.sum(axis=1), 1.0):
        raise ValueError("ham eğri tanımsız ya da bire toplanmıyor")
    return E


def on_denetim(desenler, atama: pd.Series, ns: dict, depo: pd.DataFrame) -> dict:
    """Koşmadan, option başına depo sınaması: beş bedenli her oyun option'ında (`depo`'nun satırları)
    Σ_m ns × desen_b ≤ depo_b mi. Atamasız mağaza standart paket alır ve sınamaya girmez (yalnız
    desen alan mağazalar). Dönüş: aşan option sayısı, aşan (option, beden) ve toplam aşan adet."""
    D = np.asarray(desenler, dtype=np.int64)
    a = {str(m): int(d) for m, d in atama.items()}
    yuk = {o: np.zeros(len(SUTUNLAR), dtype=np.int64) for o in depo.index}
    for (o, m), n in ns.items():
        if o in yuk and str(m) in a:
            yuk[o] += int(n) * D[a[str(m)]]
    Y = pd.DataFrame.from_dict(yuk, orient="index", columns=SUTUNLAR).loc[depo.index]
    asim = (Y - depo).clip(lower=0)
    return {"option": int((asim.sum(axis=1) > 0).sum()), "option_beden": int((asim > 0).to_numpy().sum()),
            "asim_adet": int(asim.to_numpy().sum()), "kontrol_option": int(len(depo))}


class YolGirdisi:
    """Bir yolun kararları kuran girdileri (modül notu), tembel."""

    def __init__(self, yol: int, ortam: Ortam):
        self.yol, self.ortam = int(yol), ortam
        self._tasarimlar: dict = {}
        self._ns: dict = {}
        self._agirlik: dict = {}

    @functools.cached_property
    def w(self):
        return motor.dunya(self.ortam.olcek)

    @functools.cached_property
    def lumoda(self):
        """Yolun Lumoda koşusu: vakanın o yoldaki doğrulama kolu (önbellekten ya da koşulur)."""
        return simulasyon.kos_dogrulama(self.yol, self.ortam.olcek, onbellek=self.ortam.onbellek,
                                        gun_sayisi=self.ortam.gun_sayisi)

    @property
    def kaynak_adi(self) -> str:
        """Kararların tablo kaynağı: "yayimlanan" ya da doğrulama koşusunun dizin adı."""
        return "yayimlanan" if self.ortam.yayimlanan_mi(self.yol) else f"vaka:{self.lumoda.dizin.name}"

    def _baglanti(self) -> tuple[duckdb.DuckDBPyConnection, dict]:
        """Yolun yayımlanan tablolarına bağlantı (modül notu) ve kayıtlı DataFrame'ler (bağlantı açıkken
        yaşamalı); çağıran kapatır."""
        if self.ortam.yayimlanan_mi(self.yol):
            return kaynak.baglan(), {}
        kirli = ("satis", "stok", "sevkiyat")
        t = motor.yayimlanan_bicim({a: self.lumoda.tablo(a) for a in kirli}, self.ortam.olcek)
        t = {a: t[a] if a in t else self.lumoda.tablo(a) for a in sorted(set(EGRI_TABLOLARI + DEPO_TABLOLARI))}
        con = duckdb.connect(":memory:")
        for a, df in t.items():
            con.register(a, df)
        return con, t

    @functools.cached_property
    def _kararlar(self) -> dict:
        """Eğri, ham eğri, kapsam ve depo (tablolar bir kez okunur, sonra bırakılır)."""
        t0 = time.perf_counter()
        con, sakla = self._baglanti()
        try:
            et = egri_modulu.egri_tablolari(con, sabitler.KARAR_GUNU)
            dt = kaynak.yayimlanan_tablolar(con, DEPO_TABLOLARI)
        finally:
            con.close()
            del sakla
        kapsam = kaynak.kapsam(et, sabitler.KARAR_GUNU)
        e = egri_modulu.magaza_egrisi(et, kapsam, sabitler.KARAR_GUNU)
        ham = egri_modulu.ham(et, kapsam, sabitler.KARAR_GUNU)
        del et
        depo = depo_tablosu(dt["siparis"], dt["kalite_kontrol"], dt["urun"], self.bes_optionlar)
        sip = depo_tablosu(dt["siparis"], dt["kalite_kontrol"].iloc[:0], dt["urun"], self.bes_optionlar)  # R16
        del dt
        sn = time.perf_counter() - t0
        al_oyun._ilerleme(f"y{self.yol}_girdiler", sn, False, self.ortam.ilerleme_yolu, kaynak=self.kaynak_adi,
                          kappa=e.kappa, magaza=int(len(e.magaza)))
        return {"egri": e, "ham_egri": ham_egri(e, ham), "kapsam": kapsam, "depo": depo, "siparis": sip,
                "sure_sn": round(sn, 1)}

    @property
    def egri(self) -> egri_modulu.Egri:
        return self._kararlar["egri"]

    @property
    def depo(self) -> pd.DataFrame:
        """Hata düşülmüş depo (motorun deposu): yalnız ön denetim ve korunum (modül notu)."""
        return self._kararlar["depo"]

    @property
    def siparis_deposu(self) -> pd.DataFrame:
        """İlk sipariş adedi (karar öncesi): tasarımın beklediği depo (R16)."""
        return self._kararlar["siparis"]

    def egri_tanisi(self) -> dict:
        """Eğrinin tanısı (Task 6 raporu; ayrı `kalibrasyon` komutu yok, Ruling R17): seçilen κ, κ tablosu
        (her κ için SS24 karar anında kurulan eğrinin SS24 Collection ilk haftalarının gerçekleşen
        payına ortalama L1'i; `egri.kappa_sec`), seçilenin L1'i, ızgara ucunda mı, yeni mağaza kuralı,
        sansür tanısı."""
        e = self.egri
        t = e.kappa_tablosu
        satir = [] if t is None else [{"kappa": float(r.kappa), "l1": float(r.l1), "magaza": int(r.magaza)}
                                       for r in t.itertuples(index=False)]
        secilen = next((s["l1"] for s in satir if s["kappa"] == e.kappa), None)
        return {"kappa": e.kappa, "kappa_tablosu": satir, "ss24_l1": secilen,
                "izgara_ucunda": bool(satir) and e.kappa == max(s["kappa"] for s in satir),
                "yeni_secim": e.yeni_secim, "sansur": e.sansur}

    def egri_tablosu(self, tur: str = "duzeltilmis") -> pd.DataFrame:
        return self._kararlar["ham_egri"] if tur == "ham" else self.egri.magaza

    @functools.cached_property
    def oyun_ids(self) -> list[str]:
        return simulasyon.option_idleri(self.w, simulasyon.oyun_optionlari(self.w))

    @functools.cached_property
    def bes_optionlar(self) -> list[str]:
        """Beş bedenli setlerin oyun option'ları (desen alanlar; aksesuar standart pakette kalır)."""
        _, harita = politika.paket_ekle(self.w.paketler, [sabitler.LUMODA_PAKET])
        setler = {bs for bs, d in harita if d != politika.STANDART}
        seti = self.w.optionlar.set_index(self.w.optionlar["option_id"].astype(str))["beden_seti"].astype(str)
        return sorted(o for o in self.oyun_ids if seti[o] in setler)

    @functools.cached_property
    def _giden(self) -> tuple[dict, dict]:
        oyun = set(self.oyun_ids)
        ns = {a: v for a, v in kosucu.lumoda_giden(self.lumoda).items() if a[0] in oyun}
        adet = {a: v for a, v in kosucu.giden_adet(self.lumoda).items() if a[0] in oyun}
        return ns, adet

    @property
    def giden_adet(self) -> dict:
        """Lumoda'nın oyun (option, mağaza) başına giden adedi (korunumun referansı)."""
        return self._giden[1]

    def ns(self, adet: int = sabitler.PAKET_ADET) -> dict:
        """(option_id, magaza_id) → paket, oyun option'larında (modül notu)."""
        adet = int(adet)
        if adet not in self._ns:
            ns7, adet7 = self._giden
            if adet == sabitler.PAKET_ADET:
                self._ns[adet] = dict(ns7)
            else:
                bes = set(self.bes_optionlar)
                d = kosucu.ns_donustur({a: v for a, v in adet7.items() if a[0] in bes}, adet,
                                       NS_YUVARLAMA.get(adet, "yakin"))
                self._ns[adet] = d | {a: v for a, v in ns7.items() if a[0] not in bes}
        return self._ns[adet]

    def agirlik(self, adet: int = sabitler.PAKET_ADET) -> pd.Series:
        """Mağaza → beş bedenli oyun option'larındaki ns(adet) toplamı, eğrinin mağazalarında."""
        adet = int(adet)
        if adet not in self._agirlik:
            self._agirlik[adet] = self._agirlik_kur(adet)
        return self._agirlik[adet]

    def _agirlik_kur(self, adet: int) -> pd.Series:
        bes = set(self.bes_optionlar)
        toplam: dict[str, int] = {}
        for (o, m), n in self.ns(adet).items():
            if o in bes:
                toplam[str(m)] = toplam.get(str(m), 0) + int(n)
        ids = list(self.egri.magaza.index)
        disari = sorted(set(toplam) - set(ids))
        if disari:
            raise ValueError(f"yol {self.yol}: beş bedenli oyun paketi alan ama eğrisi olmayan mağaza: "
                             f"{disari[:5]}")
        return pd.Series({m: float(toplam.get(m, 0)) for m in ids}, name="agirlik").rename_axis("magaza_id")

    def depo_payi(self, adet: int = sabitler.PAKET_ADET, tanim: str = "siparis") -> np.ndarray:
        """Beden başına beklenen depo ÷ kolun giden adedi (a × Σ agirlik), modül notu. `tanim`
        "siparis" (karar öncesi, tasarımın girdisi; R16) ya da "depo" (hata düşülmüş; yalnız sınama)."""
        if tanim not in ("siparis", "depo"):
            raise ValueError(f"depo tanımı 'siparis' ya da 'depo': {tanim!r}")
        d = self.siparis_deposu if tanim == "siparis" else self.depo
        return d.sum(axis=0).to_numpy(dtype="float64") / (int(adet) * float(self.agirlik(adet).sum()))

    def tasarim(self, kol: str, depo: str = "siparis") -> paket_tasarim.Tasarim:
        k = KOLLAR[kol]
        if k.K is None:
            raise ValueError("doğrulama kolunun tasarımı yok (Lumoda'nın standart paketi)")
        anahtar = (k.K, k.adet, k.egri, depo, k.desen)
        if anahtar not in self._tasarimlar:
            if k.desen is not None:
                self._tasarimlar[anahtar] = sabit_tasarim(k.desen, self.egri_tablosu(k.egri), self.agirlik(k.adet),
                                                          self.depo_payi(k.adet, depo))
            else:
                self._tasarimlar[anahtar] = paket_tasarim.tasarla(
                    self.egri_tablosu(k.egri), self.agirlik(k.adet), k.K, self.depo_payi(k.adet, depo), adet=k.adet)
        return self._tasarimlar[anahtar]

    @property
    def kollar(self) -> tuple[str, ...]:
        """Yolun kol kümesi (yol 0 `YOL0_KOLLARI`, yollar `YOL_KOLLARI`)."""
        return YOL0_KOLLARI if self.yol == 0 else YOL_KOLLARI

    def kos(self, kol: str):
        """Kolun simülasyonu (önbellekten ya da koşulur)."""
        if kol == DOGRULAMA:
            return self.lumoda
        k, t = KOLLAR[kol], self.tasarim(kol)
        return simulasyon.kos(kosu_adi(self.yol, kol), t.desenler, t.atama, self.ns(k.adet), yol=self.yol,
                              olcek=self.ortam.olcek, onbellek=self.ortam.onbellek,
                              gun_sayisi=self.ortam.gun_sayisi, tembel=True)

    @functools.cached_property
    def _bilgi(self) -> dict:
        return self._bilgi_kur()

    def bilgi(self) -> dict:
        """oyun.json `yollar` kaydı: kararların kaynağı ve özeti (yol başına bir kez)."""
        return self._bilgi

    def _bilgi_kur(self) -> dict:
        e = self.egri
        dep, sip = self.depo.sum(axis=0), self._kararlar["siparis"].sum(axis=0)
        ns7 = self.ns(7)
        bes = set(self.bes_optionlar)
        giden_beden = np.zeros(len(SUTUNLAR), dtype=np.int64)
        t = kosucu.ilk_dagitim_tablosu(self.lumoda)
        p = self.lumoda.tablo("paket", sutunlar=["paket_id", "beden_sira", "adet"])
        ic = p.pivot_table(index=p["paket_id"].astype(str), columns="beden_sira", values="adet", fill_value=0)
        for pid, n in t[t["option_id"].isin(bes)].groupby("paket_id")["paket"].sum().items():
            giden_beden += int(n) * ic.loc[str(pid)].reindex(range(1, 6), fill_value=0).to_numpy(dtype=np.int64)
        return {
            "yol": self.yol, "kaynak": self.kaynak_adi, "lumoda": self.lumoda.dizin.name,
            "lumoda_anahtar": self.lumoda.meta["anahtar"], "karar_gunu": sabitler.KARAR_GUNU.date().isoformat(),
            "egri": {"kappa": e.kappa, "magaza": int(len(e.magaza)),
                     "kaynak": pd.Series(e.kaynak).value_counts().sort_index().to_dict(),
                     "profil": e.profil.value_counts().sort_index().to_dict(),
                     "zincir": [round(float(x), 6) for x in e.zincir], "yeni_secim": e.yeni_secim.get("secim"),
                     "sure_sn": self._kararlar["sure_sn"]},
            "ns": {"hucre": len(ns7), "paket": int(sum(ns7.values())),
                   "bes_bedenli_option": len(bes), "oyun_option": len(self.oyun_ids),
                   "magaza": int((self.agirlik(7) > 0).sum())},
            "depo": {"ilk_siparis": [int(x) for x in sip], "depo": [int(x) for x in dep],
                     "lumoda_giden": [int(x) for x in giden_beden],
                     "depo_payi_7": [round(float(x), 6) for x in self.depo_payi(7)],
                     "depo_payi_12": [round(float(x), 6) for x in self.depo_payi(12)],
                     "depo_payi_7_hatali_dusulmus": [round(float(x), 6) for x in self.depo_payi(7, "depo")],
                     "depo_payi_12_hatali_dusulmus": [round(float(x), 6) for x in self.depo_payi(12, "depo")],
                     "tanim": "tasarım ilk sipariş adediyle (karar öncesi, R16); hata düşülmüş depo ön denetimde",
                     "tanimlar_ayni": depo_tanimlari_ayni(self)},
            "egri_tanisi": {a: v for a, v in self.egri_tanisi().items() if a != "sansur"},
            "donusum_12": kosucu.donusum_ozeti({a: v for a, v in self.giden_adet.items() if a[0] in bes},
                                               {a: v for a, v in self.ns(12).items() if a[0] in bes}, 12),
            "donusum_14": kosucu.donusum_ozeti({a: v for a, v in self.giden_adet.items() if a[0] in bes},
                                               {a: v for a, v in self.ns(14).items() if a[0] in bes}, 14,
                                               NS_YUVARLAMA.get(14, "yakin")),
        }

    # --- koşusuz rapor girdileri (Task 6) ------------------------------------

    def k_egrisi(self) -> list[dict]:
        return k_egrisi(self.egri.magaza, {a: self.agirlik(a) for a in (7, 12)},
                        {a: self.depo_payi(a) for a in (7, 12)})

    def kahin(self, kol: str = "p2") -> dict:
        """Kahin denetimi (yalnız ölçüm; hakemi burada okur)."""
        return kahin_ayni_mi(self.tasarim(kol), self.egri, hakem.gercek_pay(self.w), hakem.kayma(self.w),
                             self.agirlik(KOLLAR[kol].adet))


# ---------------------------------------------------------------------------
# Koşusuz denetimler: K eğrisi ve kahin
# ---------------------------------------------------------------------------


def sabit_tasarim(desen, egri: pd.DataFrame, agirlik: pd.Series, depo_payi) -> paket_tasarim.Tasarim:
    """Aranmayan tasarım (p1_14): `desen` her mağazaya; uyumsuzluk ve toplam depo aşımı `tasarla`'nın
    tanımlarıyla (`en_iyi_mi` False, `yontem` "sabit")."""
    D = np.asarray([desen], dtype=np.int64)
    w = agirlik.reindex(egri.index).fillna(0.0)
    u = sum(paket_tasarim.uyumsuzluk(D[0], egri.loc[m, SUTUNLAR].to_numpy(), float(w[m])) for m in egri.index)
    asim = np.maximum(0.0, float(w.sum()) * D[0] - np.asarray(depo_payi) * int(D[0].sum()) * float(w.sum()))
    asim = np.where(asim > 1e-6, asim, 0.0)
    atama = pd.Series(0, index=egri.index.copy(), name="desen")
    atama.index.name = "magaza_id"
    return paket_tasarim.Tasarim(desenler=D, atama=atama, toplam_uyumsuzluk=float(u), en_iyi_mi=False,
                                 yontem="sabit", depo_uygun=not asim.any(), depo_asimi=asim)


def ayni_tasarim(a: paket_tasarim.Tasarim, b: paket_tasarim.Tasarim) -> bool:
    return (np.array_equal(a.desenler, b.desenler)
            and a.atama.sort_index().astype(int).equals(b.atama.sort_index().astype(int)))


def k_egrisi(egri: pd.DataFrame, agirlik: dict, depo_payi: dict, adetler=(7, 12),
             K_listesi=(*sabitler.K_LISTESI, "magaza")) -> list[dict]:
    """K = 1..4 ve "magaza" için 7 ve 12'li tasarım (gerçek ağırlık `agirlik[a]`, depo `depo_payi[a]`),
    ve 7'lide Lumoda paketi. Satır: adet, K, desenler, toplam ve paket başına uyumsuzluk (beklenen eksik
    adet), en_iyi_mi, yontem, depo_uygun, `ayni` (aynı desen ve atamayı veren ilk daha küçük K; yoksa
    None: o K ayrı bir koşu olurdu)."""
    satirlar = []
    for a in adetler:
        w = agirlik[a]
        if a == sabitler.PAKET_ADET:
            L = np.asarray(sabitler.LUMODA_PAKET, dtype=float)
            u = sum(paket_tasarim.uyumsuzluk(L, egri.loc[m, SUTUNLAR].to_numpy(), float(w[m])) for m in egri.index)
            satirlar.append({"adet": a, "K": "lumoda", "desenler": [paket_tasarim.desen_adi(L)],
                             "toplam_uyumsuzluk": float(u), "paket_basina": float(u / w.sum()),
                             "en_iyi_mi": None, "yontem": None, "depo_uygun": None, "ayni": None})
        onceki: list[tuple] = []
        for K in K_listesi:
            t = paket_tasarim.tasarla(egri, w, K, depo_payi[a], adet=a)
            ayni = next((k for k, o in onceki if ayni_tasarim(o, t)), None)
            satirlar.append({"adet": a, "K": K, "desenler": [paket_tasarim.desen_adi(d) for d in t.desenler],
                             "toplam_uyumsuzluk": t.toplam_uyumsuzluk,
                             "paket_basina": t.toplam_uyumsuzluk / float(w.sum()), "en_iyi_mi": t.en_iyi_mi,
                             "yontem": t.yontem, "depo_uygun": t.depo_uygun, "ayni": ayni})
            onceki.append((K, t))
    return satirlar


def kahin_ayni_mi(tasarim: paket_tasarim.Tasarim, e: egri_modulu.Egri, gercek: pd.DataFrame,
                  kayma: pd.Series, agirlik: pd.Series) -> dict:
    """Kahin (yalnız ölçüm): tasarımın desenleri her mağazaya gerçek beden payına göre (en küçük
    beklenen eksik adet; eşitlikte ilk desen) atanırsa atama tasarımınkinden farklı mı. Ayrıca profilin
    etkin (kırpılmış) kaymaya ARI'si (eğrisi okunabilen mağazalarda) ve iki atamanın gerçek paya göre
    uyumsuzluğu."""
    ids = list(tasarim.atama.index)
    G = gercek.loc[ids, SUTUNLAR].to_numpy(dtype="float64")
    eksik = paket_tasarim._eksik(G, np.asarray(tasarim.desenler))
    kahin = pd.Series(np.argmin(eksik, axis=1), index=tasarim.atama.index)
    w = agirlik.reindex(ids).fillna(0.0).to_numpy()
    tas = tasarim.atama.astype(int).to_numpy()
    farkli = [m for m, a, b in zip(ids, tas, kahin.to_numpy()) if a != b]
    okunur = [m for m, k in e.kaynak.items() if k == "magaza"]
    return {"ayni_atama": not farkli, "farkli_magaza": farkli, "magaza": len(ids),
            "ari": olcutler_egri.ari(e.profil.loc[okunur], kayma), "ari_magaza": len(okunur),
            "uyumsuzluk_gercek_tasarim": float((w * eksik[np.arange(len(ids)), tas]).sum()),
            "uyumsuzluk_gercek_kahin": float((w * eksik[np.arange(len(ids)), kahin.to_numpy()]).sum())}


# ---------------------------------------------------------------------------
# Koşu ve ölçüm
# ---------------------------------------------------------------------------


def olcum_kaydi(k, G: YolGirdisi, kol: str) -> dict:
    """Bir koşunun ölçümü: `kosucu.olc`, korunum (Lumoda'nın giden adedine), 12'lide dönüşüm, aynı mal;
    doğrulamada TAM'da İlk Sevkiyat'ın kayıtlı ölçütleriyle kıyas."""
    o = kosucu.olc(k, G.w)
    kay = {"olcutler": o, "korunum": kosucu.korunum(k, G.giden_adet)}
    if kol == DOGRULAMA:
        ref = kosucu._referans(G.yol) if G.ortam.olcek == "tam" and G.ortam.gun_sayisi is None else None
        if ref is not None:
            fark = sorted(a for a, v in ref.items() if o.get(a) != v)
            kay["ilk_sevkiyat"] = {"birebir": len(ref) - len(fark), "olcut": len(ref), "farkli": fark}
    a = KOLLAR[kol].adet
    if a != sabitler.PAKET_ADET:
        bes = set(G.bes_optionlar)
        kay["donusum"] = kosucu.donusum_ozeti({x: v for x, v in G.giden_adet.items() if x[0] in bes},
                                              {x: v for x, v in G.ns(a).items() if x[0] in bes}, a,
                                              NS_YUVARLAMA.get(a, "yakin"))
    kay["ayni_mal"] = None if kol == DOGRULAMA else bool(
        o["kirpilan_adet"] == 0 and (a != sabitler.PAKET_ADET or kay["korunum"]["fark_adet"] == 0))
    return kay


def olcum_metinleri() -> dict[str, str]:
    """Ölçüm özetinin girdileri: `kosucu.py`, İlk Sevkiyat `olcutler.py` (dosya) ve bu modülün
    `OLCUM_FONKSIYONLARI` kaynağı (satır sonları LF)."""
    m = {Path(y).name: Path(y).read_bytes().replace(b"\r\n", b"\n").decode("utf-8")
         for y in (kosucu.__file__, al_olcutler.__file__)}
    for ad in OLCUM_FONKSIYONLARI:
        nesne = globals()[ad.split(".")[0]]
        for parca in ad.split(".")[1:]:
            nesne = vars(nesne)[parca]
        nesne = getattr(nesne, "func", None) or getattr(nesne, "fget", None) or nesne
        m[ad] = inspect.getsource(nesne)
    return m


def olcum_ozeti(metinler: dict[str, str], surum: int) -> str:
    h = hashlib.sha256()
    for ad in sorted(metinler):
        h.update(ad.encode("utf-8") + b"\0" + metinler[ad].encode("utf-8") + b"\0")
    h.update(f"surum={int(surum)}".encode())
    return h.hexdigest()


def olcum_kodu() -> str:
    """Ölçüm kodunun özeti (modül notu; içe aktarma anında kurulan `OLCUM_OZETI`): değişirse kayıt
    önbellekteki koşudan yeniden ölçülür."""
    return OLCUM_OZETI


def tasarim_kaydi(G: YolGirdisi, kol: str) -> dict:
    k = KOLLAR[kol]
    if k.K is None:
        return {"paket_adet": k.adet, "K": None, "desenler": [paket_tasarim.desen_adi(sabitler.LUMODA_PAKET)],
                "atama": None, "egri_kaynagi": None, "ns_kaynagi": "lumoda"}
    t = G.tasarim(kol)
    adlar = [paket_tasarim.desen_adi(d) for d in t.desenler]
    return {"paket_adet": k.adet, "K": k.K, "egri": k.egri, "desenler": adlar, **({"notu": k.notu} if k.notu else {}),
            "atama": {str(m): adlar[int(i)] for m, i in t.atama.items()},
            "egri_kaynagi": G.kaynak_adi, "ns_kaynagi": f"vaka:{G.lumoda.dizin.name}",
            "tasarim": {"toplam_uyumsuzluk": t.toplam_uyumsuzluk, "en_iyi_mi": t.en_iyi_mi, "yontem": t.yontem,
                        "depo_uygun": t.depo_uygun,
                        "depo_asimi": None if t.depo_asimi is None else [float(x) for x in t.depo_asimi]},
            "on_denetim": on_denetim(t.desenler, t.atama, G.ns(k.adet), G.depo)}


def kos_bir(yol: int, kol: str, G: YolGirdisi, onceki: dict | None = None) -> dict:
    """Koşu (önbellekten ya da yeni) ve ölçüm; kayıt sözlüğü. `onceki` (bu koşunun eski kaydı) anahtarı
    ve ölçüm kodu tutarsa yeniden ölçülmez."""
    if int(yol) != G.yol:
        raise ValueError(f"{kol}: yol {yol}, girdi yol {G.yol}")
    t0 = time.perf_counter()
    ad = kosu_adi(yol, kol)
    tas = tasarim_kaydi(G, kol)
    k = G.kos(kol)
    t1 = time.perf_counter()
    kod = olcum_kodu()
    if onceki and onceki.get("anahtar") == k.meta["anahtar"] and onceki.get("olcum_kodu") == kod:
        olcum = {a: onceki[a] for a in OLCUM_ALANLARI if a in onceki}
    else:
        olcum = olcum_kaydi(k, G, kol) | {"olcum_sn": round(time.perf_counter() - t1, 1)}
    kayit = {"ad": ad, "yol": int(yol), "kol": kol, "aciklama": KOLLAR[kol].aciklama, **tas,
             "anahtar": k.meta["anahtar"], "olcum_kodu": kod, "talep_tohumu": k.meta.get("talep_tohumu"),
             "motor_sn": k.meta.get("motor_sn"), "kosu_sn": k.meta.get("sure_sn"),
             "tepe_bellek_gb": k.meta.get("tepe_bellek_gb"), **olcum}
    o = kayit["olcutler"]
    al_oyun._ilerleme(ad, time.perf_counter() - t0, k.onbellekten, G.ortam.ilerleme_yolu,
                      motor_sn=k.meta.get("motor_sn"), tepe_gb=k.meta.get("tepe_bellek_gb"),
                      olcum_sn=kayit.get("olcum_sn"), surec_tepe_gb=motor._tepe_bellek_gb(),
                      bulunabilirlik=round(o["bulunabilirlik"], 3), kirpilan_adet=o["kirpilan_adet"],
                      paket_tipi=o["paket_tipi"], ayni_mal=kayit["ayni_mal"])
    return kayit


def ayni_kol(G: YolGirdisi, kol: str, depo: str = "siparis") -> str | None:
    """Aynı yolun kol kümesinde (`G.kollar`) `kol`'dan önce gelen, aynı paket adedinde aynı desen ve atamayı
    veren kol: simülasyonu adı dışında birebir aynıdır (ns paket adedine bağlı), bir kez koşulur. Yoksa
    None. `depo`: tasarımın depo tanımı (`YolGirdisi.depo_payi`)."""
    k = KOLLAR[kol]
    if k.K is None:
        return None
    for ad in G.kollar:
        if ad == kol:
            return None
        o = KOLLAR[ad]
        if o.K is not None and o.adet == k.adet and ayni_tasarim(G.tasarim(ad, depo), G.tasarim(kol, depo)):
            return ad
    return None


def depo_tanimlari_ayni(G: YolGirdisi) -> dict:
    """R16 sınaması (koşusuz): yolun her kolunda karar öncesi (sipariş) ve hata düşülmüş depoyla tasarım
    ve `ayni_kol` bağı aynı mı. Aynıysa koşuların simülasyon anahtarı tanımdan bağımsızdır."""
    farkli = [kol for kol in G.kollar if KOLLAR[kol].K is not None
              and (not ayni_tasarim(G.tasarim(kol), G.tasarim(kol, "depo"))
                   or ayni_kol(G, kol) != ayni_kol(G, kol, "depo"))]
    return {"ayni": not farkli, "farkli": farkli}


def kos_hepsi(blok: str = "hepsi", ortam: Ortam | None = None, adlar=None) -> dict:
    """Izgarayı (`izgara_listesi(blok)`; `adlar` verilirse yalnız o kollar) sırayla koşar; her koşudan
    sonra `oyun.json`. Yeniden başlatılan ızgara önbellekten sürer (anahtarı ve ölçüm kodu aynı kayıt
    yeniden ölçülmez). **Aynı koşu iki adla** (İlk Sevkiyat `imza` kalıbı): tasarımı daha önceki bir
    kolunkiyle aynı olan kol (`ayni_kol`; ör. yol 0'da pm_12 = p3_12) koşulmaz, kaydı o kolun ölçümünü
    taşır ve `ayni` alanıyla ona bağlanır."""
    ortam = Ortam() if ortam is None else ortam
    kayit = al_oyun.json_oku(ortam.oyun_yolu)
    if kayit.get("olcek", ortam.olcek) != ortam.olcek:
        raise ValueError(f"{ortam.oyun_yolu} {kayit['olcek']} ölçeğinde; bu ızgara {ortam.olcek}")
    kosular, yollar = kayit.setdefault("kosular", {}), kayit.setdefault("yollar", {})
    kayit["kosulmayan"] = KOSULMAYAN
    G, islenen = None, set()
    for yol, kol in izgara_listesi(blok):
        if adlar is not None and kol not in adlar and kosu_adi(yol, kol) not in adlar:
            continue
        if G is None or G.yol != yol:
            G = YolGirdisi(yol, ortam)                    # önceki yolun tabloları bırakılır
        ad = kosu_adi(yol, kol)
        taban = ayni_kol(G, kol)
        if taban is None:
            kosular[ad] = kos_bir(yol, kol, G, kosular.get(ad))
        else:
            tad = kosu_adi(yol, taban)
            if tad not in islenen:                        # tabanın kaydı (önbellekten; ölçüm gerekiyorsa)
                kosular[tad] = kos_bir(yol, taban, G, kosular.get(tad))
                islenen.add(tad)
            kosular[ad] = {**kosular[tad], **tasarim_kaydi(G, kol), "ad": ad, "kol": kol,
                           "aciklama": KOLLAR[kol].aciklama, "ayni": tad}
            al_oyun._ilerleme(ad, 0.0, True, ortam.ilerleme_yolu, ayni=tad)
        islenen.add(ad)
        yollar[str(yol)] = G.bilgi()
        kayit["olcek"] = ortam.olcek
        al_oyun.json_yaz(ortam.oyun_yolu, kayit)
    return kayit


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv=None) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(prog="python -m beden_paket.oyun")
    # Ayrı bir `kalibrasyon` komutu yok (Ruling R17): κ eğrinin içinde seçilir (`egri.kappa_sec`, R8); κ
    # tablosu ve SS24 uyumu `YolGirdisi.egri_tanisi()` ve oyun.json `yollar.<p>.egri_tanisi`'nde.
    alt = ap.add_subparsers(dest="komut", required=True)
    iz = alt.add_parser("izgara", help="oyun ızgarası (cikti/oyun.json, cikti/ilerleme.jsonl)")
    iz.add_argument("--blok", default="hepsi", choices=[*BLOK_SIRASI, "hepsi"])
    iz.add_argument("--olcek", default="TAM", type=str.upper, choices=["TAM", "KUCUK"])
    iz.add_argument("--ad", action="append", help="yalnız bu kol(lar) ya da koşu(lar) (tekrarlanabilir)")
    a = ap.parse_args(argv)
    al_oyun.uyanik_tut()
    t0 = time.perf_counter()
    olcek = a.olcek.lower()
    ortam = Ortam(olcek=olcek, cikti=sabitler.CIKTI if olcek == "tam" else sabitler.CIKTI / "kucuk")
    kos_hepsi(a.blok, ortam, adlar=None if a.ad is None else set(a.ad))
    print(f"ızgara bitti: {time.perf_counter() - t0:.0f} sn", flush=True)


# Ölçüm kodunun özeti, içe aktarma anında bir kez (bütün işlevler tanımlandıktan sonra)
OLCUM_OZETI = olcum_ozeti(olcum_metinleri(), OLCUM_SURUMU)


if __name__ == "__main__":
    main()
