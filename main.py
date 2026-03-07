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

CHANNELS = {
    "Serdar Akinan": "@serdarakinan",
    "Yılmaz Özdil": "@yilmaz_ozdil",
    "Cem Gürdeniz": "@cemgurdenizz",
    "Erdem Atay": "@erdematayveryansintv",
    "Onlar TV": "@onlartv"
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
    for attempt in range(3):
        try:
            res = requests.get(
                f"https://api.supadata.ai/v1/youtube/transcript?videoId={video_id}",
                headers={"x-api-key": SUPADATA_API_KEY},
                timeout=30
            ).json()
            if "content" in res:
                return " ".join([t["text"] for t in res["content"]])
            if res.get("error") == "limit-exceeded":
                print(f"Rate limit, 10 saniye bekleniyor... (Deneme {attempt+1})")
                time.sleep(10)
        except Exception as e:
            print(f"Deneme {attempt+1} başarısız: {type(e).__name__}")
            time.sleep(3)
    return None

def analyze_single_video(video):
    """Tek bir videoyu analiz et ve rapor döndür."""
    client = genai.Client(api_key=GEMINI_API_KEY)

    transkript = transkript_cek(video["video_id"])
    print(f"\n===== TRANSKRİPT: [{video['name']}] {video['title']} =====\n{transkript}\n=============================================\n")
    if not transkript:
        return f"⚠️ [{video['name']}] \"{video['title']}\" — transkript alınamadı."

    prompt = f"""
Aşağıdaki transkripti incele ve eksiksiz bir haber raporu oluştur.

Kanal: {video['name']}
Video Başlığı: {video['title']}

<TRANSKRİPT>
{transkript}
</TRANSKRİPT>

KATİ KURALLAR:
1. Her farklı konu ve alt konu ayrı bir başlık olsun. Birleştirme yapma. Bu kanalda 10 farklı konu ele alındıysa 10 ayrı başlık yaz.
2. Her başlığı transkriptten eksiksiz doldur. Tüm detayları, rakamları, özel isimleri ve analizleri yaz. Kısa geçme.
3. Her haberi tarafsız ve nesnel özetle, kendi yorumunu ekleme.
4. Yayıncı yorumlarını yumuşatmadan olduğu gibi aktar.
5. Selamlama veya kapanış cümlesi ekleme, doğrudan rapora başla.
6. Yayıncı kanala konuk aldıysa "Kanal Adı (Konuk: Kişi Adı)" formatını kullan.

Her başlık için şu yapıyı kullan:

🔹 **HABERİN BAŞLIĞI**
**Haber:** (Tarafsız özet. Kim, ne yaptı, nerede, ne zaman, sonucu ne? Tüm önemli isimler, rakamlar ve detaylar dahil.)
**Yayıncı Yorumları:**
* **[Yayıncı Adı]:** (Yaklaşımı, vurguladığı noktalar, kullandığı özel ifadeler)
"""

    response = client.models.generate_content(
        model='gemini-3-flash-preview',
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=(
                "Sen tarafsız, nesnel ve profesyonel bir Türkçe haber derleyici ve analistsin. "
                "Temel görevin verilen transkriptteki tüm haber konularını ve alt konuları eksiksiz tespit etmek, "
                "hiçbir detayı, ismi, rakamı veya analizi atlamadan raporlamaktır. "
                "Yayıncıların yorumlarını yumuşatmadan olduğu gibi aktar. "
                "Konuk isimlerini 'Kanal Adı (Konuk: Kişi Adı)' formatında belirt."
            ),
            temperature=0.3,
            top_p=0.9,
            max_output_tokens=16000,
            thinking_config=types.ThinkingConfig(
                thinking_level=types.ThinkingLevel.HIGH
            )
        )
    )

    if not response.text:
    return f"⚠️ [{video['name']}] \"{video['title']}\" — AI yanıt vermedi."

    return response.text.strip()

def combine_reports(individual_reports, videos):
    """Tüm bireysel raporları tek bir final rapora birleştir."""
    client = genai.Client(api_key=GEMINI_API_KEY)
    current_date = datetime.now().strftime("%d.%m.%Y")

    sources = "\n".join([f"- [{v['name']}] {v['title']}" for v in videos])
    combined = "\n\n---\n\n".join(individual_reports)

    prompt = f"""
Aşağıda farklı YouTube kanallarından hazırlanmış bireysel haber raporları var.
Bu raporları tek bir tutarlı final rapora birleştir.

KATİ KURALLAR:
1. Aynı konuyu ele alan başlıkları tek başlık altında birleştir. Birden fazla kanal aynı konuyu işlediyse hepsinin yorumunu o başlık altında göster.
2. Hiçbir bilgiyi, ismi, rakamı veya analizi çıkarma.
3. Başlıkları önem sırasına göre düzenle: önce dış politika ve savaş haberleri, sonra iç politika, en sona magazin ve diğerleri.
4. Selamlama veya kapanış cümlesi ekleme.

Raporun başına şunu ekle:

📅 **Tarih: {current_date}**

**İncelenen Kaynaklar:**
{sources}

---

<RAPORLAR>
{combined}
</RAPORLAR>
"""

    response = client.models.generate_content(
        model='gemini-3-flash-preview',
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=(
                "Sen tarafsız, nesnel ve profesyonel bir Türkçe haber derleyici ve analistsin. "
                "Görevin birden fazla kaynaktan gelen raporları eksiksiz biçimde tek bir raporda birleştirmektir. "
                "Hiçbir bilgiyi silme veya özetleme. Sadece düzenle ve birleştir."
            ),
            temperature=0.2,
            top_p=0.9,
            max_output_tokens=64000,
            thinking_config=types.ThinkingConfig(
                thinking_level=types.ThinkingLevel.HIGH
            )
        )
    )

    return response.text.strip()

def get_ai_report(videos):
    """Ana fonksiyon: Her videoyu ayrı ayrı analiz et, sonra birleştir."""
    individual_reports = []

    for i, video in enumerate(videos):
        print(f"[{i+1}/{len(videos)}] Analiz ediliyor: [{video['name']}] {video['title']}")
        report = analyze_single_video(video)
        individual_reports.append(report)
        print(f"  ✓ Tamamlandı.")
        time.sleep(2)  # Rate limit için kısa bekleme

    print("Birleştirme aşaması başlatılıyor...")
    final_report = combine_reports(individual_reports, videos)
    print("Final rapor hazır.")
    return final_report

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

        final_report = get_ai_report(videos)
        send_to_discord(final_report)
        print("İşlem tamamlandı, rapor Discord'a uçtu!")
