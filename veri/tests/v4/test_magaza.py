"""Testler: Görev 4 mağazalar, gizli segmentler, mağaza olayları, ölçek.

Spec: docs/superpowers/specs/2026-09-27-veri-v4-cekirdek-design.md §2.2, §2.3, §6.3
Brief: .superpowers/sdd/2026-09-27-veri-v4-cekirdek/task-4-brief.md
"""

import numpy as np
import pandas as pd
import pytest

from perakende_veri.v4 import sabitler
from perakende_veri.v4.magaza import Olcek, alt_kume, magazalari_uret, olaylari_uret
from perakende_veri.v4.rastgele import dunya_akisi


def _haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    lat1r, lon1r = np.radians(float(lat1)), np.radians(float(lon1))
    lat2r = np.radians(np.asarray(lat2, dtype=float))
    lon2r = np.radians(np.asarray(lon2, dtype=float))
    dphi = lat2r - lat1r
    dl = lon2r - lon1r
    a = np.sin(dphi / 2) ** 2 + np.cos(lat1r) * np.cos(lat2r) * np.sin(dl / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


@pytest.fixture(scope="module")
def m():
    return magazalari_uret(dunya_akisi())


@pytest.fixture(scope="module")
def olay(m):
    return olaylari_uret(dunya_akisi(), m[0], m[1])


def test_sayilar(m):
    fiz = m[0][m[0].tip != "Online"]
    assert len(fiz) == 84 and (m[0].magaza_id == "ONL").sum() == 1


def test_tip_paylari(m):
    assert m[0].tip.value_counts().to_dict() == {
        "AVM": 47, "Cadde": 27, "Outlet": 10, "Online": 1,
    }


def test_her_segment_en_az_alti(m):
    assert m[1].query("segment != 'online'").segment.value_counts().min() >= 6


def test_pencere_basinda_78_sonunda_80(m, olay):
    fiziksel = m[0][m[0].tip != "Online"]

    def acik_sayisi(tarih):
        t = pd.Timestamp(tarih)
        acilmis = fiziksel.acilis_tarihi <= t
        kapanmamis = fiziksel.kapanis_tarihi.isna() | (fiziksel.kapanis_tarihi > t)
        return int((acilmis & kapanmamis).sum())

    assert acik_sayisi(sabitler.BASLANGIC) == 78
    assert acik_sayisi(sabitler.BITIS) == 80


def test_kapanis_profilleri(m, olay):
    magazalar = m[0].set_index("magaza_id")
    kapananlar = olay.query("olay == 'kapanis'").magaza_id.tolist()
    assert len(kapananlar) == 4

    fiziksel = m[0][m[0].tip != "Online"]
    outletler = fiziksel[fiziksel.tip == "Outlet"]

    def en_yakin_diger_uzaklik(mid):
        lat0, lon0 = magazalar.loc[mid, ["enlem", "boylam"]]
        digerleri = fiziksel[fiziksel.magaza_id != mid]
        d = _haversine_km(lat0, lon0, digerleri.enlem.to_numpy(), digerleri.boylam.to_numpy())
        return d.min() if len(d) else np.inf

    def outlete_uzaklik(mid):
        lat0, lon0 = magazalar.loc[mid, ["enlem", "boylam"]]
        d = _haversine_km(lat0, lon0, outletler.enlem.to_numpy(), outletler.boylam.to_numpy())
        return d.min() if len(d) else np.inf

    # (1) çok mağazalı şehir (>= 5 fiziksel mağaza)
    assert any(sabitler.SEHIR_MAGAZA_SAYISI[magazalar.loc[mid, "sehir"]] >= 5 for mid in kapananlar)
    # (2) 150 km içinde başka fiziksel mağaza yok
    assert any(en_yakin_diger_uzaklik(mid) > 150 for mid in kapananlar)
    # (3) 100 km içinde bir outlet var
    assert any(outlete_uzaklik(mid) < 100 for mid in kapananlar)
    # (4) olay_tarihi bir sezonun indirim döneminde ([indirim, çıkış))
    olay_tarihleri = olay.query("olay == 'kapanis'").olay_tarihi

    def indirimde_mi(t):
        t = t.date()
        return any(s["indirim"] <= t < s["cikis"] for s in sabitler.SEZONLAR.values())

    assert any(indirimde_mi(t) for t in olay_tarihleri)
    # kapanan mağazalar AVM ya da Cadde
    assert set(magazalar.loc[kapananlar, "tip"]) <= {"AVM", "Cadde"}


def test_karar_olay_araligi(olay):
    assert (
        olay.query("olay=='kapanis'")
        .eval("(olay_tarihi-karar_tarihi).dt.days")
        .between(28, 42)
        .all()
    )
    assert (
        olay.query("olay=='tadilat'")
        .eval("(olay_tarihi-karar_tarihi).dt.days")
        .between(21, 42)
        .all()
    )


def test_acilis_zamanlamasi(olay):
    acilislar = olay.query("olay == 'acilis'")
    assert len(acilislar) == 6
    dalga1ler = [pd.Timestamp(s["dalgalar"][0]) for s in sabitler.SEZONLAR.values()]

    tam_pazartesi = sum(1 for t in acilislar.olay_tarihi if t in dalga1ler)
    orta_sezon = sum(
        1
        for t in acilislar.olay_tarihi
        if t not in dalga1ler
        and any(
            pd.Timedelta(28, unit="D") <= (t - w) <= pd.Timedelta(70, unit="D")
            for w in dalga1ler
        )
    )
    assert tam_pazartesi == 2
    assert orta_sezon == 4
    assert acilislar.olay_tarihi.between(
        pd.Timestamp(sabitler.BASLANGIC), pd.Timestamp(sabitler.BITIS)
    ).all()


def test_kucuk_olcek_kapsami(m, olay):
    magazalar, gizli = m
    mask = alt_kume(magazalar, gizli, olay, Olcek.KUCUK)
    secili = magazalar[mask]
    fiziksel = secili[secili.tip != "Online"]

    assert len(fiziksel) == 20
    assert (secili.magaza_id == "ONL").sum() == 1
    assert set(fiziksel.tip) >= {"AVM", "Cadde", "Outlet"}

    gizli_secili = gizli[gizli.magaza_id.isin(secili.magaza_id)]
    assert set(gizli_secili.segment) >= set(sabitler.SEGMENTLER)

    olay_magazalari = set(olay.magaza_id.unique())
    assert olay_magazalari <= set(secili.magaza_id)


def test_segment_yayimlanan_tabloda_yok(m):
    assert "segment" not in m[0].columns and "gelir" not in m[0].columns
