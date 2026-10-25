"""Uzmanın kuralı (tasarım §0, K8 `kural` satırı ve K20). Karar modülü: yalnız açık bilgi (karar günü girdisi).

**Puan.** Option içinde her mağazanın pencere satışı sıralanır (büyük satış = yüksek sıra, eşit satış ortalama
sıra; satışsızlar ortak en alt sıra); puan pencerelerin sıralarının ortalamasıdır. Pencereler `std` (option'ın
lansmanından karar gününe) ve karardan önceki 7, 14, 28 gündür; yalnız pozitif satış satırları sayılır. Sıralanan
küme option'ın hücredeki bütün mağazalarıdır. Eşitlikte `magaza_id` artan.

**Kural (K20).** Option başına, karar sabahı fotoğrafında: (a) kırık çiftler puana göre büyükten küçüğe;
(b) sırayla her uygun aday, verici olarak işaretlenmemişse alıcı olarak denenir; (c) verici havuzu option'ın,
alıcı ya da verici olarak işaretlenmemiş öteki kırık çiftleridir (çift uygun olmasa da mağaza uygunsa), en düşük
puanlı önce; (d) ihtiyaç alıcının kırık ve asorti altındaki doldurulamaz bedenleridir, verici yalnız bu
bedenlerden kendi fotoğraf stoğu kadar verir; (e) her kırık beden en az bire çıkamıyorsa alıcı atlanır, hareket
yazılmaz ve çift havuzda kalır, çıkıyorsa bedenler asorti adedine kadar arz yettiğince doldurulur ve hareketin
kaynağı çiftler verici işaretlenir; (f) adaylar bitene kadar sürer. Maliyete bakılmaz.
"""

from collections.abc import Iterable
from datetime import timedelta

import numpy as np
import pandas as pd

from kiriklik import plan, uygunluk
from kiriklik.kaynak import KararGirdisi

PENCERELER = ("std", 7, 14, 28)
_SIRALAR = (1, 2, 3, 4, 5)


def _pencereler_dogrula(pencereler: Iterable) -> tuple:
    pencereler = tuple(pencereler)
    if not pencereler:
        raise ValueError("en az bir pencere gerekir")
    for w in pencereler:
        if w != "std" and not (isinstance(w, (int, np.integer)) and not isinstance(w, bool) and w > 0):
            raise ValueError(f"pencere 'std' ya da pozitif gün sayısı olmalı: {w!r}")
    return pencereler


def puanlar(g: KararGirdisi, pencereler: tuple = PENCERELER) -> pd.DataFrame:
    """Hücredeki her (mağaza, option) çifti için [magaza_id, option_id, puan]: option içinde her pencerenin
    satış toplamının sırası (büyük satış yüksek sıra, eşitler ortalama sıra), puan sıraların ortalaması.
    `std` = option'ın lansmanından karar gününe (karar günü hariç); N = karardan önceki N gün (N gün önceki
    gün içeride). Yalnız pozitif satış satırları (iade satırları sayılmaz)."""
    pencereler = _pencereler_dogrula(pencereler)
    cift = g.hucre[["magaza_id", "option_id"]].drop_duplicates().reset_index(drop=True)
    if cift.empty:
        return cift.assign(puan=pd.Series(dtype="float64"))
    karar = pd.Timestamp(g.karar)
    if g.satis.empty:
        s = pd.DataFrame({"magaza_id": [], "option_id": [], "tarih": pd.to_datetime([]), "adet": []})
    else:
        s = g.satis.loc[g.satis.adet > 0, ["magaza_id", "urun_id", "tarih", "adet"]].copy()
        s["tarih"] = pd.to_datetime(s.tarih)
        s = s[s.tarih < karar]
        s = s.merge(g.hucre[["urun_id", "option_id"]].drop_duplicates("urun_id"), on="urun_id")
    if "std" in pencereler and "lansman_tarihi" not in g.optionlar:
        raise KeyError("std penceresi için optionlar'da lansman_tarihi gerekir")
    lansman = (pd.to_datetime(g.optionlar.set_index("option_id").lansman_tarihi)
               if "std" in pencereler else None)
    siralar = []
    for w in pencereler:
        if w == "std":
            baslangic = s.option_id.map(lansman)
            ic = s[baslangic.isna() | (s.tarih >= baslangic)]
        else:
            ic = s[s.tarih >= karar - timedelta(days=int(w))]
        toplam = ic.groupby(["magaza_id", "option_id"], observed=True).adet.sum()
        satis = cift.join(toplam.rename("satis"), on=["magaza_id", "option_id"])["satis"].fillna(0.0)
        siralar.append(satis.groupby(cift.option_id).rank(method="average"))
    cift["puan"] = pd.concat(siralar, axis=1).mean(axis=1).astype("float64")
    return cift


def kural_plani(g: KararGirdisi, pencereler: tuple = PENCERELER, kol: str = "kural") -> plan.Plan:
    """Uzmanın kuralıyla transfer planı (K20 a–f; modül belgesi). Vericisi olmayan option boş hareket verir.
    `bilgi`: pencereler, puanlar (liste), tamamlanan ve atlanan alıcılar ([option_id, magaza_id] listeleri)."""
    pencereler = _pencereler_dogrula(pencereler)
    puan_tablosu = puanlar(g, pencereler)
    puan = dict(zip(zip(puan_tablosu.magaza_id, puan_tablosu.option_id), puan_tablosu.puan))
    aday = uygunluk.adaylar(g)
    ih = uygunluk.ihtiyac_tablosu(g)
    ihtiyac = {}
    for (m, o), alt in ih.groupby(["magaza_id", "option_id"], sort=False):
        v = np.zeros(len(_SIRALAR), dtype=np.int64)
        v[alt.beden_sira.to_numpy() - 1] = alt.ihtiyac.to_numpy()
        ihtiyac[(m, o)] = v
    stok = (g.hucre.pivot_table(index=["magaza_id", "option_id"], columns="beden_sira", values="stok",
                                aggfunc="sum", fill_value=0).reindex(columns=list(_SIRALAR), fill_value=0))
    stok = {k: v for k, v in zip(stok.index, stok.to_numpy(dtype=np.int64))}
    urun = g.hucre.drop_duplicates(["option_id", "beden_sira"]).set_index(["option_id", "beden_sira"]).urun_id

    satirlar, tamamlanan, atlanan = [], [], []
    for option, alt in aday.groupby("option_id", sort=True):
        puan_o = {m: puan[(m, option)] for m in alt.magaza_id}
        havuz = [m for m, n in sorted(zip(alt.magaza_id, alt.neden), key=lambda t: (puan_o[t[0]], t[0]))
                 if n != "magaza"]
        alicilar = sorted(alt.magaza_id[alt.uygun], key=lambda m: (-puan_o[m], m))
        isaretli: set[str] = set()
        for alici in alicilar:
            if alici in isaretli:                                                # verici oldu: alıcı olamaz
                continue
            kalan = ihtiyac[(alici, option)].copy()
            kirik = stok[(alici, option)] == 0
            adaylar_ = [d for d in havuz if d not in isaretli and d != alici]
            arz = np.zeros(len(_SIRALAR), dtype=np.int64)
            for d in adaylar_:
                arz += np.where(kalan > 0, stok[(d, option)], 0)
            if not (arz[kirik] >= 1).all():
                atlanan.append([option, alici])                                  # tamamlanamaz: dokunulmaz
                continue
            verenler = set()
            for d in adaylar_:
                ver = np.minimum(kalan, stok[(d, option)])
                if ver.sum() == 0:
                    continue
                for i in np.nonzero(ver)[0]:
                    satirlar.append((option, urun[(option, _SIRALAR[i])], _SIRALAR[i], d, alici, int(ver[i])))
                kalan -= ver
                verenler.add(d)
            isaretli.add(alici)
            isaretli |= verenler
            tamamlanan.append([option, alici])
    if satirlar:
        hareket = pd.DataFrame(satirlar, columns=plan.KOLONLAR)
        hareket = (hareket.astype({"beden_sira": "int64", "adet": "int64"})
                   .sort_values(["option_id", "alici", "verici", "beden_sira"], kind="mergesort")
                   .reset_index(drop=True))
    else:
        hareket = plan.bos(kol, g.sezon, {}).hareketler
    bilgi = {"pencereler": [w if w == "std" else int(w) for w in pencereler],"cozum": "kural", "tamamlanan_alicilar": tamamlanan,
             "atlanan_alicilar": atlanan,
             "puanlar": puan_tablosu.to_dict("records")}
    return plan.Plan(kol=kol, sezon=g.sezon, hareketler=hareket, bilgi=bilgi)
