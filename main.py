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
    """1. AŞAMA: Haberleri tespit et ve birbiriyle ilişkili konuları tek başlık altında birleştir."""
    client = genai.Client(api_key=GEMINI_API_KEY)

    prompt = f"""
    Aşağıdaki <TRANSKRİPTLER> etiketleri arasındaki metni inceleyin.
    <TRANSKRİPTLER>
    {full_content}
    </TRANSKRİPTLER>

    Metindeki tüm haber konularını tespit edin. Birbiriyle doğrudan ilişkili konuları tek bir başlık altında birleştirin.
    Her başlık için o habere değinen yayıncıları da belirtin.
    Hiçbir haberi atlama. Sadece aşağıdaki formatta liste döndür, başka hiçbir metin ekleme.

    Format:
    Haber Başlığı | Yayıncı 1, Yayıncı 2
    """

    response = client.models.generate_content(
        model='gemini-3-flash-preview',
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=(
                "Sen profesyonel bir haber analistisin. Görevin transkriptlerdeki "
                "tüm haber konularını tespit etmek ve birbiriyle ilişkili olanları "
                "tek başlık altında birleştirmektir. Hiçbir haberi atlama. "
                "Sadece istenen formattaki listeyi döndür, yorum veya selamlama ekleme."
                "Yorumu yapan kişi kanala konuk alının bir kişi ise isminin yanında konuk olduğu kanal ismini belirt. 'Konuk ismi (Kanal ismi)' formatında."
            ),
            temperature=0.1,
            max_output_tokens=4096,
        )
    )

    lines = response.text.strip().split('\n')
    topics = [line.strip() for line in lines if '|' in line]
    print(f"Tespit edilen haber sayısı: {len(topics)}")
    return topics

def get_guided_report(full_content, topics, videos):
    """2. AŞAMA: İndeks listesi ve transkriptlerle tek seferde rehberli rapor oluştur."""
    client = genai.Client(api_key=GEMINI_API_KEY)
    current_date = datetime.now().strftime("%d.%m.%Y")

    # Başlık listesini numaralandırılmış formata çevir
    numbered_topics = "\n".join([f"{i+1}. {t.split('|')[0].strip()}" for i, t in enumerate(topics)])

    # Kaynak listesini oluştur
    sources = "\n".join([f"- [{v['name']}] {v['title']}" for v in videos])

    prompt = f"""
    Aşağıdaki <İNDEKS> listesindeki haberleri sırasıyla işleyerek rapor oluştur.
    
    <İNDEKS>
    {numbered_topics}
    </İNDEKS>
    
    <TRANSKRİPTLER>
    {full_content}
    </TRANSKRİPTLER>
    
    KATİ KURALLAR:
    1. İndeksteki her başlığı sırasıyla işle, hiçbirini atlama.
    2. Bir başlıkta yazdığın bilgiyi başka bir başlıkta kesinlikle tekrar etme.
    3. Her haberi tarafsız ve nesnel özetle, kendi yorumunu ekleme.
    4. Yayıncı yorumlarını yumuşatmadan olduğu gibi aktar.
    5. Selamlama veya kapanış cümlesi ekleme, doğrudan rapora başla.
    6. Transkripti bulunamayan bir video var ise rapor başında '(videonun adı) transkripti bulunamadı' şeklinde belirt.
    
    Raporun tam yapısı şu şekilde olmalıdır:
    
    📅 **Tarih: {current_date}**
    
    **İncelenen Kaynaklar:**
    {sources}
    
    ---
    
    (İndeksteki her başlık için aşağıdaki yapıyı tekrarla:)
    🔹 **HABERİN BAŞLIĞI**
    **Haber:** (Tarafsız özet. Kim, ne yaptı, nerede, ne zaman, sonucu ne?)
    **Yayıncı Yorumları:**
    * **[Yayıncı Adı]:** (Yaklaşımı ve vurguladığı noktalar)
    """

    response = client.models.generate_content(
        model='gemini-3-flash-preview',
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=(
                "Sen tarafsız, nesnel ve profesyonel bir haber derleyici ve analistsin. "
                "Temel görevin verilen indeks listesindeki her haberi sırasıyla işlemek, "
                "hiçbirini atlamamak ve aynı bilgiyi birden fazla başlık altında tekrar etmemektir. "
                "Yayıncıların yorumlarını yumuşatmadan olduğu gibi aktar."
            ),
            temperature=0.4,
            top_p=0.9,
            max_output_tokens=64000,
            thinking_config=types.ThinkingConfig(
                thinking_level=types.ThinkingLevel.HIGH
            )
        )
    )
    print(full_content)
    return response.text.strip()

def get_ai_report(videos, full_content):
    """Ana fonksiyon: İndeksleme ve rehberli sentezi sırasıyla çalıştırır."""
    print("1. Aşama başlatılıyor: Haberler indeksleniyor...")
    topics = get_news_index(full_content)

    if not topics:
        return "Haber bulunamadı veya transkript okunamadı."

    print("2. Aşama başlatılıyor: Rehberli rapor oluşturuluyor...")
    return get_guided_report(full_content, topics, videos)

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
