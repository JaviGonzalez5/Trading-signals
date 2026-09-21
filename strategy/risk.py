"""
Circuit breaker de riesgo: tras una racha de LOSS_STREAK_THRESHOLD pérdidas
seguidas en UN activo, se pausan señales nuevas de ESE activo durante
COOLDOWN_HOURS, en vez de seguir arriesgando capital real contra una racha
que ya demostró ser mala en las condiciones actuales de mercado (mismo
concepto que la "gestión especial / reducción del riesgo" del curso de
Enrique Moris, bloque de fondeo con futuros).

Motivado por el backtest real: BTC tuvo una racha de 15 pérdidas seguidas
en 6 meses (a 1% de riesgo por operación eso solo ya supera el 3% de
trailing drawdown típico de una cuenta prop firm). Validado en
scripts/backtest_improvements.py que corta el drawdown máximo sin apenas
coste de rentabilidad.

Umbrales en su propio módulo (no en strategy/core.py ni en worker/) para
que el motor en vivo (worker/risk_guard.py) y el backtest
(scripts/backtest_improvements.py) usen exactamente los mismos números.
"""

LOSS_STREAK_THRESHOLD = 4
COOLDOWN_HOURS = 24
