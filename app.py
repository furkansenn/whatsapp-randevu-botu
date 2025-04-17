import os
import base64
import json
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import pytz
import openai
from dotenv import load_dotenv

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

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

# OpenAI ile mesaj analiz et
def analyze_message_with_openai(message):
    prompt = f"""
    Kullanıcıdan gelen mesajı aşağıda veriyorum.
    - Niyetini anlamaya çalış: randevu almak mı, fiyat mı, adres mi, başka bir şey mi?
    - Eğer tarih ve saat belirtiyorsa, lütfen YYYY-MM-DD HH:MM formatında belirt.
    - Lütfen sadece aşağıdaki formatta JSON döndür:

    {{
        "intent": "appointment_request | price_query | location_query | working_hours | general",
        "datetime": "YYYY-MM-DD HH:MM" (eğer yoksa null yaz),
        "summary": "Kısa açıklama"
    }}

    Mesaj: "{message}"
    """

    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        temperature=0.2,
        messages=[
            {"role": "system", "content": "Sen bir WhatsApp randevu asistanısın."},
            {"role": "user", "content": prompt}
        ]
    )

    result = response.choices[0].message.content
    return json.loads(result)

@app.route("/whatsapp", methods=["POST"])
def whatsapp():
    msg = request.form.get('Body')
    sender = request.form.get('From')

    analysis = analyze_message_with_openai(msg)
    intent = analysis["intent"]
    randevu_datetime_str = analysis["datetime"]
    summary = analysis["summary"]

    turkey_tz = pytz.timezone("Europe/Istanbul")
    now = datetime.now(turkey_tz)
    tarih = now.strftime("%d.%m.%Y")
    saat = now.strftime("%H:%M")

    resp = MessagingResponse()

    if intent == "appointment_request":
        if randevu_datetime_str != "null":
            randevu_dt = datetime.strptime(randevu_datetime_str, "%Y-%m-%d %H:%M")
            randevu_dt = pytz.utc.localize(randevu_dt).astimezone(turkey_tz)
            randevu_str = randevu_dt.strftime("%d.%m.%Y %H:%M")
            durum = "Geçti" if randevu_dt < now else "Bekliyor"
            sheet.append_row([tarih, saat, sender, durum, randevu_str])
            resp.message(f"📅 Randevu isteğiniz {randevu_str} için alındı. En kısa sürede dönüş yapılacaktır.")
        else:
            resp.message("🕒 Randevu için lütfen tarih ve saat belirtin. Örneğin: 'Yarın saat 15:00'")
    elif intent == "price_query":
        resp.message("💸 Fiyatlarımız şu şekildedir: ... (örnek metin)")
    elif intent == "location_query":
        resp.message("📍 Adresimiz: https://goo.gl/maps/ornekadres")
    elif intent == "working_hours":
        resp.message("⏰ Çalışma saatlerimiz: Hafta içi 10:00 - 18:00, Cumartesi 11:00 - 16:00")
    else:
        resp.message("Merhaba 👋 Size nasıl yardımcı olabilirim? Randevu almak istiyorsanız tarih ve saati belirtmeniz yeterlidir.")

    return str(resp)

@app.route("/", methods=["GET"])
def home():
    return "Uygulama çalışıyor ✅"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
