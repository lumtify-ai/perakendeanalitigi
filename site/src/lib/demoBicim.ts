// site/src/lib/demoBicim.ts

/**
 * Demo kartında sabit ondalıkla basılan ölçütler. Rapor ve yazılar bu
 * ölçütleri bu kadar ondalıkla basar; `toLocaleString` sondaki sıfırları
 * attığı için ARI 1.0 "1", kararlılık 0.97 "0,97" görünürdü.
 */
const ONDALIK: Record<string, number> = {
  hakem_ari: 3,
  kararlilik: 3,
  siluet: 3,
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
