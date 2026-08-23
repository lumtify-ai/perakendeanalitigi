// site/tests/build.test.ts
import { execSync } from 'node:child_process'
import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { beforeAll, describe, expect, it } from 'vitest'

const DIST = fileURLToPath(new URL('../dist/', import.meta.url))

function oku(yol: string): string {
  return readFileSync(DIST + yol, 'utf-8')
}

beforeAll(() => {
  execSync('npm run build', { cwd: fileURLToPath(new URL('..', import.meta.url)), stdio: 'inherit' })
}, 300_000)

describe('build çıktısı', () => {
  it('türkçe ana sayfa üretilir', () => {
    expect(existsSync(DIST + 'tr/index.html')).toBe(true)
  })

  it('kök adres türkçeye yönlenir', () => {
    expect(existsSync(DIST + 'index.html')).toBe(true)
    expect(oku('index.html')).toContain('/tr/')
  })

  it('sayfa dili türkçe işaretlenir', () => {
    expect(oku('tr/index.html')).toContain('lang="tr"')
  })
})

describe('içerik koleksiyonları', () => {
  it('beş koleksiyon da dolu', async () => {
    const { readdirSync } = await import('node:fs')
    const icerik = fileURLToPath(new URL('../src/content/', import.meta.url))
    for (const ad of ['alan', 'dizi', 'yazi', 'sozluk', 'kadro']) {
      expect(readdirSync(icerik + ad).length).toBeGreaterThan(0)
    }
  })
})

describe('temel düzen', () => {
  it('üst menü her sayfada var', () => {
    const html = oku('tr/index.html')
    expect(html).toContain('href="/tr/veri-seti/"')
    expect(html).toContain('href="/tr/sozluk/"')
  })

  it('sayfa açıklaması meta olarak basılır', () => {
    expect(oku('tr/index.html')).toContain('name="description"')
  })

  it('hiçbir sayfada tarih görünmez', () => {
    // Ana spec'in başarısızlık işareti: "son yazı: 4 ay önce"
    const html = oku('tr/index.html')
    expect(html).not.toMatch(/\d{1,2}\s+(Ocak|Şubat|Mart|Nisan|Mayıs|Haziran|Temmuz|Ağustos|Eylül|Ekim|Kasım|Aralık)/)
  })
})

describe('sözlük', () => {
  it('sözlük sayfası her maddeyi çapayla basar', () => {
    const html = oku('tr/sozluk/index.html')
    expect(html).toContain('id="cover"')
    expect(html).toContain('id="kiriklik"')
    expect(html).toContain('Sell-Through Rate')
  })

  it('sözlük DefinedTermSet olarak işaretlenir', () => {
    expect(oku('tr/sozluk/index.html')).toContain('DefinedTermSet')
  })

  it('tooltip tanımı HTML içinde durur', () => {
    // Yapay zekâ tarayıcıları JS çalıştırmaz; tanım DOM'da olmalı
    const html = oku('tr/transfer/blok-transfer/sonuclar/index.html')
    expect(html).toContain('class="terim"')
    expect(html).toContain('yeterlilik süresi')
  })

  it('tooltip için script üretilmez', () => {
    const html = oku('tr/transfer/blok-transfer/sonuclar/index.html')
    expect(html).not.toMatch(/<script(?![^>]*type="application\/ld\+json")/)
  })
})

describe('kadro', () => {
  it('kadro sayfası üç karakteri de tanıtır', () => {
    const html = oku('tr/kadro/index.html')
    expect(html).toContain('Ali')
    expect(html).toContain('Veli')
    expect(html).toContain('Pelin')
    expect(html).toContain('Allocator')
    expect(html).toContain('Planner')
  })
})

describe('yazı sayfası', () => {
  it('dizili yazı üretilir', () => {
    expect(existsSync(DIST + 'tr/transfer/blok-transfer/sonuclar/index.html')).toBe(true)
  })

  it('tekil alanın yazısı üretilir', () => {
    expect(existsSync(DIST + 'tr/temeller/urun-hiyerarsisi/index.html')).toBe(true)
  })

  it('rozet ve kırıntı yolu basılır', () => {
    const html = oku('tr/transfer/blok-transfer/sonuclar/index.html')
    expect(html).toContain('rozet-sonuc')
    expect(html).toContain('BreadcrumbList')
    expect(html).toContain('href="/tr/transfer/blok-transfer/"')
  })

  it('teknik ve sonuç yazıları TechArticle işaretlenir', () => {
    expect(oku('tr/transfer/blok-transfer/sonuclar/index.html')).toContain('TechArticle')
  })

  it('hikâye yazısı Article işaretlenir', () => {
    const html = oku('tr/transfer/blok-transfer/magazanin-sorunu/index.html')
    expect(html).toContain('"@type":"Article"')
  })

  it('dizi gezinmesi önceki ve sonrakini verir', () => {
    const html = oku('tr/transfer/blok-transfer/matematiksel-model/index.html')
    expect(html).toContain('href="/tr/transfer/blok-transfer/karar-nasil-verilir/"')
    expect(html).toContain('href="/tr/transfer/blok-transfer/sql-ve-python/"')
  })

  it('hikâye yazısı kadro kutusuyla açılır', () => {
    const html = oku('tr/transfer/blok-transfer/magazanin-sorunu/index.html')
    expect(html).toContain('kadro-kutusu')
    expect(html).toContain('Allocator')
  })
})
