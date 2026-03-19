import os
import time
import requests
import isodate
from datetime import datetime, timedelta
from google import genai
from google.genai import types

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DISCORD_URL = os.getenv("DISCORD_WEBHOOK_URL")
SUPADATA_API_KEY = os.getenv("SUPADATA_API_KEY")
APIFY_API_KEY = os.getenv("APIFY_API_KEY")

CHANNELS = {
    "Serdar Akinan": "@serdarakinan",
    "Erdem Atay": "@erdematayveryansintv",
    "Onlar TV": "@onlartv",
    "Cüneyt Özdemir": "@cuneytozdemir",
    "Nevşin Mengü": "@NevşinMengüTV"
}

def is_short(video_id):
    res = requests.get(
        f"https://www.googleapis.com/youtube/v3/videos?part=contentDetails&id={video_id}&key={YOUTUBE_API_KEY}"
    ).json()
    try:
        duration = res["items"][0]["contentDetails"]["duration"]
        seconds = isodate.parse_duration(duration).total_seconds()
        return seconds <= 180
    except Exception:
        return False

def get_latest_video_list():
    found_videos = []
    yesterday_dt = datetime.utcnow() - timedelta(days=1)
    for name, handle in CHANNELS.items():
        try:
            c_res = requests.get(
                f"https://www.googleapis.com/youtube/v3/channels?part=contentDetails&forHandle={handle}&key={YOUTUBE_API_KEY}"
            ).json()
            uploads_id = c_res["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
            res = requests.get(
                f"https://www.googleapis.com/youtube/v3/playlistItems?part=snippet&playlistId={uploads_id}&maxResults=5&key={YOUTUBE_API_KEY}"
            ).json()
            for item in res.get("items", []):
                pub_date = datetime.strptime(item["snippet"]["publishedAt"], "%Y-%m-%dT%H:%M:%SZ")
                if pub_date > yesterday_dt:
                    video_id = item["snippet"]["resourceId"]["videoId"]
                    if not is_short(video_id):
                        found_videos.append({
                            "name": name,
                            "title": item["snippet"]["title"],
                            "video_id": video_id
                        })
        except Exception as e:
            print(f"HATA: {name}: {e}")
    return found_videos

def transkript_cek(video_id):
    try:
        response = requests.post(
            "https://api.apify.com/v2/acts/pintostudio~youtube-transcript-scraper/run-sync-get-dataset-items",
            params={"token": os.getenv("APIFY_API_KEY")},
            json={
                "videoUrl": f"https://www.youtube.com/watch?v={video_id}"
            },
            timeout=120
        ).json()
        print(f"  Ham Apify yanıtı: {str(response)[:500]}")
        if response and len(response) > 0:
            data = response[0].get("searchResult") or response[0].get("data") or []
            print(f"  Bulunan field: {list(response[0].keys())}")
            if data:
                transkript = " ".join([t.get("text", "") for t in data])
                print(f"  Transkript uzunluğu: {len(transkript)} karakter")
                return transkript
            else:
                print(f"  Transkript boş geldi")
    except Exception as e:
        print(f"Apify hatası: {e}")
    return None
    
def is_news_format(video):
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    transkript = transkript_cek(video["video_id"])
    if not transkript:
        return False, None
    
    prompt = f"""
GÖREV: Sen profesyonel bir içerik sınıflandırma uzmanısın. 
YouTube'da haber sunan haber kanalları var ve bu haber kanallarının farklı formatta haber sunma tarzları var. Bazıları bir haber bülteni gibi günlük haberleri kısa sunup ardından kendi özet yorumlarını yapıyorlar.
Bazıları ise video içerisinde sadece belirli bir konu üzerine derin analiz, etraflıca yorum yapıyorlar. Farklı konular bahsediyor olasalar da amaçları anlattıkları konuyu desteklemek. 
Görevin, aşağıda transkripti verilen haber videosunun yayın formatını analiz etmek ve belirlediğim iki kategoriden hangisine ait olduğunu tespit etmektir.
BAĞLAM VE KATEGORİLER:
Senin aradığın format "Kısa Haber ve Yorum" formatıdır (Haber bülteni mantığı).
1. UYGUN FORMAT (Kısa Haber ve Yorum): Yayıncı, video boyunca birbirinden bağımsız birden fazla farklı haber başlığına değinir (Örn: Önce yerel ekonomiden bahseder, biter; sonra Avrupa'daki bir seçime geçer, biter; sonra bir magazin/asayiş olayına geçer).
2. UYGUN OLMAYAN FORMAT (Tek Konu / Derinlemesine Analiz): Videonun tamamı veya çok büyük bir kısmı tek bir ana olay üzerine kuruludur.
KATI KURALLAR VE YANILSAMA FİLTRELERİ (BUNLARA KESİNLİKLE DİKKAT ET):
1. ŞEMSİYE KONU KURALI: Eğer yayıncı farklı ülkelerden, farklı isimlerden veya farklı alt olaylardan bahsediyorsa AMA bunların hepsi tek bir büyük olaya bağlanıyorsa, bu "TEK KONUNUN alt başlıklarıdır". Bu tür videolar UYGUN DEĞİLDİR.
2. SOHBET VE SPONSOR KURALI: Sponsorlu reklamlar, özel gün kutlamaları, selamlama ritüelleri veya izleyiciyle yapılan kısa sohbetler KESİNLİKLE ayrı bir haber konusu sayılamaz.
3. AĞIRLIK KURALI: Videonun %80'i tek bir konuya ayrılmışsa, aralarda 1-2 dakikalık başka ufak haberlere değinilmiş olması o videoyu bülten yapmaz. Bu videolar da UYGUN DEĞİLDİR.
4. Asla selamlama veya kapanış metni yazma. Sadece aşağıdaki formatta yanıt ver.

ÇIKTI FORMATI:
Satır 1 (sadece bu iki kelimeden biri): UYGUN veya UYGUN_DEGIL
Satır 2: gerekçen

Örnek:
UYGUN
Video birden fazla bağımsız haber konusunu ele almaktadır.

<TRANSKRİPT>
{transkript}
</TRANSKRİPT>
"""
    try:
        response = client.models.generate_content(
            model='gemini-3-flash-preview',
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=200,
                thinking_config=types.ThinkingConfig(
                    thinking_level=types.ThinkingLevel.HIGH
                )
            )
        )
        raw = response.text.strip()
        print(f"  Ham yanıt [{video['name']}]: {raw}")
        satirlar = raw.split("\n")
        karar = satirlar[0].strip().upper() == "UYGUN"
        gerekce = satirlar[1].strip() if len(satirlar) > 1 else ""
        print(f"  Format kontrolü [{video['name']}]: {'✓' if karar else '✗'} — {gerekce}")
        return karar, transkript
    except Exception as e:
        print(f"  Format kontrolü hatası: {e}")
        return True, transkript
        
def analyze_single_video(video, transkript=None):
    """Tek bir videoyu analiz et ve rapor döndür."""
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    if transkript is None:
        transkript = transkript_cek(video["video_id"])
    
    print(f"\n===== TRANSKRİPT: [{video['name']}] {video['title']} =====\n{transkript}\n=============================================\n")
    
    if not transkript:
        return f"⚠️ [{video['name']}] \"{video['title']}\" — transkript alınamadı."

    prompt = f"""
GÖREV: Sen profesyonel bir içerik analiz uzmanısın. Aşağıdaki transkripti, içerisindeki istisnasız her bir farklı konuyu/başlığı kapsayacak şekilde özetleyeceksin.

KESİN TALİMATLAR:
SIFIR KAYIP POLİTİKASI: Metinde geçen ana haberler, ara başlıklar veya kısa bilgi notlarının HİÇBİRİNİ atlama. "Özet" demek, sadece önemli olanları seçmek değil; her bir konunun özünü aktarmaktır.
KONU BAZLI GRUPLAMA: Videodaki konular dağınık işlenmiş veya aynı konuya defalarca geri dönülmüş olabilir. Aynı konuya ait tüm detayları ve yorumları tek bir başlık altında birleştir.
TARAFIZLIK: Metne hiçbir yorum, duygu veya dış bilgi ekleme. Yayıncı yorumlarını yumuşatmadan olduğu gibi aktar.
BÜTÜNLÜK KONTROLÜ: Metnin son saniyesine kadar tarama yapmayı sürdür.
GEVEZELİK: Selamlama veya kapanış cümlesi ekleme, doğrudan rapora başla.

Her başlık için şu yapıyı kullan:

🔹 **HABERİN BAŞLIĞI**
**Haber:** (Tarafsız özet. Kim, ne yaptı, nerede, ne zaman, sonucu ne? Tüm önemli isimler, rakamlar ve detaylar dahil.)
**Yayıncı Yorumları:**
* **[Yayıncı Adı]:** (Yaklaşımı, vurguladığı noktalar, kullandığı özel ifadeler)

Kanal: {video['name']}
Video Başlığı: {video['title']}

<TRANSKRİPT>
{transkript}
</TRANSKRİPT>

"""

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model='gemini-3-flash-preview',
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.3,
                    top_p=0.9,
                    max_output_tokens=16000,
                    thinking_config=types.ThinkingConfig(
                        thinking_level=types.ThinkingLevel.HIGH
                    )
                )
            )
            if response.text:
                return response.text.strip()
        except Exception as e:
            wait = (attempt + 1) * 30
            print(f"API hatası (deneme {attempt+1}): {e} — {wait} saniye bekleniyor...")
            time.sleep(wait)
    return f"⚠️ [{video['name']}] \"{video['title']}\" — AI yanıt vermedi."
    
def combine_reports(individual_reports, videos):
    """Tüm bireysel raporları tek bir final rapora birleştir."""
    client = genai.Client(api_key=GEMINI_API_KEY)
    current_date = datetime.now().strftime("%d.%m.%Y")
    sources = "\n".join([f"- [{v['name']}] {v['title']}" for v in videos])
    combined = "\n\n---\n\n".join(individual_reports)

    prompt = f"""
Sen tarafsız, nesnel ve profesyonel bir haber derleyici ve analistsin.
Aşağıda birden fazla YouTube haber kanalından toplanıp birleştirilmiş bir rapor var. Fakat birden fazla kaynaktan alındığı için bazı haberlerin tekrar ettiğini göreceksin.
Senin görevin tekrar eden haberleri ve altındaki yorumları birleştirmek.

KATI KURALLAR:
1. Sadece birbirinin aynısı olan haberleri birleştir. Birbiriyle ilgili ya da yakın olan haberleri ayrı bırak.
2. Hiçbir bilgiyi, ismi, rakamı veya analizi çıkarma.
3. Birbirinin aynısı olan haberleri birleştirirken yayıncıların verdiği detayları silme, birleştir.
3. Başlıkları önem sırasına göre düzenle: önce dış politika, sonra iç politika, en sona magazin ve diğerleri.
4. Selamlama veya kapanış cümlesi ekleme.
5. Rapor formatı Discord'da paylaşılmaya uygun olmalı

Raporun başına şunu ekle:

📅 **Tarih: {current_date}**

**İncelenen Kaynaklar:**
{sources}

---

<RAPORLAR>
{combined}
</RAPORLAR>
"""

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model='gemini-3-flash-preview',
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    top_p=0.9,
                    max_output_tokens=64000,
                    thinking_config=types.ThinkingConfig(
                        thinking_level=types.ThinkingLevel.HIGH
                    )
                )
            )
       
            if response.text:
                return response.text.strip()
            else:
                print(f"Birleştirme deneme {attempt+1}: response.text boş geldi.")
        except Exception as e:
            wait = (attempt + 1) * 30
            print(f"Birleştirme API hatası (deneme {attempt+1}): {e} — {wait} saniye bekleniyor...")
            time.sleep(wait)
    return "⚠️ Final rapor oluşturulamadı — AI yanıt vermedi."

def send_to_discord(report):
    while report:
        if len(report) <= 1900:
            chunk = report
            report = ""
        else:
            split_at = report.rfind("\n", 0, 1900)
            if split_at == -1:
                split_at = report.rfind(" ", 0, 1900)
            if split_at == -1:
                split_at = 1900
            chunk = report[:split_at]
            report = report[split_at:].lstrip()
        requests.post(DISCORD_URL, json={"content": chunk})
        time.sleep(0.5)

if __name__ == "__main__":
    videos = get_latest_video_list()
    if not videos:
        print("Son 24 saatte yeni video bulunamadı.")
    else:
        print(f"Bulunan videolar ({len(videos)} adet):")
        for v in videos:
            print(f"  - [{v['name']}] {v['title']}")

        individual_reports = []
        included_videos = []

        for i, video in enumerate(videos):
            print(f"[{i+1}/{len(videos)}] Kontrol ediliyor: [{video['name']}] {video['title']}")
            
            is_news, transkript = is_news_format(video)
            
            if not is_news:
                print(f"  ⏭️ Atlandı (derinlemesine analiz formatı)")
                continue
            
            print(f"  ✓ Haber formatı, analiz ediliyor...")
            report = analyze_single_video(video, transkript)
            individual_reports.append(report)
            included_videos.append(video)
            time.sleep(2)

        if not individual_reports:
            print("Bugün haber formatında video bulunamadı.")
        else:
            print("Birleştirme aşaması başlatılıyor...")
            final_report = combine_reports(individual_reports, included_videos)
            send_to_discord(final_report)
            print("İşlem tamamlandı, rapor Discord'a uçtu!")
