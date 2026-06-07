import '@testing-library/jest-dom'

// jsdom doesn't implement ResizeObserver (needed by recharts)
global.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

// jsdom doesn't implement canvas 2D context (needed by ZoneEditor)
HTMLCanvasElement.prototype.getContext = (() => ({
  clearRect: () => {}, fillRect: () => {}, drawImage: () => {},
  beginPath: () => {}, moveTo: () => {}, lineTo: () => {}, closePath: () => {},
  fill: () => {}, stroke: () => {}, arc: () => {}, fillText: () => {},
  setLineDash: () => {}, measureText: () => ({ width: 0 }),
})) as unknown as typeof HTMLCanvasElement.prototype.getContext
