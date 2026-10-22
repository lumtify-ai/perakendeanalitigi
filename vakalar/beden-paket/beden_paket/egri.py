"""Mağaza beden eğrisi: ham pay, sansür düzeltmesi, daraltma, profil, zincir, yeni mağaza.

Kural: bu bir karar modülüdür; yalnız yayımlanan satış ve stoktan (ve ürün, mağaza tablolarından)
okur. Gizli gerçeğe (`perakende_veri`, gizli mağaza tablosu, beden kayması) ve ölçüm modüllerine
(hakem, ölçütler) dokunmaz; yayımlanan sevkiyat tablosunu da okumaz (spec §0/13: replenishment
sevkiyatının beden karışımı Lumoda'nın, gizli gerçeği bilen planını taşır). AST kilidi
`tests/test_sizinti.py`; çalışma zamanı denetimi `tests/test_egri.py`.

**Pencereler** (`option_pencereleri`). Geçmiş penceresi karar gününden önceki son
`GECMIS_PENCERE_HAFTA` (104) tamamlanmış pazartesi-pazar haftasıdır, `[bas0, bit0)`, `bit0` karar
gününün haftasının pazartesisi (Kümeleme `ozellikler.pencere` ile aynı). Beş bedenli (`kaynak.
bes_bedenli`) ve `HATLAR`'daki her option'ın penceresi bunun içindedir:

    Collection   option'ın lansman haftasından `EGRI_PENCERE_HAFTA` (8) hafta (ilk dağıtımın
                 hizmet ettiği ilk haftalar)
    Basic, NOS   bütün geçmiş penceresi (sürekli ürün; "lansman sonrası ilk haftalar" yoktur:
                 bu option'ların lansmanı geçmiş penceresinden öncedir)

Satış haftası satış gününün pazartesisidir; pazartesi `d` stok fotoğrafı önceki yedi günü anlatır
(`stoklu_gun`, v4 README), yani `d − 7` haftasına aittir. Brüt satış (`adet > 0`) okunur. Bir
hücre (mağaza × option × beden) yalnız option'ın penceresindeki haftalarla sayılır. Tablolarda
karar gününden sonraki satır olsa da okunmaz (tarih < karar günü süzgeci; sızıntı testi).

**Ham pay** (`ham`). Mağazanın penceredeki brüt satışının beden sırasına (1..5) göre payı, bütün
option'lar birlikte (Collection ve Basic/NOS tek havuz; `hatlar` ile ayrılabilir, rapor ayrımı
basar). Örneklem `n` (`orneklem`): aynı satışın adedi.

**Sansür düzeltmesi** (`duzeltilmis`; İlk Sevkiyat `ogrenme`'nin stoklu gün hızı, Ruling R3
mantığı). Hücre başına penceredeki satış `s`, stoklu gün `f`, ve option'ın o mağazadaki gözlem
uzunluğu `L` (= 7 × option'ın herhangi bir bedeninde stok fotoğrafı olan pencere haftası sayısı;
bütün bedenlerde aynı). Hücre talebi (`hucre_talebi`):

    f >= 3       talep = s / f × L
    f = 1, 2     talep = s                  (oran çok az günden: olduğu gibi)
    f = 0        zincir hızıyla doldurulur: talep_b = T × z_b / Σ_{gözlenen b'} z_b'
                 (T: aynı mağaza × option'ın gözlenen bedenlerinin talebi; z: zincir eğrisi)

Mağaza × option'da hiçbir beden gözlenmediyse (stok fotoğrafı yok ya da hep sıfır) o option
düşer. Düzeltilmiş pay mağazanın bedenlere göre toplam talebinin payıdır. Bütün bedenleri bir
option'da hiç stoklanmamış bir mağazanın düzeltilmiş payı, o bedende zincir payını alır.

**Zincir** (`zincir`). Fiziksel, outlet olmayan bütün mağazaların (yayımlanan `magaza` tablosu;
kapsamdan bağımsız) aynı pencerelerdeki havuzlanmış ham satış payı. Ham alınır (düzeltmenin
doldurma eğrisi olduğu için döngüsel olmasın diye).

**Profil** (`profiller`). Mağaza eğrilerinin k-means kümeleri (`kumeleme.ogren.kume`, kmeans,
tohum `sabitler.TOHUM`; girdi beden payları olduğu gibi: beş sütun aynı ölçekte, standartlama
payların arasındaki farkı bozardı). Kümeler eğrilerinin ortalama beden sırasına (Σ b·p_b) göre
sıralanır; k = 3'te adlar `kucuk`, `orta`, `buyuk` (`PROFIL_ADLARI`), başka k'da `P1`..`Pk`.
Profil eğrisi (`profil_egrileri`) üye mağazaların düzeltilmiş eğrilerinin ortalamasıdır.
Profiller yalnız kapsamın yeni olmayan mağazalarıyla kurulur (`kaynak.kapsam`, `yeni`).

**Daraltma** (`daralt`). Mağazanın düzeltilmiş eğrisi öncüle çekilir: ağırlık w = n / (n + κ),
eğri = w × kendi + (1 − w) × öncül (satır bire yeniden ölçeklenir). n = 0'da eğri öncüldür.
Öncül: yeni olmayan mağazada kendi profilinin eğrisi; yeni mağazada aşağıdaki kuralın seçtiği
eğri (statikle atanmış profilin eğrisi ya da zincir).

**κ seçimi** (`kappa_sec`; hakemsiz, kural sonuç görülmeden yazıldı). Izgara `KAPPA_IZGARASI`
(adet). Kalibrasyon sezonunun karar gününde (`KAL_KARAR_GUNU`) bütün yöntem o güne kadarki
veriyle kurulur (kapsam, pencereler, zincir, profiller, yeni mağaza kuralı o güne göre); her κ
için daraltılmış eğrinin, o sezonun Collection option'larının gerçekleşen ilk
`EGRI_PENCERE_HAFTA` haftasının düzeltilmiş payına (`gerceklesen_pay`; yayımlanan veri, hakem
değil; stoksuz beden hedefin kendi havuz payıyla doldurulur) L1 uzaklığının kapsam mağazaları üzerinde ortalaması alınır. En küçük ortalama seçilir;
eşitlikte küçük κ. Hedef pencerelerin hepsi oyun karar gününün geçmiş penceresi içinde bitmelidir
(yoksa hata): κ oyun karar anında bilinen veriyle seçilir.

**Yeni mağaza** (spec §0/10; kural sonuç görülmeden yazıldı). Kapsamın yeni mağazasının
(Kümeleme eşiği: 26 haftadan az satışlı geçmiş) öncülü iki adaydan biridir: statik özelliklerle
atanmış profilin eğrisi (`kumeleme.yeni_magaza.ata`, 5 komşu, Kümeleme R10 kalıbı) ya da zincir
eğrisi. Seçim bırakbirle, hakemsiz: yeni olmayan her mağaza "yeniymiş gibi" profiller onsuz
yeniden kurulur, mağaza yalnız statikleriyle o profillerden birine atanır; atanan profilin eğrisi
ile zincirin, mağazanın kendi düzeltilmiş eğrisine L1 uzaklıkları ortalanır. Profilin ortalaması
zincirinkinden küçükse `profil`, değilse `zincir` (`Egri.yeni_secim`; atama isabeti de basılır:
bırakbir profilinin, ada göre, mağazanın tam profiliyle aynı olma oranı). Yeni mağazanın kendi
kısa geçmişi atılmaz: daraltma onu n ağırlığıyla öncüle katar (n = 0'da eğri öncüldür).
`Egri.kaynak` mağaza → `magaza` (yeni olmayan) ya da öncülün kaynağı (`profil` / `zincir`).
Yeni mağazanın `Egri.profil`'i son eğrisine L1'de en yakın profil eğrisidir; statik ataması
`Egri.yeni_atama`'da.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from kumeleme import kaynak as kumeleme_kaynak
from kumeleme import ogren, ozellikler, yeni_magaza

from beden_paket import kaynak, sabitler

SUTUNLAR = [f"b{i}" for i in range(1, sabitler.BEDEN_SAYISI + 1)]
_SIRA = np.arange(1, sabitler.BEDEN_SAYISI + 1, dtype="float64")
HATLAR = ("Collection", "Basic", "NOS")
SEZONLUK = "Collection"
FIZIKSEL_DISI = ("Online", "Outlet")
EN_AZ_STOKLU_GUN = 3
KAPPA_IZGARASI = (0, 25, 50, 100, 200, 400, 800, 1600, 3200, 6400, 12800)
PROFIL_ADLARI = ("kucuk", "orta", "buyuk")
KOMSU = yeni_magaza.KOMSU
_HAFTA = pd.Timedelta(weeks=1)


@dataclass(frozen=True)
class Egri:
    """Karar anındaki beden eğrileri (satır `magaza_id`, kapsam sırası; sütun `SUTUNLAR`)."""
    magaza: pd.DataFrame            # son eğri (daraltılmış); satırlar bire toplanır
    profil: pd.Series               # mağaza → profil adı
    zincir: np.ndarray              # [5] zincir eğrisi
    kaynak: dict                    # mağaza → "magaza" | "profil" | "zincir"
    kappa: float = 0.0
    n: pd.Series = field(default_factory=lambda: pd.Series(dtype="float64"))   # örneklem (adet)
    duzeltilmis: pd.DataFrame | None = None       # daraltma öncesi (yeni mağazada NaN olabilir)
    profil_egrisi: pd.DataFrame | None = None     # profil → eğri
    yeni_atama: dict = field(default_factory=dict)            # yeni mağaza → statik profil
    yeni_secim: dict = field(default_factory=dict)            # yeni mağaza kuralının ölçümü
    kappa_tablosu: pd.DataFrame | None = None


# ---------------------------------------------------------------------------
# Yükleme
# ---------------------------------------------------------------------------


def egri_tablolari(con, karar_gunu) -> dict[str, pd.DataFrame]:
    """Eğrinin okuduğu tablolar: `magaza`, `magaza_olay`, `urun` ve karar gününden önceki beş
    bedenli SKU'ların haftalık brüt satışı (`tarih` = haftanın pazartesisi; 18 milyon satırlık
    günlük satış bellekte tutulmaz) ile stok fotoğrafları. Haftalık satış `kaynak.kapsam`'a da
    girdi olabilir (tamamlanmış satışlı hafta tanımı aynı)."""
    karar = pd.Timestamp(karar_gunu).normalize()
    t = kaynak.yayimlanan_tablolar(con, ("magaza", "magaza_olay", "urun"))
    sku = pd.DataFrame({"urun_id": kaynak.bes_bedenli(t["urun"])["urun_id"].astype(str).unique()})
    con.register("_bes_bedenli", sku)
    try:
        t["satis"] = con.execute(
            "select date_trunc('week', s.tarih)::timestamp as tarih, s.magaza_id::varchar as magaza_id, "
            "s.urun_id::varchar as urun_id, sum(s.adet)::bigint as adet from satis s "
            "join _bes_bedenli b on s.urun_id::varchar = b.urun_id "
            "where s.adet > 0 and s.tarih < ? group by all order by 1, 2, 3", [karar]).df()
        t["stok"] = con.execute(
            "select s.tarih::timestamp as tarih, s.magaza_id::varchar as magaza_id, "
            "s.urun_id::varchar as urun_id, s.adet, s.stoklu_gun from stok s "
            "join _bes_bedenli b on s.urun_id::varchar = b.urun_id "
            "where s.tarih < ? order by 1, 2, 3", [karar]).df()
    finally:
        con.unregister("_bes_bedenli")
    for ad in ("satis", "stok"):
        for s in ("magaza_id", "urun_id"):
            t[ad][s] = t[ad][s].astype("category")
    return t


# ---------------------------------------------------------------------------
# Pencereler ve hücreler
# ---------------------------------------------------------------------------


def _pazartesi(t: pd.Series) -> pd.Series:
    g = pd.to_datetime(t).dt.normalize()
    return g - pd.to_timedelta(g.dt.weekday, unit="D")


def option_pencereleri(urunler: pd.DataFrame, karar_gunu, hatlar=HATLAR) -> pd.DataFrame:
    """Option → `[bas, bit)` (modül notu). Sütunlar `option_id, line, bas, bit`; option sırasıyla.
    Penceresi boş (lansmanı karar haftasında ya da sonra) option düşer."""
    bas0, bit0 = ozellikler.pencere(karar_gunu, sabitler.GECMIS_PENCERE_HAFTA)
    u = kaynak.bes_bedenli(urunler)
    u = u[u["line"].astype(str).isin(hatlar)]
    o = (u.assign(option_id=u["option_id"].astype(str), line=u["line"].astype(str))
         .groupby("option_id", sort=True).agg(line=("line", "first"), lansman=("lansman_tarihi", "min"))
         .reset_index())
    lh = _pazartesi(o["lansman"])
    sezonluk = (o["line"] == SEZONLUK).to_numpy()
    o["bas"] = lh.where(lh > bas0, bas0)
    son = (lh + sabitler.EGRI_PENCERE_HAFTA * _HAFTA).where(sezonluk, bit0)
    o["bit"] = son.where(son < bit0, bit0)
    o = o[o["bas"] < o["bit"]]
    return o[["option_id", "line", "bas", "bit"]].reset_index(drop=True)


def _kodla(sutun: pd.Series, dizin: pd.Index) -> np.ndarray:
    """Sütun değerlerinin `dizin`deki konumu (yoksa −1); kategorik sütunda kategori düzeyinde."""
    if isinstance(sutun.dtype, pd.CategoricalDtype):
        kod = dizin.get_indexer(sutun.cat.categories.astype(str))
        c = sutun.cat.codes.to_numpy()
        return np.where(c >= 0, kod[c], -1)
    return dizin.get_indexer(sutun.astype(str))


def _pazartesi_gun(tarih) -> np.ndarray:
    """Tarihlerin haftasının pazartesisi, gün sayısı (1970-01-01 = 0; o gün perşembe)."""
    g = pd.to_datetime(tarih).to_numpy().astype("datetime64[D]").astype("int64")
    return g - (g + 3) % 7


def _hucreler(tablolar, magazalar, pencereler: pd.DataFrame, karar_gunu) -> pd.DataFrame:
    """(magaza_id, option_id, beden_sira) → s, f, L (modül notu). Gözlemli (stok fotoğrafı ya da
    satışı olan) her mağaza × option'da beş bedenin hepsi satırdır; satırlar mağaza (`magazalar`
    sırası), option (`pencereler` sırası), beden sırasıyla."""
    karar = pd.Timestamp(karar_gunu).normalize()
    if (pencereler["bit"] > karar).any():
        raise ValueError("pencere karar gününden sonra bitiyor")
    B = sabitler.BEDEN_SAYISI
    opt = pd.Index(pencereler["option_id"].astype(str))
    o_bas = _pazartesi_gun(pencereler["bas"])
    o_bit = _pazartesi_gun(pencereler["bit"])
    u = kaynak.bes_bedenli(tablolar["urun"])
    u_opt = opt.get_indexer(u["option_id"].astype(str))
    u = u[u_opt >= 0]
    sku = pd.Index(u["urun_id"].astype(str))
    sku_opt = opt.get_indexer(u["option_id"].astype(str))
    sku_b = u["beden_sira"].to_numpy(dtype="int64") - 1
    mag = pd.Index([str(m) for m in magazalar])
    M, O = len(mag), len(opt)
    karar_gun = np.datetime64(karar.date(), "D").astype("int64")

    def _oku(tablo: pd.DataFrame, deger: str, kaydir: int):
        tarih = pd.to_datetime(tablo["tarih"]).to_numpy().astype("datetime64[D]").astype("int64")
        mi = _kodla(tablo["magaza_id"], mag)
        si = _kodla(tablo["urun_id"], sku)
        v = tablo[deger].to_numpy(dtype="float64")
        tut = (tarih < karar_gun) & (mi >= 0) & (si >= 0)
        mi, si, v, tarih = mi[tut], si[tut], v[tut], tarih[tut]
        hafta = tarih - (tarih + 3) % 7 - kaydir
        oi = sku_opt[si]
        tut = (hafta >= o_bas[oi]) & (hafta < o_bit[oi])
        return mi[tut], oi[tut], sku_b[si[tut]], hafta[tut], v[tut]

    sm, so, sb, _, sv = _oku(tablolar["satis"], "adet", 0)
    pos = sv > 0
    sm, so, sb, sv = sm[pos], so[pos], sb[pos], sv[pos]
    fm, fo, fb, fh, fv = _oku(tablolar["stok"], "stoklu_gun", 7)
    n = M * O * B
    S = np.bincount((sm * O + so) * B + sb, weights=sv, minlength=n)
    F = np.bincount((fm * O + fo) * B + fb, weights=fv, minlength=n)
    W = int(fh.max() - fh.min() + 1) if len(fh) else 1
    cift_hafta = np.unique((fm * O + fo) * W + (fh - (fh.min() if len(fh) else 0))) // W
    L = np.bincount(cift_hafta, minlength=M * O) * 7.0
    var = np.zeros(M * O, dtype=bool)
    var[sm * O + so] = True
    var[fm * O + fo] = True
    cift = np.flatnonzero(var)
    hucre = (cift[:, None] * B + np.arange(B)).ravel()
    return pd.DataFrame({"magaza_id": mag.to_numpy()[hucre // (O * B)],
                         "option_id": opt.to_numpy()[(hucre // B) % O],
                         "beden_sira": hucre % B + 1,
                         "s": S[hucre], "f": F[hucre], "L": np.repeat(L[cift], B)})


def hucre_talebi(hucre: pd.DataFrame, zincir_egrisi) -> np.ndarray:
    """Hücre başına sansür düzeltmeli talep (modül notu); `hucre` satır sırasıyla. Hiçbir bedeni
    gözlenmeyen mağaza × option'ın hücreleri NaN."""
    z = np.asarray(zincir_egrisi, dtype="float64")
    s = hucre["s"].to_numpy(dtype="float64")
    f = hucre["f"].to_numpy(dtype="float64")
    L = hucre["L"].to_numpy(dtype="float64")
    gozlem = f > 0
    talep = np.where(f >= EN_AZ_STOKLU_GUN, np.divide(s * L, f, out=np.zeros_like(s), where=f > 0), s)
    talep = np.where(gozlem, talep, 0.0)
    zb = z[hucre["beden_sira"].to_numpy(dtype=int) - 1]
    grup = pd.MultiIndex.from_arrays([hucre["magaza_id"].to_numpy(), hucre["option_id"].to_numpy()])
    kod, _ = pd.factorize(grup)
    T = np.bincount(kod, weights=talep)
    Z = np.bincount(kod, weights=np.where(gozlem, zb, 0.0))
    var = Z[kod] > 0
    dolu = np.divide(T[kod] * zb, Z[kod], out=np.zeros_like(s), where=var)
    return np.where(~var, np.nan, np.where(gozlem, talep, dolu))


def _paya(hucre: pd.DataFrame, deger: np.ndarray, ids: list[str]) -> pd.DataFrame:
    d = pd.DataFrame({"magaza_id": hucre["magaza_id"].to_numpy(), "beden_sira": hucre["beden_sira"].to_numpy(),
                      "v": deger})
    d = d[~np.isnan(d["v"].to_numpy())]
    P = (d.pivot_table(index="magaza_id", columns="beden_sira", values="v", aggfunc="sum")
         .reindex(index=ids, columns=range(1, sabitler.BEDEN_SAYISI + 1)).fillna(0.0))
    toplam = P.sum(axis=1)
    P = P.div(toplam.where(toplam > 0), axis=0)
    P.columns = SUTUNLAR
    P.index = pd.Index(ids, name="magaza_id")
    return P.astype("float64")


def _ids(kapsam) -> list[str]:
    if isinstance(kapsam, pd.DataFrame):
        return kapsam["magaza_id"].astype(str).tolist()
    return [str(m) for m in kapsam]


def _fiziksel(magaza: pd.DataFrame) -> list[str]:
    return magaza.loc[~magaza["tip"].astype(str).isin(FIZIKSEL_DISI), "magaza_id"].astype(str).tolist()


# ---------------------------------------------------------------------------
# Ham, düzeltilmiş, zincir, örneklem
# ---------------------------------------------------------------------------


def zincir(tablolar, karar_gunu, hatlar=HATLAR) -> np.ndarray:
    """Zincir eğrisi [5]: fiziksel, outlet olmayan mağazaların havuzlanmış ham satış payı."""
    pen = option_pencereleri(tablolar["urun"], karar_gunu, hatlar)
    return _havuz(_hucreler(tablolar, _fiziksel(tablolar["magaza"]), pen, karar_gunu))


def _havuz(h: pd.DataFrame) -> np.ndarray:
    v = h.groupby("beden_sira")["s"].sum().reindex(range(1, sabitler.BEDEN_SAYISI + 1), fill_value=0.0)
    if v.sum() <= 0:
        raise ValueError("havuz eğrisi için penceredeki satış yok")
    return (v / v.sum()).to_numpy(dtype="float64")


def ham(tablolar, kapsam, karar_gunu, hatlar=HATLAR) -> pd.DataFrame:
    """Mağaza × beden ham satış payı (kapsam sırası; satışsız mağaza NaN)."""
    ids = _ids(kapsam)
    h = _hucreler(tablolar, ids, option_pencereleri(tablolar["urun"], karar_gunu, hatlar), karar_gunu)
    return _paya(h, h["s"].to_numpy(dtype="float64"), ids)


def orneklem(tablolar, kapsam, karar_gunu, hatlar=HATLAR) -> pd.Series:
    """Mağaza → penceredeki brüt satış adedi (daraltmanın n'i), kapsam sırası."""
    ids = _ids(kapsam)
    h = _hucreler(tablolar, ids, option_pencereleri(tablolar["urun"], karar_gunu, hatlar), karar_gunu)
    return h.groupby("magaza_id")["s"].sum().reindex(ids, fill_value=0.0).rename("n").astype("float64")


def duzeltilmis(tablolar, kapsam, karar_gunu, hatlar=HATLAR, zincir_egrisi=None) -> pd.DataFrame:
    """Mağaza × beden sansür düzeltmeli pay (modül notu; kapsam sırası; gözlemsiz mağaza NaN)."""
    ids = _ids(kapsam)
    z = zincir(tablolar, karar_gunu, hatlar) if zincir_egrisi is None else np.asarray(zincir_egrisi)
    h = _hucreler(tablolar, ids, option_pencereleri(tablolar["urun"], karar_gunu, hatlar), karar_gunu)
    return _paya(h, hucre_talebi(h, z), ids)


# ---------------------------------------------------------------------------
# Daraltma, profil
# ---------------------------------------------------------------------------


def daralt(egri: pd.DataFrame, n: pd.Series, oncul, *, kappa: float) -> pd.DataFrame:
    """w = n / (n + κ) ağırlıkla `egri` ve `oncul` karışımı (modül notu); n = 0 ya da eğri NaN ise
    öncül. `oncul`: [5] dizi (her mağazaya aynı) ya da `egri` satırlarını kapsayan tablo."""
    if kappa < 0:
        raise ValueError(f"κ negatif: {kappa}")
    E = egri[SUTUNLAR].astype("float64")
    nn = n.reindex(E.index).astype("float64")
    if nn.isna().any():
        raise KeyError(f"n'i olmayan mağaza: {list(nn.index[nn.isna()])}")
    if isinstance(oncul, pd.DataFrame):
        O = oncul[SUTUNLAR].reindex(E.index).astype("float64").to_numpy()
    else:
        O = np.broadcast_to(np.asarray(oncul, dtype="float64"), E.shape)
    if np.isnan(O).any():
        raise ValueError("öncülde NaN var")
    bos = E.isna().any(axis=1).to_numpy() | (nn.to_numpy() <= 0)
    payda = nn.to_numpy() + kappa
    w = np.divide(nn.to_numpy(), payda, out=np.zeros(len(nn)), where=payda > 0)
    w = np.where(bos, 0.0, w)[:, None]
    X = w * np.nan_to_num(E.to_numpy()) + (1 - w) * O
    X = X / X.sum(axis=1, keepdims=True)
    return pd.DataFrame(X, index=E.index, columns=SUTUNLAR)


def ortalama_beden(egri: pd.DataFrame) -> pd.Series:
    """Mağaza → ortalama beden sırası Σ b·p_b."""
    return pd.Series(egri[SUTUNLAR].to_numpy(dtype="float64") @ _SIRA, index=egri.index)


def profil_adlari(k: int) -> tuple[str, ...]:
    return PROFIL_ADLARI if k == len(PROFIL_ADLARI) else tuple(f"P{i}" for i in range(1, k + 1))


def profiller(egri: pd.DataFrame, k: int = 3, tohum: int = sabitler.TOHUM) -> pd.Series:
    """Mağaza → profil adı (modül notu), `egri` satır sırasıyla. Etiket, kümenin ortalama eğrisinin
    ortalama beden sırasına göre (küçükten büyüğe)."""
    E = egri[SUTUNLAR].astype("float64")
    e = ogren.kume(E, "kmeans", k, tohum=tohum)
    ort = ortalama_beden(E.groupby(e.to_numpy()).mean())
    sira = list(ort.sort_values(kind="stable").index)
    adlar = profil_adlari(k)
    harita = {g: adlar[i] for i, g in enumerate(sira)}
    return pd.Series([harita[g] for g in e.to_numpy()], index=pd.Index(E.index.astype(str), name="magaza_id"),
                     name="profil")


def profil_egrileri(egri: pd.DataFrame, profil: pd.Series) -> pd.DataFrame:
    """Profil → üye eğrilerinin ortalaması (satır bire ölçekli), ortalama beden sırasıyla."""
    E = egri[SUTUNLAR].loc[profil.index].astype("float64")
    P = E.groupby(profil.to_numpy()).mean()
    P = P.div(P.sum(axis=1), axis=0)
    P = P.loc[ortalama_beden(P).sort_values(kind="stable").index]
    P.index.name = "profil"
    return P


def _en_yakin_profil(egri: pd.DataFrame, P: pd.DataFrame) -> pd.Series:
    d = np.abs(egri[SUTUNLAR].to_numpy()[:, None, :] - P[SUTUNLAR].to_numpy()[None, :, :]).sum(axis=2)
    return pd.Series(P.index.to_numpy()[np.argmin(np.round(d, 12), axis=1)], index=egri.index)


# ---------------------------------------------------------------------------
# Yeni mağaza
# ---------------------------------------------------------------------------


def _statik(kapsam: pd.DataFrame) -> pd.DataFrame:
    k = kapsam.copy()
    k["metropol"] = k["sehir"].astype(str).isin(kumeleme_kaynak.METROPOL)
    return k


def yeni_secim(kapsam: pd.DataFrame, duz: pd.DataFrame, zincir_egrisi, k: int = 3,
               tohum: int = sabitler.TOHUM) -> dict:
    """Yeni mağaza öncülü kuralı (modül notu): bırakbirde statik profil ile zincirin, yeni olmayan
    mağazaların kendi düzeltilmiş eğrisine ortalama L1'i. Dönüş: `secim`, `l1_profil`,
    `l1_zincir`, `isabet`, `magaza` (bırakbir mağaza sayısı)."""
    st = _statik(kapsam).set_index("magaza_id", drop=False)
    eski = [m for m in st.index[~st["yeni"].to_numpy(dtype=bool)] if not duz.loc[m].isna().any()]
    tam = profiller(duz.loc[eski], k, tohum)
    z = np.asarray(zincir_egrisi, dtype="float64")
    l1_p, l1_z, isabet = [], [], []
    for m in eski:
        diger = [i for i in eski if i != m]
        p = profiller(duz.loc[diger], k, tohum)
        P = profil_egrileri(duz.loc[diger], p)
        a = yeni_magaza.ata(st.loc[[m]], st.loc[diger], p, komsu=KOMSU).iloc[0]
        kendi = duz.loc[m, SUTUNLAR].to_numpy(dtype="float64")
        l1_p.append(np.abs(P.loc[a].to_numpy() - kendi).sum())
        l1_z.append(np.abs(z - kendi).sum())
        isabet.append(a == tam[m])
    lp, lz = float(np.mean(l1_p)), float(np.mean(l1_z))
    return {"secim": "profil" if lp < lz else "zincir", "l1_profil": lp, "l1_zincir": lz,
            "isabet": float(np.mean(isabet)), "magaza": len(eski)}


# ---------------------------------------------------------------------------
# Kurulum, κ seçimi, mağaza eğrisi
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Kurulum:
    duz: pd.DataFrame
    n: pd.Series
    zincir: np.ndarray
    profil: pd.Series               # yeni olmayanlar
    P: pd.DataFrame
    oncul: pd.DataFrame
    kaynak: dict
    yeni_atama: dict
    yeni_secim: dict


def _kur(tablolar, kapsam: pd.DataFrame, karar_gunu, hatlar, k: int, tohum: int) -> _Kurulum:
    """κ dışındaki her şey: düzeltilmiş eğri, n, zincir, profiller, öncüller (modül notu)."""
    ids = _ids(kapsam)
    fiz = _fiziksel(tablolar["magaza"])
    hepsi = list(dict.fromkeys(fiz + ids))
    h = _hucreler(tablolar, hepsi, option_pencereleri(tablolar["urun"], karar_gunu, hatlar), karar_gunu)
    z = _havuz(h[h["magaza_id"].isin(fiz)])
    h = h[h["magaza_id"].isin(ids)]
    duz = _paya(h, hucre_talebi(h, z), ids)
    n = h.groupby("magaza_id")["s"].sum().reindex(ids, fill_value=0.0).rename("n").astype("float64")
    yeni = dict(zip(ids, kapsam["yeni"].to_numpy(dtype=bool)))
    eski = [m for m in ids if not yeni[m]]
    eksik = [m for m in eski if duz.loc[m].isna().any()]
    if eksik:
        raise ValueError(f"yeni olmayan mağazanın penceresinde gözlem yok: {eksik}")
    if len(eski) <= k:
        raise ValueError(f"profil için yeni olmayan mağaza az: {len(eski)} (k = {k})")
    profil = profiller(duz.loc[eski], k, tohum)
    P = profil_egrileri(duz.loc[eski], profil)
    yeniler = [m for m in ids if yeni[m]]
    secim = yeni_secim(kapsam, duz, z, k, tohum)
    st = _statik(kapsam).set_index("magaza_id", drop=False)
    atama = (yeni_magaza.ata(st.loc[yeniler], st.loc[eski], profil, komsu=KOMSU).to_dict()
             if yeniler else {})
    O = pd.DataFrame(index=pd.Index(ids, name="magaza_id"), columns=SUTUNLAR, dtype="float64")
    kay = {}
    for m in ids:
        if not yeni[m]:
            O.loc[m] = P.loc[profil[m]].to_numpy()
            kay[m] = "magaza"
        elif secim["secim"] == "profil":
            O.loc[m] = P.loc[atama[m]].to_numpy()
            kay[m] = "profil"
        else:
            O.loc[m] = z
            kay[m] = "zincir"
    return _Kurulum(duz, n, z, profil, P, O, kay, atama, secim)


def gerceklesen_pay(tablolar, kal_karar_gunu, karar_gunu, kapsam) -> pd.DataFrame:
    """Kalibrasyon hedefi: `kal_karar_gunu`'nden sonraki ilk lansmanın sezonundaki Collection
    option'larının ilk `EGRI_PENCERE_HAFTA` haftasının düzeltilmiş payı (yayımlanan veri). Hedef
    pencereleri `karar_gunu`'nün geçmiş penceresi içinde bitmeli."""
    kal = pd.Timestamp(kal_karar_gunu).normalize()
    bit0 = ozellikler.pencere(karar_gunu, sabitler.GECMIS_PENCERE_HAFTA)[1]
    u = kaynak.bes_bedenli(tablolar["urun"])
    u = u[u["line"].astype(str) == SEZONLUK]
    o = (u.assign(option_id=u["option_id"].astype(str), sezon=u["sezon_kodu"].astype(str))
         .groupby("option_id", sort=True).agg(sezon=("sezon", "first"), lansman=("lansman_tarihi", "min"))
         .reset_index())
    o["bas"] = _pazartesi(o["lansman"])
    sonraki = o.loc[o["bas"] > kal, "bas"]
    if sonraki.empty:
        raise ValueError("kalibrasyon karar gününden sonra lansman yok")
    sezon = set(o.loc[o["bas"] == sonraki.min(), "sezon"])
    o = o[o["sezon"].isin(sezon)].copy()
    o["bit"] = o["bas"] + sabitler.EGRI_PENCERE_HAFTA * _HAFTA
    if (o["bit"] > bit0).any():
        raise ValueError("kalibrasyon hedefi karar gününün geçmiş penceresinde bitmiyor")
    ids = _ids(kapsam)
    h = _hucreler(tablolar, ids, o[["option_id", "bas", "bit"]], karar_gunu)
    return _paya(h, hucre_talebi(h, _havuz(h)), ids)     # doldurma: hedefin kendi havuz payı


def kappa_sec(tablolar, karar_gunu, *, kal_karar_gunu=sabitler.KAL_KARAR_GUNU, izgara=KAPPA_IZGARASI,
              hatlar=HATLAR, k: int = 3, tohum: int = sabitler.TOHUM) -> tuple[float, pd.DataFrame]:
    """Hakemsiz κ (modül notu). Dönüş: (κ, tablo `kappa, l1, magaza`)."""
    kal = pd.Timestamp(kal_karar_gunu).normalize()
    if kal >= pd.Timestamp(karar_gunu).normalize():
        raise ValueError("kalibrasyon karar günü oyun karar gününden önce olmalı")
    kapsam_kal = kaynak.kapsam(tablolar, kal)
    hedef = gerceklesen_pay(tablolar, kal, karar_gunu, kapsam_kal).dropna()
    kur = _kur(tablolar, kapsam_kal, kal, hatlar, k, tohum)
    ids = [m for m in _ids(kapsam_kal) if m in hedef.index]
    satir = []
    for kp in izgara:
        E = daralt(kur.duz, kur.n, kur.oncul, kappa=kp).loc[ids]
        satir.append({"kappa": kp, "l1": float(np.abs(E.to_numpy() - hedef.loc[ids].to_numpy()).sum(axis=1).mean()),
                      "magaza": len(ids)})
    tablo = pd.DataFrame(satir)
    en = tablo["l1"].round(12).min()
    secilen = tablo.loc[tablo["l1"].round(12) == en, "kappa"].min()
    return secilen, tablo


def magaza_egrisi(tablolar, kapsam: pd.DataFrame, karar_gunu, *, kappa: float | None = None,
                  hatlar=HATLAR, k: int = 3, tohum: int = sabitler.TOHUM) -> Egri:
    """Karar anında kapsamın her mağazasının beden eğrisi (modül notu). `kappa` verilmezse
    `kappa_sec` ile seçilir."""
    tablo = None
    if kappa is None:
        kappa, tablo = kappa_sec(tablolar, karar_gunu, hatlar=hatlar, k=k, tohum=tohum)
    kur = _kur(tablolar, kapsam, karar_gunu, hatlar, k, tohum)
    E = daralt(kur.duz, kur.n, kur.oncul, kappa=kappa)
    profil = pd.Series({m: kur.profil[m] if kay == "magaza" else None for m, kay in kur.kaynak.items()},
                       dtype=object)
    yeniler = [m for m, kay in kur.kaynak.items() if kay != "magaza"]
    if yeniler:
        profil.loc[yeniler] = _en_yakin_profil(E.loc[yeniler], kur.P).to_numpy()
    profil = profil.reindex(E.index).rename("profil")
    profil.index.name = "magaza_id"
    return Egri(magaza=E, profil=profil, zincir=kur.zincir, kaynak=kur.kaynak, kappa=float(kappa), n=kur.n,
                duzeltilmis=kur.duz, profil_egrisi=kur.P, yeni_atama=kur.yeni_atama,
                yeni_secim=kur.yeni_secim, kappa_tablosu=tablo)
