"""Hikâye merdiveni (spec §6; `hikaye_sec`, oyuncak fikstür).

Oyuncak dünyada büyüğe kayık Anadolu mağazası S06 (Erzurum) ve küçüğe kayık İstanbul mağazası S01
vardır (`conftest.PROFIL`); stok fotoğrafları normalde hep doludur (`stoklu_gun` 7). Testler SS24
option'larının fotoğraflarını düzenleyerek sahneyi kurar: S06'da 4. ve 5. beden ilk haftalarda
rafsız gün görür, 1. beden pencere boyunca rafta kalır; S01'de tersi. Eğri oyuncakta elle kurulur
(profil ve kaynak sahnenin girdisidir; eğri tahmini `test_egri.py`'de sınanır).
"""

import json

import conftest
import numpy as np
import pandas as pd
import pytest

from beden_paket import egri as egri_modulu
from beden_paket import hikaye_kos, hikaye_sec, kaynak, sabitler

KARAR = conftest.KARAR
BAS = pd.Timestamp("2024-02-12")            # oyuncak SS24 ilk dağıtımının (varış cumartesi) ilk tam haftası
OPT = "OPT-SS24-A"


def _egri(profil: dict, okunamaz=()) -> egri_modulu.Egri:
    ids = list(profil)
    E = pd.DataFrame([conftest.PAY[p] for p in profil.values()], index=pd.Index(ids, name="magaza_id"),
                     columns=egri_modulu.SUTUNLAR)
    return egri_modulu.Egri(magaza=E, profil=pd.Series(profil, name="profil").rename_axis("magaza_id"),
                            zincir=np.array(conftest.PAY["orta"]),
                            kaynak={m: "profil" if m in okunamaz else "magaza" for m in ids})


def _sahne_egrisi(**degistir):
    return _egri({**conftest.PROFIL, **degistir}, okunamaz=(conftest.YENI,))


def _bosalt(t: dict, magaza: str, option: str, bedenler: dict) -> dict:
    """`bedenler`: beden sırası → (hafta, rafsız gün): varıştan sonraki o tam haftanın fotoğrafında
    (haftanın ertesi pazartesisi) `stoklu_gun` 7 − rafsız gün, o fotoğraf ve sonrasında adet 0."""
    t = dict(t)
    st = t["stok"].copy()
    u = t["urun"].set_index("urun_id")
    sira = st["urun_id"].map(u["beden_sira"])
    opt = st["urun_id"].map(u["option_id"]) == option
    for b, (hafta, bos) in bedenler.items():
        foto = BAS + pd.Timedelta(days=7 * hafta)
        m = opt & (sira == b) & (st["magaza_id"] == magaza)
        ayni = m & (st["tarih"] == foto)
        sonra = m & (st["tarih"] > foto)
        st.loc[ayni, "stoklu_gun"] = 7 - bos
        st.loc[ayni | sonra, "adet"] = 0
        st.loc[sonra, "stoklu_gun"] = 0
    t["stok"] = st
    return t


def _sahne(tablolar):
    t = _bosalt(tablolar, "S06", OPT, {4: (1, 3), 5: (2, 2)})
    return _bosalt(t, "S01", OPT, {1: (1, 4), 2: (2, 1)})


def test_hikaye_merdiveni(tablolar):
    """Sıkı kademe: aynı option'da büyük Anadolu mağazasında 4.–5. beden ilk iki haftada biter, 1.
    beden kalır; küçük İstanbul mağazasında tersi; ikisine de standart 1-2-2-1-1 paketi gider."""
    h = hikaye_sec.sec(_sahne(tablolar), _sahne_egrisi(), KARAR)
    assert (h.buyuk["magaza"], h.kucuk["magaza"]) == ("S06", "S01")
    assert h.buyuk["option"] == h.kucuk["option"] == OPT
    assert h.kademe == 0 and h.gevseyen == [] and h.roller == "kadro"
    assert h.buyuk["desen"] == h.kucuk["desen"] == "1-2-2-1-1"
    assert h.buyuk["paket"] == h.kucuk["paket"] == 3
    bb = {r["beden_sira"]: r for r in h.buyuk["bedenler"]}
    assert (bb[4]["biten_hafta"], bb[5]["biten_hafta"], bb[1]["biten_hafta"]) == (1, 2, None)
    assert bb[4]["bos_gun"] == 3 + 7 * (hikaye_sec.PENCERE_HAFTA - 1)     # biten hafta + sonraki boş haftalar
    assert bb[1]["bos_gun"] == 0 and bb[1]["kalan"] > 0
    assert [r["gelen"] for r in h.buyuk["bedenler"]] == [3, 6, 6, 3, 3]
    kb = {r["beden_sira"]: r for r in h.kucuk["bedenler"]}
    assert (kb[1]["biten_hafta"], kb[2]["biten_hafta"], kb[5]["biten_hafta"]) == (1, 2, None)
    assert h.buyuk["satis"] == sum(r["satis"] for r in h.buyuk["bedenler"]) > 0
    assert h.dogrulama is None and h.elenen == 0
    s = h.sozluk()
    assert s["buyuk"]["magaza"] == "S06" and s["alternatif"] is None


def test_hikaye_gevser_ve_kayda_yazar(tablolar):
    """Küçük mağazada 2. beden ancak 3. haftada biterse sıkı kademe tutmaz: erken pencere 3 haftaya
    gevşer ve kayda yazılır."""
    t = _bosalt(tablolar, "S06", OPT, {4: (1, 3), 5: (2, 2)})
    t = _bosalt(t, "S01", OPT, {1: (1, 4), 2: (3, 1)})
    h = hikaye_sec.sec(t, _sahne_egrisi(), KARAR)
    assert (h.buyuk["magaza"], h.kucuk["magaza"]) == ("S06", "S01")
    assert h.kademe == 1 and len(h.gevseyen) == 1 and "3 hafta" in h.gevseyen[0]


def test_hikaye_hedef_bedenler_once_biter(tablolar):
    """Küçük mağazada orta beden de ilk haftada biterse ders zayıflar ("1. ve 2. beden önce biter"
    tutmaz): sahne ancak sıra şartı gevşeyince bulunur ve kayda yazılır."""
    t = _bosalt(tablolar, "S06", OPT, {4: (1, 3), 5: (2, 2)})
    t = _bosalt(t, "S01", OPT, {1: (1, 4), 2: (2, 1), 3: (1, 2)})
    h = hikaye_sec.sec(t, _sahne_egrisi(), KARAR)
    assert (h.buyuk["magaza"], h.kucuk["magaza"]) == ("S06", "S01")
    assert h.kademe == len(hikaye_sec.MERDIVEN) - 2 and "sıra" in h.gevseyen[-1]
    h0 = hikaye_sec.sec(t, _sahne_egrisi(), KARAR, once=False)       # sonradan eklenen şart olmadan: sıkı kademe
    assert (h0.buyuk["magaza"], h0.kucuk["magaza"], h0.kademe) == ("S06", "S01", 0)


def test_hikaye_benzer_option(tablolar):
    """Küçük mağazanın tersi aynı option'da değil, aynı sezonun aynı beden setli başka option'ında
    yoksa (oyuncakta B Kadın Numara: set farklı) sahne düşer; aynı setli bir option olsaydı benzer
    option kademesi açılırdı. Burada sahne yok: hata."""
    t = _bosalt(tablolar, "S06", OPT, {4: (1, 3), 5: (2, 2)})
    t = _bosalt(t, "S01", "OPT-SS24-B", {1: (1, 4), 2: (2, 1)})
    with pytest.raises(ValueError, match="sahne"):
        hikaye_sec.sec(t, _sahne_egrisi(), KARAR)


def test_hikaye_roller_ters(tablolar):
    """Veride büyüğe kayık İstanbul, küçüğe kayık Anadolu mağazası varsa ve kadroya uyan çift yoksa
    kurgu veriye uyar: roller tersine döner, ders aynı kalır."""
    t = _bosalt(tablolar, "S01", OPT, {4: (1, 3), 5: (2, 2)})
    t = _bosalt(t, "S06", OPT, {1: (1, 4), 2: (2, 1)})
    e = _sahne_egrisi(S01="buyuk", S02="buyuk", S06="kucuk", S07="kucuk")
    h = hikaye_sec.sec(t, e, KARAR)
    assert (h.buyuk["magaza"], h.kucuk["magaza"]) == ("S01", "S06")
    assert h.roller == "ters" and any("roller" in g for g in h.gevseyen)


def test_hikaye_hakem_eler_ve_alternatif(tablolar):
    """Hakem (yalnız doğrulama; kayma argümanla gelir): ilk sahnenin büyük mağazası gerçekte büyüğe
    kayık değilse elenir, sıradaki sahne seçilir. Alternatif ilk sahnenin mağazalarını dışlar."""
    t = _sahne(tablolar)
    t = _bosalt(t, "S07", OPT, {4: (2, 1), 5: (2, 1)})        # ikinci büyük aday, daha geç biter
    t = _bosalt(t, "S02", OPT, {1: (2, 1), 2: (2, 1)})
    kayma = pd.Series({m: conftest.KAYMA[p] for m, p in conftest.PROFIL.items()}).astype(int)
    h = hikaye_sec.sec(t, _sahne_egrisi(), KARAR, kayma=kayma)
    assert (h.buyuk["magaza"], h.kucuk["magaza"]) == ("S06", "S01") and h.elenen == 0
    assert h.dogrulama == {"kayma": {"S06": 1, "S01": -1}, "buyuk": True, "kucuk": True}
    assert h.alternatif is not None
    assert {h.alternatif.buyuk["magaza"], h.alternatif.kucuk["magaza"]} == {"S07", "S02"}
    yanlis = kayma.copy()
    yanlis["S06"] = 0
    h2 = hikaye_sec.sec(t, _sahne_egrisi(), KARAR, kayma=yanlis)
    assert h2.buyuk["magaza"] == "S07" and h2.elenen >= 1


def test_hikaye_karar_sonrasini_gormez(tablolar):
    """Karar gününden sonraki stok ve sevkiyat satırları sahneyi değiştirmez; okunamayan mağaza
    (yedek eğri) sahneye girmez."""
    t = _sahne(tablolar)
    h = hikaye_sec.sec(t, _sahne_egrisi(), KARAR)
    t2 = dict(t)
    st = t["stok"].copy()
    st.loc[st["tarih"] >= KARAR, "stoklu_gun"] = 0
    t2["stok"] = st
    sv = t["sevkiyat"].copy()
    sv.loc[sv["tarih"] >= KARAR, "adet"] = 999
    t2["sevkiyat"] = sv
    assert hikaye_sec.sec(t2, _sahne_egrisi(), KARAR).sozluk() == h.sozluk()
    with pytest.raises(ValueError, match="sahne"):
        hikaye_sec.sec(t, _egri(conftest.PROFIL, okunamaz=("S06", "S07", conftest.YENI)), KARAR)


def test_hikaye_merdiveni_tanimi():
    """Merdiven sıkıdan gevşeğe; her kademe bir öncekine ekler; roller dersten önce gevşer, ders
    (önce biten, iki beden) en son."""
    m = hikaye_sec.MERDIVEN
    assert m[0].gevseyen == () and m[0].erken == hikaye_sec.ERKEN_HAFTA
    assert all(len(b.gevseyen) == len(a.gevseyen) + 1 for a, b in zip(m, m[1:]))
    assert m[-1].iki_beden is False and m[-2].once is False and m[-2].iki_beden is True
    assert m[-3].roller == "serbest" and m[-3].once is True
    assert sabitler.EGRI_PENCERE_HAFTA == hikaye_sec.PENCERE_HAFTA


def test_hikaye_kos_kaydi(tablolar):
    """Ölçüm yanının kaydı: sahne, iki mağazanın künyesi, kod özeti, hakemsiz seçimle aynı mı; JSON'a yazılır."""
    t = _sahne(tablolar)
    g = {"tablolar": t, "kapsam": kaynak.kapsam(t, KARAR), "egri": _sahne_egrisi(), "karar_gunu": KARAR}
    h = hikaye_sec.sec(t, g["egri"], KARAR)
    out = hikaye_kos.kayit(g, h, h, hikaye_sec.sec(t, g["egri"], KARAR, once=False))
    assert out["kod"] == hikaye_kos.kod_ozeti() and out["karar_gunu"] == "2025-02-07"
    assert set(out["magazalar"]) == {"S06", "S01"} and out["magazalar"]["S01"]["istanbul"] is True
    assert out["hakemsiz_ayni"] is True and out["buyuk"]["magaza"] == "S06"
    assert out["once_sarti"]["sonradan"] is True and out["once_sarti"]["ayni"] is True
    assert out["once_sarti"]["oncesiz"]["kademe"] == 0
    assert json.loads(json.dumps(out, ensure_ascii=False)) == out
