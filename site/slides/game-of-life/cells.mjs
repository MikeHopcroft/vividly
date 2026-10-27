export function key(x, y) {
  return `${x},${y}`;
}

export function coordinates(cell) {
  const comma = cell.indexOf(',');
  return [Number(cell.slice(0, comma)), Number(cell.slice(comma + 1))];
}
