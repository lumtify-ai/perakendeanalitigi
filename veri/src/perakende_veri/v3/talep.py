"""v3 talep çarpanları — saf fonksiyonlar (durum ve rastgelelik yok).

v2'nin çarpımsal yapısı (taban × cinsiyet × line hacmi × mağaza tipi ×
beden payı × yerel sapma × ölü option) `perakende_veri.talep`ten gelir.
Burada yalnız v3'ün ekledikleri durur: yaşam eğrisi, düzgün aylık
mevsimsellik ve planlı indirim.
"""

import numpy as np

from .. import talep as v2_talep
from . import sabitler


def yasam_egrisi(h, tau: float, a: float = sabitler.YASAM_A) -> np.ndarray:
    """f(h) = (h+1)^a · exp(−h/τ), tepesi 1'e ölçekli; h < 0 için 0.

    h lansmandan beri geçen HAFTA (sürekli: gün / 7). Tepe h = aτ − 1'de.
    Ürün lansmandan önce yoktur; eğri sağa doğru söner ama sıfırlanmaz —
    çıkışı eğri değil sezon takvimi belirler.
    """
    h = np.asarray(h, dtype=float)
    tau = np.asarray(tau, dtype=float)
    tepe_h = np.maximum(a * tau - 1.0, 0.0)
    tepe = (tepe_h + 1.0) ** a * np.exp(-tepe_h / tau)
    hp = np.maximum(h, 0.0)
    deger = (hp + 1.0) ** a * np.exp(-hp / tau) / tepe
    return np.where(h < 0, 0.0, deger)


def mevsim_egrisi(alt_kategori: str, ay_kesirli) -> np.ndarray:
    """Alt kategorinin ham aylık mevsimselliği (ortalaması ~1).

    ay_kesirli: 1.0 = 1 Ocak, 12.97 = 31 Aralık. Düzgün kosinüs: ay
    sınırında sıçrama olmaz (v2'nin iki kademeli çarpanının aksine).
    """
    tepe, genlik = sabitler.MEVSIM[alt_kategori]
    x = 2 * np.pi * (np.asarray(ay_kesirli, dtype=float) - tepe) / 12.0
    # exp(A·cos) ortalaması I0(A); ona bölünce yıllık ortalama 1 olur
    return np.exp(genlik * np.cos(x)) / np.i0(genlik)


def mevsim_carpani(alt_kategori: str, line: str, ay_kesirli) -> np.ndarray:
    """Line'ın sezon etkisiyle yumuşatılmış mevsimsellik.

    Yumuşatma üs ile yapılır (m ** etki): etki 1 ise kategorinin
    dalgalanması olduğu gibi, 0 ise düz. Üs, çarpanı pozitif tutar.
    """
    return mevsim_egrisi(alt_kategori, ay_kesirli) ** v2_talep.LINE_SEZON_ETKISI[line]


def indirim_durumu(gun_farki) -> tuple[np.ndarray, np.ndarray]:
    """İndirim başından beri geçen gün → (fiyat indirim oranı, talep çarpanı).

    gun_farki < 0: indirim yok (0, 1). İlk 4 hafta %30 / ×1,6, sonrası
    %50 / ×2,2. Çıkışı çağıran taraf keser.
    """
    g = np.asarray(gun_farki)
    ilk = (g >= 0) & (g < sabitler.INDIRIM_ILK_HAFTA * 7)
    ikinci = g >= sabitler.INDIRIM_ILK_HAFTA * 7
    oran = np.where(ilk, sabitler.INDIRIM_ORANLARI[0],
                    np.where(ikinci, sabitler.INDIRIM_ORANLARI[1], 0.0))
    carpan = np.where(ilk, sabitler.INDIRIM_TALEP_CARPANI[0],
                      np.where(ikinci, sabitler.INDIRIM_TALEP_CARPANI[1], 1.0))
    return oran, carpan


def yerel_carpan_beklenen(line: str) -> float:
    """v2'nin yerel (mağaza × option) çarpanının beklenen değeri.

    Plan "sürprizsiz BEKLENEN talep"tir: hangi mağazada tutacağını bilmez
    ama zincir geçmişinden ortalamayı bilir. Lognormal(0, σ)'nın ortalaması
    exp(σ²/2) > 1 olduğu için bu düzeltme olmadan plan her option'ı
    sistematik olarak %7–12 eksik tahmin ederdi (v2 bunu umursamıyordu;
    v2'de alım yoktu).
    """
    from .. import simulasyon as v2_sim

    risk = v2_talep.LINE_MODA_RISKI[line]
    sigma = v2_sim.YEREL_TALEP_SAPMASI * risk
    olu = min(v2_sim.OLU_OPTION_OLASILIGI * risk, 0.25)
    return (1 - olu) * float(np.exp(sigma**2 / 2)) + olu * v2_sim.OLU_OPTION_CARPANI


def surpriz_beklenen(line: str) -> float:
    """Ürün sürprizinin (lognormal(0, σ)) beklenen değeri: exp(σ²/2).

    Sürprizin medyanı 1'dir, ortalaması değil. Planı medyana kurmak her
    Collection option'ını ortalamada %16 eksik planlamak olurdu; plan
    ortalamayı bilir, tek tek option'ın sürprizini bilmez.
    """
    return float(np.exp(sabitler.SURPRIZ_SIGMA[line] ** 2 / 2))
