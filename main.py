import os
import requests
from datetime import datetime, timedelta
import google.generativeai as genai

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
    yesterday = (datetime.utcnow() - timedelta(days=1)).isoformat() + "Z"
    
    for name, cid in CHANNELS.items():
        url = f"https://www.googleapis.com/youtube/v3/search?key={YOUTUBE_API_KEY}&channelId={cid}&part=snippet,id&order=date&maxResults=2&publishedAfter={yesterday}"
        res = requests.get(url).json()
        
        for item in res.get("items", []):
            title = item["snippet"]["title"]
            description = item["snippet"]["description"]
            all_text += f"\nKanal: {name}\nBaşlık: {title}\nÖzet: {description}\n---"
    return all_text

def get_ai_report(content):
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-pro') # En stabil çalışan model
    prompt = f"Aşağıdaki haber dökümlerini analiz et. Aynı haberi sunan kanalların yorumlarını kıyasla. Farklı haberleri grupla. Şık bir Discord raporu hazırla:\n\n{content}"
    response = model.generate_content(prompt)
    return response.text

def send_to_discord(report):
    # Discord mesaj sınırı 2000 karakterdir, gerekirse bölerek göndeririz
    chunks = [report[i:i+1900] for i in range(0, len(report), 1900)]
    for chunk in chunks:
        requests.post(DISCORD_URL, json={"content": chunk})

if __name__ == "__main__":
    content = get_latest_videos()
    if content:
        report = get_ai_report(content)
        send_to_discord(report)
