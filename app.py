import os
import base64
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

# Kullanıcıya özel geçici veri deposu (hafıza)
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

    # Saat yakalama (örn: 15:00)
    match_time = re.search(r"\b(\d{1,2})([:\.](\d{2}))?\b", message)
    if match_time:
        hour = int(match_time.group(1))
        minute = int(match_time.group(3)) if match_time.group(3) else 0
        date = date.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return date
    else:
        return None

def classify_message(msg):
    msg = msg.lower()
    if "fiyat" in msg or "ücret" in msg or "ne kadar" in msg:
        return "price"
    elif "nerede" in msg or "adres" in msg or "harita" in msg:
        return "location"
    elif "kaçta" in msg or "saat kaç" in msg or "çalışma saat" in msg:
        return "working_hours"
    elif "randevu" in msg or "gelmek" in msg or "saat" in msg or re.search(r"\d{1,2}/\d{1,2}", msg):
        return "appointment"
    elif "yanlış" in msg or "pardon" in msg or "değil" in msg or "değiştir" in msg or "iptal" in msg:
        return "correction"
    else:
        return "general"

@app.route("/whatsapp", methods=["POST"])
def whatsapp():
    msg = request.form.get('Body')
    sender = request.form.get('From')

    turkey_tz = pytz.timezone("Europe/Istanbul")
    now = datetime.now(turkey_tz)
    tarih = now.strftime("%d.%m.%Y")
    saat = now.strftime("%H:%M")

    message_type = classify_message(msg)
    resp = MessagingResponse()

    # İptal isteği
    if message_type == "correction" and sender in session_memory:
        randevu_str = session_memory.pop(sender)
        cell = sheet.find(randevu_str)
        if cell:
            sheet.delete_rows(cell.row)
        session_memory[sender] = "awaiting_new"
        resp.message("📝 Önceki randevu talebiniz iptal edildi. Yeni tarih ve saati belirtir misiniz?")

    # Randevu isteği
    elif message_type == "appointment":
        randevu_datetime = extract_datetime(msg)
        randevu_str = randevu_datetime.strftime("%d.%m.%Y %H:%M") if randevu_datetime else "Belirtilmedi"
        durum = "Geçti" if randevu_datetime and randevu_datetime < now else "Bekliyor"

        if not randevu_datetime:
            resp.message("🕒 Randevu için lütfen tarih ve saat belirtin. Örneğin: 19/04 15:00")
        else:
            randevu_saatleri = sheet.col_values(5)
            if randevu_str in randevu_saatleri:
                resp.message(f"❌ {randevu_str} saati için başka bir randevu bulunuyor. Lütfen başka bir saat önerin.")
            else:
                sheet.append_row([tarih, saat, sender, durum, randevu_str])
                session_memory[sender] = randevu_str
                resp.message(f"✅ Randevu isteğiniz {randevu_str} için başarıyla alındı.")

    # Önceki iptalin ardından gelen tarih-saat cevabı
    elif session_memory.get(sender) == "awaiting_new":
        randevu_datetime = extract_datetime(msg)
        if not randevu_datetime:
            resp.message("🕒 Yeni randevu için lütfen tarih ve saat belirtin.")
        else:
            randevu_str = randevu_datetime.strftime("%d.%m.%Y %H:%M")
            durum = "Geçti" if randevu_datetime < now else "Bekliyor"
            randevu_saatleri = sheet.col_values(5)
            if randevu_str in randevu_saatleri:
                resp.message(f"❌ {randevu_str} saati için başka bir randevu bulunuyor. Lütfen başka bir saat önerin.")
            else:
                sheet.append_row([tarih, saat, sender, durum, randevu_str])
                session_memory[sender] = randevu_str
                resp.message(f"✅ Yeni randevunuz {randevu_str} olarak güncellendi.")

    # Bilgi talepleri
    elif message_type == "price":
        resp.message("💸 Fiyatlarımız şu şekildedir: ... (örnek metin)")
    elif message_type == "location":
        resp.message("📍 Adresimiz: https://goo.gl/maps/ornekadres")
    elif message_type == "working_hours":
        resp.message("⏰ Çalışma saatlerimiz: Hafta içi 10:00 - 18:00, Cumartesi 11:00 - 16:00")

    # Genel karşılama mesajı
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
