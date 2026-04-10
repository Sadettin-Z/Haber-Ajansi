import os
import time
import requests
import isodate
from datetime import datetime, timedelta, timezone
from google import genai
from google.genai import types

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
DISCORD_URL = os.getenv("DISCORD_WEBHOOK_URL")
APIFY_API_KEY = os.getenv("APIFY_API_KEY")
GEMINI_API_KEYS = [
    os.getenv("GEMINI_API_KEY_1"),
    os.getenv("GEMINI_API_KEY_2"),
    os.getenv("GEMINI_API_KEY_3"),
]

CHANNELS = {
    "Serdar Akinan": "@serdarakinan",
    "Erdem Atay": "@erdematayveryansintv",
    "Veryansın Tv": "@VeryansinTv",
    "Onlar TV": "@onlartv",
    "Yılmaz Özdil": "@yilmaz_ozdil",
    "Cem Gürdeniz": "@cemgurdenizz",
    "Caspian Report": "@CaspianReport",
    "Cüneyt Özdemir": "@cuneytozdemir",
}

PROMPT_TEMPLATE = """
Sana YouTube'da haber içeriği üreten bir kanalın videosunun transkriptini gönderiyorum. Senden isteğim bu transkripteki bütün haberleri ve detayları atlamadan bir rapor hazırlaman ve bana sunman.
Sponsorukların, selamlamaların vs. değeri yok ama haber değeri taşıyan hiçbir bilgiyi atlamadığından emin ol. 
Rapor anlaşılır ve akılda kalıcı olmalı. Buna göre videonun formatına uygun olan rapor formatını seç. Bilgilerin sunulma sırasını takip etmek zorunda değilsin. Eğer daha uygun olacaksa olay örgüsüne takip ederek bir rapor oluştur.
Videolarda konuklar tarafından yapılan yorumları konuklara atfet ki rapordaki yorumların kimin yorumu olduğu anlaşılsın.
Rapor başlangıç ve bitişinde herhangi bir selamlama, açıklama, soru önerisinde bulunma. Sadece raporu ver.

Kanal: {channel_name}
Video Başlığı: {video_title}

<TRANSKRİPT>
{transkript}
</TRANSKRİPT>
"""

def is_short(video_id):
    # Videos under 3 minutes are filtered out (YouTube Shorts etc.)
    res = requests.get(
        f"https://www.googleapis.com/youtube/v3/videos?part=contentDetails&id={video_id}&key={YOUTUBE_API_KEY}"
    ).json()
    try:
        duration = res["items"][0]["contentDetails"]["duration"]
        seconds = isodate.parse_duration(duration).total_seconds()
        return seconds <= 180, f"{int(seconds // 60)} dk"
    except Exception:
        return False, "? dk"

def get_latest_video_list():
    found_videos = []
    yesterday_dt = datetime.now(timezone.utc) - timedelta(days=1)
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
                pub_date = datetime.strptime(item["snippet"]["publishedAt"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                if pub_date > yesterday_dt:
                    video_id = item["snippet"]["resourceId"]["videoId"]
                    short, duration = is_short(video_id)
                    if not short:
                        found_videos.append({
                            "name": name,
                            "title": item["snippet"]["title"],
                            "video_id": video_id,
                            "duration": duration
                        })
        except Exception as e:
            print(f"HATA: {name}: {e}")
    return found_videos

def transkript_cek(video_id):
    # Fetches transcript via Apify, retries 3 times on failure
    for attempt in range(3):
        try:
            response = requests.post(
                "https://api.apify.com/v2/acts/starvibe~youtube-video-transcript/run-sync-get-dataset-items",
                params={"token": APIFY_API_KEY},
                json={"youtube_url": f"https://www.youtube.com/watch?v={video_id}"},
                timeout=60
            ).json()
            if response and len(response) > 0:
                data = response[0].get("transcript") or []
                if data:
                    transkript = " ".join([t.get("text", "") for t in data])
                    return transkript
                else:
                    print(f"  ⚠️ Transkript boş geldi [{video_id}], deneme {attempt+1}/3")
        except Exception as e:
            print(f"  Apify hatası (deneme {attempt+1}/3): {e}")
        time.sleep(10)
    return None

def analyze_video(video, transkript):
    # Tries each Gemini API key in order, moves to next if quota exceeded
    prompt = PROMPT_TEMPLATE.format(
        channel_name=video["name"],
        video_title=video["title"],
        transkript=transkript
    )

    for key in GEMINI_API_KEYS:
        if not key:
            continue
        client = genai.Client(api_key=key)
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
                if "RESOURCE_EXHAUSTED" in str(e):
                    print(f"  Key exhausted, trying next key...")
                    break
                wait = (attempt + 1) * 30
                print(f"  API hatası (deneme {attempt+1}): {e} — {wait} saniye bekleniyor...")
                time.sleep(wait)

    return f"⚠️ [{video['name']}] \"{video['title']}\" — Tüm API keyleri tükendi."

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

        all_reports = []

        for i, video in enumerate(videos):
            print(f"\n[{i+1}/{len(videos)}] İşleniyor: [{video['name']}] {video['title']}")

            transkript = transkript_cek(video["video_id"])
            if not transkript:
                print(f"  ⚠️ Transkript alınamadı, atlanıyor.")
                continue

            print(f"  ✓ Transkript alındı, analiz ediliyor...")
            print(f"  📝 TRANSKRİPT (ilk 500 karakter):\n{transkript[:500]}...\n")
            report = analyze_video(video, transkript)

            video_section = f"**{len(all_reports) + 1}.** 📺 **[{video['name']}]** — {video['title']} `({video['duration']})`\n\n{report}"
            all_reports.append(video_section)
            print(f"  ✅ Rapor hazırlandı.")
            time.sleep(2)

        if not all_reports:
            print("Hiçbir video işlenemedi.")
        else:
            current_date = datetime.now().strftime("%d.%m.%Y")
            full_report = f"📅 **{current_date}**\n\n" + "\n\n---\n\n".join(all_reports)
            send_to_discord(full_report)
            print(f"\nİşlem tamamlandı. {len(all_reports)} video Discord'a gönderildi!")
