import os
import requests
from flask import Flask, jsonify, render_template_string
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

url: str = os.getenv("SUPABASE_URL")
key: str = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(url, key)

def hent_og_gem_spotpriser():
    """Henter de nyeste spotpriser fra Energi Data Service."""
    print("Henter spotpriser...")
    
    # User-Agent hjælper mod 429 rate limit fra Energi Data Service
    headers = {
        'User-Agent': 'MinElprisApp/1.0'
    }
    
    api_url = 'https://api.energidataservice.dk/dataset/Elspotprices?limit=100&filter={"PriceArea":["DK1","DK2"]}&sort=HourUTC desc'
    
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
                supabase.table("strompriser").upsert(data_to_insert, on_conflict="time_start").execute()
                print(f"Svar fra API! Gemt {len(data_to_insert)} timer i Supabase.")
                return len(data_to_insert)
        else:
            print(f"API-fejl: Statuskode {response.status_code}")
    except Exception as e:
        print(f"Netværksfejl: {e}")
        
    return 0

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="da">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>⚡ Dagens Elpriser</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 40px 20px; display: flex; justify-content: center; }
        .container { max-width: 700px; width: 100%; }
        h1 { text-align: center; color: #38bdf8; margin-bottom: 8px; }
        p.subtitle { text-align: center; color: #94a3b8; margin-bottom: 24px; }
        table { width: 100%; border-collapse: collapse; background: #1e293b; border-radius: 12px; overflow: hidden; box-shadow: 0 10px 25px rgba(0,0,0,0.3); }
        th, td { padding: 14px 18px; text-align: center; }
        th { background: #334155; color: #94a3b8; font-weight: 600; text-transform: uppercase; font-size: 0.85rem; letter-spacing: 0.05em; }
        tr { border-bottom: 1px solid #334155; }
        tr:last-child { border-bottom: none; }
        .price-cheap { color: #4ade80; font-weight: bold; }
        .price-mid { color: #facc15; font-weight: bold; }
        .price-high { color: #f87171; font-weight: bold; }
        .time-col { font-weight: 500; color: #cbd5e1; }
        .btn { display: inline-block; padding: 8px 16px; background: #0284c7; color: white; border-radius: 6px; text-decoration: none; font-size: 0.9rem; margin-bottom: 16px; }
        .btn:hover { background: #0369a1; }
    </style>
</head>
<body>
    <div class="container">
        <h1>⚡ Dagens Elpriser</h1>
        <p class="subtitle">Seneste elpriser for DK1 (Jylland/Fyn) og DK2 (Sjælland) i DKK/kWh</p>
        <div style="text-align: center;">
            <a href="/opdater" class="btn">🔄 Hent nyeste data</a>
        </div>
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
    response = supabase.table("strompriser").select("*").order("time_start", desc=True).limit(24).execute()
    return render_template_string(HTML_TEMPLATE, priser=response.data)

@app.route('/opdater', methods=['GET'])
def opdater_manuelt():
    hent_og_gem_spotpriser()
    return dashboard()

@app.route('/api/priser', methods=['GET'])
def get_priser_json():
    response = supabase.table("strompriser").select("*").order("time_start", desc=True).limit(24).execute()
    return jsonify(response.data)

if __name__ == '__main__':
    # Hent data ved opstart
    try:
        hent_og_gem_spotpriser()
    except Exception as e:
        print(f"Fejl: {e}")
        
    app.run(debug=True, port=5000, use_reloader=False)