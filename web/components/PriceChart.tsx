"use client";

import { useEffect, useRef } from "react";
import { createChart, ColorType, type IChartApi, type ISeriesApi } from "lightweight-charts";
import type { Candle } from "@/lib/kraken";
import { CHART_COLORS } from "@/lib/chart-theme";
import { IconInbox } from "@/components/icons";

export type SignalLevel = {
  id: string;
  direction: "LONG" | "SHORT";
  entry_price: number;
  stop_loss: number;
  take_profit: number;
};

export default function PriceChart({ candles, signals }: { candles: Candle[]; signals: SignalLevel[] }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      layout: { background: { type: ColorType.Solid, color: CHART_COLORS.bg }, textColor: CHART_COLORS.text },
      grid: { vertLines: { color: CHART_COLORS.grid }, horzLines: { color: CHART_COLORS.grid } },
      width: containerRef.current.clientWidth,
      height: 360,
      timeScale: { timeVisible: true, secondsVisible: false },
      crosshair: { vertLine: { color: "#3a3f4c", labelBackgroundColor: "#1a1d24" }, horzLine: { color: "#3a3f4c", labelBackgroundColor: "#1a1d24" } },
    });
    chartRef.current = chart;

    const series = chart.addCandlestickSeries({
      upColor: CHART_COLORS.green,
      downColor: CHART_COLORS.red,
      borderVisible: false,
      wickUpColor: CHART_COLORS.green,
      wickDownColor: CHART_COLORS.red,
    });
    seriesRef.current = series;

    const handleResize = () => {
      if (containerRef.current) chart.applyOptions({ width: containerRef.current.clientWidth });
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
    };
  }, []);

  useEffect(() => {
    if (!seriesRef.current) return;
    seriesRef.current.setData(
      candles.map((c) => ({
        time: c.time as unknown as never,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      }))
    );

    // Limpia líneas de precio previas y dibuja entrada/SL/TP de cada señal activa.
    for (const s of signals) {
      seriesRef.current.createPriceLine({
        price: s.entry_price,
        color: CHART_COLORS.blue,
        lineWidth: 1,
        lineStyle: 2,
        title: `Entrada ${s.direction}`,
      });
      seriesRef.current.createPriceLine({
        price: s.stop_loss,
        color: CHART_COLORS.red,
        lineWidth: 1,
        lineStyle: 2,
        title: "SL",
      });
      seriesRef.current.createPriceLine({
        price: s.take_profit,
        color: CHART_COLORS.green,
        lineWidth: 1,
        lineStyle: 2,
        title: "TP",
      });
    }

    chartRef.current?.timeScale().fitContent();
  }, [candles, signals]);

  if (candles.length === 0) {
    return (
      <p className="empty-state">
        <IconInbox className="icon-empty" size={22} />
        Sin datos de precio disponibles ahora mismo.
      </p>
    );
  }

  return (
    <div className="chart-card">
      <div ref={containerRef} />
    </div>
  );
}
