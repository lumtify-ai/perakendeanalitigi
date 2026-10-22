"""Vakanın ölçüm tarafı: Lumoda'nın giden paketi, ns dönüşümü, korunum, pakete duyarlı ölçütler,
İlk Sevkiyat önbelleği (salt okunur), doğrulama komutu (spec §0/5–7, §0/11, §0/16, §4.2).

    ns = lumoda_giden(kos_dogrulama(0))                     # Lumoda'nın giden paketi (option, mağaza)
    k = kos("p2", desenler, atama, ns)                       # simülasyon (`simulasyon.kos`)
    olc(k)                                                   # İlk Sevkiyat ölçütleri + paket ölçütleri

    .venv/Scripts/python -m beden_paket.kosucu dogrulama [--yol P] [--olcek tam|kucuk]

Bu modül ölçüm tarafındadır (`tests/test_sizinti.py`'de izinli): `perakende_veri`'yi ve İlk
Sevkiyat'ın motorunu ve ölçütlerini içe aktarır. Karar modülleri (`politika` dahil) bunu aktarmaz.

**Simülasyon ayrı** (Ruling R14). Koşu, dünya kopyası, politikalar ve önbellek anahtarı
`beden_paket.simulasyon`'dadır (`kos`, `hazirla`, `kos_dogrulama` kolaylık için buradan da aynı
adlarla alınabilir). Bu modül simülasyon anahtarına girmez: ölçümdeki bir değişiklik önbellekteki
koşuları bozmaz, ölçüm önbellekteki tablolardan yeniden yapılır (`oyun`, ölçüm kodu özeti).

**Ölçüm** (`olc`). İlk Sevkiyat'ın `olcutler.hesapla`'sı (yayımlanan dünyanın açık alanlarıyla;
paket kopyası yalnız `paketler`'de ayrılır) ve pakete duyarlı kayıt ölçütleri (`paket_olcutleri`):
İlk Sevkiyat'ın `kirpilan_adet`'i standart paketi varsayar (`paket_adedi`); vakada

    kirpilan_adet    Σ (istenen − giden paket) × seçilen paketin adedi (`motor.kirpma_tablosu`,
                     oyun option'ları; seçilen paket `kayitlar["paket_secimi"]`'nden, kayıt yoksa
                     setin standart paketi). 7'li paketlerde İlk Sevkiyat'ınkiyle aynı sayı
    kirpilan_hucre   kırpılan (option, mağaza) çifti
    kirpilan_option  en az bir çifti kırpılan oyun option'ı
    istenen_adet     Σ istenen paket × seçilen paketin adedi; kırpmayla aynı kapsam: sevkleri bütünüyle
                     koşunun penceresinde olan oyun option'ları (`kiyas_optionlari`, `kirpma_tablosu`'nun
                     kuralı). Tam pencerede bütün oyun option'larıdır ve istenen − giden = kırpılan
    paket_tipi       oyun option'larının ilk dağıtımında beş bedenli setlere giden ayrı beden deseni
                     sayısı (paket kimliği değil: aynı desen her sete ayrı `paket_id`'yle eklenir;
                     aksesuarın tek bedenli paketi desen değildir, sayılmaz). Lumoda 1, P1 1, P2 2

ve ilk 4 hafta beden ölçütleri (`ilk4_beden_olcutleri`, Ruling R19; başlık ölçütleri ilk haftalardır,
spec §0/12): İlk Sevkiyat'ın `kirik_cift_pay_yuzde`, `beden_kayip_payi` ve `stoklu_cift_gun`'ü aynı
yöntemle (`olcutler._beden`, günlük tablo `olcutler._gunluk` aynı aralıkla), pencere
`bulunabilirlik_ilk4`'ünki: option'ın ilk varışından `ILK4_GUN` (28) gün, çıkışla kesilir,
[b_o, min(b_o + 28, c_o)). Adları `_ilk4` ekli.

Doğrulama kolunda (`ns=None`, standart paket) bütün İlk Sevkiyat ölçütleri İlk Sevkiyat'ın `lumoda`
koşusunun ölçütleriyle birebir aynıdır (`test_dogrulama_kucuk`; TAM'da `python -m beden_paket.kosucu
dogrulama`). Paket kollarında aynı mal: oyun (option, mağaza) başına giden adet Lumoda'nın giden
adedine eşit, kırpma 0 (`korunum`).

**Lumoda'nın giden paketi** (`lumoda_giden`): bir koşunun `sevkiyat`'ının `ilk_dagitim` satırları;
paket sayısı = beden adedi ÷ paketin (`paket_id`, koşunun `paket` tablosu) o bedendeki içeriği. 12'li
kollar için `ns_donustur` (adet ÷ 12, option toplamı en büyük kalanla mağazalara) ve
`donusum_ozeti` (adet farkı, sıfıra düşen çift).

**Yollar.** `lumoda_ns(p)`: yolun Lumoda `ns`'i; İlk Sevkiyat'ın önbellekli `lumoda` / `y<p>_lumoda`
koşusu salt okunur açılabiliyorsa ondan, yoksa vakanın o yoldaki doğrulama kolundan. Izgara (`oyun`)
yolun ns'ini her zaman vakanın kendi doğrulama kolundan alır.

**Doğrulama komutu** (`dogrula`). Doğrulama kolunu koşar ya da önbellekten okur; giden paketi
İlk Sevkiyat'ın önbellekli Lumoda koşusuyla, ölçütleri İlk Sevkiyat'ın kayıtlı ölçütleriyle
(`oyun.json` / `yollar.json`) kıyaslar. İkisinden biri yoksa (önbellek ya da kayıt) kıyas yapılmış
sayılmaz, çıkış 1.
"""

import argparse
import copy
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from allocation import kaynak as al_kaynak
from allocation import motor
from allocation import olcutler as al_olcutler
from allocation import oyun as al_oyun
from perakende_veri.v4 import sabitler as v4_sabitler
from perakende_veri.v4.plan import en_buyuk_kalan

from beden_paket import politika, simulasyon
from beden_paket.simulasyon import (KOSU_DIZINI, OYUN_SEZONU, Hazirlik, PaketKaydi,  # noqa: F401 (kolaylık)
                                    dogrulama_adi, dunya_kopyasi, hazirla, kos, kos_dogrulama,
                                    oyun_optionlari)


# ---------------------------------------------------------------------------
# Giden paket, ns dönüşümü, korunum
# ---------------------------------------------------------------------------


def _tablo(k, ad: str, sutunlar) -> pd.DataFrame:
    if hasattr(k, "tablo"):
        return k.tablo(ad, sutunlar=list(sutunlar))
    return k[ad][list(sutunlar)].reset_index(drop=True)


ILK_DAGITIM_SUTUNLARI = ["option_id", "magaza_id", "paket_id", "paket", "adet"]


def ilk_dagitim_tablosu(kosu_tablolari) -> pd.DataFrame:
    """İlk dağıtım sevkleri (option, mağaza, paket_id) başına giden paket ve adet. Paket = beden
    adedi ÷ paketin o bedendeki içeriği (koşunun `paket` tablosu); adet içeriğin katı değilse ya da
    bir sevkin bedenleri farklı paket sayısı verirse `RuntimeError`. `kosu_tablolari`: `Kosu`,
    `KosuKaydi` ya da `sevkiyat`, `urun`, `paket` tablolarının sözlüğü."""
    s = _tablo(kosu_tablolari, "sevkiyat", ["tarih", "hedef", "urun_id", "adet", "tip", "paket_id"])
    s = s[(s["tip"].astype(str) == "ilk_dagitim").to_numpy()]
    if not len(s):
        return pd.DataFrame({c: pd.Series([], dtype=object if c.endswith("_id") else np.int64)
                             for c in ILK_DAGITIM_SUTUNLARI})
    u = _tablo(kosu_tablolari, "urun", ["urun_id", "option_id", "beden_sira"])
    u = u.set_index(u["urun_id"].astype(str))
    p = _tablo(kosu_tablolari, "paket", ["paket_id", "beden_sira", "adet"])
    urun = s["urun_id"].astype(str)
    t = pd.DataFrame({
        "tarih": s["tarih"].to_numpy(),
        "option_id": urun.map(u["option_id"].astype(str)).to_numpy(),
        "magaza_id": s["hedef"].astype(str).to_numpy(),
        "paket_id": s["paket_id"].astype(str).to_numpy(),
        "beden_sira": urun.map(u["beden_sira"]).to_numpy(dtype=np.int64),
        "adet": s["adet"].to_numpy(dtype=np.int64),
    })
    p = pd.DataFrame({"paket_id": p["paket_id"].astype(str).to_numpy(),
                      "beden_sira": p["beden_sira"].to_numpy(dtype=np.int64),
                      "icerik": p["adet"].to_numpy(dtype=np.int64)})
    t = t.merge(p, on=["paket_id", "beden_sira"], how="left")
    ic = t["icerik"].fillna(0).to_numpy(dtype=np.int64)
    if (ic <= 0).any() or (t["adet"].to_numpy() % np.maximum(ic, 1) != 0).any():
        raise RuntimeError("ilk dağıtım sevki paket içeriğinin katı değil (paket ↔ sevkiyat tutmuyor)")
    t["paket"] = t["adet"].to_numpy() // ic
    anahtar = ["option_id", "magaza_id", "paket_id"]
    sevk = t.groupby(anahtar + ["tarih"])["paket"].agg(["min", "max"])
    if (sevk["min"] != sevk["max"]).any():
        raise RuntimeError("ilk dağıtım sevkinin bedenleri farklı paket sayısı veriyor: "
                           f"{int((sevk['min'] != sevk['max']).sum())} sevk")
    paket = sevk["min"].groupby(level=anahtar).sum().rename("paket")
    adet = t.groupby(anahtar)["adet"].sum()
    return pd.concat([paket, adet], axis=1).reset_index()[ILK_DAGITIM_SUTUNLARI].astype(
        {"paket": np.int64, "adet": np.int64})


def _sozluk(t: pd.DataFrame, sutun: str) -> dict[tuple[str, str], int]:
    g = t.groupby(["option_id", "magaza_id"])[sutun].sum()
    return {(str(o), str(m)): int(v) for (o, m), v in g.items() if v > 0}


def lumoda_giden(kosu_tablolari) -> dict[tuple[str, str], int]:
    """Bir koşunun (Lumoda'nın) ilk dağıtımında (option_id, magaza_id) başına giden paket sayısı
    (`ilk_dagitim_tablosu`; yalnız pozitif)."""
    return _sozluk(ilk_dagitim_tablosu(kosu_tablolari), "paket")


def giden_adet(kosu_tablolari) -> dict[tuple[str, str], int]:
    """İlk dağıtımda (option_id, magaza_id) başına giden adet (yalnız pozitif)."""
    return _sozluk(ilk_dagitim_tablosu(kosu_tablolari), "adet")


def ns_donustur(giden_adet: dict, paket_adet: int, yuvarlama: str = "yakin") -> dict[tuple[str, str], int]:
    """Adetten `paket_adet`'lik paket sayısına (12'li kollar, R10): option başına toplam ⌊Σ adet ÷
    paket_adet + ½⌋ paket (`yuvarlama` "yakin"; "asagi": ⌊Σ adet ÷ paket_adet⌋, kol Lumoda'dan fazla
    adet istemesin diye, R22), mağazalara adet payıyla en büyük kalanla (v4 `en_buyuk_kalan`; eşitlikte
    magaza_id sırası). Payı 0'a düşen mağaza 0 paket alır (sözlükte yok; `donusum_ozeti` sayar)."""
    a = int(paket_adet)
    if a <= 0:
        raise ValueError(f"paket adedi pozitif olmalı: {paket_adet}")
    if yuvarlama not in ("yakin", "asagi"):
        raise ValueError(f"yuvarlama 'yakin' ya da 'asagi': {yuvarlama!r}")
    option: dict[str, dict[str, int]] = {}
    for (o, m), v in giden_adet.items():
        if int(v) < 0:
            raise ValueError(f"adet negatif olamaz: {(o, m)} → {v}")
        option.setdefault(str(o), {})[str(m)] = int(v)
    ns = {}
    for o, d in sorted(option.items()):
        mag = sorted(d)
        adet = np.array([d[m] for m in mag], dtype=np.int64)
        toplam = (int((2 * int(adet.sum()) + a) // (2 * a)) if yuvarlama == "yakin"   # ⌊Σ/a + ½⌋, tamsayıyla
                  else int(adet.sum()) // a)
        for m, n in zip(mag, en_buyuk_kalan(toplam, adet)):
            if n > 0:
                ns[(o, m)] = int(n)
    return ns


def donusum_ozeti(giden_adet: dict, ns: dict, paket_adet: int, yuvarlama: str = "yakin") -> dict[str, int]:
    """`ns_donustur`'un bedeli: Lumoda'nın ve kolun toplam adedi, fark (kol − Lumoda), adetli çift ve
    paketi 0'a düşen çift sayısı; option başına en büyük |paket_adet × Σ paket − Σ adet| ve sınırı
    (`yuvarlama` "yakin": ⌊paket_adet ÷ 2⌋, option toplamı en yakın tam pakete; "asagi": paket_adet − 1)."""
    a = int(paket_adet)
    lum = {(str(o), str(m)): int(v) for (o, m), v in giden_adet.items() if int(v) > 0}
    kol = int(sum(int(v) for v in ns.values())) * a
    opt_lum: dict[str, int] = {}
    opt_kol: dict[str, int] = {}
    for (o, _), v in lum.items():
        opt_lum[o] = opt_lum.get(o, 0) + v
    for (o, _), v in ns.items():
        opt_kol[str(o)] = opt_kol.get(str(o), 0) + int(v) * a
    en_buyuk = max((abs(opt_kol.get(o, 0) - v) for o, v in opt_lum.items()), default=0)
    return {"lumoda_adet": int(sum(lum.values())), "kol_adet": kol, "fark_adet": kol - int(sum(lum.values())),
            "hucre": len(lum), "sifir_hucre": int(sum(1 for k in lum if int(ns.get(k, 0)) == 0)),
            "option": len(opt_lum), "option_en_buyuk_fark": int(en_buyuk),
            "option_fark_siniri": a // 2 if yuvarlama == "yakin" else a - 1}


def korunum(kosu, referans_adet: dict) -> dict[str, int]:
    """Aynı mal: koşunun ilk dağıtım adedi ile `referans_adet` ((option, mağaza) → adet; ör.
    Lumoda'nın `giden_adet`'i) arasında, referansın option'larında: çift sayısı, farklı çift,
    Σ|fark| ve Σ(kol − referans)."""
    ref = {(str(o), str(m)): int(v) for (o, m), v in referans_adet.items()}
    secili = {o for o, _ in ref}
    kol = {a: v for a, v in giden_adet(kosu).items() if a[0] in secili}
    anahtar = set(ref) | set(kol)
    fark = [kol.get(a, 0) - ref.get(a, 0) for a in anahtar]
    return {"hucre": len(anahtar), "fark_hucre": int(sum(f != 0 for f in fark)),
            "fark_adet": int(sum(abs(f) for f in fark)), "net_fark_adet": int(sum(fark))}


# ---------------------------------------------------------------------------
# Ölçüm
# ---------------------------------------------------------------------------


def _paket_boylari(kosu) -> tuple[np.ndarray, dict[str, int], np.ndarray, pd.DataFrame]:
    """Koşunun `paket` tablosundan (paket_idleri, set → standart indis, [P] paket adedi, içerik
    tablosu paket_id × beden_sira)."""
    p = kosu.tablo("paket", sutunlar=["paket_id", "beden_seti", "beden_sira", "adet"])
    ids, standart = politika.paket_indisleri(p)
    boy = p.groupby("paket_id", sort=False)["adet"].sum().reindex(ids).to_numpy(dtype=np.int64)
    icerik = p.pivot_table(index=p["paket_id"].astype(str), columns="beden_sira", values="adet",
                           aggfunc="sum", fill_value=0)
    return ids, standart, boy, icerik


def kiyas_optionlari(kosu, w) -> np.ndarray:
    """Sevkleri bütünüyle koşunun penceresinde olan option indisleri (`motor.kirpma_tablosu`'nun
    kıyas kuralı, aynen): ilk dağıtım kaydındaki ilk karar günü pencere başında ya da sonra ve
    max(lansman, son karar günü) pencerenin ve koşunun son gününde ya da önce."""
    kayit = kosu.kayitlar["ilk_dagitim"]
    if not len(kayit):
        return np.zeros(0, dtype=np.int64)
    tarih = pd.DatetimeIndex(pd.to_datetime(w.takvim["tarih"]))
    D = min(int(kosu.meta.get("gun_sayisi") or w.gun_sayisi), len(tarih))
    bas, son = pd.Timestamp(v4_sabitler.BASLANGIC), min(pd.Timestamp(v4_sabitler.BITIS), tarih[D - 1])
    karar = kayit.groupby("arg0")["gun"].agg(["min", "max"])
    o = karar.index.to_numpy(dtype=np.int64)
    lansman = pd.DatetimeIndex(pd.to_datetime(w.optionlar["lansman_tarihi"]))[o]
    tam = (tarih[karar["min"].to_numpy()] >= bas) & (np.maximum(lansman, tarih[karar["max"].to_numpy()]) <= son)
    return o[np.asarray(tam)]


def paket_olcutleri(kosu, w) -> dict[str, float]:
    """Pakete duyarlı kayıt ölçütleri (modül notu), oyun option'larında."""
    oyun = oyun_optionlari(w)
    oyun_ids = set(simulasyon.option_idleri(w, oyun))
    O, M = len(w.optionlar), len(w.magazalar)
    ids, standart, boy, icerik = _paket_boylari(kosu)
    seti = w.optionlar["beden_seti"].astype(str).to_numpy()
    secim = np.full((O, M), -1, dtype=np.int64)
    for o in oyun:
        secim[o, :] = standart[seti[o]]
    ps = kosu.kayitlar.get("paket_secimi")
    if ps is not None and len(ps):
        son = ps.sort_values("gun", kind="stable").drop_duplicates(["arg0", "indis"], keep="last")
        secim[son["arg0"].to_numpy(), son["indis"].to_numpy()] = son["deger"].to_numpy()
    adet = np.where(secim >= 0, boy[np.maximum(secim, 0)], 0)

    kiyas = np.intersect1d(oyun, kiyas_optionlari(kosu, w))
    kayit = kosu.kayitlar["ilk_dagitim"]
    k = kayit[np.isin(kayit["arg0"].to_numpy(), kiyas) & (kayit["indis"].to_numpy() >= 0)]
    istenen = np.maximum(k["deger"].to_numpy(dtype=np.int64), 0)
    istenen_adet = int((istenen * adet[k["arg0"].to_numpy(), k["indis"].to_numpy()]).sum())

    kirp = motor.kirpma_tablosu(kosu, w)
    kirp = kirp[kirp["option_id"].isin(oyun_ids)]
    o_idx = pd.Index(w.optionlar["option_id"].astype(str)).get_indexer(kirp["option_id"])
    m_idx = pd.Index(w.magazalar["magaza_id"].astype(str)).get_indexer(kirp["magaza_id"])
    kirpilan = int(((kirp["istenen_paket"] - kirp["giden_paket"]).to_numpy() * adet[o_idx, m_idx]).sum())
    t = ilk_dagitim_tablosu(kosu)
    giden = t.loc[t["option_id"].isin(oyun_ids), "paket_id"].astype(str).unique()
    bes = icerik.loc[[i for i in giden if (icerik.loc[i] > 0).sum() > 1]]
    tip = len({tuple(int(x) for x in r) for r in bes.to_numpy()})
    return {"kirpilan_adet": float(kirpilan), "kirpilan_hucre": float(len(kirp)),
            "kirpilan_option": float(kirp["option_id"].nunique()),
            "istenen_adet": float(istenen_adet), "paket_tipi": float(tip)}


ILK4_GUN = al_olcutler.ILK4_GUN


def ilk4_beden_olcutleri(kosu, w, harita=None, gun: int = ILK4_GUN) -> dict[str, float]:
    """İlk `gun` günün kırık set, beden kaybı payı ve stoklu çift-gün sayısı (modül notu): İlk Sevkiyat'ın
    `_beden`'i, kapsamın çıkış günleri min(çıkış, ilk varış + gun) ile (`_musteri_maskesi`'nin `ufuk`'u
    gibi). Günlük tablo `hesapla`'nınkiyle aynı aralıktan."""
    harita = al_kaynak.harita_kur(w) if harita is None else harita
    k = al_olcutler.Kapsam(w, harita, al_kaynak.oyun_optionlari(w, OYUN_SEZONU))
    adlar = ("kirik_cift_pay_yuzde", "beden_kayip_payi", "stoklu_cift_gun")
    if not len(k.opt):
        return {f"{a}_ilk4": 0.0 for a in adlar}
    sevk = kosu.tablo("sevkiyat", al_olcutler.SEVK, urunler=k.skular)
    bas = al_olcutler.baslangiclar(sevk, k)
    gercek = kosu.tablo("gercek", al_olcutler.GERCEK, urunler=k.skular)
    ilk = al_olcutler._ilk_adet(sevk, k)
    gun_bas = pd.Timestamp(bas[k.opt].min()).date()
    gun_son = (pd.Timestamp(k.cikis[k.opt].max()) - pd.Timedelta(days=1)).date()
    gunluk = al_olcutler._gunluk(kosu, k, gun_bas, gun_son)
    k4 = copy.copy(k)
    k4.cikis = np.minimum(k.cikis, bas + np.timedelta64(int(gun), "D"))
    r = al_olcutler._beden(gunluk, gercek, ilk, k4, bas)
    return {f"{a}_ilk4": float(r[a]) for a in adlar}


def olc(kosu, w=None) -> dict[str, float]:
    """Koşunun ölçütleri: İlk Sevkiyat'ın `olcutler.hesapla`'sı (oyun sezonu), `kirpilan_adet` pakete
    duyarlı olanla değiştirilmiş, ve `paket_olcutleri` (modül notu). `w`: yayımlanan dünya (verilmezse
    koşunun ölçeğinde)."""
    w = motor.dunya(kosu.meta["olcek"]) if w is None else w
    harita = al_kaynak.harita_kur(w)
    sonuc = al_olcutler.hesapla(kosu, w, harita, OYUN_SEZONU)
    return sonuc | paket_olcutleri(kosu, w) | ilk4_beden_olcutleri(kosu, w, harita)


# ---------------------------------------------------------------------------
# İlk Sevkiyat önbelleği (salt okunur) ve yollar
# ---------------------------------------------------------------------------


def allocation_anahtari(yol: int = 0, olcek: str = "tam") -> str:
    """İlk Sevkiyat'ın yol `yol` Lumoda koşusunun (`lumoda` / `y<p>_lumoda`) önbellek anahtarı."""
    return motor.onbellek_anahtari(ad=al_oyun.lumoda_adi(yol), parametreler={},
                                   talep_tohumu=al_oyun.talep_tohumu(yol), operasyon_tohumu=motor.TOHUM,
                                   olcek=str(olcek).lower(), gun_sayisi=None, turler={}, politikalar={})


def allocation_lumoda(yol: int = 0, olcek: str = "tam") -> motor.KosuKaydi | None:
    """İlk Sevkiyat'ın önbellekli Lumoda koşusu, salt okunur ve tembel (`motor.KosuKaydi`); anahtarı
    tutan tam bir kayıt yoksa None. Hiçbir dosyayı yazmaz ya da silmez (`motor._oku_tembel`'in
    aksine)."""
    anahtar = allocation_anahtari(yol, olcek)
    return salt_okunur_kayit(motor._dizin(motor.KOSU_DIZINI, al_oyun.lumoda_adi(yol), anahtar), anahtar)


def salt_okunur_kayit(dizin: Path, anahtar: str) -> motor.KosuKaydi | None:
    """`dizin`'deki koşu kaydı, salt okunur ve tembel; anahtarı tutan tam bir kayıt yoksa None. Hiçbir
    dosyayı yazmaz ya da silmez: başka bir süreç aynı önbelleğe yazarken de güvenli (`motor._oku_tembel`
    ve `simulasyon.kos` yarım kalmış yazımları siler)."""
    dizin = Path(dizin)
    meta_yolu = dizin / "meta.json"
    if not meta_yolu.is_file():
        return None
    meta = json.loads(meta_yolu.read_text(encoding="utf-8"))
    if meta.get("anahtar") != anahtar:
        return None
    dosyalar = ([dizin / f"tablo_{a}.parquet" for a in meta["tablolar"]]
                + [dizin / f"kayit_{a}.parquet" for a in meta["kayitlar"]] + [dizin / "gercek.parquet"])
    if not all(d.is_file() for d in dosyalar):
        return None
    kayitlar = {a: pd.read_parquet(dizin / f"kayit_{a}.parquet") for a in meta["kayitlar"]}
    return motor.KosuKaydi(dizin=dizin, meta=meta, kayitlar=kayitlar, onbellekten=True)


def lumoda_ns(yol: int = 0, *, olcek: str = "tam", onbellek: Path | None = KOSU_DIZINI
              ) -> tuple[dict[tuple[str, str], int], str]:
    """(Yolun Lumoda `ns`'i, kaynak): İlk Sevkiyat'ın önbellekli `lumoda` / `y<p>_lumoda` koşusu salt
    okunur açılabiliyorsa ondan ("allocation:<dizin>"), yoksa vakanın o yoldaki doğrulama kolundan
    ("vaka:<ad>_<anahtar[:20]>"; önbellekte yoksa koşulur)."""
    k = allocation_lumoda(yol, olcek)
    if k is not None:
        return lumoda_giden(k), f"allocation:{k.dizin.name}"
    k = kos_dogrulama(yol, olcek, onbellek=onbellek)
    return lumoda_giden(k), f"vaka:{dogrulama_adi(yol)}_{k.meta['anahtar'][:20]}"


# ---------------------------------------------------------------------------
# Komut satırı: TAM doğrulama
# ---------------------------------------------------------------------------


def _referans(yol: int) -> dict | None:
    """İlk Sevkiyat'ın kayıtlı Lumoda ölçütleri (salt okunur): yol 0 `oyun.json`, yol p `yollar.json`."""
    cikti = motor.KOSU_DIZINI.parent
    try:
        if int(yol) == 0:
            return json.loads((cikti / "oyun.json").read_text(encoding="utf-8"))["kosular"]["lumoda"]["olcutler"]
        y = json.loads((cikti / "yollar.json").read_text(encoding="utf-8"))["yollar"][str(int(yol))]
        return y["kosular"]["lumoda"]["olcutler"]
    except (FileNotFoundError, KeyError):
        return None


def dogrula(yol: int = 0, olcek: str = "tam") -> int:
    """Doğrulama kolunu koşar (ya da önbellekten okur), giden paketini ve ölçütlerini İlk Sevkiyat'ın
    Lumoda'sınınkiyle kıyaslar; ikisi de yapılıp birebir ise 0 (İlk Sevkiyat'ın önbelleği ya da kayıtlı
    ölçütü yoksa 1)."""
    t0 = time.perf_counter()
    k = kos_dogrulama(yol, olcek)
    print(f"koşu {dogrulama_adi(yol)}: {'önbellekten' if k.onbellekten else 'koşuldu'}, "
          f"{time.perf_counter() - t0:.0f} sn, motor {k.meta.get('motor_sn')} sn, "
          f"tepe {k.meta.get('tepe_bellek_gb')} GB", flush=True)
    o = olc(k)
    print(f"ölçüm: {time.perf_counter() - t0:.0f} sn; bulunabilirlik {o['bulunabilirlik']:.4f}, "
          f"kirpilan_adet {o['kirpilan_adet']:.0f}", flush=True)
    al = allocation_lumoda(yol, olcek)
    if al is None:
        print(f"İlk Sevkiyat'ın önbellekli Lumoda koşusu yok ({allocation_anahtari(yol, olcek)[:20]}): "
              "giden paket kıyaslanamadı", flush=True)
        sonuc = 1
    else:
        ayni = lumoda_giden(k) == lumoda_giden(al)
        print(f"giden paket (option, mağaza) İlk Sevkiyat {al.dizin.name} ile {'aynı' if ayni else 'FARKLI'}")
        sonuc = int(not ayni)
    ref = _referans(yol) if str(olcek).lower() == "tam" else None
    if ref is None:
        print("İlk Sevkiyat'ın kayıtlı ölçütü yok (yalnız TAM): kıyas yapılmadı")
        return 1
    fark = {a: (o.get(a), v) for a, v in ref.items() if o.get(a) != v}
    for a, (b, v) in sorted(fark.items()):
        print(f"  FARK {a}: vaka {b!r} ≠ İlk Sevkiyat {v!r}")
    print(f"ölçütler: {len(ref) - len(fark)}/{len(ref)} birebir")
    return int(bool(fark) or sonuc)


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(prog="python -m beden_paket.kosucu")
    alt = ap.add_subparsers(dest="komut", required=True)
    d = alt.add_parser("dogrulama", help="doğrulama kolu ↔ İlk Sevkiyat Lumoda (birebir ölçüt)")
    d.add_argument("--yol", type=int, default=0)
    d.add_argument("--olcek", default="tam")
    a = ap.parse_args(argv)
    al_oyun.uyanik_tut()
    return dogrula(a.yol, a.olcek)


if __name__ == "__main__":
    sys.exit(main())
