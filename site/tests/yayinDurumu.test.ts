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
import {
  hazirlaniyorAdresleri,
  pasifAsamaAdresleri,
  sitemapSuzgeci,
} from '../src/lib/yayinDurumu.mjs'

// Windows'ta new URL().pathname sürücü harfini bozar; fileURLToPath şart
const YAZI_KOKU = fileURLToPath(new URL('../src/content/yazi/', import.meta.url))
const ALAN_KOKU = fileURLToPath(new URL('../src/content/alan/', import.meta.url))

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
    expect(adresler).toEqual(['/alan/dizi/taslak/'])
  })

  it('gerçek içerikte şu an hazırlanıyor yazı yok', () => {
    // Bütün yazılar yayında. Bu satır düşerse bir taslak eklenmiş demektir;
    // o zaman site haritası ve noindex testleri de güncellenmeli.
    expect(hazirlaniyorAdresleri(YAZI_KOKU)).toEqual([])
  })

  it('her adres eğik çizgiyle başlar ve biter', () => {
    for (const adres of hazirlaniyorAdresleri(YAZI_KOKU)) {
      expect(adres).toMatch(/^\/.+\/$/)
    }
  })

  it('var olmayan kökte boş dizi döner', () => {
    expect(hazirlaniyorAdresleri(YAZI_KOKU + 'yok-boyle-bir-dizin')).toEqual([])
  })
})

describe('sitemapSuzgeci', () => {
  const suzgec = sitemapSuzgeci(['/transfer/blok-transfer/sonuclar/'])

  it('dışarıda bırakılan adresi eler', () => {
    expect(suzgec('https://perakendeanalitigi.com/transfer/blok-transfer/sonuclar/')).toBe(false)
  })

  it('diğer adresleri geçirir', () => {
    expect(suzgec('https://perakendeanalitigi.com/transfer/blok-transfer/')).toBe(true)
    expect(suzgec('https://perakendeanalitigi.com/')).toBe(true)
  })
})

describe('pasifAsamaAdresleri', () => {
  // Sentetik ağaç: taslak (yalnız hazırlanıyor), karma, yayında, yazısız
  // aşama ve yalnız taslağı olan Temeller.
  function agacKur() {
    const kok = mkdtempSync(join(tmpdir(), 'asama-'))
    const alanKoku = join(kok, 'alan')
    const yaziKoku = join(kok, 'yazi')
    mkdirSync(alanKoku, { recursive: true })
    for (const alan of ['indirim', 'rpt', 'transfer', 'crm', 'temeller']) {
      writeFileSync(join(alanKoku, `${alan}.md`), '---\ntanim: X\n---\n')
    }
    const yaz = (yol: string, durum?: string) => {
      const tam = join(yaziKoku, yol)
      mkdirSync(join(tam, '..'), { recursive: true })
      writeFileSync(tam, `---\nbaslik: X\n${durum ? `durum: ${durum}\n` : ''}---\n`)
    }
    yaz('indirim/markdown/a.mdx', 'hazirlaniyor')
    yaz('indirim/markdown/b.mdx', 'hazirlaniyor')
    yaz('rpt/tekrar-siparis/a.mdx', 'hazirlaniyor')
    yaz('rpt/tekrar-siparis/b.mdx', 'yayinda')
    // Şema varsayılanı yayında: durum yazılmamışsa yayında sayılır.
    yaz('transfer/blok-transfer/a.mdx')
    yaz('temeller/taslak.mdx', 'hazirlaniyor')
    return { alanKoku, yaziKoku }
  }

  it('yalnız hazırlanıyor yazısı olan aşamayı ve yazısız aşamayı dışarıda bırakır', () => {
    const { alanKoku, yaziKoku } = agacKur()
    expect(pasifAsamaAdresleri(alanKoku, yaziKoku).sort()).toEqual(['/crm/', '/indirim/'])
  })

  it('karma aşama, varsayılan durumlu aşama ve Temeller dahil kalır', () => {
    const { alanKoku, yaziKoku } = agacKur()
    const pasifler = pasifAsamaAdresleri(alanKoku, yaziKoku)
    expect(pasifler).not.toContain('/rpt/')
    expect(pasifler).not.toContain('/transfer/')
    expect(pasifler).not.toContain('/temeller/')
  })

  it('gerçek içerikte bütün aşamalar aktif', () => {
    expect(pasifAsamaAdresleri(ALAN_KOKU, YAZI_KOKU)).toEqual([])
  })

  it('var olmayan kökte boş dizi döner', () => {
    expect(pasifAsamaAdresleri(ALAN_KOKU + 'yok', YAZI_KOKU)).toEqual([])
  })
})
