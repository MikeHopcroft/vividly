/* Worker-only MLP training core. Storage: Wa[IN,H], Wb[H,OUT], row-major. */
(function () {
  "use strict";
  function rng(seed) {
    let state = seed | 0;
    return () => {
      state = (state + 0x6D2B79F5) | 0;
      let value = Math.imul(state ^ (state >>> 15), 1 | state);
      value = (value + Math.imul(value ^ (value >>> 7), 61 | value)) ^ value;
      return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
    };
  }
  function gaussian(random) {
    return scale => {
      let u = 0, v = 0;
      while (!u) u = random();
      while (!v) v = random();
      return scale * Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
    };
  }
  function initialize(IN, H, OUT, seed) {
    const sample = gaussian(rng(seed >>> 0));
    const Wa = new Float32Array(IN * H), Wb = new Float32Array(H * OUT);
    for (let i = 0; i < Wa.length; i += 1) Wa[i] = sample(Math.sqrt(2 / IN));
    for (let i = 0; i < Wb.length; i += 1) Wb[i] = sample(Math.sqrt(2 / H));
    return { IN, H, OUT, Wa, ba: new Float32Array(H), Wb, bb: new Float32Array(OUT) };
  }
  function scratch(N, IN, H, OUT) {
    return {
      Z1: new Float32Array(N * H), A1: new Float32Array(N * H), P: new Float32Array(N * OUT),
      dZ2: new Float32Array(N * OUT), dZ1: new Float32Array(N * H),
      dWa: new Float32Array(IN * H), dba: new Float32Array(H),
      dWb: new Float32Array(H * OUT), dbb: new Float32Array(OUT),
    };
  }
  function forward(model, X, N, work) {
    const { IN, H, OUT, Wa, ba, Wb, bb } = model;
    const { Z1, A1, P } = work;
    for (let n = 0; n < N; n += 1) {
      const xb = n * IN, hb = n * H, ob = n * OUT;
      for (let h = 0; h < H; h += 1) Z1[hb + h] = ba[h];
      for (let i = 0; i < IN; i += 1) {
        if (!X[xb + i]) continue;
        for (let h = 0; h < H; h += 1) Z1[hb + h] += Wa[i * H + h];
      }
      for (let h = 0; h < H; h += 1) A1[hb + h] = Math.max(0, Z1[hb + h]);
      for (let o = 0; o < OUT; o += 1) P[ob + o] = bb[o];
      for (let h = 0; h < H; h += 1) {
        const activation = A1[hb + h];
        if (!activation) continue;
        for (let o = 0; o < OUT; o += 1) P[ob + o] += activation * Wb[h * OUT + o];
      }
      let maximum = -Infinity;
      for (let o = 0; o < OUT; o += 1) maximum = Math.max(maximum, P[ob + o]);
      let sum = 0;
      for (let o = 0; o < OUT; o += 1) { P[ob + o] = Math.exp(P[ob + o] - maximum); sum += P[ob + o]; }
      for (let o = 0; o < OUT; o += 1) P[ob + o] /= sum;
    }
  }
  function adam(model) {
    const zeros = values => new Float32Array(values.length);
    return { t: 0, mWa: zeros(model.Wa), vWa: zeros(model.Wa), mba: zeros(model.ba), vba: zeros(model.ba), mWb: zeros(model.Wb), vWb: zeros(model.Wb), mbb: zeros(model.bb), vbb: zeros(model.bb) };
  }
  function update(weights, gradients, moments, variances, step) {
    const b1 = .9, b2 = .999, correction1 = 1 - b1 ** (step + 1), correction2 = 1 - b2 ** (step + 1);
    for (let i = 0; i < weights.length; i += 1) {
      moments[i] = b1 * moments[i] + (1 - b1) * gradients[i];
      variances[i] = b2 * variances[i] + (1 - b2) * gradients[i] ** 2;
      weights[i] -= .003 * (moments[i] / correction1) / (Math.sqrt(variances[i] / correction2) + 1e-8);
    }
  }
  function trainBatch(model, X, y, N, work, optimizer) {
    const { IN, H, OUT, Wb } = model;
    forward(model, X, N, work);
    const { Z1, A1, P, dZ2, dZ1, dWa, dba, dWb, dbb } = work;
    dWa.fill(0); dba.fill(0); dWb.fill(0); dbb.fill(0);
    let loss = 0;
    for (let n = 0; n < N; n += 1) {
      const ob = n * OUT, target = y[n];
      loss -= Math.log(P[ob + target] + 1e-9);
      for (let o = 0; o < OUT; o += 1) {
        const gradient = (P[ob + o] - (o === target ? 1 : 0)) / N;
        dZ2[ob + o] = gradient; dbb[o] += gradient;
      }
    }
    for (let n = 0; n < N; n += 1) {
      const hb = n * H, ob = n * OUT;
      for (let h = 0; h < H; h += 1) {
        const activation = A1[hb + h];
        if (activation) for (let o = 0; o < OUT; o += 1) dWb[h * OUT + o] += activation * dZ2[ob + o];
        let gradient = 0;
        if (Z1[hb + h] > 0) for (let o = 0; o < OUT; o += 1) gradient += dZ2[ob + o] * Wb[h * OUT + o];
        dZ1[hb + h] = gradient;
        dba[h] += gradient;
      }
    }
    for (let n = 0; n < N; n += 1) {
      const xb = n * IN, hb = n * H;
      for (let i = 0; i < IN; i += 1) if (X[xb + i]) for (let h = 0; h < H; h += 1) dWa[i * H + h] += dZ1[hb + h];
    }
    update(model.Wa, dWa, optimizer.mWa, optimizer.vWa, optimizer.t);
    update(model.ba, dba, optimizer.mba, optimizer.vba, optimizer.t);
    update(model.Wb, dWb, optimizer.mWb, optimizer.vWb, optimizer.t);
    update(model.bb, dbb, optimizer.mbb, optimizer.vbb, optimizer.t);
    optimizer.t += 1;
    return loss / N;
  }
  function batcher(N, IN, seed) {
    const order = new Int32Array(N);
    for (let i = 0; i < N; i += 1) order[i] = i;
    return { order, random: rng((seed >>> 0) || 1), X: new Float32Array(N * IN), y: new Int32Array(N) };
  }
  function trainEpoch(model, data, work, batches, optimizer, batchSize) {
    const { order, random, X, y } = batches;
    for (let i = data.N - 1; i > 0; i -= 1) {
      const j = (random() * (i + 1)) | 0;
      const value = order[i]; order[i] = order[j]; order[j] = value;
    }
    let loss = 0;
    for (let start = 0; start < data.N; start += batchSize) {
      const count = Math.min(batchSize, data.N - start);
      for (let row = 0; row < count; row += 1) {
        const sourceRow = order[start + row];
        y[row] = data.y[sourceRow];
        X.set(data.X.subarray(sourceRow * data.IN, (sourceRow + 1) * data.IN), row * data.IN);
      }
      loss = trainBatch(model, X, y, count, work, optimizer);
    }
    return loss;
  }
  const lines = [[0,1,2],[3,4,5],[6,7,8],[0,3,6],[1,4,7],[2,5,8],[0,4,8],[2,4,6]];
  const powers = [1,3,9,27,81,243,729,2187,6561];
  function winner(board) { for (const [a,b,c] of lines) if (board[a] && board[a] === board[b] && board[a] === board[c]) return board[a]; return 0; }
  function player(board) { let count = 0; for (const cell of board) if (cell) count += 1; return count % 2 ? 2 : 1; }
  function pack(board) { let key = 0; for (let i = 0; i < 9; i += 1) key += board[i] * powers[i]; return key; }
  function dataset() {
    const memo = new Int8Array(19683), solveBoard = new Int8Array(9);
    function solve() {
      const key = pack(solveBoard), known = memo[key];
      if (known) return known - 2;
      if (winner(solveBoard)) { memo[key] = 1; return -1; }
      if (!solveBoard.includes(0)) { memo[key] = 2; return 0; }
      const turn = player(solveBoard); let best = -2;
      for (let i = 0; i < 9; i += 1) if (!solveBoard[i]) { solveBoard[i] = turn; best = Math.max(best, -solve()); solveBoard[i] = 0; }
      memo[key] = best + 2; return best;
    }
    const visited = new Uint8Array(19683), keys = [], board = new Int8Array(9);
    function visit() {
      const key = pack(board); if (visited[key]) return; visited[key] = 1;
      if (winner(board) || !board.includes(0)) return;
      keys.push(key); const turn = player(board);
      for (let i = 0; i < 9; i += 1) if (!board[i]) { board[i] = turn; visit(); board[i] = 0; }
    }
    visit(); keys.sort((a,b) => a-b);
    const N = keys.length, X = new Float32Array(N * 27), y = new Int32Array(N), optimal = new Uint8Array(N * 9), boards = new Array(N);
    for (let n = 0; n < N; n += 1) {
      let key = keys[n]; const current = new Int8Array(9);
      for (let i = 0; i < 9; i += 1) { current[i] = key % 3; key = (key / 3) | 0; X[n * 27 + i * 3 + current[i]] = 1; solveBoard[i] = current[i]; }
      boards[n] = current;
      const turn = player(current), value = solve();
      for (let i = 0; i < 9; i += 1) if (!current[i]) { solveBoard[i] = turn; const result = -solve(); solveBoard[i] = 0; if (result === value) { optimal[n * 9 + i] = 1; if (y[n] === 0 && !optimal[n * 9]) y[n] = i; } }
      for (let i = 0; i < 9; i += 1) if (optimal[n * 9 + i]) { y[n] = i; break; }
    }
    return { N, IN: 27, OUT: 9, X, y, optimal, boards };
  }
  function score(model, data, work, exampleLimit = 0) {
    forward(model, data.X, data.N, work); let failed = 0;
    const failingBoards = [];
    for (let n = 0; n < data.N; n += 1) {
      let choice = 0;
      for (let o = 1; o < 9; o += 1) if (work.P[n*9+o] > work.P[n*9+choice]) choice = o;
      if (!data.optimal[n*9+choice]) {
        failed += 1;
        if (failingBoards.length < exampleLimit) {
          failingBoards.push({ board: Array.from(data.boards[n]), prediction: choice });
        }
      }
    }
    return { failed, pct: failed * 100 / data.N, failingBoards };
  }
  self.TrainingCore = { initialize, scratch, adam, batcher, trainEpoch, dataset, score };
})();
