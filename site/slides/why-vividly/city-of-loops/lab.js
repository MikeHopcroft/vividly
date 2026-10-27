import { Slide } from 'vividly/runtime/slide.js';
import { createCityRenderer } from './engine.js';
import { cityTransform, SKETCH_STROKES } from './sketch.js';

export const meta = { template: './lab.html', styles: ['./lab.css'], steps: 1 };
const SVG_NS = 'http://www.w3.org/2000/svg';

export default class CityLoopsLab extends Slide {
  mount(root) {
    this.root = root;
    this.disposed = false;
    this.loadVersion = 0;
    this.lab = root.querySelector('.loops-lab');
    this.canvas = root.querySelector('canvas');
    this.renderer = createCityRenderer(this.canvas, { composition: true, reducedMotion: true });
    this.svg = root.querySelector('.sketch-layer');
    this.labels = root.querySelector('.labels-layer');
    this.imported = root.querySelector('.imported-layer');
    this.error = root.querySelector('[role="alert"]');
    const transform = cityTransform(1920, 1080);
    for (const stroke of SKETCH_STROKES) {
      const points = stroke.points.map(([x, y]) => [
        transform.ox + x * transform.scale,
        transform.oy + y * transform.scale,
      ]);
      const path = document.createElementNS(SVG_NS, 'path');
      path.id = stroke.id;
      path.setAttribute('d', points.map(([x, y], index) => (
        `${index ? 'L' : 'M'}${x.toFixed(2)},${y.toFixed(2)}`
      )).join(' '));
      path.setAttribute('opacity', stroke.alpha);
      this.svg.append(path);
      if (stroke.id.endsWith('-arrow')) continue;
      const label = document.createElementNS(SVG_NS, 'text');
      const point = points[Math.floor(points.length * .4)];
      label.setAttribute('x', point[0]);
      label.setAttribute('y', point[1] - 12);
      label.textContent = stroke.id;
      this.labels.append(label);
    }
    this.events = new AbortController();
    const options = { signal: this.events.signal };
    root.querySelectorAll('[data-layer]').forEach(input => {
      const update = () => {
        root.querySelector(input.dataset.layer).style.opacity = input.value;
      };
      input.addEventListener('input', update, options);
      update();
    });
    root.querySelectorAll('[data-toggle]').forEach(input => {
      input.addEventListener('change', () => {
        root.querySelector(input.dataset.toggle).toggleAttribute('hidden', !input.checked);
      }, options);
    });
    root.querySelector('[name="svg"]').addEventListener('change', event => {
      this.loadSVG(event.target.files[0]);
    }, options);
    root.querySelector('.clear-svg').addEventListener('click', () => {
      this.clearSVG();
      root.querySelector('[name="svg"]').value = '';
    }, options);
    root.querySelector('.clean-button').addEventListener('click', () => {
      this.lab.classList.add('is-clean');
      this.lab.focus();
    }, options);
    root.querySelector('.restore-button').addEventListener('click', () => {
      this.lab.classList.remove('is-clean');
      root.querySelector('.clean-button').focus();
    }, options);
    root.querySelector('.download-button').addEventListener('click', () => {
      const svg = this.svg.cloneNode(true);
      svg.setAttribute('xmlns', SVG_NS);
      svg.setAttribute('width', '1920');
      svg.setAttribute('height', '1080');
      svg.setAttribute('fill', 'none');
      svg.setAttribute('stroke', '#ff5a52');
      svg.setAttribute('stroke-width', '4.86');
      svg.setAttribute('stroke-linecap', 'round');
      svg.setAttribute('stroke-linejoin', 'round');
      svg.removeAttribute('style');
      const url = URL.createObjectURL(new Blob(
        [new XMLSerializer().serializeToString(svg)], { type: 'image/svg+xml' },
      ));
      const link = document.createElement('a');
      link.href = url;
      link.download = 'city-of-loops-sketch.svg';
      link.click();
      URL.revokeObjectURL(url);
    }, options);
  }

  async loadSVG(file) {
    if (!file) return;
    const version = ++this.loadVersion;
    this.error.textContent = '';
    const text = await file.text().catch(error => {
      if (!this.disposed && version === this.loadVersion) {
        this.error.textContent = `Could not read SVG: ${error.message}`;
      }
      return null;
    });
    if (this.disposed || version !== this.loadVersion || text === null) return;
    const document = new DOMParser().parseFromString(text, 'image/svg+xml');
    const svg = document.documentElement;
    const viewBox = svg.getAttribute('viewBox')?.trim().split(/[\s,]+/).map(Number);
    if (document.querySelector('parsererror') || svg.localName !== 'svg'
      || !viewBox || viewBox.length !== 4
      || viewBox.some((value, index) => value !== [0, 0, 1920, 1080][index])) {
      this.error.textContent = 'Use a valid SVG with viewBox="0 0 1920 1080". The previous overlay is unchanged.';
      return;
    }
    this.clearSVG();
    this.objectURL = URL.createObjectURL(new Blob([text], { type: 'image/svg+xml' }));
    this.imported.onload = () => { this.imported.hidden = false; };
    this.imported.onerror = () => {
      this.error.textContent = 'The SVG could not be rendered. Check the file and try again.';
      this.clearSVG();
    };
    this.imported.src = this.objectURL;
  }

  clearSVG() {
    this.loadVersion += 1;
    this.imported.onload = null;
    this.imported.onerror = null;
    this.imported.hidden = true;
    this.imported.removeAttribute('src');
    if (this.objectURL) URL.revokeObjectURL(this.objectURL);
    this.objectURL = null;
  }

  enter() {
    this.renderer.start();
    this.renderer.stop();
  }

  unmount() {
    this.disposed = true;
    this.events.abort();
    this.clearSVG();
    this.renderer.destroy();
  }
}
