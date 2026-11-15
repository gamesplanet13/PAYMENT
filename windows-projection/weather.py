"""The weather grid point for Gurudwara Road, Civil Lines, Rampur."""
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from urllib.request import urlopen

RAMPUR = (28.7829727, 79.0243871)
IST = timezone(timedelta(hours=5, minutes=30))


def read_weather():
    query = urlencode({
        'latitude': RAMPUR[0], 'longitude': RAMPUR[1],
        'current': 'temperature_2m,relative_humidity_2m',
        'timezone': 'Asia/Kolkata',
    })
    with urlopen('https://api.open-meteo.com/v1/forecast?' + query, timeout=10) as response:
        current = json.loads(response.read(32768))['current']
    observed = datetime.fromisoformat(current['time']).replace(tzinfo=IST)
    age = datetime.now(IST) - observed
    if not -timedelta(minutes=5) <= age <= timedelta(minutes=40):
        raise ValueError('Weather reading is stale')
    return {
        'city': {'slug':'rampur-civil-lines-gurudwara'},
        'weather': {'temperature_c': current['temperature_2m'],
                    'humidity_pct': current['relative_humidity_2m'], 'time': current['time']},
        'forecast': {'daily': []},
    }
