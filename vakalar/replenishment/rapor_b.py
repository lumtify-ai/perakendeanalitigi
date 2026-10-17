"""Raporun veri yarısı: `rapor.py`'nin bastığı her sayının girdisi buradan (önbellekten) gelir.

Bu dosya **motoru koşturmaz**. Oyun koşularını `cikti/kosular/`'dan, `cikti/oyun.json`'daki
anahtarla, yalnız okumak için açar (`Onbellek`): meta yoksa, anahtar oyun.json'dakinden farklıysa
ya da kayıt bugünkü koşu kodu, v4 dosyası ve kütüphane sürümleriyle yazılmamışsa `RuntimeError`
(rapor stdout'a hiçbir şey basmaz; önce ızgara: `python -m replenishment.oyun izgara`). Okuyucu
`motor.kos`'un tersine bozuk kaydı silmez ve eksik koşuyu koşmaz.

Girdiler:

    cikti/oyun.json, yollar.json, kalibrasyon.json, hikaye.json, esitlik.json   (ölçülmüş kayıtlar)
    cikti/kosular/<ad>_<anahtar>/                (koşuların tabloları, gizli gerçek, kol kayıtları)
    veri/cikti/v4/perakende.duckdb               (yayımlanan dünya: VERİ, hikâyenin depo stoğu)
    cikti/tahmin/yol0.json                       (yol 0 LightGBM; kimliği koşununkiyle aynı olmalı)

**Kural hedefinin yeniden kurulması** (`hedef_yeniden_kur`). Kolun kaydı pazartesi başına yalnız
hedef toplamını tutar (`hedef_adet`); tabanın kaç çiftte bağladığı, toplam ile max farkı ve sansür
düzeltmesinin hedefe etkisi çift düzeyinde hedef ister. Rapor, kolun her pazartesi gördüğü
geçmişi koşunun kendi tablolarından kurar: satış matrisi `satis`'in pozitif satırlarından (ham
koşu tablosu: kirli kayıt yok), stoklu matris akışlardan (`stoklu_matrisi`: bir pazartesi
fotoğrafından başlayıp her gün satıştan önce varışlar eklenir, mağazadan çıkan sevkler düşülür; satış
ve iade günün sonunda; motorun 14. adımdaki `stok > 0` bayrağı), özel gün katsayıları pencere başına
dek geçmişten (`ihtiyac.ozel_gun_katsayilari`, kolun bir kerelik hesabıyla aynı girdi). Sonra
`ihtiyac.kural_ongorusu` ve `guvenlik_stoku` kolun kendi fonksiyonlarıyla çağrılır. Korunum:
yeniden kurulan fiziksel hedef toplamı her pazartesi kolun kaydettiği `hedef_adet`'le birebir
(`HEDEF_TOLERANSI`). Ortak `stok.gunluk_magaza` kullanılmaz: "uygun" saymadığı günler (yeni açılan
mağazanın açılış haftası, lansman öncesi) motorun bayrağından ayrılır.

**LightGBM'in ilk pazartesisi** (`ilk_pazartesi_lgbm`): oyunun ilk pazartesisinde bütün kolların
geçmişi aynıdır (pencereden önce hepsi Lumoda). Özellikler aynı matrislerden
`tahmin.ozellik_tablosu` ile kurulur, tahmin yol 0 modeliyle; korunum: fiziksel toplam
`tahmin_ref`'in ilk pazartesi `hedef_adet`'ine eşit.

**Teşhis** (Ruling R33, `teshis`): kolların gizli gerçeğinden pencerede, fiziksel mağazalarda,
talepli hücre-gün ve karşılanmayan talep üç kesitte gruplanır: lansman grubu (pencerede lanse
edilen AW25 option'ları, dalga 2–3, lansmandan bu yana geçen güne göre; öncekiler), line × pencere
yarısı, line × beden sınıfı (çekirdek beden sırası 2–4, kenar, tek bedenli). Korunum: grupların
toplamı kolun ölçütüne (`talep_adet`, `bulunabilirlik`) eşit.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from replenishment import ihtiyac, kaynak, motor, oyun, politika, sabitler, tahmin
from replenishment import yollar as yollar_modulu
from replenishment.kaynak import ONLINE, _HucreIndisi

CIKTI = sabitler.CIKTI
OYUN_BAS, OYUN_BIT = sabitler.OYUN_BAS, sabitler.OYUN_BIT
SURUM_PAKETLERI = ("numpy", "pandas", "pyarrow", "lightgbm", "scikit-learn")
ANAHTAR_ALANLARI = ("ad", "parametreler", "ilk_alim_orani", "kaydedici", "turler", "politikalar", "talep_tohumu",
                    "operasyon_tohumu", "olcek", "gun_sayisi", "kod", "veri", "surumler")
HEDEF_TOLERANSI = 1e-9          # yeniden kurulan hedef / kayıt − 1, her pazartesi (birebir)
GECMIS_GUN = 56                 # LightGBM'in en uzun penceresi (8 hafta) ve istatistik ailesi
STOKLU_GUN = 28                 # ros ailesinin penceresi; stoklu matris bu kadar geriden kurulur
CEKIRDEK = (2, 3, 4)            # olcutler.CEKIRDEK_BEDENLER ile aynı (kırık çift tanımı)

# Teşhis ve sınırın kolları (R33): kısıtlı Lumoda, kural referans + ufuk taraması; ötekiler bağlam
SINIR_KOLLARI = ("lumoda_ref", "kural_ref", "kural_ufuk_14", "kural_ufuk_21", "kural_ufuk_28")
TESHIS_KOLLARI = ("lumoda_kisitsiz",) + SINIR_KOLLARI + ("tahmin_taban_ref", "tahmin_ref", "kural_basit_ref")
# Kural hedefinin yeniden kurulduğu koşular (aile taraması + en geniş ufuk)
HEDEF_KOSULARI = ("kural_ref", "kural_gs_ros", "kural_gs_istatistik", "kural_ufuk_28")
# Alım düzeyi → referans noktaya en yakın kural koşusu (DEPO: ilk alım, defter başlangıcı)
ALIM_KOSULARI = {0.4: "kural_a040_oncelik_cover", 0.7: "demo_kural_a070_gevsek", 1.0: "kural_ref"}


def _ts(d) -> pd.Timestamp:
    return pd.Timestamp(d).normalize()


def _json(yol: Path) -> dict:
    yol = Path(yol)
    if not yol.exists():
        raise RuntimeError(f"{yol} yok: önce ızgara, yollar ve hikâye adımları (README)")
    return json.loads(yol.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Önbellekten okuma (koşmaz)
# ---------------------------------------------------------------------------


def guncel_kimlik() -> dict:
    """Bugünkü koşu kodu özeti, v4 dosyasının parmak izi, kütüphane sürümleri."""
    return {"kod": motor.kod_ozeti(), "veri": motor.veri_parmak_izi(),
            "surumler": {p: motor._surum(p) for p in SURUM_PAKETLERI}}


def _ayni(a, b) -> bool:
    return json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)


def kayit_sorunlari(meta: dict, beklenen_anahtar: str, guncel: dict) -> list[str]:
    """Önbellekteki koşu kaydının bugünkü kodla, veriyle ve oyun.json'la tutarsızlıkları (boşsa
    geçerli): anahtar oyun.json'dakiyle aynı; `kod`, `veri`, `surumler` güncel; meta'nın anahtar
    alanlarının özeti anahtarın kendisi (`motor.kos` aynı özetle arar)."""
    sorun = []
    if meta.get("anahtar") != beklenen_anahtar:
        sorun.append("anahtar oyun.json'daki ölçülmüş kayıttan farklı")
    for a in ("kod", "veri", "surumler"):
        if not _ayni(meta.get(a), guncel.get(a)):
            sorun.append(f"{a} bugünkünden farklı")
    icerik = {a: meta[a] for a in ANAHTAR_ALANLARI if a in meta}
    if motor._ozet(icerik) != meta.get("anahtar"):
        sorun.append("meta alanlarının özeti anahtarı vermiyor")
    return sorun


class Onbellek:
    """oyun.json'daki koşuları önbellekten açar (koşmaz, silmez); açılanları `acilan`'da sayar."""

    def __init__(self, kosular: dict, dizin: Path = motor.KOSU_DIZINI, guncel: dict | None = None):
        self.kosular = kosular
        self.dizin = Path(dizin)
        self.guncel = guncel if guncel is not None else guncel_kimlik()
        self.acilan: set[str] = set()

    def ac(self, ad: str, *, kayit: bool = True) -> motor.KosuKaydi:
        e = self.kosular.get(ad)
        if e is None:
            raise RuntimeError(f"{ad} oyun.json'da yok: önce `python -m replenishment.oyun izgara`")
        d = motor._dizin(self.dizin, ad, e["anahtar"])
        meta_yolu = d / "meta.json"
        if not meta_yolu.exists():
            raise RuntimeError(f"{ad}: koşu önbellekte yok ({d}); rapor motoru koşmaz, önce ızgara")
        meta = json.loads(meta_yolu.read_text(encoding="utf-8"))
        sorun = kayit_sorunlari(meta, e["anahtar"], self.guncel)
        if sorun:
            raise RuntimeError(f"{ad}: önbellek kaydı geçersiz ({'; '.join(sorun)}); ızgarayı yeniden ölçün")
        dosyalar = ([d / f"tablo_{a}.parquet" for a in meta["tablolar"]]
                    + [d / f"kayit_{a}.parquet" for a in meta["kayitlar"]] + [d / "gercek.parquet"])
        eksik = [p.name for p in dosyalar if not p.is_file()]
        if eksik:
            raise RuntimeError(f"{ad}: önbellek kaydında dosya eksik: {eksik}")
        kayitlar = ({a: pd.read_parquet(d / f"kayit_{a}.parquet") for a in meta["kayitlar"]} if kayit else {})
        self.acilan.add(ad)
        return motor.KosuKaydi(dizin=d, meta=meta, kayitlar=kayitlar, onbellekten=True)


def _oku(kosu, ad: str, sutunlar, bas=None, bit=None, sutun: str = "tarih", ek=None) -> pd.DataFrame:
    """Koşunun Parquet tablosu (ya da "gercek"), yalnız `sutunlar`, `sutun` ∈ [bas, bit]."""
    suzgec = list(ek or [])
    if bas is not None:
        suzgec.append((sutun, ">=", _ts(bas)))
    if bit is not None:
        suzgec.append((sutun, "<", _ts(bit) + pd.Timedelta(days=1)))
    return pd.read_parquet(kosu._yol(ad), columns=list(sutunlar), filters=suzgec or None)


# ---------------------------------------------------------------------------
# Dünya: hücre ekseni ve satıştaki çiftler
# ---------------------------------------------------------------------------


@dataclass(eq=False)
class Eksen:
    w: object
    h: kaynak.Harita
    idx: _HucreIndisi
    gun0: pd.Timestamp

    @property
    def C(self) -> int:
        return len(self.h.hucre_sku)

    @property
    def OC(self) -> int:
        return len(self.h.oc_magaza)

    def dunya_gunu(self, tarih) -> int:
        return int((_ts(tarih) - self.gun0).days)

    def satistaki_ciftler(self, tarih) -> np.ndarray:
        """bool[OC]: fiziksel, option satışta (lansman ≤ gün < çıkış), mağaza açık."""
        d = self.dunya_gunu(tarih)
        o = self.h.oc_option
        lans = self.w.optionlar["lansman_gun"].to_numpy()[o]
        cik = self.w.optionlar["cikis_gun"].to_numpy()[o]
        t = _ts(tarih).to_datetime64()
        ac = pd.to_datetime(self.w.magazalar["acilis_tarihi"]).to_numpy()
        ka = pd.to_datetime(self.w.magazalar["kapanis_tarihi"]).to_numpy()
        acik = (np.isnat(ac) | (ac <= t)) & (np.isnat(ka) | (ka > t))
        return (~self.h.oc_online) & (lans <= d) & (d < cik) & acik[self.h.oc_magaza]


def eksen_kur() -> Eksen:
    w = motor.dunya("tam", 1.0)
    return Eksen(w=w, h=kaynak.harita_kur(w), idx=_HucreIndisi(kaynak.hucre_anahtari(w)),
                 gun0=_ts(w.takvim["tarih"].iloc[0]))


def pazartesiler(bas: date = OYUN_BAS, bit: date = OYUN_BIT) -> list[pd.Timestamp]:
    return list(pd.date_range(_ts(bas), _ts(bit), freq="W-MON"))


# ---------------------------------------------------------------------------
# Matrisler (koşunun kendi tablolarından)
# ---------------------------------------------------------------------------


def satis_matrisi(kosu, E: Eksen, bas, bit, dtype=np.int32) -> np.ndarray:
    """`[gün, C]` brüt satış (pozitif satırlar), gün 0 = `bas`."""
    s = _oku(kosu, "satis", ["tarih", "magaza_id", "urun_id", "adet"], bas, bit, ek=[("adet", ">", 0)])
    h = E.idx.kategorik(s["magaza_id"].array, s["urun_id"].array)
    g = ((s["tarih"] - _ts(bas)).dt.days).to_numpy()
    n = int((_ts(bit) - _ts(bas)).days) + 1
    M = np.zeros((n, E.C), dtype=dtype)
    v = h >= 0
    np.add.at(M, (g[v], h[v]), s["adet"].to_numpy()[v].astype(dtype))
    return M


def _gunluk(df, h, g, deger, n: int, C: int, maske=None) -> np.ndarray:
    M = np.zeros((n, C), dtype=np.int32)
    v = (h >= 0) & (g >= 0) & (g < n)
    if maske is not None:
        v &= maske
    np.add.at(M, (g[v], h[v]), deger[v])
    return M


def stoklu_matrisi(kosu, E: Eksen, mat_bas, bas, bit) -> np.ndarray:
    """bool `[gün, C]` (gün 0 = `mat_bas`): fiziksel hücrenin satış öncesi stoğu > 0, `[bas, bit]`
    günlerinde (`bas` pazartesi). Başlangıç `bas` sabahının fotoğrafı (önceki gün sonu); her gün
    satış öncesi stok = dünkü kapanış + varış − mağazadan çıkan sevk, kapanış = satış öncesi − satış
    + iade (motorun gün sırası: transferler, satış, iade)."""
    bas, bit, mat_bas = _ts(bas), _ts(bit), _ts(mat_bas)
    if bas.weekday() != 0:
        raise ValueError(f"stoklu matrisi pazartesi fotoğrafından başlar: {bas.date()}")
    n_b = int((bit - bas).days) + 1
    C = E.C
    st = _oku(kosu, "stok", ["tarih", "magaza_id", "urun_id", "adet"], bas, bas)
    h = E.idx.kategorik(st["magaza_id"].array, st["urun_id"].array)
    stok = np.zeros(C, dtype=np.int64)
    np.add.at(stok, h[h >= 0], st["adet"].to_numpy()[h >= 0])
    sv = _oku(kosu, "sevkiyat", ["varis_tarihi", "hedef", "urun_id", "adet"], bas, bit, sutun="varis_tarihi")
    gir = _gunluk(sv, E.idx.kategorik(sv["hedef"].array, sv["urun_id"].array),
                  ((sv["varis_tarihi"] - bas).dt.days).to_numpy(), sv["adet"].to_numpy(), n_b, C)
    sv = _oku(kosu, "sevkiyat", ["tarih", "kaynak", "urun_id", "adet"], bas, bit)
    cik = _gunluk(sv, E.idx.kategorik(sv["kaynak"].array, sv["urun_id"].array),
                  ((sv["tarih"] - bas).dt.days).to_numpy(), sv["adet"].to_numpy(), n_b, C)
    del sv
    sa = _oku(kosu, "satis", ["tarih", "magaza_id", "urun_id", "adet"], bas, bit)
    hs = E.idx.kategorik(sa["magaza_id"].array, sa["urun_id"].array)
    gs = ((sa["tarih"] - bas).dt.days).to_numpy()
    a = sa["adet"].to_numpy()
    sat = _gunluk(sa, hs, gs, a, n_b, C, a > 0)
    iad = _gunluk(sa, hs, gs, -a, n_b, C, a < 0)
    del sa
    M = np.zeros((int((bit - mat_bas).days) + 1, C), dtype=bool)
    off = int((bas - mat_bas).days)
    fiz = ~E.h.hucre_online
    for d in range(n_b):
        once = stok + gir[d] - cik[d]
        M[off + d] = (once > 0) & fiz
        stok = once - sat[d] + iad[d]
    return M


def _takvim(E: Eksen, mat_bas) -> pd.DataFrame:
    return E.w.takvim.iloc[E.dunya_gunu(mat_bas):].reset_index(drop=True)


def ozel_gun_katsayilari(kosu, E: Eksen) -> dict[str, float]:
    """Kolun bir kerelik hesabı: `CEVRIMDISI_BAS`'tan pencere başına dek koşunun geçmişi."""
    bas = _ts(tahmin.CEVRIMDISI_BAS)
    son = _ts(OYUN_BAS) - pd.Timedelta(days=1)
    S = satis_matrisi(kosu, E, bas, son, dtype=np.int16)
    n = S.shape[0]
    return ihtiyac.ozel_gun_katsayilari(S, E.h, _takvim(E, bas), n)


# ---------------------------------------------------------------------------
# Kural hedefi
# ---------------------------------------------------------------------------


def _hedef_haftasi_talebi(kosu, E: Eksen, pzt: list[pd.Timestamp]) -> np.ndarray:
    """Pazartesi başına fiziksel gerçek talep, hedef haftası [pzt+1, pzt+7]."""
    g = _oku(kosu, "gercek", ["tarih", "magaza_id", "talep"], pzt[0] + pd.Timedelta(days=1),
             pzt[-1] + pd.Timedelta(days=7))
    g = g[(g["magaza_id"].astype(str) != ONLINE).to_numpy()]
    gunluk = g.groupby(g["tarih"].dt.normalize())["talep"].sum()
    return np.array([float(gunluk[(gunluk.index > p) & (gunluk.index <= p + pd.Timedelta(days=7))].sum())
                     for p in pzt])


@dataclass
class HedefSonucu:
    ad: str
    gs: dict
    pazartesi: list                    # Timestamp
    kayit_hedef: np.ndarray            # kolun kaydı (fiziksel bütün çiftler)
    yeni_hedef: np.ndarray             # yeniden kurulan (fiziksel bütün çiftler)
    satistaki: np.ndarray              # satıştaki çift sayısı
    ongoru: np.ndarray                 # Σ öngörü (satıştaki)
    ongoru_ham: np.ndarray             # Σ öngörü, sansür düzeltmesiz (takvim gününe bölme)
    gs_top: np.ndarray                 # Σ güvenlik stoku (satıştaki)
    hedef: np.ndarray                  # Σ max(öngörü, gs) (satıştaki)
    hedef_ham: np.ndarray              # Σ max(öngörü_ham, gs)
    toplam: np.ndarray                 # Σ (öngörü + gs)
    baglayan: np.ndarray               # gs > öngörü olan satıştaki çift
    baglayan_sifir: np.ndarray         # bunlardan öngörüsü 0 olan
    talep: np.ndarray                  # hedef haftasının gerçek talebi (fiziksel)


def hedef_yeniden_kur(kosu, E: Eksen, katsayilar: dict, gs: ihtiyac.GuvenlikStoku) -> HedefSonucu:
    """Modül notu. Pazartesiler kolun kaydından (`politika.hafta_tablosu`)."""
    hafta = politika.hafta_tablosu(kosu)
    pzt = [_ts(t) for t in hafta["tarih"]]
    mat_bas = _ts(OYUN_BAS) - pd.Timedelta(days=GECMIS_GUN)
    S = satis_matrisi(kosu, E, mat_bas, OYUN_BIT)
    ST = stoklu_matrisi(kosu, E, mat_bas, _ts(OYUN_BAS) - pd.Timedelta(days=STOKLU_GUN), OYUN_BIT)
    takvim = _takvim(E, mat_bas)
    fiz = ~E.h.oc_online
    alan = {a: [] for a in ("yeni_hedef", "satistaki", "ongoru", "ongoru_ham", "gs_top", "hedef", "hedef_ham",
                           "toplam", "baglayan", "baglayan_sifir")}
    for p in pzt:
        d = int((p - mat_bas).days)
        ong = ihtiyac.kural_ongorusu(S, E.h, d, katsayilar, ST, takvim=takvim)
        ham = ihtiyac.kural_ongorusu(S, E.h, d, katsayilar, None, takvim=takvim)
        g = ihtiyac.guvenlik_stoku(S, E.h, d, gs, ST)
        hed = np.maximum(ong, g)
        sat = E.satistaki_ciftler(p)
        alan["yeni_hedef"].append(float(np.where(fiz, hed, 0.0).sum()))
        alan["satistaki"].append(int(sat.sum()))
        alan["ongoru"].append(float(ong[sat].sum()))
        alan["ongoru_ham"].append(float(ham[sat].sum()))
        alan["gs_top"].append(float(g[sat].sum()))
        alan["hedef"].append(float(hed[sat].sum()))
        alan["hedef_ham"].append(float(np.maximum(ham, g)[sat].sum()))
        alan["toplam"].append(float((ong + g)[sat].sum()))
        b = sat & (g > ong)
        alan["baglayan"].append(int(b.sum()))
        alan["baglayan_sifir"].append(int((b & (ong <= 0)).sum()))
    del S, ST
    return HedefSonucu(ad=kosu.meta["ad"], gs={"aile": gs.aile, "deger": gs.deger}, pazartesi=pzt,
                       kayit_hedef=hafta["hedef_adet"].to_numpy(dtype=float),
                       talep=_hedef_haftasi_talebi(kosu, E, pzt),
                       **{a: np.array(v) for a, v in alan.items()})


@dataclass
class IlkPazartesi:
    tarih: pd.Timestamp
    satistaki: int
    kural_ongoru: float                # satıştaki çiftler
    lgbm_ongoru: float
    kural_hedef: float                 # max(kural öngörü, gs)
    taban_hedef: float                 # max(LightGBM, gs)
    talep: float                       # hedef haftasının gerçek talebi (fiziksel)
    lgbm_fiziksel: float               # fiziksel bütün çiftler (korunum: tahmin_ref kaydı)
    taban_fiziksel: float              # max(LightGBM, gs), fiziksel bütün çiftler (tahmin_taban_ref kaydı)
    kayit_tahmin: float
    kayit_taban: float
    tahminci: str


def ilk_pazartesi_lgbm(kosu, E: Eksen, katsayilar: dict, gs: ihtiyac.GuvenlikStoku, tahminci_yolu: Path,
                       kayit_tahmin: float, kayit_taban: float) -> IlkPazartesi:
    """Modül notu. `kosu` herhangi bir pencere kolu (ilk pazartesiye dek bütün koşular aynıdır)."""
    p = _ts(OYUN_BAS)
    mat_bas = p - pd.Timedelta(days=GECMIS_GUN)
    son = p - pd.Timedelta(days=1)
    S = satis_matrisi(kosu, E, mat_bas, son)
    ST = stoklu_matrisi(kosu, E, mat_bas, p - pd.Timedelta(days=STOKLU_GUN), son)
    d = GECMIS_GUN
    t = tahmin.Tahminci.yukle(tahminci_yolu).sabitle()
    oz = tahmin.oznitelik_kur(E.w, E.h, mat_bas)
    lgbm = t.tahmin(tahmin.ozellik_tablosu(S, ST, E.h, oz, d))
    takvim = _takvim(E, mat_bas)
    ong = ihtiyac.kural_ongorusu(S, E.h, d, katsayilar, ST, takvim=takvim)
    g = ihtiyac.guvenlik_stoku(S, E.h, d, gs, ST)
    sat = E.satistaki_ciftler(p)
    fiz = ~E.h.oc_online
    return IlkPazartesi(
        tarih=p, satistaki=int(sat.sum()), kural_ongoru=float(ong[sat].sum()), lgbm_ongoru=float(lgbm[sat].sum()),
        kural_hedef=float(np.maximum(ong, g)[sat].sum()), taban_hedef=float(np.maximum(lgbm, g)[sat].sum()),
        talep=float(_hedef_haftasi_talebi(kosu, E, [p])[0]), lgbm_fiziksel=float(lgbm[fiz].sum()),
        taban_fiziksel=float(np.maximum(lgbm, g)[fiz].sum()), kayit_tahmin=kayit_tahmin, kayit_taban=kayit_taban,
        tahminci=t.kimlik)


# ---------------------------------------------------------------------------
# Teşhis (R33)
# ---------------------------------------------------------------------------


YAS_GRUPLARI = ("lansmandan 0–13 gün", "lansmandan 14–27 gün", "lansmandan 28+ gün")
YARILAR = {"ilk": "pencerenin ilk yarısı (hafta 1–9)", "ikinci": "pencerenin ikinci yarısı (hafta 10–18)"}
SAYILAR = ["talepli", "bulunan", "talep", "karsilanmayan"]
ALANLAR = ["kesit", "grup", "line", "yari", "beden", "pencerede", "hafta"]


def lansman_grubu(line, sezon, lansman_tarihi, tarih) -> tuple[np.ndarray, np.ndarray]:
    """(etiket, pencerede) dizileri. AW25 Collection'da lansmanı pencerede olanlar (dalga 2–3) "pencerede
    lanse, lansmandan …" (`tarih` gününe göre yaş: 0–13 / 14–27 / 28+); öncekiler "AW25 dalga 1"; öteki
    Collection "önceki sezonlar"; NOS / Basic / Outlet line adıyla. İlk dağıtım her kolda Lumoda'nındır:
    kollar yeni lansmanların yalnız replenishment'ını farklı yapar."""
    line = np.asarray(line).astype(str)
    lans = pd.to_datetime(pd.Series(np.asarray(lansman_tarihi)))
    col = line == "Collection"
    aw25 = np.asarray(sezon).astype(str) == "AW25"
    icinde = col & aw25 & (lans >= _ts(OYUN_BAS)).to_numpy()
    yas = (pd.to_datetime(pd.Series(np.asarray(tarih))) - lans).dt.days.to_numpy()
    yas_g = np.where(yas < 14, YAS_GRUPLARI[0], np.where(yas < 28, YAS_GRUPLARI[1], YAS_GRUPLARI[2]))
    etiket = np.where(icinde, np.char.add("pencerede lanse, ", yas_g.astype(str)),
                      np.where(col & aw25, "AW25 dalga 1", np.where(col, "önceki sezonlar", line)))
    return etiket.astype(str), icinde


def urun_gruplari(urun: pd.DataFrame) -> pd.DataFrame:
    """urun_id indeksli: line, sezon, lansman tarihi, beden sınıfı (`beden`: çekirdek beden sırası 2–4,
    kenar, tek beden)."""
    u = urun.copy()
    u["urun_id"] = u["urun_id"].astype(str)
    tek = (u["beden_seti"].astype(str) == "Standart").to_numpy()
    u["beden"] = np.where(tek, "tek beden", np.where(u["beden_sira"].isin(CEKIRDEK).to_numpy(), "çekirdek", "kenar"))
    return u.set_index("urun_id")[["line", "sezon_kodu", "beden", "lansman_tarihi", "option_id", "dalga"]]


def teshis_tablosu(gercek: pd.DataFrame, gruplar: pd.DataFrame, bas: date = OYUN_BAS) -> pd.DataFrame:
    """`gercek` (pencere, fiziksel): kesit × grup başına talepli hücre-gün (`talepli`), bulunabilir
    hücre-gün (`bulunan`), `talep`, `karsilanmayan`; grubun alanları (`line`, `yari` "ilk"/"ikinci",
    `beden`, `pencerede`, `hafta` 0…) açıkça. Kesitler: `lansman` (`lansman_grubu`, yaş satırın gününe
    göre), `line_yari` (pencerenin ilk / ikinci yarısı: hafta 0–8 / 9+), `line_beden`, `hafta`."""
    uid = gercek["urun_id"].astype(str)
    line = uid.map(gruplar["line"]).to_numpy().astype(str)
    etiket, pencerede = lansman_grubu(line, uid.map(gruplar["sezon_kodu"]).to_numpy(),
                                      uid.map(gruplar["lansman_tarihi"]).to_numpy(), gercek["tarih"].to_numpy())
    beden = uid.map(gruplar["beden"]).to_numpy().astype(str)
    hafta = ((gercek["tarih"] - _ts(bas)).dt.days // 7).to_numpy()
    yari = np.where(hafta < 9, "ilk", "ikinci")
    talep = gercek["talep"].to_numpy(dtype=np.int64)
    kendi = gercek["kendi_satis"].to_numpy(dtype=np.int64)
    sayi = {"talepli": talep > 0, "bulunan": (talep > 0) & (kendi > 0), "talep": talep,
            "karsilanmayan": gercek["karsilanmayan"].to_numpy(dtype=np.int64)}
    n = len(gercek)
    bos, yok, hayir = np.full(n, ""), np.full(n, -1), np.zeros(n, dtype=bool)
    lansman_line = np.where(np.isin(etiket, ["NOS", "Basic", "Outlet"]), line, "Collection")
    yari_etiket = pd.Series(yari).map(YARILAR).to_numpy().astype(str)
    kesitler = {
        "lansman": dict(grup=etiket, line=lansman_line, yari=bos, beden=bos, pencerede=pencerede, hafta=yok),
        "line_yari": dict(grup=np.char.add(np.char.add(line, " · "), yari_etiket), line=line, yari=yari, beden=bos,
                          pencerede=hayir, hafta=yok),
        "line_beden": dict(grup=np.char.add(np.char.add(line, " · "), beden), line=line, yari=bos, beden=beden,
                           pencerede=hayir, hafta=yok),
        "hafta": dict(grup=np.char.add("hafta ", np.char.zfill((hafta + 1).astype(str), 2)), line=bos, yari=bos,
                      beden=bos, pencerede=hayir, hafta=hafta),
    }
    parca = []
    for kesit, alan in kesitler.items():
        df = pd.DataFrame({**alan, **sayi})
        t = df.groupby(["grup", "line", "yari", "beden", "pencerede", "hafta"], sort=True)[SAYILAR].sum().reset_index()
        parca.append(t.assign(kesit=kesit))
    sonuc = pd.concat(parca, ignore_index=True)
    sonuc[SAYILAR] = sonuc[SAYILAR].astype(np.int64)
    return sonuc[ALANLAR + SAYILAR].sort_values(["kesit", "grup"], ignore_index=True)


def oc_kirik(kosu, E: Eksen, tarih) -> tuple[np.ndarray, np.ndarray]:
    """(stoklu [OC], kırık [OC]): `tarih` sabahı fotoğrafında, `olcutler.kirik_ciftler`'in tanımıyla (sorumlu
    çift evreni; çiftin çeşidindeki çekirdek bedenlerden biri 0)."""
    from replenishment import olcutler

    st = _oku(kosu, "stok", ["tarih", "magaza_id", "urun_id", "adet"], tarih, tarih)
    stok_c = olcutler._stok_c(st, E.idx, E.C)
    evren = olcutler.cift_evreni(E.w, E.h, _ts(tarih))
    oc = E.h.oc
    cift = np.bincount(oc, evren, minlength=E.OC) > 0
    stoklu = cift & (np.bincount(oc, np.where(evren, stok_c, 0), minlength=E.OC) > 0)
    cekirdek = evren & np.isin(E.h.sku_beden[E.h.hucre_sku], olcutler.CEKIRDEK_BEDENLER)
    eksik = np.bincount(oc, cekirdek & (stok_c <= 0), minlength=E.OC) > 0
    return stoklu, stoklu & eksik


def kirik_tablosu(kosu, E: Eksen, ara, son) -> pd.DataFrame:
    """Kırık çift, teşhis gruplarına göre: `lansman` (son fotoğraf; yaş o güne göre) ve `line_yari` (ilk yarı
    `ara` fotoğrafı = hafta 9'un sonu, ikinci yarı `son` fotoğrafı). Sütunlar: kesit, grup, stoklu, kirik."""
    o = E.w.optionlar
    op = E.h.oc_option
    line = o["line"].to_numpy().astype(str)[op]
    parca = []
    for yari, tarih in (("ilk", ara), ("ikinci", son)):
        stoklu, kirik = oc_kirik(kosu, E, tarih)
        grup = np.char.add(np.char.add(line, " · "), YARILAR[yari])
        parca.append(pd.DataFrame({"kesit": "line_yari", "grup": grup, "stoklu": stoklu, "kirik": kirik}))
        if yari == "ikinci":
            etiket, _ = lansman_grubu(line, o["sezon_kodu"].to_numpy()[op], o["lansman_tarihi"].to_numpy()[op],
                                      np.full(len(op), _ts(tarih).to_datetime64()))
            parca.append(pd.DataFrame({"kesit": "lansman", "grup": etiket, "stoklu": stoklu, "kirik": kirik}))
    df = pd.concat(parca, ignore_index=True)
    return df.groupby(["kesit", "grup"], sort=True)[["stoklu", "kirik"]].sum().astype(np.int64).reset_index()


def grup_katkisi(a: pd.DataFrame, b: pd.DataFrame) -> pd.DataFrame:
    """Bulunabilirlik farkının (a − b, puan) gruplara ayrışımı: bulunabilirlik = Σ_g pay_g × bul_g
    (pay = grubun talepli hücre-gün payı) olduğu için katkı_g = pay^a_g bul^a_g − pay^b_g bul^b_g ve
    Σ katkı = toplam fark (iki kolun talepli hücre-günü az farklıdır; pay her kolun kendisinden).
    Girdi: tek kesitin `teshis_tablosu` satırları."""
    def oran(t):
        t = t.set_index("grup")
        pay = t["talepli"] / t["talepli"].sum()
        bul = t["bulunan"] / t["talepli"].where(t["talepli"] > 0)
        return pay, bul.fillna(0.0)

    pa, ba = oran(a)
    pb, bb = oran(b)
    gr = sorted(set(pa.index) | set(pb.index))
    pa, ba, pb, bb = (x.reindex(gr).fillna(0.0) for x in (pa, ba, pb, bb))
    sonuc = pd.DataFrame({"grup": gr, "pay_a": pa.to_numpy(), "bul_a": 100 * ba.to_numpy(), "pay_b": pb.to_numpy(),
                          "bul_b": 100 * bb.to_numpy(), "katki": 100 * (pa * ba - pb * bb).to_numpy()})
    alan = [c for c in ALANLAR if c not in ("kesit", "grup") and c in a.columns]
    if alan:
        ozn = pd.concat([a, b])[["grup"] + alan].drop_duplicates("grup")
        sonuc = sonuc.merge(ozn, on="grup", how="left")
    return sonuc


def ortalama_magaza_stogu(kosu, bas: date = OYUN_BAS, bit: date = OYUN_BIT) -> float:
    """Pencere pazartesilerinin (sabah fotoğrafı) fiziksel mağaza stoğu ortalaması."""
    st = _oku(kosu, "stok", ["tarih", "magaza_id", "adet"], bas, bit)
    st = st[(st["magaza_id"].astype(str) != ONLINE).to_numpy()]
    return float(st.groupby(st["tarih"].dt.normalize())["adet"].sum().mean())


def nb_depo(kosu, nb: set[str], bas: date = OYUN_BAS, bit: date = OYUN_BIT) -> pd.DataFrame:
    """NOS + Basic SKU'larının pazartesi depo stoğu: tarih, adet, bos_pay (stoğu 0 SKU payı)."""
    d = _oku(kosu, "depo_stok", ["tarih", "urun_id", "adet"], bas, bit)
    d = d[d["urun_id"].astype(str).isin(nb).to_numpy() & (d["tarih"].dt.weekday == 0).to_numpy()]
    g = d.groupby(d["tarih"].dt.normalize())
    return pd.DataFrame({"adet": g["adet"].sum(), "bos_pay": g["adet"].apply(lambda s: float((s <= 0).mean()))}
                        ).reset_index().rename(columns={"index": "tarih"})


# ---------------------------------------------------------------------------
# DEPO
# ---------------------------------------------------------------------------


def ilk_alim(kosu) -> pd.DataFrame:
    """AW25 sezonluk option'larının ilk alımı (siparis `ilk`), line başına: option sayısı, adet."""
    sp = _oku(kosu, "siparis", ["tip", "option_id", "urun_id", "adet"])
    sp = sp[(sp["tip"].astype(str) == "ilk").to_numpy()].astype({"urun_id": str, "option_id": str})
    u = _oku(kosu, "urun", ["urun_id", "line", "sezon_kodu"]).astype({"urun_id": str})
    sp = sp.merge(u, on="urun_id", how="left")
    sp = sp[(sp["sezon_kodu"] == "AW25").to_numpy()]
    return sp.groupby("line").agg(option=("option_id", "nunique"), adet=("adet", "sum")).reset_index()


def sezon_plani(E: Eksen, sezon: str = "AW25") -> pd.DataFrame:
    """Sezonun sezonluk option'larının sezon planı (dünyanın plan özeti: lansmandan indirime, iki kanal;
    alım düzeyinin uygulandığı talep tahmininin tabanı), line başına: option sayısı, plan adedi."""
    o = E.w.optionlar.reset_index(drop=True)
    top = np.asarray(E.w.plan_ozeti.gunluk).sum(axis=1)
    N, O = top.shape
    kum = np.vstack([np.zeros((1, O)), np.cumsum(top, axis=0)])
    i = np.arange(O)
    lans = np.clip(o["lansman_gun"].to_numpy(dtype=np.int64), 0, N)
    ind = np.clip(o["indirim_gun"].to_numpy(dtype=np.int64), 0, N)
    plan = kum[ind, i] - kum[lans, i]
    sec = o["sezonluk"].to_numpy(dtype=bool) & (o["sezon_kodu"] == sezon).to_numpy()
    df = pd.DataFrame({"line": o["line"].to_numpy()[sec], "plan": plan[sec]})
    return df.groupby("line").agg(option=("plan", "size"), plan=("plan", "sum")).reset_index()


def depo_son(kosu, bit: date = OYUN_BIT) -> pd.DataFrame:
    """Pencerenin son gününün depo stoğu, line başına: adet, SKU sayısı, stoğu 0 SKU sayısı."""
    d = _oku(kosu, "depo_stok", ["tarih", "urun_id", "adet"], bit, bit)
    u = _oku(kosu, "urun", ["urun_id", "line"])
    d = d.assign(line=d["urun_id"].astype(str).map(u.assign(urun_id=u["urun_id"].astype(str)).set_index("urun_id")["line"]))
    return d.groupby("line").agg(adet=("adet", "sum"), sku=("urun_id", "size"),
                                 bos=("adet", lambda s: int((s <= 0).sum()))).reset_index()


def stok_devri(kosu, bas, bit) -> int:
    """`(bas, bit]` aralığında depoya varan `stok_devri` sevki (adet)."""
    sv = _oku(kosu, "sevkiyat", ["varis_tarihi", "hedef", "adet", "tip"], _ts(bas) + pd.Timedelta(days=1), bit,
              sutun="varis_tarihi")
    m = (sv["tip"].astype(str) == "stok_devri").to_numpy() & (sv["hedef"].astype(str) == "DEPO").to_numpy()
    return int(sv["adet"].to_numpy()[m].sum())


# ---------------------------------------------------------------------------
# Yayımlanan dünya (VERİ, hikâye)
# ---------------------------------------------------------------------------


@dataclass
class Yayimlanan:
    magazalar: pd.DataFrame
    etkin_option: pd.DataFrame          # line, option sayısı
    repl: pd.DataFrame                  # line: adet, çift (mağaza–option), satır
    varis: pd.DataFrame                 # gün farkı → adet
    son7: dict                          # ilk pazartesiden önceki 7 gün: çift, adet
    ilk_dagitim: int                    # penceredeki ilk dağıtım adedi (fiziksel)
    nb_depo: pd.DataFrame               # NOS/Basic pazartesi depo stoğu
    paket: pd.DataFrame                 # paket_id, beden_seti, adet (koli içeriği)
    kal_ort: float                      # kalibrasyon penceresinde haftalık ortalama replenishment (tavanın girdisi)
    hikaye_depo: dict = field(default_factory=dict)


def yayimlanan_kur(sahne: dict | None) -> Yayimlanan:
    con = kaynak.baglan()
    try:
        bas, bit = OYUN_BAS, OYUN_BIT
        mag = kaynak.fiziksel_magazalar(con)
        etkin = kaynak.etkin_optionlar(con, bas, bit).groupby("line").size().rename("option").reset_index()
        repl = con.execute("""
            select u.line::varchar as line, sum(s.adet)::bigint as adet,
                   count(distinct s.hedef::varchar || '|' || u.option_id::varchar) as cift, count(*) as satir
            from sevkiyat s join urun u using (urun_id) join magaza m on m.magaza_id::varchar = s.hedef::varchar
            where s.tip::varchar = 'replenishment' and m.tip::varchar <> 'Online'
              and s.tarih::date between ? and ?
            group by 1 order by 1""", [bas, bit]).df()
        varis = con.execute("""
            select datediff('day', s.tarih::date, s.varis_tarihi::date)::int as gun, sum(s.adet)::bigint as adet
            from sevkiyat s join magaza m on m.magaza_id::varchar = s.hedef::varchar
            where s.tip::varchar = 'replenishment' and m.tip::varchar <> 'Online' and s.varis_tarihi is not null
              and s.tarih::date between ? and ?
            group by 1 order by 1""", [bas, bit]).df()
        ts = kaynak.ortak.temiz_satis(con)
        son7 = con.execute(f"""
            with h as (select s.magaza_id::varchar as m, u.option_id::varchar as o, sum(s.adet) as adet
                       from {ts} s join urun u using (urun_id)
                       where s.adet > 0 and s.magaza_id::varchar <> 'ONL'
                         and s.tarih::date between ? and ?
                       group by 1, 2)
            select count(*) as cift, sum(adet)::bigint as adet from h""",
                           [bas - timedelta(days=7), bas - timedelta(days=1)]).df().iloc[0]
        ilk = con.execute("""
            select coalesce(sum(s.adet), 0)::bigint from sevkiyat s join magaza m on m.magaza_id::varchar = s.hedef::varchar
            where s.tip::varchar = 'ilk_dagitim' and m.tip::varchar <> 'Online' and s.tarih::date between ? and ?""",
                          [bas, bit]).fetchone()[0]
        nb = con.execute("""
            select d.tarih::date as tarih, sum(d.adet)::bigint as adet, avg(case when d.adet <= 0 then 1 else 0 end) as bos_pay
            from depo_stok d join urun u using (urun_id)
            where u.line::varchar in ('NOS', 'Basic') and d.tarih::date between ? and ? and dayofweek(d.tarih) = 1
            group by 1 order by 1""", [bas, bit]).df()
        paket = con.execute("select paket_id::varchar as paket_id, beden_seti::varchar as beden_seti, "
                            "sum(adet)::int as adet, string_agg(adet::varchar, '-' order by beden_sira) as dagilim "
                            "from paket group by 1, 2 order by 1").df()
        from replenishment import kalibrasyon

        kal_n = kalibrasyon._pazartesi_sayisi(sabitler.KAL_BAS, sabitler.KAL_BIT)
        kal_ort = float(kaynak.haftalik_replenishment(con, sabitler.KAL_BAS, sabitler.KAL_BIT)["adet"].sum()) / kal_n
        y = Yayimlanan(magazalar=mag, etkin_option=etkin, repl=repl, varis=varis,
                       son7={"cift": int(son7["cift"]), "adet": int(son7["adet"])}, ilk_dagitim=int(ilk),
                       nb_depo=nb, paket=paket, kal_ort=kal_ort)
        if sahne:
            sku, oid = sahne["sku"], sahne["option_id"]
            p = _ts(sahne["pazartesi"])
            for etiket, gun in (("pazartesi", p), ("ertesi", p + pd.Timedelta(days=1))):
                r = con.execute("""
                    select coalesce(sum(case when d.urun_id::varchar = ? then d.adet end), 0)::bigint,
                           coalesce(sum(d.adet), 0)::bigint
                    from depo_stok d join urun u using (urun_id)
                    where u.option_id::varchar = ? and d.tarih::date = ?""", [sku, oid, gun.date()]).fetchone()
                y.hikaye_depo[etiket] = {"sku": int(r[0]), "option": int(r[1])}
            sv = con.execute("""
                select s.hedef::varchar as magaza_id, sum(s.adet)::bigint as adet from sevkiyat s
                where s.tip::varchar = 'replenishment' and s.urun_id::varchar = ? and s.tarih::date = ?
                group by 1 order by 1""", [sku, p.date()]).df()
            y.hikaye_depo["sevk"] = dict(zip(sv["magaza_id"], sv["adet"].astype(int)))
    finally:
        con.close()
    return y


# ---------------------------------------------------------------------------
# Hepsi
# ---------------------------------------------------------------------------


@dataclass
class Veri:
    oyun: dict
    yollar: dict
    kal: dict
    hikaye: dict
    esitlik: dict
    yayimlanan: Yayimlanan
    satistaki: dict                     # pazartesi → satıştaki fiziksel çift (alım 1,0 dünyası)
    katsayilar: dict
    hedef: dict                         # koşu adı → HedefSonucu
    ilk: IlkPazartesi
    teshis: dict                        # koşu adı → teshis_tablosu
    kirik: dict                         # koşu adı → kirik_tablosu
    ort_stok: dict                      # koşu adı → ortalama mağaza stoğu
    nb_depo: dict                       # koşu adı → nb_depo
    ilk_alim: dict                      # alım düzeyi → ilk_alim tablosu
    plan: pd.DataFrame                  # AW25 sezonluk option'larının sezon planı (line)
    defter_bas: dict                    # alım düzeyi → ilk pazartesi defter kalemleri
    depo_son: dict                      # koşu adı → depo_son
    uzl: pd.DataFrame                   # kural_ref'in pazartesi uzlaştırma kalemleri
    stok_devri: dict                    # (önceki, pazartesi) → stok devri girişi, kural_ref
    demo: dict                          # senaryolar.uret() çıktısı
    olcum_kodu: str
    yollar_kodu: str
    acilan: list
    yol_kosulari: int
    tahmin_parametreleri: dict
    tahmin_ozet: dict                   # cikti/tahmin/yol0_ozet.json (eğitim ve doğrulama özeti)
    bf_haftasi: int                     # Black Friday'in pencere haftası (0'dan; takvimden)


def hazirla(cikti: Path = CIKTI) -> Veri:
    """Bütün girdiler (önbellekten; motor koşmaz). Eksik ya da geçersiz koşu `RuntimeError`."""
    import senaryolar

    oy = _json(Path(cikti) / "oyun.json")
    yl = _json(Path(cikti) / "yollar.json")
    kal = _json(Path(cikti) / "kalibrasyon.json")
    hk = _json(Path(cikti) / "hikaye.json")
    es = _json(Path(cikti) / "esitlik.json")
    ob = Onbellek(oy["kosular"])
    # yol 0 kayıtları oyun.json'la aynı koşu (yollar yol 0'da ızgaranın anahtarını kullanır)
    E = eksen_kur()
    satistaki = {p: int(E.satistaki_ciftler(p).sum()) for p in pazartesiler()}

    ref = ob.ac("kural_ref")
    katsayilar = ozel_gun_katsayilari(ref, E)
    hedef = {}
    for ad in HEDEF_KOSULARI:
        k = ref if ad == "kural_ref" else ob.ac(ad)
        g = k.meta["politikalar"]["replenishment"]["parametreler"]["ayar"]["gs"]
        hedef[ad] = hedef_yeniden_kur(k, E, katsayilar, ihtiyac.GuvenlikStoku(g["aile"], float(g["deger"])))
        del k
    kayit_ilk = {}
    tahminci_kimlik = None
    for ad in ("tahmin_ref", "tahmin_taban_ref"):
        k = ob.ac(ad)
        kayit_ilk[ad] = float(politika.hafta_tablosu(k)["hedef_adet"].iloc[0])
        tk = k.meta["politikalar"]["replenishment"]["parametreler"]["tahminci"]
        if tahminci_kimlik not in (None, tk):
            raise RuntimeError("tahmin kollarının tahmincisi farklı")
        tahminci_kimlik = tk
        del k
    gs_ref = ref.meta["politikalar"]["replenishment"]["parametreler"]["ayar"]["gs"]
    ilk = ilk_pazartesi_lgbm(ref, E, katsayilar, ihtiyac.GuvenlikStoku(gs_ref["aile"], float(gs_ref["deger"])),
                             Path(cikti) / "tahmin" / "yol0.json", kayit_ilk["tahmin_ref"], kayit_ilk["tahmin_taban_ref"])
    if ilk.tahminci != tahminci_kimlik:
        raise RuntimeError("cikti/tahmin/yol0.json'un kimliği tahmin koşularınınkinden farklı")
    tozet = _json(Path(cikti) / "tahmin" / "yol0_ozet.json")
    if tozet.get("kimlik") != tahminci_kimlik:
        raise RuntimeError("cikti/tahmin/yol0_ozet.json başka bir tahminciye ait")

    gruplar = urun_gruplari(_oku(ref, "urun", ["urun_id", "option_id", "line", "sezon_kodu", "dalga", "lansman_tarihi",
                                               "beden_seti", "beden_sira"]))
    nb = set(gruplar.index[gruplar["line"].isin(["NOS", "Basic"]).to_numpy()])
    teshis, kirik, ort_stok, nbd = {}, {}, {}, {}
    pz = pazartesiler()
    ara_foto, son_foto = pz[9], pz[-1]          # hafta 9'un sonu (10. pazartesi sabahı) ve son fotoğraf
    for ad in TESHIS_KOLLARI:
        k = ob.ac(ad, kayit=False)
        g = _oku(k, "gercek", ["tarih", "magaza_id", "urun_id", "talep", "kendi_satis", "karsilanmayan"], OYUN_BAS, OYUN_BIT)
        g = g[(g["magaza_id"].astype(str) != ONLINE).to_numpy()].reset_index(drop=True)
        teshis[ad] = teshis_tablosu(g, gruplar)
        del g
        kirik[ad] = kirik_tablosu(k, E, ara_foto, son_foto)
        if ad in ("lumoda_kisitsiz",) + SINIR_KOLLARI:
            ort_stok[ad] = ortalama_magaza_stogu(k)
            nbd[ad] = nb_depo(k, nb)

    ilk_alim_t, defter_bas = {}, {}
    for alim, ad in ALIM_KOSULARI.items():
        k = ref if ad == "kural_ref" else ob.ac(ad)
        ilk_alim_t[alim] = ilk_alim(k)
        h0 = politika.hafta_tablosu(k).iloc[0]
        defter_bas[alim] = {a: float(h0[a]) for a in ("uzl_kapali_koli", "uzl_kapali_adet", "uzl_acik_adet")}
    depo_s = {ad: depo_son(ref if ad == "kural_ref" else ob.ac(ad, kayit=False))
              for ad in ("kural_ref", "kural_a040_oncelik_cover", "lumoda_ref")}
    uzl = politika.hafta_tablosu(ref)
    pzt = [_ts(t) for t in uzl["tarih"]]
    devir = {(a, b): stok_devri(ref, a, b) for a, b in zip(pzt[:-1], pzt[1:])}

    # yolların koşuları (yol p > 0 `y<p>_` önekli): önbellekte ve bugünkü kodla olmalı
    yol_kayit = {(kol if int(p) == 0 else f"y{p}_{kol}"): {"anahtar": e["anahtar"]}
                 for p, yv in yl["yollar"].items() for kol, e in yv["kosular"].items()}
    ob_yol = Onbellek(yol_kayit, guncel=ob.guncel)
    for ad in sorted(yol_kayit):
        ob_yol.ac(ad, kayit=False)

    demo = senaryolar.uret(oy, onbellek=ob.dizin)
    yay = yayimlanan_kur(hk.get("sahne"))
    return Veri(oyun=oy, yollar=yl, kal=kal, hikaye=hk, esitlik=es, yayimlanan=yay, satistaki=satistaki,
                katsayilar=katsayilar, hedef=hedef, ilk=ilk, teshis=teshis, kirik=kirik, ort_stok=ort_stok, nb_depo=nbd,
                ilk_alim=ilk_alim_t, plan=sezon_plani(E), defter_bas=defter_bas, depo_son=depo_s, uzl=uzl, stok_devri=devir, demo=demo,
                olcum_kodu=oyun.olcum_kodu(_kal_nesnesi(kal), oyun.Ortam()), yollar_kodu=yollar_modulu.kod_ozeti(),
                acilan=sorted(ob.acilan | ob_yol.acilan), yol_kosulari=len(yol_kayit), tahmin_parametreleri=dict(tahmin.PARAMETRELER), tahmin_ozet=tozet, bf_haftasi=bf_haftasi(E))


def bf_haftasi(E: Eksen) -> int:
    """Pencere içindeki Black Friday gününün hafta indisi (hafta 0 = ilk karar pazartesisinden 7 gün)."""
    t = E.w.takvim
    tarih = pd.to_datetime(t["tarih"]).dt.normalize()
    m = t["black_friday_mi"].to_numpy(dtype=bool) & ((tarih >= _ts(OYUN_BAS)) & (tarih <= _ts(OYUN_BIT))).to_numpy()
    gunler = tarih[m]
    if len(gunler) != 1:
        raise RuntimeError(f"pencerede tek Black Friday günü beklenirdi: {len(gunler)}")
    return int((gunler.iloc[0] - _ts(OYUN_BAS)).days // 7)


def _kal_nesnesi(kal: dict):
    from replenishment import kalibrasyon

    return kalibrasyon.sozlukten(kal)
