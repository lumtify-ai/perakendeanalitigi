"""v4 günlük stok-satış motoru (Görev 12–14).

    durum.py   Durum, Gorunum, yolda kuyruğu, kayıt tamponları, orantili_kes
    satis.py   fiyat, talep çekimi, satış, iade
    dongu.py   simule_et (günlük sıra; belgesi motorun sözleşmesidir)
"""

from .dongu import simule_et
from .durum import Gorunum

__all__ = ["Gorunum", "simule_et"]
