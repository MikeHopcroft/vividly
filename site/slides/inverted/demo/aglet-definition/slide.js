import { Slide } from '../../../../vividly/runtime/slide.js';
import { loadLibreCaslonText } from '../../../../shared/libre-caslon-text.js';

export const meta = {
  styles: ['./slide.css'],
};

const LOOP = {
  start: [1.053, 0.1097],
  segments: [
    [[1.0425, 0.0987], [1.0136, 0.0616], [0.9897, 0.0438]],
    [[0.9658, 0.026], [0.9393, 0.0141], [0.9098, 0.0029]],
    [[0.8802, -0.0082], [0.8512, -0.016], [0.8124, -0.0231]],
    [[0.7735, -0.0303], [0.7575, -0.0368], [0.6767, -0.0399]],
    [[0.596, -0.0431], [0.4129, -0.0423], [0.3279, -0.042]],
    [[0.243, -0.0416], [0.213, -0.0424], [0.1671, -0.0378]],
    [[0.1212, -0.0332], [0.0857, -0.0267], [0.0523, -0.0144]],
    [[0.019, -0.0021], [-0.0095, 0.0139], [-0.0329, 0.0359]],
    [[-0.0564, 0.0578], [-0.0748, 0.0841], [-0.0884, 0.1171]],
    [[-0.102, 0.1501], [-0.1101, 0.1825], [-0.1145, 0.2339]],
    [[-0.1188, 0.2854], [-0.1181, 0.3382], [-0.1147, 0.4257]],
    [[-0.1114, 0.5132], [-0.103, 0.6835], [-0.0942, 0.759]],
    [[-0.0854, 0.8345], [-0.0749, 0.8447], [-0.0618, 0.8787]],
    [[-0.0487, 0.9127], [-0.0341, 0.9384], [-0.0157, 0.9629]],
    [[0.0026, 0.9873], [0.0226, 1.0079], [0.0481, 1.0254]],
    [[0.0736, 1.043], [0.1007, 1.0576], [0.1373, 1.0683]],
    [[0.174, 1.0791], [0.1874, 1.0874], [0.268, 1.09]],
    [[0.3486, 1.0927], [0.5309, 1.0882], [0.621, 1.084]],
    [[0.7111, 1.0799], [0.7582, 1.0738], [0.8085, 1.0652]],
    [[0.8588, 1.0565], [0.8892, 1.0458], [0.9227, 1.0323]],
    [[0.9561, 1.0187], [0.9835, 1.0033], [1.0092, 0.9838]],
    [[1.0349, 0.9643], [1.0575, 0.9432], [1.0768, 0.9152]],
    [[1.0962, 0.8872], [1.1132, 0.8592], [1.1255, 0.8157]],
    [[1.1377, 0.7723], [1.1471, 0.7443], [1.1503, 0.6543]],
    [[1.1534, 0.5643], [1.1508, 0.3625], [1.1445, 0.2759]],
    [[1.1382, 0.1893], [1.1274, 0.1723], [1.1125, 0.1348]],
    [[1.0976, 0.0974], [1.0775, 0.0734], [1.0551, 0.0511]],
    [[1.0327, 0.0287], [1.0065, 0.014], [0.9779, 0.0006]],
    [[0.9494, -0.0128], [0.9195, -0.0213], [0.8839, -0.0293]],
    [[0.8484, -0.0373], [0.7845, -0.0444], [0.7646, -0.0474]],
  ],
};

const escapeHtml = (value) => String(value)
  .replaceAll('&', '&amp;')
  .replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;');

const highlightTerms = (html) => html.replace(
  /\b(plastic|shoelace)\b/gi,
  (match, term) => `<mark class="${term.toLowerCase()}">${match}</mark>`,
);

const sensesTemplate = (senses) => senses
  .map((sense, index) => `
    <span class="sense sense-${index + 1}">
      ${highlightTerms(
    escapeHtml(sense).replace(/^(\d+\.)\s/, '<strong class="sense-number">$1</strong> '),
  )}
    </span>
  `)
  .join(' ');

const entryTemplate = (entry) => {
  const forms = entry.forms
    .map((form) => `<span class="headword">${escapeHtml(form)}</span>`)
    .join(', ');
  const etymology = entry.etym ? ` ${escapeHtml(entry.etym)}` : '';
  const label = entry.label
    ? ` <span class="label">${escapeHtml(entry.label)}</span>`
    : '';

  return `
    <p class="entry${entry.target ? ' target' : ''}">
      ${forms}, <span class="part-of-speech">${escapeHtml(entry.pos)}</span>${etymology}${label}
      ${sensesTemplate(entry.senses)}
    </p>
  `;
};

const point = (box, [horizontal, vertical]) => (
  `${(box.x + (horizontal * box.width)).toFixed(1)},${(box.y + (vertical * box.height)).toFixed(1)}`
);

export default class DictionaryPage extends Slide {
  async preload() {
    [this.page] = await Promise.all([
      this.ctx.load('./data/dictionary.json'),
      loadLibreCaslonText(this.ctx),
    ]);
    return { steps: 3 };
  }

  mount(root) {
    const columns = ['a', 'b', 'c']
      .map((column) => `
        <div class="dictionary-column">
          ${this.page.columns[column].map(entryTemplate).join('')}
        </div>
      `)
      .join('');

    root.innerHTML = `
      <article class="sheet" aria-label="Dictionary page ${this.page.page}">
        <header>
          <span>${escapeHtml(this.page.guideLeft)}</span>
          <strong>${this.page.page}</strong>
          <span>${escapeHtml(this.page.guideRight)}</span>
        </header>
        <div class="columns">${columns}</div>
        <svg class="loop" viewBox="0 0 1100 1500" aria-hidden="true">
          <defs>
            <filter id="aglet-felt-tip" x="-10%" y="-10%" width="120%" height="120%">
              <feTurbulence type="fractalNoise" baseFrequency="0.8" numOctaves="2" seed="7" result="grain"></feTurbulence>
              <feDisplacementMap in="SourceGraphic" in2="grain" scale="2.4" xChannelSelector="R" yChannelSelector="G" result="rough"></feDisplacementMap>
              <feTurbulence type="fractalNoise" baseFrequency="0.035" numOctaves="2" seed="3" result="ink"></feTurbulence>
              <feColorMatrix in="ink" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 -0.9 1.35" result="ink-alpha"></feColorMatrix>
              <feComposite in="rough" in2="ink-alpha" operator="in"></feComposite>
            </filter>
          </defs>
          <path filter="url(#aglet-felt-tip)"></path>
        </svg>
      </article>
    `;

    this.root = root;
    this.sheet = root.querySelector('.sheet');
    this.columns = root.querySelector('.columns');
    this.dictionaryColumns = [...root.querySelectorAll('.dictionary-column')];
    this.target = root.querySelector('.entry.target');
    this.path = root.querySelector('.loop path');
    this.resizeObserver = new ResizeObserver(() => this.layout());
    this.resizeObserver.observe(root);
    this.layoutTimer = setTimeout(() => this.layout(), 0);
  }

  fitColumns() {
    const available = this.sheet.clientHeight - this.columns.offsetTop - 60;
    let low = 6;
    let high = 30;

    for (let iteration = 0; iteration < 18; iteration += 1) {
      const middle = (low + high) / 2;
      this.columns.style.fontSize = `${middle}px`;
      if (this.dictionaryColumns.every((column) => column.scrollHeight <= available)) {
        low = middle;
      } else {
        high = middle;
      }
    }

    this.columns.style.fontSize = `${low}px`;
    this.columns.style.height = `${available}px`;
  }

  entryBox() {
    let x = 0;
    let y = 0;
    let element = this.target;
    while (element && element !== this.sheet) {
      x += element.offsetLeft;
      y += element.offsetTop;
      element = element.offsetParent;
    }
    return {
      x,
      y,
      width: this.target.offsetWidth,
      height: this.target.offsetHeight,
    };
  }

  layoutLoop(box = this.entryBox()) {
    if (!box.width || !box.height) {
      return;
    }
    const commands = LOOP.segments
      .map(([first, second, third]) => (
        ` C${point(box, first)} ${point(box, second)} ${point(box, third)}`
      ))
      .join('');
    this.path.setAttribute('d', `M${point(box, LOOP.start)}${commands}`);
    const length = this.path.getTotalLength();
    this.loopLength = length;
    this.path.style.strokeDasharray = `${length} ${length}`;
    this.root.style.setProperty('--loop-length', length);
    this.applyLoop();
  }

  updateView(box = this.entryBox()) {
    const width = this.root.clientWidth;
    const height = this.root.clientHeight;
    if (!width || !height || !box.width || !box.height) {
      return;
    }

    const fitScale = Math.min((height * 0.96) / 1500, (width * 0.96) / 1100);
    const fitX = (width - (1100 * fitScale)) / 2;
    const fitY = (height - (1500 * fitScale)) / 2;
    const zoomScale = Math.min(
      (width * 0.7) / box.width,
      (height * 0.7) / box.height,
    );
    const zoomX = (width / 2) - ((box.x + (box.width / 2)) * zoomScale);
    const zoomY = (height / 2) - ((box.y + (box.height / 2)) * zoomScale);

    this.root.style.setProperty('--fit-scale', fitScale);
    this.root.style.setProperty('--fit-x', `${fitX}px`);
    this.root.style.setProperty('--fit-y', `${fitY}px`);
    this.root.style.setProperty('--zoom-scale', zoomScale);
    this.root.style.setProperty('--zoom-x', `${zoomX}px`);
    this.root.style.setProperty('--zoom-y', `${zoomY}px`);
    this.view = {
      fit: { scale: fitScale, x: fitX, y: fitY },
      zoom: { scale: zoomScale, x: zoomX, y: zoomY },
    };
    this.applyView();
  }

  layout() {
    this.root.classList.add('instant-geometry');
    this.fitColumns();
    const box = this.entryBox();
    this.layoutLoop(box);
    this.updateView(box);
    void this.root.offsetHeight;
    this.root.classList.remove('instant-geometry');
    this.sheet.getAnimations().forEach((animation) => animation.cancel());
    this.path.getAnimations().forEach((animation) => animation.cancel());
  }

  applyView() {
    if (!this.view || this.step === undefined) {
      return;
    }
    const view = this.step === 0 ? this.view.fit : this.view.zoom;
    this.sheet.style.transform = `translate(${view.x}px, ${view.y}px) scale(${view.scale})`;
  }

  setStep(step) {
    this.step = step;
    this.applyView();
    this.applyLoop();
  }

  applyLoop() {
    if (!this.loopLength || this.step === undefined) {
      return;
    }
    this.path.style.strokeDashoffset = this.step === 0 ? this.loopLength : 0;
  }

  enter({ step }) {
    if (this.step === undefined) {
      this.step = step;
    }
    this.layout();
  }

  unmount() {
    clearTimeout(this.layoutTimer);
    this.resizeObserver.disconnect();
  }
}
