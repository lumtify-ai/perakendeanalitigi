// site/src/lib/demoBicim.ts

/**
 * Demo kartında sabit ondalıkla basılan ölçütler. Rapor ve yazılar bu
 * ölçütleri bu kadar ondalıkla basar; `toLocaleString` sondaki sıfırları
 * attığı için ARI 1.0 "1", kararlılık 0.97 "0,97", bulunabilirlik 97.0 "97"
 * görünürdü.
 */
const ONDALIK: Record<string, number> = {
  hakem_ari: 3,
  kararlilik: 3,
  siluet: 3,
  // Beden ve Koli: rapor ilk 4 hafta yüzdelerini bir ondalıkla, brüt kârı
  // tam TL olarak basar.
  bulunabilirlik_ilk4: 1,
  beden_kayip_payi_ilk4: 1,
  kirik_cift_pay_yuzde_ilk4: 1,
  brut_kar_tl: 0,
}

/** Bir demo ölçütünün değerini Türkçe sayı biçimiyle basar. */
export function demoDegeri(olcut: string, deger: number): string {
  const ondalik = ONDALIK[olcut]
  if (ondalik === undefined) return deger.toLocaleString('tr-TR')
  return deger.toLocaleString('tr-TR', {
    minimumFractionDigits: ondalik,
    maximumFractionDigits: ondalik,
  })
}
