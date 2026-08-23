// site/src/lib/zorunlu.ts
//
// `getEntry(...)!` dört sayfa şablonunda geçiyordu. `!` yalnızca TypeScript'i
// susturur; çalışma anında `undefined.data` okunur ve build derlenmiş bir
// chunk dosyasını (dist/.prerender/chunks/index_*.mjs:54 gibi) gösteren native
// bir abort ile çöker. İçerik ağacı doğrulaması (src/lib/agacSekli.ts) bu
// durumun kök nedenini zaten kapatıyor; bu yardımcı ikinci savunma hattıdır
// ve dört şablonun aynı mesajı vermesini garanti eder.

/**
 * Bir koleksiyon girdisinin var olduğunu zorunlu kılar.
 *
 * @param girdi     getEntry sonucu
 * @param koleksiyon Koleksiyon adı (`alan`, `dizi`, …)
 * @param id        Aranan girdinin id'si
 */
export function zorunlu<T>(girdi: T | undefined | null, koleksiyon: string, id: string): T {
  if (girdi === undefined || girdi === null) {
    throw new Error(
      `"${koleksiyon}" koleksiyonunda "${id}" girdisi yok. ` +
        `src/content/${koleksiyon}/${id}.md dosyasını ekleyin. ` +
        'Bu hata normalde build öncesi doğrulamada (npm run dogrula) yakalanır; ' +
        'buraya kadar geldiyse doğrulama atlanmış demektir.',
    )
  }
  return girdi
}
