import os
import requests
from datetime import datetime, timedelta
from google import genai
from youtube_transcript_api import YouTubeTranscriptApi # YENİ EKLENDİ

# Ayarlar
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

def get_latest_videos():
    all_text = ""
    yesterday_dt = datetime.utcnow() - timedelta(days=2) 
    
    for name, cid in CHANNELS.items():
        channel_url = f"https://www.googleapis.com/youtube/v3/channels?part=contentDetails&forHandle={cid}&key={YOUTUBE_API_KEY}"
        c_res = requests.get(channel_url).json()
        
        try:
            uploads_playlist_id = c_res["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
        except (KeyError, IndexError):
            print(f"YOUTUBE HATASI ({name}) - Kanal bilgisi alınamadı.")
            continue

        url = f"https://www.googleapis.com/youtube/v3/playlistItems?part=snippet&playlistId={uploads_playlist_id}&maxResults=10&key={YOUTUBE_API_KEY}"
        res = requests.get(url).json()
        
        if "error" in res:
            print(f"API HATASI ({name}) - Video çekilirken hata: {res['error']['message']}")
            continue
        
        for item in res.get("items", []):
            pub_date_str = item["snippet"]["publishedAt"]
            pub_date = datetime.strptime(pub_date_str, "%Y-%m-%dT%H:%M:%SZ")
            
            if pub_date > yesterday_dt:
                title = item["snippet"]["title"]
                video_id = item["snippet"]["resourceId"]["videoId"] # VİDEO ID'Sİ ALINDI
                
                print(f"Bulunan Video ({name}): {title}")
                
                # TRANSKRİPT ÇEKME İŞLEMİ
                try:
                    # 'tr' dili öncelikli, yoksa otomatik oluşturulanı dener
                    transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['tr'])
                    transcript_text = " ".join([t['text'] for t in transcript_list])
                    print(f"  -> Transkript başarıyla çekildi ({len(transcript_text)} karakter).")
                except Exception as e:
                    transcript_text = "(Bu videonun transkripti kapalı veya okunamadı.)"
                    print(f"  -> Transkript çekilemedi (Altyazı kapalı olabilir).")

                all_text += f"\nKanal: {name}\nBaşlık: {title}\nTranskript: {transcript_text}\n---"
                
    return all_text

def get_ai_report(content):
    client = genai.Client(api_key=GEMINI_API_KEY)
    prompt = f"""Sen profesyonel ve tarafsız bir haber özetleyici asistansın. Görevin, sana verilen video metinlerini (transkriptleri) tarafsız ve anlaşılır şekilde özetlemektir. Kesinlikle uyman gereken kurallar şunlardır:
1-Her zaman kısa, net ve anlaşılır bir Türkçe kullan.
2-Haberin özünden sapma, gereksiz detayları ve tekrarları atla.
3-Kendi kişisel yorumunu, duygularını veya tavsiyelerini kesinlikle ekleme; sadece metindeki gerçekleri aktar.
4-Önemli hiçbir detayı atlama.

{content}"""
    
    print("--- GÖNDERİLEN PROMPT ÖNİZLEMESİ ---")
    # Çok uzun metinler logları kilitlemesin diye sadece ilk 1000 karakteri yazdırıyoruz
    print(prompt[:1000] + "\n... [DEVAMI VAR] ...") 
    
    response = client.models.generate_content(
        model='gemini-3-flash-preview',
        contents=prompt,
    )
    return response.text

def send_to_discord(report):
    chunks = [report[i:i+1900] for i in range(0, len(report), 1900)]
    for chunk in chunks:
        requests.post(DISCORD_URL, json={"content": chunk})

if __name__ == "__main__":
    print("Sistem uyandı, videolar resmi kanallardan çekiliyor...")
    
    api_test = str(YOUTUBE_API_KEY)[:5] if YOUTUBE_API_KEY else "BULUNAMADI VEYA BOŞ!"
    print(f"Sistemdeki YouTube API Anahtarı Durumu: {api_test}...")
    
    content = get_latest_videos()
    
    if content:
        print("Yeni videolar bulundu. Gemini analiz ediyor...")
        report = get_ai_report(content)
        send_to_discord(report)
        print("Rapor başarıyla Discord'a gönderildi!")
    else:
        print("Son 48 saatte bu kanallarda yeni video bulunamadı veya bir hata oluştu.")
