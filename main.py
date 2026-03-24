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
APIFY_API_KEY = os.getenv("APIFY_API_KEY")

CHANNELS = {
    "Serdar Akinan": "@serdarakinan",
    "Erdem Atay": "@erdematayveryansintv",
    "Onlar TV": "@onlartv",
    "Cüneyt Özdemir": "@cuneytozdemir",
    "Nevşin Mengü": "@NevşinMengüTV",
    "Yılmaz Özdil": "@yilmaz_ozdil",
    "Cem Gürdeniz": "@cemgurdenizz"
}

PROMPT_TEMPLATE = """
Sana YouTube'da haber içeriği üreten bir kanalın videosunun transkriptini gönderiyorum. Senden isteğim bu transkripteki bütün haberleri ve detayları atlamadan bir rapor hazırlaman ve bana sunman.
Sponsorukların, selamlamaların vs. değeri yok ama haber değeri taşıyan hiçbir bilgiyi atlamadığından emin ol. 
Rapor anlaşılır ve akılda kalıcı olmalı. Buna göre videonun formatına uygun olan rapor formatını seç. Bilgilerin sunulma sırasını takip etmek zorunda değilsin. Eğer daha uygun olacaksa olay örgüsüne takip ederek bir rapor oluştur.
Rapor başlangıç ve bitişinde herhangi bir selamlama, açıklama, soru önerisinde bulunma. Bana sadece raporu ver.

Kanal: {channel_name}
Video Başlığı: {video_title}

<TRANSKRİPT>
{transkript}
</TRANSKRİPT>
"""

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
            params={"token": APIFY_API_KEY},
            json={"videoUrl": f"https://www.youtube.com/watch?v={video_id}"},
            timeout=120
        ).json()
        if response and len(response) > 0:
            data = response[0].get("searchResult") or response[0].get("data") or []
            if data:
                transkript = " ".join([t.get("text", "") for t in data])
                return transkript
            else:
                print(f"  ⚠️ Transkript boş geldi [{video_id}]")
    except Exception as e:
        print(f"  Apify hatası: {e}")
    return None

def analyze_video(video, transkript):
    client = genai.Client(api_key=GEMINI_API_KEY)

    prompt = PROMPT_TEMPLATE.format(
        channel_name=video["name"],
        video_title=video["title"],
        transkript=transkript
    )

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
            print(f"  API hatası (deneme {attempt+1}): {e} — {wait} saniye bekleniyor...")
            time.sleep(wait)

    return f"⚠️ [{video['name']}] \"{video['title']}\" — AI yanıt vermedi."

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

        sent_count = 0

        for i, video in enumerate(videos):
            print(f"\n[{i+1}/{len(videos)}] İşleniyor: [{video['name']}] {video['title']}")

            transkript = transkript_cek(video["video_id"])
            if not transkript:
                print(f"  ⚠️ Transkript alınamadı, atlanıyor.")
                continue

            print(f"  ✓ Transkript alındı, analiz ediliyor...")
            report = analyze_video(video, transkript)

            current_date = datetime.now().strftime("%d.%m.%Y")
            header = f"📅 **{current_date}** | 📺 **[{video['name']}]** — {video['title']}\nhttps://www.youtube.com/watch?v={video['video_id']}\n\n"
            send_to_discord(header + report)
            sent_count += 1
            print(f"  ✅ Discord'a gönderildi.")
            time.sleep(2)

        if sent_count == 0:
            print("Hiçbir video işlenemedi.")
        else:
            print(f"\nİşlem tamamlandı. {sent_count} rapor Discord'a gönderildi!")
