from dataclasses import dataclass


@dataclass(frozen=True)
class Parametreler:
    """Bütün sayısal sabitler tek yerde (spec §4). Gerekçeler paket README'sinde."""
    hiz_penceresi_hafta: int = 8
    ufuk_hafta: int = 8
    soguma_hafta: int = 2
    min_koli: int = 6
    adet_maliyeti_tl: float = 25.0
    rota_sabiti_tl: float = 500.0
    buyuk_cover: float = 999.0
    mip_zaman_limiti_sn: int = 60
    verici_cover_esigi: float = 6.0   # senaryo parametresi: gönderen mağazada asgari cover
    alici_cover_tavani: float = 0.0   # senaryo parametresi: alıcıda azami cover; 0 = kapalı
    min_satis: float = 1.0       # senaryo parametresi
