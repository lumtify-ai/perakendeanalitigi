// site/worker/index.ts
//
// Sitenin tek sunucu kodu: JavaScript'siz ziyaret sayacı. Her sayfadaki görünmez
// <img src="/sayac.gif"> buraya gelir; sayfaların kendisi bu koda hiç uğramaz
// (wrangler.jsonc, run_worker_first). HTML'i çekip görseli çekmeyen botların
// çoğu bu yüzden sayıma girmez.
//
// Tekil sayımda çerez ve IP yok. Görsel `no-cache` olduğu için tarayıcı her
// sayfada yeniden sorar ve elindeki tarihi `If-Modified-Since` ile geri yollar.
// O tarih herkese aynı verilen "bugünün başlangıcı"dır, kişiye özel bir şey
// taşımaz; yalnız bu tarayıcının bugün daha önce gelip gelmediğini söyler.

const SAYAC_YOLU = '/sayac.gif'

// Şeffaf 1x1 GIF. Modül düzeyinde yalnız bu değişmez bayt dizisi tutulur.
const GIF = Uint8Array.from(atob('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7'), (c) =>
  c.charCodeAt(0),
)

const GUN_MS = 86_400_000
// Türkiye 2016'dan beri yaz saati uygulamıyor: sabit UTC+3.
const ISTANBUL_FARKI_MS = 3 * 3_600_000

// Analytics Engine sınırı: indeks en çok 96 bayt. Yol, URL ayrıştırıcısından
// yüzde kodlu geldiği için ASCII'dir; karakter sayısı bayt sayısına eşittir.
const INDEKS_SINIRI = 96
const TARAYICI_SINIRI = 512

/** İstanbul'da içinde bulunulan günün başlangıcı (epoch ms). */
function gunBasi(simdi: number): number {
  return Math.floor((simdi + ISTANBUL_FARKI_MS) / GUN_MS) * GUN_MS - ISTANBUL_FARKI_MS
}

/** Görseli isteyen sayfanın yolu. Bu siteden gelmiyorsa boş. */
function sayfaYolu(istek: Request): string {
  const yonlendiren = istek.headers.get('Referer')
  if (!yonlendiren) return ''
  try {
    const adres = new URL(yonlendiren)
    return adres.host === new URL(istek.url).host ? adres.pathname : ''
  } catch {
    return ''
  }
}

function yaz(istek: Request, env: Env, gununIlki: boolean, ilkKez: boolean): void {
  const sayfa = sayfaYolu(istek)
  try {
    env.SAYAC.writeDataPoint({
      blobs: [
        sayfa,
        String(istek.cf?.country ?? ''),
        String(istek.cf?.asOrganization ?? ''),
        (istek.headers.get('User-Agent') ?? '').slice(0, TARAYICI_SINIRI),
        istek.headers.get('Sec-Fetch-Dest') ?? '',
      ],
      doubles: [gununIlki ? 1 : 0, ilkKez ? 1 : 0],
      indexes: [sayfa.slice(0, INDEKS_SINIRI) || 'yok'],
    })
  } catch (hata) {
    // Sayım kaçabilir ama sayfada kırık görsel oluşmamalı.
    console.error(JSON.stringify({ olay: 'sayac_yazilamadi', hata: String(hata) }))
  }
}

export async function sayacYaniti(istek: Request, env: Env, simdi: number): Promise<Response> {
  if (new URL(istek.url).pathname !== SAYAC_YOLU) return env.ASSETS.fetch(istek)

  if (istek.method !== 'GET' && istek.method !== 'HEAD') {
    return new Response(null, { status: 405, headers: { Allow: 'GET, HEAD' } })
  }

  const bugun = gunBasi(simdi)
  const onceki = Date.parse(istek.headers.get('If-Modified-Since') ?? '')
  const ilkKez = Number.isNaN(onceki)
  const gununIlki = ilkKez || onceki < bugun

  if (istek.method === 'GET') yaz(istek, env, gununIlki, ilkKez)

  const basliklar = {
    'Cache-Control': 'private, no-cache',
    'Last-Modified': new Date(bugun).toUTCString(),
    'X-Robots-Tag': 'noindex',
    'X-Content-Type-Options': 'nosniff',
  }
  if (!gununIlki) return new Response(null, { status: 304, headers: basliklar })
  return new Response(istek.method === 'GET' ? GIF : null, {
    headers: { ...basliklar, 'Content-Type': 'image/gif' },
  })
}

export default {
  fetch(istek: Request, env: Env): Promise<Response> {
    return sayacYaniti(istek, env, Date.now())
  },
} satisfies ExportedHandler<Env>
