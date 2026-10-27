export const walkthrough = [
  { id: 'overview', title: 'Your first interactive slide', short: 'What we will make', demo: true },
  { id: 'install', title: 'Install Vividly', short: 'Install' },
  { id: 'provision', title: 'Create a new Vividly Project'  , short: 'Create Project' },
  { id: 'prompt', title: 'Ask your agent', short: 'First prompt' },
  { id: 'preview', title: 'See it work', short: 'Preview', demo: true },
  { id: 'refine', title: 'Make one improvement', short: 'Refine', demo: true },
  { id: 'present', title: 'Present your slide', short: 'Present' },
  { id: 'publish', title: 'Publish and share', short: 'Publish' },
].map(page => ({
  ...page,
  address: `make-something/get-started/${page.id}`,
  source: `./content/${page.id}.md`,
  tutorial: true,
}));

export const documents = [
  { id: 'documentation', title: 'Documentation', address: 'documentation/overview' },
  { id: 'agent-session', title: 'Inside an agent session' },
  { id: 'troubleshooting', title: 'Getting unstuck' },
  { id: 'customize', title: 'Customize and extend' },
  { id: 'authoring', title: 'Authoring slides', reference: 'authoring.md' },
  { id: 'slides', title: 'Slide model', reference: 'slides.md' },
  { id: 'controls', title: 'Built-in controls', reference: 'controls.md' },
  { id: 'keyboard', title: 'Present and navigate', reference: 'keyboard.md' },
  { id: 'publishing', title: 'Publishing', reference: 'publishing.md' },
  { id: 'dependencies', title: 'Browser dependencies', reference: 'dependencies.md' },
  { id: 'cli', title: 'Command line', reference: 'cli.md' },
  { id: 'why-vividly-long-form', title: 'Why Vividly? — Long form', source: '../../make-something/further-reading/why-vividly.md' },
  { id: 'the-case-for-vividly', title: 'The case for Vividly', source: '../../make-something/further-reading/the-case-for-vividly.md' },
  { id: 'agentic', title: 'Documentation for coding agents', reference: 'agentic.md' },
  { id: 'agentic-bootstrap', title: 'Agentic bootstrap', reference: 'agentic-bootstrap.md' },
  { id: 'agentic-start', title: 'Start with your agent', address: 'make-something/agentic/bootstrap' },
].map(page => ({
  ...page,
  address: page.address || `documentation/${page.id}`,
  source: page.source || (page.reference ? `../../../reference/${page.reference}` : `./content/${page.id}.md`),
}));

export const pages = [...walkthrough, ...documents];
