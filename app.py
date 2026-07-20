import os
import requests
from datetime import datetime, timedelta
from flask import Flask, jsonify, render_template_string, request
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

url: str = os.getenv("SUPABASE_URL")
key: str = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(url, key)

def hent_og_gem_spotpriser():
    """Henter dagsaktuelle og kommende spotpriser fra Energi Data Service."""
    headers = {'User-Agent': 'MinElprisApp/1.0'}
    
    # Hent fra 1 dag tilbage for at dække alle tidszoner ordentligt
    start_dato = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    api_url = f'https://api.energidataservice.dk/dataset/Elspotprices?start={start_dato}T00:00&filter={{"PriceArea":["DK1","DK2"]}}&sort=HourDK asc'
    
    try:
        res = requests.get(api_url, headers=headers, timeout=8)
        if res.status_code == 200:
            records = res.json().get('records', [])
            formatted = {}
            for item in records:
                time_start = item['HourDK']
                area = item['PriceArea']
                price_dkk = round((item['SpotPriceEUR'] * 7.45) / 1000, 2)
                
                if time_start not in formatted:
                    formatted[time_start] = {"time_start": time_start}
                
                if area == "DK1":
                    formatted[time_start]["price_dk1"] = price_dkk
                elif area == "DK2":
                    formatted[time_start]["price_dk2"] = price_dkk

            data_to_insert = list(formatted.values())
            if data_to_insert:
                supabase.table("strompriser").upsert(data_to_insert, on_conflict="time_start").execute()
                print(f"Gemte {len(data_to_insert)} rækker i Supabase.")
                return True
    except Exception as e:
        print(f"API Fejl: {e}")
    return False

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="da">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>⚡ Dagens Elpriser</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 20px 15px; display: flex; justify-content: center; }
        .container { max-width: 650px; width: 100%; }
        h1 { text-align: center; color: #38bdf8; margin-bottom: 4px; font-size: 1.6rem; }
        p.subtitle { text-align: center; color: #94a3b8; margin-bottom: 20px; font-size: 0.9rem; }
        
        /* Dato Valg Knapper */
        .date-selector { display: flex; gap: 8px; justify-content: center; margin-bottom: 20px; flex-wrap: wrap; }
        .date-btn { padding: 10px 16px; background: #1e293b; color: #94a3b8; border: 1px solid #334155; border-radius: 8px; text-decoration: none; font-size: 0.9rem; font-weight: 600; transition: all 0.2s; }
        .date-btn:hover { background: #334155; color: white; }
        .date-btn.active { background: #0284c7; color: white; border-color: #38bdf8; }
        
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
        .btn-update { display: inline-block; padding: 8px 14px; background: #334155; color: #cbd5e1; border-radius: 6px; text-decoration: none; font-size: 0.8rem; }
        .btn-update:hover { background: #475569; color: white; }
        .no-data { text-align: center; padding: 30px; background: #1e293b; border-radius: 12px; color: #94a3b8; }
    </style>
</head>
<body>
    <div class="container">
        <h1>⚡ Elpriser & Oversigt</h1>
        <p class="subtitle">Klik på en dag for at se priserne</p>
        
        <!-- DATO KNAPPER -->
        <div class="date-selector">
            <a href="/?dag=idag" class="date-btn {% if valgt_dag == 'idag' %}active{% endif %}">📅 I dag</a>
            <a href="/?dag=imorgen" class="date-btn {% if valgt_dag == 'imorgen' %}active{% endif %}">🔮 I morgen</a>
        </div>

        <div class="btn-wrap">
            <a href="/opdater?dag={{ valgt_dag }}" class="btn-update">🔄 Tving genhentning af data</a>
        </div>

        {% if stats %}
        <div class="card">
            <h3>📊 Nøgletal for {{ dato_visning }}</h3>
            <div class="grid">
                {% if stats.dk1 %}
                <div class="stat-box">
                    <div class="stat-title">DK1 (Jylland/Fyn)</div>
                    <div>Gennemsnit: <b>{{ stats.dk1.avg }} kr</b></div>
                    <div>🟢 Lavest: <span class="val-cheap">{{ stats.dk1.min }} kr</span> (kl. {{ stats.dk1.min_t }})</div>
                    <div>🔴 Højest: <span class="val-high">{{ stats.dk1.max }} kr</span> (kl. {{ stats.dk1.max_t }})</div>
                </div>
                {% endif %}
                {% if stats.dk2 %}
                <div class="stat-box">
                    <div class="stat-title">DK2 (Sjælland)</div>
                    <div>Gennemsnit: <b>{{ stats.dk2.avg }} kr</b></div>
                    <div>🟢 Lavest: <span class="val-cheap">{{ stats.dk2.min }} kr</span> (kl. {{ stats.dk2.min_t }})</div>
                    <div>🔴 Højest: <span class="val-high">{{ stats.dk2.max }} kr</span> (kl. {{ stats.dk2.max_t }})</div>
                </div>
                {% endif %}
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
        {% else %}
        <div class="no-data">
            {% if valgt_dag == 'imorgen' %}
                ℹ️ Priser for i morgen er endnu ikke udgivet af Nord Pool.<br><small>(Udgives normalt kl. 13:00)</small>
            {% else %}
                ⚠️ Ingen data fundet. Tryk på "Tving genhentning af data" ovenfor.
            {% endif %}
        </div>
        {% endif %}
    </div>
</body>
</html>
"""

def laf_stats(rows):
    if not rows:
        return None
    dk1 = [r['price_dk1'] for r in rows if r.get('price_dk1') is not None]
    dk2 = [r['price_dk2'] for r in rows if r.get('price_dk2') is not None]
    res = {}
    if dk1:
        min_r = min(rows, key=lambda x: x.get('price_dk1', 99))
        max_r = max(rows, key=lambda x: x.get('price_dk1', -99))
        res['dk1'] = {'avg': round(sum(dk1)/len(dk1), 2), 'min': min_r['price_dk1'], 'min_t': min_r['time_start'][11:16], 'max': max_r['price_dk1'], 'max_t': max_r['time_start'][11:16]}
    if dk2:
        min_r = min(rows, key=lambda x: x.get('price_dk2', 99))
        max_r = max(rows, key=lambda x: x.get('price_dk2', -99))
        res['dk2'] = {'avg': round(sum(dk2)/len(dk2), 2), 'min': min_r['price_dk2'], 'min_t': min_r['time_start'][11:16], 'max': max_r['price_dk2'], 'max_t': max_r['time_start'][11:16]}
    return res

@app.route('/', methods=['GET'])
def dashboard():
    valgt_dag = request.args.get('dag', 'idag')
    
    if valgt_dag == 'imorgen':
        soeg_dato = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        dato_visning = "I MORGEN"
    else:
        soeg_dato = datetime.now().strftime('%Y-%m-%d')
        dato_visning = "I DAG"
        
    response = supabase.table("strompriser").select("*").like("time_start", f"{soeg_dato}%").order("time_start", desc=False).execute()
    data = response.data or []
    
    # Hvis databasen er helt tom for i dag, så prøv at hente automatisk én gang
    if not data and valgt_dag == 'idag':
        hent_og_gem_spotpriser()
        response = supabase.table("strompriser").select("*").like("time_start", f"{soeg_dato}%").order("time_start", desc=False).execute()
        data = response.data or []
        
    stats = laf_stats(data)
    return render_template_string(HTML_TEMPLATE, priser=data, stats=stats, valgt_dag=valgt_dag, dato_visning=dato_visning)

@app.route('/opdater', methods=['GET'])
def opdater_manuelt():
    valgt_dag = request.args.get('dag', 'idag')
    hent_og_gem_spotpriser()
    return dashboard()

if __name__ == '__main__':
    hent_og_gem_spotpriser()
    app.run(debug=True, port=5000, use_reloader=False)