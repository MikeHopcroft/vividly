"use strict";
importScripts("./training-core.js");

let runGeneration = 0;

self.onmessage = event => {
  const message = event.data;
  if (message.type === "start") start(message.config, ++runGeneration);
  else if (message.type === "stop") runGeneration += 1;
};

function copyParameters(model) {
  return {
    H: model.H,
    Wa: model.Wa.slice(),
    ba: model.ba.slice(),
    Wb: model.Wb.slice(),
    bb: model.bb.slice(),
  };
}

function start(config, generation) {
  const builtAt = performance.now();
  const data = TrainingCore.dataset();
  const model = TrainingCore.initialize(data.IN, config.H, data.OUT, config.seed);
  const work = TrainingCore.scratch(data.N, data.IN, config.H, data.OUT);
  const optimizer = TrainingCore.adam(model);
  const batches = TrainingCore.batcher(data.N, data.IN, (config.seed ^ 0x9e3779b9) >>> 0);
  const startedAt = performance.now();
  let epoch = 0;
  let loss = null;
  postMessage({ type: "meta", generation: config.generation, boards: data.N, buildMs: startedAt - builtAt });

  function finish({ perfect = false, stopped = false } = {}) {
    const result = TrainingCore.score(model, data, work, config.failingLimit);
    postMessage({
      type: "done",
      generation: config.generation,
      epoch,
      loss,
      failed: result.failed,
      pct: result.pct,
      perfect,
      stopped,
      elapsed: performance.now() - startedAt,
      params: copyParameters(model),
      failingBoards: result.failingBoards,
    });
  }

  function chunk() {
    if (generation !== runGeneration) {
      finish({ stopped: true });
      return;
    }
    const deadline = performance.now() + config.chunkMs;
    do {
      loss = TrainingCore.trainEpoch(model, data, work, batches, optimizer, config.batchSize);
      epoch += 1;
    } while (performance.now() < deadline && epoch < config.maxEpochs);
    const result = TrainingCore.score(model, data, work, config.failingLimit);
    postMessage({
      type: "progress",
      generation: config.generation,
      epoch,
      loss,
      failed: result.failed,
      pct: result.pct,
      elapsed: performance.now() - startedAt,
      params: copyParameters(model),
      failingBoards: result.failingBoards,
    });
    if (result.failed === 0 || epoch >= config.maxEpochs) {
      finish({ perfect: result.failed === 0 });
      return;
    }
    setTimeout(chunk, 0);
  }

  setTimeout(chunk, 0);
}
