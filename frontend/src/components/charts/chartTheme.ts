// Chart styling shared by every Recharts component. Series that share a chart differ in both
// colour and line style, so they stay distinguishable without colour vision.

export const CHART_COLORS = {
  blue: '#3B82F6',
  violet: '#8B5CF6',
  amber: '#F59E0B',
  green: '#22C55E',
  red: '#EF4444',
  grid: '#263449',
  axis: '#94A3B8',
};

export const DASH = {
  solid: undefined,
  dashed: '6 4',
  dotted: '2 3',
};

export const AXIS_PROPS = {
  stroke: CHART_COLORS.axis,
  tick: { fill: CHART_COLORS.axis, fontSize: 11 },
  tickLine: false,
  axisLine: false,
} as const;

export const GRID_PROPS = {
  stroke: CHART_COLORS.grid,
  strokeDasharray: '3 3',
  vertical: false,
} as const;

export const CHART_HEIGHT = 240;
