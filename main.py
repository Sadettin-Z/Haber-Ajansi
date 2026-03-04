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
            time.sleep(3)
    return "(Transkript bulunamadı)"

def get_news_index(full_content):
    """1. AŞAMA: Transkriptteki tüm haberleri tespit edip liste oluşturur."""
    client = genai.Client(api_key=GEMINI_API_KEY)

    prompt = f"""
    Aşağıdaki <TRANSKRİPTLER> etiketleri arasındaki metni inceleyin.
    <TRANSKRİPTLER>
    {full_content}
    </TRANSKRİPTLER>

    Metindeki her bir farklı haber konusunu ve o konuyu sunan yayıncıları aşağıdaki formatta listeleyin.
    Her haber için tek bir satır kullanın. Başka hiçbir metin eklemeyin.

    Format:
    Haber Başlığı | Yayıncı 1, Yayıncı 2
    """

    response = client.models.generate_content(
        model='gemini-3-flash-preview',
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=(
                "Sen profesyonel bir haber analistisin. Görevin transkriptlerdeki "
                "tüm haber konularını ve yayıncıları tespit etmektir. "
                "Hiçbir haberi atlama. Sadece istenen formattaki listeyi döndür, yorum veya selamlama ekleme."
            ),
            temperature=0.1,
            max_output_tokens=4096,
        )
    )

    lines = response.text.strip().split('\n')
    topics = [line.strip() for line in lines if '|' in line]
    return topics

def analyze_single_topic(full_content, topic_line):
    """2. AŞAMA: Tek bir habere odaklanarak detaylı analiz yapar."""
    client = genai.Client(api_key=GEMINI_API_KEY)
    topic_title = topic_line.split('|')[0].strip()

    prompt = f"""
    Aşağıdaki <TRANSKRİPTLER> etiketleri arasındaki metni kullanarak SADECE belirtilen hedefe odaklanın.

    <HEDEF_HABER>
    {topic_title}
    </HEDEF_HABER>

    <TRANSKRİPTLER>
    {full_content}
    </TRANSKRİPTLER>

    Transkriptleri tarayın ve SADECE hedef haber ile ilgili kısımları analiz ederek aşağıdaki yapıda rapor oluşturun:

    🔹 **{topic_title}**
    **Haber:** (Haberin tarafsız özeti. Kim, ne yaptı, nerede, ne zaman, sonucu ne?)
    **Yayıncı Yorumları:**
    * **[Yayıncı Adı]:** (Bu yayıncının habere yaklaşımı, vurguladığı noktalar)
    """

    response = client.models.generate_content(
        model='gemini-3-flash-preview',
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=(
                "Sen tarafsız, nesnel ve profesyonel bir haber derleyici ve analistsin. "
                "Haberi tamamen tarafsız bir dille özetle. Kendi yorumunu kesinlikle ekleme. "
                "Yayıncıların yorumlarını, siyasi duruşlarını yumuşatmadan aktar. "
                "Yanıtına selamlama veya kapanış ekleme."
            ),
            temperature=0.4,
            top_p=0.9,
            max_output_tokens=4096,
            thinking_config=types.ThinkingConfig(
                thinking_level=types.ThinkingLevel.HIGH
            )
        )
    )
    return response.text.strip()

def get_ai_report(videos, full_content):
    """3. AŞAMA: İndeksi alır, döngüyü çalıştırır ve raporu birleştirir."""
    print("1. Aşama başlatılıyor: Haberler indeksleniyor...")
    topics = get_news_index(full_content)

    if not topics:
        return "Haber bulunamadı veya transkript okunamadı."

    print(f"Tespit edilen haber sayısı: {len(topics)}")

    current_date = datetime.now().strftime("%d.%m.%Y")

    # Rapor başlığı — kaynaklar videos listesinden alınıyor
    final_report = f"📅 **Tarih: {current_date}**\n\n"
    final_report += "**İncelenen Kaynaklar:**\n"
    for v in videos:
        final_report += f"- [{v['name']}] {v['title']}\n"
    final_report += "\n---\n\n"

    # Her haberi ayrı ayrı analiz et
    for i, topic_line in enumerate(topics, 1):
        topic_title = topic_line.split('|')[0].strip()
        print(f"2. Aşama ({i}/{len(topics)}): '{topic_title}' analiz ediliyor...")

        try:
            analysis = analyze_single_topic(full_content, topic_line)
            final_report += analysis + "\n\n---\n\n"
        except Exception as e:
            print(f"HATA: '{topic_title}' atlandı: {e}")
            final_report += f"🔹 **{topic_title}**\n**Haber:** (Analiz sırasında hata oluştu.)\n\n---\n\n"

        time.sleep(4)  # rate limit koruması

    return final_report.strip()

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

        send_to_discord(get_ai_report(videos, content_for_ai))
        print("İşlem tamamlandı, rapor Discord'a uçtu!")
