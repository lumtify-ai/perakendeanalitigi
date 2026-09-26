"""Sızıntı kalkanı: kâhin dışındaki kollar gelecekteki talebi görmez."""

import dataclasses

import numpy as np
import pytest

from rpt import oyun


def _siparisler(ham, once):
    return sorted((s["option"], s["siparis_gun"], int(np.sum(s["adetler"])))
                  for s in ham["siparis"] if s["tip"] == "rpt" and s["siparis_gun"] < once)


@pytest.mark.veri
@pytest.mark.parametrize("kol", ["mevcut", "frr3", "oneri", "kahin"])
def test_gelecek_talep_karari_degistirmez(yol0, kol):
    b = yol0["baglam"]
    w = b.dunya
    # SS25'in içinde bir pazartesi: sonrasının talebi bozulur
    kesim = int(w.optionlar.loc[w.optionlar["sezon_kodu"] == "SS25", "lansman_gun"].min()) + 7 * 12
    T2 = b.talep.copy()
    T2[kesim:] = T2[kesim:] * 3
    b2 = dataclasses.replace(b, talep=T2)
    ham1, _, _ = oyun.kos(b, kol, "d")
    ham2, _, _ = oyun.kos(b2, kol, "d")
    ayni = _siparisler(ham1, kesim) == _siparisler(ham2, kesim)
    if kol == "kahin":
        assert not ayni          # kâhin geleceği görür: kalkanın sınadığı şeyin sağlaması
    else:
        assert ayni


@pytest.mark.veri
def test_oneri_en_fazla_bir_rpt_oyun_disi_ayni(yol0):
    b = yol0["baglam"]
    ham, _, _ = oyun.kos(b, "oneri", "d")
    opt = b.dunya.optionlar
    maske = b.oyun_maskesi()
    oyun_rpt = [s["option"] for s in ham["siparis"] if s["tip"] == "rpt" and maske[s["option"]]]
    assert len(oyun_rpt) == len(set(oyun_rpt))
    ref = yol0["ham"][("mevcut", "mevcut")]

    def dis(h):
        return sorted((s["option"], s["siparis_gun"]) for s in h["siparis"]
                      if s["tip"] == "rpt" and not maske[s["option"]]
                      and opt.at[s["option"], "sezon_kodu"] in ("SS24", "AW23"))

    assert dis(ham) == dis(ref)
