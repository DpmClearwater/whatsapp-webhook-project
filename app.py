import os
import logging
import random
import string
from flask import Flask, request, jsonify
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from datetime import datetime
import pytz
import mysql.connector  # Per la connessione al database

# Configura il logger
logging.basicConfig(level=logging.DEBUG, filename="webhook.log", filemode="a",
                    format="%(asctime)s - %(levelname)s - %(message)s")

# Inizializza l'app Flask
app = Flask(__name__)

# Configurazioni generali
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")  # ID del Foglio Google
SERVICE_ACCOUNT_FILE = "/etc/secrets/GOOGLE_APPLICATION_CREDENTIALS"  # Credenziali Google
DB_CONFIG = {  # Configurazione MySQL/PostgreSQL
    "host": "localhost",
    "user": "root",
    "password": "clear",
    "database": "webhook_data"
}

# Token casuale per la verifica del webhook
VERIFY_TOKEN = ''.join(random.choices(string.ascii_letters + string.digits, k=16))
logging.info(f"Token di verifica generato: {VERIFY_TOKEN}")

# Configurazione fogli Google Sheets
WHATSAPP_SHEET = "WhatsApp!A2"  # Foglio dedicato ai messaggi WhatsApp

# Funzione per connettersi al database
def connect_to_db():
    try:
        return mysql.connector.connect(**DB_CONFIG)
    except mysql.connector.Error as err:
        logging.error(f"Errore di connessione al database: {err}")
        raise

# Funzione per formattare le date
def format_date_iso_to_italian(iso_date):
    if not iso_date:
        return ""
    try:
        dt = datetime.fromisoformat(iso_date)
        return dt.strftime("%d/%m/%Y")  # Formato italiano: giorno/mese/anno
    except ValueError:
        logging.error(f"Formato data non valido: {iso_date}")
        return iso_date

# Funzione per salvare su Google Sheets
def save_to_google_sheet(data):
    try:
        credentials = Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        service = build("sheets", "v4", credentials=credentials)

        # Aggiunge i dati al foglio
        service.spreadsheets().values().append(
            spreadsheetId=GOOGLE_SHEET_ID,
            range=WHATSAPP_SHEET,
            valueInputOption="RAW",
            body={"values": [data]}
        ).execute()
        logging.info(f"Dati salvati su Google Sheets: {data}")
    except Exception as e:
        logging.error(f"Errore durante il salvataggio su Google Sheets: {e}")

# Funzione per salvare su database
def save_to_database(data):
    try:
        connection = connect_to_db()
        cursor = connection.cursor()
        query = """
            INSERT INTO whatsapp_messages (timestamp, sender, message)
            VALUES (%s, %s, %s)
        """
        cursor.execute(query, data)
        connection.commit()
        logging.info(f"Dati salvati nel database: {data}")
    except mysql.connector.Error as err:
        logging.error(f"Errore durante il salvataggio nel database: {err}")
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()

# Funzione per rispondere ai messaggi
def send_whatsapp_reply(sender, message):
    # Qui aggiungeremo la logica per inviare risposte dinamiche
    logging.info(f"Risposta inviata a {sender}: {message}")

# Endpoint per gestire i webhook
@app.route("/webhook", methods=["POST"])
def webhook_handler():
    try:
        payload = request.json
        logging.debug(f"Payload ricevuto dal webhook: {payload}")

        # Verifica del messaggio WhatsApp
        if "messages" in payload["entry"][0]["changes"][0]["value"]:
            messages = payload["entry"][0]["changes"][0]["value"]["messages"]
            for message in messages:
                sender = message["from"]
                text = message["text"]["body"]

                # Salva i dati
                timestamp = datetime.now(pytz.timezone('Europe/Rome')).strftime("%d/%m/%Y %H:%M:%S")
                save_to_google_sheet([timestamp, sender, text])
                save_to_database((timestamp, sender, text))

                # Rispondi automaticamente
                send_whatsapp_reply(sender, "Grazie per il tuo messaggio!")

        return jsonify({"status": "success"}), 200
    except Exception as e:
        logging.error(f"Errore nel webhook: {e}")
        return jsonify({"error": str(e)}), 500

# Verifica del token
@app.route("/webhook", methods=["GET"])
def verify_webhook():
    if request.args.get("hub.verify_token") == VERIFY_TOKEN:
        return request.args.get("hub.challenge")
    return "Token non valido", 403

@app.route("/test_db", methods=["GET"])
def test_db():
    try:
        connection = connect_to_db()
        if connection.is_connected():
            return jsonify({"message": "Connessione al database riuscita!"}), 200
    except Exception as e:
        return jsonify({"error": f"Errore nella connessione al database: {e}"}), 500
    
# Endpoint di base per verificare lo stato del server
@app.route("/", methods=["GET"])
def home():
    logging.info("Richiesta di keep-alive ricevuta.")
    return jsonify({"message": "Il server è attivo e funzionante!"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5001)), debug=True)
