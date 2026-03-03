import os
import requests
from datetime import datetime, timedelta
from google import genai

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
                    found_videos.append({"name": name, "title": item["snippet"]["title"], "video_id": item["snippet"]["resourceId"]["videoId"]})
        except Exception as e:
            print(f"HATA: {name}: {e}")
    return found_videos

def transkript_cek(video_id):
    for attempt in range(3):  # tries 3 times before giving up
        try:
            res = requests.get(
                f"https://api.supadata.ai/v1/youtube/transcript?videoId={video_id}",
                headers={"x-api-key": SUPADATA_API_KEY},
                timeout=10
            ).json()
            if "content" in res:
                return " ".join([t["text"] for t in res["content"]])
        except Exception as e:
            print(f"Deneme {attempt+1} başarısız: {type(e).__name__}")
    
    return "(Transkript bulunamadı)"

def get_ai_report(full_content):
    client = genai.Client(api_key=GEMINI_API_KEY)
    prompt = f"""GÖREV Sana birden fazla YouTube haber kanalının video transkriptlerini yükleyeceğim. Bu transkriptleri okuyarak içlerinde geçen tüm haberleri aşağıdaki formatta özetle.
ÖNEMLİ KURALLAR
* HİÇBİR haberi atlama. Haber değeri taşıyan her konuyu, ne kadar kısa geçilmiş olursa olsun, listeye ekle.
* Her haberi tarafsız ve nesnel bir şekilde özetle. Kendi yorum veya değerlendirmeni ekleme.
* Yayıncıların yorumlarını olduğu gibi aktar, yorumlamadan veya yumuşatmadan.
* Bir haber birden fazla kanalda geçiyorsa, her kanalın o habere bakışını ayrı ayrı yaz.
* Bir kanal belirli bir habere hiç değinmediyse, o kanalı o haberin altına ekleme.
* Raporun başında hangi kanalların hangi videosunu kullanıldığını bir liste halinde belirt.
FORMAT Her haber için şu yapıyı kullan:
🔹 [HABERİN KISA BAŞLIĞI]
Özet: [Haberin tarafsız özeti. Kim, ne yaptı, nerede, ne zaman, sonucu ne?]
Yayıncı Yorumları:
* [Yayıncı 1 Adı]: [Bu yayıncının habere yaklaşımı, vurguladığı noktalar, yorumu]
* [Yayıncı 2 Adı]: [Bu yayıncının habere yaklaşımı, vurguladığı noktalar, yorumu]
* (Bu haberi ele alan tüm yayıncıları sırasıyla ekle)

{full_content}"""
    print(prompt)
    return client.models.generate_content(model='gemini-3-flash-preview', contents=prompt).text
#gemini-3-flash-preview
def send_to_discord(report):
    for chunk in [report[i:i+1900] for i in range(0, len(report), 1900)]:
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
