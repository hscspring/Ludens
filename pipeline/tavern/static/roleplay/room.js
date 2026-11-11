class RoleplayRoom {
  constructor() {
    this.cache = new Map();
    this.selected = null;
    this.busy = false;
    this.pointerDown = false;
    this.canvas = document.querySelector('#canvas');
    this.context = this.canvas.getContext('2d');
    this.motion = document.querySelector('#motion');
    this.replayEvents = [];
    this.replayIndex = 0;
    this.idle = document.querySelector('#idle');
    this.audio = new SceneAudio();
    this.journal = new SceneJournal(this);
    window.addEventListener('pagehide', () => this.leavePlay());
    window.addEventListener('pageshow', event => { if (event.persisted) this.showLibrary(); });
    document.querySelector('#enter-scene').onclick = () => this.closeOpening();
    document.querySelector('#opening-video').onended = () => this.closeOpening();
    document.querySelector('#new').onclick = () => { if (confirm('重新开局会重置当前故事的对话与进展，确定重新开始吗？')) this.enter(true); };
    document.querySelector('#choose').onclick = () => this.showLibrary();
    document.querySelector('#wide').onclick = () => { this.selected = null; this.inspecting = false; this.render(); };
    document.querySelector('#chat').onsubmit = event => { event.preventDefault(); this.act({kind: 'talk', text: document.querySelector('#text').value}); };
    document.querySelector('#watch').onclick = () => this.act({kind: 'wait'});
    document.querySelector('#discuss').onclick = () => this.discuss();
    document.querySelector('#dismiss-moment').onclick = () => this.dismissMoment();
    document.querySelector('#replay').onclick = () => this.openReplay();
    document.querySelector('#close-viewer').onclick = () => this.closeViewer();
    document.querySelector('#previous').onclick = () => this.replayStep(-1);
    document.querySelector('#next').onclick = () => this.replayStep(1);
    document.querySelector('#continuous').onclick = () => this.toggleReplay();
    document.querySelector('#text').oninput = event => { event.target.style.height = 'auto'; event.target.style.height = `${Math.min(112,event.target.scrollHeight + 2)}px`; this.lastInteraction = Date.now(); };
    document.addEventListener('pointerdown', () => { this.pointerDown = true; this.lastInteraction = Date.now(); });
    document.addEventListener('pointerup', () => { this.pointerDown = false; });
    this.motion.onended = () => { if (this.autoReplay) this.replayStep(1); else document.querySelector('#replay-again').hidden = false; this.finishVideo(); };
    document.querySelector('#replay-again').onclick = () => { this.motion.currentTime = 0; this.motion.play().catch(error => this.error(error.message)); document.querySelector('#replay-again').hidden = true; };
    document.addEventListener('keydown', event => { if (event.key !== 'Escape' || this.journal.dialog.open) return; if (this.viewing) this.closeViewer(); else document.querySelector('#wide').click(); });
    this.motion.onerror = () => { document.querySelector('#viewer-note').textContent = '视频加载失败，可以关闭后继续玩。'; };
    this.view = new SceneView(this);
    this.start();
  }
  async start() {
    try {
      this.stories = await this.request('/api/stories');
      const requested = new URLSearchParams(location.search).get('story');
      this.showLibrary();
      const story = this.stories.find(story => story.id === requested);
      if (story) await this.chooseStory(story);
    } catch (error) { this.error(error.message); }
  }
  showLibrary() {
    this.entryAttempt = (this.entryAttempt || 0) + 1;
    this.leavePlay();
    clearTimeout(this.timer);
    this.entering = false; this.busy = false;
    this.journal.dialog.close();
    this.journal.button.hidden = true;
    document.querySelector('#entry-status').hidden = true;
    this.audio.leave();
    this.closeViewer();
    document.querySelector('#opening-video').pause();
    this.idle.pause();
    document.body.classList.remove('playing');
    this.dismissMoment();
    document.querySelector('#backdrop').width = innerWidth;
    document.querySelector('#backdrop').hidden = true;
    document.querySelector('#backdrop').style.backgroundImage = '';
    document.title = 'Ludens · 选择故事';
    document.querySelector('#library').hidden = false;
    document.querySelector('#project-links').hidden = false;
    document.querySelector('.story-heading').hidden = true;
    document.querySelector('.header-actions').hidden = true;
    document.querySelector('#opening').hidden = true;
    document.querySelector('#play-area').hidden = true;
    document.querySelector('#title').textContent = '选择一段经历';
    document.querySelector('#intro').textContent = '';
    document.querySelector('#replay').hidden = true;
    document.querySelector('#new').hidden = true;
    history.replaceState(null, '', '/');
    const cards = document.querySelector('#stories'); cards.replaceChildren();
    for (const story of this.stories) {
      const card = document.createElement('article'); card.className = 'story-card';
      const cover = document.createElement('img'); cover.src = story.cover; cover.alt = story.title; cover.loading = 'lazy';
      const copy = document.createElement('div'); copy.className = 'card-copy';
      const character = document.createElement('small'); character.textContent = story.character;
      const title = document.createElement('h3'); title.textContent = story.title;
      const intro = document.createElement('p'); intro.textContent = story.intro;
      const button = document.createElement('button');
      button.textContent = localStorage.getItem(`ludens-roleplay-${story.id}-session`) ? '继续这个故事 →' : '开始这个故事 →';
      button.onclick = () => this.chooseStory(story);
      copy.append(character, title, intro, button); card.append(cover,copy); cards.append(card);
    }
  }
  async chooseStory(story) {
    if (this.busy) return;
    this.story = story;
    this.key = `ludens-roleplay-${story.id}-session`;
    document.querySelector('#library').hidden = true;
    document.querySelector('#project-links').hidden = true;
    document.querySelector('.story-heading').hidden = false;
    document.querySelector('.header-actions').hidden = false;
    for (const id of ['replay','new']) document.querySelector('#'+id).hidden = false;
    document.querySelector('#title').textContent = story.title;
    document.querySelector('#intro').textContent = story.intro;
    document.querySelector('#text').placeholder = story.placeholder;
    document.querySelector('#text').value = '';
    document.querySelector('#character').textContent = story.character;
    document.querySelector('#backdrop').style.backgroundImage = `url("${story.cover}")`;
    document.querySelector('#backdrop').hidden = false;
    document.title = `Ludens · ${story.title}`;
    history.replaceState(null, '', `/?story=${encodeURIComponent(story.id)}`);
    await this.enter();
  }
  async request(path, body) {
    const response = await fetch(path, body === undefined ? {cache: 'no-store'} : {
      method: 'POST', headers: {'Content-Type': 'application/json', 'X-Play-Ticket': this.ticket || ''}, body: JSON.stringify(body)
    });
    const data = await response.json();
    if (response.status === 429 && path.startsWith('/api/session') && this.ticket) {
      this.queue = {admitted: false, position: 0};
      this.render();
    }
    if (!response.ok) { const error = new Error(typeof data.detail === 'string' ? data.detail : '请求没有成功。'); error.status = response.status; throw error; }
    return data;
  }
  reservePlay() {
    if (this.ticket && this.queue?.admitted) return Promise.resolve(true);
    this.ticket = Array.from(crypto.getRandomValues(new Uint32Array(4)), value => value.toString(16)).join('-');
    this.queue = {admitted: false, position: 0};
    this.render();
    return new Promise(resolve => { this.admit = resolve; this.heartbeat(this.ticket); });
  }
  async heartbeat(ticket) {
    try {
      const queue = await this.request(`/api/play/${ticket}`, {});
      if (this.ticket !== ticket) { navigator.sendBeacon(`/api/play/${ticket}/leave`); return; }
      this.queue = queue;
      if (queue.admitted) { this.admit?.(true); this.admit = null; }
      this.render();
    } catch (error) {
      if (this.ticket !== ticket) return;
      this.queue = {admitted: false, position: 0, disconnected: true};
      this.render();
    }
    if (this.ticket === ticket) this.queueTimer = setTimeout(() => this.heartbeat(ticket), 5000);
  }
  leavePlay() {
    const ticket = this.ticket;
    this.ticket = null; this.queue = null;
    clearTimeout(this.queueTimer);
    this.admit?.(false); this.admit = null;
    if (ticket) navigator.sendBeacon(`/api/play/${ticket}/leave`);
  }
  closeOpening() {
    if (this.entering || !this.state?.world || !this.queue?.admitted) return;
    document.querySelector('#opening-video').pause();
    document.querySelector('#opening').hidden = true;
    document.querySelector('#play-area').hidden = false;
    document.body.classList.add('playing');
    const log = document.querySelector('#events'); log.scrollTop = log.lastElementChild ? log.lastElementChild.getBoundingClientRect().top - log.getBoundingClientRect().top + log.scrollTop : 0;
    this.audio.enter(this.story, this.state?.music);
  }
  error(message) { document.querySelector('#error').textContent = message; }
  async enter(fresh = false) {
    if (this.busy) return;
    const attempt = this.entryAttempt = (this.entryAttempt || 0) + 1;
    this.busy = true;
    this.entering = true; this.entryError = null;
    clearTimeout(this.timer);
    this.error('');
    this.closeViewer(); this.idle.pause(); this.idle.hidden = true;
    this.journal.dialog.close(); this.journal.button.hidden = true;
    this.state = null;
    document.querySelector('#opening-text').textContent = this.story.prologue || '';
    document.querySelector('#opening-full').textContent = this.story.prologue_full || '';
    document.querySelector('#opening-details').hidden = !this.story.prologue_full;
    const film = document.querySelector('#opening-video');
    film.hidden = !this.story.opening_video;
    if (this.story.opening_video) film.src = this.story.opening_video;
    document.querySelector('#opening').hidden = !this.story.prologue;
    document.querySelector('#play-area').hidden = Boolean(this.story.prologue);
    document.body.classList.toggle('playing', !this.story.prologue);
    this.audio.leave();
    this.render();
    this.startedTurn = null; this.attentionSeq = null; this.eventCount = 0; this.eventRevision = null; this.selected = null; this.inspecting = false;
    this.momentSeq = null; this.dismissedMoment = null;

    try {
      if (!await this.reservePlay() || this.entryAttempt !== attempt) return;
      const saved = fresh ? null : localStorage.getItem(this.key);
      let state;
      if (saved) {
        try { state = await this.request(`/api/session/${saved}`); }
        catch (error) { if (error.status !== 404) throw error; }
      }
      if (this.entryAttempt !== attempt) return;
      if (state && state.story_id !== this.story.id) state = null;
      const opening = !state && Boolean(this.story.prologue);
      document.querySelector('#opening').hidden = !opening;
      document.querySelector('#play-area').hidden = opening;
      document.body.classList.toggle('playing', !opening);
      if (opening) this.audio.leave(); else this.audio.enter(this.story, state?.music);
      this.render();
      state ??= await this.request(`/api/session?scene=roleplay&story_id=${encodeURIComponent(this.story.id)}`, {});
      if (this.entryAttempt !== attempt) return;
      this.state = state;
      localStorage.setItem(this.key, state.id);
      await this.paint();
    } catch (error) { if (this.entryAttempt === attempt) { this.entryError = error.message; this.error(error.message); } }
    finally {
      if (this.entryAttempt === attempt) {
        this.entering = false; this.busy = false; this.render();
        this.timer = setTimeout(() => this.poll(), 800);
      }
    }
  }
  async poll() {
    if (!document.querySelector('#library').hidden) return;
    if (this.state && !this.busy) {
      const id = this.state.id;
      try {
        const state = await this.request(`/api/session/${id}`);
        if (!this.busy && this.state?.id === id && document.querySelector('#library').hidden && state.revision > this.state.revision) {
          this.state = state;
          this.syncReplay();
          await this.paint();
          this.render();
        }
      } catch (error) { this.error(error.message); }
    }
    this.timer = setTimeout(() => this.poll(), 800);
  }
  load(url) {
    if (!this.cache.has(url)) this.cache.set(url, new Promise((resolve, reject) => {
      const image = new Image(); image.onload = () => resolve(image); image.onerror = () => reject(new Error('场景图片加载失败。')); image.src = url;
    }));
    return this.cache.get(url);
  }
  async paint() {
    const state = this.state;
    if (!state) return;
    const visual = state.visual;
    const objects = (state.world?.objects || []).filter(obj => obj.id in visual.objects);
    const moved = !state.preview && objects.some(obj => obj.dx !== visual.positions[obj.id]);
    const base = await this.load(state.preview || (moved ? visual.background : visual.frame));
    const sprites = moved ? await Promise.all(objects.map(obj => this.load(visual.objects[obj.id].sprite))) : [];
    if (state !== this.state) return;
    this.context.drawImage(base, 0, 0, this.canvas.width, this.canvas.height);
    if (moved) objects.forEach((obj, index) => {
      const dx = obj.dx - visual.positions[obj.id];
      this.context.drawImage(sprites[index], dx, Math.round(dx * state.slopes[obj.id]), this.canvas.width, this.canvas.height);
    });
    document.querySelector('#backdrop').style.backgroundImage = `url("${state.preview || visual.frame}")`;
    this.view.ambient();
    const useIdle = visual.idle && !state.preview && !moved && !this.viewing && document.querySelector('#library').hidden;
    this.idle.hidden = !useIdle;
    if (useIdle) {
      if (this.idle.dataset.url !== visual.idle) { this.idle.dataset.url = visual.idle; this.idle.src = visual.idle; }
      this.idle.play().catch(() => { this.idle.hidden = true; });
    } else this.idle.pause();
  }
  async select(id) {
    if (!this.state?.world || this.busy || this.state.preview) return;
    this.closeViewer();
    this.dismissMoment();
    if (id === this.selected && this.inspecting) { this.selected = 'character'; this.inspecting = false; this.render(); return; }
    this.selected = id;
    this.inspecting = id !== 'character';
    this.render();
    if (id === 'character') { document.querySelector('#text').focus({preventScroll: true}); return; }
    document.querySelector('#interaction-dock').scrollTop = 0;
    const obj = this.state.world.objects.find(obj => obj.id === id);
    if (this.state.pending || this.state.leads_pending || (obj?.inspected && !obj.inspect_ready)) return;
    await this.act({kind: 'inspect', target: id});
  }
  discuss() {
    if (this.busy || this.state?.pending || this.state?.leads_pending) return;
    const obj = this.state.world.objects.find(obj => obj.id === this.selected);
    if (!obj) return;
    const input = document.querySelector('#text');
    if (!input.value.trim()) input.value = `我想听你说说${obj.name}。`;
    input.dispatchEvent(new Event('input')); input.focus();
    this.selected = 'character'; this.inspecting = false; this.render();
    this.lastInteraction = Date.now();

    document.querySelector('#chat-hint').textContent = '可以改成自己的问题，再点“发送”回应。';
  }
  draft(choice) {
    if (this.busy || this.state?.pending) return;
    const input = document.querySelector('#text');
    if (input.value === choice.text) return;
    if (input.value.trim() && input.value !== choice.text && !confirm('用这条建议替换你正在写的草稿吗？')) return;
    input.value = choice.text; input.dispatchEvent(new Event('input')); input.focus();
    document.querySelector('#chat-hint').textContent = '已填入草稿，可以修改；点击发送才会回应。';
  }
  dismissMoment() {
    this.dismissedMoment = this.state?.moment?.seq;
    this.renderMoment();
  }
  renderMoment() {
    const moment = this.state?.moment;
    const active = moment && moment.seq !== this.dismissedMoment && !this.viewing && !this.state.preview;
    if (active && this.momentSeq !== moment.seq) { this.momentSeq = moment.seq; this.selected = 'character'; this.inspecting = false; }
    const ready = Boolean(active && moment.status === 'ready');
    const picture = document.querySelector('#story-moment'); picture.hidden = !ready;
    if (ready) { picture.src = moment.url; picture.alt = moment.title; }
    document.body.classList.toggle('moment', ready);
    document.querySelector('#moment-head').hidden = !active;
    if (active) document.querySelector('#moment-title').textContent = moment.title +
      (['queued','generating'].includes(moment.status) ? ' · 画面正在展开，可先回应' :
        ['failed','unavailable'].includes(moment.status) ? ' · 动作图暂不可用，仍可继续回应' : '');
  }
  recall(seq) {
    const line = document.querySelector(`#event-${seq}`);
    if (!line) return;
    line.focus({preventScroll: true});
    line.scrollIntoView({block: 'nearest', behavior: 'instant'});
  }
  async act(action) {
    if (!this.state?.world || this.busy || !this.queue?.admitted) return;
    if (this.state.pending && ['talk', 'wait'].includes(action.kind)) return;
    if ((this.state.pending || this.state.leads_pending || this.state.preview) && ['move', 'inspect'].includes(action.kind)) return;
    if (this.viewing && action.kind !== 'inspect') this.closeViewer();
    if (action.kind === 'talk' && !action.text.trim()) { this.error('请先在输入框里写一句话。'); document.querySelector('#text').focus(); return; }
    let before = JSON.parse(JSON.stringify(this.state));
    this.busy = true; this.inspectRequest = action.kind === 'inspect' ? action.target : null; this.error('');
    try {
      if (action.kind === 'move') {
        this.inspecting = true;
        this.state.world.objects.find(obj => obj.id === action.target).dx += action.delta;
        await this.paint();
      }
      if (action.kind !== 'inspect') { this.startedTurn = null; this.inspecting = action.kind === 'move'; if (!this.inspecting) this.selected = 'character'; this.submittedAt = Date.now(); }
      if (action.kind !== 'inspect') this.dismissMoment();
      this.render();
      this.state = await this.request(`/api/session/${this.state.id}/act`, action);
      before = this.state;
      if (action.kind === 'talk') { document.querySelector('#text').value = ''; document.querySelector('#text').style.height = 'auto'; }
      await this.paint();
    } catch (error) { this.state = before; this.error(error.message); await this.paint().catch(error => this.error(error.message)); }
    finally { this.busy = false; this.inspectRequest = null; this.render(); }
  }
  closeViewer() {
    clearTimeout(this.replayTimer);
    this.replaySession = null;
    this.viewingSeq = null;
    this.autoReplay = false;
    this.motion.pause(); this.motion.removeAttribute('src'); this.motion.load();
    document.querySelector('#viewer').hidden = true;
    document.querySelector('#playback-details').hidden = true;
    document.querySelector('#replay-caption').hidden = true;
    document.querySelector('#replay-again').hidden = true;
    document.querySelector('#scene').removeAttribute('aria-label');
    document.body.classList.remove('viewing');
    document.querySelector('#camera').inert = false;
    this.viewing = false;
    this.audio.score(this.state?.music, true);
    this.audio.replaying = false; this.audio.sync();
    this.renderMoment();
    if (this.state?.world) this.hits();
    document.querySelector('#continuous').textContent = '连续回放';
  }
  showViewer() {

    this.viewing = true;
    this.audio.replaying = true; this.audio.sync();
    this.renderMoment();
    document.body.classList.add('viewing');
    document.querySelector('#camera').inert = true;
    document.querySelector('#viewer').hidden = false;
    document.querySelector('#playback-details').hidden = false;
    document.querySelector('#replay-again').hidden = true;
    this.idle.pause();
    document.querySelector('#scene').setAttribute('aria-label', '回看过去的时刻，返回场景后继续互动');
  }
  async eventVideo(seq) {
    const id = this.state.id;
    const clip = this.state.events.find(event => event.seq === seq)?.video;
    if (!clip) return;
    if (clip.status === 'ready') {
      this.closeViewer();
      this.showViewer();
      this.viewingSeq = seq;
      document.querySelector('#viewer-title').textContent = '回看这一刻';
      this.videoNote(clip);
      document.querySelector('#replay-nav').hidden = true;
      document.querySelector('#replay-image').hidden = true;
      document.querySelector('#replay-text').textContent = this.state.events.find(event => event.seq === seq).text;
      this.motion.poster = this.state.events.find(event => event.seq === seq).image_url;
      this.motion.dataset.silent = String(!clip.line);
      this.motion.src = clip.url; this.motion.hidden = false;
      this.motion.play().catch(() => { document.querySelector('#viewer-note').textContent = '点击视频播放键观看这一刻。'; });
      return;
    }
    if (clip.status !== 'available') return;
    try {
      const state = await this.request(`/api/session/${id}/events/${seq}/video`, {});
      if (this.state.id === id && state.revision >= this.state.revision) { this.state = state; this.render(); }
    } catch (error) { this.error(error.message); }
  }
  videoNote(clip) {
    const progress = {checking: '返回画面正在确认，暂保留之前的完整场景。', repairing: '正在恢复完整场景，你可以先看视频。'};
    document.querySelector('#viewer-note').textContent = (clip.line ? `片段台词：“${clip.line}”` : '这一刻是无对白的神态反应。')
      + ' ' + (clip.scene_error || progress[clip.scene_status] || '');
  }
  async finishVideo() {
    if (this.replaySession || this.viewingSeq == null || !this.motion.ended) return;
    const id = this.state.id, seq = this.viewingSeq;
    try {
      const state = await this.request(`/api/session/${id}/playback`, {turn: seq, phase: 'end'});
      if (this.state.id !== id || state.revision < this.state.revision) return;
      this.state = state;
      await this.paint(); this.render();
    } catch (error) { this.error(`末帧表情暂未保存：${error.message}`); }
  }
  async openReplay() {
    const id = this.state?.id;
    if (!id || !this.state.world) return;
    try {
      const state = await this.request(`/api/session/${id}/replay`, {});
      if (this.state.id !== id) return;
      if (state.revision >= this.state.revision) this.state = state;
      this.closeViewer();
      this.replaySource = state.replay.events;
      if (this.story.opening_video) this.replaySource.unshift({
        seq: 0, kind: 'opening', actor: '前情', text: this.story.prologue || '',
        video: {status: 'ready', url: this.story.opening_video},
      });
      this.replayEvents = this.cutReplay(this.replaySource);
      this.replayIndex = 0;
      this.replaySession = id;
      this.showViewer();
      this.autoReplay = true;
      document.querySelector('#continuous').textContent = '暂停回放';
      document.querySelector('#replay-nav').hidden = false;
      this.showReplay(); this.syncReplay(); this.render();
    } catch (error) { this.error(error.message); }
  }
  cutReplay(events) {
    const shots = [];
    let pending = [];
    for (const event of events) {
      if (event.kind === 'inspect') continue;
      pending.push(event);
      if (event.actor === '你' && event !== events.at(-1)) continue;
      const shot = {...event, sources: pending.map(item => item.seq), text: pending.map(item => `${item.actor}：${item.text}`).join('\n\n')};
      shot.caption = (pending.find(item => item.actor === '你') || event).text.slice(0, 56);
      shot.key = JSON.stringify([event.visual?.frame, event.world?.objects?.map(obj => [obj.id, obj.dx]), event.music]);
      const previous = shots.at(-1);
      if (previous && !previous.video && !shot.video && !previous.image && !shot.image && previous.key === shot.key) {
        shot.text = previous.text + '\n\n' + shot.text;
        shot.sources.unshift(...previous.sources); shots.pop();
      }
      shots.push(shot); pending = [];
    }
    if (pending.length) {
      const event = pending.at(-1);
      shots.push({...event, sources: pending.map(item => item.seq), text: pending.map(item => `${item.actor}：${item.text}`).join('\n\n'), caption: event.text.slice(0, 56)});
    }
    return shots;
  }
  syncReplay() {
    if (this.replaySession !== this.state.id) return;
    const current = this.replayEvents[this.replayIndex];
    let changed = false;
    for (const event of this.replaySource) {
      const source = this.state.events.find(item => item.seq === event.seq);
      if (source?.image?.status === 'ready' && event.image?.status !== 'ready') {
        event.image = {...source.image};
        changed = true;
      }
      const video = source?.video;
      if (video?.status !== 'ready' || event.video?.status === 'ready') continue;
      event.video = {...video};
      changed = true;
    }
    if (!changed) return;
    this.replayEvents = this.cutReplay(this.replaySource);
    this.replayIndex = Math.max(0, this.replayEvents.findIndex(event => event.sources.includes(current.seq)));
    const updated = this.replayEvents[this.replayIndex];
    document.querySelector('#previous').disabled = this.replayIndex === 0;
    document.querySelector('#next').disabled = this.replayIndex === this.replayEvents.length - 1;
    if (current.video?.status !== 'ready' && (updated.video?.status === 'ready' || updated.image?.url !== current.image?.url)) this.showReplay();
    else document.querySelector('#viewer-title').textContent = `这场经历 · ${this.replayIndex + 1} / ${this.replayEvents.length}`;
  }
  showReplay() {
    clearTimeout(this.replayTimer);
    const event = this.replayEvents[this.replayIndex];
    this.motion.pause();
    document.querySelector('#viewer-title').textContent = `这场经历 · ${this.replayIndex + 1} / ${this.replayEvents.length}`;
    document.querySelector('#viewer-note').textContent = '重复画面已合并；完整对话可展开阅读，也保留在聊天历史中。';
    document.querySelector('#replay-text').textContent = event.text;
    document.querySelector('#replay-caption').textContent = event.caption || '';
    document.querySelector('#replay-caption').hidden = false;
    const hasVideo = event.video?.status === 'ready';
    if (hasVideo && event.kind !== 'opening') document.querySelector('#viewer-note').textContent += event.video.line ? ` 片段台词：“${event.video.line}”` : ' 这一刻是无对白的神态反应。';
    document.querySelector('#replay-again').hidden = true;
    const picture = document.querySelector('#replay-image');
    picture.hidden = hasVideo;
    picture.src = (event.image?.status === 'ready' ? event.image.url : event.image_url) || this.story.cover;
    if (!hasVideo && !matchMedia('(prefers-reduced-motion: reduce)').matches) picture.animate([{opacity: .35}, {opacity: 1}], {duration: 350});
    this.motion.hidden = !hasVideo;
    if (hasVideo) {
      this.motion.dataset.silent = String(event.kind !== 'opening' && !event.video.line);
      this.motion.poster = event.image?.url || event.image_url || this.story.cover;
      this.motion.src = event.video.url;
      if (this.autoReplay) this.motion.play().catch(() => { this.autoReplay = false; document.querySelector('#continuous').textContent = '连续回放'; });
    } else if (this.autoReplay) {
      this.replayTimer = setTimeout(() => this.replayStep(1), 4000);
    }
    document.querySelector('#previous').disabled = this.replayIndex === 0;
    document.querySelector('#next').disabled = this.replayIndex === this.replayEvents.length - 1;
  }
  replayStep(delta) {
    const next = this.replayIndex + delta;
    if (next < 0 || next >= this.replayEvents.length) {
      this.autoReplay = false; document.querySelector('#continuous').textContent = '连续回放'; return;
    }
    this.replayIndex = next; this.showReplay();
  }
  toggleReplay() {
    this.autoReplay = !this.autoReplay;
    document.querySelector('#continuous').textContent = this.autoReplay ? '暂停回放' : '连续回放';
    this.showReplay();
  }
  render() {
    const waiting = this.queue && !this.queue.admitted;
    const preparing = waiting || this.entering || !this.state?.world;
    const entry = document.querySelector('#entry-status');
    const opening = !document.querySelector('#opening').hidden;
    entry.classList.toggle('in-opening', opening);
    if (opening) document.querySelector('#enter-scene').before(entry);
    else document.querySelector('#error').after(entry);
    entry.hidden = !preparing || !document.querySelector('#library').hidden;
    const failed = this.entryError || (!this.state?.world && this.state?.npc_error);
    entry.querySelector('strong').textContent = waiting ? (this.queue.disconnected ? '正在重新连接游玩队列…' : this.queue.position ? `正在排队 · 你是第 ${this.queue.position} 位` : '正在确认游玩名额…') : failed ? '暂时没能进入故事' : '正在准备场景…';
    entry.querySelector('.thinking').hidden = Boolean(failed);
    document.querySelector('#entry-message').textContent = waiting ? '最多两人同时游玩。有空位会自动进入，可以先阅读前情，也可以返回选择故事离开队列。' : failed ? '请点“重新开局”再试一次，或返回选择故事。' : opening ? '可以先阅读前情，准备好后即可进入场景。' : '正在准备人物与场景，请稍候。准备好后即可回应。';
    document.querySelector('#play-area').inert = preparing;
    document.querySelector('#text').disabled = preparing;
    document.querySelector('#text').placeholder = preparing ? '场景准备中，稍后即可输入…' : this.story?.placeholder || '说说你的想法…';
    for (const id of ['send','watch','enter-scene']) document.querySelector('#'+id).disabled = preparing;
    document.querySelector('#enter-scene').textContent = waiting ? '等待游玩名额…' : preparing ? '场景准备中…' : '进入场景 · 由你回应 →';
    document.querySelector('#new').disabled = this.busy || waiting;
    document.querySelector('#choose').disabled = this.entering && !waiting;
    document.querySelector('#replay').disabled = preparing;
    if (waiting) return;
    if (!this.state) return;
    const state = this.state, world = state.world;
    this.journal.sync(state);
    const viewingClip = state.events.find(event => event.seq === this.viewingSeq)?.video;
    if (this.viewing && !this.replaySession && viewingClip && !this.motion.error) this.videoNote(viewingClip);
    const locked = this.busy || !world;
    for (const id of ['send', 'watch']) document.querySelector('#' + id).disabled = locked || state.pending;
    document.querySelector('#send').setAttribute('aria-label', !world ? '准备中' : this.busy ? '提交中' : state.pending ? '等待角色回应' : '发送消息');
    document.querySelector('#reply-status').hidden = !state.pending || !world;
    document.querySelector('#watch').disabled = locked || state.pending;
    document.querySelector('#watch').textContent = state.pending ? '正在回应…' : '让角色继续说 →';
    document.querySelector('#chat-hint').textContent = state.pending ? '正在回应，可先编辑，回复后再发送。' : state.preview ? '画面已更新，物品位置确认中，可以继续说话。' : '';
    document.querySelector('#new').disabled = this.busy;
    document.querySelector('#replay').disabled = !world;
    const inspecting = world?.objects.find(obj => obj.id === this.inspectRequest);
    const noticed = state.pending && state.events.at(-1)?.notice;
    const noticedObject = noticed && world?.objects.find(obj => obj.id === state.events.at(-1).action?.target);
    document.querySelector('.conversation').classList.toggle('reacting', Boolean(noticed));
    document.querySelector('#object-menu').classList.toggle('reacting', Boolean(noticed));
    document.querySelector('#reply-status').classList.toggle('reacting', Boolean(noticed));
    document.querySelector('#reply-label').textContent = noticed
      ? `你留意了「${noticedObject?.name || '这件物品'}」，${world.character} 正在回应…`
      : '正在回应，你可以先编辑下一句话。';
    const status = document.querySelector('#status');
    status.textContent = !world ? '正在准备这一局的故事…' : inspecting ? `正在查看${inspecting.name}…` : noticed ? `${world.character} 注意到了你的动作，正在回应…` : state.pending ? '正在想怎么回应你。' : this.story.rest;
    status.classList.toggle('responding', Boolean(inspecting || noticed));
    if (state.npc_error) this.error(state.npc_error);
    if (!world) return;
    this.renderMoment();
    if (!this.viewing && document.querySelector('#library').hidden) this.audio.score(state.music);
    if (document.querySelector('#library').hidden) document.querySelector('#title').textContent = this.story.title;
    document.querySelector('#character').textContent = world.character;
    const selected = world.objects.find(obj => obj.id === this.selected);
    document.querySelector('#object-panel').hidden = !selected || !this.inspecting;
    document.querySelector('#object-empty').hidden = Boolean(selected && this.inspecting);
    document.querySelector('#object-menu').hidden = Boolean(state.preview) || !selected || !this.inspecting;
    document.querySelector('#suggestion-area').hidden = !state.suggestions?.length || state.pending;
    document.querySelector('#description').textContent = selected?.description || '你们说过的话、做过的事会留在这场经历里。想问点什么，可以直接开口。';
    if (selected?.contents) document.querySelector('#description').textContent = '查看内容：' + selected.contents;
    document.querySelector('#object-hint').textContent = selected?.lead?.hint || '';
    document.querySelector('#visible-label').hidden = !selected;
    document.querySelector('#visible-label').textContent = selected?.visible === false ? '已知物品 · 当前在画面外' : selected?.position_verified ? '眼前所见' : '物品位置待确认';
    const optionsPending = state.pending || state.leads_pending || Boolean(inspecting);
    document.querySelector('#discuss').replaceChildren(this.view.icon('chat'), document.createTextNode(noticed ? `${world.character} 正在回应…` : inspecting ? '正在查看…' : optionsPending ? '选项准备中…' : '询问这件物品'));
    document.querySelector('#discuss').disabled = locked || optionsPending;
    document.querySelector('#discuss').hidden = !optionsPending && Boolean(selected?.lead?.options?.length);
    document.querySelector('#recollections').hidden = !selected;
    const memories = document.querySelector('#memories'); memories.replaceChildren();
    const quotes = (state.object_quotes || []).filter(quote => quote.target === selected?.id);
    for (const quote of quotes) {
      const button = document.createElement('button');
      button.textContent = `${quote.actor}：“${quote.quote}”`;
      button.title = '回到当时的对话'; button.onclick = () => this.recall(quote.seq);
      memories.append(button);
    }
    document.querySelector('#memory-hint').textContent = quotes.length ? '点一句话，回到当时的对话。' : '你们还没聊到这里的故事。想知道的话，可以直接问。';
    document.querySelector('#object-state').textContent = selected?.movable ? (selected.dx ? `已向${selected.dx < 0 ? '左' : '右'}移动 ${Math.abs(selected.dx / 16)} 步 · 位置会保留` : '可以挪动位置 · 当前在起始位置') : '';
    if (selected?.movable && !state.visual.objects[selected.id]) document.querySelector('#object-state').textContent = '暂不可移动 · 可以查看或询问';
    if (selected?.location && selected.location !== '开场画面中的位置') document.querySelector('#object-state').textContent = selected.location;
    const actions = document.querySelector('#actions'); actions.replaceChildren();
    if (selected) {
      for (const choice of state.choices.filter(choice => choice.target === selected.id)) {
        const button = document.createElement('button'); button.textContent = choice.label; button.dataset.direction = choice.delta < 0 ? 'left' : 'right'; button.disabled = locked || optionsPending;
        button.prepend(this.view.icon(choice.delta < 0 ? 'left' : 'right'));
        button.onclick = () => this.act({kind: choice.kind, target: choice.target, delta: choice.delta}); actions.append(button);
      }
      for (const choice of optionsPending ? [] : selected.lead?.options || []) {
        const button = document.createElement('button'); button.textContent = choice.label;
        button.dataset.direction = 'talk'; button.disabled = locked || state.pending;
        button.prepend(this.view.icon(choice.intent || 'chat')); button.title = choice.text;
        button.onclick = () => this.draft(choice); actions.append(button);
      }
    }
    const objectButtons = document.querySelector('#objects'); objectButtons.replaceChildren();
    for (const item of world.objects) {
      const button = document.createElement('button');
      const name = document.createElement('span'); name.textContent = item.name;
      button.append(this.view.thumbnail(item), name); button.title = item.name;
      button.disabled = this.busy || Boolean(state.preview);
      button.setAttribute('aria-pressed', String(this.selected === item.id)); button.onclick = () => this.select(item.id); objectButtons.append(button);
    }
    this.hits();
    if (this.eventRevision !== state.revision) {
      this.renderSuggestions();
      const log = document.querySelector('#events');
      const oldScroll = log.scrollTop;
      const changed = log.dataset.seq !== String(state.events.at(-1)?.seq);
      log.replaceChildren();
      for (const event of state.events) {
        const line = this.eventElement(event); line.id = `event-${event.seq}`;
        log.append(line);
      }
      log.scrollTop = changed && log.lastElementChild ? log.lastElementChild.getBoundingClientRect().top - log.getBoundingClientRect().top + log.scrollTop : oldScroll;
      log.dataset.seq = String(state.events.at(-1)?.seq);
      this.eventRevision = state.revision;
    }
    if (state.npc_ms != null) document.querySelector('#timing').textContent = `最近文字回应 ${(state.npc_ms / 1000).toFixed(1)} 秒。视频仅在主动展开时生成。`;
    for (const button of document.querySelectorAll('#suggestions button')) button.disabled = locked || state.pending;
  }

  eventElement(event) {
    const line = document.createElement('p'); line.className = event.kind === 'say' ? event.actor === '你' ? 'player' : 'npc' : event.kind;
    line.tabIndex = -1;
    const actor = document.createElement('strong'); actor.textContent = event.kind === 'inspect' ? '查看' : event.actor;
    line.append(actor, document.createTextNode(event.text));
    const previous = this.state.events[this.state.events.indexOf(event) - 1];
    if (event.kind === 'say' && event.actor !== '你' && previous?.kind === 'inspect' && previous.notice) {
      const object = this.state.world.objects.find(obj => obj.id === previous.action?.target);
      const origin = document.createElement('small'); origin.className = 'reaction-origin';
      origin.textContent = `回应你对「${object?.name || '这件物品'}」的留意`;
      actor.after(origin); line.classList.add('notice-reply');
    }
    if (event.image) {
      const note = document.createElement('small'); note.className = 'image-status';
      const labels = {queued: '画面更新排队中，仍可继续互动', generating: '正在绘制这一刻的画面…', locating: '新图已生成，正在确认互动位置…', ready: '这一刻的画面已记录', failed: '画面更新失败，保留原图', unavailable: '图片服务未连接，保留原图'};
      note.textContent = labels[event.image.status]; note.dataset.status = event.image.status;
      line.append(note);
    }
    if (event.video) {
      const button = document.createElement('button');
      const labels = {available: '▷ 让这一幕动起来', queued: '视频排队中…', generating: '正在生成视频…', ready: '▶ 查看视频', failed: '视频暂不可用'};
      button.textContent = labels[event.video.status];
      button.disabled = !['available', 'ready'].includes(event.video.status);
      button.className = 'event-video'; button.dataset.seq = event.seq;
      button.onclick = () => this.eventVideo(event.seq);
      line.append(button);
    }
    if (event.kind === 'say') {
      const save = document.createElement('button'); save.className = 'event-save';
      save.textContent = '记入手记'; save.title = '将这段对话收录到故事手记';
      save.onclick = () => this.journal.remember(event.seq); line.append(save);
    }
    return line;
  }

  renderSuggestions() {
    const choices = this.state.pending ? [] : this.state.suggestions || [];
    const area = document.querySelector('#suggestion-area'); area.hidden = !choices.length;
    const list = document.querySelector('#suggestions'); list.replaceChildren();
    for (const choice of choices) {
      const button = document.createElement('button');
      const copy = document.createElement('span'), label = document.createElement('strong'), detail = document.createElement('small');
      label.textContent = choice.label; detail.textContent = choice.text; copy.append(label, detail);
      button.title = choice.text;
      button.append(this.view.icon(choice.intent || 'chat'), copy, this.view.icon('right'));
      button.disabled = this.busy || this.state.pending;
      button.onclick = () => this.draft(choice);
      list.append(button);
    }
  }
  polygon(id) {
    if (this.state.regions?.[id]) return this.state.regions[id];
    const obj = this.state.world.objects.find(obj => obj.id === id);
    const delta = obj.dx - this.state.visual.positions[id];
    return this.state.visual.objects[id].polygon.map(([x,y]) => [x + delta, y + Math.round(delta * this.state.slopes[id])]);
  }
  targetPolygon(id) {
    if (id !== 'character') return this.polygon(id);
    const [x1,y1,x2,y2] = this.state.viewport.character_region;
    return [[x1,y1],[x2,y1],[x2,y2],[x1,y2]];
  }
  hits() {
    const svg = document.querySelector('#hits'); svg.replaceChildren();
    if (this.state.preview) { this.view.render([]); return; }
    const ns = 'http://www.w3.org/2000/svg';
    const [x1, y1, x2, y2] = this.state.viewport.character_region;
    const targets = [{id: 'character', name: this.state.world.character, polygon: [[x1,y1],[x2,y1],[x2,y2],[x1,y2]]}];
    for (const obj of this.state.world.objects) {
      if (!obj.position_verified) continue;
      targets.push({id: obj.id, name: obj.name, polygon: this.polygon(obj.id)});
    }
    this.view.render(targets);
    for (const item of targets) {
      const hit = document.createElementNS(ns, 'polygon');
      hit.setAttribute('points', item.polygon.map(point => point.join(',')).join(' '));
      hit.setAttribute('fill', 'transparent'); hit.setAttribute('role', 'button'); hit.setAttribute('tabindex', '0');
      hit.setAttribute('aria-label', `查看${item.name}`); hit.dataset.object = item.id;
      hit.classList.toggle('selected', this.selected === item.id);
      hit.onclick = () => this.select(item.id);
      hit.onkeydown = event => { if (['Enter', ' '].includes(event.key)) { event.preventDefault(); this.select(item.id); } };
      svg.append(hit);
    }
  }
}
window.room = new RoleplayRoom();
