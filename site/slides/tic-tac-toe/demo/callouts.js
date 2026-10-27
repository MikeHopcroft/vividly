const SVG_NAMESPACE = "http://www.w3.org/2000/svg";

function anchorPoint(rect, point = "center") {
  const points = {
    center: { position: [0.5, 0.5] },
    "top-center": { position: [0.5, 0], axis: "vertical" },
    "bottom-center": { position: [0.5, 1], axis: "vertical" },
    "center-left": { position: [0, 0.5], axis: "horizontal" },
    "center-right": { position: [1, 0.5], axis: "horizontal" },
  };
  const anchor = Array.isArray(point) ? { position: point } : points[point] ?? points.center;
  const [x, y] = anchor.position;
  return {
    x: rect.left + rect.width * x,
    y: rect.top + rect.height * y,
    axis: anchor.axis,
  };
}

function cardPosition(viewport, card, index) {
  const slot = Math.max(1, Number(card.slot) || index + 1);
  const gap = 12;
  const margin = 18;
  const width = Math.max(140, Math.min(220, (viewport.clientWidth - margin * 2 - gap * 2) / 3));
  const horizontalPosition = Number.isFinite(card.horizontal)
    ? Math.max(margin, Math.min(viewport.clientWidth - margin - width, viewport.clientWidth * card.horizontal - width / 2))
    : slot === 1
      ? margin
      : slot === 2
        ? (viewport.clientWidth - width) / 2
        : viewport.clientWidth - margin - width;
  if (card.zone === "bottom") {
    return { left: horizontalPosition, bottom: margin, width };
  }
  if (card.zone === "left") {
    return { left: margin, top: margin + (slot - 1) * 92, width };
  }
  if (card.zone === "right") {
    return {
      right: margin,
      top: card.vertical === "center" ? "50%" : margin + (slot - 1) * 92,
      translate: card.vertical === "center" ? "0 -50%" : "none",
      width,
    };
  }
  return { left: horizontalPosition, top: margin, width };
}

function leaderStart(cardRect, anchor) {
  const center = { x: cardRect.left + cardRect.width / 2, y: cardRect.top + cardRect.height / 2 };
  const horizontal = Math.abs(anchor.x - center.x) > Math.abs(anchor.y - center.y);
  if (horizontal) {
    return {
      x: anchor.x < center.x ? cardRect.left : cardRect.right,
      y: center.y,
      axis: "horizontal",
    };
  }
  return {
    x: center.x,
    y: anchor.y < center.y ? cardRect.top : cardRect.bottom,
    axis: "vertical",
  };
}

function leaderPath(start, anchor) {
  const xBend = start.x + (anchor.x - start.x) * 0.55;
  const yBend = start.y + (anchor.y - start.y) * 0.55;
  const anchorAxis = anchor.axis ?? start.axis;
  const firstControl = start.axis === "horizontal"
    ? { x: xBend, y: start.y }
    : { x: start.x, y: yBend };
  const lastControl = anchorAxis === "horizontal"
    ? { x: xBend, y: anchor.y }
    : { x: anchor.x, y: yBend };
  return `M ${start.x} ${start.y} C ${firstControl.x} ${firstControl.y}, ${lastControl.x} ${lastControl.y}, ${anchor.x} ${anchor.y}`;
}

function positionCard(viewport, element, specification, index) {
  for (const property of ["left", "right", "top", "bottom", "width", "translate"]) {
    element.style[property] = "";
  }
  const position = cardPosition(viewport, specification.card ?? {}, index);
  Object.assign(element.style, Object.fromEntries(
    Object.entries(position).map(([key, value]) => [
      key,
      typeof value === "number" ? `${value}px` : value,
    ]),
  ));
}

export function createCalloutOverlay(viewport, targets = {}) {
  const root = document.createElement("div");
  root.className = "callout-overlay";
  root.setAttribute("aria-live", "polite");
  const svg = document.createElementNS(SVG_NAMESPACE, "svg");
  svg.classList.add("callout-leaders");
  const cards = document.createElement("div");
  cards.className = "callout-cards";
  root.append(svg, cards);
  viewport.append(root);

  let currentTargets = targets;
  let specifications = [];
  let frameRequest = 0;

  function updateNow() {
    frameRequest = 0;
    if (!specifications.length) return;
    const viewportRect = viewport.getBoundingClientRect();
    svg.setAttribute("viewBox", `0 0 ${viewport.clientWidth} ${viewport.clientHeight}`);
    specifications.forEach((specification, index) => {
      const target = currentTargets[specification.anchor.target];
      const card = cards.querySelector(`[data-callout-id="${specification.id}"]`);
      const leader = svg.querySelector(`[data-callout-id="${specification.id}"]`);
      if (!target || !card || !leader) return;
      positionCard(viewport, card, specification, index);
      const targetRect = target.getBoundingClientRect();
      const absoluteAnchor = anchorPoint(targetRect, specification.anchor.point);
      const anchor = {
        x: absoluteAnchor.x - viewportRect.left,
        y: absoluteAnchor.y - viewportRect.top,
        axis: absoluteAnchor.axis,
      };
      const absoluteCardRect = card.getBoundingClientRect();
      const cardRect = {
        left: absoluteCardRect.left - viewportRect.left,
        top: absoluteCardRect.top - viewportRect.top,
        right: absoluteCardRect.right - viewportRect.left,
        bottom: absoluteCardRect.bottom - viewportRect.top,
        width: absoluteCardRect.width,
        height: absoluteCardRect.height,
      };
      const start = leaderStart(cardRect, anchor);
      leader.setAttribute("d", leaderPath(start, anchor));
      leader.setAttribute("visibility", "visible");
    });
    const cardsAnimating = cards.getAnimations({ subtree: true })
      .some(animation => animation.playState === "running");
    if (cardsAnimating) frameRequest = requestAnimationFrame(updateNow);
  }

  function update() {
    if (!frameRequest) frameRequest = requestAnimationFrame(updateNow);
  }

  function show(nextSpecifications) {
    const next = nextSpecifications.map(specification => ({ ...specification }));
    const nextIds = new Set(next.map(specification => specification.id));
    cards.querySelectorAll("[data-callout-id]").forEach(card => {
      if (!nextIds.has(card.dataset.calloutId)) card.remove();
    });
    svg.querySelectorAll("[data-callout-id]").forEach(leader => {
      if (!nextIds.has(leader.dataset.calloutId)) leader.remove();
    });
    next.forEach((specification, index) => {
      if (cards.querySelector(`[data-callout-id="${specification.id}"]`)) return;
      const card = document.createElement("article");
      card.className = "callout-card";
      card.dataset.calloutId = specification.id;
      positionCard(viewport, card, specification, index);
      const number = document.createElement("span");
      number.className = "callout-number";
      number.textContent = specification.number;
      const text = document.createElement("p");
      text.textContent = specification.text;
      card.append(number, text);
      cards.append(card);

      const leader = document.createElementNS(SVG_NAMESPACE, "path");
      leader.classList.add("callout-leader");
      leader.dataset.calloutId = specification.id;
      leader.setAttribute("visibility", "hidden");
      svg.append(leader);
    });
    specifications = next;
    root.toggleAttribute("shown", true);
    update();
  }

  function hide() {
    specifications = [];
    root.toggleAttribute("shown", false);
    cards.replaceChildren();
    svg.replaceChildren();
  }

  function setTargets(nextTargets) {
    currentTargets = nextTargets;
    update();
  }

  const resizeObserver = new ResizeObserver(update);
  resizeObserver.observe(viewport);

  function destroy() {
    if (frameRequest) cancelAnimationFrame(frameRequest);
    resizeObserver.disconnect();
    root.remove();
  }

  return { show, hide, update, setTargets, destroy, isShown: () => specifications.length > 0 };
}
