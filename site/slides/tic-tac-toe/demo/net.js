export function encodeBoard(board) {
  const encoded = new Float32Array(27);
  board.forEach((value, cell) => { encoded[cell * 3 + value] = 1; });
  return encoded;
}

export function forward(params, input) {
  const preactivation = new Float32Array(params.H);
  const hidden = new Float32Array(params.H);
  for (let column = 0; column < params.H; column += 1) {
    let sum = params.ba[column];
    for (let row = 0; row < params.IN; row += 1) {
      if (input[row]) sum += input[row] * params.Wa[row * params.H + column];
    }
    preactivation[column] = sum;
    hidden[column] = Math.max(0, sum);
  }

  const logits = new Float32Array(params.OUT);
  for (let output = 0; output < params.OUT; output += 1) {
    let sum = params.bb[output];
    for (let column = 0; column < params.H; column += 1) {
      sum += hidden[column] * params.Wb[column * params.OUT + output];
    }
    logits[output] = sum;
  }
  return { preactivation, hidden, logits };
}

export function chooseLegalMove(logits, board) {
  let move = -1;
  let best = -Infinity;
  for (let index = 0; index < board.length; index += 1) {
    if (board[index] === 0 && logits[index] > best) {
      move = index;
      best = logits[index];
    }
  }
  return move;
}
