"""Geçmişin (2025-01-01 – oyun başlangıcı) v2'nin kendi ikmal kuralıyla
yeniden oynatılması.

`V2Politikasi` `perakende_veri.simulasyon.simule_et`'in günlük döngüsündeki
ikmal adımının birebir kopyasıdır (bkz. o modülün 2. adımı): iki haftada
bir (ISO hafta − 1 çift) pazartesi artı açılış günü, hedef zincir planının
`TEDARIK_HEDEF_HAFTA` haftalık toplamı, yalnız hücrenin kendi son 28 günlük
satış hızı onu zaten bu hedefin altında bırakıyorsa sevk edilir (ölü stok
koruyucusu). Depo bu ön-oyun aşamasında kasten sınırsızdır: burada oyunu
oynamıyoruz, v2'nin geçmişini yeniden kuruyoruz.

`gecmisi_oynat` bu politikayla gün 0'dan `bit`in bir gün öncesine kadar
`motor.gunu_isle`'yi çağırır ve `bit` sabahındaki `Durum`'u (FIFO doğal
olarak tüketilmiş, iade kuyruğu son `IADE_GECIKME` günün satışıyla dolu)
döner.

`yol_baslangici` alternatif talep yollarını (Task 9'un `talep_yolu`'su) bu
oynatmayla birleştirip her yolun 1 Eylül sabahına kendi stok/satış
geçmişiyle gelmesini sağlar; yol 0 gerçek v2 verisini kullanır, replay
yapmaz.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import kaynak, sabitler
from .dunya import Dunya
from .motor import Durum, baslangic_durumu, gunu_isle
from .talep_yolu import talep_yolu


@dataclass
class V2Politikasi:
    """v2'nin kendi ikmal kuralı: iki haftada bir (ISO hafta − 1 çift)
    pazartesi artı açılış günü, hedef = rint(plan × 7 × 6), yalnız
    stok < son 28 gün hızı × 7 × 6 ise sevk edilir. Depo sınırsızdır."""

    def gonderilecek(
        self,
        dunya: Dunya,
        gun: int,
        stok: np.ndarray,
        son_satislar: list[np.ndarray],
    ) -> np.ndarray:
        """int64[H]: bugün gönderilecek miktar (sevk günü olmasa 0 dizisi)."""
        sezon = dunya.sezon[gun]
        hedef = np.rint(dunya.plan[sezon] * 7 * sabitler.TEDARIK_HEDEF_HAFTA).astype(np.int64)
        eksik = np.maximum(hedef - stok, 0)

        if not son_satislar:
            uygun = np.ones_like(eksik, dtype=bool)
        else:
            haftalik = np.sum(son_satislar, axis=0) / len(son_satislar) * 7.0
            uygun = stok < haftalik * sabitler.TEDARIK_HEDEF_HAFTA

        gonderilen = np.zeros_like(eksik)
        maske = (eksik > 0) & uygun
        gonderilen[maske] = eksik[maske]
        return gonderilen


_OLU_STOK_PENCERESI_GUN = 28


def gecmisi_oynat(
    dunya: Dunya,
    talep: np.ndarray,
    bit: str = sabitler.OYUN_BAS,
    iade_tohumu: int = sabitler.IADE_TOHUM,
) -> tuple[np.ndarray, Durum]:
    """Gün 0'dan bit'in bir gün öncesine kadar V2Politikasi ile oynatır.

    Döner: (gözlenen satış [365, H], bit günü sabahındaki Durum)."""
    H = len(dunya.hucre_magaza)
    bit_gunu = dunya.gun(bit)

    tarihler = pd.DatetimeIndex(dunya.tarihler)
    hafta_gunleri = tarihler.dayofweek.to_numpy()
    haftalar = tarihler.isocalendar()["week"].to_numpy()

    durum = baslangic_durumu(np.zeros(H, dtype=np.int64), [])
    rng = np.random.default_rng(iade_tohumu)
    politika = V2Politikasi()

    gozlenen = np.zeros((365, H), dtype=np.int32)
    son_satislar: list[np.ndarray] = []

    for g in range(bit_gunu):
        acilis = g == 0
        pazartesi = hafta_gunleri[g] == 0
        sevk_gunu = acilis or (pazartesi and (int(haftalar[g]) - 1) % 2 == 0)

        gelen = politika.gonderilecek(dunya, g, durum.stok, son_satislar) if sevk_gunu else None

        satis, _kayip = gunu_isle(durum, g, talep[g], gelen, None, rng)
        gozlenen[g] = satis

        son_satislar.append(satis.astype(np.int64))
        if len(son_satislar) > _OLU_STOK_PENCERESI_GUN:
            son_satislar.pop(0)

    return gozlenen, durum


def yol_baslangici(
    dunya: Dunya, yol: int, con
) -> tuple[np.ndarray, np.ndarray, Durum]:
    """(talep, geçmiş satış, başlangıç durumu).

    yol 0: gerçek v2 verisi (kâhin talep, oyun günleri sıfırlanmış gözlenen
    satış, 1 Eylül stok fotoğrafı, son 7 günün gözlenen satışıyla önceden
    doldurulmuş iade kuyruğu) — replay yapılmaz.
    yol ≥ 1: `talep_yolu` + `gecmisi_oynat`."""
    if yol == 0:
        talep = kaynak.kahin_talep(con, dunya)

        bas_gunu = dunya.gun(sabitler.OYUN_BAS)
        gecmis_satis = kaynak.gozlenen_satis(con, dunya).copy()
        gecmis_satis[bas_gunu:] = 0

        stok = kaynak.stok_fotografi(con, dunya, sabitler.OYUN_BAS)
        son_7 = list(gecmis_satis[bas_gunu - sabitler.IADE_GECIKME : bas_gunu])
        durum = baslangic_durumu(stok, son_7)
        return talep, gecmis_satis, durum

    talep = talep_yolu(dunya, yol)
    gecmis_satis, durum = gecmisi_oynat(dunya, talep)
    return talep, gecmis_satis, durum
