import os
import requests
import isodate
from datetime import datetime, timedelta
from google import genai
import time
import anthropic

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
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
        import isodate
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
            c_res = requests.get(f"https://www.googleapis.com/youtube/v3/channels?part=contentDetails&forHandle={handle}&key={YOUTUBE_API_KEY}").json()
            uploads_id = c_res["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
            res = requests.get(f"https://www.googleapis.com/youtube/v3/playlistItems?part=snippet&playlistId={uploads_id}&maxResults=5&key={YOUTUBE_API_KEY}").json()
            for item in res.get("items", []):
                pub_date = datetime.strptime(item["snippet"]["publishedAt"], "%Y-%m-%dT%H:%M:%SZ")
                if pub_date > yesterday_dt:
                    video_id = item["snippet"]["resourceId"]["videoId"]
                    if not is_short(video_id):
                        found_videos.append({"name": name, "title": item["snippet"]["title"], "video_id": video_id})
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
            time.sleep(3)  # timeout sonrası 3 saniye bekle
    
    return "(Transkript bulunamadı)"

def get_ai_report(full_content):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = f"""GÖREV Sana birden fazla YouTube haber kanalının video transkriptlerini yükleyeceğim. Bu transkriptleri okuyarak içlerinde geçen tüm haberleri aşağıdaki formatta özetle.
ÖNEMLİ KURALLAR
* HİÇBİR haberi atlama. Haber değeri taşıyan her konuyu, ne kadar kısa geçilmiş olursa olsun, listeye ekle.
* Her haberi tarafsız ve nesnel bir şekilde özetle. Kendi yorum veya değerlendirmeni ekleme.
* Yayıncıların yorumlarını olduğu gibi aktar, yorumlamadan veya yumuşatmadan.
* Bir haber birden fazla kanalda geçiyorsa, her kanalın o habere bakışını ayrı ayrı yaz.
* Bir kanal belirli bir habere hiç değinmediyse, o kanalı o haberin altına ekleme.
* Raporun başında hangi kanalların hangi videosunu kullanıldığını bir liste halinde belirt.
* Rapor Discord'da yayınlamaya uygun olmalı.
* Yanıtına başlarken hiçbir selamlama, nezaket cümlesi veya açıklama metni kullanma. Yanıtın başlangıcına bugünün tarihini ekle.

FORMAT
Her haber için şu yapıyı kullan:
🔹 [HABERİN KISA BAŞLIĞI]
Haber: (Haberin tarafsız özeti. Kim, ne yaptı, nerede, ne zaman, sonucu ne?)
Yayıncı Yorumları:
* [Yayıncı 1 Adı]: (Bu yayıncının habere yaklaşımı, vurguladığı noktalar, yorumu)
* [Yayıncı 2 Adı]: (Bu yayıncının habere yaklaşımı, vurguladığı noktalar, yorumu)
* (Bu haberi ele alan tüm yayıncıları sırasıyla ekle)

{full_content}"""
    print(prompt)
    with client.messages.stream(
        model="claude-sonnet-4-6",
        max_tokens=64000,
        messages=[{"role": "user", "content": prompt}]
    ) as stream:
        for text in stream.text_stream:
            full_response += text
    
    return full_response
#gemini-3-flash-preview
#gemini-3-pro-preview
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
if __name__ == "__main__":
    videos = get_latest_video_list()
    if not videos:
        print("Son 24 saatte yeni video bulunamadı.")
    else:
        print(f"Bulunan videolar ({len(videos)} adet):")
        for v in videos:
            print(f"  - [{v['name']}] {v['title']}")
        
        content_for_ai = ""
        for v in videos:
            content_for_ai += f"Kanal: {v['name']}\nBaşlık: {v['title']}\nMetin: {transkript_cek(v['video_id'])}\n\n"
        
        send_to_discord(get_ai_report(content_for_ai))
        print("İşlem tamamlandı, rapor Discord'a uçtu!")
