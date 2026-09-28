"""Görev 9: online olay kaydı (spec §5, `online_olay`; pencere 2025-09-01 –
2025-11-30). Günlük liste özetinin (`online.online_gun`) olay düzeyine
açılmış hâlidir: olay günlerinde her hücrenin tıklama ve sepete ekleme
sayısı, her listenin görüntüleme sayısı olay kaydındaki sayıyla birebir
aynıdır; her ONL satış fişi için tam bir `siparis` olayı vardır.

**Sipariş oturumları.** Günün her ONL satış fişi bir oturumdur (giriş
yapmış, müşteri = fişin sahibi). Fişin satın alma birimlerinin düştüğü her
(liste) için bir liste görüntüleme, her (hücre) için bir tıklama ve bir
sepete ekleme; en sonda `siparis` (fiş_id'li; `liste`, `sira`, `option`
boş). Sipariş anı fişin saat dakikası + düzgün saniye; önceki olaylar
geriye doğru üstel aralıklarla (gün başını geçerse sıkıştırılır).

**Tarama oturumları.** Günlük oturum = görüntüleme / 3; sipariş oturumları
dışındaki oturumlar kalan görüntülemeleri 1–6'lık oturumlara (rastgele
boyut, toplam birebir) paylaşır; liste görüntülemeleri rastgele yerleşir.
Kalan tıklamalar aynı listenin rastgele bir tarama görüntülemesine,
kalan sepete eklemeler aynı hücrenin rastgele tıklamalarına bağlanır.
Başlangıç ONL fiş saati dağılımından (`ayristir.fis_saati`), olaylar arası
üstel `OLAY_ARALIK_SN`.

**Giriş.** Bütün oturumların `GIRIS_PAYI`'na (%60) ulaşacak kadar tarama
oturumu giriş yapmıştır; müşteri, o gün hayatta, online_payi > 0 ve o güne
kadar görünür (kimlikli) olmuş müşterilerden ziyaret_hizi × online_payi
ağırlığıyla (yerine koyarak) çekilir. Anonim oturumda müşteri −1.

Oturum kimliği: günler sırayla, gün içinde başlangıç anına göre.
"""

import numpy as np
import pandas as pd

from .. import sabitler as a_sabitler
from . import sabitler as S
from .ayristir import fis_saati
from .online import GUN_ADIMLARI, _hayatta
from .rastgele import crm_alt_ureticiler

OLAY_ADIMLARI = ("oturum", "atama", "giris", "zaman")   # yeni adım SONA
OLAY_TIPLERI = ["liste_goruntuleme", "tiklama", "sepete_ekleme", "siparis"]
GUN_SN = 86400
TABAN_SN = int(np.datetime64(a_sabitler.ISINMA_BASLANGIC, "s").astype(np.int64))


def _boyutlar(rng, N: int, R: int) -> np.ndarray:
    """Toplamı R olan N oturum boyutu, her biri 1–OTURUM_EN_COK."""
    E = S.OTURUM_EN_COK
    assert N <= R <= E * N
    q = min(max((R / N - 1.0) / (E - 1), 0.0), 1.0)
    b = 1 + rng.binomial(E - 1, q, size=N)
    fark = R - int(b.sum())
    while fark:
        uygun = np.flatnonzero(b < E) if fark > 0 else np.flatnonzero(b > 1)
        sec = rng.choice(uygun, size=min(abs(fark), len(uygun)), replace=False)
        b[sec] += 1 if fark > 0 else -1
        fark = R - int(b.sum())
    return b


def _grup_sirasi(grup: np.ndarray) -> np.ndarray:
    """Sıralı `grup` dizisinde her elemanın grup içindeki sırası."""
    n = len(grup)
    if not n:
        return np.zeros(0, dtype=np.int64)
    bas = np.r_[0, np.flatnonzero(np.diff(grup)) + 1]
    return np.arange(n) - np.repeat(bas, np.diff(np.r_[bas, n]))


def musteri_havuzu(nufus, d: int) -> tuple[np.ndarray, np.ndarray]:
    """Giriş yapabilecek müşteriler ve kümülatif ağırlık."""
    s = (_hayatta(nufus, d) & (nufus.online_payi > 0) & nufus.gorunur_mu
         & (nufus.gorunur_gun <= d))
    k = np.flatnonzero(s)
    return k, np.cumsum(nufus.ziyaret_hizi[k] * nufus.online_payi[k])


def gun_olaylari(d: int, g: dict, nufus, tohum: int, ofset: int) -> dict:
    """Gün d'nin olayları (modül docstring'i). `g` `online_gun`'ün olay
    girdisi. Dönen sözlük olay sütunları (oturum sırasında) ve
    `oturum_sayisi`."""
    akis = crm_alt_ureticiler(d, "online", GUN_ADIMLARI + OLAY_ADIMLARI, tohum)
    fis = g["fis"] or {"fis_id": np.zeros(0, np.int64), "musteri": np.zeros(0, np.int64),
                       "saat": np.zeros(0, np.int64)}
    F = len(fis["fis_id"])
    h_l, h_s, h_o = g["h_liste"], g["h_sira"], g["h_opt"]
    tik, sep, V, gerek = g["tik"], g["sep"], g["V"], g["gerek"]
    cf, ch = g["cift_fis"], g["cift_hucre"]
    L, H = len(V), len(h_o)
    assert F == 0 or np.array_equal(np.unique(cf), np.arange(F)), f"gün {d}: alımı olmayan ONL fişi"

    # --- sipariş oturumları ------------------------------------------------
    r_at = akis["atama"]
    v_anahtar = np.unique(cf * L + h_l[ch])
    vf, vl = v_anahtar // L, v_anahtar % L
    v_k1 = r_at.random(len(vf))
    c_view = np.searchsorted(v_anahtar, cf * L + h_l[ch])
    c_k2 = r_at.random(len(cf))
    sip = {
        "s": [vf, cf, cf, np.arange(F)],
        "k1": [v_k1, v_k1[c_view], v_k1[c_view], np.full(F, 2.0)],
        "k2": [np.full(len(vf), -1.0), c_k2, c_k2, np.zeros(F)],
        "k3": [np.zeros(len(vf)), np.zeros(len(cf)), np.ones(len(cf)), np.zeros(F)],
        "tip": [np.zeros(len(vf)), np.ones(len(cf)), np.full(len(cf), 2), np.full(F, 3)],
        "liste": [vl, h_l[ch], h_l[ch], np.full(F, -1)],
        "sira": [np.full(len(vf), -1), h_s[ch], h_s[ch], np.full(F, -1)],
        "option": [np.full(len(vf), -1), h_o[ch], h_o[ch], np.full(F, -1)],
        "fis": [np.full(len(vf), -1), np.full(len(cf), -1), np.full(len(cf), -1), fis["fis_id"]],
    }

    # --- tarama oturumları -------------------------------------------------
    r_ot = akis["oturum"]
    V_kalan = V - gerek
    assert (V_kalan >= 0).all()
    R = int(V_kalan.sum())
    N_top = int(round(V.sum() / S.OTURUM_GORUNTULEME))
    N_b = int(min(max(N_top - F, -(-R // S.OTURUM_EN_COK)), R))
    boy = _boyutlar(r_ot, N_b, R) if N_b else np.zeros(0, dtype=np.int64)
    b_s = np.repeat(np.arange(N_b), boy)
    b_j = _grup_sirasi(b_s).astype(float)
    b_l = r_ot.permutation(np.repeat(np.arange(L), V_kalan))

    n_cift = np.bincount(ch, minlength=H)
    c_kalan = tik - n_cift
    s_kalan = sep - n_cift
    assert (c_kalan >= 0).all() and (s_kalan >= 0).all() and (s_kalan <= c_kalan).all()
    t_h = np.repeat(np.arange(H), c_kalan)
    t_l = h_l[t_h]
    v_sira = np.argsort(b_l, kind="stable")
    v_bas = np.r_[0, np.cumsum(np.bincount(b_l, minlength=L))]
    assert (V_kalan[t_l] > 0).all(), f"gün {d}: tıklamanın tarama görüntülemesi yok"
    t_v = v_sira[v_bas[t_l] + np.floor(r_at.random(len(t_h)) * V_kalan[t_l]).astype(np.int64)]
    t_k2 = r_at.random(len(t_h))
    o = np.lexsort((r_at.random(len(t_h)), t_h))       # hücre içinde rastgele sıra
    rank = np.empty(len(t_h), dtype=np.int64)
    rank[o] = _grup_sirasi(t_h[o])
    sp = rank < s_kalan[t_h]
    ts = F + b_s[t_v]
    tar = {
        "s": [F + b_s, ts, ts[sp]],
        "k1": [b_j, b_j[t_v], b_j[t_v][sp]],
        "k2": [np.full(R, -1.0), t_k2, t_k2[sp]],
        "k3": [np.zeros(R), np.zeros(len(t_h)), np.ones(int(sp.sum()))],
        "tip": [np.zeros(R), np.ones(len(t_h)), np.full(int(sp.sum()), 2)],
        "liste": [b_l, t_l, t_l[sp]],
        "sira": [np.full(R, -1), h_s[t_h], h_s[t_h][sp]],
        "option": [np.full(R, -1), h_o[t_h], h_o[t_h][sp]],
        "fis": [np.full(R, -1), np.full(len(t_h), -1), np.full(int(sp.sum()), -1)],
    }
    ev = {k: np.concatenate(sip[k] + tar[k]) for k in sip}
    sira = np.lexsort((ev["k3"], ev["k2"], ev["k1"], ev["s"]))
    ev = {k: v[sira] for k, v in ev.items()}
    N = F + N_b
    s = ev["s"].astype(np.int64)

    # --- zaman ---------------------------------------------------------------
    r_z = akis["zaman"]
    n_ev = len(s)
    aralik = r_z.exponential(S.OLAY_ARALIK_SN, n_ev)
    ilk = np.r_[True, s[1:] != s[:-1]] if n_ev else np.zeros(0, dtype=bool)
    aralik[ilk] = 0.0
    kum = np.cumsum(aralik)
    ilk_i = np.flatnonzero(ilk)
    kum -= np.repeat(kum[ilk_i], np.diff(np.r_[ilk_i, n_ev]))
    T = np.bincount(s, weights=aralik, minlength=N)
    bas = np.zeros(N)
    olcek = np.ones(N)
    if F:
        sip_an = fis["saat"] * 60.0 + r_z.integers(0, 60, F)
        bas[:F] = sip_an - T[:F]
        kisa = bas[:F] < 0
        olcek[:F][kisa] = sip_an[kisa] / T[:F][kisa]
        bas[:F][kisa] = 0.0
    if N_b:
        b0 = fis_saati(r_z, d, np.ones(N_b, dtype=bool)) * 60.0 + r_z.integers(0, 60, N_b)
        Tb = T[F:]
        b0 = np.where(b0 + Tb > GUN_SN - 1, np.maximum(GUN_SN - 1 - Tb, 0.0), b0)
        olcek[F:] = np.where(Tb > GUN_SN - 1, (GUN_SN - 1) / np.maximum(Tb, 1.0), 1.0)
        bas[F:] = b0
    zaman = bas[s] + kum * olcek[s]
    siparis = ev["tip"] == 3
    if F:
        zaman[siparis] = sip_an[s[siparis]]
    zaman = np.floor(zaman).astype(np.int64)

    # --- giriş -------------------------------------------------------------
    r_g = akis["giris"]
    musteri = np.full(N, -1, dtype=np.int64)
    musteri[:F] = fis["musteri"]
    n_log = int(min(max(round(S.GIRIS_PAYI * N) - F, 0), N_b))
    k, kw = musteri_havuzu(nufus, d)
    if n_log and len(k):
        sec = F + r_g.permutation(N_b)[:n_log]
        musteri[sec] = k[np.minimum(np.searchsorted(kw, r_g.random(n_log) * kw[-1], side="right"), len(k) - 1)]

    # --- oturum kimliği: başlangıç anına göre ----------------------------------
    ilk_an = np.full(N, np.iinfo(np.int64).max)
    np.minimum.at(ilk_an, s, zaman)
    sira_s = np.argsort(ilk_an, kind="stable")
    yeni = np.empty(N, dtype=np.int64)
    yeni[sira_s] = np.arange(N)
    e_id = yeni[s]
    o = np.argsort(e_id, kind="stable")
    return {
        "oturum_id": ofset + e_id[o],
        "musteri": musteri[s][o],
        "zaman": ((TABAN_SN + d * GUN_SN + zaman[o]) * 1_000_000_000).astype(np.int64),
        "olay_tipi": ev["tip"][o].astype(np.int8),
        "liste": ev["liste"][o].astype(np.int16),
        "sira": ev["sira"][o].astype(np.int16),
        "option": ev["option"][o].astype(np.int32),
        "fis_id": ev["fis"][o].astype(np.int64),
        "oturum_sayisi": N,
    }


def olay_tablosu(olaylar: list[dict], listeler) -> pd.DataFrame:
    """Günlerin olaylarını tek tabloya: oturum_id, musteri (−1 anonim),
    zaman, olay_tipi, liste (siparişte boş), sira, option (−1 boş),
    fis_id (yalnız siparişte, yoksa −1)."""
    tipler = {"oturum_id": np.int64, "musteri": np.int64, "zaman": np.int64, "olay_tipi": np.int8,
              "liste": np.int16, "sira": np.int16, "option": np.int32, "fis_id": np.int64}
    sutun = {}
    for k, t in tipler.items():   # sütun sütun birleştir, günlük parçayı hemen bırak (tepe bellek)
        sutun[k] = (np.concatenate([o.pop(k) for o in olaylar]).astype(t, copy=False)
                    if olaylar else np.zeros(0, dtype=t))
    df = pd.DataFrame({
        "oturum_id": sutun.pop("oturum_id"),
        "musteri": sutun.pop("musteri"),
        "zaman": sutun.pop("zaman").view("datetime64[ns]"),
        "olay_tipi": pd.Categorical.from_codes(sutun.pop("olay_tipi"), categories=OLAY_TIPLERI),
        "liste": pd.Categorical.from_codes(sutun.pop("liste"), categories=list(listeler)),
        "sira": sutun.pop("sira"),
        "option": sutun.pop("option"),
        "fis_id": sutun.pop("fis_id"),
    }, copy=False)
    return df
