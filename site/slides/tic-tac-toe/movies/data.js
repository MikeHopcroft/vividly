export const CATALOG_SIZE = 9500;

export const LIKED = [
  { title: "The Bucharest Exchange", row: 812, score: 9.31, filename: "the-bucharest-exchange-6.jpg" },
  { title: "The Odessa Cipher", row: 2046, score: 9.12, filename: "the-odessa-cipher-5.jpg" },
  { title: "The Ninth Embassy", row: 5133, score: 8.97, filename: "the-ninth-embassy-3.jpg" },
  { title: "Three Days in Tangier", row: 7721, score: 8.88, filename: "three-days-in-tangier-5.jpg" },
];

export const WINNER = {
  title: "Cold Case, Warm Room", row: 3302, score: 8.54, filename: "cold-case-warm-room.jpg",
};

export const CANDIDATES = [
  ["The House on Halloway Street", 6.06, "the-house-on-halloway-street.jpg"],
  ["Encore Anyway", 3.33, "encore-anyway.jpg"],
  ["The Quiet Orchard", 5.67, "the-quiet-orchard.jpg"],
  ["My Roommate Is a Municipal Employee", 3.98, "my-roommate-is-a-municipal-employee.jpg"],
  ["Hill 44", 7.73, "hill-44.jpg"],
  ["Sidewalk Serenade", 3.57, "sidewalk-serenade.jpg"],
  ["Neon Overture", 3.46, "neon-overture.jpg"],
  ["The Plus-One Problem", 4.82, "the-plus-one-problem.jpg"],
  ["Aunt Dorothy Explodes", 3.56, "aunt-dorothy-explodes.jpg"],
  ["The Long Retreat", 7.07, "the-long-retreat.jpg"],
  ["Secondhand Love", 4.21, "secondhand-love.jpg"],
  ["Gate 27", 4.10, "gate-27.jpg"],
  ["The People v. Harlan Reese", 6.53, "the-people-v-harlan-reese.jpg"],
  ["Twelve Rooms on Delancey", 8.24, "twelve-rooms-on-delancey.jpg"],
  ["The Quiet Inventory", 8.10, "the-quiet-inventory.jpg"],
  ["Motion to Dismiss", 6.67, "motion-to-dismiss.jpg"],
  ["A Dollar for the Preacher", 6.40, "a-dollar-for-the-preacher.jpg"],
  ["Unlisted Number", 8.22, "the-unlisted-number.jpg"],
  ["Chain of Custody", 7.69, "chain-of-custody.jpg"],
  ["The Grand Marquee", 3.51, "the-grand-marquee.jpg"],
  ["The Last Train to Mercy", 6.57, "the-last-train-to-mercy.jpg"],
  ["Blood on the Cimarron", 6.43, "blood-on-the-cimarron.jpg"],
  ["The Seventh Juror", 6.53, "the-seventh-juror.jpg"],
  ["The Cartographer's War", 7.26, "the-cartographers-war.jpg"],
  ["A Season of Small Rain", 6.04, "a-season-of-small-rain.jpg"],
  ["Precinct Nineteen", 7.78, "precinct-nineteen.jpg"],
  ["Forecast: Falling", 4.34, "forecast-falling.jpg"],
  ["Winter at Crow's Crossing", 6.13, "winter-at-crows-crossing.jpg"],
  ["Chorus on the Fifth Floor", 3.14, "chorus-of-the-fifth-floor.jpg"],
  ["Wrong Larry", 3.57, "the-wrong-larry.jpg"],
  ["Ashes over Dresden", 7.05, "ashes-over-dresden.jpg"],
  ["Letters from the Coast", 6.18, "letters-from-the-coast.jpg"],
  ["Nine Lawn Flamingos", 4.07, "nine-lawn-flamingos.jpg"],
  ["Cold Room", 8.08, "cold-room.jpg"],
  ["The Inheritance of Thomas Vale", 5.85, "the-inheritance-of-thomas-vale.jpg"],
  ["Body-Worn", 7.94, "body-worn.jpg"],
  ["In Chambers", 6.73, "in-chambers.jpg"],
  ["Burden of Proof", 7.06, "burden-of-proof.jpg"],
  ["Signal Lost", 7.58, "signal-lost.jpg"],
  ["The Hanging at Bitter Creek", 6.51, "the-hanging-at-bitter-creek.jpg"],
  ["Call Me After Midnight", 4.05, "call-me-after-midnight.jpg"],
].map(([title, score, filename]) => ({ title, score, filename }));

export const POSTERS = [...LIKED, WINNER, ...CANDIDATES];
export const posterUrl = movie => new URL(`./posters/${movie.filename}`, import.meta.url).href;

export const ROW_SCORES = new Map([
  [0, 5.12], [1, 3.87], [2, 6.41], [811, 6.02], [813, 4.77],
  [2045, 5.55], [2047, 6.88], [3301, 7.12], [3303, 5.93],
  [5132, 6.30], [5134, 4.41], [7720, 7.02], [7722, 5.68],
  [9497, 3.95], [9498, 6.76], [9499, 5.21],
  ...LIKED.map(movie => [movie.row, movie.score]), [WINNER.row, WINNER.score],
]);
