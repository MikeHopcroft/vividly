import { CELL, GUTTER, MATRIX_WIDTH, format, randomSequence, svgElement, size, dots, gap } from "../mlp-diagram.js";
import { CATALOG_SIZE, LIKED, WINNER, CANDIDATES, ROW_SCORES, posterUrl } from "./data.js";

const GAP_HEIGHT = 22;
const PITCH_X = 224;
const PITCH_Y = 374;
const LEFT_RING = 3;
const TOP_RING = 2;
const likedRows = new Set(LIKED.map(movie => movie.row));

function rowLayout(groups) {
  const rows = [];
  let height = 0;
  groups.forEach((group, index) => {
    if (index) {
      const previous = groups[index - 1];
      rows.push({ omitted: group[0] - previous[previous.length - 1] - 1, y: height });
      height += GAP_HEIGHT;
    }
    for (const row of group) {
      rows.push({ index: row, y: height });
      height += CELL;
    }
  });
  return { rows, height };
}

function matrixRows(svg, layout, seed, input = false) {
  size(svg, GUTTER + MATRIX_WIDTH, layout.height);
  const random = randomSequence(seed);
  for (const row of layout.rows) {
    if (row.omitted !== undefined) {
      gap(svg, row.y, row.omitted, GAP_HEIGHT);
      continue;
    }
    const selected = input && likedRows.has(row.index);
    const winner = !input && row.index === WINNER.row;
    const group = svgElement(svg, "g", {
      class: selected ? "selected-row" : winner ? "winner-row" : "weight-row",
      "data-row": row.index,
    });
    if (selected || winner) svgElement(group, "rect", {
      x: GUTTER, y: row.y, width: MATRIX_WIDTH, height: CELL,
      class: selected ? "row-highlight" : "winner-highlight", rx: 3,
    });
    svgElement(group, "text", { x: GUTTER - 6, y: row.y + CELL - 2, class: "row-index" }, format(row.index));
    dots(group, GUTTER, row.y, random, !input || selected);
  }
}

function renderMatrices(root) {
  const input = rowLayout([
    [0, 1, 2], [811, 812, 813], [2045, 2046, 2047],
    [5132, 5133, 5134], [7720, 7721, 7722], [9497, 9498, 9499],
  ]);
  const output = rowLayout([
    [0, 1, 2], [811, 812, 813], [2045, 2046, 2047], [3301, 3302, 3303],
    [5132, 5133, 5134], [7720, 7721, 7722], [9497, 9498, 9499],
  ]);
  matrixRows(root.querySelector(".input-weights"), input, 11, true);
  matrixRows(root.querySelector(".output-weights"), output, 41);
  const encoded = root.querySelector(".input-vector");
  size(encoded, 170, input.height);
  for (const row of input.rows) {
    if (row.omitted !== undefined) {
      svgElement(encoded, "text", { x: 161, y: row.y + 16, class: "ellipsis" }, "⋮");
      continue;
    }
    const movie = LIKED.find(item => item.row === row.index);
    svgElement(encoded, "circle", {
      cx: 161, cy: row.y + CELL / 2, r: CELL * .38,
      class: `binary-value${movie ? " active" : ""}`,
    });
    if (movie) svgElement(encoded, "text", {
      x: 150, y: row.y + CELL / 2 + 4, class: "input-movie-label",
    }, movie.title.replace(/^The /, ""));
  }
  const bias = root.querySelector(".hidden-bias");
  size(bias, GUTTER + MATRIX_WIDTH, CELL);
  dots(bias, GUTTER, 0, randomSequence(23));
  const hidden = root.querySelector(".hidden-vector");
  size(hidden, MATRIX_WIDTH, CELL + 8);
  const random = randomSequence(5);
  for (let column = 0; column < 48; column += 1) {
    const value = random() < .4 ? 0 : random();
    svgElement(hidden, "circle", {
      cx: column * CELL + CELL / 2, cy: 4 + CELL / 2,
      r: value ? Math.max(1.5, value * CELL * .47) : 2,
      class: value ? "positive" : "zero-activation",
    });
  }
  const outputBias = root.querySelector(".output-bias");
  const logits = root.querySelector(".logits");
  size(outputBias, CELL, output.height);
  size(logits, 190, output.height);
  const biasRandom = randomSequence(42);
  for (const row of output.rows) {
    if (row.omitted !== undefined) {
      for (const svg of [outputBias, logits]) {
        svgElement(svg, "text", { x: CELL / 2 + 1, y: row.y + 16, class: "ellipsis" }, "⋮");
      }
      continue;
    }
    dots(outputBias, 0, row.y, biasRandom, true, 1);
    const score = ROW_SCORES.get(row.index);
    const masked = likedRows.has(row.index);
    const winner = row.index === WINNER.row;
    const group = svgElement(logits, "g", {
      "data-row": row.index, class: masked ? "masked-logit" : winner ? "winner-logit" : "logit",
    });
    svgElement(group, "circle", {
      cx: CELL / 2 + 1, cy: row.y + CELL / 2, r: CELL * .44, class: "logit-guide",
    });
    svgElement(group, "circle", {
      cx: CELL / 2 + 1, cy: row.y + CELL / 2,
      r: Math.max(1, (score - 3) / 6.5 * CELL * .36), class: "logit-value",
    });
    svgElement(group, "text", { x: CELL + 10, y: row.y + CELL / 2 + 4.5, class: "logit-score" }, score.toFixed(2));
    if (masked || winner) svgElement(group, "text", {
      x: CELL + 52, y: row.y + CELL / 2 + 4, class: "logit-note",
    }, masked ? "masked · liked" : "← argmax");
  }
}

function poster(movie) {
  const frame = document.createElement("div");
  frame.className = "poster";
  const image = document.createElement("img");
  image.src = posterUrl(movie);
  image.alt = `Poster for ${movie.title}`;
  image.draggable = false;
  frame.append(image);
  return frame;
}

function tile(movie, { masked = false, winner = false, decorative = false } = {}) {
  const card = document.createElement("article");
  card.className = `movie-tile${masked ? " masked" : ""}${winner ? " winner" : ""}`;
  card.dataset.title = movie.title;
  card.dataset.score = movie.score;
  if (decorative) {
    card.classList.add("decorative");
    card.setAttribute("aria-hidden", "true");
  }
  card.append(poster(movie));
  const title = document.createElement("h3");
  title.className = "movie-title";
  title.textContent = movie.title;
  card.append(title);
  const score = document.createElement("p");
  score.className = "score";
  score.innerHTML = `${movie.score.toFixed(2)} <small>Logit</small>`;
  card.append(score);
  const bar = document.createElement("div");
  bar.className = "score-bar";
  bar.setAttribute("aria-hidden", "true");
  bar.innerHTML = `<span style="width:${movie.score * 10}%"></span>`;
  card.append(bar);
  if (masked || winner) {
    const badge = document.createElement("span");
    badge.className = "tile-badge";
    badge.textContent = masked ? "Liked · masked" : "Argmax · unseen";
    card.append(badge);
  }
  return card;
}

function renderWall(root) {
  const wall = root.querySelector(".movie-wall");
  const fixed = new Map([
    ["2,4", { movie: WINNER, winner: true }],
    ["1,5", { movie: LIKED[0], masked: true }],
    ["3,2", { movie: LIKED[1], masked: true }],
    ["0,8", { movie: LIKED[2], masked: true }],
    ["4,7", { movie: LIKED[3], masked: true }],
  ]);
  const holes = new Set(["0,0", "0,9", "4,0", "4,9"]);
  const random = randomSequence(77);
  let candidate = 0;
  for (let row = 0; row < 10; row += 1) {
    for (let column = 0; column < 16; column += 1) {
      const r = row - TOP_RING;
      const c = column - LEFT_RING;
      const central = r >= 0 && r < 5 && c >= 0 && c < 10 && !holes.has(`${r},${c}`);
      let card;
      if (central) {
        const entry = fixed.get(`${r},${c}`);
        card = entry ? tile(entry.movie, entry) : tile(CANDIDATES[candidate++]);
      } else {
        const movie = CANDIDATES[Math.floor(random() * CANDIDATES.length)];
        card = tile({ ...movie, score: 3 + random() * 5.2 }, { decorative: true });
        const distance = Math.max(r < 0 ? -r : r >= 5 ? r - 4 : 0, c < 0 ? -c : c >= 10 ? c - 9 : 0, 1);
        card.style.opacity = [1, .9, .55, .22][Math.min(distance, 3)];
      }
      card.style.left = `${column * PITCH_X}px`;
      card.style.top = `${row * PITCH_Y}px`;
      wall.append(card);
    }
  }
  const more = root.querySelector(".more-movies");
  more.textContent = `⋮ ${format(CATALOG_SIZE - 46)} more movies, each with its own logit ⋮`;
  more.style.top = `${7.9 * PITCH_Y}px`;
  const focus = root.querySelector(".winner-focus");
  focus.style.left = `${7 * PITCH_X - 80}px`;
  focus.style.top = `${3 * PITCH_Y - 32}px`;
  focus.style.width = `${2 * PITCH_X + 160}px`;
  focus.style.height = `${2 * PITCH_Y + 64}px`;
}

export function renderMovieDiagram(root) {
  const liked = root.querySelector(".liked-grid");
  for (const movie of LIKED) {
    const card = document.createElement("figure");
    card.append(poster(movie));
    const caption = document.createElement("figcaption");
    caption.textContent = movie.title;
    const badge = document.createElement("span");
    badge.className = "row-badge";
    badge.textContent = `row ${format(movie.row)}`;
    card.append(caption, badge);
    liked.append(card);
  }
  renderMatrices(root);
  renderWall(root);
}
