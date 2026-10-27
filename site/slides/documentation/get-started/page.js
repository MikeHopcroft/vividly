import { Slide } from 'vividly/runtime/slide.js';
import { documents, pages, walkthrough } from './pages.js';
import { mountGrowthDemo } from './growth.js';

export const meta = { styles: ['./page.css'], steps: 1 };

let arrivalHeading = null;

const agentIcon = `
  <svg class="guide-agent-icon" viewBox="0 0 48 48" fill="none" stroke="currentColor"
    stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">
    <path d="M24 7v7M7 25H4v10h3m34-10h3v10h-3"/>
    <circle cx="24" cy="5" r="2"/>
    <rect x="8" y="14" width="32" height="28" rx="7"/>
    <circle cx="18" cy="25" r="2"/><circle cx="30" cy="25" r="2"/>
    <path d="M18 34h12"/>
  </svg>`;

function agentReferenceAddresses(nodes, parent = '') {
  return nodes.flatMap(node => {
    const address = parent ? `${parent}/${node.id}` : node.id;
    return [
      ...(node.type === 'slide' && node.props?.agentNotice ? [address] : []),
      ...agentReferenceAddresses(node.children || [], address),
    ];
  });
}

export default class GettingStartedPage extends Slide {
  async preload() {
    this.page = pages.find(page => page.id === this.ctx.props.page);
    if (!this.page) throw new Error(`Unknown documentation page: ${this.ctx.props.page}`);
    this.tutorialStyle = Boolean(this.page.tutorial || this.page.id === 'agentic-start');
    this.agentNotice = this.ctx.props.agentNotice;
    if (this.agentNotice !== undefined) {
      const notice = this.agentNotice;
      if (!notice || typeof notice.href !== 'string' || !notice.href.trim()
        || typeof notice.linkText !== 'string' || !notice.linkText.trim()) {
        throw new Error(`Invalid agentNotice for ${this.page.id}: href and linkText must be nonempty strings`);
      }
      const url = new URL(notice.href, location.href);
      if (!['http:', 'https:'].includes(url.protocol)) {
        throw new Error(`Invalid agentNotice for ${this.page.id}: href must use HTTP, HTTPS, or a local route`);
      }
    }
    this.markdown = await this.ctx.load(this.page.source);
    if (this.page.id === 'documentation') {
      const manifest = await this.ctx.load('../../../presentations/vividly.yaml');
      this.agentReferences = new Set(agentReferenceAddresses(manifest.nodes));
    }
  }

  mount(root) {
    this.root = root;
    this.events = new AbortController();
    const { signal } = this.events;
    const index = walkthrough.indexOf(this.page);
    const agenticStart = this.page.id === 'agentic-start';
    root.innerHTML = `
      <section class="guide-shell">
        <header class="guide-topbar">
          <nav aria-label="Breadcrumb">
            <a href="#/vividly/opening">Vividly</a><span aria-hidden="true">/</span>
            <a class="guide-parent"></a>
          </nav>
          <a class="guide-doc-link"></a>
        </header>
        <div class="guide-scroll" tabindex="0" role="region" aria-label="Page content">
          <main class="guide-main">
            <div class="guide-context"></div>
            <h1></h1>
            <div class="guide-body">
              <article class="guide-article"><vividly-markdown></vividly-markdown></article>
            </div>
            <footer class="guide-footer" aria-label="Page navigation"></footer>
          </main>
        </div>
        <button class="guide-more" hidden>More below <span aria-hidden="true">&#8595;</span></button>
      </section>`;
    const shell = root.querySelector('.guide-shell');
    shell.classList.toggle('guide-tutorial', this.tutorialStyle);
    shell.classList.toggle('guide-walkthrough', Boolean(this.page.tutorial));
    this.scroll = root.querySelector('.guide-scroll');
    this.main = root.querySelector('main');
    this.more = root.querySelector('.guide-more');
    const parent = root.querySelector('.guide-parent');
    if (agenticStart) {
      parent.dataset.address = 'make-something/choose-your-path';
      parent.href = this.href(parent.dataset.address);
    } else {
      parent.dataset.page = this.page.tutorial ? 'overview' : 'documentation';
    }
    parent.textContent = this.page.tutorial || agenticStart ? 'Get Started' : 'Documentation';
    const other = root.querySelector('.guide-doc-link');
    other.dataset.page = this.page.tutorial ? 'documentation' : 'overview';
    other.textContent = this.page.tutorial ? 'Documentation' : 'Get Started';
    const context = root.querySelector('.guide-context');
    if (this.page.tutorial) {
      const details = document.createElement('details');
      details.className = 'guide-progress';
      const summary = document.createElement('summary');
      summary.textContent = `${index + 1} of ${walkthrough.length} · ${this.page.short}`;
      const nav = document.createElement('nav');
      nav.setAttribute('aria-label', 'Walkthrough pages');
      walkthrough.forEach((page, number) => {
        const link = this.link(page, `${number + 1}. ${page.short}`);
        if (page === this.page) link.setAttribute('aria-current', 'page');
        nav.append(link);
      });
      details.append(summary, nav);
      context.append(details);
      const sidebar = nav.cloneNode(true);
      sidebar.className = 'guide-sidebar';
      sidebar.setAttribute('aria-label', 'Guided introduction steps');
      const heading = document.createElement('p');
      heading.textContent = 'Guided introduction';
      sidebar.prepend(heading);
      shell.insertBefore(sidebar, this.scroll);
    } else if (agenticStart) {
      const link = document.createElement('a');
      link.dataset.address = 'make-something/choose-your-path';
      link.href = this.href(link.dataset.address);
      link.textContent = 'GET STARTED / FULLY AGENTIC';
      context.append(link);
    } else {
      context.append(this.link(documents[0], 'DOCUMENTATION'));
      if (this.page.reference) context.append(' / VERSION-MATCHED REFERENCE');
    }
    root.querySelector('h1').textContent = this.page.title;
    if (this.agentNotice) this.mountAgentNotice();
    if (this.page.demo) {
      const aside = document.createElement('aside');
      aside.className = 'guide-demo';
      aside.setAttribute('aria-label', 'Working compound-growth example');
      root.querySelector('.guide-body').append(aside);
      root.querySelector('.guide-body').classList.add('guide-with-demo');
      mountGrowthDemo(aside, { comparison: this.page.id === 'refine', signal });
    }
    const footer = root.querySelector('.guide-footer');
    if (this.page.tutorial) {
      if (index > 0) footer.append(this.link(walkthrough[index - 1], `← ${walkthrough[index - 1].short}`));
      else footer.append(this.link(documents[0], 'Browse documentation'));
      const next = walkthrough[index + 1] || documents[0];
      const link = this.link(next, index === walkthrough.length - 1 ? 'Explore the documentation →' : `Next: ${next.short} →`);
      link.className = 'guide-next';
      footer.append(link);
    } else if (agenticStart) {
      const back = document.createElement('a');
      back.dataset.address = 'make-something/choose-your-path';
      back.href = this.href(back.dataset.address);
      back.textContent = '← Choose your starting path';
      footer.append(back);
      footer.append(this.link(walkthrough[0], 'Prefer the guided introduction? →'));
    } else {
      footer.append(this.link(documents[0], '← Documentation'));
      footer.append(this.link(walkthrough[0], 'Make your first slide →'));
    }
    root.querySelectorAll('[data-page]').forEach(anchor => {
      const page = pages.find(page => page.id === anchor.dataset.page);
      anchor.href = this.href(page.address);
    });
    this.viewer = root.querySelector('vividly-markdown');
    this.viewer.addEventListener('vividly-rendered', () => this.decorateContent(), { signal });
    this.viewer.baseUrl = this.ctx.asset(this.page.source);
    this.viewer.highlight = true;
    this.viewer.value = this.markdown;
    root.addEventListener('click', event => this.handleClick(event), { signal });
    this.scroll.addEventListener('scroll', () => this.updateOverflow(), { signal, passive: true });
    this.more.addEventListener('click', () => this.scroll.scrollBy({
      top: this.scroll.clientHeight * 0.7,
      behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth',
    }), { signal });
    this.observer = new ResizeObserver(() => this.updateOverflow());
    this.observer.observe(this.scroll);
    this.observer.observe(this.main);
  }

  mountAgentNotice() {
    const aside = document.createElement('aside');
    aside.className = 'guide-agent-notice';
    aside.setAttribute('aria-label', 'Documentation for coding agents');
    aside.innerHTML = `
      ${agentIcon}
      <div>
        <h2>Documentation for coding agents</h2>
        <p>This reference provides implementation details for coding agents working with Vividly.</p>
        <p class="guide-agent-destination">Looking for the guided workflow? <a></a></p>
      </div>`;
    const anchor = aside.querySelector('a');
    anchor.setAttribute('href', this.agentNotice.href);
    anchor.textContent = this.agentNotice.linkText;
    const destination = pages.find(page => this.href(page.address) === this.agentNotice.href);
    if (destination) anchor.dataset.address = destination.address;
    this.root.querySelector('h1').after(aside);
  }

  href(address) {
    const presentation = location.hash.split('/')[1];
    return `#/${presentation}/${address}`;
  }

  link(page, text) {
    const anchor = document.createElement('a');
    anchor.href = this.href(page.address);
    anchor.dataset.address = page.address;
    anchor.textContent = text;
    return anchor;
  }

  decorateContent() {
    this.viewer.querySelector('h1')?.remove();
    this.viewer.querySelectorAll('h2, h3, h4').forEach(heading => {
      const fragment = heading.dataset.fragment || heading.id || heading.textContent.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
      heading.dataset.fragment = fragment;
      heading.id = `guide-${this.ctx.address.replaceAll('/', '-')}-${fragment}`;
    });
    this.viewer.querySelectorAll('a').forEach(anchor => {
      const href = anchor.getAttribute('href');
      if (href.startsWith('#/')) {
        const address = href.slice(2);
        anchor.href = this.href(address);
        anchor.dataset.address = address;
      } else if (!href.startsWith('#')) {
        const url = new URL(href, this.ctx.asset(this.page.source));
        const reference = documents.find(page => page.reference && new URL(this.ctx.asset(page.source)).pathname === url.pathname);
        if (reference) {
          anchor.href = this.href(reference.address);
          anchor.dataset.address = reference.address;
          if (url.hash) anchor.dataset.fragment = url.hash.slice(1);
        }
      }
      if (this.agentReferences?.has(anchor.dataset.address) && !anchor.classList.contains('guide-agent-reference')) {
        anchor.classList.add('guide-agent-reference');
        anchor.setAttribute('aria-label', `${anchor.textContent} (Agent reference)`);
        anchor.title = 'Agent reference';
        anchor.insertAdjacentHTML('afterbegin', agentIcon);
      }
    });
    this.updateOverflow();
  }

  handleClick(event) {
    const anchor = event.target.closest('a');
    if (!anchor || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const address = anchor.dataset.address || pages.find(page => page.id === anchor.dataset.page)?.address;
    if (address) {
      event.preventDefault();
      if (anchor.dataset.fragment) {
        if (address === this.ctx.address) {
          this.scrollToHeading(anchor.dataset.fragment);
          return;
        }
        arrivalHeading = { address, fragment: anchor.dataset.fragment };
      } else {
        arrivalHeading = null;
      }
      this.ctx.navigate(address);
    } else if (anchor.getAttribute('href').startsWith('#') && !anchor.getAttribute('href').startsWith('#/')) {
      event.preventDefault();
      this.scrollToHeading(anchor.getAttribute('href').slice(1));
    }
  }

  scrollToHeading(fragment) {
    const heading = [...this.viewer.querySelectorAll('[data-fragment]')].find(node => node.dataset.fragment === fragment);
    heading?.scrollIntoView({ block: 'start' });
  }

  updateOverflow() {
    this.more.hidden = this.scroll.scrollHeight - this.scroll.clientHeight - this.scroll.scrollTop < 24;
  }

  enter() {
    this.scroll.scrollTop = 0;
    const heading = arrivalHeading;
    arrivalHeading = null;
    this.frame = requestAnimationFrame(() => {
      if (heading?.address === this.ctx.address) {
        this.scrollToHeading(heading.fragment);
      }
      this.updateOverflow();
    });
  }

  unmount() {
    this.events.abort();
    this.observer.disconnect();
    cancelAnimationFrame(this.frame);
    this.viewer = null;
    this.root = null;
  }
}
