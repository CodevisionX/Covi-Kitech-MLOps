import { Chart } from 'chart.js';

export const CHART_COLORS = ['#002387', '#0f7f7a', '#b76e00', '#a3346b', '#5c6b80', '#5b4bb2'];
export const CHART_REFERENCE_COLOR = '#8a93a3';

export function applyChartTheme(): void {
  const { defaults } = Chart;
  defaults.font.family = getComputedStyle(document.documentElement).getPropertyValue('--font-family');
  defaults.font.size = 13;
  defaults.color = '#566072';
  defaults.borderColor = '#dfe3e8';
  defaults.elements.point.radius = 0;
  defaults.elements.point.hoverRadius = 4;
  defaults.elements.line.borderWidth = 2;
  defaults.plugins.legend.labels.usePointStyle = true;
  defaults.plugins.legend.labels.pointStyle = 'line';
  defaults.plugins.legend.labels.boxWidth = 24;
}
