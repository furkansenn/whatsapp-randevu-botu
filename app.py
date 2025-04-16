import os
import base64
import json
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import pytz

app = Flask(__name__)

# Google Sheets bağlantısı
scope = ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive']

# Ortam değişkeninden gelen base64 string'i çöz ve geçici dosyaya yaz
credentials_base64 = os.environ.get("GOOGLE_CREDENTIALS_BASE64")
credentials_json = base64.b64decode(credentials_base64).decode("utf-8")

with open("temp_credentials.json", "w") as f:
    f.write(credentials_json)

creds = ServiceAccountCredentials.from_json_keyfile_name("temp_credentials.json", scope)
client = gspread.authorize(creds)
sheet = client.open_by_url("https://docs.google.com/spreadsheets/d/1d5y0kD9DY24-CAnqJkC_oofjLJOsCNhdT9LX22w8El4/edit").sheet1

@app.route("/whatsapp", methods=["POST"])
def whatsapp():
    msg = request.form.get('Body')
    sender = request.form.get('From')

    turkey_tz = pytz.timezone("Europe/Istanbul")
    now = datetime.now(turkey_tz)

    tarih = now.strftime("%d.%m.%Y")
    saat = now.strftime("%H:%M")

    sheet.append_row([tarih, saat, sender, "Bekliyor"])

    resp = MessagingResponse()
    resp.message("Randevu isteğin alındı 📝 En kısa sürede dönüş yapılacaktır.")
    return str(resp)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
