import requests
from datetime import datetime, timedelta
from flask import Flask, render_template_string, request

app = Flask(__name__)

def hent_spotpriser():
    headers = {'User-Agent': 'MinElprisApp/1.0'}
    
    # Hent de seneste rækker direkte uden avancerede filtre
    api_url = 'https://api.energidataservice.dk/dataset/Elspotprices?limit=50&sort=HourDK desc'
    
    print(f"--- KALDERS API: {api_url} ---")
    
    formatted = {}
    try:
        res = requests.get(api_url, headers=headers, timeout=10)
        print(f"--- API STATUS KODE: {res.status_code} ---")
        
        if res.status_code == 200:
            records = res.json().get('records', [])
            print(f"--- ANTAL RÆKKER FRA API: {len(records)} ---")
            
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
        print(f"--- API FEJL: {e} ---")
        
    data = list(formatted.values())
    print(f"--- UNIKKE TIDSPUNKTER SAMLET: {len(data)} ---")
    return data

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="da">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>⚡ Elpriser Test</title>
    <style>
        body { font-family: sans-serif; background: #0f172a; color: white; padding: 20px; }
        table { width: 100%; border-collapse: collapse; margin-top: 20px; }
        th, td { padding: 8px; border: 1px solid #334155; text-align: center; }
        .date-btn { padding: 8px 12px; background: #334155; color: white; text-decoration: none; border-radius: 4px; margin-right: 5px; }
        .active { background: #0284c7; }
    </style>
</head>
<body>
    <h1>⚡ Elpriser Live Test</h1>
    <p>Valgt dato-match: <b>{{ mål_dato }}</b></p>
    
    <div>
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
                <th>Tid (HourDK)</th>
                <th>DK1 (kr)</th>
                <th>DK2 (kr)</th>
            </tr>
        </thead>
        <tbody>
            {% for row in priser %}
            <tr>
                <td>{{ row.time_start }}</td>
                <td>{{ row.price_dk1 }}</td>
                <td>{{ row.price_dk2 }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    {% else %}
    <p style="color: #f87171; margin-top: 20px;">⚠️ Ingen rækker matchede datoen: <b>{{ mål_dato }}</b></p>
    <p>Tjek din Render-log for at se, hvilke datoer API'et reelt afleverede!</p>
    {% endif %}
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
    
    # Filtrer på dato
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