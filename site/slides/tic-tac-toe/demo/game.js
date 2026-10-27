const WIN_LINES = [
  [0, 1, 2], [3, 4, 5], [6, 7, 8],
  [0, 3, 6], [1, 4, 7], [2, 5, 8],
  [0, 4, 8], [2, 4, 6],
];

export function winner(board) {
  for (const [a, b, c] of WIN_LINES) {
    if (board[a] && board[a] === board[b] && board[a] === board[c]) return board[a];
  }
  return 0;
}

export function legalMoves(board) {
  if (winner(board)) return [];
  const moves = [];
  for (let index = 0; index < board.length; index += 1) {
    if (board[index] === 0) moves.push(index);
  }
  return moves;
}

export function playerToMove(board) {
  let crosses = 0;
  let noughts = 0;
  for (const cell of board) {
    if (cell === 1) crosses += 1;
    else if (cell === 2) noughts += 1;
  }
  return crosses <= noughts ? 1 : 2;
}

export function gameStatus(board) {
  const winningPlayer = winner(board);
  if (winningPlayer) return `${winningPlayer === 1 ? "X" : "O"} wins`;
  if (!board.includes(0)) return "Draw";
  return `${playerToMove(board) === 1 ? "X" : "O"} to move`;
}

export function boardsEqual(left, right) {
  return left.length === right.length && left.every((value, index) => value === right[index]);
}
