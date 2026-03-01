import os
import requests
from datetime import datetime, timedelta
from google import genai

# Ayarlar
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DISCORD_URL = os.getenv("DISCORD_WEBHOOK_URL")

CHANNELS = {
    "Serdar Akinan": "@serdarakinan",
   
}

def get_latest_videos():
    all_text = ""
    # Zaman penceresini 48 saate (2 güne) çıkardık ki kıl payı kaçan videoları yakalayalım
    yesterday_dt = datetime.utcnow() - timedelta(days=2) 
    
    for name, cid in CHANNELS.items():
        channel_url = f"https://www.googleapis.com/youtube/v3/channels?part=contentDetails&forHandle={cid}&key={YOUTUBE_API_KEY}"
        c_res = requests.get(channel_url).json()
        
        try:
            uploads_playlist_id = c_res["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
        except (KeyError, IndexError):
            print(f"YOUTUBE HATASI ({name}) - Kanal bilgisi alınamadı: {c_res}")
            continue

        # maxResults=10 yaptık (Shorts videoları asıl videoları aşağı itmesin diye)
        url = f"https://www.googleapis.com/youtube/v3/playlistItems?part=snippet&playlistId={uploads_playlist_id}&maxResults=10&key={YOUTUBE_API_KEY}"
        res = requests.get(url).json()
        
        # Eğer API kota/limit hatası verdiyse loglara yazdıralım
        if "error" in res:
            print(f"API HATASI ({name}) - Video çekilirken hata: {res['error']['message']}")
            continue
        
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
        model='gemini-3.0-flash', # veya 'gemini-3-flash'
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
