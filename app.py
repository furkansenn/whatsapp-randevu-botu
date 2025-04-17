import os
import base64
import requests
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import pytz
import re

app = Flask(__name__)

# Google Sheets bağlantısı
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
credentials_base64 = os.environ.get("GOOGLE_CREDENTIALS_BASE64")
credentials_json = base64.b64decode(credentials_base64).decode("utf-8")
with open("temp_credentials.json", "w") as f:
    f.write(credentials_json)
creds = ServiceAccountCredentials.from_json_keyfile_name("temp_credentials.json", scope)
client = gspread.authorize(creds)
sheet = client.open_by_url("https://docs.google.com/spreadsheets/d/1d5y0kD9DY24-CAnqJkC_oofjLJOsCNhdT9LX22w8El4/edit").sheet1

# Kullanıcıya özel geçici veri deposu
session_memory = {}

def extract_datetime(message):
    turkey_tz = pytz.timezone("Europe/Istanbul")
    now = datetime.now(turkey_tz)
    message = message.lower()

    match = re.search(r"(\d{1,2})[\/\.](\d{1,2})\s+(\d{1,2})([:\.](\d{2}))?", message)
    if match:
        day = int(match.group(1))
        month = int(match.group(2))
        hour = int(match.group(3))
        minute = int(match.group(5)) if match.group(5) else 0
        year = now.year
        try:
            return datetime(year, month, day, hour, minute, tzinfo=turkey_tz)
        except ValueError:
            return None
    return None

def classify_message(msg):
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        return "general"

    try:
        url = "https://api.deepseek.com/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        prompt = (
            "Sen bir WhatsApp mesaj sınıflayıcısısın. Gelen mesajı aşağıdaki kategorilerden birine ayır:\n\n"
            "- price: müşteri fiyatla ilgili bilgi soruyorsa\n"
            "- location: adres veya konum soruyorsa\n"
            "- working_hours: saat ya da açık olduğu zamanları soruyorsa\n"
            "- appointment: randevu almak istiyorsa\n"
            "- correction: daha önceki randevusunu iptal edip yeni bir tarih veriyorsa\n"
            "- general: diğer tüm mesajlar\n\n"
            f"Gelen mesaj: \"{msg}\"\n\n"
            "Sadece kategori ismini döndür (örneğin: appointment)."
        )
        data = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "user", "content": prompt}
            ]
        }
        response = requests.post(url, headers=headers, json=data)
        category = response.json()["choices"][0]["message"]["content"].strip().lower()
        return category
    except:
        return "general"

@app.route("/whatsapp", methods=["POST"])
def whatsapp():
    msg = request.form.get('Body')
    sender = request.form.get('From')
    turkey_tz = pytz.timezone("Europe/Istanbul")
    now = datetime.now(turkey_tz)
    tarih = now.strftime("%d.%m.%Y")
    saat = now.strftime("%H:%M")

    resp = MessagingResponse()

    if session_memory.get(sender) and isinstance(session_memory[sender], dict) and "awaiting_name" in session_memory[sender]:
        randevu_str = session_memory[sender]["awaiting_name"]
        randevu_dt = turkey_tz.localize(datetime.strptime(randevu_str, "%d.%m.%Y %H:%M"))
        durum = "Geçti" if randevu_dt < now else "Bekliyor"
        sheet.append_row([tarih, saat, sender.replace("whatsapp:", ""), durum, randevu_str, msg.strip()])
        session_memory[sender] = randevu_str
        resp.message(f"✅ Randevunuz {randevu_str} için başarıyla kaydedildi. Teşekkürler {msg.strip()}!")
        return str(resp)

    message_type = classify_message(msg)

    if message_type == "correction" and sender in session_memory:
        randevu_str = session_memory.pop(sender)
        cell = sheet.find(randevu_str)
        if cell:
            sheet.delete_rows(cell.row)
        session_memory[sender] = "awaiting_new"
        resp.message("📝 Önceki randevu talebiniz iptal edildi. Yeni tarih ve saati belirtir misiniz?")

    elif message_type == "appointment":
        randevu_datetime = extract_datetime(msg)
        randevu_str = randevu_datetime.strftime("%d.%m.%Y %H:%M") if randevu_datetime else "Belirtilmedi"
        if not randevu_datetime:
            resp.message("🕒 Randevu için lütfen tarih ve saat belirtin. Örneğin: 19/04 15:00")
        else:
            randevu_saatleri = sheet.col_values(5)
            if randevu_str in randevu_saatleri:
                resp.message(f"❌ {randevu_str} saati için başka bir randevu bulunuyor. Lütfen başka bir saat önerin.")
            else:
                session_memory[sender] = {"awaiting_name": randevu_str}
                resp.message(f"📛 Randevu saatiniz {randevu_str} olarak ayarlandı. Lütfen isminizi de yazar mısınız?")

    elif session_memory.get(sender) == "awaiting_new":
        randevu_datetime = extract_datetime(msg)
        if not randevu_datetime:
            resp.message("🕒 Yeni randevu için lütfen tarih ve saat belirtin.")
        else:
            randevu_str = randevu_datetime.strftime("%d.%m.%Y %H:%M")
            randevu_saatleri = sheet.col_values(5)
            if randevu_str in randevu_saatleri:
                resp.message(f"❌ {randevu_str} saati için başka bir randevu bulunuyor. Lütfen başka bir saat önerin.")
            else:
                session_memory[sender] = {"awaiting_name": randevu_str}
                resp.message(f"📛 Yeni randevu saatiniz {randevu_str}. Lütfen isminizi yazın.")

    elif message_type == "price":
        resp.message("💸 Fiyatlarımız şu şekildedir: ... (örnek metin)")
    elif message_type == "location":
        resp.message("📍 Adresimiz: https://goo.gl/maps/ornekadres")
    elif message_type == "working_hours":
        resp.message("⏰ Çalışma saatlerimiz: Hafta içi 10:00 - 18:00, Cumartesi 11:00 - 16:00")
    else:
        resp.message(
            "Merhaba 👋 Size nasıl yardımcı olabilirim?\n\n"
            "1️⃣ Randevu almak için **gün/ay saat** formatında yazınız. Örneğin: 19/04 15:00\n"
            "2️⃣ Fiyat bilgisi için 'fiyat' yazınız\n"
            "3️⃣ Çalışma saatleri için 'çalışma' yazınız\n"
            "4️⃣ Adres için 'adres' yazınız"
        )

    return str(resp)

@app.route("/", methods=["GET"])
def home():
    return "Uygulama çalışıyor ✅"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
