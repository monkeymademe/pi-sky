import { Tile } from './Tile.js';
import {
  GRID_COLS, GRID_ROWS, STAGGER_DELAY, SCRAMBLE_DURATION,
  TOTAL_TRANSITION, ACCENT_COLORS
} from './constants.js';

export class Board {
  constructor(containerEl, soundEngine) {
    this.cols = GRID_COLS;
    this.rows = GRID_ROWS;
    this.soundEngine = soundEngine;
    this.isTransitioning = false;
    /** @type {string[]|null} Latest message queued while animating */
    this._pendingDisplay = null;
    this.tiles = [];
    this.currentGrid = [];
    this.accentIndex = 0;

    // Build board DOM
    this.boardEl = document.createElement('div');
    this.boardEl.className = 'board';
    this.boardEl.style.setProperty('--grid-cols', this.cols);
    this.boardEl.style.setProperty('--grid-rows', this.rows);

    // Left accent squares (2 small stacked blocks)
    this.leftBar = this._createAccentBar('accent-bar-left');
    this.boardEl.appendChild(this.leftBar);

    // Tile grid
    this.gridEl = document.createElement('div');
    this.gridEl.className = 'tile-grid';

    for (let r = 0; r < this.rows; r++) {
      const row = [];
      const charRow = [];
      for (let c = 0; c < this.cols; c++) {
        const tile = new Tile(r, c);
        tile.setChar(' ');
        this.gridEl.appendChild(tile.el);
        row.push(tile);
        charRow.push(' ');
      }
      this.tiles.push(row);
      this.currentGrid.push(charRow);
    }

    this.boardEl.appendChild(this.gridEl);

    // Right accent squares
    this.rightBar = this._createAccentBar('accent-bar-right');
    this.boardEl.appendChild(this.rightBar);

    // Keyboard hint icon (bottom-left)
    const hint = document.createElement('div');
    hint.className = 'keyboard-hint';
    hint.textContent = 'N';
    hint.title = 'Keyboard shortcuts';
    hint.addEventListener('click', (e) => {
      e.stopPropagation();
      const overlay = this.boardEl.querySelector('.shortcuts-overlay');
      if (overlay) overlay.classList.toggle('visible');
    });
    this.boardEl.appendChild(hint);

    // Shortcuts overlay
    const overlay = document.createElement('div');
    overlay.className = 'shortcuts-overlay';
    overlay.innerHTML = `
      <div><span>Next message</span><kbd>Enter</kbd></div>
      <div><span>Previous</span><kbd>\u2190</kbd></div>
      <div><span>Fullscreen</span><kbd>F</kbd></div>
      <div><span>Mute</span><kbd>M</kbd></div>
    `;
    this.boardEl.appendChild(overlay);

    containerEl.appendChild(this.boardEl);
    this._updateAccentColors();
  }

  _createAccentBar(extraClass) {
    const bar = document.createElement('div');
    bar.className = `accent-bar ${extraClass}`;
    // Just 2 small stacked squares like the original
    for (let i = 0; i < 2; i++) {
      const seg = document.createElement('div');
      seg.className = 'accent-segment';
      bar.appendChild(seg);
    }
    return bar;
  }

  _updateAccentColors() {
    const color = ACCENT_COLORS[this.accentIndex % ACCENT_COLORS.length];
    const segments = this.boardEl.querySelectorAll('.accent-segment');
    segments.forEach(seg => {
      seg.style.backgroundColor = color;
    });
  }

  displayMessage(lines) {
    if (this.isTransitioning) {
      this._pendingDisplay = lines;
      return;
    }
    this.isTransitioning = true;

    let hasChanges = false;
    try {
      const newGrid = this._formatToGrid(lines);

      for (let r = 0; r < this.rows; r++) {
        for (let c = 0; c < this.cols; c++) {
          const newChar = newGrid[r][c];
          const oldChar = this.currentGrid[r][c];

          if (newChar !== oldChar) {
            const delay = (r * this.cols + c) * STAGGER_DELAY;
            this.tiles[r][c].scrambleTo(newChar, delay);
            hasChanges = true;
          }
        }
      }

      if (hasChanges && this.soundEngine) {
        try {
          this.soundEngine.playTransition();
        } catch (e) {
          console.warn('FlipOff sound:', e);
        }
      }

      this.accentIndex++;
      this._updateAccentColors();
      this.currentGrid = newGrid;
    } catch (e) {
      console.error('FlipOff displayMessage:', e);
    } finally {
      const delay = hasChanges ? TOTAL_TRANSITION + 200 : 0;
      setTimeout(() => {
        this.isTransitioning = false;
        if (this._pendingDisplay) {
          const pending = this._pendingDisplay;
          this._pendingDisplay = null;
          this.displayMessage(pending);
        }
      }, delay);
    }
  }

  _formatToGrid(lines) {
    const grid = [];
    for (let r = 0; r < this.rows; r++) {
      const line = (lines[r] || '').toUpperCase();
      const padTotal = this.cols - line.length;
      const padLeft = Math.max(0, Math.floor(padTotal / 2));
      const padded = ' '.repeat(padLeft) + line + ' '.repeat(Math.max(0, this.cols - padLeft - line.length));
      grid.push(padded.split(''));
    }
    return grid;
  }
}
