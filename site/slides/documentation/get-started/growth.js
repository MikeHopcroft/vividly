const svgNamespace = 'http://www.w3.org/2000/svg';
const money = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 0,
});

export function mountGrowthDemo(host, { comparison, signal }) {
  host.innerHTML = `
    <div class="guide-demo-label">THE SLIDE YOU WILL MAKE</div>
    <h2>Small changes.<br>Growing differences.</h2>
    <p>$1,000 invested for five years. No extra deposits.</p>
    <svg viewBox="0 0 500 280" role="img" aria-label="Investment value over five years"></svg>
    <label class="guide-rate">Annual growth
      <output>8%</output>
      <input type="range" min="0" max="20" value="8" step="1" aria-label="Annual growth percentage">
    </label>
    <div class="guide-demo-total"><span>After five years</span><strong></strong></div>
    <p class="guide-demo-note"></p>`;
  const chart = host.querySelector('svg');
  const input = host.querySelector('input');
  const output = host.querySelector('output');
  const total = host.querySelector('.guide-demo-total strong');
  const note = host.querySelector('.guide-demo-note');
  const element = (tag, attributes, text) => {
    const node = document.createElementNS(svgNamespace, tag);
    for (const [name, value] of Object.entries(attributes)) node.setAttribute(name, value);
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const draw = () => {
    const rate = Number(input.value);
    const values = Array.from({ length: 6 }, (_, year) => 1000 * (1 + rate / 100) ** year);
    chart.replaceChildren();
    for (const value of [1000, 1500, 2000, 2500]) {
      const y = 232 - (value - 1000) / 1500 * 200;
      chart.append(element('line', { x1: 60, x2: 475, y1: y, y2: y, class: 'guide-gridline' }));
      chart.append(element('text', { x: 50, y: y + 4, 'text-anchor': 'end' }, money.format(value)));
    }
    for (let year = 0; year <= 5; year++) {
      chart.append(element('text', { x: 60 + year * 83, y: 260, 'text-anchor': 'middle' }, year));
    }
    if (comparison) {
      chart.append(element('line', { x1: 60, x2: 475, y1: 232, y2: 232, class: 'guide-baseline' }));
    }
    const points = values.map((value, year) => `${60 + year * 83},${232 - (value - 1000) / 1500 * 200}`);
    chart.append(element('polyline', { points: points.join(' '), class: 'guide-growth-line' }));
    const [cx, cy] = points.at(-1).split(',');
    chart.append(element('circle', { cx, cy, r: 5, class: 'guide-growth-dot' }));
    chart.setAttribute('aria-label', `At ${rate}% annual growth, $1,000 becomes ${money.format(values[5])} after five years.`);
    output.value = `${rate}%`;
    total.textContent = money.format(values[5]);
    note.textContent = comparison
      ? `Dashed line: $1,000 at 0% growth. Difference: ${money.format(values[5] - 1000)}.`
      : 'Try the slider. The rate changes; the scale stays fixed.';
  };
  input.addEventListener('input', draw, { signal });
  draw();
}
