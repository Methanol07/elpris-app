import os
import requests
from datetime import datetime, timedelta
from flask import Flask, render_template_string, request

app = Flask(__name__)

def hent_priser_for_dato_og_omraade(dato_dt, price_area):
    """Henter statisk JSON-fil fra elprisenligenu.dk"""
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
    """Henter både DK1 og DK2 for den valgte dato og lægger dem sammen pr. time."""
    data_dk1 = hent_priser_for_dato_og_omraade(dato_dt, "DK1")
    data_dk2 = hent_priser_for_dato_og_omraade(dato_dt, "DK2")
    
    formatted = {}
    
    # Behandl DK1 (Priserne i API'et er i DKK/kWh ekskl. moms -> vi lægger 25% moms på (* 1.25))
    for item in data_dk1:
        time_start = item.get('time_start', '')[:16]
        raw_price = item.get('DKK_per_kWh')
        if raw_price is not None:
            price_med_moms = round(raw_price * 1.25, 2)
            formatted[time_start] = {"time_start": time_start, "price_dk1": price_med_moms, "price_dk2": None}

    # Behandl DK2
    for item in data_dk2:
        time_start = item.get('time_start', '')[:16]
        raw_price = item.get('DKK_per_kWh')
        if raw_price is not None:
            price_med_moms = round(raw_price * 1.25, 2)
            if time_start not in formatted:
                formatted[time_start] = {"time_start": time_start, "price_dk1": None, "price_dk2": price_med_moms}
            else:
                formatted[time_start]["price_dk2"] = price_med_moms

    # Sorter efter tidspunkt
    resultat = list(formatted.values())
    resultat.sort(key=lambda x: x['time_start'])
    return resultat

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
        .attribution { text-align: center; margin-top: 25px; font-size: 0.8rem; color: #64748b; }
        .attribution a { color: #38bdf8; text-decoration: none; }
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
                    <td style="color:#94a3b8;">{{ row.time_start.replace('T', ' kl. ') }}</td>
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
            ℹ️ Ingen spotpriser fundet for <b>{{ mål_dato }}</b> endnu.<br>
            <small>(Priser for i morgen udgives dagligt omkring kl. 13:00)</small>
        </div>
        {% endif %}

        <div class="attribution">
            Elpriser leveret af <a href="https://www.elprisenligenu.dk" target="_blank">Elprisen lige nu.dk</a>
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
    labels = ["I dag", "I morgen"]
    for i in range(2):
        d = idag + timedelta(days=i)
        lbl = labels[i] if i < len(labels) else f"+{i} dage"
        dags_knapper.append({
            'offset': i,
            'label': lbl,
            'dato_str': d.strftime('%d/%m')
        })
        
    data = hent_samlet_dagsdata(valgt_dato)
    
    return render_template_string(
        HTML_TEMPLATE,
        priser=data,
        valgt_offset=offset,
        dags_knapper=dags_knapper,
        mål_dato=mål_dato_str
    )

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)