class SceneCreation {
  constructor() {
    this.form = document.querySelector('#create-form');
    this.form.onsubmit = event => { event.preventDefault(); this.submit(); };
    this.list();
  }
  async request(path, body) {
    const response = await fetch(path, body === undefined ? {cache:'no-store'} : {
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)
    });
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '请检查输入内容。');
    return data;
  }
  async list() {
    try {
      const stories = await this.request('/api/stories');
      const list = document.querySelector('#created'); list.replaceChildren();
      for (const story of stories) {
        const link = document.createElement('a'); link.textContent = story.title;
        link.href = '/?story=' + encodeURIComponent(story.id); list.append(link);
      }
    } catch (error) { document.querySelector('#error').textContent = error.message; }
  }
  async submit() {
    document.querySelector('#submit').disabled = true;
    document.querySelector('#error').textContent = '';
    document.querySelector('#enter').hidden = true;
    try {
      const data = await this.request('/api/stories/create', Object.fromEntries(new FormData(this.form)));
      this.id = data.id;
      document.querySelector('#progress').hidden = false;
      await this.poll();
    } catch (error) { this.fail(error.message); }
  }
  async poll() {
    try {
      const state = await this.request('/api/stories/creation/' + this.id);
      document.querySelector('#stage').textContent = state.stage;
      document.querySelector('#note').textContent = '已等待 ' + Math.max(0,Math.floor(Date.now()/1000-state.started)) + ' 秒';
      if (state.status === 'failed') { this.fail(state.error); return; }
      if (state.status === 'ready') {
        const link = document.querySelector('#enter'); link.href = '/?story=' + encodeURIComponent(state.story_id); link.hidden = false;
        document.querySelector('#submit').disabled = false; await this.list(); return;
      }
      setTimeout(() => this.poll(), 1500);
    } catch (error) { this.fail(error.message); }
  }
  fail(message) {
    document.querySelector('#stage').textContent = '本次创建未完成';
    document.querySelector('#error').textContent = message;
    document.querySelector('#submit').disabled = false;
  }
}
new SceneCreation();
