import os
import requests
from datetime import datetime, timedelta
from flask import Flask, jsonify, render_template_string
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

url: str = os.getenv("SUPABASE_URL")
key: str = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(url, key)

def hent_og_gem_spotpriser():
    """Henter priser fra i dag og frem (inkl. i morgen hvis tilgængelig)."""
    print("Forsøger at hente spotpriser...")
    
    headers = {'User-Agent': 'MinElprisApp/1.0'}
    
    # Hent fra dags dato kl 00:00
    idag_str = datetime.now().strftime('%Y-%m-%d')
    api_url = f'https://api.energidataservice.dk/dataset/Elspotprices?start={idag_str}T00:00&filter={{"PriceArea":["DK1","DK2"]}}&sort=HourUTC asc'
    
    try:
        response = requests.get(api_url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            records = response.json().get('records', [])
            formatted_data = {}
            
            for item in records:
                time_start = item['HourDK']  # Brug lokal dansk tid
                area = item['PriceArea']
                price_dkk = round((item['SpotPriceEUR'] * 7.45) / 1000, 2)
                
                if time_start not in formatted_data:
                    formatted_data[time_start] = {"time_start": time_start}
                
                if area == "DK1":
                    formatted_data[time_start]["price_dk1"] = price_dkk
                elif area == "DK2":
                    formatted_data[time_start]["price_dk2"] = price_dkk

            data_to_insert = list(formatted_data.values())
            if data_to_insert:
                # Gem/opdater i Supabase uten at slette alt råt først
                supabase.table("strompriser").upsert(data_to_insert, on_conflict="time_start").execute()
                print(f"Succes! Hentede og gemte {len(data_to_insert)} timer.")
                return True
        else:
            print(f"API sendte status: {response.status_code} (bruger eksisterende data)")
    except Exception as e:
        print(f"Netværksfejl ved hentning: {e}")
        
    return False

def beregn_nøgletal(data):
    """Opdeler data i I DAG og I MORGEN og beregner gennemsnit + ekstremer."""
    idag_str = datetime.now().strftime('%Y-%m-%d')
    imorgen_str = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
    
    idag_rows = [r for r in data if r['time_start'].startswith(idag_str)]
    imorgen_rows = [r for r in data if r['time_start'].startswith(imorgen_str)]
    
    def laf_stats(rows):
        if not rows:
            return None
        dk1_priser = [r['price_dk1'] for r in rows if r.get('price_dk1') is not None]
        dk2_priser = [r['price_dk2'] for r in rows if r.get('price_dk2') is not None]
        
        res = {}
        if dk1_priser:
            min_r = min(rows, key=lambda x: x.get('price_dk1', 99))
            max_r = max(rows, key=lambda x: x.get('price_dk1', -99))
            res['dk1'] = {
                'avg': round(sum(dk1_priser)/len(dk1_priser), 2),
                'min': min_r['price_dk1'],
                'min_t': min_r['time_start'][11:16],
                'max': max_r['price_dk1'],
                'max_t': max_r['time_start'][11:16]
            }
        if dk2_priser:
            min_r = min(rows, key=lambda x: x.get('price_dk2', 99))
            max_r = max(rows, key=lambda x: x.get('price_dk2', -99))
            res['dk2'] = {
                'avg': round(sum(dk2_priser)/len(dk2_priser), 2),
                'min': min_r['price_dk2'],
                'min_t': min_r['time_start'][11:16],
                'max': max_r['price_dk2'],
                'max_t': max_r['time_start'][11:16]
            }
        return res

    return {
        'idag': laf_stats(idag_rows),
        'imorgen': laf_stats(imorgen_rows),
        'har_imorgen': len(imorgen_rows) > 0
    }

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="da">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>⚡ Dagens & Morgendagens Elpriser</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 20px 15px; display: flex; justify-content: center; }
        .container { max-width: 650px; width: 100%; }
        h1 { text-align: center; color: #38bdf8; margin-bottom: 4px; font-size: 1.6rem; }
        p.subtitle { text-align: center; color: #94a3b8; margin-bottom: 20px; font-size: 0.9rem; }
        
        .card { background: #1e293b; border-radius: 12px; padding: 16px; margin-bottom: 20px; border: 1px solid #334155; }
        .card h3 { margin: 0 0 12px 0; color: #38bdf8; font-size: 1.05rem; border-bottom: 1px solid #334155; padding-bottom: 6px; }
        
        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
        .stat-box { background: #0f172a; padding: 10px; border-radius: 8px; font-size: 0.85rem; }
        .stat-title { font-weight: bold; color: #cbd5e1; margin-bottom: 6px; }
        .val-cheap { color: #4ade80; font-weight: bold; }
        .val-high { color: #f87171; font-weight: bold; }
        
        table { width: 100%; border-collapse: collapse; background: #1e293b; border-radius: 12px; overflow: hidden; }
        th, td { padding: 10px 12px; text-align: center; font-size: 0.9rem; }
        th { background: #334155; color: #94a3b8; font-weight: 600; text-transform: uppercase; font-size: 0.75rem; }
        tr { border-bottom: 1px solid #334155; }
        
        .price-cheap { color: #4ade80; font-weight: bold; }
        .price-mid { color: #facc15; font-weight: bold; }
        .price-high { color: #f87171; font-weight: bold; }
        
        .btn-wrap { text-align: center; margin-bottom: 18px; }
        .btn { display: inline-block; padding: 10px 18px; background: #0284c7; color: white; border-radius: 8px; text-decoration: none; font-size: 0.9rem; font-weight: 600; }
        
        .notice { background: #334155; padding: 10px; border-radius: 8px; text-align: center; font-size: 0.85rem; color: #cbd5e1; margin-bottom: 15px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>⚡ Elpriser & Oversigt</h1>
        <p class="subtitle">DKK pr. kWh (Spotpris uden afgifter/tarif)</p>
        
        <div class="btn-wrap">
            <a href="/opdater" class="btn">🔄 Opdater data</a>
        </div>

        {% if stats.idag %}
        <div class="card">
            <h3>📅 Oversigt for I DAG</h3>
            <div class="grid">
                {% if stats.idag.dk1 %}
                <div class="stat-box">
                    <div class="stat-title">DK1 (Jylland/Fyn)</div>
                    <div>Snit: <b>{{ stats.idag.dk1.avg }} kr</b></div>
                    <div>🟢 Lavest: <span class="val-cheap">{{ stats.idag.dk1.min }} kr</span> (kl. {{ stats.idag.dk1.min_t }})</div>
                    <div>🔴 Højest: <span class="val-high">{{ stats.idag.dk1.max }} kr</span> (kl. {{ stats.idag.dk1.max_t }})</div>
                </div>
                {% endif %}
                {% if stats.idag.dk2 %}
                <div class="stat-box">
                    <div class="stat-title">DK2 (Sjælland)</div>
                    <div>Snit: <b>{{ stats.idag.dk2.avg }} kr</b></div>
                    <div>🟢 Lavest: <span class="val-cheap">{{ stats.idag.dk2.min }} kr</span> (kl. {{ stats.idag.dk2.min_t }})</div>
                    <div>🔴 Højest: <span class="val-high">{{ stats.idag.dk2.max }} kr</span> (kl. {{ stats.idag.dk2.max_t }})</div>
                </div>
                {% endif %}
            </div>
        </div>
        {% endif %}

        {% if stats.har_imorgen %}
        <div class="card">
            <h3>🔮 Prognose / Priser for I MORGEN</h3>
            <div class="grid">
                {% if stats.imorgen.dk1 %}
                <div class="stat-box">
                    <div class="stat-title">DK1 (Jylland/Fyn)</div>
                    <div>Snit: <b>{{ stats.imorgen.dk1.avg }} kr</b></div>
                    <div>🟢 Lavest: <span class="val-cheap">{{ stats.imorgen.dk1.min }} kr</span> (kl. {{ stats.imorgen.dk1.min_t }})</div>
                    <div>🔴 Højest: <span class="val-high">{{ stats.imorgen.dk1.max }} kr</span> (kl. {{ stats.imorgen.dk1.max_t }})</div>
                </div>
                {% endif %}
                {% if stats.imorgen.dk2 %}
                <div class="stat-box">
                    <div class="stat-title">DK2 (Sjælland)</div>
                    <div>Snit: <b>{{ stats.imorgen.dk2.avg }} kr</b></div>
                    <div>🟢 Lavest: <span class="val-cheap">{{ stats.imorgen.dk2.min }} kr</span> (kl. {{ stats.imorgen.dk2.min_t }})</div>
                    <div>🔴 Højest: <span class="val-high">{{ stats.imorgen.dk2.max }} kr</span> (kl. {{ stats.imorgen.dk2.max_t }})</div>
                </div>
                {% endif %}
            </div>
        </div>
        {% else %}
        <div class="notice">
            ℹ️ Priser for i morgen offentliggøres af Nord Pool hver dag omkring kl. 13:00.
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
                    <td style="color:#94a3b8;">{{ row.time_start.replace('T', ' kl. ')[:16] }}</td>
                    <td class="{% if row.price_dk1 and row.price_dk1 < 0.8 %}price-cheap{% elif row.price_dk1 and row.price_dk1 < 1.5 %}price-mid{% else %}price-high{% endif %}">
                        {{ row.price_dk1 if row.price_dk1 is not none else '-' }} kr.
                    </td>
                    <td class="{% if row.price_dk2 and row.price_dk2 < 0.8 %}price-cheap{% elif row.price_dk2 and row.price_dk2 < 1.5 %}price-mid{% else %}price-high{% endif %}">
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
    # Hent kun historik fra dags dato og frem
    idag_str = datetime.now().strftime('%Y-%m-%d')
    response = supabase.table("strompriser").select("*").gte("time_start", idag_str).order("time_start", desc=False).execute()
    data = response.data or []
    
    stats = beregn_nøgletal(data)
    return render_template_string(HTML_TEMPLATE, priser=data, stats=stats)

@app.route('/opdater', methods=['GET'])
def opdater_manuelt():
    hent_og_gem_spotpriser()
    return dashboard()

if __name__ == '__main__':
    hent_og_gem_spotpriser()
    app.run(debug=True, port=5000, use_reloader=False)