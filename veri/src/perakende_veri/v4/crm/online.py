"""Görev 9: online liste sayfaları, Lumoda'nın sıralaması, gizli tıklama
modeli, günlük liste özeti (spec §5). Olay kaydı `online_olay.py`'de.

**Listeler** (`listeler`): A'nın option'larında dolu olan her üst kategori ×
cinsiyet için `kategori:<üst>:<cinsiyet>`, `yeni_gelenler`, `indirim` ve 17
alt kategori araması `arama:<alt>`. Görüntüleme başına ilk
`LISTE_UZUNLUGU` (48 = 2 × 24) sıra gösterilir.

**Sıralama politikası** (enjekte edilebilir): `siralama(gorunum) ->
{liste: option dizisi}`; `gorunum` (`GunGorunum`) yalnız o sabah bilinen
yayımlanabilir veriyi taşır (dünkü ve öncesi ONL satışı, lansman günü,
online indirim oranı, depo stoğu ve satış penceresi bayrağı). Motor her
listeyi 48'e keser; dönen her option'ın uygun (depo stoğu > 0, satış
penceresinde, ONL hücresi var) olduğunu doğrular. Lumoda'nın politikası
`lumoda_siralama`: kategori ve arama listeleri son 7 günün (d−7 … d−1) ONL
satış adedine göre azalan, eşitlikte option indisi artan (yeni ürün satışı
olmadığı için alta düşer: bilerek duran geri besleme döngüsü);
`yeni_gelenler` son 28 günde lansman, lansmana göre yeni önce;
`indirim` online indirim oranı (`max(online hattın markdown'ı, ONL
kampanyası)`) > 0, azalan.

**Depo stoğu.** A'nın `depo_stok` fotoğrafı gün başında çekilir; o gün
option'ın SKU'larından birinde adet > 0 ise stoklu (fotoğrafta olmayan SKU
0). Gün içinde varış olursa option stoksuz görünüp satabilir: o satın alma
listede değildir.

**Tıklama modeli (gizli).** bakılma(sıra) = 1 / (1 + sıra)^0,8 (sıra 1'den);
ilgi(option, arketip) = exp(log sürpriz + öznitelik etkisi (A, segment
ortalaması; sezonluk option kendi sezonu, DEVAMLI günün sezonu) + arketip
tercihi (alt kategori, fiyat segmenti, kalıp, desen ortalarının düzgüne göre
log-oranı) + 0,5 × arketip indirim duyarlılığı ortalaması × oran). Günün
ilgisi γ(option, d), online etkin müşterilerin (hayatta, online_payi > 0)
arketip ağırlığıyla (Σ ziyaret_hizi × online_payi; pencere başından 7
günlük adımlarla, adımın ilk günü) ortalanır. Tıklama olasılığı konum
yanlılığı modeli (PBM): p = min(0,9, c × bakılma(sıra) × γ), c koşu
boyunca TEK sabit (`tiklama_sabiti`): bütün pencerede (koşulan aralıktan
bağımsız) Lumoda'nın sıralamasıyla beklenen Σ tıklama / Σ görüntüleme =
`TIKLAMA_GORUNTULEME` olacak şekilde bir ön geçişte ayarlanır. Enjekte
edilen başka politika aynı c ile (aynı gerçek tıklama modeliyle) koşar.

**Gün d** (`online_gun`):

1. Satın alma (option × gün) sabit: ONL satış fişlerinin satırları.
2. Görüntüleme: toplam = ONL satış fişi × `GORUNTULEME_FIS` (BF ×2 fişin
   kendisinden); liste türlerine `LISTE_TRAFIK_PAYI` (kategori ve arama
   listeleri içinde son 7 gün satış + 1 ile orantılı; boş liste 0),
   multinom.
3. Hücre tıklama olasılığı = min(0,9, c × bakılma(sıra) × γ(option, d)).
4. Listede olmayan satın alınan option `arama:<alt>` listesinin 1. sırasına
   eklenir (**enjekte hücre**; aynı (gün, liste, sıra 1)'de iki option
   olabilir, anahtar (gün, liste, sıra, option)).
5. Satın alma, option'ın hücrelerine görüntüleme × tıklama olasılığı ×
   (sabit) dönüşüm ağırlığıyla multinom dağıtılır; toplam birebir (assert).
6. Olay günlerinde satın alma birimleri fiş satırlarına bağlanır (aynı
   option'ın birimleri rastgele eşlenir); (fiş, liste) çifti sayısı
   listenin en az görüntülemesidir.
7. gösterim = liste görüntülemesi (≥ hücredeki alım ve tıklama); tıklama =
   max(Binom(gösterim, p), alım); enjekte hücrede tıklama = alım +
   Poisson(3 × alım), gösterim = tıklama + Poisson(2 × tıklama) (o option'ı
   bulan arama sayısı); sepete ekleme = max(Binom(tıklama, 0,25), alım).

**Gizli** (`OnlineCikti.gizli`): bakılma eğrisi, `tiklama_sabiti` c,
`ilgi_gunluk` (gun, option, ilgi = o gün kullanılan γ; o gün hücresi olan
her option), `arketip_agirligi` (adım başı gün × arketip), sezon × option ×
arketip `ilgi` (oran 0), `enjekte` (gun, liste, sira, option: listede
olmayan satın almanın arama hücreleri). Gerçek tıklama olasılığı
`tiklama_olasiligi(sira, ilgi, c)` ile yeniden kurulur.

Rastgelelik `crm_alt_ureticiler(d, "online", GUN_ADIMLARI)`; olay adımları
aynı akışın sonraki adımları (`online_olay.OLAY_ADIMLARI`).
"""

import time
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd

from .. import sabitler as a_sabitler
from ..takvim import gun_indisi
from . import sabitler as S
from .rastgele import crm_alt_ureticiler

GUN_ADIMLARI = ("goruntuleme", "dagitim", "birim", "tiklama", "sepet", "enjekte")
L_UZUN = S.LISTE_UZUNLUGU


# ---------------------------------------------------------------------------
# Listeler ve kamu görünümü
# ---------------------------------------------------------------------------


def listeler(optionlar: pd.DataFrame) -> tuple[tuple[str, ...], np.ndarray, np.ndarray]:
    """(liste adları, [O] option'ın kategori listesi indisi, [O] arama listesi
    indisi). Sıra: kategori listeleri (A'nın `KATEGORILER` × `CINSIYETLER`
    sırasıyla, yalnız dolu olanlar), `yeni_gelenler`, `indirim`, 17 arama."""
    ust = optionlar["ust_kategori"].to_numpy()
    cins = optionlar["cinsiyet"].to_numpy()
    alt = optionlar["alt_kategori"].to_numpy()
    adlar: list[str] = []
    kat = np.full(len(optionlar), -1, dtype=np.int16)
    for u in a_sabitler.KATEGORILER:
        for c in a_sabitler.CINSIYETLER:
            s = (ust == u) & (cins == c)
            if s.any():
                kat[s] = len(adlar)
                adlar.append(f"kategori:{u}:{c}")
    adlar += ["yeni_gelenler", "indirim"]
    arama = np.full(len(optionlar), -1, dtype=np.int16)
    for a in S.ALT_KATEGORILER:
        arama[alt == a] = len(adlar)
        adlar.append(f"arama:{a}")
    assert (kat >= 0).all() and (arama >= 0).all()
    return tuple(adlar), kat, arama


@dataclass(frozen=True)
class GunGorunum:
    """Sıralama politikasının gördüğü yayımlanabilir veri (gün d sabahı).

    listeler        liste adları
    kategori_liste  [O] option'ın kategori listesi indisi
    arama_liste     [O] option'ın arama listesi indisi
    uygun           [O] depo stoğu > 0, satış penceresinde, ONL'de satılır
    satis7          [O] d−7 … d−1 ONL satış adedi
    lansman_gun     [O]
    oran            [O] online indirim oranı (markdown ya da kampanya)"""

    gun: int
    listeler: tuple
    kategori_liste: np.ndarray
    arama_liste: np.ndarray
    uygun: np.ndarray
    satis7: np.ndarray
    lansman_gun: np.ndarray
    oran: np.ndarray


def _grupla_sirala(liste: np.ndarray, o: np.ndarray, anahtar: np.ndarray, adlar) -> dict:
    """`liste` grubu içinde `anahtar` artan, eşitlikte option artan."""
    sira = np.lexsort((o, anahtar, liste))
    ls, os_ = liste[sira], o[sira]
    sinir = np.flatnonzero(np.diff(ls)) + 1
    return {adlar[int(pl[0])]: po for pl, po in zip(np.split(ls, sinir), np.split(os_, sinir)) if len(pl)}


def lumoda_siralama(g: GunGorunum) -> dict[str, np.ndarray]:
    """Lumoda'nın sıralaması (modül docstring'i). Kesilmemiş listeler."""
    o = np.flatnonzero(g.uygun)
    s7 = -np.asarray(g.satis7, dtype=np.int64)[o]
    out = _grupla_sirala(np.asarray(g.kategori_liste)[o], o, s7, g.listeler)
    out.update(_grupla_sirala(np.asarray(g.arama_liste)[o], o, s7, g.listeler))
    lg = np.asarray(g.lansman_gun)[o]
    yeni = o[(lg > g.gun - S.YENI_GELEN_GUN) & (lg <= g.gun)]
    out["yeni_gelenler"] = yeni[np.lexsort((yeni, -np.asarray(g.lansman_gun)[yeni]))]
    ind = o[np.asarray(g.oran)[o] > 0]
    out["indirim"] = ind[np.lexsort((ind, -np.asarray(g.oran)[ind]))]
    return out


# ---------------------------------------------------------------------------
# Gizli tıklama modeli
# ---------------------------------------------------------------------------


def bakilma(sira) -> np.ndarray:
    """Gizli bakılma eğrisi 1 / (1 + sıra)^0,8, sıra 1'den."""
    return 1.0 / (1.0 + np.asarray(sira, dtype=float)) ** S.BAKILMA_US


def tiklama_olasiligi(sira, ilgi, sabit) -> np.ndarray:
    """Görüntüleme başına hücre tıklama olasılığı (PBM):
    min(0,9, c × bakılma(sıra) × γ)."""
    return np.minimum(S.TIKLAMA_UST, float(sabit) * bakilma(sira) * np.asarray(ilgi, dtype=float))


def _log_goreli(anahtar: str, eksen: list, degerler: np.ndarray) -> np.ndarray:
    """[n, A] arketip tercih ortasının düzgüne göre log-oranı, `degerler`
    (`eksen` etiketleri) satırları için."""
    t = np.array([S.ARKETIP_PARAMETRE[a][anahtar] for a in S.ARKETIPLER], dtype=float)
    t = t / t.sum(axis=1, keepdims=True) * t.shape[1]
    idx = pd.Series(degerler).map({e: i for i, e in enumerate(eksen)}).to_numpy(dtype=np.int64)
    return np.log(t[:, idx].T)


def arketip_tercihi(optionlar: pd.DataFrame) -> np.ndarray:
    """[O, A] gizli arketip tercih log-terimi (alt kategori + fiyat segmenti
    + kalıp + desen)."""
    return (_log_goreli("kategori", S.ALT_KATEGORILER, optionlar["alt_kategori"].to_numpy())
            + _log_goreli("fiyat_segment", S.FIYAT_SEGMENTLERI, optionlar["fiyat_segmenti"].to_numpy())
            + _log_goreli("kalip", S.KALIPLAR, optionlar["kalip"].to_numpy())
            + _log_goreli("desen", S.DESENLER, optionlar["desen"].to_numpy()))


def arketip_indirim_ortalamasi() -> np.ndarray:
    t = np.array([S.ARKETIP_PARAMETRE[a]["indirim_beta"] for a in S.ARKETIPLER], dtype=float)
    return t[:, 0] / t.sum(axis=1)


def sezon_ilk_gunleri() -> np.ndarray:
    """A'nın sezonlarının ilk dalga günleri (`SEZONLAR` sırası)."""
    return np.array([gun_indisi(s["dalgalar"][0]) for s in a_sabitler.SEZONLAR.values()], dtype=np.int64)


def gunun_sezonu(d: int) -> int:
    """İlk dalgası başlamış son sezon (A'nın `talep.sezon_gun` kuralı)."""
    return max(int(np.searchsorted(sezon_ilk_gunleri(), d, side="right")) - 1, 0)


def cekicilik(dunya, ham: dict) -> np.ndarray:
    """[Sezon, O] gizli A çekiciliği log sürpriz + öznitelik etkisi (segment
    ortalaması); sezonluk option'ın bütün satırları kendi sezonunun
    değeri. A'nın `gizli_gercek` tablosundan."""
    from ..tablolar import gizli_gercek

    gz = gizli_gercek(dunya, ham)
    opt = dunya.optionlar
    O = len(opt)
    sezonlar = list(a_sabitler.SEZONLAR)
    et = gz["oznitelik_etkisi"]
    Sn, G = len(sezonlar), len(a_sabitler.SEGMENTLER)
    assert len(et) == Sn * G * O
    assert (et["option_id"].to_numpy()[:O] == opt["option_id"].to_numpy()).all()
    assert list(et["sezon_kodu"].to_numpy()[:: G * O]) == sezonlar
    etki = et["etki"].to_numpy(dtype=float).reshape(Sn, G, O).mean(axis=1)
    sp = gz["surpriz"]
    assert (sp["option_id"].to_numpy() == opt["option_id"].to_numpy()).all()
    z = np.log(sp["surpriz"].to_numpy(dtype=float))[None, :] + etki
    kendi = opt["sezon_kodu"].map({k: i for i, k in enumerate(sezonlar)}).to_numpy()
    sezonluk = ~pd.isna(kendi)
    if sezonluk.any():
        o = np.flatnonzero(sezonluk)
        z[:, o] = z[kendi[o].astype(np.int64), o][None, :]
    return z


# ---------------------------------------------------------------------------
# Hazırlık
# ---------------------------------------------------------------------------


@dataclass(eq=False)
class _Hazir:
    O: int
    listeler: tuple
    kat_liste: np.ndarray
    arama_liste: np.ndarray
    liste_turu: np.ndarray       # [L] 0 kategori, 1 yeni, 2 indirim, 3 arama
    satin: np.ndarray            # [D, O] ONL satış adedi
    fis_sayisi: np.ndarray       # [D] ONL satış fişi
    stoklu: np.ndarray           # [D, O]
    md_oran: np.ndarray          # [D, O] online hat markdown
    penceresi: tuple             # (lansman_gun [O], cikis_gun [O], onl_var [O])
    z: np.ndarray                # [Sezon, O]
    tercih: np.ndarray           # [O, A]
    ind_a: np.ndarray            # [A]
    olay_satir: dict = field(default_factory=dict)   # gün → ONL satış satırları
    olay_fis: dict = field(default_factory=dict)     # gün → ONL satış fişleri


def _birlestir(parcalar, sutunlar):
    return {k: np.concatenate([p[k] for p in parcalar]) if parcalar else np.zeros(0, dtype=np.int64)
            for k in sutunlar}


def _hazirla(girdi, crm_ham, olay_gunleri: set) -> _Hazir:
    dunya, ham = girdi.dunya, girdi.ham
    opt = dunya.optionlar
    O = len(opt)
    D = girdi.D
    adlar, kat, arama = listeler(opt)
    tur = np.array([0 if a.startswith("kategori:") else 3 if a.startswith("arama:")
                    else 1 if a == "yeni_gelenler" else 2 for a in adlar], dtype=np.int8)
    sku_opt = pd.Index(opt["option_id"]).get_indexer(dunya.urunler["option_id"]).astype(np.int64)
    assert (sku_opt >= 0).all()
    onl = crm_ham.nufus.magaza.onl

    satin = np.zeros((D, O), dtype=np.int32)
    fis_sayisi = np.zeros(D, dtype=np.int64)
    kayit = crm_ham.kayit
    olay_satir, olay_fis = {}, {}
    for d in range(crm_ham.D):
        fis = _birlestir(kayit.gun_parcalari("fis", d), ("fis_id", "magaza", "musteri", "tip", "saat"))
        s = (fis["magaza"] == onl) & (fis["tip"] == 0)
        if not s.any():
            continue
        fid = fis["fis_id"][s].astype(np.int64)
        o = np.argsort(fid)
        fid = fid[o]
        fis_sayisi[d] = len(fid)
        sat = _birlestir(kayit.gun_parcalari("fis_satir", d), ("fis_id", "sku", "adet"))
        sf = sat["fis_id"].astype(np.int64)
        p = np.minimum(np.searchsorted(fid, sf), len(fid) - 1)
        m = (fid[p] == sf) & (sat["adet"] > 0)
        so = sku_opt[sat["sku"][m].astype(np.int64)]
        sa = sat["adet"][m].astype(np.int64)
        np.add.at(satin[d], so, sa)
        if d in olay_gunleri:
            olay_fis[d] = {"fis_id": fid, "musteri": fis["musteri"][s][o].astype(np.int64),
                           "saat": fis["saat"][s][o].astype(np.int64)}
            olay_satir[d] = {"fis": p[m], "option": so, "adet": sa}

    ds = ham["depo_stok"]
    dg = ds["gun"].to_numpy(dtype=np.int64)
    da = ds["adet"].to_numpy()
    m = (da > 0) & (dg < D)
    stoklu = np.zeros((D, O), dtype=bool)
    stoklu[dg[m], sku_opt[ds["sku"].to_numpy(dtype=np.int64)[m]]] = True

    f = ham["fiyat"]
    f = f[f["hat"].to_numpy() == 2]
    fg = f["gun"].to_numpy(dtype=np.int64)
    fo = f["option"].to_numpy(dtype=np.int64)
    fr = f["oran"].to_numpy(dtype=float)
    md = np.full((D, O), np.nan, dtype=np.float32)
    anahtar = fg * O + fo
    # aynı (gün, option)'da son kayıt geçerli
    son = len(anahtar) - 1 - np.unique(anahtar[::-1], return_index=True)[1]
    son = son[fg[son] < D]
    md[fg[son], fo[son]] = fr[son]
    md = pd.DataFrame(md).ffill().fillna(0.0).to_numpy(dtype=np.float32)

    ho = np.asarray(dunya.hucre_option, dtype=np.int64)
    onl_var = np.zeros(O, dtype=bool)
    onl_var[ho[np.asarray(dunya.hucre_online)]] = True
    pencere = (opt["lansman_gun"].to_numpy(dtype=np.int64), opt["cikis_gun"].to_numpy(dtype=np.int64), onl_var)

    return _Hazir(O=O, listeler=adlar, kat_liste=kat, arama_liste=arama, liste_turu=tur, satin=satin,
                  fis_sayisi=fis_sayisi, stoklu=stoklu, md_oran=md, penceresi=pencere,
                  z=cekicilik(dunya, ham), tercih=arketip_tercihi(opt), ind_a=arketip_indirim_ortalamasi(),
                  olay_satir=olay_satir, olay_fis=olay_fis)


def arketip_agirligi(nufus, d: int) -> np.ndarray:
    """[A] online etkin (hayatta, online_payi > 0) müşterilerin Σ
    ziyaret_hizi × online_payi."""
    h = _hayatta(nufus, d) & (nufus.online_payi > 0)
    return np.bincount(nufus.arketip[h], weights=(nufus.ziyaret_hizi * nufus.online_payi)[h],
                       minlength=len(S.ARKETIPLER))


def _hayatta(nufus, d: int) -> np.ndarray:
    tg = nufus.terk_gun
    return (nufus.kayit_gun <= d) & ((tg < 0) | (tg > d))


# ---------------------------------------------------------------------------
# Gün
# ---------------------------------------------------------------------------


def _dagit(rng, adet: np.ndarray, h_opt: np.ndarray, w: np.ndarray) -> np.ndarray:
    """`adet[o]` birimi option'ın hücrelerine `w` ile orantılı multinom
    (koşullu binom zinciri; son hücre kalanı alır). Toplam birebir."""
    n = len(h_opt)
    out = np.zeros(n, dtype=np.int64)
    if not n:
        return out
    sira = np.argsort(h_opt, kind="stable")
    ho, ww = h_opt[sira], np.asarray(w, dtype=float)[sira]
    bas = np.r_[0, np.flatnonzero(np.diff(ho)) + 1]
    son = np.r_[bas[1:], n]
    grup = np.repeat(np.arange(len(bas)), son - bas)
    rank = np.arange(n) - bas[grup]
    cs = np.r_[np.cumsum(ww[::-1])[::-1], 0.0]
    kalan_w = cs[:n] - cs[son[grup]]
    kalan = adet[ho[bas]].astype(np.int64).copy()
    for r in range(int(rank.max()) + 1):
        i = np.flatnonzero(rank == r)
        g = grup[i]
        sonuncu = i == son[g] - 1
        p = np.where(kalan_w[i] > 0, ww[i] / np.where(kalan_w[i] > 0, kalan_w[i], 1.0), 0.0)
        p = np.where(sonuncu, 1.0, np.clip(p, 0.0, 1.0))
        x = rng.binomial(kalan[g], p)
        kalan[g] -= x
        out[sira[i]] = x
    assert (kalan == 0).all()
    return out


@dataclass
class GunSonucu:
    """Günün hücreleri (liste, sıra, option, gösterim, tıklama, sepete,
    satın alma, enjekte) ve olay günüyse olay girdileri."""

    liste: np.ndarray
    sira: np.ndarray
    option: np.ndarray
    gosterim: np.ndarray
    tiklama: np.ndarray
    sepete: np.ndarray
    satin_alma: np.ndarray
    enjekte: np.ndarray
    goruntuleme: np.ndarray          # [L] liste görüntülemesi
    olay: dict | None = None         # online_olay.gun_olaylari girdisi


@dataclass
class Hucreler:
    """Gün d'nin deterministik kısmı: listelenen hücreler (enjekte hariç),
    γ [O], liste görüntüleme payı `w_l` [L] ve toplam görüntüleme `V_top`."""

    h_l: np.ndarray
    h_s: np.ndarray
    h_o: np.ndarray
    ilgi: np.ndarray
    w_l: np.ndarray
    V_top: int


def gun_hucreleri(d: int, hz: _Hazir, dunya, nufus, siralama: Callable, w_a: np.ndarray) -> Hucreler:
    """Sıralama, gizli ilgi γ ve görüntüleme payları (rastgelelik yok)."""
    O, L = hz.O, len(hz.listeler)
    lansman, cikis, onl_var = hz.penceresi
    uygun = hz.stoklu[d] & (lansman <= d) & (d <= cikis) & onl_var
    satis7 = hz.satin[max(d - S.SATIS_PENCERE_GUN, 0):d].sum(axis=0, dtype=np.int64)
    kamp = np.asarray(dunya.kampanya_takvimi(d))[nufus.magaza.onl]
    oran = np.maximum(hz.md_oran[d].astype(float), kamp)
    gor = GunGorunum(gun=d, listeler=hz.listeler, kategori_liste=hz.kat_liste.copy(),
                     arama_liste=hz.arama_liste.copy(), uygun=uygun.copy(), satis7=satis7.copy(),
                     lansman_gun=lansman.copy(), oran=oran.copy())
    sirali = siralama(gor)

    idx = {a: i for i, a in enumerate(hz.listeler)}
    hl, hs, ho = [], [], []
    for ad, dizi in sirali.items():
        dizi = np.asarray(dizi, dtype=np.int64)[:L_UZUN]
        if not len(dizi):
            continue
        assert ad in idx, f"bilinmeyen liste {ad}"
        assert uygun[dizi].all(), f"gün {d}: {ad} listesinde uygun olmayan option"
        assert len(np.unique(dizi)) == len(dizi), f"gün {d}: {ad} listesinde tekrar"
        hl.append(np.full(len(dizi), idx[ad], dtype=np.int64))
        hs.append(np.arange(1, len(dizi) + 1, dtype=np.int64))
        ho.append(dizi)
    h_l = np.concatenate(hl) if hl else np.zeros(0, dtype=np.int64)
    h_s = np.concatenate(hs) if hs else np.zeros(0, dtype=np.int64)
    h_o = np.concatenate(ho) if ho else np.zeros(0, dtype=np.int64)

    # gizli ilgi γ
    z = hz.z[gunun_sezonu(d)]
    u = z[:, None] + hz.tercih + S.ILGI_INDIRIM * hz.ind_a[None, :] * oran[:, None]
    ilgi = np.exp(u) @ (w_a / w_a.sum()) if w_a.sum() > 0 else np.exp(u).mean(axis=1)

    # görüntüleme payları
    tur = hz.liste_turu
    w_l = np.zeros(L)
    dolu = np.bincount(h_l, minlength=L) > 0
    ag = np.bincount(h_l, weights=satis7[h_o] + 1.0, minlength=L)
    for t, ad in ((0, "kategori"), (3, "arama")):
        s_ = (tur == t) & dolu
        if ag[s_].sum() > 0:
            w_l[s_] = S.LISTE_TRAFIK_PAYI[ad] * ag[s_] / ag[s_].sum()
    for t, ad in ((1, "yeni_gelenler"), (2, "indirim")):
        w_l[(tur == t) & dolu] = S.LISTE_TRAFIK_PAYI[ad]
    if w_l.sum() > 0:
        w_l = w_l / w_l.sum()
    V_top = int(round(hz.fis_sayisi[d] * S.GORUNTULEME_FIS))
    return Hucreler(h_l=h_l, h_s=h_s, h_o=h_o, ilgi=ilgi, w_l=w_l, V_top=V_top)


def online_gun(d: int, hz: _Hazir, hc: Hucreler, sabit: float, tohum: int, olay: bool) -> GunSonucu:
    """Gün d'nin liste hücreleri (modül docstring'i); `hc` `gun_hucreleri`,
    `sabit` koşunun tıklama sabiti c."""
    akis = crm_alt_ureticiler(d, "online", GUN_ADIMLARI, tohum)
    O, L = hz.O, len(hz.listeler)
    h_l, h_s, h_o, ilgi = hc.h_l, hc.h_s, hc.h_o, hc.ilgi

    # listede olmayan satın alma → arama:<alt>, sıra 1
    satin = hz.satin[d].astype(np.int64)
    listede = np.zeros(O, dtype=bool)
    listede[h_o] = True
    eksik = np.flatnonzero((satin > 0) & ~listede)
    n_liste = len(h_o)
    h_l = np.r_[h_l, hz.arama_liste[eksik].astype(np.int64)]
    h_s = np.r_[h_s, np.ones(len(eksik), dtype=np.int64)]
    h_o = np.r_[h_o, eksik]
    enj = np.r_[np.zeros(n_liste, dtype=bool), np.ones(len(eksik), dtype=bool)]
    p = tiklama_olasiligi(h_s, ilgi[h_o], sabit)

    # görüntüleme
    V = (akis["goruntuleme"].multinomial(hc.V_top, hc.w_l).astype(np.int64)
         if hc.w_l.sum() > 0 else np.zeros(L, dtype=np.int64))

    # satın alma dağıtımı
    alim = _dagit(akis["dagitim"], satin, h_o, V[h_l] * p)
    assert (np.bincount(h_o, weights=alim, minlength=O).astype(np.int64) == satin).all(), \
        f"gün {d}: satın alma toplamı tutmadı"

    olay_girdi = None
    V_max = np.zeros(L, dtype=np.int64)
    np.maximum.at(V_max, h_l, alim)
    V = np.maximum(V, V_max)
    if olay:
        cift_fis, cift_hucre = _birim_hucre(akis["birim"], hz.olay_satir.get(d), h_o, alim)
        cl = h_l[cift_hucre]
        gerek = np.bincount(np.unique(cift_fis * L + cl) % L, minlength=L)
        V = np.maximum(V, gerek)
        olay_girdi = {"cift_fis": cift_fis, "cift_hucre": cift_hucre, "gerek": gerek,
                      "fis": hz.olay_fis.get(d)}

    # tıklama, sepete
    tik = np.maximum(akis["tiklama"].binomial(V[h_l], p), alim)
    ek = akis["enjekte"].poisson(S.ARAMA_EK_TIKLAMA * alim[enj])
    tik[enj] = alim[enj] + ek
    tmax = np.zeros(L, dtype=np.int64)
    np.maximum.at(tmax, h_l, tik)
    V = np.maximum(V, tmax)
    sep = np.maximum(akis["sepet"].binomial(tik, S.SEPET_ORANI), alim)
    if olay:
        # tarama oturumlarına kalan tıklaması olan listede en az bir tarama görüntülemesi
        n_cift = np.bincount(olay_girdi["cift_hucre"], minlength=len(h_o))
        kalan_tik = np.bincount(h_l, weights=tik - n_cift, minlength=L)
        V = np.where((kalan_tik > 0) & (V - olay_girdi["gerek"] <= 0), olay_girdi["gerek"] + 1, V)
    gos = V[h_l].copy()
    gos[enj] = tik[enj] + akis["enjekte"].poisson(2.0 * tik[enj])
    if olay:
        olay_girdi.update({"h_liste": h_l, "h_sira": h_s, "h_opt": h_o, "tik": tik, "sep": sep,
                           "V": V, "enj": enj})
    return GunSonucu(liste=h_l, sira=h_s, option=h_o, gosterim=gos, tiklama=tik, sepete=sep,
                     satin_alma=alim, enjekte=enj, goruntuleme=V, olay=olay_girdi)


def _birim_hucre(rng, satir: dict | None, h_o: np.ndarray, alim: np.ndarray):
    """Satın alma birimlerini fiş satırlarına bağlar: her option'ın birimleri
    (satır sırasıyla) ile hücre birimleri (rastgele sırayla) eşlenir. Dönen:
    ayrık (fiş, hücre) çiftleri (fiş: günün ONL satış fişi yerel indisi)."""
    if satir is None or not len(satir["option"]):
        assert alim.sum() == 0
        return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int64)
    so, sa, sf = satir["option"], satir["adet"], satir["fis"]
    o1 = np.argsort(so, kind="stable")
    birim_fis = np.repeat(sf[o1], sa[o1])
    birim_opt1 = np.repeat(so[o1], sa[o1])
    hucre = np.repeat(np.arange(len(h_o)), alim)
    ho = h_o[hucre]
    o2 = np.lexsort((rng.random(len(hucre)), ho))
    hucre, ho = hucre[o2], ho[o2]
    assert len(hucre) == len(birim_fis) and (ho == birim_opt1).all()
    anahtar = np.unique(birim_fis * len(h_o) + hucre)
    return anahtar // len(h_o), anahtar % len(h_o)


# ---------------------------------------------------------------------------
# Bütün pencere
# ---------------------------------------------------------------------------


@dataclass(eq=False)
class OnlineCikti:
    """`gunluk` (gun, liste, sira, option, gosterim, tiklama, sepete_ekleme,
    satin_alma; `liste` kategorik), `olay` (online_olay), `gizli`
    (bakılma eğrisi, option × arketip ilgisi, parametreler), `listeler`,
    `sure` (sn)."""

    gunluk: pd.DataFrame
    olay: pd.DataFrame
    gizli: dict
    listeler: tuple
    sure: dict


def tiklama_sabiti(hz: _Hazir, dunya, nufus, gunler, w_a_gun: Callable, onbellek: dict | None = None) -> float:
    """Koşunun tek tıklama sabiti c: Lumoda'nın sıralamasıyla `gunler`de
    Σ_gün Σ_hücre E[görüntüleme] × bakılma × γ × c = `TIKLAMA_GORUNTULEME` ×
    Σ görüntüleme (üst sınır 0,9 yok sayılır). `onbellek` verilirse günlerin
    `Hucreler`'i oraya yazılır (Lumoda koşusu yeniden hesaplamaz)."""
    pay = payda = 0.0
    for d in gunler:
        hc = gun_hucreleri(d, hz, dunya, nufus, lumoda_siralama, w_a_gun(d))
        if onbellek is not None:
            onbellek[d] = hc
        EV = hc.V_top * hc.w_l
        payda += float((EV[hc.h_l] * bakilma(hc.h_s) * hc.ilgi[hc.h_o]).sum())
        pay += hc.V_top
    assert payda > 0, "tıklama sabiti: hiç hücre yok"
    return S.TIKLAMA_GORUNTULEME * pay / payda


def gizli_tablolar(hz: _Hazir, optionlar: pd.DataFrame) -> dict:
    """Bakılma eğrisi ve sezon × option × arketip ilgisi (oran 0; indirim
    terimi ayrıca `ilgi_indirim_katsayisi` × arketip ort. × oran)."""
    sezonlar = np.array(list(a_sabitler.SEZONLAR))
    Sn, O = hz.z.shape
    A = hz.tercih.shape[1]
    ilgi = np.exp(hz.z[:, :, None] + hz.tercih[None, :, :])        # [S, O, A]
    kendi = optionlar["sezon_kodu"].map({k: i for i, k in enumerate(sezonlar)}).to_numpy()
    ss, oo, aa = np.meshgrid(np.arange(Sn), np.arange(O), np.arange(A), indexing="ij")
    tut = pd.isna(kendi)[oo] | (kendi[oo] == ss)
    tut = np.asarray(tut, dtype=bool)
    return {
        "bakilma": pd.DataFrame({"sira": np.arange(1, L_UZUN + 1), "bakilma": bakilma(np.arange(1, L_UZUN + 1))}),
        "bakilma_us": S.BAKILMA_US,
        "ilgi": pd.DataFrame({
            "sezon_kodu": sezonlar[ss[tut]], "option": oo[tut].astype(np.int32),
            "arketip": np.array(S.ARKETIPLER)[aa[tut]], "ilgi": ilgi[tut],
        }),
        "ilgi_indirim_katsayisi": S.ILGI_INDIRIM,
        "arketip_indirim_ortalamasi": dict(zip(S.ARKETIPLER, hz.ind_a.tolist())),
        "tiklama_goruntuleme": S.TIKLAMA_GORUNTULEME,
        "tiklama_ust": S.TIKLAMA_UST,
        "goruntuleme_fis": S.GORUNTULEME_FIS,
        "liste_trafik_payi": dict(S.LISTE_TRAFIK_PAYI),
    }


def online_uret(girdi, crm_ham, tohum: int = S.CRM_TOHUM, siralama: Callable = lumoda_siralama,
                olay_bas: str = "2025-09-01", olay_son: str = "2025-11-30",
                gun_bas: int | None = None, gun_son: int | None = None) -> OnlineCikti:
    """Günlük liste özeti bütün pencerede (2023-01-01 – 2025-12-31; `gun_bas`
    / `gun_son` verilirse o aralık, ikisi dahil), olay kaydı
    [olay_bas, olay_son] içinde. Koşulan gün sayısı `crm_ham.D`'yi aşmaz."""
    from ..tablolar import pencere
    from .online_olay import olay_tablosu, gun_olaylari

    sure: dict = {}
    t = time.perf_counter()
    pb, ps = pencere()
    ps = min(ps, crm_ham.D - 1)
    bas = pb if gun_bas is None else int(gun_bas)
    son = min(ps if gun_son is None else int(gun_son), crm_ham.D - 1)
    ob, os_ = gun_indisi(olay_bas), gun_indisi(olay_son)
    olay_gunleri = set(range(max(ob, bas), min(os_, son) + 1))
    nufus = crm_ham.nufus
    hz = _hazirla(girdi, crm_ham, olay_gunleri)
    dunya = girdi.dunya
    sure["hazirlik"] = time.perf_counter() - t

    # arketip ağırlığı: pencere başından 7 günlük adımlar (koşulan aralıktan bağımsız)
    w_onbellek: dict = {}

    def w_a_gun(d: int) -> np.ndarray:
        g0 = pb + ((d - pb) // 7) * 7
        if g0 not in w_onbellek:
            w_onbellek[g0] = arketip_agirligi(nufus, g0)
        return w_onbellek[g0]

    t = time.perf_counter()
    hucre_onbellek: dict = {}
    sabit = tiklama_sabiti(hz, dunya, nufus, range(pb, ps + 1), w_a_gun,
                           hucre_onbellek if siralama is lumoda_siralama else None)
    sure["tiklama_sabiti"] = time.perf_counter() - t

    parca = {k: [] for k in ("gun", "liste", "sira", "option", "gosterim", "tiklama", "sepete_ekleme",
                             "satin_alma")}
    enj_parca, ilgi_parca = [], []
    olaylar = []
    oturum_ofset = 0
    t_gun = t_olay = 0.0
    for d in range(bas, son + 1):
        t0 = time.perf_counter()
        hc = hucre_onbellek.pop(d, None)
        if hc is None:
            hc = gun_hucreleri(d, hz, dunya, nufus, siralama, w_a_gun(d))
        g = online_gun(d, hz, hc, sabit, tohum, d in olay_gunleri)
        sira = np.lexsort((g.option, g.sira, g.liste))
        n = len(sira)
        parca["gun"].append(np.full(n, d, dtype=np.int16))
        parca["liste"].append(g.liste[sira].astype(np.int16))
        parca["sira"].append(g.sira[sira].astype(np.int16))
        parca["option"].append(g.option[sira].astype(np.int32))
        parca["gosterim"].append(g.gosterim[sira].astype(np.int32))
        parca["tiklama"].append(g.tiklama[sira].astype(np.int32))
        parca["sepete_ekleme"].append(g.sepete[sira].astype(np.int32))
        parca["satin_alma"].append(g.satin_alma[sira].astype(np.int32))
        e = np.flatnonzero(g.enjekte)
        enj_parca.append((np.full(len(e), d), g.liste[e], g.sira[e], g.option[e]))
        uo = np.unique(g.option)
        ilgi_parca.append((np.full(len(uo), d), uo, hc.ilgi[uo]))
        t1 = time.perf_counter()
        t_gun += t1 - t0
        if g.olay is not None:
            ol = gun_olaylari(d, g.olay, nufus, tohum, oturum_ofset)
            oturum_ofset += ol["oturum_sayisi"]
            olaylar.append(ol)
            t_olay += time.perf_counter() - t1
    hucre_onbellek.clear()
    sure["gunluk"] = t_gun
    sure["olay"] = t_olay

    t = time.perf_counter()
    gunluk = pd.DataFrame({k: np.concatenate(v) if v else np.zeros(0) for k, v in parca.items()})
    gunluk["liste"] = pd.Categorical.from_codes(gunluk["liste"].to_numpy(), categories=list(hz.listeler))
    toplam = int(gunluk["satin_alma"].sum())
    beklenen = int(hz.satin[bas:son + 1].sum())
    assert toplam == beklenen, f"satın alma toplamı {toplam} ≠ ONL fiş satırları {beklenen}"
    olay = olay_tablosu(olaylar, hz.listeler)
    gizli = gizli_tablolar(hz, dunya.optionlar)
    gizli["tiklama_sabiti"] = sabit

    def birles(parcalar, i, tip):
        return np.concatenate([p[i] for p in parcalar]).astype(tip) if parcalar else np.zeros(0, tip)

    gizli["enjekte"] = pd.DataFrame({
        "gun": birles(enj_parca, 0, np.int16),
        "liste": pd.Categorical.from_codes(birles(enj_parca, 1, np.int16), categories=list(hz.listeler)),
        "sira": birles(enj_parca, 2, np.int16), "option": birles(enj_parca, 3, np.int32),
    })
    gizli["ilgi_gunluk"] = pd.DataFrame({"gun": birles(ilgi_parca, 0, np.int16),
                                         "option": birles(ilgi_parca, 1, np.int32),
                                         "ilgi": birles(ilgi_parca, 2, np.float64)})
    gz = sorted(w_onbellek)
    gizli["arketip_agirligi"] = pd.DataFrame({
        "adim_gun": np.repeat(gz, len(S.ARKETIPLER)),
        "arketip": np.tile(S.ARKETIPLER, len(gz)),
        "agirlik": np.concatenate([w_onbellek[g] / w_onbellek[g].sum() for g in gz]) if gz else np.zeros(0),
    })
    sure["birlestir"] = time.perf_counter() - t
    return OnlineCikti(gunluk=gunluk, olay=olay, gizli=gizli, listeler=hz.listeler, sure=sure)
