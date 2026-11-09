export const CELL = 13;
export const GUTTER = 52;
export const MATRIX_WIDTH = CELL * 48;
export const format = value => value.toLocaleString("en-US");

export function randomSequence(seed) {
  let state = seed;
  return () => {
    state = (state + 0x6D2B79F5) | 0;
    let value = Math.imul(state ^ state >>> 15, 1 | state);
    value = value + Math.imul(value ^ value >>> 7, 61 | value) ^ value;
    return ((value ^ value >>> 14) >>> 0) / 4294967296;
  };
}

export function svgElement(parent, name, attributes, content) {
  const element = document.createElementNS("http://www.w3.org/2000/svg", name);
  for (const [key, value] of Object.entries(attributes)) element.setAttribute(key, value);
  if (content !== undefined) element.textContent = content;
  parent.append(element);
  return element;
}

export function size(svg, width, height) {
  svg.setAttribute("width", width);
  svg.setAttribute("height", height);
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
}

export function dots(svg, x, y, random, active = true, columns = 48) {
  for (let column = 0; column < columns; column += 1) {
    const value = (random() + random() + random() - 1.5) / 1.5;
    svgElement(svg, "circle", {
      cx: x + column * CELL + CELL / 2,
      cy: y + CELL / 2,
      r: Math.max(.9, Math.abs(value) * CELL * .47),
      class: value > 0 ? "positive" : "negative",
      opacity: active ? .95 : .17,
    });
  }
}

export function gap(svg, y, count, height, gutter = GUTTER) {
  svgElement(svg, "line", {
    x1: gutter, x2: gutter + MATRIX_WIDTH,
    y1: y + height / 2, y2: y + height / 2, class: "row-gap",
  });
  const center = gutter + MATRIX_WIDTH / 2;
  svgElement(svg, "rect", {
    x: center - 75, y: y + height * .08, width: 150, height: height * .84,
    rx: height * .42, class: "gap-pill",
  });
  svgElement(svg, "text", { x: center, y: y + height / 2 + 4, class: "gap-label" },
    `⋮ ${format(count)} rows ⋮`);
}
