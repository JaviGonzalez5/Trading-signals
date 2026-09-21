"use client";

import { useEffect, useRef } from "react";
import { createChart, ColorType, type IChartApi, type ISeriesApi } from "lightweight-charts";
import type { Candle } from "@/lib/kraken";

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
      layout: { background: { type: ColorType.Solid, color: "#131519" }, textColor: "#c3c7cd" },
      grid: { vertLines: { color: "#1a1c21" }, horzLines: { color: "#1a1c21" } },
      width: containerRef.current.clientWidth,
      height: 360,
      timeScale: { timeVisible: true, secondsVisible: false },
    });
    chartRef.current = chart;

    const series = chart.addCandlestickSeries({
      upColor: "#3ecf8e",
      downColor: "#f2555a",
      borderVisible: false,
      wickUpColor: "#3ecf8e",
      wickDownColor: "#f2555a",
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
        color: "#5b9cf6",
        lineWidth: 1,
        lineStyle: 2,
        title: `Entrada ${s.direction}`,
      });
      seriesRef.current.createPriceLine({
        price: s.stop_loss,
        color: "#f2555a",
        lineWidth: 1,
        lineStyle: 2,
        title: "SL",
      });
      seriesRef.current.createPriceLine({
        price: s.take_profit,
        color: "#3ecf8e",
        lineWidth: 1,
        lineStyle: 2,
        title: "TP",
      });
    }

    chartRef.current?.timeScale().fitContent();
  }, [candles, signals]);

  if (candles.length === 0) {
    return <p className="empty-state">Sin datos de precio disponibles ahora mismo.</p>;
  }

  return (
    <div className="chart-card">
      <div ref={containerRef} />
    </div>
  );
}
