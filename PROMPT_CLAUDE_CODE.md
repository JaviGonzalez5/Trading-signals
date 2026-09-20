# Proyecto: Web de señales de trading 24/7 (señales-trading)

## Contexto y objetivo
Quiero construir una web independiente (nada que ver con mi otro proyecto Voltreo:
repo, Railway, Supabase y Vercel deben ser TODOS nuevos y separados) que:

1. Tenga un buscador donde pueda escribir un activo (XAUUSD, BTC, ETH, USDT, etc.)
2. Analice el mercado 24/7 mediante un worker que corre en Railway (proceso siempre
   activo, ejecuta el motor de señales cada X minutos)
3. Genere señales de compra/venta con: precio de entrada, stop loss, take profit,
   y tamaño de posición recomendado según mi capital y % de riesgo (1% por defecto)
4. Me avise por Telegram cuando salte una señal nueva
5. Guarde TODAS las señales generadas (aunque yo no opere) en una base de datos
   (Supabase, proyecto nuevo, sin relación con el de Voltreo)
6. Revise periódicamente el resultado real de cada señal pasada (si tocó TP o SL)
   y muestre estadísticas de aciertos/fallos en la web, para poder ajustar la
   estrategia con datos reales en vez de intuición

## Estado actual del proyecto
Ya tengo escrita y probada (en estructura, pendiente de backtest con datos reales
porque el entorno de chat de Claude no tenía acceso a Yahoo Finance) la lógica de
la estrategia base:

- Filtro de tendencia: EMA 50 vs EMA 200
- Gatillo de entrada: ruptura de máximo/mínimo de las últimas 20 velas + confirmación
  con RSI(14) (>50 para largos, <50 para cortos)
- Stop loss: 1.5x ATR(14) desde la entrada
- Take profit: 2.5x ATR(14) desde la entrada
- Cálculo de tamaño de posición: (capital x riesgo%) / distancia al SL

Adjunto los archivos ya escritos:
- `strategy/core.py` — indicadores y generación de señales
- `backtest/engine.py` — simulador de operaciones vela a vela
- `backtest/run_backtest.py` — script de backtest con yfinance (XAUUSD/BTC/ETH, 2 años, velas 1h)

## Lo que necesito que hagas, paso a paso (nada de un solo golpe grande)

### Paso 1 — Validar la estrategia
Ejecuta `backtest/run_backtest.py` (instala dependencias si hace falta) y enséñame
los resultados: número de operaciones, % de acierto, retorno estimado, drawdown
máximo, para XAUUSD, BTC y ETH por separado. NO sigas al paso 2 hasta que yo
confirme que esos números me convencen.

### Paso 2 — Estructura del proyecto e infraestructura
- Crea un repo NUEVO en GitHub (pregúntame el nombre si no lo tengo claro)
- Crea un proyecto NUEVO en Railway (independiente del que uso para Voltreo)
- Crea un proyecto NUEVO en Supabase (independiente del de Voltreo) y diséñame el
  esquema de tablas: activos, señales (con entrada/sl/tp/resultado), histórico de
  precios
- Crea un proyecto NUEVO en Vercel para el frontend

Avísame antes de crear nada si hace falta que yo confirme cuentas o pague algo.

### Paso 3 — Worker de señales (Railway)
Proceso en Python que corre en bucle (o vía cron), para cada activo que yo tenga
configurado:
- Descarga velas recientes (fuente de datos: para cripto usa la API pública de
  Binance; para XAUUSD/forex, de momento usa la misma fuente del backtest o
  pregúntame si prefiero conectar mi cuenta de Interactive Brokers, que ya tengo
  activa para otro proyecto)
- Aplica `strategy/core.py` para generar señal
- Si hay señal nueva, la guarda en Supabase y envía notificación a Telegram (te
  diré el bot token y chat_id cuando lo tengas listo, no los inventes ni los pidas
  como si ya los tuvieras)

### Paso 4 — Revisión de resultados (aprendizaje asistido)
Cron diario que revisa las señales de días anteriores, comprueba si el precio
tocó TP o SL después, y actualiza el resultado en Supabase. Esto NO es un sistema
de auto-aprendizaje de IA — es un registro objetivo de aciertos/fallos para que
yo pueda ajustar los parámetros de la estrategia con datos reales.

### Paso 5 — Web (Vercel)
Frontend simple con:
- Buscador de activos
- Vista de señales activas e histórico por activo
- Panel de estadísticas (% acierto, retorno estimado, drawdown) por estrategia/activo

## Restricciones importantes
- Cero relación con el proyecto Voltreo: ni repo, ni Railway, ni Supabase, ni Vercel
  compartidos. Todo nuevo y separado.
- No soy trader profesional. Trabajaré primero con una cuenta demo de prop firm
  (Orion Funded, $100k, evaluación con 5% profit target / 1% daily loss / 3%
  trailing max loss) antes de valorar capital real.
- Riesgo por operación: 1% del capital configurado, ajustable.
- No inventes datos ni asumas credenciales/tokens que no te haya dado — pregúntame.
- Ve avisándome en cada paso importante de qué has probado y qué falta.
