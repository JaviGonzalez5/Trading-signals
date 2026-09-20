# senales-trading

Web de señales de trading 24/7 (XAUUSD, BTC, ETH...). Proyecto independiente
de Voltreo: repo, Railway, Supabase y Vercel propios, sin relación de datos
ni infraestructura compartida.

Ver `PROMPT_CLAUDE_CODE.md` para el plan completo por pasos.

## Estado

- **Paso 1 (validar estrategia con backtest real)** — pendiente. `yfinance`
  y la API pública de Binance no son accesibles desde el sandbox de Claude
  Code; hace falta correr `backtest/run_backtest.py` desde un entorno con
  salida a internet normal (tu ordenador) o pasar un CSV de velas.
- **Paso 2 (infraestructura)** — en curso:
  - Supabase: proyecto `senales-trading` (ref `puckxtgmogxczuyizrcy`, región
    eu-west-1, plan Free/0€ mes), esquema aplicado (`assets`, `price_history`,
    `signals`).
  - Railway: proyecto `senales-trading` creado, sin servicio desplegado aún.
  - GitHub: este repo.
  - Vercel: pendiente de crear el proyecto.
- **Paso 3 (worker 24/7)** — no iniciado.
- **Paso 4 (revisión de resultados)** — no iniciado.
- **Paso 5 (web)** — no iniciado.

## Estructura

```
strategy/core.py       # indicadores (EMA/RSI/ATR) y generación de señales
backtest/engine.py      # simulador de operaciones vela a vela
backtest/run_backtest.py  # script de backtest con yfinance (XAUUSD/BTC/ETH, 2 años, 1h)
```

## Variables de entorno

Ver `.env.example`. Nunca commitear `.env` con valores reales.
