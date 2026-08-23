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

describe('dizi sayfası', () => {
  it('beş yazıyı sırayla listeler', () => {
    const html = oku('tr/transfer/blok-transfer/index.html')
    const sira = ['magazanin-sorunu', 'karar-nasil-verilir', 'matematiksel-model', 'sql-ve-python', 'sonuclar']
    const yerler = sira.map((slug) => html.indexOf(slug))
    expect(yerler.every((y) => y > -1)).toBe(true)
    expect([...yerler].sort((a, b) => a - b)).toEqual(yerler)
  })

  it('kısayolu açıkça söyler', () => {
    expect(oku('tr/transfer/blok-transfer/index.html')).toMatch(/hikâye|hikaye/i)
  })

  it('CreativeWorkSeries olarak işaretlenir', () => {
    expect(oku('tr/transfer/blok-transfer/index.html')).toContain('CreativeWorkSeries')
  })
})

describe('alan sayfası', () => {
  it('dizili alan dizileri listeler', () => {
    const html = oku('tr/transfer/index.html')
    expect(html).toContain('href="/tr/transfer/blok-transfer/"')
  })

  it('tekil alan yazıları listeler', () => {
    const html = oku('tr/temeller/index.html')
    expect(html).toContain('href="/tr/temeller/urun-hiyerarsisi/"')
  })

  it('tanım paragrafıyla açılır', () => {
    // Hikâyeyle açılan sayfa alıntılanmaz (ana spec §9)
    const html = oku('tr/transfer/index.html')
    const govde = html.slice(html.indexOf('<main'))
    expect(govde).toMatch(/Transfer,\s*bir mağazada/)
  })

  it('alan sayfası kod içermez', () => {
    expect(oku('tr/transfer/index.html')).not.toContain('<pre')
  })
})

describe('ana sayfa', () => {
  it('tanım paragrafıyla açılır', () => {
    const govde = oku('tr/index.html')
    expect(govde).toMatch(/Perakende analitiği/)
  })

  it('ağacın tamamını gösterir', () => {
    const html = oku('tr/index.html')
    expect(html).toContain('href="/tr/transfer/"')
    expect(html).toContain('href="/tr/temeller/"')
    expect(html).toContain('href="/tr/transfer/blok-transfer/"')
  })

  it('akış veya son yazılar bölümü içermez', () => {
    const html = oku('tr/index.html')
    expect(html).not.toMatch(/son yazılar|en yeni|güncel yazılar/i)
  })
})

describe('veri seti sayfası', () => {
  it('Dataset olarak işaretlenir', () => {
    // Rakipler veri yayınlamaz; bu işaretleme ayrıştırıcıdır
    expect(oku('tr/veri-seti/index.html')).toContain('"@type":"Dataset"')
  })

  it('yedi tabloyu da listeler', () => {
    const html = oku('tr/veri-seti/index.html')
    for (const tablo of ['magaza', 'urun', 'takvim', 'satis', 'stok', 'sevkiyat', 'kayip_satis']) {
      expect(html).toContain(tablo)
    }
  })

  it('üç formatı da duyurur', () => {
    const html = oku('tr/veri-seti/index.html')
    expect(html).toContain('CSV')
    expect(html).toContain('Parquet')
    expect(html).toContain('DuckDB')
  })
})

describe('demo', () => {
  it('demo sayfası üretilir', () => {
    expect(existsSync(DIST + 'tr/transfer/blok-transfer/demo/index.html')).toBe(true)
  })

  it('bütün kombinasyonlar HTML içinde hazır durur', () => {
    // Sunucu yok; sayfa her koşulda anında açılır
    const html = oku('tr/transfer/blok-transfer/demo/index.html')
    expect(html).toContain('data-anahtar="4|0"')
    expect(html).toContain('data-anahtar="12|2"')
  })

  it('parametre seçimi radio ile yapılır, script ile değil', () => {
    const html = oku('tr/transfer/blok-transfer/demo/index.html')
    expect(html).toContain('type="radio"')
  })

  it('senaryo dosyası bütçeyi aşmıyor', async () => {
    // Kombinasyon sayısı çarpımsal büyür; sınır dosya boyutudur
    const { statSync } = await import('node:fs')
    const yol = fileURLToPath(new URL('../src/data/senaryolar/blok-transfer.json', import.meta.url))
    expect(statSync(yol).size).toBeLessThan(500 * 1024)
  })

  it('demo JSON sözleşmeye uyar', async () => {
    const { default: veri } = await import('../src/data/senaryolar/blok-transfer.json')
    expect(Array.isArray(veri.parametreler)).toBe(true)
    const beklenenAnahtarSayisi = veri.parametreler.reduce(
      (carpim: number, p: { degerler: unknown[] }) => carpim * p.degerler.length,
      1,
    )
    expect(Object.keys(veri.sonuclar).length).toBe(beklenenAnahtarSayisi)
  })

  it('sonuç görünürlüğü saf css :has() ile üretilir, script değil', () => {
    // hidden özniteliği yerine build-zamanında üretilen bir <style> bloğu
    // seçili radyo birleşimine karşılık gelen [data-anahtar] bloğunu açar.
    const html = oku('tr/transfer/blok-transfer/demo/index.html')
    expect(html).toContain('<style')
    expect(html).toContain(':has(')
    expect(html).not.toContain('hidden')
    expect(html).not.toMatch(/<script(?![^>]*type="application\/ld\+json")/)
  })

  it(':has() desteklenmeyen tarayıcı için @supports yedeği var', () => {
    const html = oku('tr/transfer/blok-transfer/demo/index.html')
    expect(html).toContain('@supports not selector(:has(*))')
  })

  it('üretilen kural sayısı kombinasyon sayısına eşit', async () => {
    const { default: veri } = await import('../src/data/senaryolar/blok-transfer.json')
    const beklenenAnahtarSayisi = veri.parametreler.reduce(
      (carpim: number, p: { degerler: unknown[] }) => carpim * p.degerler.length,
      1,
    )
    const html = oku('tr/transfer/blok-transfer/demo/index.html')
    const stilEslesme = html.match(/<style[^>]*>([\s\S]*?)<\/style>/)
    expect(stilEslesme).not.toBeNull()
    const stilIcerigi = stilEslesme![1]
    const kuralSayisi = (stilIcerigi.match(/\[data-anahtar="[^"]+"\]\s*\{\s*display:\s*block\s*\}/g) ?? []).length
    expect(kuralSayisi).toBe(beklenenAnahtarSayisi)
  })
})
