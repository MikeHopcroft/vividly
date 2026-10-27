export function createPresentationDirector({ scenes, initialScene = null, onChange = () => {} }) {
  const sceneMap = new Map();
  for (const scene of scenes) {
    if (!scene?.id || sceneMap.has(scene.id)) throw new Error("Presentation scenes require unique ids");
    sceneMap.set(scene.id, scene);
  }
  if (!sceneMap.size) throw new Error("Presentation director requires at least one scene");
  if (initialScene !== null && !sceneMap.has(initialScene)) throw new RangeError(`Unknown initial scene: ${initialScene}`);

  let currentId = initialScene;
  let transitioning = false;
  let generation = 0;
  let activeTransition = null;

  function current() {
    return currentId === null ? null : sceneMap.get(currentId);
  }

  function state() {
    const scene = current();
    return {
      scene: currentId,
      transitioning,
      generation,
      sceneState: scene?.state?.() ?? null,
    };
  }

  function emit() {
    onChange(state());
  }

  async function goTo(id, options = {}) {
    if (!sceneMap.has(id)) throw new RangeError(`Unknown presentation scene: ${id}`);
    if (transitioning || id === currentId) return false;
    const from = currentId;
    const target = sceneMap.get(id);
    const activeGeneration = ++generation;
    transitioning = true;
    activeTransition = { from, target, direction: Math.sign(Number(options.direction) || 0) };
    emit();
    try {
      const entered = await target.enter?.({ from, ...options });
      if (activeGeneration !== generation) return false;
      if (entered === false) {
        transitioning = false;
        activeTransition = null;
        emit();
        return false;
      }
      currentId = id;
      transitioning = false;
      activeTransition = null;
      emit();
      return true;
    } catch (error) {
      if (activeGeneration === generation) {
        transitioning = false;
        activeTransition = null;
        emit();
      }
      throw error;
    }
  }

  function invoke(method) {
    if (transitioning) {
      const sameDirection = method === "next"
        ? activeTransition?.direction >= 0
        : method === "previous" && activeTransition?.direction < 0;
      if (method === "finish" || sameDirection) {
        activeTransition?.target.finish?.();
        return true;
      }
      if (method === "next" || method === "previous" || method === "cancel") {
        const transition = activeTransition;
        generation += 1;
        transitioning = false;
        activeTransition = null;
        transition?.target.cancel?.();
        emit();
        return true;
      }
      return false;
    }
    const handler = current()?.[method];
    return handler ? handler() !== false : false;
  }

  function setScene(id) {
    if (!sceneMap.has(id)) throw new RangeError(`Unknown presentation scene: ${id}`);
    if (transitioning) {
      const transition = activeTransition;
      generation += 1;
      transitioning = false;
      activeTransition = null;
      transition?.target.cancel?.();
    }
    const changed = currentId !== id;
    currentId = id;
    emit();
    return changed;
  }

  return Object.freeze({
    goTo,
    setScene,
    next: () => invoke("next"),
    previous: () => invoke("previous"),
    finish: () => invoke("finish"),
    cancel: () => invoke("cancel"),
    state,
    scenes: () => [...sceneMap.keys()],
  });
}
