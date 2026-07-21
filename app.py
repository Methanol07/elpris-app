import time
import requests
from datetime import datetime, timedelta
from flask import Flask, render_template_string, request

app = Flask(__name__)

# Global cache variabler
CACHE_DATA = None
CACHE_TIME = 0
CACHE_DURATION = 600  # Gemmer data i 10 minutter (600 sekunder)

def hent_spotpriser():
    global CACHE_DATA, CACHE_TIME
    
    nu = time.time()
    # KUN brug cache hvis den indeholder REEL DATA
    if CACHE_DATA and len(CACHE_DATA) > 0 and (nu - CACHE_TIME) < CACHE_DURATION:
        print("--- BRUGER CACHED DATA ---")
        return CACHE_DATA

    headers = {
        'User-Agent': 'MinPrivateElprisApp/3.0 (kontakt@minelpris.dk)'
    }
    
    api_url = 'https://api.energidataservice.dk/dataset/Elspotprices?limit=200&sort=HourDK desc'
    print(f"--- KALDER API DOKUMENT: {api_url} ---")
    
    formatted = {}
    try:
        res = requests.get(api_url, headers=headers, timeout=10)
        print(f"--- API STATUS KODE: {res.status_code} ---")
        
        if res.status_code == 200:
            records = res.json().get('records', [])
            for item in records:
                time_start = item.get('HourDK', '')
                area = item.get('PriceArea')
                spot_eur = item.get('SpotPriceEUR')
                
                if spot_eur is None or not time_start:
                    continue
                    
                price_dkk = round((spot_eur * 7.45) / 1000, 2)
                
                if time_start not in formatted:
                    formatted[time_start] = {"time_start": time_start, "price_dk1": None, "price_dk2": None}
                
                if area == "DK1":
                    formatted[time_start]["price_dk1"] = price_dkk
                elif area == "DK2":
                    formatted[time_start]["price_dk2"] = price_dkk
            
            resultat = list(formatted.values())
            # GEM KUN I CACHE HVIS VI FIK TALLENE!
            if len(resultat) > 0:
                CACHE_DATA = resultat
                CACHE_TIME = nu
                print(f"--- SUCCES! GEMTE {len(resultat)} RÆKKER I CACHEN ---")
            else:
                print("--- ADVARSEL: Modtog 0 rækker fra API ---")
        else:
            print(f"--- ADVARSEL: Modtog statuskode {res.status_code} ---")
            
    except Exception as e:
        print(f"--- API FEJL: {e} ---")
        
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
        .date-btn.active { background: #0284c7; color: white; border-color: #38bdf8; }
        
        table { width: 100%; border-collapse: collapse; background: #1e293b; border-radius: 12px; overflow: hidden; }
        th, td { padding: 10px 12px; text-align: center; font-size: 0.9rem; }
        th { background: #334155; color: #94a3b8; }
        tr { border-bottom: 1px solid #334155; }
        
        .price-cheap { color: #4ade80; font-weight: bold; }
        .price-mid { color: #facc15; font-weight: bold; }
        .price-high { color: #f87171; font-weight: bold; }
        
        .no-data { text-align: center; padding: 30px; background: #1e293b; border-radius: 12px; color: #94a3b8; }
    </style>
</head>
<body>
    <div class="container">
        <h1>⚡ Elpriser Live</h1>
        <p class="subtitle">Direkte fra Energi Data Service</p>
        
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
                    <td style="color:#94a3b8;">{{ row.time_start.replace('T', ' kl. ')[:16] }}</td>
                    <td class="{% if row.price_dk1 is not none %}{% if row.price_dk1 < 0.8 %}price-cheap{% elif row.price_dk1 < 1.5 %}price-mid{% else %}price-high{% endif %}{% endif %}">
                        {{ row.price_dk1 if row.price_dk1 is not none else '-' }} kr.
                    </td>
                    <td class="{% if row.price_dk2 is not none %}{% if row.price_dk2 < 0.8 %}price-cheap{% elif row.price_dk2 < 1.5 %}price-mid{% else %}price-high{% endif %}{% endif %}">
                        {{ row.price_dk2 if row.price_dk2 is not none else '-' }} kr.
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        {% else %}
        <div class="no-data">
            ℹ️ Ingen data tilgængelige for datoen <b>{{ mål_dato }}</b> endnu.<br>
            <small>(Spotpriser udgives dagligt omkring kl. 13:00)</small>
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
    for i in range(4):
        d = idag + timedelta(days=i)
        lbl = labels[i] if i < len(labels) else f"+{i} dage"
        dags_knapper.append({
            'offset': i,
            'label': lbl,
            'dato_str': d.strftime('%d/%m')
        })
        
    alle_data = hent_spotpriser()
    
    # Filtrer på valgt dato
    data = [r for r in alle_data if str(r.get('time_start', '')).startswith(mål_dato_str)]
    data.sort(key=lambda x: str(x.get('time_start', '')))
    
    return render_template_string(
        HTML_TEMPLATE,
        priser=data,
        valgt_offset=offset,
        dags_knapper=dags_knapper,
        mål_dato=mål_dato_str
    )

if __name__ == '__main__':
    app.run(debug=True, port=5000)