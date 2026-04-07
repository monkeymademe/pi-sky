import { MESSAGES, MESSAGE_INTERVAL, TOTAL_TRANSITION } from './constants.js';

export class MessageRotator {
  constructor(board) {
    this.board = board;
    this.messages = MESSAGES;
    this.currentIndex = -1;
    this._timer = null;
    this._paused = false;
  }

  start() {
    // Show first message immediately
    this.next();

    // Begin auto-rotation
    this._timer = setInterval(() => {
      if (!this._paused && !this.board.isTransitioning) {
        this.next();
      }
    }, MESSAGE_INTERVAL + TOTAL_TRANSITION);
  }

  stop() {
    if (this._timer) {
      clearInterval(this._timer);
      this._timer = null;
    }
  }

  next() {
    this.currentIndex = (this.currentIndex + 1) % this.messages.length;
    this.board.displayMessage(this.messages[this.currentIndex]);
    this._resetAutoRotation();
  }

  prev() {
    this.currentIndex = (this.currentIndex - 1 + this.messages.length) % this.messages.length;
    this.board.displayMessage(this.messages[this.currentIndex]);
    this._resetAutoRotation();
  }

  _resetAutoRotation() {
    // Reset timer when user manually navigates
    if (this._timer) {
      clearInterval(this._timer);
      this._timer = setInterval(() => {
        if (!this._paused && !this.board.isTransitioning) {
          this.next();
        }
      }, MESSAGE_INTERVAL + TOTAL_TRANSITION);
    }
  }
}
