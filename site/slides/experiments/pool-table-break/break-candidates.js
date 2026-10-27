import { BilliardsTable } from './billiards.js';

const CANDIDATES = [
  { seed: 80, title: 'Best all-round starting point',
    note: 'Highest combined score; all eight table regions occupied at rest, only pairs clustered, and no pocketed balls at either searched width.',
    turns: 39, late: 17, regions: 8, cluster: 2, seconds: 4.00 },
  { seed: 235, title: 'Sustained second-wave action',
    note: 'Twenty hard turns after the initial burst and long total travel. A strong option if the rebound phase matters more than a perfectly even finish.',
    turns: 40, late: 20, regions: 7, cluster: 2, seconds: 3.92 },
  { seed: 190, title: 'Whole-table coverage',
    note: 'Moving balls reach all eight regions during the early action, and the final arrangement also fills all eight.',
    turns: 39, late: 17, regions: 8, cluster: 2, seconds: 3.98 },
  { seed: 214, title: 'Presentation-width contender',
    note: 'Especially strong at the wider table size. No pocketed balls at either width; a distributed finish with fewer hard turns than the busiest options.',
    turns: 31, late: 17, regions: 8, cluster: 2, seconds: 4.00 },
  { seed: 19, title: 'Fast, high-travel burst',
    note: 'The longest total travel among these candidates in the smaller layout, with a slightly quicker finish and all eight regions occupied.',
    turns: 43, late: 19, regions: 8, cluster: 2, seconds: 3.79 },
  { seed: 117, title: 'Busy small-layout alternative',
    note: 'Fifty hard turns, twenty after the initial burst, and no close-neighbor clusters at rest. Less competitive at the wider layout.',
    turns: 50, late: 20, regions: 8, cluster: 1, seconds: 3.86 },
  { seed: 7, title: 'Current default - baseline',
    note: 'Still lively, but leaves a five-ball near-neighbor cluster in the smaller layout. Included to judge whether the new options actually improve the slide.',
    turns: 34, late: 21, regions: 7, cluster: 5, seconds: 3.73 },
];

export function createBreakCandidates(root) {
  root.innerHTML = `
    <div class="break-comparison">
      <header>
        <h1>Billiards break candidates</h1>
        <p>Six candidates from a 256-seed search, plus the current seed 7 for comparison.
          These use the actual slide simulation and rendering. Stills show the settled result;
          use Replay to judge the motion. The presentation's default seed is unchanged.</p>
        <div class="controls">
          <button data-play-all type="button">Replay all</button>
          <button data-settle-all type="button">Settle all</button>
          <label>Table width
            <select data-layout>
              <option value="512">512 px - smaller slide layout</option>
              <option value="737.203125">737 px - 1920px presentation layout</option>
            </select>
          </label>
        </div>
        <p>Metrics describe the 512px layout. A "hard turn" is a direction change over 60 degrees
          while moving faster than 300 mm/s on both sides of the turn, not an exact collision count.
          Pocket and cluster counts can change at the other width. Narrow windows may further shrink previews.</p>
      </header>
      <main class="candidates"></main>
    </div>`;
  const main = root.querySelector('.candidates');
  const events = new AbortController();
  const options = { signal: events.signal };
  const tables = [];
  for (const candidate of CANDIDATES) {
    const card = document.createElement('article');
    const description = document.createElement('div');
    description.className = 'description';
    const heading = document.createElement('h2');
    heading.textContent = `Seed ${candidate.seed}: ${candidate.title}`;
    const note = document.createElement('p');
    note.textContent = candidate.note;
    const metrics = document.createElement('p');
    metrics.className = 'metrics';
    metrics.textContent = `${candidate.turns} hard turns (${candidate.late} late); `
      + `${candidate.regions}/8 final regions; largest cluster ${candidate.cluster}; `
      + `0 pocketed; settled at ${candidate.seconds.toFixed(2)}s.`;
    const actions = document.createElement('div');
    actions.className = 'actions';
    const replay = document.createElement('button');
    replay.type = 'button';
    replay.textContent = 'Replay';
    replay.setAttribute('aria-label', `Replay seed ${candidate.seed}`);
    const link = document.createElement('a');
    const url = new URL('../../../', import.meta.url);
    url.searchParams.set('breakSeed', candidate.seed);
    url.hash = '/pool-table-break-lab/opening';
    link.href = url.href;
    link.target = '_blank';
    link.rel = 'noopener';
    link.textContent = 'Open in slide';
    link.setAttribute('aria-label', `Open seed ${candidate.seed} in the slide`);
    actions.append(replay, link);
    description.append(heading, note, metrics, actions);
    const canvas = document.createElement('canvas');
    canvas.setAttribute('role', 'img');
    canvas.setAttribute('aria-label', `Billiards break using seed ${candidate.seed}`);
    card.append(description, canvas);
    main.append(card);
    const table = new BilliardsTable(canvas, candidate.seed);
    replay.addEventListener('click', () => table.play(), options);
    tables.push(table);
  }
  const finish = () => tables.forEach(table => {
    table.resize();
    table.finish();
  });
  root.querySelector('[data-play-all]').addEventListener('click', () => {
    tables.forEach(table => table.play());
  }, options);
  root.querySelector('[data-settle-all]').addEventListener('click', finish, options);
  const layout = root.querySelector('[data-layout]');
  layout.addEventListener('change', () => {
    main.style.setProperty('--table-width', `${layout.value}px`);
  }, options);
  return {
    finish,
    stop: () => tables.forEach(table => table.stop()),
    settle() {
      const running = tables.some(table => table.running);
      if (running) finish();
      return running;
    },
    dispose() {
      events.abort();
      tables.forEach(table => table.dispose());
    },
  };
}
