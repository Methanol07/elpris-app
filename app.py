import os
import time
import requests
from datetime import datetime, timedelta
from flask import Flask, render_template_string, request

app = Flask(__name__)

CACHE_DATA = None
CACHE_TIME = 0

def hent_spotpriser():
    global CACHE_DATA, CACHE_TIME
    
    nu = time.time()
    # 1. Gem i cache i 5 minutter hvis vi har data
    if CACHE_DATA and len(CACHE_DATA) > 0 and (nu - CACHE_TIME) < 300:
        return CACHE_DATA

    headers = {'User-Agent': 'MinElprisApp/1.0'}
    api_url = 'https://api.energidataservice.dk/dataset/Elspotprices?limit=100&sort=HourDK desc'
    
    print(f"--- KALDER API: {api_url} ---")
    
    formatted = {}
    try:
        # Sæt timeout lavt (3 sek), så siden ikke hænger eller viser blank skærm
        res = requests.get(api_url, headers=headers, timeout=3)
        print(f"--- API STATUS KODE: {res.status_code} ---")
        
        if res.status_code == 200:
            records = res.json().get('records', [])
            for item in records:
                time_start = item.get('HourDK', '')
                area = item.get('PriceArea')
                spot_eur = item.get('SpotPriceEUR')
                
                if spot_eur is None or not time_start or area not in ["DK1", "DK2"]:
                    continue
                    
                price_dkk = round(((spot_eur * 7.45) / 1000) * 1.25, 2)
                
                if time_start not in formatted:
                    formatted[time_start] = {"time_start": time_start, "price_dk1": None, "price_dk2": None}
                
                if area == "DK1":
                    formatted[time_start]["price_dk1"] = price_dkk
                elif area == "DK2":
                    formatted[time_start]["price_dk2"] = price_dkk
            
            CACHE_DATA = list(formatted.values())
            CACHE_TIME = nu
            return CACHE_DATA
    except Exception as e:
        print(f"--- API FEJL / TIMEOUT: {e} ---")
        
    # Returner eksisterende cache hvis API svigter
    return CACHE_DATA or []

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="da">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>⚡ Elpriser Live</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 20px 15px; display: flex; justify-content: center; }
        .container { max-width: 650px; width: 100%; }
        h1 { text-align: center; color: #38bdf8; margin-bottom: 4px; }
        p.subtitle { text-align: center; color: #94a3b8; margin-bottom: 20px; font-size: 0.9rem; }
        
        .date-selector { display: flex; gap: 8px; justify-content: center; margin-bottom: 20px; flex-wrap: wrap; }
        .date-btn { padding: 10px 14px; background: #1e293b; color: #94a3b8; border: 1px solid #334155; border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 0.85rem; }
        .date-btn:hover { background: #334155; color: white; }
        .date-btn.active { background: #0284c7; color: white; border-color: #38bdf8; }
        
        table { width: 100%; border-collapse: collapse; background: #1e293b; border-radius: 12px; overflow: hidden; }
        th, td { padding: 10px 12px; text-align: center; font-size: 0.9rem; }
        th { background: #334155; color: #94a3b8; }
        tr { border-bottom: 1px solid #334155; }
        
        .price-cheap { color: #4ade80; font-weight: bold; }
        .price-mid { color: #facc15; font-weight: bold; }
        .price-high { color: #f87171; font-weight: bold; }
        
        .no-data { text-align: center; padding: 30px; background: #1e293b; border-radius: 12px; color: #94a3b8; line-height: 1.5; }
    </style>
</head>
<body>
    <div class="container">
        <h1>⚡ Elpriser Live</h1>
        <p class="subtitle">Spotpriser inkl. moms i DKK/kWh</p>
        
        <div class="date-selector">
            {% for d in dags_knapper %}
            <a href="/?offset={{ d.offset }}" class="date-btn {% if valgt_offset == d.offset %}active{% endif %}">
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
                </tr>
            </thead>
            <tbody>
                {% for row in priser %}
                <tr>
                    <td style="color:#94a3b8;">{{ str(row.time_start).replace('T', ' kl. ')[:16] }}</td>
                    <td class="{% if row.price_dk1 is not none %}{% if row.price_dk1 < 1.0 %}price-cheap{% elif row.price_dk1 < 2.0 %}price-mid{% else %}price-high{% endif %}{% endif %}">
                        {{ row.price_dk1 if row.price_dk1 is not none else '-' }} kr.
                    </td>
                    <td class="{% if row.price_dk2 is not none %}{% if row.price_dk2 < 1.0 %}price-cheap{% elif row.price_dk2 < 2.0 %}price-mid{% else %}price-high{% endif %}{% endif %}">
                        {{ row.price_dk2 if row.price_dk2 is not none else '-' }} kr.
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        {% else %}
        <div class="no-data">
            ℹ️ Ingen data tilgængelige lige nu. Prøv at genopfriske siden om et øjeblik.
        </div>
        {% endif %}
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
    labels = ["I dag", "I morgen"]
    for i in range(2):
        d = idag + timedelta(days=i)
        lbl = labels[i] if i < len(labels) else f"+{i} dage"
        dags_knapper.append({
            'offset': i,
            'label': lbl,
            'dato_str': d.strftime('%d/%m')
        })
        
    alle_data = hent_spotpriser()
    
    # Filtrer data på dato, hvis der er data – ellers vis hvad vi har
    data = [r for r in alle_data if str(r.get('time_start', '')).startswith(mål_dato_str)]
    if not data and alle_data:
        data = alle_data
        
    data.sort(key=lambda x: str(x.get('time_start', '')))
    
    return render_template_string(
        HTML_TEMPLATE,
        priser=data,
        valgt_offset=offset,
        dags_knapper=dags_knapper,
        mål_dato=mål_dato_str,
        str=str
    )

if __name__ == '__main__':
    # VIGTIGT: Hent porten direkte fra Renders miljøvariabler
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)