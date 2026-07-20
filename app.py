import os
import requests
from datetime import datetime, timedelta
from flask import Flask, render_template_string, request
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

url: str = os.getenv("SUPABASE_URL")
key: str = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(url, key)

def hent_og_gem_spotpriser():
    """Henter spotpriser for de seneste og kommende dage fra Energi Data Service."""
    headers = {'User-Agent': 'MinElprisApp/1.0'}
    
    # Hent fra 2 dage siden til i dag/i morgen
    fra_dato = (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d')
    api_url = f'https://api.energidataservice.dk/dataset/Elspotprices?start={fra_dato}&filter={{"PriceArea":["DK1","DK2"]}}&sort=HourDK asc'
    
    try:
        res = requests.get(api_url, headers=headers, timeout=10)
        if res.status_code == 200:
            records = res.json().get('records', [])
            formatted = {}
            for item in records:
                time_start = item['HourDK']
                area = item['PriceArea']
                spot_eur = item.get('SpotPriceEUR')
                
                if spot_eur is None:
                    continue
                    
                price_dkk = round((spot_eur * 7.45) / 1000, 2)
                
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
        print(f"Fejl ved opdatering af spotpriser: {e}")
    return False

def laf_stats(rows):
    if not rows:
        return None
    dk1 = [r['price_dk1'] for r in rows if r.get('price_dk1') is not None]
    dk2 = [r['price_dk2'] for r in rows if r.get('price_dk2') is not None]
    res = {}
    if dk1:
        min_r = min(rows, key=lambda x: x.get('price_dk1', 99))
        max_r = max(rows, key=lambda x: x.get('price_dk1', -99))
        res['dk1'] = {
            'avg': round(sum(dk1)/len(dk1), 2),
            'min': min_r['price_dk1'],
            'min_t': str(min_r['time_start'])[11:16],
            'max': max_r['price_dk1'],
            'max_t': str(max_r['time_start'])[11:16]
        }
    if dk2:
        min_r = min(rows, key=lambda x: x.get('price_dk2', 99))
        max_r = max(rows, key=lambda x: x.get('price_dk2', -99))
        res['dk2'] = {
            'avg': round(sum(dk2)/len(dk2), 2),
            'min': min_r['price_dk2'],
            'min_t': str(min_r['time_start'])[11:16],
            'max': max_r['price_dk2'],
            'max_t': str(max_r['time_start'])[11:16]
        }
    return res

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="da">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>⚡ Elpriser & Oversigt</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 20px 15px; display: flex; justify-content: center; }
        .container { max-width: 700px; width: 100%; }
        h1 { text-align: center; color: #38bdf8; margin-bottom: 4px; font-size: 1.6rem; }
        p.subtitle { text-align: center; color: #94a3b8; margin-bottom: 20px; font-size: 0.9rem; }
        
        .date-selector { display: flex; gap: 8px; justify-content: center; margin-bottom: 20px; flex-wrap: wrap; }
        .date-btn { padding: 10px 14px; background: #1e293b; color: #94a3b8; border: 1px solid #334155; border-radius: 8px; text-decoration: none; font-size: 0.85rem; font-weight: 600; transition: all 0.2s; }
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
        .no-data { text-align: center; padding: 30px; background: #1e293b; border-radius: 12px; color: #94a3b8; line-height: 1.6; }
    </style>
</head>
<body>
    <div class="container">
        <h1>⚡ Elpriser & Prognose</h1>
        <p class="subtitle">Vælg en dag for at se priser eller forventet niveau</p>
        
        <!-- KNAPPER TIL DAGE (I DAG, I MORGEN, +2 DAGE, +3 DAGE) -->
        <div class="date-selector">
            {% for d in dags_knapper %}
            <a href="/?offset={{ d.offset }}" class="date-btn {% if valgt_offset == d.offset %}active{% endif %}">
                {{ d.label }} ({{ d.dato_str }})
            </a>
            {% endfor %}
        </div>

        <div class="btn-wrap">
            <a href="/opdater?offset={{ valgt_offset }}" class="btn-update">🔄 Hent seneste priser fra API</a>
        </div>

        {% if stats %}
        <div class="card">
            <h3>📊 Nøgletal for {{ dato_overskrift }}</h3>
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
            {% if valgt_offset > 1 %}
                🔮 <b>Prognose for {{ dato_overskrift }}:</b><br>
                Børsen (Nord Pool) udgiver kun endelige timepriser for 1 dag ad gangen (udgives dagligt kl. 13:00).<br>
                Forventede priser 2-3 dage frem følger den generelle vind- og solprognose.
            {% else %}
                ⚠️ Ingen gemte data for denne dag endnu.<br>
                Tryk på knappen <b>"🔄 Hent seneste priser fra API"</b> ovenfor.
            {% endif %}
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
    
    # Byg knapper for I dag (0), I morgen (+1), Dag 3 (+2), Dag 4 (+3)
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
        
    dato_overskrift = valgt_dato.strftime('%d-%m-%Y')
    
    # Hent alle rækker fra Supabase og filtrér direkte i Python (undgår PostgreSQL timezone-konflikter)
    response = supabase.table("strompriser").select("*").execute()
    alle_data = response.data or []
    
    # Filtrér rækker, der matcher den valgte dato
    data = [r for r in alle_data if str(r.get('time_start', '')).startswith(mål_dato_str)]
    data.sort(key=lambda x: str(x.get('time_start', '')))
    
    # Hvis databasen er tom for i dag, hent automatisk fra API
    if not data and offset == 0:
        hent_og_gem_spotpriser()
        response = supabase.table("strompriser").select("*").execute()
        alle_data = response.data or []
        data = [r for r in alle_data if str(r.get('time_start', '')).startswith(mål_dato_str)]
        data.sort(key=lambda x: str(x.get('time_start', '')))
        
    stats = laf_stats(data)
    
    return render_template_string(
        HTML_TEMPLATE,
        priser=data,
        stats=stats,
        valgt_offset=offset,
        dags_knapper=dags_knapper,
        dato_overskrift=dato_overskrift,
        str=str
    )

@app.route('/opdater', methods=['GET'])
def opdater_manuelt():
    hent_og_gem_spotpriser()
    offset = request.args.get('offset', 0)
    return dashboard()

if __name__ == '__main__':
    hent_og_gem_spotpriser()
    app.run(debug=True, port=5000, use_reloader=False)