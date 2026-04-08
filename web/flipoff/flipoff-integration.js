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

function isValidAirportField(v) {
  const s = String(v ?? '').trim();
  if (!s) return false;
  if (/^-+$/.test(s)) return false;
  if (/pending/i.test(s)) return false;
  const u = s.toUpperCase();
  if (u === '---' || u === 'N/A' || u === 'NA' || u === '?') return false;
  if (u === 'UNKNOWN' || u === 'NONE' || u === 'TBD' || u === 'NULL') return false;
  return true;
}

function hasFullRoute(flight) {
  if (!flight) return false;
  return isValidAirportField(flight.origin) && isValidAirportField(flight.destination);
}

/** Only called for flights that pass hasFullRoute */
function buildLines(flight) {
  const cs = clipLine(flight.callsign || 'UNIDENTIFIED');
  const origin = clipLine(flight.origin);
  const dest = clipLine(flight.destination);
  const routeLine = clipLine(`${origin}  ->  ${dest}`);
  const oc = flight.origin_country ? clipLine(flight.origin_country) : '';
  const dc = flight.destination_country ? clipLine(flight.destination_country) : '';

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

  const unlockAudio = async () => {
    if (!soundEngine) return;
    await soundEngine.unlock();
  };

  document.addEventListener(
    'click',
    () => {
      void unlockAudio();
    },
    { once: true },
  );
  document.addEventListener(
    'keydown',
    () => {
      void unlockAudio();
    },
    { once: true },
  );

  const flipoffSection = document.querySelector('.flipoff-section');
  if (flipoffSection) {
    flipoffSection.addEventListener(
      'pointerdown',
      () => {
        void unlockAudio();
      },
      { once: true },
    );
  }

  const muteBtn = document.getElementById('flipoff-mute-btn');
  if (muteBtn) {
    muteBtn.addEventListener('click', async (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (!soundEngine) return;
      if (!soundEngine.unlocked) {
        await soundEngine.unlock();
        return;
      }
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

  const routed = flights.filter(hasFullRoute);
  if (routed.length === 0) {
    lastSignature = '';
    board.displayMessage(['', '', 'NO ROUTE', 'DATA YET', '']);
    return;
  }

  const sorted = [...routed].sort((a, b) => (a.seen ?? 999) - (b.seen ?? 999));
  const latest = sorted[0];
  const sig = signature(latest);
  if (sig === lastSignature) return;
  lastSignature = sig;

  board.displayMessage(buildLines(latest));
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => initFlipoffBoard(), { once: true });
} else {
  initFlipoffBoard();
}

document.addEventListener('flights-updated', (ev) => {
  const flights = ev.detail && ev.detail.flights;
  updateFlipoffFromFlights(flights);
});
