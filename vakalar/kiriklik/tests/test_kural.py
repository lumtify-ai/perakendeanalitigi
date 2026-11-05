"""`plan` ve `kural`: Plan veri yapısı ve uzmanın kuralı (K20). Elle kurulmuş `KararGirdisi`lerle sınanır
(bir option, beş mağaza); `veri` işaretli test yayımlanan v4'te plan tutarlılığını sınar.

Dünya: karar günü 2024-12-09, asorti 1-2-2-1-1. Puan yalnız satıştan gelir: `_dunya`da her mağazaya karardan
3 gün önce o kadar adet satış verilir (mağazanın sırası = satışının sırası)."""

import ast
import json
import time
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from kiriklik import kaynak, kural, plan, sabitler, uygunluk

KARAR = date(2024, 12, 9)
KOLONLAR = ["option_id", "urun_id", "beden_sira", "verici", "alici", "adet"]


def _cift(magaza, option, stoklar, depo=(0,) * 5, acik=(0,) * 5):
    return [(magaza, option, i + 1, s, d, a) for i, (s, d, a) in enumerate(zip(stoklar, depo, acik))]


def _dunya(satirlar, satis=(), magazalar=None, lansman="2024-08-19") -> kaynak.KararGirdisi:
    """`satirlar`: (magaza, option, beden_sira, stok, depo, acik_siparis). `satis`: (magaza, option, gun_once,
    adet), `gun_once` karardan kaç gün önce. `magazalar`: {magaza: uygun} (verilmezse hepsi uygun)."""
    hucre = pd.DataFrame(satirlar, columns=["magaza_id", "option_id", "beden_sira", "stok", "depo", "acik_siparis"])
    hucre["urun_id"] = hucre.option_id + "-" + hucre.beden_sira.astype(str)
    hucre["liste_fiyati"], hucre["alis_fiyati"] = 100.0, 40.0
    if magazalar is None:
        magazalar = {m: True for m in hucre.magaza_id.unique()}
    magaza = pd.DataFrame({"magaza_id": list(magazalar), "ad": list(magazalar), "sehir": "X", "bolge": "Y",
                           "tip": "AVM", "uygun": list(magazalar.values())})
    s = pd.DataFrame([(m, f"{o}-3", pd.Timestamp(KARAR) - timedelta(days=gun), adet, 100.0 * adet)
                      for m, o, gun, adet in satis], columns=["magaza_id", "urun_id", "tarih", "adet", "tutar"])
    opt = pd.DataFrame({"option_id": sorted(hucre.option_id.unique())})
    opt["lansman_tarihi"] = pd.Timestamp(lansman)
    return kaynak.KararGirdisi(sezon="AW24", karar=KARAR, indirim=date(2025, 1, 2), cikis=date(2025, 2, 24),
                               hucre=hucre, satis=s, stoklu=pd.DataFrame(), magaza=magaza, optionlar=opt,
                               takvim=pd.DataFrame(), kampanya=pd.DataFrame())


def _satis(**adetler):
    """{mağaza: adet} → O1 için karardan 3 gün önce tek satış satırı."""
    return [(m, "O1", 3, a) for m, a in adetler.items()]


def _hareketler(p) -> list[tuple]:
    return list(p.hareketler[["alici", "verici", "beden_sira", "adet"]].itertuples(index=False, name=None))


# ---------------------------------------------------------------- Plan yapısı

def _plan_ornek(kol="kural", sezon="AW24") -> plan.Plan:
    h = pd.DataFrame({"option_id": ["O1", "O1", "O2"], "urun_id": ["O1-2", "O1-4", "O2-2"],
                      "beden_sira": [2, 4, 2], "verici": ["B", "C", "B"], "alici": ["A", "A", "A"],
                      "adet": [2, 1, 1]})
    return plan.Plan(kol=kol, sezon=sezon, hareketler=h, bilgi={})


def test_plan_kimligi_sira_bagimsiz():
    p = _plan_ornek()
    karisik = p.hareketler.iloc[[2, 0, 1]].reset_index(drop=True)
    q = plan.Plan(kol="kural", sezon="AW24", hareketler=karisik, bilgi={"baska": 1})
    assert p.kimlik == q.kimlik and len(p.kimlik) == 64
    # adet tipi (int32 / float) kimliği değiştirmez
    r = plan.Plan(kol="kural", sezon="AW24", hareketler=p.hareketler.astype({"adet": "int32"}), bilgi={})
    assert r.kimlik == p.kimlik
    # kol, sezon ve içerik kimliğe girer
    assert _plan_ornek(kol="kural_28").kimlik != p.kimlik
    assert _plan_ornek(sezon="SS25").kimlik != p.kimlik
    h = p.hareketler.copy()
    h.loc[0, "adet"] = 3
    assert plan.Plan(kol="kural", sezon="AW24", hareketler=h, bilgi={}).kimlik != p.kimlik


def test_plan_sema_dogrulanir():
    h = _plan_ornek().hareketler
    with pytest.raises(ValueError):
        plan.Plan(kol="kural", sezon="AW24", hareketler=h.drop(columns=["urun_id"]), bilgi={})
    with pytest.raises(ValueError):
        plan.Plan(kol="kural", sezon="AW24", hareketler=h.assign(adet=[2, 0, 1]), bilgi={})


def test_plan_anahtari_tekil_ve_adet_tamsayi():
    h = _plan_ornek().hareketler
    cift = pd.concat([h, h.iloc[[0]]], ignore_index=True)          # (O1, A, B, 2) iki kez
    with pytest.raises(ValueError, match="tekil"):
        plan.Plan(kol="kural", sezon="AW24", hareketler=cift, bilgi={})
    with pytest.raises(ValueError, match="tamsayı"):
        plan.Plan(kol="kural", sezon="AW24", hareketler=h.assign(adet=[2.0, 1.5, 1.0]), bilgi={})
    # tamsayı değerli float kabul edilir, int64 saklanır; plan girdinin savunma kopyasını tutar; kimlik bir kez
    girdi = h.assign(adet=[2.0, 1.0, 1.0])
    p = plan.Plan(kol="kural", sezon="AW24", hareketler=girdi, bilgi={})
    assert p.hareketler.adet.dtype == "int64" and p.hareketler is not girdi
    girdi.loc[0, "adet"] = 7.0
    assert p.hareketler.adet.tolist() == [2, 1, 1]
    k = p.kimlik
    p.hareketler.loc[0, "adet"] = 5
    assert p.kimlik == k == _plan_ornek().kimlik


def test_bos_plan_ve_rotalar():
    b = plan.bos("kural", "AW24", {"not": "x"})
    assert b.hareketler.empty and list(b.hareketler.columns) == KOLONLAR and b.bilgi == {"not": "x"}
    assert plan.rotalar(b.hareketler).empty
    assert plan.bos("kural", "AW24", {}).kimlik == plan.bos("kural", "AW24", {"a": 1}).kimlik
    r = plan.rotalar(_plan_ornek().hareketler)
    assert list(r.columns) == ["verici", "alici", "adet", "option_sayisi"]
    # B → A iki option (3 adet), C → A bir option (1 adet); tekil rota
    assert r.to_dict("records") == [{"verici": "B", "alici": "A", "adet": 3, "option_sayisi": 2},
                                    {"verici": "C", "alici": "A", "adet": 1, "option_sayisi": 1}]
    assert plan.rotalar(_plan_ornek().hareketler).adet.dtype.kind == "i"


# ---------------------------------------------------------------- puanlar

def test_puan_pencere_sinirlari_ve_pozitif_satis():
    # std: lansmandan karara; 7/14/28: karardan önceki N gün (N gün önceki gün içeride, karar günü dışarıda)
    satirlar = (_cift("A", "O1", (1, 0, 2, 1, 1)) + _cift("B", "O1", (1, 0, 2, 1, 1))
                + _cift("C", "O1", (1, 0, 2, 1, 1)))
    satis = [("A", "O1", 7, 5), ("A", "O1", 8, 1),          # 7. gün içeride, 8. gün 7'nin dışında
             ("B", "O1", 8, 4), ("B", "O1", 14, 1),
             ("C", "O1", 29, 9), ("C", "O1", 3, -4)]        # iade negatif: sayılmaz; 29. gün 28'in dışında
    g = _dunya(satirlar, satis)

    def puan(pencere):
        return kural.puanlar(g, pencere).set_index("magaza_id").puan.to_dict()

    assert puan((7,)) == {"A": 3.0, "B": 1.5, "C": 1.5}     # A: 5; B ve C: 0 (eşit sıra ortalaması)
    assert puan((14,)) == {"A": 3.0, "B": 2.0, "C": 1.0}    # A: 6, B: 5, C: 0
    assert puan((28,)) == {"A": 3.0, "B": 2.0, "C": 1.0}    # C'nin 29. gündeki satışı 28'e girmez
    assert puan(("std",)) == {"A": 2.0, "B": 1.0, "C": 3.0}  # A: 6, B: 5, C: 9 (iade yok sayılır)


def test_puan_std_lansmandan_baslar_ve_satissizlar_en_alta():
    satirlar = (_cift("A", "O1", (1, 0, 2, 1, 1)) + _cift("B", "O1", (1, 0, 2, 1, 1))
                + _cift("C", "O1", (1, 0, 2, 1, 1)) + _cift("D", "O1", (1, 0, 2, 1, 1)))
    g = _dunya(satirlar, [("A", "O1", 100, 3), ("B", "O1", 10, 1)], lansman="2024-09-20")
    p = kural.puanlar(g, ("std",)).set_index("magaza_id").puan
    assert p["B"] == 4.0                                    # lansmandan sonra tek satan
    assert p["A"] == p["C"] == p["D"] == 2.0                # A'nın satışı lansmandan önce: satışsızlarla ortak en alt
    # dört pencere: puan = sıraların ortalaması
    g2 = _dunya(satirlar, [("A", "O1", 3, 5), ("B", "O1", 20, 5), ("C", "O1", 40, 1)])
    t = kural.puanlar(g2)
    assert list(t.columns) == ["magaza_id", "option_id", "puan"] and len(t) == 4
    assert t.set_index("magaza_id").puan.to_dict() == {"A": 3.75, "B": 2.75, "C": 1.875, "D": 1.625}


def test_puan_std_lansmansiz_optionlar_hata():
    g = _dunya(_cift("A", "O1", (1, 0, 2, 1, 1)) + _cift("B", "O1", (1, 2, 2, 1, 1)), _satis(A=1))
    g = kaynak.KararGirdisi(**{**g.__dict__, "optionlar": g.optionlar.drop(columns=["lansman_tarihi"])})
    with pytest.raises(KeyError, match="lansman_tarihi"):
        kural.puanlar(g)
    assert kural.puanlar(g, (7, 28)).puan.notna().all()                  # std'siz pencereler lansmana bakmaz


def test_bilgi_pencereleri_json_uyumlu():
    g = _dunya(_cift("A", "O1", (1, 0, 2, 1, 1)) + _cift("B", "O1", (1, 2, 2, 1, 1)), _satis(A=1))
    p = kural.kural_plani(g, ("std", np.int64(7), 28))
    assert p.bilgi["pencereler"] == ["std", 7, 28]
    assert [type(w) for w in p.bilgi["pencereler"]] == [str, int, int]
    json.dumps(p.bilgi["pencereler"])


def test_puan_gecersiz_pencere():
    g = _dunya(_cift("A", "O1", (1, 0, 2, 1, 1)))
    for kotu in ((), (0,), (-7,), ("hepsi",)):
        with pytest.raises(ValueError):
            kural.puanlar(g, kotu)


def test_puan_satissiz_dunya():
    g = _dunya(_cift("A", "O1", (1, 0, 2, 1, 1)) + _cift("B", "O1", (1, 0, 2, 1, 1)))
    assert kural.puanlar(g).puan.tolist() == [1.5, 1.5]


def test_kural_28_puan_yalniz_28():
    # A: son haftalarda çok, eski satışı daha çok (std ve 7/14'te önde); B: 28. güne doğru satmış (yalnız
    # 28'de önde); C tam set; D vericidir. Tam kuralda A, yalnız 28'de B alıcıdır.
    satirlar = (_cift("A", "O1", (1, 0, 2, 1, 1)) + _cift("B", "O1", (1, 0, 2, 1, 1))
                + _cift("C", "O1", (1, 2, 2, 1, 1)) + _cift("D", "O1", (0, 2, 0, 0, 0)))
    satis = [("A", "O1", 3, 10), ("A", "O1", 60, 20), ("B", "O1", 20, 15), ("C", "O1", 6, 1)]
    g = _dunya(satirlar, satis)
    tam = kural.puanlar(g).set_index("magaza_id").puan.to_dict()
    sade = kural.puanlar(g, (28,)).set_index("magaza_id").puan.to_dict()
    assert sade == {"A": 3.0, "B": 4.0, "C": 2.0, "D": 1.0}
    assert tam == {"A": 3.75, "B": 2.5, "C": 2.5, "D": 1.25}
    p_tam = kural.kural_plani(g)
    p_28 = kural.kural_plani(g, (28,), kol="kural_28")
    assert _hareketler(p_tam) == [("A", "D", 2, 2)] and p_tam.kol == "kural"
    assert _hareketler(p_28) == [("B", "D", 2, 2)] and p_28.kol == "kural_28"
    assert p_tam.kimlik != p_28.kimlik


# ---------------------------------------------------------------- kural_plani

def test_alici_en_yuksek_puanli_uygun():
    # E en çok satan ama kapanış kararlı (uygun değil); F tam set. A ikinci ve uygun: alıcı A
    satirlar = (_cift("A", "O1", (1, 0, 2, 1, 1)) + _cift("B", "O1", (1, 0, 2, 1, 1))
                + _cift("D", "O1", (0, 2, 0, 0, 0)) + _cift("E", "O1", (1, 0, 2, 1, 1))
                + _cift("F", "O1", (1, 2, 2, 1, 1)))
    g = _dunya(satirlar, _satis(E=500, F=400, A=100, B=50, D=1),
               magazalar={"A": True, "B": True, "D": True, "E": False, "F": True})
    p = kural.kural_plani(g)
    assert _hareketler(p) == [("A", "D", 2, 2)]
    assert list(p.hareketler.columns) == KOLONLAR
    assert p.hareketler.urun_id.tolist() == ["O1-2"] and p.kol == "kural" and p.sezon == "AW24"


def test_verici_en_dusuk_puanli_once():
    # iki verici de 2 adet verebilir, alıcı 2 ister: en düşük puanlı (D1) verir, D2'ye dokunulmaz
    satirlar = (_cift("A", "O1", (1, 0, 2, 1, 1)) + _cift("D1", "O1", (0, 2, 0, 0, 0))
                + _cift("D2", "O1", (0, 2, 0, 0, 0)))
    g = _dunya(satirlar, _satis(A=100, D2=10, D1=1))
    assert _hareketler(kural.kural_plani(g)) == [("A", "D1", 2, 2)]
    # puan terslenince verici de değişir
    g = _dunya(satirlar, _satis(A=100, D1=10, D2=1))
    assert _hareketler(kural.kural_plani(g)) == [("A", "D2", 2, 2)]


def test_verici_esitlikte_magaza_id_artan():
    satirlar = (_cift("A", "O1", (1, 0, 2, 1, 1)) + _cift("D2", "O1", (0, 2, 0, 0, 0))
                + _cift("D1", "O1", (0, 2, 0, 0, 0)))
    g = _dunya(satirlar, _satis(A=100))                   # D1 ve D2 satışsız: eşit puan
    assert _hareketler(kural.kural_plani(g)) == [("A", "D1", 2, 2)]


def test_alici_esitlikte_magaza_id_artan():
    satirlar = (_cift("B", "O1", (1, 0, 2, 1, 1)) + _cift("A", "O1", (1, 0, 2, 1, 1))
                + _cift("D", "O1", (0, 2, 0, 0, 0)))
    g = _dunya(satirlar, _satis(A=10, B=10))
    assert set(kural.kural_plani(g).hareketler.alici) == {"A"}


def test_tamamlanamayan_alici_atlanir():
    # A'nın kırık bedenleri 2 ve 5; 2'yi D verebilir, 5'i kimse: A tamamlanamaz, hiçbir hareket yazılmaz
    # (D'nin ikinci bedeni de alınmaz: kısmi doldurma yok) ve atlanan bilgisi tutulur
    satirlar = _cift("A", "O1", (1, 0, 2, 1, 0)) + _cift("D", "O1", (0, 2, 0, 0, 0))
    g = _dunya(satirlar, _satis(A=100, D=1))
    p = kural.kural_plani(g)
    assert p.hareketler.empty and list(p.hareketler.columns) == KOLONLAR
    assert p.bilgi["atlanan_alicilar"] == [["O1", "A"], ["O1", "D"]]   # D de alıcı adayı: 1, 3, 4, 5 kırık, A'da 5 yok
    assert p.bilgi["tamamlanan_alicilar"] == []


def test_atlanan_alici_vericiyi_tuketmez():
    # O1'de A atlanır (5 yok); aynı vericiyle ayrı bir option'daki alıcı etkilenmez
    satirlar = (_cift("A", "O1", (1, 0, 2, 1, 0)) + _cift("D", "O1", (0, 2, 0, 0, 0))
                + _cift("A", "O2", (1, 0, 2, 1, 1)) + _cift("D", "O2", (0, 2, 0, 0, 0)))
    g = _dunya(satirlar, _satis(A=100, D=1))
    p = kural.kural_plani(g)
    assert p.hareketler.option_id.tolist() == ["O2"] and _hareketler(p) == [("A", "D", 2, 2)]


def test_tam_set_verici_olmaz():
    # beden 2'yi yalnız tam set mağaza (F) taşıyor: seti bozmaz, alıcı tamamlanamaz, plan boş
    satirlar = _cift("A", "O1", (1, 0, 2, 1, 1)) + _cift("F", "O1", (1, 2, 2, 1, 1)) + _cift("G", "O1", (1, 0, 2, 1, 1))
    g = _dunya(satirlar, _satis(A=10, F=100, G=1))
    p = kural.kural_plani(g)
    assert p.hareketler.empty
    assert "F" not in set(p.hareketler.verici)


def test_verici_alici_olamaz():
    # A (en yüksek) D'den alır → D verici; B'nin 4. bedeni yalnız A'da (alıcı olmuş, verici olamaz) ve D'de yok
    satirlar = (_cift("A", "O1", (1, 0, 2, 1, 1)) + _cift("B", "O1", (1, 2, 2, 0, 1))
                + _cift("D", "O1", (0, 2, 0, 0, 0)))
    g = _dunya(satirlar, _satis(A=100, B=50, D=1))
    p = kural.kural_plani(g)
    assert _hareketler(p) == [("A", "D", 2, 2)]
    assert not set(p.hareketler.alici) & set(p.hareketler.verici)
    assert p.bilgi["atlanan_alicilar"] == [["O1", "B"]]      # B için A'dan alınamadı; D da zaten verici
    assert p.bilgi["tamamlanan_alicilar"] == [["O1", "A"]]


def test_hedef_asorti_adedi():
    # A: 1-0-1-1-1 (beden 2 kırık, beden 3 asortiden 1 eksik): 2. beden 0→2, 3. beden 1→2; vericinin fazlası kalır
    satirlar = _cift("A", "O1", (1, 0, 1, 1, 1)) + _cift("D", "O1", (0, 5, 3, 0, 0))
    g = _dunya(satirlar, _satis(A=10, D=1))
    p = kural.kural_plani(g)
    assert _hareketler(p) == [("A", "D", 2, 2), ("A", "D", 3, 1)]
    # alıcının son stoğu asorti adedi
    son = np.asarray([1, 0, 1, 1, 1]) + np.bincount(p.hareketler.beden_sira - 1, weights=p.hareketler.adet,
                                                    minlength=5).astype(int)
    assert son.tolist() == list(sabitler.ASORTI)


def test_arz_yetmedigi_kadar_doldurulur():
    # kırık beden 2 için yalnız 1 adet var: en az bir olduğu için alıcı tamamlanır, 2'ye değil 1'e çıkar
    satirlar = _cift("A", "O1", (1, 0, 2, 1, 1)) + _cift("D", "O1", (0, 1, 0, 0, 0))
    g = _dunya(satirlar, _satis(A=10, D=1))
    assert _hareketler(kural.kural_plani(g)) == [("A", "D", 2, 1)]


def test_birden_cok_vericiden_toplanir():
    # A beden 2'de 2 ister; üç verici 1'er adet taşır → ikisi verir, üçüncüye dokunulmaz
    satirlar = (_cift("A", "O1", (1, 0, 2, 1, 1)) + _cift("D1", "O1", (0, 1, 0, 0, 0))
                + _cift("D2", "O1", (0, 1, 0, 0, 0)) + _cift("D3", "O1", (0, 1, 0, 0, 0)))
    g = _dunya(satirlar, _satis(A=10, D3=3, D2=2, D1=1))
    assert _hareketler(kural.kural_plani(g)) == [("A", "D1", 2, 1), ("A", "D2", 2, 1)]


def test_coklu_alici():
    # A ve B aynı option'da alıcı: A 2. bedeni D1'den, B 4. bedeni D2'den alır; A'nın 4. bedeni B'ye gitmez
    satirlar = (_cift("A", "O1", (1, 0, 2, 1, 1)) + _cift("B", "O1", (1, 2, 2, 0, 1))
                + _cift("D1", "O1", (0, 2, 0, 0, 0)) + _cift("D2", "O1", (0, 0, 0, 1, 0)))
    g = _dunya(satirlar, _satis(A=100, B=50, D2=2, D1=1))
    p = kural.kural_plani(g)
    assert _hareketler(p) == [("A", "D1", 2, 2), ("B", "D2", 4, 1)]
    assert p.bilgi["tamamlanan_alicilar"] == [["O1", "A"], ["O1", "B"]]


def test_vericisiz_option_bos_plan():
    # O1: tek kırık çift var, öteki mağazalar tam set; O2: hiç kırık yok; O3: kırık çift yalnız bir mağazada
    satirlar = (_cift("A", "O1", (1, 0, 2, 1, 1)) + _cift("F", "O1", (1, 2, 2, 1, 1))
                + _cift("A", "O2", (1, 2, 2, 1, 1)) + _cift("F", "O2", (1, 2, 2, 1, 1))
                + _cift("A", "O3", (1, 0, 2, 1, 1)))
    g = _dunya(satirlar, _satis(A=10, F=5))
    p = kural.kural_plani(g)
    assert p.hareketler.empty and list(p.hareketler.columns) == KOLONLAR
    assert p.hareketler.adet.dtype.kind == "i"
    assert p.bilgi["atlanan_alicilar"] == [["O1", "A"], ["O3", "A"]]
    assert len(p.kimlik) == 64
    # kırık çifti hiç olmayan dünya da boş plan döner
    g2 = _dunya(_cift("F", "O2", (1, 2, 2, 1, 1)))
    assert kural.kural_plani(g2).hareketler.empty


def test_depolu_beden_transferle_doldurulmaz():
    # A ve D'nin ikisinin de kırık bedeni 2 ve o bedenin deposu var → ikisi de aday değil → alıcı yok
    satirlar = (_cift("A", "O1", (1, 0, 2, 1, 1), depo=(0, 9, 0, 0, 0))
                + _cift("D", "O1", (1, 0, 0, 3, 3), depo=(0, 9, 0, 0, 0)))
    g = _dunya(satirlar, _satis(A=10, D=1))
    assert not uygunluk.adaylar(g).uygun.any()
    p = kural.kural_plani(g)
    assert p.hareketler.empty and p.bilgi["atlanan_alicilar"] == []


def test_verici_havuzu_uygun_olmayan_cifti_da_icerir():
    # D'nin çifti aday değil (3. bedeni depoda) ama kırık ve mağazası uygun: verici olabilir; kapalı mağaza olamaz
    satirlar = _cift("A", "O1", (1, 0, 2, 1, 1)) + _cift("D", "O1", (0, 2, 0, 0, 0), depo=(0, 0, 5, 0, 0)) \
        + _cift("K", "O1", (0, 2, 0, 0, 0))
    g = _dunya(satirlar, _satis(A=10, D=2, K=1), magazalar={"A": True, "D": True, "K": False})
    assert _hareketler(kural.kural_plani(g)) == [("A", "D", 2, 2)]


def test_hareket_sirasi_ve_tipleri():
    satirlar = (_cift("B", "O2", (1, 0, 2, 1, 1)) + _cift("D", "O2", (0, 2, 0, 0, 0))
                + _cift("A", "O1", (1, 0, 2, 1, 1)) + _cift("E", "O1", (0, 2, 0, 0, 0)))
    g = _dunya(satirlar, [("B", "O2", 3, 5), ("A", "O1", 3, 5)])
    h = kural.kural_plani(g).hareketler
    assert h.option_id.tolist() == ["O1", "O2"]
    assert [str(t) for t in h.dtypes] == ["object", "object", "int64", "object", "object", "int64"] or \
        [t.kind for t in h.dtypes] == ["O", "O", "i", "O", "O", "i"]


def test_karar_modulleri_ice_aktarma_kilidi():
    yasak = ("perakende_veri", "allocation", "kiriklik.hakem", "kiriklik.simulasyon", "kiriklik.olcutler",
             "kiriklik.oyun")
    for modul in (plan, kural):
        agac = ast.parse(Path(modul.__file__).read_text(encoding="utf-8"))
        alinan = set()
        for n in ast.walk(agac):
            if isinstance(n, ast.Import):
                alinan |= {a.name for a in n.names}
            elif isinstance(n, ast.ImportFrom):
                alinan.add(n.module or "")
                alinan |= {f"{n.module}.{a.name}" for a in n.names}
        assert not [a for a in alinan if any(a == y or a.startswith(y + ".") for y in yasak)], modul.__name__


# ---------------------------------------------------------------- gerçek veri

def _tutarlilik(g, p):
    """Plan tutarlılığı: hareketler vericinin karar fotoğrafı stoğunu aşmaz, alıcı hücre son stoğu ≤ asorti,
    tamamlanan her alıcının bütün bedenleri ≥ 1; alıcı verici olmaz, vericiler kırık çift."""
    stok = g.hucre.set_index(["magaza_id", "option_id", "beden_sira"]).stok
    h = p.hareketler
    assert (h.adet > 0).all()
    cikan = h.groupby(["verici", "option_id", "beden_sira"]).adet.sum()
    for (m, o, b), adet in cikan.items():
        assert adet <= stok.get((m, o, b), 0), (m, o, b)
    gelen = h.groupby(["alici", "option_id", "beden_sira"]).adet.sum()
    asorti = dict(zip(range(1, 6), sabitler.ASORTI))
    for (m, o, b), adet in gelen.items():
        assert stok.get((m, o, b), 0) + adet <= asorti[b], (m, o, b)
    for o, m in p.bilgi["tamamlanan_alicilar"]:
        son = {b: stok.get((m, o, b), 0) + gelen.get((m, o, b), 0) for b in range(1, 6)}
        assert min(son.values()) >= 1, (m, o, son)
    ciftler = set(zip(h.alici, h.option_id)) & set(zip(h.verici, h.option_id))
    assert not ciftler
    kirik = set(map(tuple, uygunluk.adaylar(g)[["magaza_id", "option_id"]].to_numpy()))
    assert all((v, o) in kirik for v, o in set(zip(h.verici, h.option_id)))
    assert sorted(map(tuple, h[["option_id", "alici", "verici", "beden_sira"]].to_numpy().tolist())) == \
        list(map(tuple, h[["option_id", "alici", "verici", "beden_sira"]].to_numpy().tolist()))


@pytest.mark.veri
def test_kural_plani_aw24_tutarli(veri_con):
    g = kaynak.karar_girdisi(veri_con, "AW24")
    t0 = time.time()
    p = kural.kural_plani(g)
    assert time.time() - t0 < 30
    assert not p.hareketler.empty
    _tutarlilik(g, p)
    assert len(p.bilgi["tamamlanan_alicilar"]) > 0


@pytest.mark.veri
def test_kural_plani_ss25_tutarli(veri_con):
    g = kaynak.karar_girdisi(veri_con, "SS25")
    p = kural.kural_plani(g, kol="kural")
    _tutarlilik(g, p)
    assert p.sezon == "SS25"
