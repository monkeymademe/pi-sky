/**
 * Embeds FlipOff split-flap board for the latest flight (source/destination).
 * Upstream: https://github.com/magnum6actual/flipoff (MIT)
 */
import { Board } from './js/Board.js';
import { SoundEngine } from './js/SoundEngine.js';

const MAX_LINE = 22;

function clipLine(s) {
  const t = String(s || '')
    .toUpperCase()
    .trim();
  return t.length <= MAX_LINE ? t : t.slice(0, MAX_LINE);
}

function buildLines(flight) {
  const cs = clipLine(flight.callsign || 'UNIDENTIFIED');
  const origin = flight.origin ? clipLine(flight.origin) : null;
  const dest = flight.destination ? clipLine(flight.destination) : null;
  const oc = flight.origin_country ? clipLine(flight.origin_country) : '';
  const dc = flight.destination_country ? clipLine(flight.destination_country) : '';

  let routeLine;
  if (origin && dest) {
    routeLine = clipLine(`${origin}  ->  ${dest}`);
  } else if (origin) {
    routeLine = clipLine(`${origin}  ->  IN FLIGHT`);
  } else {
    routeLine = clipLine('ROUTE PENDING...');
  }

  return [
    clipLine('Latest flight'),
    cs,
    routeLine,
    oc || '---',
    dc || '---',
  ];
}

let board = null;
let soundEngine = null;
let lastSignature = '';

function signature(flight) {
  return [
    flight.icao,
    flight.callsign,
    flight.origin,
    flight.destination,
    flight.origin_country,
    flight.destination_country,
  ].join('|');
}

export function initFlipoffBoard() {
  const el = document.getElementById('flipoff-board-container');
  if (!el) return;

  soundEngine = new SoundEngine();
  board = new Board(el, soundEngine);

  board.displayMessage([
    '',
    'FLIPOFF',
    '',
    'WAITING FOR',
    'FLIGHT DATA...',
  ]);

  const initAudio = async () => {
    if (!soundEngine) return;
    await soundEngine.init();
    soundEngine.resume();
  };
  document.addEventListener('click', initAudio, { once: true });
  document.addEventListener('keydown', initAudio, { once: true });

  const muteBtn = document.getElementById('flipoff-mute-btn');
  if (muteBtn) {
    muteBtn.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      initAudio();
      const muted = soundEngine.toggleMute();
      muteBtn.classList.toggle('muted', muted);
      muteBtn.setAttribute('aria-pressed', muted ? 'true' : 'false');
    });
  }
}

export function updateFlipoffFromFlights(flights) {
  if (!board) return;

  if (!flights || flights.length === 0) {
    lastSignature = '';
    board.displayMessage(['', '', 'NO ACTIVE', 'FLIGHTS', '']);
    return;
  }

  const sorted = [...flights].sort((a, b) => (a.seen ?? 999) - (b.seen ?? 999));
  const latest = sorted[0];
  const sig = signature(latest);
  if (sig === lastSignature) return;
  lastSignature = sig;

  board.displayMessage(buildLines(latest));
}

document.addEventListener('flights-updated', (ev) => {
  const flights = ev.detail && ev.detail.flights;
  updateFlipoffFromFlights(flights);
});

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => initFlipoffBoard());
} else {
  initFlipoffBoard();
}
