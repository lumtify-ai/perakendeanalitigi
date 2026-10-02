"""Görev 14: B'nin kalibrasyon bantları (spec §8), TAM, yayımlanan B tohumu.

Bantlar spec §8'in yedi satırı birebir, bir istisnayla (kontrolcü kararı,
Görev 12): "online satırlarda yorum oranı" %4–8 yerine %0,9–1,5 (spec'in
yorum sayısı hedefi 50–80k ile %6 TAM'da çelişir; sayı hedefi korundu).
Ölçütler yalnız yayımlanan tablolardan (öğrenenin gördüğü), izleme
satırları (çapraz cinsiyet, kalite sinyali, nüfus seyri) ham sonuçtan.

Tanımlar (pencere yılları 2023–2025; "aktif" = o yıl en az bir kartlı
satış fişi, mağaza ya da online):

- kart payı: mağaza satış fişlerinde `musteri_id` dolu payı;
- fiş başına adet: satış fişlerinin `adet` ortalaması (mağaza · online);
- yıllık ziyaret: Σ_yıl kartlı satış fişi / Σ_yıl o yılın aktif müşterisi
  (üç yılın havuzu; yıl yıl değerler izleme satırı);
- dönme oranı: Y'de aktif olanların Y+1'de de aktif payı (2023→24 ve
  2024→25 havuzu);
- yeni müşteri payı: Y'nin aktiflerinde `kayit_tarihi` Y içinde olanların
  payı (üç yılın havuzu);
- yorum oranı: yorum sayısı / penceredeki online satış fişi satırları;
  ortalama puan: yorumların `puan` ortalaması;
- giriş payı: `online_olay`'da `musteri_id` dolu oturumların payı.

Çok tohumlu koşu: `araclar/v4_crm_cok_tohum.py` (aynı yardımcılar).
Bütün testler `yavas` işaretli; oturum fixture'ı `tam_crm` (conftest).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pytest

YILLAR = (2023, 2024, 2025)


def _aralik(a, b):
    return lambda x: a <= x <= b


# (anahtar, spec §8 satırı, bant metni, geçer mi). Spec'in yedi satırı;
# 2. ve 6. satır ikişer ölçüt.
BANTLAR = [
    ("kart_payi", "Mağazada kart okutma payı", "%50–60", _aralik(0.50, 0.60)),
    ("sepet_magaza", "Fiş başına adet: mağaza", "2,0–2,5", _aralik(2.0, 2.5)),
    ("sepet_online", "Fiş başına adet: online", "1,6–2,0", _aralik(1.6, 2.0)),
    ("yillik_ziyaret", "Kartlı müşteri yıllık ziyaret", "2,5–4", _aralik(2.5, 4.0)),
    ("donme_orani", "Ertesi yıl dönme oranı", "%45–65", _aralik(0.45, 0.65)),
    ("yeni_payi", "Yeni müşterinin yıllık aktif payı", "%25–40", _aralik(0.25, 0.40)),
    ("yorum_orani", "Online satırlarda yorum oranı", "%0,9–1,5 (karar)", _aralik(0.009, 0.015)),
    ("ortalama_puan", "Yorum ortalama puanı", "4,0–4,4", _aralik(4.0, 4.4)),
    ("giris_payi", "Giriş yapmış oturum payı", "%55–65", _aralik(0.55, 0.65)),
]

# Bant dışı izleme satırları (anahtar, açıklama, hedef metni, geçer mi | None).
IZLEME = [
    ("yorum_sayisi", "Yorum sayısı", "60–80k", _aralik(60_000, 80_000)),
    ("kalite_sinyali", "Hatalı tedarikçide kalite konusu katı", "≥ 2", lambda x: x >= 2.0),
    ("capraz_giyim", "Çapraz cinsiyet payı (giyim, kartlı)", "%8–15", _aralik(0.08, 0.15)),
    ("capraz_aksesuar", "Çapraz cinsiyet payı (aksesuar)", "(bilgi)", None),
    ("sozlesme", "fis_satir = A'nın temiz satışı (kuruş)", "= 1", lambda x: x == 1),
    ("ziyaret_2023", "Yıllık ziyaret 2023", "(bilgi)", None),
    ("ziyaret_2024", "Yıllık ziyaret 2024", "(bilgi)", None),
    ("ziyaret_2025", "Yıllık ziyaret 2025", "(bilgi)", None),
    ("donme_2024", "Dönme 2023→2024", "(bilgi)", None),
    ("donme_2025", "Dönme 2024→2025", "(bilgi)", None),
    ("yeni_2023", "Yeni payı 2023", "(bilgi)", None),
    ("yeni_2024", "Yeni payı 2024", "(bilgi)", None),
    ("yeni_2025", "Yeni payı 2025", "(bilgi)", None),
    ("aktif_2025", "Aktif kartlı müşteri 2025", "(bilgi)", None),
    ("n_musteri", "musteri satırı", "(bilgi; spec ~1–1,5M)", None),
    ("n_fis", "fis satırı", "(bilgi; spec ~10M)", None),
    ("n_fis_satir", "fis_satir satırı", "(bilgi; spec ~22M)", None),
    ("n_olay", "online_olay satırı", "(bilgi)", None),
    ("hayatta_2022", "Yıl sonu hayatta 2022", "(bilgi)", None),
    ("hayatta_2025", "Yıl sonu hayatta 2025", "(bilgi)", None),
    ("katilis_2024", "Katılış 2024", "(bilgi)", None),
    ("terk_2024", "Terk 2024", "(bilgi)", None),
    ("eksik_musteri", "Eksik (ziyaretçi yetmedi) yeni müşteri", "(bilgi)", None),
    ("yorum_iadeli", "Yorum: iade edilmiş satırda", "(bilgi)", None),
    ("yorum_hediye", "Yorum: hediye satırında (alıcılı metin)", "(bilgi)", None),
    ("yorum_hediye_yazar", "Yorum yazarı: hediye satırında", "(bilgi)", None),
    ("yorum_dusen_hediye", "Yorum düşen: hediye, uyan metin yok", "(bilgi)", None),
    ("yorum_dusen_kapasite", "Yorum düşen: kapasite (hediye dahil)", "(bilgi)", None),
    ("yorum_dusen_tarih", "Yorum düşen: pencere sonrası tarih", "(bilgi)", None),
    ("yorum_dusen_tarih_iade", "  bunun iade tarihi kuralından gelen kısmı", "(bilgi)", None),
]


# ---------------------------------------------------------------------------
# Yardımcılar (çok tohumlu betik de kullanır)
# ---------------------------------------------------------------------------


def _no(s: pd.Series) -> np.ndarray:
    """'F00000001' gibi kimlik → 0 tabanlı tam sayı; boş → −1."""
    a = pa.array(s.array)
    dolu = a.drop_null()
    if not len(dolu):
        return np.full(len(a), -1, dtype=np.int64)
    ilk = dolu[0].as_py()
    n_onek = len(ilk) - len(ilk.lstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ"))
    sayi = pc.cast(pc.utf8_slice_codeunits(a, n_onek), pa.int64())
    return np.asarray(sayi.fill_null(0).to_numpy(zero_copy_only=False), dtype=np.int64) - 1


def _yil(tarih: pd.Series) -> np.ndarray:
    return tarih.dt.year.to_numpy()


def yayimlanan_olcutler(t: dict) -> dict:
    """Spec §8 bant ölçütleri ve yayımlanan tablolardan izleme sayıları."""
    o: dict = {}
    f = t["fis"]
    satis = (f["fis_tipi"] == "satis").to_numpy()
    magaza = (f["kanal"] == "magaza").to_numpy()
    kart = f["musteri_id"].notna().to_numpy()
    adet = f["adet"].to_numpy()
    o["kart_payi"] = float(kart[satis & magaza].mean())
    o["sepet_magaza"] = float(adet[satis & magaza].mean())
    o["sepet_online"] = float(adet[satis & ~magaza].mean())

    yil = _yil(f["tarih"])
    mus = _no(f["musteri_id"])
    aktif: dict[int, np.ndarray] = {}
    fis_say, mus_say = 0, 0
    for y in YILLAR:
        s = satis & kart & (yil == y)
        aktif[y] = np.unique(mus[s])
        o[f"ziyaret_{y}"] = float(s.sum() / len(aktif[y]))
        fis_say += int(s.sum())
        mus_say += len(aktif[y])
    o["yillik_ziyaret"] = fis_say / mus_say
    o["aktif_2025"] = len(aktif[2025])

    don, taban = 0, 0
    for y in YILLAR[1:]:
        ortak = np.intersect1d(aktif[y - 1], aktif[y], assume_unique=True)
        o[f"donme_{y}"] = len(ortak) / len(aktif[y - 1])
        don += len(ortak)
        taban += len(aktif[y - 1])
    o["donme_orani"] = don / taban

    m = t["musteri"]
    m_no = _no(m["musteri_id"])
    kayit_yil = np.full(m_no.max() + 1, -1, dtype=np.int64)
    kayit_yil[m_no] = _yil(m["kayit_tarihi"])
    yeni, taban = 0, 0
    for y in YILLAR:
        n_yeni = int((kayit_yil[aktif[y]] == y).sum())
        o[f"yeni_{y}"] = n_yeni / len(aktif[y])
        yeni += n_yeni
        taban += len(aktif[y])
    o["yeni_payi"] = yeni / taban

    # Yorum oranı: online satış fişlerinin satırları (pencere; adet > 0).
    fs = t["fis_satir"]
    fis_no = _no(fs["fis_id"])
    onl_satis = satis & ~magaza
    n_onl_satir = int((onl_satis[fis_no] & (fs["adet"].to_numpy() > 0)).sum())
    y = t["yorum"]
    o["yorum_sayisi"] = len(y)
    o["yorum_orani"] = len(y) / n_onl_satir
    o["ortalama_puan"] = float(y["puan"].astype(float).mean())

    ol = t["online_olay"]
    oturum = ol["oturum_id"].to_numpy()
    giris = ol["musteri_id"].notna().to_numpy()
    u, ilk = np.unique(oturum, return_index=True)
    # bir oturumun bütün olayları aynı müşteriyi taşır (giriş oturum düzeyinde)
    o["giris_payi"] = float(giris[ilk].mean())

    o["n_musteri"] = len(m)
    o["n_fis"] = len(f)
    o["n_fis_satir"] = len(fs)
    o["n_olay"] = len(ol)
    return o


def a_satis_ozeti(girdi) -> pd.DataFrame:
    """A'nın temiz yayımlanan `satis`'i (iadeler dahil), (tarih, mağaza,
    ürün) anahtarında adet / tutar / indirim kuruş toplamları. A sabit
    olduğundan bir kez hesaplanır."""
    from perakende_veri.v4.tablolar import _Kimlik, satis_tablosu

    s = satis_tablosu(girdi.dunya, girdi.ham, _Kimlik(girdi.dunya))
    return _sozlesme_grupla(s["tarih"], s["magaza_id"], s["urun_id"], s["adet"], s["tutar"],
                            s["indirim_tutari"], girdi.dunya)


def _kod(seri: pd.Series, idler: np.ndarray) -> np.ndarray:
    ix = pd.Index(idler)
    if isinstance(seri.dtype, pd.CategoricalDtype):
        eslem = ix.get_indexer(seri.cat.categories.astype(str))
        kod = eslem[seri.cat.codes.to_numpy()]
    else:
        kod = ix.get_indexer(seri.astype(str).to_numpy())
    assert (kod >= 0).all()
    return kod.astype(np.int64)


def _kurus(x) -> np.ndarray:
    return np.round(np.asarray(x, dtype=np.float64) * 100).astype(np.int64)


def _sozlesme_grupla(tarih, magaza, urun, adet, tutar, indirim, dunya) -> pd.DataFrame:
    mag = dunya.magazalar["magaza_id"].to_numpy().astype(str)
    uru = dunya.urunler["urun_id"].to_numpy().astype(str)
    gun = (tarih.to_numpy().astype("datetime64[D]").astype(np.int64))
    anahtar = (gun * len(mag) + _kod(magaza, mag)) * len(uru) + _kod(urun, uru)
    df = pd.DataFrame({"k": anahtar, "adet": np.asarray(adet, dtype=np.int64),
                       "tutar": _kurus(tutar), "indirim": _kurus(indirim)})
    return df.groupby("k", sort=True).sum()


def sozlesme_tutar_mi(t: dict, a_ozet: pd.DataFrame, dunya) -> bool:
    """`fis_satir`'ın (tarih, mağaza, ürün) toplamı A'nın temiz satışına
    adet, tutar ve indirim olarak kuruşu kuruşuna eşit mi (grup kümesi dahil)."""
    f, fs = t["fis"], t["fis_satir"]
    fis_no = _no(fs["fis_id"])
    assert (_no(f["fis_id"]) == np.arange(len(f))).all()
    tarih = pd.Series(f["tarih"].to_numpy()[fis_no])
    magaza = pd.Series(pd.Categorical.from_codes(f["magaza_id"].cat.codes.to_numpy()[fis_no],
                                                 categories=f["magaza_id"].cat.categories))
    b = _sozlesme_grupla(tarih, magaza, fs["urun_id"], fs["adet"], fs["tutar"], fs["indirim_tutari"], dunya)
    if len(b) != len(a_ozet) or not (b.index.to_numpy() == a_ozet.index.to_numpy()).all():
        return False
    return bool((b.to_numpy() == a_ozet.to_numpy()).all())


def ham_olcutler(ham) -> dict:
    """Ham sonuçtan izleme satırları: çapraz cinsiyet (Görev 5b, kartlı satış
    birimleri), kalite sinyali (Görev 12), nüfus seyri."""
    from perakende_veri.v4.crm.tercih import cinsiyet_ozeti
    from perakende_veri.v4.takvim import gun_indisi

    o: dict = {}
    crm = ham.crm
    fis = crm.tablo("fis")
    c = cinsiyet_ozeti(crm.nufus, fis, crm.kayit.tablo("fis_satir"), ham.girdi.dunya.urunler)
    o["capraz_giyim"] = c["capraz"]
    o["capraz_aksesuar"] = c["capraz_aksesuar"]
    del fis

    y = ham.yorum
    b = y.yorum[["yorum_id", "fis_satir_id"]].merge(y.gizli[["yorum_id", "konular"]], on="yorum_id")
    b = b.merge(y.aday[["satir_id", "hatali_tedarikci"]], left_on="fis_satir_id", right_on="satir_id",
                how="left")
    kalite = b["konular"].astype(str).str.contains("kumas_kalite").to_numpy()
    h = b["hatali_tedarikci"].to_numpy(bool)
    o["kalite_sinyali"] = float(kalite[h].mean() / kalite[~h].mean())
    yaz = y.aday.set_index("satir_id").loc[y.yorum["fis_satir_id"], ["iade", "hediye"]]
    o["yorum_iadeli"] = int(yaz["iade"].sum())
    o["yorum_hediye"] = int(yaz["hediye"].sum())
    o["yorum_hediye_yazar"] = int(y.hediye_yazar)
    o["yorum_dusen_hediye"] = int(y.dusen_hediye)
    o["yorum_dusen_kapasite"] = int(y.dusen_kapasite)
    o["yorum_dusen_tarih"] = int(y.dusen_tarih)
    o["yorum_dusen_tarih_iade"] = int(y.dusen_tarih_iade)

    n = crm.nufus
    kg, tg = n.kayit_gun.astype(np.int64), n.terk_gun.astype(np.int64)
    for yil in (2022, 2023, 2024, 2025):
        b_, s_ = max(gun_indisi(f"{yil}-01-01"), 0), min(gun_indisi(f"{yil}-12-31"), crm.D - 1)
        o[f"hayatta_{yil}"] = int(((kg <= s_) & ((tg < 0) | (tg > s_))).sum())
        o[f"katilis_{yil}"] = int(((kg >= b_) & (kg <= s_)).sum())
        o[f"terk_{yil}"] = int(((tg >= b_) & (tg <= s_)).sum())
    o["eksik_musteri"] = int(crm.kayit.sayac.get("yeni", 0))
    return o


def kalibrasyon_olcutleri(tablolar: dict, ham, a_ozet: pd.DataFrame | None = None) -> dict:
    """Bir B koşusunun bütün ölçütleri (bant + izleme)."""
    o = yayimlanan_olcutler(tablolar)
    o.update(ham_olcutler(ham))
    if a_ozet is not None:
        o["sozlesme"] = int(sozlesme_tutar_mi(tablolar, a_ozet, ham.girdi.dunya))
    return o


# ---------------------------------------------------------------------------
# Testler (TAM, CRM_TOHUM)
# ---------------------------------------------------------------------------

pytestmark = pytest.mark.yavas


@pytest.fixture(scope="module")
def olcut(tam_crm):
    o = tam_crm["olcut"]
    print("\nB kalibrasyonu (TAM, CRM_TOHUM):")
    for anahtar, satir, bant, _ in BANTLAR + IZLEME:
        if anahtar in o:
            print(f"  {satir:44s} {o[anahtar]!s:>22.22} {bant}")
    return o


@pytest.mark.parametrize("anahtar", [b[0] for b in BANTLAR])
def test_bant(olcut, anahtar):
    _, satir, bant, gecer = next(b for b in BANTLAR if b[0] == anahtar)
    assert gecer(olcut[anahtar]), f"{satir}: {olcut[anahtar]:.4f} (bant {bant})"


def test_tutarlilik_sozlesmesi_tam(olcut):
    assert olcut["sozlesme"] == 1


def test_yorum_sayisi_ve_kalite_sinyali(olcut):
    assert 60_000 <= olcut["yorum_sayisi"] <= 80_000
    assert olcut["kalite_sinyali"] >= 2.0


def test_capraz_cinsiyet_payi(olcut):
    assert 0.08 <= olcut["capraz_giyim"] <= 0.15


def test_b_suresi(tam_crm):
    # B (A kurulumu hariç, yazma hariç) < 20 dk
    assert tam_crm["sure_sn"] < 20 * 60
