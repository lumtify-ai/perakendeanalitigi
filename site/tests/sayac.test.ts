// site/tests/sayac.test.ts
import { describe, expect, it } from 'vitest'
import { sayacYaniti } from '../worker/index'

// 5 Kasım 2026, İstanbul'da 15.00. İstanbul günü UTC'de 21.00'de başlar.
const SIMDI = Date.UTC(2026, 10, 5, 12)
const BUGUN = new Date(Date.UTC(2026, 10, 4, 21)).toUTCString()
const DUN = new Date(Date.UTC(2026, 10, 3, 21)).toUTCString()

const SAYFA = 'https://perakendeanalitigi.com/sozluk/'

function istek(
  basliklar: Record<string, string> = { Referer: SAYFA },
  yontem = 'GET',
  yol = '/sayac.gif',
) {
  const r = new Request('https://perakendeanalitigi.com' + yol, {
    method: yontem,
    headers: basliklar,
  })
  return Object.assign(r, { cf: { country: 'TR', asOrganization: 'Turk Telekom' } })
}

/** Yazılan veri noktalarını biriktiren gerçek bir bağlama eşdeğeri. */
function ortam() {
  const yazilanlar: { blobs: string[]; doubles: number[]; indexes: string[] }[] = []
  return {
    yazilanlar,
    env: {
      SAYAC: { writeDataPoint: (n: (typeof yazilanlar)[number]) => void yazilanlar.push(n) },
      ASSETS: { fetch: async () => new Response('varlik') },
    },
  }
}

const calistir = (r: Request, env: unknown, simdi = SIMDI) =>
  sayacYaniti(r as never, env as never, simdi)

describe('sayaç görseli', () => {
  it('tarayıcının ilk isteğine 1x1 GIF döner', async () => {
    const { env } = ortam()
    const yanit = await calistir(istek(), env)
    expect(yanit.status).toBe(200)
    expect(yanit.headers.get('Content-Type')).toBe('image/gif')
    const govde = new Uint8Array(await yanit.arrayBuffer())
    expect(new TextDecoder().decode(govde.slice(0, 6))).toBe('GIF89a')
  })

  it('tarayıcı her sayfada yeniden sorsun diye önbelleği doğrulamaya bağlar', async () => {
    const { env } = ortam()
    const yanit = await calistir(istek(), env)
    expect(yanit.headers.get('Cache-Control')).toBe('private, no-cache')
    expect(yanit.headers.get('Last-Modified')).toBe(BUGUN)
  })

  it('dizinlenmez ve tür tahminine kapalıdır', async () => {
    const { env } = ortam()
    const yanit = await calistir(istek(), env)
    expect(yanit.headers.get('X-Robots-Tag')).toBe('noindex')
    expect(yanit.headers.get('X-Content-Type-Options')).toBe('nosniff')
  })
})

describe('tekil sayım (çerezsiz)', () => {
  it('hiç gelmemiş tarayıcı hem günün ilki hem ilk kez sayılır', async () => {
    const { env, yazilanlar } = ortam()
    await calistir(istek(), env)
    expect(yazilanlar[0].doubles).toEqual([1, 1])
  })

  it('aynı gün dönen tarayıcıya 304 verir ve yalnız görüntüleme yazar', async () => {
    const { env, yazilanlar } = ortam()
    const yanit = await calistir(istek({ Referer: SAYFA, 'If-Modified-Since': BUGUN }), env)
    expect(yanit.status).toBe(304)
    expect(await yanit.arrayBuffer()).toHaveProperty('byteLength', 0)
    expect(yanit.headers.get('Last-Modified')).toBe(BUGUN)
    expect(yazilanlar[0].doubles).toEqual([0, 0])
  })

  it('önceki günden dönen tarayıcı günün ilki sayılır ama ilk kez sayılmaz', async () => {
    const { env, yazilanlar } = ortam()
    const yanit = await calistir(istek({ Referer: SAYFA, 'If-Modified-Since': DUN }), env)
    expect(yanit.status).toBe(200)
    expect(yanit.headers.get('Last-Modified')).toBe(BUGUN)
    expect(yazilanlar[0].doubles).toEqual([1, 0])
  })

  it('gün sınırı İstanbul saatine göredir', async () => {
    // UTC'de hâlâ 5 Kasım 21.30, İstanbul'da 6 Kasım 00.30: yeni gün.
    const { env, yazilanlar } = ortam()
    const yanit = await calistir(
      istek({ Referer: SAYFA, 'If-Modified-Since': BUGUN }),
      env,
      Date.UTC(2026, 10, 5, 21, 30),
    )
    expect(yanit.status).toBe(200)
    expect(yazilanlar[0].doubles).toEqual([1, 0])
  })

  it('okunamayan tarih başlığını hiç gelmemiş sayar', async () => {
    const { env, yazilanlar } = ortam()
    await calistir(istek({ Referer: SAYFA, 'If-Modified-Since': 'dün gibi' }), env)
    expect(yazilanlar[0].doubles).toEqual([1, 1])
  })
})

describe('yazılan veri noktası', () => {
  it('sayfa, ülke, ağ, tarayıcı ve istek türünü sabit sırayla yazar', async () => {
    const { env, yazilanlar } = ortam()
    await calistir(
      istek({ Referer: SAYFA, 'User-Agent': 'Mozilla/5.0 Deneme', 'Sec-Fetch-Dest': 'image' }),
      env,
    )
    expect(yazilanlar[0].blobs).toEqual([
      '/sozluk/',
      'TR',
      'Turk Telekom',
      'Mozilla/5.0 Deneme',
      'image',
    ])
    expect(yazilanlar[0].indexes).toEqual(['/sozluk/'])
  })

  it('IP adresini hiçbir alana yazmaz', async () => {
    const { env, yazilanlar } = ortam()
    await calistir(
      istek({ Referer: SAYFA, 'CF-Connecting-IP': '203.0.113.7', 'X-Real-IP': '203.0.113.7' }),
      env,
    )
    expect(JSON.stringify(yazilanlar[0])).not.toContain('203.0.113.7')
  })

  it('sayfa adresinin sorgu kısmını atar', async () => {
    const { env, yazilanlar } = ortam()
    await calistir(istek({ Referer: SAYFA + '?utm_source=mail&ad=ali' }), env)
    expect(yazilanlar[0].blobs[0]).toBe('/sozluk/')
  })

  it('başka siteden ya da yönlendirensiz gelen isteği sayfasız yazar', async () => {
    const { env, yazilanlar } = ortam()
    await calistir(istek({ Referer: 'https://baska.example/sozluk/' }), env)
    await calistir(istek({}), env)
    expect(yazilanlar.map((n) => n.blobs[0])).toEqual(['', ''])
    // Analytics Engine boş indeksi örnekleme anahtarı olarak kullanamaz.
    expect(yazilanlar.map((n) => n.indexes[0])).toEqual(['yok', 'yok'])
  })

  it('uzun değerleri sınırlar: indeks 96 bayt, tarayıcı 512 karakter', async () => {
    const { env, yazilanlar } = ortam()
    await calistir(
      istek({
        Referer: `https://perakendeanalitigi.com/${'a'.repeat(300)}/`,
        'User-Agent': 'b'.repeat(2000),
      }),
      env,
    )
    expect(yazilanlar[0].indexes[0]).toHaveLength(96)
    expect(yazilanlar[0].blobs[3]).toHaveLength(512)
  })

  it('yazma hata verse de görsel döner', async () => {
    const yanit = await calistir(istek(), {
      SAYAC: {
        writeDataPoint: () => {
          throw new Error('yazılamadı')
        },
      },
    })
    expect(yanit.status).toBe(200)
  })
})

describe('yönlendirme', () => {
  it('sayaç dışındaki yolu varlıklara bırakır, sayım yapmaz', async () => {
    const { env, yazilanlar } = ortam()
    const yanit = await calistir(istek({}, 'GET', '/sozluk/'), env)
    expect(await yanit.text()).toBe('varlik')
    expect(yazilanlar).toEqual([])
  })

  it('HEAD isteği yanıtlanır ama sayılmaz', async () => {
    const { env, yazilanlar } = ortam()
    const yanit = await calistir(istek({}, 'HEAD'), env)
    expect(yanit.status).toBe(200)
    expect(yazilanlar).toEqual([])
  })

  it('başka yöntemleri reddeder', async () => {
    const { env, yazilanlar } = ortam()
    const yanit = await calistir(istek({}, 'POST'), env)
    expect(yanit.status).toBe(405)
    expect(yazilanlar).toEqual([])
  })
})
