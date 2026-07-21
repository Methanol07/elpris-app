import requests
from datetime import datetime, timedelta
from flask import Flask, render_template_string, request

app = Flask(__name__)

def hent_spotpriser():
    """Henter de seneste og nyeste spotpriser direkte fra Energi Data Service."""
    headers = {'User-Agent': 'MinElprisApp/1.0'}
    # Hent de seneste 100 rækker for DK1 og DK2 (dækker rigeligt i dag og i morgen)
    api_url = 'https://api.energidataservice.dk/dataset/Elspotprices?limit=100&filter={"PriceArea":["DK1","DK2"]}&sort=HourDK desc'
    
    formatted = {}
    try:
        res = requests.get(api_url, headers=headers, timeout=10)
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
    except Exception as e:
        print(f"Fejl ved hentning af spotpriser: {e}")
        
    return list(formatted.values())

def hent_vind_prognose():
    """Henter vindprognoser for de kommende dage for at estimere prisniveauet."""
    headers = {'User-Agent': 'MinElprisApp/1.0'}
    api_url = 'https://api.energidataservice.dk/dataset/WindPower5MinForecast?limit=200&sort=ForecastDay desc'
    
    dags_prognose = {}
    try:
        res = requests.get(api_url, headers=headers, timeout=10)
        if res.status_code == 200:
            records = res.json().get('records', [])
            for r in records:
                dato = str(r.get('ForecastDay', ''))[:10]
                mwh = r.get('ForecastMWh', 0) or 0
                if dato:
                    if dato not in dags_prognose:
                        dags_prognose[dato] = []
                    dags_prognose[dato].append(mwh)
    except Exception as e:
        print(f"Fejl ved prognose: {e}")
        
    res_prognose = {}
    for dato, vals in dags_prognose.items():
        snit = sum(vals) / len(vals) if vals else 0
        if snit > 1800:
            res_prognose[dato] = {"tekst": "🟢 Forventet LAV pris (Meget vind)", "farve": "#4ade80"}
        elif snit > 900:
            res_prognose[dato] = {"tekst": "🟡 Forventet MEDIUM pris (Normal vind)", "farve": "#facc15"}
        else:
            res_prognose[dato] = {"tekst": "🔴 Forventet HØJ pris (Lidt vind)", "farve": "#f87171"}
            
    return res_prognose

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="da">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>⚡ Elpriser & Prognose</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 20px 15px; display: flex; justify-content: center; }
        .container { max-width: 650px; width: 100%; }
        h1 { text-align: center; color: #38bdf8; margin-bottom: 4px; }
        p.subtitle { text-align: center; color: #94a3b8; margin-bottom: 20px; font-size: 0.9rem; }
        
        .date-selector { display: flex; gap: 8px; justify-content: center; margin-bottom: 20px; flex-wrap: wrap; }
        .date-btn { padding: 10px 14px; background: #1e293b; color: #94a3b8; border: 1px solid #334155; border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 0.85rem; }
        .date-btn:hover { background: #334155; color: white; }
        .date-btn.active { background: #0284c7; color: white; border-color: #38bdf8; }
        
        .prognose-card { background: #1e293b; padding: 15px; border-radius: 12px; border: 1px solid #334155; text-align: center; margin-bottom: 20px; }
        
        table { width: 100%; border-collapse: collapse; background: #1e293b; border-radius: 12px; overflow: hidden; }
        th, td { padding: 10px 12px; text-align: center; font-size: 0.9rem; }
        th { background: #334155; color: #94a3b8; }
        tr { border-bottom: 1px solid #334155; }
        
        .price-cheap { color: #4ade80; font-weight: bold; }
        .price-mid { color: #facc15; font-weight: bold; }
        .price-high { color: #f87171; font-weight: bold; }
        
        .no-data { text-align: center; padding: 20px; background: #1e293b; border-radius: 12px; color: #94a3b8; }
    </style>
</head>
<body>
    <div class="container">
        <h1>⚡ Elpriser & Prognose</h1>
        <p class="subtitle">Live data og vindbaserede forudsigelser</p>
        
        <div class="date-selector">
            {% for d in dags_knapper %}
            <a href="/?offset={{ d.offset }}" class="date-btn {% if valgt_offset == d.offset %}active{% endif %}">
                {{ d.label }} ({{ d.dato_str }})
            </a>
            {% endfor %}
        </div>

        {% if prognose_info %}
        <div class="prognose-card">
            <div style="font-size: 0.85rem; color: #94a3b8; margin-bottom: 5px;">🔮 Vindbaseret Prisprognose:</div>
            <div style="font-size: 1.1rem; font-weight: bold; color: {{ prognose_info.farve }};">
                {{ prognose_info.tekst }}
            </div>
        </div>
        {% endif %}

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
            ℹ️ Ingen koblede spotpriser for denne dato endnu.<br>
            <small>(Spotpriser for næste døgn frigives dagligt omkring kl. 13:00)</small>
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
    data = [r for r in alle_data if str(r.get('time_start', '')).startswith(mål_dato_str)]
    data.sort(key=lambda x: str(x.get('time_start', '')))
    
    prognoser = hent_vind_prognose()
    prognose_info = prognoser.get(mål_dato_str)
    
    return render_template_string(
        HTML_TEMPLATE,
        priser=data,
        valgt_offset=offset,
        dags_knapper=dags_knapper,
        prognose_info=prognose_info,
        str=str
    )

if __name__ == '__main__':
    app.run(debug=True, port=5000)