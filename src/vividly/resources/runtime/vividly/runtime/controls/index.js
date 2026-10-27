import { VividlyAnnotatedMarkdown } from './annotated-markdown.js';
import { VividlyAdvance } from './advance.js';
import { VividlyCode } from './code.js';
import { VividlyImage } from './image.js';
import { VividlyMarkdown } from './markdown.js';
import { VividlyStepProgress } from './step-progress.js';
import { VividlyThumbnail } from './thumbnail.js';

customElements.define('vividly-annotated-markdown', VividlyAnnotatedMarkdown);
customElements.define('vividly-advance', VividlyAdvance);
customElements.define('vividly-code', VividlyCode);
customElements.define('vividly-image', VividlyImage);
customElements.define('vividly-markdown', VividlyMarkdown);
customElements.define('vividly-step-progress', VividlyStepProgress);
customElements.define('vividly-thumbnail', VividlyThumbnail);