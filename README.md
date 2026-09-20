# senales-trading

Web de señales de trading 24/7 (XAUUSD, BTC, ETH...). Proyecto independiente
de Voltreo: repo, Railway, Supabase y Vercel propios, sin relación de datos
ni infraestructura compartida.

Ver `PROMPT_CLAUDE_CODE.md` para el plan completo por pasos.

## Estado

- **Paso 1 (validar estrategia con backtest real)** — pendiente, decidido
  saltarlo por ahora. `yfinance` no es accesible desde el sandbox de Claude
  Code; hace falta correr `backtest/run_backtest.py` desde un entorno con
  salida a internet normal (tu ordenador) o pasar un CSV de velas. **Sin
  este paso no sabemos si la estrategia gana dinero de verdad.**
- **Paso 2 (infraestructura)** — completo:
  - Supabase: proyecto `senales-trading` (ref `puckxtgmogxczuyizrcy`, región
    eu-west-1, plan Free/0€ mes), esquema `assets`/`price_history`/`signals`.
  - Railway: proyecto `senales-trading`, servicio `worker` desplegado.
  - GitHub: este repo.
  - Vercel: conector verificado, proyecto pendiente de crear (Paso 5).
- **Paso 3 (worker 24/7)** — desplegado y verificado en Railway:
  - Cada `POLL_INTERVAL_MINUTES` (15 por defecto) revisa BTC/ETH/XAUUSD.
  - Fuente de datos: **Kraken** (API pública, sin key). Binance devuelve
    451 desde IPs de Railway/cloud; yfinance se cuelga sin timeout desde
    Railway (mismo bloqueo anti-scraping de Yahoo visto en el sandbox).
  - **XAUUSD es un proxy vía PAXG/USD** (oro tokenizado 1:1, Kraken no
    tiene XAUUSD real) — pendiente sustituir por Interactive Brokers si se
    quiere el spot real (requiere IB Gateway corriendo 24/7 en otro sitio,
    no es una llamada HTTP simple).
  - Dedupe en dos capas (comprobación previa + índice único en DB).
  - Sin `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` sigue guardando señales,
    solo no avisa.
- **Paso 4 (revisión de resultados)** — código listo
  (`worker/check_results.py`), pendiente de desplegar como cron en Railway
  (servicio aparte del worker 24/7). Recorre las señales `ACTIVE`, mira las
  velas reales desde que se generaron y marca `HIT_TP`/`HIT_SL` en cuanto
  se toca alguno — mismo criterio que `backtest/engine.py`.
- **Paso 5 (web)** — no iniciado.

## Estructura

```
strategy/core.py            # indicadores (EMA/RSI/ATR) y generación de señales
backtest/engine.py          # simulador de operaciones vela a vela
backtest/run_backtest.py    # script de backtest con yfinance (XAUUSD/BTC/ETH, 2 años, 1h)
worker/main.py               # worker 24/7: descarga velas, genera señales, guarda y avisa
worker/check_results.py      # cron diario: revisa señales ACTIVE, marca HIT_TP/HIT_SL
worker/data_sources.py       # Kraken (en uso) / Binance / yfinance (con incidencias, ver arriba)
worker/db.py                 # acceso a Supabase (service_role)
worker/telegram_client.py    # notificaciones (opcional)
```

## Variables de entorno

Ver `.env.example`. Nunca commitear `.env` con valores reales.

## Despliegue en Railway

Dos servicios en el mismo proyecto `senales-trading`:

- **`worker`** — `python -m worker.main`, siempre activo (sin cron).
- **`results-checker`** — `python -m worker.check_results`, con cron diario
  (se ejecuta una vez y termina).

Ambos comparten `SUPABASE_URL`/`SUPABASE_KEY`.
