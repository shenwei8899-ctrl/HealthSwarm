// Keep the title at the viewport midpoint; controls only reduce its safe width.
export function standardNavGeometry({ viewportWidth, row, leftWidth = 0, rightWidth = 0, capsuleLeft, title = '', fontSize = 16 }) {
  const center = viewportWidth / 2 - row.left
  const gap = 8
  const rightEdge = Math.min(row.right, Number.isFinite(capsuleLeft) ? capsuleLeft - gap : row.right)
  const rightInset = Math.max(0, row.right - rightEdge)
  const titleWidth = (actionWidth) => Math.max(0, 2 * Math.min(center - leftWidth - gap, rightEdge - row.left - actionWidth - gap - center))
  // A business action gets its own row when it would crowd the centered title.
  const desiredWidth = Math.min(160, Array.from(String(title)).length * fontSize)
  const actionsBelow = rightWidth > 0 && titleWidth(rightWidth) < desiredWidth
  return { center, rightInset, width: titleWidth(actionsBelow ? 0 : rightWidth), actionsBelow }
}
