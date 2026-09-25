from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
V2_DB = KOK.parents[1] / "veri" / "cikti" / "v2" / "perakende.duckdb"
CIKTI = KOK / "cikti"

OYUN_BAS, OYUN_BIT = "2025-09-01", "2025-12-31"
ON_OYUN_BAS, ON_OYUN_BIT = "2025-05-05", "2025-08-31"
KARAR_SAYISI = 17

KOLI = (1, 2, 2, 2, 1)
KOLI_ADET = 8
ACIK_PAYI = {"Collection": 0.20, "Outlet": 0.20, "NOS": 0.40, "Basic": 0.40}
TEK_ALIM_LINE = ("Collection", "Outlet")
# En sikisi (%30) kitligi gercekten isirtmak icin var: %60'ta bile depo
# donem sonunda 36 bin adetle kapaniyor ve uc paylastirma onceligi ayni
# sonucu veriyor. Kitlik yokken paylastirma kuralini tartismak bos.
ALIM_ORANLARI = (0.30, 0.60, 0.80, 1.00)
EN_SIKI_ALIM = 0.30
TEDARIK_HEDEF_HAFTA = 6

ACIK_TL_ADET = 10.0
ACIK_TL_DUYARLILIK = (5.0, 10.0, 20.0)
KOLI_TL = 20.0
ACIK_KAPASITE_ORANI = 0.25
ACIK_KAPASITE_DUYARLILIK = (0.15, 0.25, 0.40)

IADE_ORANI = 0.06
IADE_GECIKME = 7
YOL_SAYISI = 20
YOL_TOHUM_TABANI = 1000
IADE_TOHUM = 7
