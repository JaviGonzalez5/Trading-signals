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
- **Paso 5 (web)** — código listo en `web/` (Next.js App Router):
  - `/` — buscador de activos, con badge de señales activas por activo.
  - `/asset/[symbol]` — señales activas, histórico y panel de estadísticas
    (% acierto, retorno estimado, drawdown máximo) calculado con la misma
    lógica que `backtest/engine.py::summarize` (`web/lib/stats.ts`), pero
    usando el `risk_pct` real de cada señal en vez de uno fijo.
  - Server Components leen Supabase directamente con la service_role key
    (`web/lib/supabase-server.ts`, variables de entorno server-only, nunca
    `NEXT_PUBLIC_` — la clave no llega al navegador).
  - `npm run build` verificado en local (0 vulnerabilidades tras fijar
    `postcss` vía `overrides` en `package.json`, mismo patrón que Voltreo).
  - Pendiente de crear el proyecto en Vercel y desplegar.

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
web/                          # frontend Next.js (búsqueda, señales, estadísticas)
```

## Variables de entorno

Ver `.env.example`. Nunca commitear `.env` con valores reales.

## Despliegue en Railway

Dos servicios en el mismo proyecto `senales-trading`:

- **`worker`** — `python -m worker.main`, siempre activo (sin cron).
- **`results-checker`** — `python -m worker.check_results`, con cron diario
  (se ejecuta una vez y termina).

Ambos comparten `SUPABASE_URL`/`SUPABASE_KEY`.

## Despliegue en Vercel

Proyecto Vercel apuntando a este repo con **root directory `web`**. Variables
de entorno: `SUPABASE_URL`/`SUPABASE_KEY` (las mismas del worker, marcadas
como server-only — nunca como "Exposed to the browser").
