"""Testler: Görev 16 politika eşdeğerliği ve sayaç bağımsızlığı.

Spec: docs/superpowers/specs/2026-09-27-veri-v4-cekirdek-design.md §6
Brief: .superpowers/sdd/2026-09-27-veri-v4-cekirdek/task-16-brief.md

Üç iddia:
  1. Lumoda politikalarını açıkça enjekte etmek varsayılan koşuyla birebir
     aynı sonucu verir (`Politikalar()` == `Politikalar(**lumoda_politikalari())`).
  2. Bir mağazanın replenishment'ını sıfırlayan bir politika, BAŞKA
     mağazaların kaydedilen günlük talebini değiştirmez (rastgelelik
     politikadan bağımsızdır — `dongu.py` üst belgesi).
  3. Markdown'ı her zaman 0 döndüren bir politika, varsayılan koşunun
     markdown'ı 0 olan (gün, hücre) hücrelerinde talebi değiştirmez (aynı
     tekdüzeler, aynı λ; `oran_talep = max(md, kampanya)` kampanyaya döner).
"""

import numpy as np
import pandas as pd

from perakende_veri.v4.motor import simule_et
from perakende_veri.v4.motor.satis import hat_indisi
from perakende_veri.v4.politika import (
    LumodaElleTransfer,
    LumodaMarkdown,
    LumodaRPT,
    Politikalar,
    lumoda_politikalari,
    lumoda_replenishment,
)

GUN_SAYISI = 400  # tam KUCUK koşusu yavaş; önek eşitliği başka testlerle garanti


# ---------------------------------------------------------------------------
# 1) Lumoda enjekte edilmiş == varsayılan
# ---------------------------------------------------------------------------


def test_lumoda_enjekte_esit_varsayilan(kucuk_dunya, kucuk_kosu):
    # Sınıf tabanlı politikalar (markdown/RPT/elle transfer) taze örneklerle:
    # `lumoda_politikalari()` modül tekil örneklerini döndürür; bunlar bugün
    # durum tutmasa da enjeksiyonun tekil örneğe değil davranışa eşitliğini
    # sınamak için taze örnek kullanıyoruz.
    pol = dict(lumoda_politikalari())
    pol["markdown"] = LumodaMarkdown()
    pol["rpt"] = LumodaRPT()
    pol["elle_transfer"] = LumodaElleTransfer()
    b = simule_et(kucuk_dunya, Politikalar(**pol))
    for ad in ("satis", "sevkiyat", "stok", "gizli_kayip"):
        pd.testing.assert_frame_equal(
            kucuk_kosu[ad].reset_index(drop=True), b[ad].reset_index(drop=True), obj=ad,
        )


# ---------------------------------------------------------------------------
# 2) Sayaç bağımsızlığı: bir mağazanın replenishment'ı sıfırlansa da
#    başka mağazaların talep dizisi değişmez.
# ---------------------------------------------------------------------------


def _sifirla_magaza_replenishment(magaza_idx: int):
    def pol(g):
        istek = np.array(lumoda_replenishment(g), dtype=np.int64, copy=True)
        istek[g.dunya.hucre_magaza == magaza_idx] = 0
        return istek
    return pol


def test_sayac_bagimsizligi(kucuk_dunya):
    """Bir mağazanın replenishment'ını 0'layan politika BAŞKA mağazaların
    çekilişini (u, λ) değiştirmez — ama zincir düzeyinde STR'ye dayanan
    `LumodaMarkdown`/`LumodaRPT`, o mağazaya gidenin azalmasıyla aynı
    option'ın zincir STR'sini kaydırıp markdown kararını (dolayısıyla
    `oran_talep`'i) BAŞKA mağazalarda da değiştirebilir — bu dolaylı,
    politika-aracılı bir etkidir, sayaç bağımlılığı değil. Bu yüzden
    karşılaştırma, markdown/kampanya oranı iki koşuda da aynı kalan
    (gün, hücre) çiftleriyle sınırlanır (test 3'teki gibi); fiyatı
    değişen hücrelerde (değişen mağazanın kendisi, ONL ve aynı option'ı
    taşıyan başka mağazalar dahil) talep de değişebilir, bunlar hariç
    tutulur ve aşağıda sayılarak raporlanır."""
    w = kucuk_dunya
    D = GUN_SAYISI
    O = len(w.optionlar)
    magaza_idx = int(np.flatnonzero((w.magazalar["tip"] == "AVM").to_numpy())[0])

    a = simule_et(w, gun_sayisi=D, kayit_talep=True)
    b = simule_et(
        w, Politikalar(replenishment=_sifirla_magaza_replenishment(magaza_idx)),
        gun_sayisi=D, kayit_talep=True,
    )
    talep_a, talep_b = a["talep"], b["talep"]
    assert talep_a.shape == talep_b.shape

    onl, outlet_c = w.hucre_online, w.hucre_outlet_akisi
    hat_c = hat_indisi(onl, outlet_c)
    ho = w.hucre_option
    md_a = _md_gecmisi(a["fiyat"], D, O)[:, ho, hat_c]
    md_b = _md_gecmisi(b["fiyat"], D, O)[:, ho, hat_c]
    fiyat_ayni = md_a == md_b

    degisen_magaza = w.hucre_magaza == magaza_idx
    diger = ~degisen_magaza
    assert diger.any()

    maske = diger & fiyat_ayni
    # Fiyatı dolaylı etkilenen başka-mağaza hücresi olup olmaması dünyaya
    # bağlıdır (Görev 18: OZNITELIK_TABAN_SIGMA 0,30 ile KÜÇÜK 400 günde
    # hiç yok); iddia yalnız karşılaştırılacak hücre bulunmasını ister.
    assert maske.any(), "fiyatı etkilenmeyen başka-mağaza hücre/günü beklenir"
    print(f"\nfiyatı dolaylı etkilenen başka-mağaza (gün, hücre): {int((diger & ~fiyat_ayni).sum())}")
    # Fiyatı değişmeyen (gün, hücre) çiftlerinde talep birebir aynı olmalı
    # (aynı tekdüze u, aynı λ): sayaç bağımsızlığının asıl iddiası budur.
    np.testing.assert_array_equal(
        talep_a[maske], talep_b[maske],
        err_msg="fiyatı aynı kalan hücrelerde başka mağazaların talebi de aynı olmalı",
    )


# ---------------------------------------------------------------------------
# 3) Markdown politikası talep akışını değiştirmez (md=0 olan hücrelerde).
# ---------------------------------------------------------------------------


def _sifir_markdown(g):
    O = len(g.dunya.optionlar)
    return np.zeros((O, 3), dtype=float)


def _md_gecmisi(fiyat_df: pd.DataFrame, D: int, O: int) -> np.ndarray:
    """[D, O, 3] fiyat_orani geçmişi: `fiyat` kaydından (gün, option, hat,
    oran) günlük duruma ileri-doldurma (motorun 12. adımda kullandığı
    değerle birebir — aynı gün değişimi aynı gün geçerlidir)."""
    md = np.zeros((D, O, 3), dtype=float)
    cur = np.zeros((O, 3), dtype=float)
    gunler = np.sort(fiyat_df["gun"].unique()) if len(fiyat_df) else np.array([], dtype=np.int64)
    onceki = -1
    for gun in gunler:
        gun = int(gun)
        if gun >= D:
            break
        if gun > onceki + 1:
            md[onceki + 1:gun] = cur
        satirlar = fiyat_df[fiyat_df["gun"] == gun]
        cur = cur.copy()
        cur[satirlar["option"].to_numpy(), satirlar["hat"].to_numpy()] = satirlar["oran"].to_numpy()
        md[gun] = cur
        onceki = gun
    if onceki + 1 < D:
        md[onceki + 1:D] = cur
    return md


def test_markdown_politikasi_talep_akisini_degistirmez(kucuk_dunya):
    w = kucuk_dunya
    D = GUN_SAYISI
    O = len(w.optionlar)

    a = simule_et(w, gun_sayisi=D, kayit_talep=True)
    b = simule_et(w, Politikalar(markdown=_sifir_markdown), gun_sayisi=D, kayit_talep=True)

    onl, outlet_c = w.hucre_online, w.hucre_outlet_akisi
    hat_c = hat_indisi(onl, outlet_c)
    ho = w.hucre_option

    md_a = _md_gecmisi(a["fiyat"], D, O)
    # (gün, hücre) düzeyinde varsayılan koşunun markdown oranı (motorun 12.
    # adımda kullandığı `md = z.fiyat_orani[ho, hat_c]` ile birebir).
    md_a_hucre = md_a[:, ho, hat_c]   # [D, C]

    # Varsayılan koşunun markdown'ı hiç uygulamadığı (gün, hücre) hücreleri:
    # kampanya politikadan bağımsız (dünya verisi), bu yüzden oran_talep
    # `b`'de de aynı kampanya oranına eşit olur → talep birebir aynı olmalı.
    maske = md_a_hucre == 0.0
    assert maske.any() and (~maske).any(), "hem markdown'lı hem markdown'sız hücre/gün beklenir"

    np.testing.assert_array_equal(
        a["talep"][maske], b["talep"][maske],
        err_msg="markdown 0 olan (gün, hücre) hücrelerinde talep aynı tekdüzeyi/λ kullanmalı",
    )
