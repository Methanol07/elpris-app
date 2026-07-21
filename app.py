import os
import requests
from datetime import datetime, timedelta
from flask import Flask, render_template_string, request

app = Flask(__name__)

def hent_priser_for_dato_og_omraade(dato_dt, price_area):
    aar = dato_dt.strftime('%Y')
    maaned = dato_dt.strftime('%m')
    dag = dato_dt.strftime('%d')
    url = f"https://www.elprisenligenu.dk/api/v1/prices/{aar}/{maaned}-{dag}_{price_area}.json"
    
    try:
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        print(f"Fejl ved hentning af {url}: {e}")
    return []

def hent_samlet_dagsdata(dato_dt):
    data_dk1 = hent_priser_for_dato_og_omraade(dato_dt, "DK1")
    data_dk2 = hent_priser_for_dato_og_omraade(dato_dt, "DK2")
    
    formatted = {}
    for item in data_dk1:
        time_start = item.get('time_start', '')[:16]
        raw_price = item.get('DKK_per_kWh')
        if raw_price is not None:
            formatted[time_start] = {"time_start": time_start, "price_dk1": round(raw_price * 1.25, 2), "price_dk2": None}

    for item in data_dk2:
        time_start = item.get('time_start', '')[:16]
        raw_price = item.get('DKK_per_kWh')
        if raw_price is not None:
            if time_start not in formatted:
                formatted[time_start] = {"time_start": time_start, "price_dk1": None, "price_dk2": round(raw_price * 1.25, 2)}
            else:
                formatted[time_start]["price_dk2"] = round(raw_price * 1.25, 2)

    res = list(formatted.values())
    res.sort(key=lambda x: x['time_start'])
    return res

def beregn_vejr_prognose(dato_dt):
    """Henter vejrudsigten fra Open-Meteo og estimerer elprisen ud fra vind og sol."""
    # Koordinater for Danmark (ca. Midtjylland)
    lat, lon = 56.0, 10.0
    dato_str = dato_dt.strftime('%Y-%m-%d')
    
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=windspeed_10m,direct_radiation&start_date={dato_str}&end_date={dato_str}&timezone=Europe%2FCopenhagen"
    
    prognose_timer = []
    try:
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            data = res.json().get('hourly', {})
            tider = data.get('time', [])
            vinde = data.get('windspeed_10m', [])
            soler = data.get('direct_radiation', [])
            
            for i in range(len(tider)):
                time_iso = tider[i] # YYYY-MM-DDTHH:00
                time_dt = datetime.strptime(time_iso, '%Y-%m-%dT%H:%00')
                time_hour = time_dt.hour
                
                vind = vinde[i] if i < len(vinde) else 15
                sol = soler[i] if i < len(soler) else 0
                
                # Basis elpris inkl moms (1,20 kr)
                estimeret_pris = 1.20
                
                # 1. Vindeffekt (Mere vind = lavere pris)
                if vind > 35:
                    estimeret_pris -= 0.45  # Kraftig blæst
                elif vind > 25:
                    estimeret_pris -= 0.25  # God vind
                elif vind < 10:
                    estimeret_pris += 0.35  # Vindstille
                    
                # 2. Soleffekt (Solcelleproduktion midt på dagen)
                if sol > 300 and 10 <= time_hour <= 16:
                    estimeret_pris -= 0.20
                    
                # 3. Forbrugsmønster (Kogetoppe & morgen/aften)
                if 17 <= time_hour <= 20:
                    estimeret_pris += 0.40  # Aftenspids
                elif 7 <= time_hour <= 9:
                    estimeret_pris += 0.20  # Morgenspids
                elif 0 <= time_hour <= 5:
                    estimeret_pris -= 0.20  # Natrabat
                    
                estimeret_pris = max(0.10, round(estimeret_pris, 2))
                
                prognose_timer.append({
                    "time_start": time_iso,
                    "price_dk1": estimeret_pris,
                    "price_dk2": estimeret_pris,
                    "vind": round(vind, 1),
                    "is_forecast": True
                })
    except Exception as e:
        print(f"Vejr API fejl: {e}")
        
    return prognose_timer

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="da">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>⚡ Elpriser & Vejrprognose</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 20px 15px; display: flex; justify-content: center; }
        .container { max-width: 680px; width: 100%; }
        h1 { text-align: center; color: #38bdf8; margin-bottom: 4px; }
        p.subtitle { text-align: center; color: #94a3b8; margin-bottom: 20px; font-size: 0.9rem; }
        
        .date-selector { display: flex; gap: 8px; justify-content: center; margin-bottom: 20px; flex-wrap: wrap; }
        .date-btn { padding: 10px 14px; background: #1e293b; color: #94a3b8; border: 1px solid #334155; border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 0.85rem; }
        .date-btn:hover { background: #334155; color: white; }
        .date-btn.active { background: #0284c7; color: white; border-color: #38bdf8; }
        .date-btn.forecast { border-color: #f59e0b; color: #fbbf24; }
        .date-btn.forecast.active { background: #d97706; color: white; }
        
        table { width: 100%; border-collapse: collapse; background: #1e293b; border-radius: 12px; overflow: hidden; }
        th, td { padding: 10px 12px; text-align: center; font-size: 0.9rem; }
        th { background: #334155; color: #94a3b8; }
        tr { border-bottom: 1px solid #334155; }
        
        .price-cheap { color: #4ade80; font-weight: bold; }
        .price-mid { color: #facc15; font-weight: bold; }
        .price-high { color: #f87171; font-weight: bold; }
        
        .badge-forecast { background: #78350f; color: #fef3c7; padding: 2px 6px; border-radius: 4px; font-size: 0.75rem; margin-left: 4px; }
        .no-data { text-align: center; padding: 30px; background: #1e293b; border-radius: 12px; color: #94a3b8; line-height: 1.5; }
        .attribution { text-align: center; margin-top: 25px; font-size: 0.8rem; color: #64748b; }
        .attribution a { color: #38bdf8; text-decoration: none; }
    </style>
</head>
<body>
    <div class="container">
        <h1>⚡ Elpriser & Prognose</h1>
        <p class="subtitle">Spotpriser inkl. moms i DKK/kWh</p>
        
        <div class="date-selector">
            {% for d in dags_knapper %}
            <a href="/?offset={{ d.offset }}" class="date-btn {% if d.is_forecast %}forecast{% endif %} {% if valgt_offset == d.offset %}active{% endif %}">
                {{ d.label }} ({{ d.dato_str }})
            </a>
            {% endfor %}
        </div>

        {% if priser %}
        <table>
            <thead>
                <tr>
                    <th>Tidspunkt</th>
                    <th>DK1 (Jylland/Fyn)</th>
                    <th>DK2 (Sjælland)</th>
                    {% if er_prognose %}<th>Forventet Vind</th>{% endif %}
                </tr>
            </thead>
            <tbody>
                {% for row in priser %}
                <tr>
                    <td style="color:#94a3b8;">{{ row.time_start.replace('T', ' kl. ') }}</td>
                    <td class="{% if row.price_dk1 is not none %}{% if row.price_dk1 < 1.0 %}price-cheap{% elif row.price_dk1 < 2.0 %}price-mid{% else %}price-high{% endif %}{% endif %}">
                        {{ row.price_dk1 if row.price_dk1 is not none else '-' }} kr.
                        {% if er_prognose %}<span class="badge-forecast">Est.</span>{% endif %}
                    </td>
                    <td class="{% if row.price_dk2 is not none %}{% if row.price_dk2 < 1.0 %}price-cheap{% elif row.price_dk2 < 2.0 %}price-mid{% else %}price-high{% endif %}{% endif %}">
                        {{ row.price_dk2 if row.price_dk2 is not none else '-' }} kr.
                        {% if er_prognose %}<span class="badge-forecast">Est.</span>{% endif %}
                    </td>
                    {% if er_prognose %}
                    <td style="color:#60a5fa;">💨 {{ row.vind }} km/t</td>
                    {% endif %}
                </tr>
                {% endfor %}
            </tbody>
        </table>
        {% else %}
        <div class="no-data">
            ℹ️ Ingen data fundet for <b>{{ mål_dato }}</b> endnu.
        </div>
        {% endif %}

        <div class="attribution">
            Priser fra <a href="https://www.elprisenligenu.dk" target="_blank">Elprisen lige nu</a> | Vejr fra <a href="https://open-meteo.com/" target="_blank">Open-Meteo</a>
        </div>
    </div>
</body>
</html>
"""

@app.route('/', methods=['GET'])
def dashboard():
    try:
        offset = int(request.args.get('offset', 0))
    except ValueError:
        offset = 0

    idag = datetime.now()
    valgt_dato = idag + timedelta(days=offset)
    mål_dato_str = valgt_dato.strftime('%Y-%m-%d')
    
    dags_knapper = []
    labels = ["I dag", "I morgen", "🔮 +2 Dage (Prognose)"]
    for i in range(3):
        d = idag + timedelta(days=i)
        lbl = labels[i] if i < len(labels) else f"+{i} dage"
        dags_knapper.append({
            'offset': i,
            'label': lbl,
            'dato_str': d.strftime('%d/%m'),
            'is_forecast': (i == 2)
        })
        
    er_prognose = (offset == 2)
    
    if er_prognose:
        # Hvis der er valgt +2 dage, beregner vi ud fra vejret
        data = beregn_vejr_prognose(valgt_dato)
    else:
        # Ellers henter vi rigtige spottal
        data = hent_samlet_dagsdata(valgt_dato)
    
    return render_template_string(
        HTML_TEMPLATE,
        priser=data,
        valgt_offset=offset,
        dags_knapper=dags_knapper,
        mål_dato=mål_dato_str,
        er_prognose=er_prognose
    )

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)