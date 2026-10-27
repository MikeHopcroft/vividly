import { Slide } from '../../../../vividly/runtime/slide.js';

export const meta = {
  styles: ['./slide.css'],
};

const LISTS = {
  plastic: [
    'Aglet', 'Albolith', 'Aplastic', 'Archeus', 'Chicle', 'Coreplasty',
    'Cosmoplastic', 'Cuvette', 'Fictor', 'Flashing', 'Flexible', 'Flexile',
    'Food', 'Force', 'Formative', 'Galvanoplastic', 'Haemadynameter',
    'Helcoplasty', 'Imagination', 'Interpenetrate', 'Intrusion', 'Intrusive',
    'Labioplasty', 'Modeler', 'Modeling', 'Multiform', 'Organoleptic',
    'Pipe clay', 'Plastic', 'Plastical', 'Plastically', 'Plasticity',
    'Plastography', 'Pliant', 'Pug', 'Pugging', 'Pumice', 'Represent',
    'Rhinoplasty', 'Sculptor', 'Sculpture', 'Solid', 'Stomatoplasty', 'Tonic',
    'Uranoplasty', 'Wipe',
  ],
  shoelace: ['Aglet', 'Eyelet', 'Lace', 'Latchet', 'Tag'],
};

const ROW = 50;
const SCROLL_MS = 2600;
const EASE_POWER = 3;
const RIPPLE_MS = 14;

const key = (word) => word.toLowerCase();
const MERGED = [...new Set([...LISTS.plastic, ...LISTS.shoelace])]
  .sort((left, right) => key(left).localeCompare(key(right)));
const MERGED_ROW = Object.fromEntries(MERGED.map((word, index) => [word, index]));

const BUILD_OFFSETS = (() => {
  const count = LISTS.plastic.length;
  const buildCount = LISTS.shoelace.length;
  const timeAt = (position) => SCROLL_MS
    * (1 - Math.pow(1 - (position / count), 1 / EASE_POWER));
  const starts = Array.from(
    { length: buildCount },
    (_, index) => timeAt(count - buildCount + index),
  );
  return starts.map((time) => Math.round(time - starts[0]));
})();

export default class ConcordanceMerge extends Slide {
  preload() {
    return { steps: 5 };
  }

  mount(root) {
    root.innerHTML = `
      <div class="match-box"></div>
      <div class="heading plastic"><span>plastic</span> <small>46</small></div>
      <div class="heading shoelace"><span>shoelace</span> <small>5</small></div>
      <div class="clip plastic"></div>
      <div class="clip shoelace"></div>
    `;

    this.root = root;
    this.box = root.querySelector('.match-box');
    this.headings = {
      plastic: root.querySelector('.heading.plastic'),
      shoelace: root.querySelector('.heading.shoelace'),
    };
    this.clips = {
      plastic: root.querySelector('.clip.plastic'),
      shoelace: root.querySelector('.clip.shoelace'),
    };
    this.words = { plastic: [], shoelace: []     };
    this.reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
    this.buildWords();
    this.mounted = true;
  }

  buildWords() {
    for (const name of ['plastic', 'shoelace']) {
      const host = this.root.querySelector(`.clip.${name}`);
      LISTS[name].forEach((word, index) => {
        const element = document.createElement('div');
        element.className = 'word';
        element.textContent = word;
        element.dataset.own = index;
        element.dataset.merged = MERGED_ROW[word];
        element.style.opacity = 0;
        host.appendChild(element);
        this.words[name].push(element);
      });
    }
  }

  enter({ step }) {
    this.entered = true;
    if (this.step === undefined) {
      this.step = step;
      this.applyImmediate(step);
    }
  }

  setStep(step) {
    if (!this.mounted) {
      return;
    }

    const previous = this.step;
    this.step = step;
    if (previous === undefined || !this.entered) {
      this.applyImmediate(step);
      return;
    }

    this.applyAnimated(step, previous);
  }

  applyImmediate(step) {
    this.root.classList.add('instant');
    this.cancelCustomMotion();
    this.updateVisibility(step);

    if (step >= 1) {
      this.finishScroll();
    } else {
      this.hidePlastic();
    }

    if (step >= 2) {
      this.finishBuild();
    } else {
      this.hideShoelace();
    }

    this.place(step >= 3);
    this.box.classList.toggle('shown', step >= 4);

    void this.root.offsetHeight;
    this.root.classList.remove('instant');
  }

  applyAnimated(step, previous) {
    this.cancelCustomMotion();
    this.updateVisibility(step);

    if (step < 1) {
      this.hidePlastic();
    } else if (step === 1 && previous < 1) {
      this.startScroll();
    } else if (step >= 3) {
      this.showPlastic();
    } else {
      this.finishScroll();
    }

    if (step < 2) {
      this.hideShoelace();
    } else if (step === 2 && previous < 2) {
      this.startBuild();
    } else if (step >= 3) {
      this.showShoelace();
    } else {
      this.finishBuild();
    }

    const merged = step >= 3;
    const wasMerged = previous >= 3;
    if (merged !== wasMerged) {
      this.place(merged);
    }
    this.box.classList.toggle('shown', step >= 4);
  }

  updateVisibility(step) {
    const plasticVisible = step >= 1;
    const shoelaceVisible = step >= 2;
    this.headings.plastic.classList.add('shown');
    this.headings.shoelace.classList.toggle('shown', shoelaceVisible);
    this.headings.plastic.setAttribute('aria-hidden', 'false');
    this.headings.shoelace.setAttribute('aria-hidden', String(!shoelaceVisible));
    this.clips.plastic.setAttribute('aria-hidden', String(!plasticVisible));
    this.clips.shoelace.setAttribute('aria-hidden', String(!shoelaceVisible));
  }

  setScroll(position) {
    const count = LISTS.plastic.length;
    this.words.plastic.forEach((element, index) => {
      const reverseRank = count - 1 - index;
      const row = position - reverseRank - 1;
      const displayRow = index === 0 ? 0 : row;
      element.style.transform = `translateY(${displayRow * ROW}px)`;
      element.style.opacity = Math.max(0, Math.min(1, row + 1));
    });
  }

  startScroll() {
    this.words.plastic.forEach((element) => element.classList.remove('animated'));
    if (this.reduceMotion) {
      this.finishScroll();
      return;
    }

    this.scrollAnimating = true;
    const startedAt = performance.now();
    const tick = (now) => {
      const progress = Math.min(1, (now - startedAt) / SCROLL_MS);
      const position = LISTS.plastic.length
        * (1 - Math.pow(1 - progress, EASE_POWER));
      this.setScroll(position);
      if (progress < 1) {
        this.scrollFrame = requestAnimationFrame(tick);
      } else {
        this.finishScroll();
      }
    };
    this.scrollFrame = requestAnimationFrame(tick);
  }

  finishScroll() {
    cancelAnimationFrame(this.scrollFrame);
    this.scrollAnimating = false;
    this.setScroll(LISTS.plastic.length);
  }

  showPlastic() {
    cancelAnimationFrame(this.scrollFrame);
    this.scrollAnimating = false;
    this.words.plastic.forEach((element) => {
      element.style.opacity = 1;
    });
  }

  hidePlastic() {
    cancelAnimationFrame(this.scrollFrame);
    this.scrollAnimating = false;
    this.words.plastic.forEach((element) => {
      element.classList.remove('animated');
      element.style.opacity = 0;
    });
  }

  startBuild() {
    if (this.reduceMotion) {
      this.finishBuild();
      return;
    }

    this.buildAnimating = true;
    this.words.shoelace.forEach((element, index) => {
      element.classList.remove('animated');
      element.classList.add('building');
      element.style.transform = `translateY(${index * ROW}px)`;
      element.style.opacity = 0;
      const timer = setTimeout(() => {
        element.style.opacity = 1;
        if (index === this.words.shoelace.length - 1) {
          this.buildAnimating = false;
          this.buildTimers = [];
        }
      }, BUILD_OFFSETS[index]);
      this.buildTimers.push(timer);
    });
  }

  finishBuild() {
    this.clearBuildTimers();
    this.buildAnimating = false;
    this.words.shoelace.forEach((element, index) => {
      element.classList.remove('building');
      element.style.transform = `translateY(${index * ROW}px)`;
      element.style.opacity = 1;
    });
  }

  showShoelace() {
    this.clearBuildTimers();
    this.buildAnimating = false;
    this.words.shoelace.forEach((element) => {
      element.classList.remove('building');
      element.style.opacity = 1;
    });
  }

  hideShoelace() {
    this.clearBuildTimers();
    this.buildAnimating = false;
    this.words.shoelace.forEach((element) => {
      element.classList.remove('building');
      element.classList.add('animated');
      element.style.transitionDelay = '0ms, 0ms';
      element.style.opacity = 0;
    });
  }

  clearBuildTimers() {
    (this.buildTimers ?? []).forEach(clearTimeout);
    this.buildTimers = [];
  }

  place(merged) {
    const count = MERGED.length;
    for (const name of ['plastic', 'shoelace']) {
      this.words[name].forEach((element) => {
        const mergedIndex = Number(element.dataset.merged);
        const index = merged ? mergedIndex : Number(element.dataset.own);
        const delay = (merged ? count - 1 - mergedIndex : mergedIndex) * RIPPLE_MS;
        element.classList.remove('building');
        element.classList.add('animated');
        element.style.transitionDelay = `0ms, ${delay}ms`;
        element.style.transform = `translateY(${index * ROW}px)`;
      });
    }
  }

  settleStep() {
    if (this.scrollAnimating) {
      this.finishScroll();
      return true;
    }
    if (this.buildAnimating) {
      this.finishBuild();
      return true;
    }
    return false;
  }

  cancelCustomMotion() {
    cancelAnimationFrame(this.scrollFrame);
    this.scrollAnimating = false;
    this.clearBuildTimers();
    this.buildAnimating = false;
  }

  exit() {
    this.settleStep();
    this.entered = false;
  }

  unmount() {
    this.cancelCustomMotion();
    this.mounted = false;
  }
}
