import os
import requests
from datetime import datetime
from flask import Flask, jsonify, render_template_string
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

url: str = os.getenv("SUPABASE_URL")
key: str = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(url, key)

def hent_og_gem_spotpriser():
    """Henter de nyeste spotpriser for i dag og i morgen fra Energi Data Service."""
    print("Henter dagsfriske spotpriser...")
    
    headers = {
        'User-Agent': 'MinElprisApp/1.0'
    }
    
    idag_str = datetime.utcnow().strftime('%Y-%m-%d')
    api_url = f'https://api.energidataservice.dk/dataset/Elspotprices?start={idag_str}T00:00&filter={{"PriceArea":["DK1","DK2"]}}&sort=HourUTC desc'
    
    try:
        response = requests.get(api_url, headers=headers)
        
        if response.status_code == 200:
            records = response.json().get('records', [])
            formatted_data = {}
            
            for item in records:
                time_start = item['HourUTC']
                area = item['PriceArea']
                
                # Omregn EUR/MWh til DKK/kWh
                price_dkk = round((item['SpotPriceEUR'] * 7.45) / 1000, 2)
                
                if time_start not in formatted_data:
                    formatted_data[time_start] = {"time_start": time_start}
                
                if area == "DK1":
                    formatted_data[time_start]["price_dk1"] = price_dkk
                elif area == "DK2":
                    formatted_data[time_start]["price_dk2"] = price_dkk

            data_to_insert = list(formatted_data.values())
            if data_to_insert:
                # Slet gamle historiske rækker i Supabase, så vi kun har dagsaktuelle data
                supabase.table("strompriser").delete().neq("time_start", "1970-01-01").execute()
                supabase.table("strompriser").upsert(data_to_insert, on_conflict="time_start").execute()
                print(f"Svar fra API! Gemt {len(data_to_insert)} timer for i dag.")
                return len(data_to_insert)
        else:
            print(f"API-fejl: Statuskode {response.status_code}")
    except Exception as e:
        print(f"Netværksfejl: {e}")
        
    return 0

def beregn_prognose(data):
    """Beregner snit, billigste og dyreste time for DK1 og DK2."""
    if not data:
        return None
        
    priser_dk1 = [r['price_dk1'] for r in data if r.get('price_dk1') is not None]
    priser_dk2 = [r['price_dk2'] for r in data if r.get('price_dk2') is not None]
    
    prognose = {}
    
    if priser_dk1:
        snit_dk1 = round(sum(priser_dk1) / len(priser_dk1), 2)
        min_row_dk1 = min(data, key=lambda x: x.get('price_dk1') if x.get('price_dk1') is not None else 999)
        max_row_dk1 = max(data, key=lambda x: x.get('price_dk1') if x.get('price_dk1') is not None else -999)
        
        prognose['dk1'] = {
            'avg': snit_dk1,
            'min_price': min_row_dk1['price_dk1'],
            'min_time': min_row_dk1['time_start'][11:16],
            'max_price': max_row_dk1['price_dk1'],
            'max_time': max_row_dk1['time_start'][11:16]
        }
        
    if priser_dk2:
        snit_dk2 = round(sum(priser_dk2) / len(priser_dk2), 2)
        min_row_dk2 = min(data, key=lambda x: x.get('price_dk2') if x.get('price_dk2') is not None else 999)
        max_row_dk2 = max(data, key=lambda x: x.get('price_dk2') if x.get('price_dk2') is not None else -999)
        
        prognose['dk2'] = {
            'avg': snit_dk2,
            'min_price': min_row_dk2['price_dk2'],
            'min_time': min_row_dk2['time_start'][11:16],
            'max_price': max_row_dk2['price_dk2'],
            'max_time': max_row_dk2['time_start'][11:16]
        }
        
    return prognose

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="da">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>⚡ Dagens Elpriser & Prognose</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 30px 15px; display: flex; justify-content: center; }
        .container { max-width: 750px; width: 100%; }
        h1 { text-align: center; color: #38bdf8; margin-bottom: 6px; font-size: 1.8rem; }
        p.subtitle { text-align: center; color: #94a3b8; margin-bottom: 20px; font-size: 0.95rem; }
        
        /* Prognose Cards Grid */
        .prognose-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 15px; margin-bottom: 25px; }
        .card { background: #1e293b; border-radius: 12px; padding: 18px; box-shadow: 0 4px 15px rgba(0,0,0,0.2); border: 1px solid #334155; }
        .card h3 { margin-top: 0; color: #38bdf8; font-size: 1.1rem; border-bottom: 1px solid #334155; padding-bottom: 8px; }
        .stat-row { display: flex; justify-content: space-between; margin: 8px 0; font-size: 0.95rem; }
        .stat-label { color: #94a3b8; }
        .stat-value { font-weight: bold; }
        .val-cheap { color: #4ade80; }
        .val-high { color: #f87171; }
        
        table { width: 100%; border-collapse: collapse; background: #1e293b; border-radius: 12px; overflow: hidden; box-shadow: 0 10px 25px rgba(0,0,0,0.3); }
        th, td { padding: 12px 14px; text-align: center; }
        th { background: #334155; color: #94a3b8; font-weight: 600; text-transform: uppercase; font-size: 0.8rem; letter-spacing: 0.05em; }
        tr { border-bottom: 1px solid #334155; }
        tr:last-child { border-bottom: none; }
        .price-cheap { color: #4ade80; font-weight: bold; }
        .price-mid { color: #facc15; font-weight: bold; }
        .price-high { color: #f87171; font-weight: bold; }
        .time-col { font-weight: 500; color: #cbd5e1; }
        
        .actions { text-align: center; margin-bottom: 20px; }
        .btn { display: inline-block; padding: 10px 20px; background: #0284c7; color: white; border-radius: 8px; text-decoration: none; font-size: 0.95rem; font-weight: 600; }
        .btn:hover { background: #0369a1; }
    </style>
</head>
<body>
    <div class="container">
        <h1>⚡ Dagens Elpriser</h1>
        <p class="subtitle">Live priser & dagsprognose (DKK/kWh)</p>
        
        <div class="actions">
            <a href="/opdater" class="btn">🔄 Hent nyeste data</a>
        </div>

        {% if prognose %}
        <div class="prognose-grid">
            {% if prognose.dk1 %}
            <div class="card">
                <h3>📊 Prognose: Jylland / Fyn (DK1)</h3>
                <div class="stat-row">
                    <span class="stat-label">Gennemsnit i dag:</span>
                    <span class="stat-value">{{ prognose.dk1.avg }} kr.</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">🟢 Billigste time (kl. {{ prognose.dk1.min_time }}):</span>
                    <span class="stat-value val-cheap">{{ prognose.dk1.min_price }} kr.</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">🔴 Dyreste time (kl. {{ prognose.dk1.max_time }}):</span>
                    <span class="stat-value val-high">{{ prognose.dk1.max_price }} kr.</span>
                </div>
            </div>
            {% endif %}

            {% if prognose.dk2 %}
            <div class="card">
                <h3>📊 Prognose: Sjælland (DK2)</h3>
                <div class="stat-row">
                    <span class="stat-label">Gennemsnit i dag:</span>
                    <span class="stat-value">{{ prognose.dk2.avg }} kr.</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">🟢 Billigste time (kl. {{ prognose.dk2.min_time }}):</span>
                    <span class="stat-value val-cheap">{{ prognose.dk2.min_price }} kr.</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">🔴 Dyreste time (kl. {{ prognose.dk2.max_time }}):</span>
                    <span class="stat-value val-high">{{ prognose.dk2.max_price }} kr.</span>
                </div>
            </div>
            {% endif %}
        </div>
        {% endif %}

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
                    <td class="time-col">{{ row.time_start[:16].replace('T', ' kl. ') }}</td>
                    <td class="{% if row.price_dk1 and row.price_dk1 < 1.0 %}price-cheap{% elif row.price_dk1 and row.price_dk1 < 2.0 %}price-mid{% else %}price-high{% endif %}">
                        {{ row.price_dk1 if row.price_dk1 is not none else '-' }} kr.
                    </td>
                    <td class="{% if row.price_dk2 and row.price_dk2 < 1.0 %}price-cheap{% elif row.price_dk2 and row.price_dk2 < 2.0 %}price-mid{% else %}price-high{% endif %}">
                        {{ row.price_dk2 if row.price_dk2 is not none else '-' }} kr.
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</body>
</html>
"""

@app.route('/', methods=['GET'])
def dashboard():
    response = supabase.table("strompriser").select("*").order("time_start", desc=True).execute()
    data = response.data or []
    prognose = beregn_prognose(data)
    return render_template_string(HTML_TEMPLATE, priser=data, prognose=prognose)

@app.route('/opdater', methods=['GET'])
def opdater_manuelt():
    hent_og_gem_spotpriser()
    return dashboard()

@app.route('/api/priser', methods=['GET'])
def get_priser_json():
    response = supabase.table("strompriser").select("*").order("time_start", desc=True).execute()
    return jsonify(response.data)

if __name__ == '__main__':
    try:
        hent_og_gem_spotpriser()
    except Exception as e:
        print(f"Fejl: {e}")
        
    app.run(debug=True, port=5000, use_reloader=False)