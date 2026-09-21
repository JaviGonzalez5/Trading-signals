"""
Prueba de conectividad puntual desde Railway — NO forma parte del sistema,
es un script de un solo uso para comprobar si Binance/Bybit bloquean las
IPs de Railway también en sus endpoints de leaderboard/copytrading, igual
que ya bloquean la API normal de Binance (ver README, Paso 3).
"""

import requests

TARGETS = {
    "binance.com (root)": "https://www.binance.com",
    "binance leaderboard (endpoint comunidad)": (
        "https://www.binance.com/bapi/futures/v1/public/future/leaderboard/getLeaderboardRank"
    ),
    "bybit.com (root)": "https://www.bybit.com",
    "bybit api (root)": "https://api.bybit.com/v5/market/time",
}

for name, url in TARGETS.items():
    try:
        resp = requests.get(url, timeout=10)
        print(f"{name}: HTTP {resp.status_code}")
    except Exception as e:
        print(f"{name}: ERROR {e}")
