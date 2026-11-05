import { Slide } from 'vividly/runtime/slide.js';
import {
  OWL_PATH, OWL_DRAW_DURATION, OWL_HOLD_DURATION, OWL_ALIGN_DURATION,
  sampleOwl, sliceOwl, projectOwl, easeInOutCubic,
} from '../../why-vividly/visual-promise/slide.js';

export const meta = {
  template: './slide.html',
  styles: ['./slide.css'],
  steps: 1,
};

const SVG_NS = 'http://www.w3.org/2000/svg';
let resourceSerial = 0;

export default class OwlLab extends Slide {
  mount(root) {
    this.root = root;
    this.events = new AbortController();
    this.frame = null;
    this.entered = false;
    this.penCount ??= 3;
    this.drawDuration ??= OWL_DRAW_DURATION;
    this.penInput = root.querySelector('[name="pens"]');
    this.durationInput = root.querySelector('[name="duration"]');
    this.penInput.value = String(this.penCount);
    this.durationInput.value = String(this.drawDuration / 1000);
    this.status = root.querySelector('[role="status"]');
    this.heading = root.querySelector('[data-multiple-heading]');
    const source = document.createElementNS(SVG_NS, 'path');
    source.setAttribute('d', OWL_PATH);
    this.points = sampleOwl(source);
    this.views = [...root.querySelectorAll('svg')].map((svg) => this.configureView(svg));
    const options = { signal: this.events.signal };
    for (const input of [this.penInput, this.durationInput]) {
      input.addEventListener('input', () => {
        if (!this.penInput.checkValidity() || !this.durationInput.checkValidity()) {
          this.stop();
          this.status.textContent = 'Enter a whole number of pens from 1 to 24 and a drawing time from 0.1 to 30 seconds.';
          return;
        }
        this.penCount = this.penInput.valueAsNumber;
        this.drawDuration = this.durationInput.valueAsNumber * 1000;
        if (this.entered) this.rerun();
      }, options);
    }
    root.querySelector('[data-rerun]').addEventListener('click', () => {
      if (!this.penInput.reportValidity() || !this.durationInput.reportValidity()) return;
      this.rerun();
    }, options);
    this.preparePens();
    this.render(0, 0);
  }

  configureView(svg) {
    const id = `owl-lab-${++resourceSerial}`;
    const gradient = svg.querySelector('linearGradient');
    const glow = svg.querySelector('filter');
    gradient.id = `${id}-light`;
    glow.id = `${id}-glow`;
    const body = svg.querySelector('.owl-body');
    body.style.stroke = `url("#${gradient.id}")`;
    svg.querySelector('.owl-glow').style.filter = `url("#${glow.id}")`;
    return {
      paths: [...svg.querySelectorAll('.owl-wire')],
      tipsRoot: svg.querySelector('.owl-tips'),
      tips: [],
    };
  }

  preparePens() {
    this.heading.textContent = `${this.penCount} ${this.penCount === 1 ? 'pen' : 'pens'}`;
    this.views.forEach((view, index) => {
      view.tipsRoot.replaceChildren();
      view.tips = Array.from({ length: index === 0 ? 1 : this.penCount }, () => {
        const tip = document.createElementNS(SVG_NS, 'circle');
        tip.setAttribute('r', '7');
        view.tipsRoot.append(tip);
        return tip;
      });
    });
  }

  enter() {
    this.entered = true;
    this.rerun();
  }

  rerun() {
    this.stop();
    this.preparePens();
    this.render(0, 0);
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      this.finish();
      return;
    }
    this.status.textContent = 'Drawing both owls';
    const startedAt = performance.now();
    const duration = this.drawDuration + OWL_HOLD_DURATION + OWL_ALIGN_DURATION;
    const tick = (time) => {
      const elapsed = Math.max(0, time - startedAt);
      const draw = Math.min(1, elapsed / this.drawDuration);
      const alignmentElapsed = elapsed - this.drawDuration - OWL_HOLD_DURATION;
      const alignment = easeInOutCubic(Math.max(0, Math.min(1, alignmentElapsed / OWL_ALIGN_DURATION)));
      this.render(draw, alignment);
      if (elapsed < duration) {
        this.frame = requestAnimationFrame(tick);
      } else {
        this.frame = null;
        this.status.textContent = 'Both owls complete';
      }
    };
    this.frame = requestAnimationFrame(tick);
  }

  render(draw, alignment) {
    const projected = this.points.map((point) => projectOwl(point, alignment));
    this.views.forEach((view) => {
      const count = view.tips.length;
      const drawing = draw > 0 && draw < 1;
      // Alternating directions preserve the original three-pen joins.
      const sections = drawing ? Array.from({ length: count }, (_, index) => {
        const start = index % 2 === 0 ? index / count : (index + 1) / count;
        const end = start + (index % 2 === 0 ? 1 : -1) * draw / count;
        return sliceOwl(projected, start, end);
      }) : [];
      const visible = draw === 1 ? [projected] : sections;
      const data = visible.map((section) => section.map(({ x, y }, index) =>
        `${index === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${y.toFixed(1)}`).join(' ')).join(' ');
      for (const path of view.paths) path.setAttribute('d', data);
      view.tips.forEach((tip, index) => {
        tip.style.opacity = drawing ? '1' : '0';
        if (!drawing) return;
        const endpoint = sections[index].at(-1);
        tip.setAttribute('cx', String(endpoint.x));
        tip.setAttribute('cy', String(endpoint.y));
      });
    });
  }

  finish() {
    this.stop();
    this.render(1, 1);
    this.status.textContent = 'Both owls complete';
  }

  settleStep() {
    if (this.frame === null) return false;
    this.finish();
    return true;
  }

  stop() {
    if (this.frame !== null) cancelAnimationFrame(this.frame);
    this.frame = null;
  }

  exit() {
    this.entered = false;
    this.stop();
  }

  unmount() {
    this.exit();
    this.events.abort();
  }
}
