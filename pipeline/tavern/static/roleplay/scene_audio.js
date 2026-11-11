class SceneAudio {
  constructor() {
    this.controls = document.querySelector('#sound-controls');
    this.button = document.querySelector('#sound-toggle');
    this.slider = document.querySelector('#sound-volume');
    this.muted = localStorage.getItem('ludens-sound-muted') === 'true';
    this.slider.value = localStorage.getItem('ludens-sound-volume') ?? '35';
    this.active = false;
    this.mood = 'quiet';
    this.changedAt = -15000;
    this.tracks = ['tense', 'calm', 'warm', 'rain'].map(name => {
      const audio = new Audio();
      audio.preload = 'none'; audio.loop = true;
      audio.src = `/static/roleplay/audio/${name}.mp3`;
      const track = {name, audio};
      audio.onerror = () => { track.failed = true; this.render(); };
      return track;
    });
    this.videos = [document.querySelector('#motion'), document.querySelector('#opening-video')];
    for (const video of this.videos) {
      for (const event of ['play', 'pause', 'ended', 'volumechange', 'emptied']) video.addEventListener(event, () => this.sync());
    }
    this.button.onclick = () => {
      this.muted = this.context?.state === 'running' ? !this.muted : false;
      localStorage.setItem('ludens-sound-muted', String(this.muted));
      this.unlock(); this.sync();
    };
    this.slider.oninput = () => {
      localStorage.setItem('ludens-sound-volume', this.slider.value);
      this.sync();
    };
    document.addEventListener('click', () => this.unlock());
    document.addEventListener('keydown', event => { if (['Enter', ' '].includes(event.key)) this.unlock(); });
    document.addEventListener('visibilitychange', () => this.sync());
    window.addEventListener('pagehide', () => { for (const track of this.tracks) track.audio.pause(); });
    this.render();
  }
  async unlock() {
    if (this.muted) return;
    try {
      if (!this.context) {
        this.context = new (window.AudioContext || window.webkitAudioContext)();
        for (const track of this.tracks) {
          track.gain = this.context.createGain(); track.gain.gain.value = 0;
          this.context.createMediaElementSource(track.audio).connect(track.gain).connect(this.context.destination);
        }
      }
      await this.context.resume();
      this.blocked = false;
      this.sync();
    } catch (error) { this.blocked = true; this.render(); }
  }
  enter(story, mood = 'quiet') {
    this.active = true;
    this.score(mood, true);
    this.rain = /雨|\brain(?:y|ing)?\b/i.test(`${story.intro || ''} ${story.prologue || ''}`);
    this.controls.hidden = false;
    this.sync();
  }
  leave() {
    this.active = false;
    clearTimeout(this.scoreTimer);
    this.controls.hidden = true;
    this.sync();
  }
  score(mood, immediate = false) {
    if (!['tense', 'calm', 'warm', 'quiet'].includes(mood)) return;
    clearTimeout(this.scoreTimer);
    if (mood === this.mood) return;
    const delay = 15000 - (performance.now() - this.changedAt);
    if (!immediate && mood !== 'quiet' && this.mood !== 'quiet' && delay > 0) {
      this.scoreTimer = setTimeout(() => this.score(mood, true), delay);
      return;
    }
    this.mood = mood;
    this.changedAt = performance.now();
    this.sync();
  }
  sync() {
    this.render();
    if (!this.context) return;
    const enabled = this.active && !this.muted && !document.hidden && !this.replaying;
    const volume = Number(this.slider.value) / 100;
    const duck = this.videos.some(video => !video.paused && !video.ended && !video.muted && video.volume > 0 && video.dataset.silent !== 'true');
    for (const track of this.tracks) {
      const playing = enabled && volume > 0 && (track.name === 'rain' ? this.rain : track.name === this.mood);
      const level = playing ? volume * (track.name === 'rain' ? .28 : .65) * (duck ? .18 : 1) : 0;
      clearTimeout(track.pauseTimer);
      track.gain.gain.cancelScheduledValues(this.context.currentTime);
      track.gain.gain.setTargetAtTime(level, this.context.currentTime, enabled && !duck ? .7 : .15);
      if (playing && track.audio.paused && !track.starting && !track.failed) {
        track.starting = true;
        track.audio.play().catch(error => {
          if (error.name === 'NotAllowedError') this.blocked = true;
          else if (error.name !== 'AbortError') track.failed = true;
          this.render();
        }).finally(() => { track.starting = false; });
      } else if (!playing) {
        if (document.hidden || this.replaying) track.audio.pause();
        else track.pauseTimer = setTimeout(() => track.audio.pause(), enabled ? 2800 : 600);
      }
    }
  }
  render() {
    const off = this.muted || Number(this.slider.value) === 0;
    const blocked = this.blocked || this.context?.state !== 'running';
    this.button.textContent = this.replaying ? '回放中 · 背景音暂停' : off ? '背景音 · 关' : blocked ? '开启背景音' : '背景音 · 开';
    this.button.disabled = Boolean(this.replaying);
    this.slider.disabled = Boolean(this.replaying);
    this.button.setAttribute('aria-pressed', String(!off && !blocked && !this.replaying));
    this.button.title = this.tracks.some(track => track.failed) ? '部分背景音加载失败，请刷新重试' : '控制配乐和环境声；视频原声由播放器控制';
    this.slider.setAttribute('aria-valuetext', `${this.slider.value}%`);
  }
}
