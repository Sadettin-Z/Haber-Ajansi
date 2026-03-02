import os
import requests
from datetime import datetime, timedelta
from google import genai
from youtube_transcript_api import YouTubeTranscriptApi

# --- AYARLAR ---
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DISCORD_URL = os.getenv("DISCORD_WEBHOOK_URL")

CHANNELS = {
    "Serdar Akinan": "@serdarakinan",
    "Yılmaz Özdil": "@yilmaz_ozdil",
    "Cem Gürdeniz": "@cemgurdenizz",
    "Erdem Atay": "@erdematayveryansintv",
    "Onlar TV": "@onlartv"
}

# --- 1. KISIM: VİDEOLARI BULMA ---
def get_latest_video_list():
    """Kanalları gezer ve son 24 saatteki videoların listesini döner."""
    found_videos = []
    yesterday_dt = datetime.utcnow() - timedelta(days=1)
    
    for name, handle in CHANNELS.items():
        channel_url = f"https://www.googleapis.com/youtube/v3/channels?part=contentDetails&forHandle={handle}&key={YOUTUBE_API_KEY}"
        try:
            c_res = requests.get(channel_url).json()
            uploads_id = c_res["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
            
            url = f"https://www.googleapis.com/youtube/v3/playlistItems?part=snippet&playlistId={uploads_id}&maxResults=5&key={YOUTUBE_API_KEY}"
            res = requests.get(url).json()
            
            for item in res.get("items", []):
                pub_date_str = item["snippet"]["publishedAt"]
                pub_date = datetime.strptime(pub_date_str, "%Y-%m-%dT%H:%M:%SZ")
                
                if pub_date > yesterday_dt:
                    found_videos.append({
                        "name": name,
                        "title": item["snippet"]["title"],
                        "video_id": item["snippet"]["resourceId"]["videoId"]
                    })
        except Exception as e:
            print(f"HATA: {name} kanalı taranırken bir sorun oluştu.")
            
    return found_videos

# --- 2. KISIM: SENİN ÇALIŞAN TRANSKRİPT METODUN ---
def transkript_cek(video_id):
    """Senin doğruladığın çalışan transkript çekme mantığı."""
    try:
        # Yeni API'yi başlat
        ytt_api = YouTubeTranscriptApi()
        
        # Altyazı listesini çek ve Türkçe veya İngilizce olanı bul
        transcript_list = ytt_api.list(video_id)
        transcript = transcript_list.find_transcript(['tr', 'en'])
        
        # Veriyi işle
        fetched_transcript = transcript.fetch()
        transcript_data = fetched_transcript.to_raw_data()
        
        # Metni birleştir
        return " ".join([t['text'] for t in transcript_data])
        
    except Exception as e:
        return f"(Transkript okunamadı: {type(e).__name__})"

# --- 3. KISIM: ANALİZ VE GÖNDERİM ---
def get_ai_report(full_content):
    client = genai.Client(api_key=GEMINI_API_KEY)
    prompt = f"Aşağıdaki haber metinlerini tarafsız ve kısa bir şekilde özetle:\n\n{full_content}"
    print(prompt)
    response = client.models.generate_content(model='gemini-3-flash-preview', contents=prompt)
    return response.text

def send_to_discord(report):
    chunks = [report[i:i+1900] for i in range(0, len(report), 1900)]
    for chunk in chunks:
        requests.post(DISCORD_URL, json={"content": chunk})

# --- ANA ÇALIŞTIRICI ---
if __name__ == "__main__":
    print("Sistem başlatıldı...")
    
    videos = get_latest_video_list()
    
    if not videos:
        print("Son 24 saatte yeni video bulunamadı.")
    else:
        content_for_ai = ""
        for v in videos:
            print(f"İşleniyor: {v['title']}")
            t_text = transkript_cek(v['video_id'])
            content_for_ai += f"Kanal: {v['name']}\nBaşlık: {v['title']}\nMetin: {t_text}\n\n"
        
        print("Gemini'ye gönderiliyor...")
        final_report = get_ai_report(content_for_ai)
        send_to_discord(final_report)
        print("İşlem tamamlandı, rapor Discord'a uçtu!")
