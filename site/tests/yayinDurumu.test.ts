// site/tests/yayinDurumu.test.ts
//
// `hazirlaniyor` yazılar üretilir ama site haritasında ilan edilmez. Süzgeç
// astro.config.mjs içinden çağrılır; burada gerçek içerik ağacı üzerinde
// doğrulanır.
import { mkdtempSync, mkdirSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { hazirlaniyorAdresleri, sitemapSuzgeci } from '../src/lib/yayinDurumu.mjs'

// Windows'ta new URL().pathname sürücü harfini bozar; fileURLToPath şart
const YAZI_KOKU = fileURLToPath(new URL('../src/content/yazi/', import.meta.url))

describe('hazirlaniyorAdresleri', () => {
  it('sentetik ağaçtaki hazırlanıyor yazıyı bulur, yayındakini bulmaz', () => {
    // Gerçek içerik ağacında şu an taslak yok (aşağıdaki test). Mekanizmanın
    // kendisi içeriğin durumuna bağlı kalmasın diye sentetik ağaçta sınanır.
    const kok = mkdtempSync(join(tmpdir(), 'yayin-'))
    mkdirSync(join(kok, 'alan', 'dizi'), { recursive: true })
    const yaz = (yol: string, durum: string) =>
      writeFileSync(join(kok, yol), `---
baslik: X
tip: teknik
sira: 1
durum: ${durum}
---
`)
    yaz(join('alan', 'dizi', 'taslak.mdx'), 'hazirlaniyor')
    yaz(join('alan', 'dizi', 'yayinda.mdx'), 'yayinda')

    const adresler = hazirlaniyorAdresleri(kok)
    expect(adresler).toEqual(['/tr/alan/dizi/taslak/'])
  })

  it('gerçek içerikte şu an hazırlanıyor yazı yok', () => {
    // Yedi yazının tamamı yayında. Bu satır düşerse bir taslak eklenmiş
    // demektir; o zaman site haritası ve noindex testleri de güncellenmeli.
    expect(hazirlaniyorAdresleri(YAZI_KOKU)).toEqual([])
  })

  it('her adres eğik çizgiyle biter ve /tr/ ile başlar', () => {
    for (const adres of hazirlaniyorAdresleri(YAZI_KOKU)) {
      expect(adres).toMatch(/^\/tr\/.+\/$/)
    }
  })

  it('var olmayan kökte boş dizi döner', () => {
    expect(hazirlaniyorAdresleri(YAZI_KOKU + 'yok-boyle-bir-dizin')).toEqual([])
  })
})

describe('sitemapSuzgeci', () => {
  const suzgec = sitemapSuzgeci(['/tr/transfer/blok-transfer/sonuclar/'])

  it('dışarıda bırakılan adresi eler', () => {
    expect(suzgec('https://perakendeanalitigi.com/tr/transfer/blok-transfer/sonuclar/')).toBe(false)
  })

  it('diğer adresleri geçirir', () => {
    expect(suzgec('https://perakendeanalitigi.com/tr/transfer/blok-transfer/')).toBe(true)
    expect(suzgec('https://perakendeanalitigi.com/tr/')).toBe(true)
  })
})
