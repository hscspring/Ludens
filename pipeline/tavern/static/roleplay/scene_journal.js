class SceneJournal {
  constructor(room) {
    this.room = room;
    this.dialog = document.querySelector('#journal');
    this.button = document.querySelector('#journal-open');
    this.list = document.querySelector('#journal-entries');
    this.filter = 'all';
    this.entries = [];
    this.button.onclick = () => this.open();
    document.querySelector('#journal-close').onclick = () => this.dialog.close();
    document.querySelector('#journal-filters').onclick = event => {
      const filter = event.target.closest('[data-filter]');
      if (!filter) return;
      this.filter = filter.dataset.filter; this.render();
    };
  }
  sync(state) {
    this.button.hidden = !state.world || !document.querySelector('#library').hidden;
    this.button.disabled = !state.world || this.room.entering;
    if (!state.world) return;
    if (this.session !== state.id) {
      this.session = state.id; this.filter = 'all'; this.signature = null;
      this.key = `ludens-journal-${state.id}`;
      this.notes = {saved: [], question: [], manual: [], seen: []};
      try {
        const stored = JSON.parse(localStorage.getItem(this.key) || '{}');
        for (const key of Object.keys(this.notes)) if (Array.isArray(stored[key])) this.notes[key] = stored[key];
      } catch (error) { this.room.error('手记标记读取失败，仍可查看本局记录。'); }
    }
    const entries = [], seen = new Set();
    const names = new Map(state.world.objects.map(obj => [obj.id, obj.name]));
    const add = (event, id, kind, title, text, target = null) => {
      const identity = `${kind === '物品变化' ? event.seq : event.actor}:${text}`;
      if (!text?.trim() || seen.has(identity)) return;
      seen.add(identity);
      entries.push({id, kind, title, text, target, seq: event.seq, actor: event.actor});
    };
    for (const event of state.events) {
      if (event.kind === 'inspect') {
        const target = event.action?.target;
        add(event, `inspect:${event.seq}`, '查看所得', names.get(target) || '一次发现', event.text, target);
      }
      if (event.kind === 'action' && event.action?.kind === 'move')
        add(event, `action:${event.seq}`, '行动记录', names.get(event.action.target) || '一次行动', event.text, event.action.target);
      for (const item of event.object_updates || [])
        add(event, `state:${event.seq}:${item.id}`, '物品变化', names.get(item.id), `${item.description} · ${item.location}`, item.id);
      for (const [i, quote] of (event.object_quotes || []).entries()) {
        if (event.text.includes(quote.quote) && names.has(quote.target))
          add(event, `quote:${event.seq}:${i}`, '角色原话', names.get(quote.target), quote.quote, quote.target);
      }
      for (const [i, quote] of (event.memories || []).entries()) {
        if (event.text.includes(quote)) add(event, `memory:${event.seq}:${i}`, '重要交流', `${event.actor}的话`, quote);
      }
      if (event.moment && !event.memories?.length)
        add(event, `moment:${event.seq}`, '剧情时刻', event.moment.title, event.text, event.moment.target === 'character' ? null : event.moment.target);
      if (this.notes.manual.includes(event.seq)) add(event, `event:${event.seq}`, '手动收录', `${event.actor}的这段话`, event.text);
    }
    this.entries = entries;
    const unread = entries.filter(entry => !this.notes.seen.includes(entry.id)).length;
    this.button.textContent = unread ? `故事手记 · ${unread} 条新记录` : `故事手记${entries.length ? ` · ${entries.length}` : ''}`;
    this.button.classList.toggle('has-new', unread > 0);
    const signature = JSON.stringify([entries, this.notes, state.pending, state.preview, this.room.busy, state.world.objects.map(obj => [obj.id, obj.position_verified])]);
    if (signature !== this.signature) {
      this.signature = signature;
      if (this.dialog.open) this.render();
    }
  }
  persist() {
    try { localStorage.setItem(this.key, JSON.stringify(this.notes)); }
    catch (error) { this.room.error('浏览器未能保存手记标记，本次打开期间仍可使用。'); }
  }
  open() {
    if (!this.room.state?.world || this.room.entering) return;
    this.sync(this.room.state);
    if (!this.dialog.open) this.dialog.showModal();
    this.notes.seen = this.entries.map(entry => entry.id);
    this.persist(); this.sync(this.room.state); this.render();
  }
  remember(seq) {
    if (!this.notes.manual.includes(seq)) this.notes.manual.push(seq);
    this.sync(this.room.state);
    const event = this.room.state.events.find(event => event.seq === seq);
    const entry = this.entries.find(entry => entry.text === event?.text) || this.entries.find(entry => entry.seq === seq);
    if (entry && !this.notes.saved.includes(entry.id)) this.notes.saved.push(entry.id);
    this.filter = 'saved'; this.open();
  }
  toggle(entry, field) {
    this.notes[field] = this.notes[field].includes(entry.id)
      ? this.notes[field].filter(id => id !== entry.id) : [...this.notes[field], entry.id];
    this.persist(); this.render();
    this.list.querySelector(`[data-entry="${entry.id}"] [data-field="${field}"]`)?.focus();
  }
  ask(entry) {
    if (this.room.busy || this.room.state.pending) return;
    this.dialog.close();
    this.room.closeViewer();
    const text = `关于${entry.title}，这句「${entry.text.slice(0, 300)}」我想再问清楚一点。`;
    this.room.draft({text});
  }
  render() {
    for (const button of document.querySelectorAll('#journal-filters button'))
      button.setAttribute('aria-pressed', String(button.dataset.filter === this.filter));
    const scroll = this.list.scrollTop;
    this.list.replaceChildren();
    const entries = [...this.entries].reverse().filter(entry => this.filter === 'all' || this.notes[this.filter].includes(entry.id))
      .sort((a, b) => Number(this.notes.saved.includes(b.id)) - Number(this.notes.saved.includes(a.id)));
    if (!entries.length) {
      const empty = document.createElement('p'); empty.className = 'journal-empty';
      empty.textContent = this.filter === 'all' ? '还没有留下记录。看看身边的物品，或从一段对话里点“记入手记”。'
        : this.filter === 'question' ? '还没有待追问的事。遇到在意的说法，可以标记在这里。' : '还没有主动收录的记录。点一条记录的“收录”，把它留在这里。';
      this.list.append(empty);
    }
    for (const entry of entries) {
      const card = document.createElement('article'); card.className = 'journal-card'; card.dataset.entry = entry.id;
      const meta = document.createElement('small'); meta.className = 'journal-meta';
      meta.textContent = `${entry.kind} · ${entry.kind === '查看所得' ? '物品可见内容' : entry.actor + '的叙述'}${this.notes.question.includes(entry.id) ? ' · 待追问' : ''}`;
      const title = document.createElement('h3'); title.textContent = entry.title;
      const text = document.createElement('p'); text.textContent = entry.text;
      const controls = document.createElement('div'); controls.className = 'journal-actions';
      for (const [field, label, active] of [['saved', '收录', '已收录'], ['question', '标为待追问', '取消待追问']]) {
        const button = document.createElement('button'); button.dataset.field = field;
        button.textContent = this.notes[field].includes(entry.id) ? active : label;
        button.setAttribute('aria-pressed', String(this.notes[field].includes(entry.id)));
        button.onclick = () => this.toggle(entry, field); controls.append(button);
      }
      const source = document.createElement('button'); source.textContent = '回到出处';
      source.onclick = () => { this.dialog.close(); this.room.closeViewer(); this.room.recall(entry.seq); };
      const ask = document.createElement('button'); ask.textContent = '接着问';
      ask.disabled = this.room.busy || this.room.state.pending; ask.onclick = () => this.ask(entry);
      controls.append(source, ask);
      if (entry.target) {
        const object = this.room.state.world.objects.find(obj => obj.id === entry.target);
        const locate = document.createElement('button'); locate.textContent = object?.position_verified ? '看看物品' : '查看物品记录';
        locate.disabled = !object || Boolean(this.room.state.preview) || this.room.busy;
        locate.onclick = () => { this.dialog.close(); this.room.selected = null; this.room.select(entry.target); };
        controls.append(locate);
      }
      card.append(meta, title, text, controls); this.list.append(card);
    }
    this.list.scrollTop = scroll;
  }
}
