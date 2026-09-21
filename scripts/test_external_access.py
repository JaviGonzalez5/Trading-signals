"""
Prueba de conectividad puntual desde Railway — NO forma parte del sistema,
es un script de un solo uso para comprobar si Binance/Bybit bloquean las
IPs de Railway también en sus endpoints de leaderboard/copytrading, igual
que ya bloquean la API normal de Binance (ver README, Paso 3).
"""

import requests

LEADERBOARD_URL = "https://www.binance.com/bapi/futures/v1/public/future/leaderboard/getLeaderboardRank"
LEADERBOARD_BODY = {
    "isTrader": False,
    "isShared": True,
    "periodType": "WEEKLY",
    "statisticsType": "ROI",
    "tradeType": "PERPETUAL",
}

try:
    resp = requests.post(LEADERBOARD_URL, json=LEADERBOARD_BODY, timeout=15)
    print(f"getLeaderboardRank: HTTP {resp.status_code}")
    print(resp.text[:2000])
except Exception as e:
    print(f"getLeaderboardRank: ERROR {e}")
