// site/tests/renk.test.ts
//
// Renk değişkenlerinin okunabilirlik sözleşmesi. Palet tek dosyada
// (src/styles/site.css, `:root` ve koyu tema bloğu) yaşıyor ve bütün
// bileşenler rengi yalnızca oradan okuyor; o yüzden kontrastı da orada,
// değişkenler üzerinden kilitlemek yetiyor.
//
// Neden var: 2026-09-26 tasarım incelemesi açık temada `--soluk` metnin
// `--kutu-zemin` üstünde 4,31:1'de kaldığını (AA sınırı 4,5) ve bağlantı alt
// çizgisinin (`--vurgu-cizgi`) iki temada da 1,5:1 civarında neredeyse
// görünmez olduğunu buldu. Hiçbir test bunu yakalamıyordu; göz kararı palet
// seçimi aynı hatayı tekrar yapabilir.
//
// Ölçüt WCAG 2.2: gövde metni için 4,5:1 (AA), metin olmayan arayüz öğesi
// (alt çizgi, nokta halkası) için 3:1 (1.4.11). Gövde metnine 7:1 (AAA)
// isteniyor, çünkü site uzun okuma için var.
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const CSS = readFileSync(
  fileURLToPath(new URL('../src/styles/site.css', import.meta.url)),
  'utf-8',
)

/** Bir CSS bloğundaki `--ad: #rrggbb` değişkenleri. */
function degiskenler(blok: string): Record<string, string> {
  const sonuc: Record<string, string> = {}
  for (const [, ad, deger] of blok.matchAll(/--([a-z-]+):\s*(#[0-9a-fA-F]{6})\b/g)) {
    sonuc[ad] = deger.toLowerCase()
  }
  return sonuc
}

/** İlk `:root { … }` bloğu açık tema, koyu medya sorgusundaki blok koyu tema. */
function temalar(): { acik: Record<string, string>; koyu: Record<string, string> } {
  const acikBlok = CSS.match(/:root\s*\{([^}]*)\}/)
  const koyuBlok = CSS.match(/@media\s*\(prefers-color-scheme:\s*dark\)\s*\{\s*:root[^{]*\{([^}]*)\}/)
  if (!acikBlok || !koyuBlok) throw new Error('site.css içinde tema blokları bulunamadı')
  return { acik: degiskenler(acikBlok[1]), koyu: degiskenler(koyuBlok[1]) }
}

function goreliParlaklik(hex: string): number {
  const kanal = (i: number) => {
    const c = parseInt(hex.slice(1 + i * 2, 3 + i * 2), 16) / 255
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  }
  return 0.2126 * kanal(0) + 0.7152 * kanal(1) + 0.0722 * kanal(2)
}

export function kontrast(a: string, b: string): number {
  const [acik, koyu] = [goreliParlaklik(a), goreliParlaklik(b)].sort((x, y) => y - x)
  return (acik + 0.05) / (koyu + 0.05)
}

/** [ön plan, zemin, asgari oran, ne için] */
const CIFTLER: [string, string, number, string][] = [
  ['ink', 'bg', 7, 'gövde metni'],
  ['koyu', 'bg', 7, 'başlık ve kalın metin'],
  ['ink', 'kutu-zemin', 4.5, 'kutu içindeki metin'],
  ['ink', 'kod-zemin', 4.5, 'kod'],
  ['ink', 'tablo-baslik', 4.5, 'tablo başlığı'],
  ['soluk', 'bg', 4.5, 'soluk metin'],
  ['soluk', 'kutu-zemin', 4.5, 'kutudaki soluk metin (faz kartı, dizi kartı)'],
  ['vurgu', 'bg', 4.5, 'bağlantı metni'],
  ['vurgu', 'vurgu-zemin', 4.5, 'vurgu zemininde bağlantı'],
  ['rozet-ink', 'rozet-zemin', 4.5, 'tip rozeti'],
  ['tooltip-ink', 'tooltip-zemin', 4.5, 'sözlük ipucu'],
  ['ink', 'uyari-zemin', 4.5, 'uyarı kutusu'],
  ['vurgu-cizgi', 'bg', 3, 'bağlantı alt çizgisi (metin dışı öğe)'],
  ['soluk', 'bg', 3, 'soluk istasyon halkası (metin dışı öğe)'],
]

describe('renk paleti', () => {
  const { acik, koyu } = temalar()

  for (const [tema, degerler] of [['açık', acik], ['koyu', koyu]] as const) {
    describe(`${tema} tema`, () => {
      for (const [on, zemin, asgari, ne] of CIFTLER) {
        it(`${ne}: --${on} / --${zemin} en az ${asgari}:1`, () => {
          expect(degerler[on], `--${on} tanımlı değil`).toBeDefined()
          expect(degerler[zemin], `--${zemin} tanımlı değil`).toBeDefined()
          const oran = kontrast(degerler[on], degerler[zemin])
          expect(oran, `${degerler[on]} / ${degerler[zemin]} = ${oran.toFixed(2)}`).toBeGreaterThanOrEqual(asgari)
        })
      }
    })
  }

  it('koyu tema açık temadaki her renk değişkenini yeniden tanımlar', () => {
    expect(Object.keys(koyu).sort()).toEqual(Object.keys(acik).sort())
  })
})
