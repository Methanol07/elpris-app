import os
import requests
from datetime import datetime, timedelta
from flask import Flask, render_template_string, request

app = Flask(__name__)

def beregn_nettarif_og_afgift(time_hour):
    """
    Estimerer elafgift og nettarif (inkl. 25% moms) ud fra tidspunkt på døgnet.
    Afgift: ca. 0.76 DKK/kWh
    Tarif: Varierer (Lav om natten, høj om aftenen)
    """
    elafgift = 0.76
    
    if 0 <= time_hour < 6:
        nettarif = 0.20  # Nat
    elif 17 <= time_hour < 21:
        nettarif = 0.85  # Aftenspids
    else:
        nettarif = 0.35  # Dag/Aften
        
    return elafgift + nettarif

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

def hent_samlet_dagsdata(dato_dt, med_afgifter=False):
    data_dk1 = hent_priser_for_dato_og_omraade(dato_dt, "DK1")
    data_dk2 = hent_priser_for_dato_og_omraade(dato_dt, "DK2")
    
    formatted = {}
    
    for item in data_dk1:
        time_start = item.get('time_start', '')[:16]
        time_hour = int(time_start.split('T')[1].split(':')[0]) if 'T' in time_start else 0
        raw_price = item.get('DKK_per_kWh')
        
        if raw_price is not None:
            pris = raw_price * 1.25 # Spotpris m. moms
            if med_afgifter:
                pris += beregn_nettarif_og_afgift(time_hour)
            formatted[time_start] = {"time_start": time_start, "price_dk1": round(pris, 2), "price_dk2": None}

    for item in data_dk2:
        time_start = item.get('time_start', '')[:16]
        time_hour = int(time_start.split('T')[1].split(':')[0]) if 'T' in time_start else 0
        raw_price = item.get('DKK_per_kWh')
        
        if raw_price is not None:
            pris = raw_price * 1.25 # Spotpris m. moms
            if med_afgifter:
                pris += beregn_nettarif_og_afgift(time_hour)
                
            if time_start not in formatted:
                formatted[time_start] = {"time_start": time_start, "price_dk1": None, "price_dk2": round(pris, 2)}
            else:
                formatted[time_start]["price_dk2"] = round(pris, 2)

    res = list(formatted.values())
    res.sort(key=lambda x: x['time_start'])
    return res

def beregn_vejr_prognose(dato_dt, med_afgifter=False):
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
                time_iso = tider[i]
                time_hour = int(time_iso.split('T')[1].split(':')[0])
                
                vind = vinde[i] if i < len(vinde) else 15
                sol = soler[i] if i < len(soler) else 0
                
                estimeret_spot = 1.20
                if vind > 35: estimeret_spot -= 0.45
                elif vind > 25: estimeret_spot -= 0.25
                elif vind < 10: estimeret_spot += 0.35
                    
                if sol > 300 and 10 <= time_hour <= 16: estimeret_spot -= 0.20
                if 17 <= time_hour <= 20: estimeret_spot += 0.40
                elif 7 <= time_hour <= 9: estimeret_spot += 0.20
                elif 0 <= time_hour <= 5: estimeret_spot -= 0.20
                    
                estimeret_spot = max(0.10, estimeret_spot)
                
                samlet_pris = estimeret_spot
                if med_afgifter:
                    samlet_pris += beregn_nettarif_og_afgift(time_hour)
                
                prognose_timer.append({
                    "time_start": time_iso,
                    "price_dk1": round(samlet_pris, 2),
                    "price_dk2": round(samlet_pris, 2),
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
        p.subtitle { text-align: center; color: #94a3b8; margin-bottom: 15px; font-size: 0.9rem; }
        
        /* Toggle Switch Styling */
        .toggle-box { display: flex; justify-content: center; align-items: center; gap: 10px; margin-bottom: 20px; background: #1e293b; padding: 10px 16px; border-radius: 30px; border: 1px solid #334155; width: fit-content; margin-left: auto; margin-right: auto; }
        .toggle-text { font-size: 0.85rem; font-weight: 600; color: #94a3b8; }
        .toggle-text.active { color: #38bdf8; }
        .switch { position: relative; display: inline-block; width: 44px; height: 22px; }
        .switch input { opacity: 0; width: 0; height: 0; }
        .slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: #334155; transition: .3s; border-radius: 22px; }
        .slider:before { position: absolute; content: ""; height: 16px; width: 16px; left: 3px; bottom: 3px; background-color: white; transition: .3s; border-radius: 50%; }
        input:checked + .slider { background-color: #0284c7; }
        input:checked + .slider:before { transform: translateX(22px); }

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
        <p class="subtitle">
            {% if med_afgifter %}
                <b>Inkl. Elafgift & Nettariffer (Slutpris)</b>
            {% else %}
                <b>Ren Spotpris (Inkl. moms)</b>
            {% endif %}
        </p>
        
        <!-- Toggle Knap -->
        <div class="toggle-box">
            <span class="toggle-text {% if not med_afgifter %}active{% endif %}">Spotpris</span>
            <label class="switch">
                <input type="checkbox" onchange="toggleAfgifter(this)" {% if med_afgifter %}checked{% endif %}>
                <span class="slider"></span>
            </label>
            <span class="toggle-text {% if med_afgifter %}active{% endif %}">Slutpris</span>
        </div>

        <div class="date-selector">
            {% for d in dags_knapper %}
            <a href="/?offset={{ d.offset }}&afgifter={{ 1 if med_afgifter else 0 }}" class="date-btn {% if d.is_forecast %}forecast{% endif %} {% if valgt_offset == d.offset %}active{% endif %}">
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
                    <td class="{% if row.price_dk1 is not none %}{% if row.price_dk1 < (1.5 if not med_afgifter else 2.5) %}price-cheap{% elif row.price_dk1 < (2.5 if not med_afgifter else 3.5) %}price-mid{% else %}price-high{% endif %}{% endif %}">
                        {{ row.price_dk1 if row.price_dk1 is not none else '-' }} kr.
                        {% if er_prognose %}<span class="badge-forecast">Est.</span>{% endif %}
                    </td>
                    <td class="{% if row.price_dk2 is not none %}{% if row.price_dk2 < (1.5 if not med_afgifter else 2.5) %}price-cheap{% elif row.price_dk2 < (2.5 if not med_afgifter else 3.5) %}price-mid{% else %}price-high{% endif %}{% endif %}">
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

    <script>
        function toggleAfgifter(cb) {
            const afgifter = cb.checked ? 1 : 0;
            const urlParams = new URLSearchParams(window.location.search);
            urlParams.set('afgifter', afgifter);
            window.location.search = urlParams.toString();
        }
    </script>
</body>
</html>
"""

@app.route('/', methods=['GET'])
def dashboard():
    try:
        offset = int(request.args.get('offset', 0))
    except ValueError:
        offset = 0

    med_afgifter = request.args.get('afgifter', '0') == '1'

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
        data = beregn_vejr_prognose(valgt_dato, med_afgifter=med_afgifter)
    else:
        data = hent_samlet_dagsdata(valgt_dato, med_afgifter=med_afgifter)
    
    return render_template_string(
        HTML_TEMPLATE,
        priser=data,
        valgt_offset=offset,
        dags_knapper=dags_knapper,
        mål_dato=mål_dato_str,
        er_prognose=er_prognose,
        med_afgifter=med_afgifter
    )

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)