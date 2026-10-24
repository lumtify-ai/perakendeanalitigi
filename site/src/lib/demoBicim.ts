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
  // İndirim Takvimi: rapor para ve adet kartlarını bir ondalıkla basar
  // (milyon TL, bin adet, yüzde). Tam fiyat STR kartı `tf_str` adıyla gelir:
  // İlk Sevkiyat demosunun `tam_fiyat_str` kartı tam sayı basmaya devam eder,
  // sözlüğe girmez; yoksa o demonun çıktısı değişirdi.
  katki_farki_mtl: 1,
  olu_stok_bin: 1,
  markdown_mtl: 1,
  son_str: 1,
  tf_str: 1,
}

/** Bir demo ölçütünün değerini Türkçe sayı biçimiyle basar. */
export function demoDegeri(olcut: string, deger: number): string {
  const ondalik = ONDALIK[olcut]
  if (ondalik === undefined) return deger.toLocaleString('tr-TR')
  // Yuvarlanınca sıfır çıkan değer eksi işaretsiz basılır ("-0,0" değil).
  if (Math.abs(deger) < 0.5 / 10 ** ondalik) deger = 0
  return deger.toLocaleString('tr-TR', {
    minimumFractionDigits: ondalik,
    maximumFractionDigits: ondalik,
  })
}
