/**
 * Paleta compartida para los gráficos (lightweight-charts y el SVG de equity).
 * No es lógica de datos: solo centraliza los hex que antes vivían duplicados
 * y sueltos dentro de cada componente, para que ambos gráficos y globals.css
 * se muevan siempre juntos si se retoca la paleta.
 */
export const CHART_COLORS = {
  bg: "#0f1115",
  grid: "#1c1f26",
  text: "#8b90a0",
  green: "#26d99a",
  greenDim: "rgba(38, 217, 154, 0.14)",
  red: "#f2495c",
  redDim: "rgba(242, 73, 92, 0.14)",
  blue: "#5b9cf6",
} as const;
