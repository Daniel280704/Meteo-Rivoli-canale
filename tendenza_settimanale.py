#!/usr/bin/env python3
import os
import requests
import google.generativeai as genai
from datetime import datetime, timedelta

LAT = 45.073443
LON = 7.543472

# Dizionari per forzare l'italiano senza dipendere dal sistema operativo
GIORNI_IT = {0: "lunedì", 1: "martedì", 2: "mercoledì", 3: "giovedì", 4: "venerdì", 5: "sabato", 6: "domenica"}
MESI_IT = {1: "gennaio", 2: "febbraio", 3: "marzo", 4: "aprile", 5: "maggio", 6: "giugno", 
           7: "luglio", 8: "agosto", 9: "settembre", 10: "ottobre", 11: "novembre", 12: "dicembre"}

def formatta_data_it(dt):
    giorno_sett = GIORNI_IT[dt.weekday()]
    mese = MESI_IT[dt.month]
    return f"{giorno_sett} {dt.day} {mese}"

def interpella_gemini(dati_tendenza):
    api_key = os.getenv("GEMINI_API_KEY")
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('models/gemini-3-flash-preview')    

    prompt = f"""
    Sei un meteorologo professionista. Scrivi una PANORAMICA SINTETICA (tendenza meteo a medio termine) per Rivoli (TO) per i tre giorni successivi indicati in tabella.
    
    REGOLE DI SCRITTURA (TENDENZA SETTIMANALE):
    1. NON usare elenchi puntati. Struttura il testo in ESATTAMENTE TRE brevi paragrafi separati, dedicando un paragrafo a ciascuna giornata indicata. Non inserire alcun titolo o sottotitolo, inizia direttamente con il testo.
    2. Descrizione giornaliera: fai una cronaca fluida, sintetica ma completa per il giorno in esame, nominando chiaramente la giornata all'inizio del rispettivo paragrafo (es. "Martedì il cielo si presenterà in prevalenza sereno con massime fino a 30 gradi...").
    
    REGOLA NUVOLOSITÀ:
    3. Integra lo stato del 'Cielo' fornito nella tabella in modo discorsivo.
    
    REGOLA PRECIPITAZIONI E STAGIONALITÀ (CRITICA):
    4. Analizza 'Probabilità Pioggia'. Se indica 'Assente', IGNORA TOTALMENTE il tema della pioggia per quel periodo.
       - Se presente, menziona la FASCIA ORARIA indicata nei dati (es. "specialmente nel pomeriggio").
       - Tra MARZO e OTTOBRE usa "rovesci" o "temporali".
       - Tra NOVEMBRE e FEBBRAIO usa "piogge" o "precipitazioni" (vietato parlare di temporali).
       
    REGOLE DI DISAGIO TERMICO E WIND CHILL (SINTESI):
    5. Se la tabella indica "disagio termico moderato" o "forte disagio termico", inserisci l'informazione in modo naturale (es. "...con punte di 33 gradi che porteranno un forte disagio termico"). Non inventare spiegazioni fisiologiche.
    6. Se la tabella indica "freddo pungente", descrivi le nottate/mattinate rigide a causa del vento.

    DIVIETO ASSOLUTO SUI TERMINI TECNICI E SULLE PARENTESI:
    7. È severamente VIETATO menzionare i nomi delle colonne ("T.Min", "T.Max", "Probabilità").
    8. NON racchiudere MAI il livello di disagio termico tra parentesi nel discorso finale, rendilo parte integrante della frase.

    DATI SINTETICI GIORNALIERI:
    {dati_tendenza}
    """

    try:
        response = model.generate_content(prompt, generation_config={"temperature": 0.4})
        return response.text.strip()
    except Exception as e:
        return f"Errore AI: {e}"

def estrai_membri(daily_data, prefisso_variabile, indice_giorno):
    valori = []
    for key, array_vals in daily_data.items():
        if key.startswith(prefisso_variabile):
            if indice_giorno < len(array_vals) and array_vals[indice_giorno] is not None:
                valori.append(array_vals[indice_giorno])
    return valori

def main():
    # 1. Dati orari deterministici (Dew Point, Vento, Precipitazioni e Sunshine)
    dati_det = requests.get("https://api.open-meteo.com/v1/forecast", params={
        "latitude": LAT, "longitude": LON,
        "hourly": "temperature_2m,dew_point_2m,wind_speed_10m,precipitation,sunshine_duration,is_day",
        "models": "icon_seamless",
        "timezone": "Europe/Rome", "forecast_days": 6
    }).json()

    # 2. Dati Ensemble Giornalieri
    dati_eps = requests.get("https://ensemble-api.open-meteo.com/v1/ensemble", params={
        "latitude": LAT, "longitude": LON,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max",
        "models": "icon_seamless",
        "timezone": "Europe/Rome", "forecast_days": 6
    }).json()

    daily = dati_eps.get('daily', {})
    date_array = daily.get('time', [])
    
    hourly_det = dati_det.get('hourly', {})
    h_temp = hourly_det.get('temperature_2m', [])
    h_dew = hourly_det.get('dew_point_2m', [])
    h_wind = hourly_det.get('wind_speed_10m', [])
    h_prec = hourly_det.get('precipitation', [])
    h_sun = hourly_det.get('sunshine_duration', [])
    h_is_day = hourly_det.get('is_day', [])

    report = "Giorno | Cielo | T.Min | T.Max | Probabilità Pioggia | Vento Max\n"

    is_summer = 5 <= datetime.now().month <= 10

    # Scansione dei soli 3 giorni successivi a oggi e domani (indici 2, 3 e 4)
    for i in range(2, 5): 
        if i >= len(date_array): break
        
        data_obj = datetime.strptime(date_array[i], "%Y-%m-%d")
        giorno_str = formatta_data_it(data_obj)
        
        # --- CALCOLO MEDIE TEMPERATURE E VENTO ENSEMBLE ---
        t_min_mem = estrai_membri(daily, "temperature_2m_min_member", i)
        t_max_mem = estrai_membri(daily, "temperature_2m_max_member", i)
        vento_mem = estrai_membri(daily, "wind_speed_10m_max_member", i)
        
        t_min_avg = round(sum(t_min_mem) / len(t_min_mem)) if t_min_mem else 0
        t_max_avg = round(sum(t_max_mem) / len(t_max_mem)) if t_max_mem else 0
        vento_avg = round(sum(vento_mem) / len(vento_mem)) if vento_mem else 0

        # --- CALCOLO PROBABILITÀ PIOGGIA ENSEMBLE ---
        prec_mem = estrai_membri(daily, "precipitation_sum_member", i)
        
        p1 = (sum(1 for v in prec_mem if v >= 1) / len(prec_mem) * 100) if prec_mem else 0
        p3 = (sum(1 for v in prec_mem if v >= 3) / len(prec_mem) * 100) if prec_mem else 0
        p5 = (sum(1 for v in prec_mem if v >= 5) / len(prec_mem) * 100) if prec_mem else 0

        prob_str = "Assente"
        if p1 >= 10:
            def livello(p):
                if p >= 30: return "Serio rischio"
                if p >= 20: return "Probabile"
                return "Minima possibilità"

            if p5 >= 10: prob_str = f"{livello(p5)} pioggia intensa o instabilità diffusa"
            elif p3 >= 10: prob_str = f"{livello(p3)} pioggia moderata o instabilità sparsa"
            else: prob_str = f"{livello(p1)} pioggia debole o instabilità isolata"

        # --- MOTORE SCANSIONE ORARIA (Cielo, Timing Pioggia, Disagi) ---
        disagio_score_max = 0
        wind_chill_flag = False
        
        daylight_hours = 0
        sunshine_sec = 0
        prec_fasce = {"nella notte": 0, "al mattino": 0, "nel pomeriggio": 0, "in serata": 0}
        
        start_hour = i * 24
        end_hour = start_hour + 24
        
        for h in range(start_hour, end_hour):
            if h < len(h_temp):
                t_val = h_temp[h]
                d_val = h_dew[h] if h < len(h_dew) else None
                w_val = h_wind[h] if h < len(h_wind) else None
                p_val = h_prec[h] if h < len(h_prec) and h_prec[h] is not None else 0
                sun_val = h_sun[h] if h < len(h_sun) and h_sun[h] is not None else 0
                is_day_val = h_is_day[h] if h < len(h_is_day) and h_is_day[h] is not None else 0
                
                # Valutazione Disagio Termico Estivo e Wind Chill
                if t_val is not None and d_val is not None:
                    d_score = 0
                    if (t_val >= 32 and d_val >= 20) or (t_val >= 30 and d_val >= 24): d_score = 2
                    elif (t_val >= 28 and d_val >= 15) or (t_val >= 25 and d_val >= 20): d_score = 1
                    disagio_score_max = max(disagio_score_max, d_score)
                
                if t_val is not None and w_val is not None:
                    if t_val <= 8 and w_val >= 15:
                        wind_chill_flag = True

                # Fasce orarie delle precipitazioni
                ora_giorno = h % 24
                if 0 <= ora_giorno < 6: prec_fasce["nella notte"] += p_val
                elif 6 <= ora_giorno < 12: prec_fasce["al mattino"] += p_val
                elif 12 <= ora_giorno < 18: prec_fasce["nel pomeriggio"] += p_val
                else: prec_fasce["in serata"] += p_val
                
                # Logica Rigorosa Sunshine con Filtro Crepuscolare (+/- 2 ore)
                is_twilight = False
                if is_day_val == 1:
                    for offset in [-2, -1, 1, 2]:
                        idx = h + offset
                        if 0 <= idx < len(h_is_day) and h_is_day[idx] == 0:
                            is_twilight = True
                            break
                
                # Accumuliamo il soleggiamento SOLO nel "Deep Day"
                if is_day_val == 1 and not is_twilight:
                    daylight_hours += 1
                    sunshine_sec += sun_val

        # --- DETERMINAZIONE STATO DEL CIELO GLOBALE GIORNALIERO ---
        if daylight_hours > 0:
            sun_pct = (sunshine_sec / (daylight_hours * 3600)) * 100
            if sun_pct >= 80: cielo_str = "In prevalenza sereno"
            elif sun_pct >= 50: cielo_str = "Parzialmente nuvoloso"
            elif sun_pct >= 20: cielo_str = "Da parzialmente a irregolarmente nuvoloso"
            elif sun_pct >= 5: cielo_str = "Irregolarmente nuvoloso"
            else: cielo_str = "Coperto"
        else:
            cielo_str = "Molto nuvoloso"

        # --- AGGIUNTA TIMING ALLA PIOGGIA ---
        if prob_str != "Assente":
            max_fascia = max(prec_fasce, key=prec_fasce.get)
            if prec_fasce[max_fascia] > 0:
                prob_str += f" specialmente {max_fascia}"

        # --- FORMATTAZIONE TESTUALE DEI DISAGI ---
        def formatta_disagio(score):
            if score == 2: return ", forte disagio termico 🔴" if is_summer else ""
            if score == 1: return ", disagio termico moderato 🟠" if is_summer else ""
            return ""
            
        str_disagio = formatta_disagio(disagio_score_max)
        str_wc = ", freddo pungente causa vento" if wind_chill_flag else ""

        report += f"{giorno_str} | {cielo_str} | Min {t_min_avg}°C{str_wc} | Max {t_max_avg}°C{str_disagio} | {prob_str} | {vento_avg} km/h\n"

    # Generazione testo AI
    testo_tendenza = interpella_gemini(report)
    
    # Formattazione finale del messaggio con il Titolo e la riga vuota
    messaggio_finale = f"**Aggiornamento meteo a medio termine**\n\n{testo_tendenza}"
    
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
