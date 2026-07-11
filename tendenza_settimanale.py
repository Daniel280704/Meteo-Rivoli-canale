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

LAT = 45.073443
LON = 7.543472

def interpella_gemini(dati_tendenza):
    api_key = os.getenv("GEMINI_API_KEY")
    genai.configure(api_key=api_key)
    # Modello con limiti ampi per gestire la tendenza
    model = genai.GenerativeModel('models/gemini-3-flash-preview')    

    oggi = datetime.now()
    
    prompt = f"""
    Sei un meteorologo professionista. Scrivi una PANORAMICA SINTETICA (tendenza meteo) per Rivoli (TO) per i prossimi giorni.
    Oggi è {oggi.strftime("%A %d %B")}. Il bollettino deve coprire ESCLUSIVAMENTE i giorni indicati nella tabella sottostante.
    
    REGOLE DI SCRITTURA (TENDENZA SETTIMANALE):
    1. NON usare elenchi puntati. Scrivi un singolo paragrafo fluido, sintetico e professionale, ideale per l'inizio della settimana.
    2. Unisci i concetti: non fare la cronaca meccanica giorno per giorno, ma raggruppa le tendenze (es. "tra mercoledì e giovedì avremo una fase stabile, mentre da venerdì le temperature caleranno...").
    
    REGOLA PRECIPITAZIONI E STAGIONALITÀ (CRITICA):
    3. Se i dati indicano precipitazioni (>0):
       - Tra MARZO e OTTOBRE: parla di rischio "rovesci" o "temporali".
       - Tra NOVEMBRE e FEBBRAIO: parla solo di "piogge" o "precipitazioni" (vietato parlare di temporali).
       
    REGOLE DI DISAGIO TERMICO E NEVE (SINTESI):
    4. Se la T.Max Media supera i 30°C, accenna a un possibile aumento dell'afa e del disagio termico nelle ore centrali.
    5. Se la T.Min Media scende sotto o vicino allo zero (<= 2°C), avvisa del rischio di gelate o, in caso di precipitazioni previste, di fiocchi a bassa quota.

    DIVIETO ASSOLUTO SUI TERMINI TECNICI:
    6. È severamente VIETATO menzionare i nomi delle colonne ("T.Min", "T.Max", "Prec"). L'utente non deve MAI leggere questi acronimi. Traduci i numeri in un discorso naturale.

    DATI SINTETICI GIORNALIERI (Basati sulla Media degli Scenari Ensemble CH2):
    {dati_tendenza}
    """

    try:
        response = model.generate_content(prompt, generation_config={"temperature": 0.4})
        return response.text
    except Exception as e:
        return f"Errore AI: {e}"

def main():
    # Interroghiamo l'API ENSEMBLE puntando specificamente a ICON-CH2 EPS
    url = "https://ensemble-api.open-meteo.com/v1/ensemble"
    params = {
        "latitude": LAT, 
        "longitude": LON,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max",
        "models": "meteoswiss_icon_ch2_ensemble",
        "timezone": "Europe/Rome", 
        "forecast_days": 5 # 5 giorni: i primi 2 li saltiamo, usiamo i restanti 3
    }
    
    dati = requests.get(url, params=params).json()
    daily = dati.get('daily', {})
    date_array = daily.get('time', [])
    
    # Funzione che calcola la media matematica di tutti gli "spaghi" CH2
    def calcola_media_ens(base_var, index):
        valori = []
        for key, array_vals in daily.items():
            if key.startswith(f"{base_var}_member"):
                val = array_vals[index]
                if val is not None:
                    valori.append(val)
        if valori:
            return sum(valori) / len(valori)
        return 0.0

    report = "Giorno | T.Min Media | T.Max Media | Prec. Media | Vento Max Medio\n"
    
    # Il ciclo parte da 2 e arriva fino a 5 esclusi (quindi indici 2, 3 e 4), che sono i 3 giorni finali
    for i in range(2, 5): 
        if i >= len(date_array): break
        
        data_obj = datetime.strptime(date_array[i], "%Y-%m-%d")
        giorno_str = data_obj.strftime("%A %d %B")
        
        t_min_avg = calcola_media_ens("temperature_2m_min", i)
        t_max_avg = calcola_media_ens("temperature_2m_max", i)
        prec_avg = calcola_media_ens("precipitation_sum", i)
        vento_avg = calcola_media_ens("wind_speed_10m_max", i)
        
        report += f"{giorno_str} | {t_min_avg:.1f}°C | {t_max_avg:.1f}°C | {prec_avg:.1f} mm | {vento_avg:.1f} km/h\n"

    tendenza = interpella_gemini(report)
    
    # Aggiungo un titolo in grassetto
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
