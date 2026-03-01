import os
import requests
from datetime import datetime, timedelta
from google import genai

# Ayarlar
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DISCORD_URL = os.getenv("DISCORD_WEBHOOK_URL")

CHANNELS = {
    "Serdar Akinan": "UCyHwV6n_r4O8Y9v7b0X-Iyg",
    "Yılmaz Özdil": "UCW7-Nl8WpD6VnU7GfKj-pAg",
    "Cem Gürdeniz": "UCLn_f_m8vY0L9b6v-uK0k6g",
    "Erdem Atay": "UC9W1Zp-pE1Gj0v7b8_v4L0w",
    "Onlar TV": "UCX8P7_7v1b8MvY-6v-G0u6w"
}

def get_latest_videos():
    all_text = ""
    yesterday_dt = datetime.utcnow() - timedelta(days=1)
    
    for name, cid in CHANNELS.items():
        channel_url = f"https://www.googleapis.com/youtube/v3/channels?part=contentDetails&id={cid}&key={YOUTUBE_API_KEY}"
        c_res = requests.get(channel_url).json()
        
        try:
            uploads_playlist_id = c_res["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
        except (KeyError, IndexError):
            # İŞTE RÖNTGEN BURADA: YouTube'un asıl hatasını yazdırıyoruz
            print(f"YOUTUBE HATASI ({name}) - YouTube'un Gerçek Cevabı: {c_res}")
            continue

        url = f"https://www.googleapis.com/youtube/v3/playlistItems?part=snippet&playlistId={uploads_playlist_id}&maxResults=3&key={YOUTUBE_API_KEY}"
        res = requests.get(url).json()
        
        for item in res.get("items", []):
            pub_date_str = item["snippet"]["publishedAt"]
            pub_date = datetime.strptime(pub_date_str, "%Y-%m-%dT%H:%M:%SZ")
            
            if pub_date > yesterday_dt:
                title = item["snippet"]["title"]
                description = item["snippet"]["description"]
                all_text += f"\nKanal: {name}\nBaşlık: {title}\nÖzet: {description}\n---"
    return all_text

def get_ai_report(content):
    client = genai.Client(api_key=GEMINI_API_KEY)
    prompt = f"Aşağıdaki haber dökümlerini analiz et. Aynı haberi sunan kanalların yorumlarını kıyasla. Farklı haberleri grupla. Şık bir Discord raporu hazırla:\n\n{content}"
    
    response = client.models.generate_content(
        model='gemini-1.5-pro',
        contents=prompt,
    )
    return response.text

def send_to_discord(report):
    chunks = [report[i:i+1900] for i in range(0, len(report), 1900)]
    for chunk in chunks:
        requests.post(DISCORD_URL, json={"content": chunk})

if __name__ == "__main__":
    print("Sistem uyandı, videolar resmi kanallardan çekiliyor...")
    
    # API Anahtarının kod tarafından görünüp görünmediğini test edelim
    api_test = str(YOUTUBE_API_KEY)[:5] if YOUTUBE_API_KEY else "BULUNAMADI VEYA BOŞ!"
    print(f"Sistemdeki YouTube API Anahtarı Durumu: {api_test}...")
    
    content = get_latest_videos()
    
    if content:
        print("Harika! Yeni videolar bulundu. Gemini analiz ediyor...")
        report = get_ai_report(content)
        send_to_discord(report)
        print("Rapor başarıyla Discord'a gönderildi!")
    else:
        print("Son 24 saatte bu kanallarda yeni video bulunamadı veya bir hata oluştu.")
