#!/usr/bin/env python3
import os
import requests
import google.generativeai as genai
from datetime import datetime, timedelta
import locale

# Imposta la lingua italiana per i giorni della settimana
try:
    locale.setlocale(locale.LC_TIME, 'it_IT.UTF-8')
except:
    pass

LAT = 45.1384
LON = 7.7684

def interpella_gemini(dati_tendenza):
    api_key = os.getenv("GEMINI_API_KEY")
    genai.configure(api_key=api_key)
    # Usiamo il modello con limiti ampi, perfetto per i riassunti
    model = genai.GenerativeModel('models/gemini-3-flash-preview')    

    oggi = datetime.now()
    
    prompt = f"""
    Sei un meteorologo professionista. Scrivi una PANORAMICA SINTETICA (tendenza meteo) per Settimo Torinese (TO) per i prossimi giorni.
    Oggi è {oggi.strftime("%A %d %B")}. Il bollettino deve coprire ESCLUSIVAMENTE i giorni indicati nella tabella sottostante.
    
    REGOLE DI SCRITTURA (TENDENZA SETTIMANALE):
    1. NON usare elenchi puntati. Scrivi un singolo paragrafo fluido, sintetico e professionale, ideale per l'inizio della settimana.
    2. Unisci i concetti: non fare la cronaca meccanica giorno per giorno, ma raggruppa le tendenze (es. "tra mercoledì e giovedì avremo una fase stabile, mentre da venerdì le temperature caleranno...").
    
    REGOLA PRECIPITAZIONI E STAGIONALITÀ (CRITICA):
    3. Se i dati indicano precipitazioni (>0):
       - Tra MARZO e OTTOBRE: parla di rischio "rovesci" o "temporali".
       - Tra NOVEMBRE e FEBBRAIO: parla solo di "piogge" o "precipitazioni" (vietato parlare di temporali).
       
    REGOLE DI DISAGIO TERMICO E NEVE (SINTESI):
    4. Se la T.Max supera i 30°C, accenna a un possibile aumento dell'afa e del disagio termico nelle ore centrali.
    5. Se la T.Min scende sotto o vicino allo zero (<= 2°C), avvisa del rischio di gelate o, in caso di precipitazioni previste, di fiocchi a bassa quota.

    DIVIETO ASSOLUTO SUI TERMINI TECNICI:
    6. È severamente VIETATO menzionare i nomi delle colonne ("T.Min", "T.Max", "Prec"). L'utente non deve MAI leggere questi acronimi. Traduci i numeri in un discorso naturale (es. "le massime sfioreranno i 35 gradi", "accumuli pluviometrici").

    DATI SINTETICI GIORNALIERI (Usa ESCLUSIVAMENTE questi per la tendenza):
    {dati_tendenza}
    """

    try:
        response = model.generate_content(prompt, generation_config={"temperature": 0.4})
        return response.text
    except Exception as e:
        return f"Errore AI: {e}"

def main():
    # Usiamo icon_seamless che unisce in automatico ICON-D2, ICON-EU e ICON-CH2
    dati = requests.get("https://api.open-meteo.com/v1/forecast", params={
        "latitude": LAT, "longitude": LON,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max",
        "models": "icon_seamless",
        "timezone": "Europe/Rome", 
        "forecast_days": 6
    }).json()
    
    daily = dati.get('daily', {})
    date_array = daily.get('time', [])
    
    report = "Giorno | T.Min | T.Max | Prec. Totali | Vento Max\n"
    
    # Il ciclo parte da 2 per saltare Oggi (0) e Domani (1) già coperti dal bollettino giornaliero
    for i in range(2, 6): 
        if i >= len(date_array): break
        
        data_obj = datetime.strptime(date_array[i], "%Y-%m-%d")
        giorno_str = data_obj.strftime("%A %d %B")
        
        t_min = daily.get('temperature_2m_min', [0]*6)[i]
        t_max = daily.get('temperature_2m_max', [0]*6)[i]
        prec = daily.get('precipitation_sum', [0]*6)[i]
        vento = daily.get('wind_speed_10m_max', [0]*6)[i]
        
        report += f"{giorno_str} | {t_min}°C | {t_max}°C | {prec} mm | {vento} km/h\n"

    tendenza = interpella_gemini(report)
    
    # Aggiungo un titolo in grassetto per distinguerlo sul canale
    messaggio_finale = f"📅 **TENDENZA METEO SETTIMANALE**\n\n{tendenza}"
    
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if token and chat_id:
        risposta_tg = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", 
                      data={"chat_id": chat_id, "text": messaggio_finale, "parse_mode": "Markdown"})
        
        if risposta_tg.status_code == 200:
            print("Tendenza settimanale inviata con successo al canale!")
        else:
            print(f"ERRORE TELEGRAM: {risposta_tg.text}")
    else:
        print("Errore: Token o Chat ID mancanti.")

if __name__ == "__main__":
    main()