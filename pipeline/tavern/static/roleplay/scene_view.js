class SceneView {
  constructor(room) {
    this.room = room;
    this.camera = document.querySelector('#camera');
    this.markers = document.querySelector('#markers');
    this.thumbnails = new Map();
    new ResizeObserver(() => { if (this.room.state?.world) this.room.hits(); }).observe(this.camera);
  }
  ambient() {
    if (!document.body.classList.contains('playing') || this.room.viewing) return;
    const backdrop = document.querySelector('#backdrop'), context = backdrop.getContext('2d');
    const {left,top,width,height} = this.camera.getBoundingClientRect();
    if (!width || !height) return;
    backdrop.width = innerWidth; backdrop.height = innerHeight;
    const columns = [[0,left,0,128,-1],[left,width,0,672,1],[left+width,innerWidth-left-width,544,128,-1]];
    const rows = [[0,top,0,24,-1],[top,height,0,384,1],[top+height,innerHeight-top-height,360,24,-1]];
    for (const [x,w,sx,sw,flipX] of columns) for (const [y,h,sy,sh,flipY] of rows) {
      if (w <= 0 || h <= 0) continue;
      context.save();
      context.translate(x + (flipX < 0 ? w : 0), y + (flipY < 0 ? h : 0));
      context.scale(flipX,flipY);
      context.drawImage(this.room.canvas,sx,sy,sw,sh,0,0,w,h);
      context.restore();
    }
  }
  center(id) {
    if (id === 'character' && this.room.state.viewport.expression_region) {
      const [x1,y1,x2,y2] = this.room.state.viewport.expression_region;
      return [(x1+x2)/2,y2];
    }
    const points = this.room.targetPolygon(id);
    const xs = points.map(point => point[0]), ys = points.map(point => point[1]);
    return [(Math.min(...xs) + Math.max(...xs)) / 2, Math.min(...ys) + (Math.max(...ys) - Math.min(...ys)) * (id === 'character' ? .25 : .5)];
  }
  icon(name) {
    const paths = {
      chat: 'M21 11a8 8 0 0 1-8 8H7l-5 3 2-6a8 8 0 1 1 17-5ZM8 11h.01M12 11h.01M16 11h.01',
      ask: 'M9 8a3 3 0 1 1 5 2c-1 1-2 1-2 3M12 17h.01M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z',
      comfort: 'M20 5c-3-3-7-1-8 1-1-2-5-4-8-1-4 4 1 9 8 14 7-5 12-10 8-14Z',
      challenge: 'M4 5h16v12h-6l-4 4v-4H4ZM12 8v4M12 14h.01',
      decline: 'M6 6l12 12M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z',
      agree: 'm6 12 4 4 8-8M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z',
      note: 'M6 3h9l4 4v14H6ZM14 3v5h5M9 12h7M9 16h7',
      search: 'M16 16l5 5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0Z',
      left: 'M20 12H4m6-6-6 6 6 6',
      right: 'M4 12h16m-6-6 6 6-6 6',
      box: 'm3 7 9-4 9 4v10l-9 4-9-4Zm0 0 9 4 9-4M12 11v10',
    };
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 24 24'); svg.setAttribute('aria-hidden', 'true'); svg.classList.add('ui-icon');
    const path = document.createElementNS(svg.namespaceURI, 'path'); path.setAttribute('d', paths[name]); svg.append(path);
    return svg;
  }
  thumbnail(item) {
    const key = `${this.room.state.id}:${item.id}`;
    if (!item.position_verified || this.room.state.preview) return this.thumbnails.get(key) || this.icon('box');
    const points = this.room.polygon(item.id), source = this.room.canvas;
    const xs = points.map(point => point[0]), ys = points.map(point => point[1]);
    const x = Math.max(0, Math.min(...xs) - 8), y = Math.max(0, Math.min(...ys) - 8);
    const w = Math.min(source.width, Math.max(...xs) + 8) - x, h = Math.min(source.height, Math.max(...ys) + 8) - y;
    const canvas = document.createElement('canvas'); canvas.width = 112; canvas.height = 80; canvas.setAttribute('aria-hidden', 'true');
    const scale = Math.min(canvas.width / w, canvas.height / h);
    canvas.getContext('2d').drawImage(source, x, y, w, h, (canvas.width-w*scale)/2, (canvas.height-h*scale)/2, w*scale, h*scale);
    this.thumbnails.set(key, canvas);
    return canvas;
  }
  positionMenu() {
    const menu = document.querySelector('#object-menu');
    if (menu.hidden) return;
    const scene = document.querySelector('#scene').getBoundingClientRect(), camera = this.camera.getBoundingClientRect();
    const selected = this.room.state.world.objects.find(obj => obj.id === this.room.selected);
    const [x,y] = selected?.position_verified ? this.center(this.room.selected) : [336, 370], half = menu.offsetWidth / 2;
    menu.style.left = `${Math.max(half+12, Math.min(scene.width-half-12, camera.left-scene.left+x/672*camera.width))}px`;
    menu.style.top = `${Math.max(12, Math.min(scene.height-menu.offsetHeight-12, camera.top-scene.top+y/384*camera.height-menu.offsetHeight-24))}px`;
  }
  render(targets) {
    this.ambient();
    this.positionMenu();
    const focused = this.markers.contains(document.activeElement) ? document.activeElement.dataset.object : null;
    this.markers.replaceChildren();
    for (const item of targets.filter(item => item.id !== 'character')) {
      let [x,y] = this.center(item.id);
      if (item.id !== 'character') {
        const xs = item.polygon.map(point => point[0]);
        if (Math.max(...xs) - Math.min(...xs) > 300) x = Math.max(...xs) - 30;
      }
      const button = document.createElement('button');
      button.disabled = this.room.busy;
      button.dataset.object = item.id; button.setAttribute('aria-label', item.name);
      button.setAttribute('aria-expanded', String(this.room.selected === item.id && this.room.inspecting));
      button.style.setProperty('--pulse-delay', `${targets.indexOf(item) * -.6}s`);
      button.setAttribute('aria-pressed', String(this.room.selected === item.id));
      button.style.left = `${Math.max(8,Math.min(85,x / 672 * 100))}%`;
      button.style.top = `${Math.max(12,Math.min(86,y / 384 * 100))}%`;
      button.onclick = () => this.room.select(item.id);
      this.markers.append(button);
      if (focused === item.id) button.focus({preventScroll:true});
    }
  }
}
