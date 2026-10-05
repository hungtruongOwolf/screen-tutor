// Plays the steps of an answer one after another while more of them are still
// arriving: show a step (drawing it on), let the viewer read, show the next. Used by
// the desktop app and by the web page, so both behave the same.
//
// The player knows nothing about drawing: it is given a function that shows a step
// (and resolves when its drawing has finished) and a way to wait.

export interface PlayerDeps<S> {
  // Show step `index`. With `animate` its new shapes are drawn on stroke by stroke.
  // Resolves when the drawing and the caption are finished.
  show(index: number, animate: boolean, step: S): Promise<void>;
  sleep(ms: number): Promise<void>;
  // How long a step is left on screen before the next one starts.
  dwell(step: S): number;
  // Called when showing a step failed (the player goes on with the next step).
  onError?(error: unknown, index: number): void;
  // Called when automatic playback starts or stops (paused, taken over or finished).
  onPlaying?(playing: boolean): void;
}

export class StepPlayer<S> {
  readonly steps: S[] = [];
  index = -1; // the step shown last (-1: none yet)
  streaming = false; // more steps may still arrive
  private active = false;
  private token = 0;
  private wake: (() => void) | undefined;

  constructor(private readonly deps: PlayerDeps<S>) {}

  // Automatic playback is running (not paused or finished).
  get playing(): boolean {
    return this.active;
  }

  private setPlaying(value: boolean): void {
    if (this.active === value) return;
    this.active = value;
    this.deps.onPlaying?.(value);
  }

  // A new answer: forget the old steps, stop the old playback, start a new one.
  begin(): void {
    this.token += 1;
    this.steps.length = 0;
    this.index = -1;
    this.streaming = true;
    this.wake?.();
    void this.run(this.token, 0);
  }

  // Carry on with automatic playback after the viewer paused it: from the step after
  // the one on screen.
  resume(): void {
    this.token += 1;
    this.wake?.();
    void this.run(this.token, this.index + 1);
  }

  // A step has arrived.
  add(step: S): void {
    this.steps.push(step);
    this.wake?.();
  }

  // No more steps will arrive.
  end(): void {
    this.streaming = false;
    this.wake?.();
  }

  // The viewer takes over (a key press): automatic playback stops.
  stop(): void {
    this.token += 1;
    this.setPlaying(false);
    this.wake?.();
  }

  // Forget everything and stop.
  reset(): void {
    this.stop();
    this.steps.length = 0;
    this.index = -1;
    this.streaming = false;
  }

  // Show a step on request (outside automatic playback).
  async goTo(index: number, animate: boolean): Promise<void> {
    const step = this.steps[index];
    if (step === undefined) return;
    this.index = index;
    try {
      await this.deps.show(index, animate, step);
    } catch (error) {
      this.deps.onError?.(error, index);
    }
  }

  private async run(token: number, start: number): Promise<void> {
    this.setPlaying(true);
    try {
      await this.loop(token, start);
    } finally {
      if (token === this.token) this.setPlaying(false);
    }
  }

  private async loop(token: number, first: number): Promise<void> {
    let next = first;
    while (token === this.token) {
      if (next >= this.steps.length) {
        if (!this.streaming) return;
        // Wait for the next step (or for the end, or for a takeover).
        await new Promise<void>((resolve) => {
          this.wake = resolve;
        });
        this.wake = undefined;
        continue;
      }
      const step = this.steps[next] as S;
      this.index = next;
      try {
        await this.deps.show(next, true, step);
      } catch (error) {
        this.deps.onError?.(error, next); // one bad step does not stop the rest
      }
      if (token !== this.token) return;
      const last = !this.streaming && next === this.steps.length - 1;
      if (!last) await this.deps.sleep(this.deps.dwell(step));
      next += 1;
    }
  }
}
