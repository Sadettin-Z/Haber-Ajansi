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
    try:
        res = requests.get(f"https://api.supadata.ai/v1/youtube/transcript?videoId={video_id}", headers={"x-api-key": SUPADATA_API_KEY}).json()
        return " ".join([t["text"] for t in res["content"]]) if "content" in res else "(Transkript bulunamadı)"
    except Exception as e:
        return f"(Transkript okunamadı: {type(e).__name__})"

def get_ai_report(full_content):
    client = genai.Client(api_key=GEMINI_API_KEY)
    prompt = f"Aşağıdaki haber metinlerini tarafsız ve kısa bir şekilde özetle:\n\n{full_content}"
    print(prompt)
    return client.models.generate_content(model='gemini-3-flash-preview', contents=prompt).text

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
