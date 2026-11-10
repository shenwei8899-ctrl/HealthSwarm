// Pure helpers for the conversation drawer's drag-to-close gesture.
// Kept out of the component so the thresholds can be unit tested.
export const DRAWER_SETTLE_MS = 180
export const DRAWER_CLOSE_RATIO = 1 / 3
export const DRAWER_FLING_VELOCITY = 0.5
export const DRAWER_MIN_DISTANCE = 24

/** 1:1 follow, clamped so the panel never travels past its own width or to the right. */
export function clampDragOffset(distance, width) {
  const max = Number.isFinite(width) && width > 0 ? width : 0
  const moved = Number.isFinite(distance) ? distance : 0
  return Math.max(0, Math.min(max, moved))
}

/** Close when dragged past a third of the panel, or on a short but fast flick. */
export function shouldCloseDrawer({ distance, width, duration, ratio = DRAWER_CLOSE_RATIO, flingVelocity = DRAWER_FLING_VELOCITY, minDistance = DRAWER_MIN_DISTANCE }) {
  const max = Number.isFinite(width) && width > 0 ? width : 0
  const moved = Number.isFinite(distance) && distance > 0 ? distance : 0
  if (!max) return moved >= minDistance
  if (moved >= max * ratio) return true
  const elapsed = Number.isFinite(duration) && duration > 0 ? duration : 1
  return moved >= minDistance && moved / elapsed >= flingVelocity
}

/** Backdrop fades in step with the panel so the two never look detached. */
export function backdropOpacity(distance, width) {
  const max = Number.isFinite(width) && width > 0 ? width : 0
  if (!max) return 1
  return Math.max(0, Math.min(1, 1 - clampDragOffset(distance, max) / max))
}
