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
    model = genai.GenerativeModel('models/gemini-3.5-flash')
    
    oggi_str = datetime.now().strftime("%A %d %B")
    domani_str = (datetime.now() + timedelta(days=1)).strftime("%A %d %B")
    
    prompt = f"""
    Sei un meteorologo professionista. Scrivi un bollettino meteo discorsivo per Rivoli (TO) per le prossime 48 ore.
    Oggi è {oggi_str}, domani sarà {domani_str}.
    
    RIFERIMENTI UFFICIALI (Usa questi valori per le temperature min/max):
    {info_giornaliere}

    REGOLE DI SCRITTURA (BOLLETTINO 4 STAGIONI):
    1. NON usare elenchi puntati. Scrivi paragrafi fluidi (es. "La giornata di [Giorno] comincerà con...").
    2. Usa le temperature min/max fornite nei riferimenti ufficiali come base della narrazione.
    3. Focalizzati su nuvolosità, vento/raffiche e rischio precipitazioni basandoti sui dati orari.
    4. REGOLA NEBBIA/BRINA: Valuta autonomamente il rischio incrociando Temperatura, UR% e Dew Point (Punto di rugiada). Menziona possibili foschie, nebbie o brinate SOLO se le condizioni fisiche lo suggeriscono fortemente (es. aria stagnante, T notturna vicina allo 0°C, UR > 90% e T vicina al Dew Point). Se le condizioni non ci sono (es. estate, aria secca o ventilazione), non nominarli affatto e non dare giustificazioni.
    5. REGOLA DISAGIO TERMICO: Valuta lo stress termico per il corpo umano. In estate (T > 30°C), incrocia Temperatura e Dew Point per segnalare eventuale afa o marcato disagio da caldo. In inverno (T < 10°C), incrocia Temperatura e Vento per segnalare freddo acuito (Wind Chill). Se i valori rientrano in un normale comfort termico, non menzionare nulla.
    
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
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage", 
                      data={"chat_id": chat_id, "text": bollettino, "parse_mode": "Markdown"})
        print("Bollettino inviato con successo.")
    else:
        print("\n--- ANTEPRIMA BOLLETTINO ---\n")
        print(bollettino)

if __name__ == "__main__":
    main()
