// Manifest loading and flattening into an ordered list of addressable leaves.

export async function loadManifest(manifestUrl, yaml) {
  const response = await fetch(manifestUrl, { cache: 'no-cache' });
  if (!response.ok) throw new Error(`Cannot load manifest ${manifestUrl}`);
  const raw = yaml.load(await response.text());
  if (raw.dependencies !== undefined) {
    throw new Error(
      `Presentation manifest ${manifestUrl} cannot declare dependencies; declare them in catalog.yaml`
    );
  }
  const keyboardHints = raw.keyboardHints ?? 'auto';
  if (!['auto', 'always', 'never'].includes(keyboardHints)) {
    throw new Error(`Invalid keyboardHints policy "${keyboardHints}"`);
  }
  const nodes = await normalize(raw.nodes || [], manifestUrl, yaml);
  const index = indexPresentation(nodes);
  return {
    id: raw.id || new URL(manifestUrl).pathname,
    title: raw.title || 'Untitled',
    theme: raw.theme ? new URL(raw.theme, manifestUrl).href : null,
    transition: raw.transition || 'dissolve',
    keyboardHints,
    preloadWindow: { prev: 1, next: 1, ...(raw.preloadWindow || {}) },
    nodes,
    ...index,
  };
}

async function normalize(nodes, baseUrl, yaml) {
  const out = [];
  for (const node of nodes) {
    if (node.type === 'section') {
      out.push({
        ...node,
        children: await normalize(node.children || [], baseUrl, yaml),
      });
    } else if (node.type === 'presentation') {
      // Incorporation by reference, resolved at load time: manifests are cheap,
      // slide modules are not. See spec §6.
      const childUrl = new URL(node.manifest, baseUrl).href;
      const child = await loadManifest(childUrl, yaml);
      out.push({
        type: 'section',
        id: node.id,
        title: node.title || child.title,
        children: child.nodes,
      });
    } else {
      const moduleUrl = new URL(node.module, baseUrl).href;
      const dataUrl = node.data
        ? new URL(node.data.endsWith('/') ? node.data : `${node.data}/`, baseUrl).href
        : new URL('./', moduleUrl).href;
      out.push({ ...node, type: 'slide', moduleUrl, dataUrl });
    }
  }
  return out;
}

export function indexPresentation(nodes) {
  const leaves = [];
  const leavesByAddress = new Map();
  const sections = new Map();
  const navigators = new Map();
  const sectionOwners = new Map();

  const visit = (children, prefix = [], trail = [], parentAddress = null) => {
    for (const node of children) {
      const path = [...prefix, node.id];
      const address = path.join('/');
      const nodeTrail = [...trail, node];
      if (node.type === 'section') {
        const section = {
          node,
          address,
          title: node.title || node.id,
          parentAddress,
          firstLeafIndex: null,
          lastLeafIndex: null,
        };
        sections.set(address, section);
        const firstLeafIndex = leaves.length;
        visit(node.children, path, nodeTrail, address);
        if (leaves.length > firstLeafIndex) {
          section.firstLeafIndex = firstLeafIndex;
          section.lastLeafIndex = leaves.length - 1;
        }
      } else {
        const leaf = {
          node,
          address,
          title: node.title || node.id,
          trail: nodeTrail,
          sectionAddress: parentAddress,
        };
        leaves.push(leaf);
        leavesByAddress.set(address, leaf);
      }
    }
  };

  visit(nodes);

  for (const leaf of leaves) {
    const navigatorNode = leaf.node.navigator;
    const references = navigatorNode?.sections;
    if (references === undefined) continue;
    if (!Array.isArray(references) || references.length === 0) {
      throw new Error(`Navigator "${leaf.address}" must declare at least one section`);
    }
    const choiceStartStep = navigatorNode.choiceStartStep ?? 0;
    if (!Number.isInteger(choiceStartStep) || choiceStartStep < 0) {
      throw new Error(
        `Navigator "${leaf.address}" choiceStartStep must be a nonnegative integer`
      );
    }

    const navigatorSections = [];
    const seen = new Set();
    for (const [index, reference] of references.entries()) {
      if (typeof reference !== 'string' || !reference.startsWith('./')) {
        throw new Error(`Invalid navigator section "${reference}" on "${leaf.address}"`);
      }
      const relativeAddress = reference.slice(2);
      const segments = relativeAddress.split('/');
      if (segments.some((segment) => !segment || segment === '.' || segment === '..')) {
        throw new Error(`Invalid navigator section "${reference}" on "${leaf.address}"`);
      }
      const targetAddress = [leaf.sectionAddress, relativeAddress].filter(Boolean).join('/');
      if (seen.has(targetAddress)) {
        throw new Error(`Duplicate navigator section "${targetAddress}" on "${leaf.address}"`);
      }
      seen.add(targetAddress);

      const target = sections.get(targetAddress);
      if (!target) {
        if (leavesByAddress.has(targetAddress)) {
          throw new Error(`Navigator section "${reference}" targets slide "${targetAddress}"`);
        }
        throw new Error(`Unknown navigator section "${reference}" on "${leaf.address}"`);
      }
      if (target.parentAddress !== leaf.sectionAddress) {
        throw new Error(`Navigator section "${targetAddress}" is not a direct child of "${leaf.sectionAddress}"`);
      }
      if (target.firstLeafIndex === null) {
        throw new Error(`Navigator section "${targetAddress}" has no slides`);
      }
      if (sectionOwners.has(targetAddress)) {
        throw new Error(`Navigator section "${targetAddress}" is already owned`);
      }

      const step = choiceStartStep + index;
      navigatorSections.push({ address: target.address, title: target.title, step });
      sectionOwners.set(targetAddress, {
        navigatorAddress: leaf.address,
        choiceStep: step,
        entryAddress: leaves[target.firstLeafIndex].address,
        forwardRoute: { address: leaf.address, step: step + 1 },
        backwardRoute: { address: leaf.address, step },
      });
    }

    navigators.set(leaf.address, {
      address: leaf.address,
      sectionAddress: leaf.sectionAddress,
      choiceStartStep,
      afterStep: choiceStartStep + navigatorSections.length,
      sections: navigatorSections,
    });
  }

  return { leaves, leavesByAddress, sections, navigators, sectionOwners };
}

export function flattenLeaves(nodes) {
  return indexPresentation(nodes).leaves;
}
