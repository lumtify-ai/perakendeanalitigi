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
    tepe_hafta: int = 52          # tepe talep ufku (hafta)
    olcum_hafta: int = 8          # karar anından sonraki ölçüm penceresi (hafta)
    mip_zaman_limiti_sn: int = 3600
    mip_dugum_limiti: int | None = 10_000  # emniyet; süre limitinden önce bağlar (Görev 5 ölçümü)
    # MIP sonlanma ölçütü: göreli boşluk. Durum "optimal" = CBC bu tolerans içinde
    # durdu, kanıtlı optimum değil: plan optimuma en fazla bu oran kadar uzak.
    mip_bosluk_orani: float = 5e-3        # %0,5; Görev 5 ölçümü (kayıt defteri, Ruling)
    verici_cover_esigi: float = 6.0   # senaryo parametresi: gönderen mağazada asgari cover
    alici_cover_tavani: float = 0.0   # senaryo parametresi: alıcıda azami cover; 0 = kapalı
    min_satis: float = 1.0       # senaryo parametresi
