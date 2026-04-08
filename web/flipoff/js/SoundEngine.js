import { FLAP_AUDIO_BASE64 } from './flapAudio.js';

export class SoundEngine {
  constructor() {
    this.ctx = null;
    this.muted = false;
    this._initialized = false;
    /** True after unlock() has run in response to a user gesture (required for playback). */
    this._unlocked = false;
    this._audioBuffer = null;
    this._currentSource = null;
    /** @type {Promise<void>|null} */
    this._initPromise = null;
  }

  /**
   * Decode audio. Safe to call before user gesture; buffer is ready when promise resolves.
   */
  async init() {
    if (this._initPromise) return this._initPromise;
    this._initPromise = this._doInit();
    return this._initPromise;
  }

  async _doInit() {
    if (this._initialized) return;
    try {
      this.ctx = new (window.AudioContext || window.webkitAudioContext)();
      const binaryStr = atob(FLAP_AUDIO_BASE64);
      const bytes = new Uint8Array(binaryStr.length);
      for (let i = 0; i < binaryStr.length; i++) {
        bytes[i] = binaryStr.charCodeAt(i);
      }
      this._audioBuffer = await this.ctx.decodeAudioData(bytes.buffer);
      this._initialized = true;
    } catch (e) {
      console.warn('Failed to decode flap audio:', e);
    }
  }

  /**
   * Must run from a user gesture (click/tap/key). Resumes the AudioContext so playTransition can be heard.
   */
  async unlock() {
    if (this._unlocked) return;
    await this.init();
    if (!this.ctx || !this._audioBuffer) return;
    try {
      this.ctx.resume();
    } catch (e) {
      console.warn('AudioContext.resume:', e);
    }
    this._unlocked = true;
  }

  resume() {
    if (this.ctx && this.ctx.state === 'suspended') {
      void this.ctx.resume();
    }
  }

  get unlocked() {
    return this._unlocked;
  }

  toggleMute() {
    this.muted = !this.muted;
    return this.muted;
  }

  /**
   * Play the full transition sound once.
   * This is a single recorded clip of a split-flap board transition,
   * played once per message change (not per tile).
   */
  playTransition() {
    if (!this._unlocked || !this.ctx || !this._audioBuffer || this.muted) return;
    if (this.ctx.state === 'suspended') {
      void this.ctx.resume();
    }

    // Stop any currently playing transition sound
    if (this._currentSource) {
      try {
        this._currentSource.stop();
      } catch (e) {
        // ignore if already stopped
      }
    }

    const source = this.ctx.createBufferSource();
    source.buffer = this._audioBuffer;

    const gain = this.ctx.createGain();
    gain.gain.value = 0.8;

    source.connect(gain);
    gain.connect(this.ctx.destination);

    source.start(0);
    this._currentSource = source;

    source.onended = () => {
      if (this._currentSource === source) {
        this._currentSource = null;
      }
    };
  }

  /** Get the duration of the transition audio clip in ms */
  getTransitionDuration() {
    if (this._audioBuffer) {
      return this._audioBuffer.duration * 1000;
    }
    return 3800; // fallback
  }

  // Keep this for API compatibility but it now plays the full transition
  scheduleFlaps() {
    this.playTransition();
  }
}
