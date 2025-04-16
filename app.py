from flask import Flask, request, make_response
from twilio.twiml.messaging_response import MessagingResponse
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

app = Flask(__name__)

# Google Sheets bağlantısı
scope = ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive']
creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
client = gspread.authorize(creds)
sheet = client.open_by_url("https://docs.google.com/spreadsheets/d/1d5y0kD9DY24-CAnqJkC_oofjLJOsCNhdT9LX22w8El4/edit").sheet1

@app.route("/whatsapp", methods=["POST"])
def whatsapp():
    try:
        msg = request.form.get('Body')
        sender = request.form.get('From')

        now = datetime.now()
        tarih = now.strftime("%d.%m.%Y")
        saat = now.strftime("%H:%M")

        sheet.append_row([tarih, saat, sender, "Bekliyor"])

        resp = MessagingResponse()
        resp.message("Randevu isteğin alındı 📝 En kısa sürede dönüş yapılacaktır.")
        
        response = make_response(str(resp))
        response.headers['Content-Type'] = 'application/xml'
        return response

    except Exception as e:
        print("❌ HATA:", e)
        return "error", 500

if __name__ == "__main__":
    app.run(debug=True)
