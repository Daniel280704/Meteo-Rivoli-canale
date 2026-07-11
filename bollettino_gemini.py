#!/usr/bin/env python3
import os
import requests
import sys
import google.generativeai as genai
from datetime import datetime, timedelta
import locale

# Tentativo di usare l'italiano per i giorni della settimana
try:
    locale.setlocale(locale.LC_TIME, 'it_IT.UTF-8')
except:
    pass

LAT = 45.0716
LON = 7.5157

def interpella_gemini(dati_meteo, info_giornaliere):
    api_key = os.getenv("GEMINI_API_KEY")
    genai.configure(api_key=api_key)
    # MODELLO AGGIORNATO (Versione 1.5)
    model = genai.GenerativeModel('models/gemini-3.5-flash')
    
    oggi_str = datetime.now().strftime("%A %d %B")
    domani_str = (datetime.now() + timedelta(days=1)).strftime("%A %d %B")
    
    prompt = f"""
    Sei un meteorologo professionista. Scrivi un bollettino meteo discorsivo per Rivoli (TO) per le prossime 48 ore.
    Oggi è {oggi_str}, domani sarà {domani_str}.
    
    RIFERIMENTI UFFICIALI (Usa questi valori per le temperature min/max):
    {info_giornaliere}

    REGOLE DI SCRITTURA (BOLLETTINO AVANZATO):
    1. NON usare elenchi puntati. Scrivi paragrafi fluidi e professionali.
    2. Usa le temperature min/max fornite nei riferimenti ufficiali come base della narrazione.
    
    REGOLA PRECIPITAZIONI E STAGIONALITÀ (CRITICA):
    3. Analizza SEMPRE la colonna EPS-Max. Se EPS-Max è maggiore di 0.0, anche se Prec.D2 è 0, DEVI obbligatoriamente segnalare l'instabilità, applicando questo filtro stagionale:
       - Se il mese corrente è compreso tra MARZO e OTTOBRE: avvisa del rischio di "rovesci" o "temporali sparsi".
       - Se il mese corrente è compreso tra NOVEMBRE e FEBBRAIO: usa ESCLUSIVAMENTE i termini "piogge", "precipitazioni" o "pioviggini" (è assolutamente vietato menzionare i temporali in questi mesi).
    
    REGOLA NEVE:
    4. Se le colonne Prec.D2 o EPS-Max indicano precipitazioni (>0) e in quelle stesse ore la Temperatura (T) è <= 2°C, DEVI esplicitamente annunciare la possibilità di nevicate o pioggia mista a neve.
    
    REGOLE DI DISAGIO TERMICO (BIOMETEOROLOGIA):
    5. AFA E CALDO (Basato su indice Humidex usando T e Dew Point):
       - ASSENZA DI DISAGIO: Se le condizioni non rientrano nei casi successivi, usa termini standard senza menzionare l'afa.
       - DISAGIO MODERATO (Attenzione - Colore Giallo): Se (T >= 28°C e Dew >= 15°C) OPPURE (T >= 25°C e Dew >= 20°C), segnala condizioni di "afa" e "disagio termico moderato".
       - FORTE DISAGIO (Pericolo - Colore Rosso): Se (T >= 32°C e Dew >= 20°C) OPPURE (T >= 30°C e Dew >= 24°C), segnala esplicitamente "caldo opprimente", "afa intensa" e "potenziale rischio fisico" per le ore centrali.
       
    6. WIND CHILL (Basato su T e Vento):
       - ASSENZA DI DISAGIO: Se Vento < 15 km/h o T > 8°C, usa le temperature standard senza menzionare il freddo percepito.
       - DISAGIO MODERATO (Freddo acuito - Colore Azzurro): Se (T <= 8°C e Vento >= 15 km/h), spiega che a causa della ventilazione la sensazione di freddo sarà sensibilmente più pungente rispetto alla temperatura reale.
       - FORTE DISAGIO (Rischio gelo - Colore Blu Scuro): Se (T <= 0°C e Vento >= 50 km/h) OPPURE (T <= -2°C e Vento >= 35 km/h) OPPURE (T <= -5°C e Vento >= 20 km/h), avvisa di condizioni "gelide" con percezione corporea severa (Wind Chill inferiore a -18°C).
    
    REGOLA NEBBIA/BRINA:
    7. Menziona foschie, nebbie o brinate SOLO in caso di inversione termica probabile: aria stagnante (Vento < 5 km/h), T notturna vicina o sotto lo 0°C, e UR% vicina al 100%.
    
    DATI ANALITICI ORARI (Ora | T | UR% | Dew | Prec.D2 | EPS-Max | Vento | Raffica):
    {dati_meteo}
    """

    try:
        response = model.generate_content(prompt, generation_config={"temperature": 0.3})
        return response.text
    except Exception as e:
        return f"Errore AI: {e}"

def main():
    # Fetch dati 48 ore con DAILY (min/max) e UR/Dew Point
    dati = requests.get("https://api.open-meteo.com/v1/forecast", params={
        "latitude": LAT, "longitude": LON,
        "hourly": "temperature_2m,relative_humidity_2m,dew_point_2m,precipitation,cloud_cover,wind_speed_10m,wind_gusts_10m",
        "daily": "temperature_2m_max,temperature_2m_min",
        "models": "icon_d2",
        "timezone": "Europe/Rome", "forecast_days": 2
    }).json()
    
    # Fetch EPS (Ensemble) per la precipitazione massima probabile
    dati_eps = requests.get("https://ensemble-api.open-meteo.com/v1/ensemble", params={
        "latitude": LAT, "longitude": LON,
        "hourly": "precipitation",
        "models": "icon_d2",
        "timezone": "Europe/Rome", "forecast_days": 2
    }).json()

    # Prepara info giornaliere sicure
    daily = dati.get('daily', {})
    info_giornaliere = f"""
    {datetime.now().strftime("%A %d %B")}: Min {daily.get('temperature_2m_min', ['N/A'])[0]}°C, Max {daily.get('temperature_2m_max', ['N/A'])[0]}°C
    {(datetime.now() + timedelta(days=1)).strftime("%A %d %B")}: Min {daily.get('temperature_2m_min', ['N/A', 'N/A'])[1]}°C, Max {daily.get('temperature_2m_max', ['N/A', 'N/A'])[1]}°C
    """

    # Prepara tabella oraria
    report = "Ora | T | UR% | Dew | Prec.D2 | EPS-Max | Vento | Raffica\n"
    hourly = dati.get('hourly', {})
    orari = hourly.get('time', [])
    
    for i in range(48): 
        if i >= len(orari): break
        
        # Estrazione EPS massima
        eps_vals = [dati_eps['hourly'].get(f"precipitation_member{m:02d}", [0]*48)[i] or 0 for m in range(1,21)]
        eps_max = max(eps_vals) if eps_vals else 0.0
            
        t = hourly.get('temperature_2m', [0]*48)[i]
        ur = hourly.get('relative_humidity_2m', [0]*48)[i]
        dew = hourly.get('dew_point_2m', [0]*48)[i]
        p_d2 = hourly.get('precipitation', [0]*48)[i] or 0
        v_vel = hourly.get('wind_speed_10m', [0]*48)[i]
        v_raf = hourly.get('wind_gusts_10m', [0]*48)[i]
        
        report += f"{orari[i][-5:]} | {t}°C | {ur}% | {dew}°C | {p_d2} | {eps_max:.1f} | {v_vel}km/h | {v_raf}km/h\n"

    # Invia a Gemini e poi a Telegram
    bollettino = interpella_gemini(report, info_giornaliere)
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if token and chat_id:
        risposta_tg = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", 
                      data={"chat_id": chat_id, "text": bollettino, "parse_mode": "Markdown"})
        
        if risposta_tg.status_code == 200:
            print("Bollettino inviato con successo al canale!")
        else:
            print(f"ERRORE TELEGRAM - Codice: {risposta_tg.status_code}")
            print(f"Motivo esatto: {risposta_tg.text}")
            print("\n--- TESTO CHE HA CAUSATO L'ERRORE ---\n")
            print(bollettino)
    else:
        print("Errore: Non trovo i Secrets (Token o Chat ID)!")

if __name__ == "__main__":
    main()
