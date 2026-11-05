// site/tests/sayacOzeti.test.ts
import { describe, expect, it } from 'vitest'
import { elemeNedeni, ozetle, sorgu, type Satir } from '../scripts/sayacOzeti'

const INSAN = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/154.0.0.0 Safari/537.36'

function satir(degisen: Partial<Satir> = {}): Satir {
  return {
    gun: 20762, // 5 Kasım 2026, 1970 başından gün sayısı
    sayfa: '/sozluk/',
    ulke: 'TR',
    ag: 'Turk Telekom',
    tarayici: INSAN,
    istekTuru: 'image',
    goruntuleme: 1,
    tekil: 1,
    yeni: 1,
    ...degisen,
  }
}

describe('elemeNedeni', () => {
  it('sıradan bir tarayıcıyı elemez', () => {
    expect(elemeNedeni(satir())).toBeNull()
  })

  it('sitedeki bir sayfadan gelmeyen isteği eler', () => {
    expect(elemeNedeni(satir({ sayfa: '' }))).toBe('sayfasız')
  })

  it('görsel olarak istenmeyeni eler, başlığı hiç göndermeyen eski tarayıcıyı elemez', () => {
    expect(elemeNedeni(satir({ istekTuru: 'document' }))).toBe('görsel değil')
    expect(elemeNedeni(satir({ istekTuru: '' }))).toBeNull()
  })

  it.each([
    'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)',
    'Mozilla/5.0 (compatible; Baiduspider-render/2.0)',
    'Mozilla/5.0 Chrome/153.0.0.0 Safari/537.36 (compatible; Google-InspectionTool/1.0)',
    'Mozilla/5.0 (X11; Linux x86_64) HeadlessChrome/120.0.0.0',
    'Mozilla/5.0 Chrome/143.0.0.0 Safari/537.36 iubenda-radar/3.37.0',
    'curl/8.4.0',
    '',
  ])('kendini bot diye tanıtanı ya da tanıtmayanı eler: %s', (tarayici) => {
    expect(elemeNedeni(satir({ tarayici }))).toBe('bot')
  })

  it('güncelliğini yitirmiş Chrome tanıtımını eler', () => {
    const eski = 'Mozilla/5.0 (Linux; Android 10; HUAWEI P30 Pro) Chrome/89.0.4389.105 Mobile Safari/537.36'
    expect(elemeNedeni(satir({ tarayici: eski }))).toBe('eski Chrome')
  })

  it.each(['DIGITALOCEAN-ASN', 'Amazon.com, Inc.', 'Hangzhou Alibaba Advertising Co.,Ltd.', 'OVH SAS'])(
    'veri merkezi ağını eler: %s',
    (ag) => {
      expect(elemeNedeni(satir({ ag }))).toBe('veri merkezi')
    },
  )

  it.each(['Akamai International B.V.', 'Cloudflare, Inc.', 'Fastly, Inc.'])(
    'iCloud Özel Geçiş çıkışını veri merkezi saymaz: %s',
    (ag) => {
      expect(elemeNedeni(satir({ ag }))).toBeNull()
    },
  )
})

describe('ozetle', () => {
  it('kalanları günlere toplar, elenenleri nedeniyle ayrı sayar', () => {
    const ozet = ozetle([
      satir({ goruntuleme: 5, tekil: 2, yeni: 1 }),
      satir({ gun: 20761, goruntuleme: 3, tekil: 3, yeni: 3 }),
      satir({ ag: 'OVH SAS', goruntuleme: 7, tekil: 7, yeni: 7 }),
      satir({ sayfa: '', goruntuleme: 2, tekil: 2, yeni: 2 }),
    ])
    expect(ozet.gunler).toEqual([
      { gun: '2026-11-04', goruntuleme: 3, tekil: 3, yeni: 3 },
      { gun: '2026-11-05', goruntuleme: 5, tekil: 2, yeni: 1 },
    ])
    expect(ozet.toplam).toEqual({ goruntuleme: 8, tekil: 5, yeni: 4 })
    expect(ozet.elenen).toEqual({ 'veri merkezi': 7, sayfasız: 2 })
  })

  it('sayfaları ve ülkeleri görüntülemeye göre sıralar', () => {
    const ozet = ozetle([
      satir({ sayfa: '/a/', ulke: 'TR', goruntuleme: 1 }),
      satir({ sayfa: '/b/', ulke: 'DE', goruntuleme: 4 }),
      satir({ sayfa: '/b/', ulke: 'TR', goruntuleme: 2 }),
    ])
    expect(ozet.sayfalar).toEqual([
      ['/b/', 6],
      ['/a/', 1],
    ])
    expect(ozet.ulkeler).toEqual([
      ['DE', 4],
      ['TR', 3],
    ])
  })

  it('hiç veri yoksa boş özet döner', () => {
    const ozet = ozetle([])
    expect(ozet.gunler).toEqual([])
    expect(ozet.toplam).toEqual({ goruntuleme: 0, tekil: 0, yeni: 0 })
  })
})

describe('sorgu', () => {
  it('örneklemeyi hesaba katar ve günü İstanbul saatine göre keser', () => {
    const sql = sorgu(30)
    expect(sql).toContain('SUM(_sample_interval)')
    expect(sql).toContain('SUM(_sample_interval * double1)')
    expect(sql).toContain('toUInt32(timestamp) + 10800')
    expect(sql).toContain("INTERVAL '30' DAY")
    expect(sql).toContain('FROM perakende_sayac')
    expect(sql).toContain('FORMAT JSON')
  })

  it('geçersiz gün sayısını reddeder', () => {
    expect(() => sorgu(0)).toThrow()
    expect(() => sorgu(1.5)).toThrow()
    expect(() => sorgu(200)).toThrow()
  })
})
