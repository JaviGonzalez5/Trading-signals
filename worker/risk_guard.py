"""
Circuit breaker en vivo: antes de abrir una señal nueva, comprueba si el
activo está en pausa por una racha de pérdidas reciente. Umbrales en
strategy/risk.py (compartidos con la validación de backtest en
scripts/backtest_improvements.py).
"""

from datetime import datetime, timedelta, timezone

from strategy.risk import COOLDOWN_HOURS, LOSS_STREAK_THRESHOLD
from worker.db import Client, get_recent_closed_signals


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def is_paused(client: Client, asset_id: str) -> bool:
    """True si las últimas LOSS_STREAK_THRESHOLD señales cerradas de este
    activo fueron TODAS pérdidas y la más reciente cerró hace menos de
    COOLDOWN_HOURS — en ese caso no se abren señales nuevas de este activo
    hasta que pase el enfriamiento."""
    recent = get_recent_closed_signals(client, asset_id, limit=LOSS_STREAK_THRESHOLD)
    if len(recent) < LOSS_STREAK_THRESHOLD:
        return False
    if not all(s["status"] == "HIT_SL" for s in recent):
        return False

    last_loss_closed = max(_parse_iso(s["closed_at"]) for s in recent)
    return datetime.now(timezone.utc) < last_loss_closed + timedelta(hours=COOLDOWN_HOURS)
