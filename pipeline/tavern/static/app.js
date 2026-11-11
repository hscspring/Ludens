const names = {
  bucket: "铁桶",
  crate: "木箱",
  ledger: "旧账册",
  towel_1: "第一条毛巾",
  towel_2: "第二条毛巾",
  leak: "窗边的漏水",
  cassian: "Cassian",
};

class SceneView {
  constructor(root, onSelect) {
    this.root = root;
    this.onSelect = onSelect;
    this.props = {};
    this.puddle = document.createElement("div");
    this.puddle.className = "puddle";
    root.append(this.puddle);
    const drip = document.createElement("div");
    drip.className = "drip";
    root.append(drip);
    for (const [name, art] of Object.entries({
      bucket: "bucket",
      crate: "crate",
      ledger: "ledger",
      towel_1: "towel",
      towel_2: "towel",
    })) {
      const button = document.createElement("button");
      button.className = "prop";
      button.dataset.object = name;
      button.setAttribute("aria-label", names[name]);
      button.innerHTML = `<svg viewBox="${art === "crate" ? "0 0 240 165" : art === "ledger" ? "0 0 180 120" : art === "towel" ? "0 0 190 110" : "0 0 180 180"}" aria-hidden="true"><use href="#${art}-art"/></svg><span class="tag">${names[name]}</span>`;
      button.onclick = () => onSelect?.(name);
      if (!onSelect) button.tabIndex = -1;
      root.append(button);
      this.props[name] = button;
    }
    for (const [name, className, html] of [
      ["leak", "leak-marker", "◇"],
      ["cassian", "cassian-marker", "<span>Cassian</span>"],
    ]) {
      const button = document.createElement("button");
      button.className = className;
      button.setAttribute("aria-label", names[name]);
      button.innerHTML = html;
      button.onclick = () => onSelect?.(name);
      if (!onSelect) button.tabIndex = -1;
      root.append(button);
    }
  }

  render(world, selected = "") {
    const safe = world.crate === "safe";
    const positions = {
      bucket: world.bucket === "catch" ? [80, 57, 9] : [12, 82, 10],
      crate: safe ? [53, 71, 17] : [72, 69, 17],
      ledger:
        world.ledger === "shelf" ? [64, 82, 10] : [safe ? 53 : 72, 59, 10],
      towel_1: [88, 76, 10],
      towel_2: [91, 88, 10],
    };
    for (const [name, node] of Object.entries(this.props)) {
      const [x, y, w] = positions[name];
      Object.assign(node.style, {
        left: `${x}%`,
        top: `${y}%`,
        width: `${w}%`,
      });
      node.classList.toggle("selected", name === selected);
      node.classList.toggle(
        "catch",
        name === "bucket" && world.bucket === "catch",
      );
      node.classList.toggle("wet", world.towels[name] === "wet");
      node.classList.toggle("damp", world.towels[name] === "damp");
      const condition = world.towels[name];
      node.querySelector(".tag").textContent =
        names[name] +
        (condition
          ? ` · ${{ dry: "干", damp: "潮", wet: "湿" }[condition]}`
          : "");
    }
    this.puddle.style.opacity = world.puddle ? "1" : "0";
  }
}

class TavernApp {
  constructor() {
    this.state = null;
    this.videoEnabled = false;
    this.selected = "leak";
    this.actionBusy = false;
    this.historyEvents = [];
    this.scene = new SceneView(document.querySelector("#scene"), (name) =>
      this.select(name),
    );
    this.replayScene = new SceneView(document.querySelector("#replay-scene"));
    this.conversationRevision = -1;
    document.querySelector("#chat").onsubmit = async (event) => {
      event.preventDefault();
      const input = document.querySelector("#message");
      const text = input.value.trim();
      if (text && (await this.act({ kind: "talk", text }))) input.value = "";
    };
    document.querySelector("#help").onclick = () =>
      this.act({ kind: "talk", text: "你能搭把手吗？看看现在最需要做什么。" });
    document.querySelector("#watch").onclick = () => this.act({ kind: "wait" });
    document.querySelector("#restart").onclick = () => this.start(true);
    document.querySelector("#history-button").onclick = () =>
      this.openHistory();
    document.querySelector("#close-history").onclick = () =>
      document.querySelector("#history").close();
    document.querySelector("#timeline").oninput = (event) =>
      this.showMoment(Number(event.target.value));
    document.querySelector("#generate-video").onclick = () =>
      this.generateVideo();
  }

  async request(path, options = {}) {
    const response = await fetch(path, {
      ...options,
      headers: { "Content-Type": "application/json" },
    });
    const data = await response.json();
    if (!response.ok)
      throw new Error(
        typeof data.detail === "string"
          ? data.detail
          : "这次操作没有完成，请再试一次。",
      );
    return data;
  }

  async start(fresh = false) {
    try {
      const settings = await this.request("/static/settings.json");
      this.videoEnabled = settings.video_enabled;
      const saved = fresh
        ? null
        : localStorage.getItem("ludens-tavern-session");
      let next;
      if (saved) {
        const response = await fetch(
          `/api/session/${encodeURIComponent(saved)}`,
        );
        if (response.status === 404) {
          next = await this.request("/api/session", { method: "POST" });
          this.notice("上次服务中的经历已结束，已重新进入酒馆。");
        } else {
          if (!response.ok) throw new Error("暂时无法连接酒馆，请刷新重试。");
          next = await response.json();
        }
      } else next = await this.request("/api/session", { method: "POST" });
      this.state = null;
      this.conversationRevision = -1;
      this.selected = "leak";
      localStorage.setItem("ludens-tavern-session", next.id);
      this.accept(next);
      if (fresh) this.notice("你重新走进了酒馆。");
    } catch (error) {
      this.notice(error.message);
    }
  }

  async poll() {
    if (this.state) {
      const id = this.state.id;
      try {
        const next = await this.request(`/api/session/${id}`);
        if (this.state.id === id) this.accept(next);
      } catch (error) {
        this.notice(error.message);
      }
    }
    setTimeout(() => this.poll(), 800);
  }

  accept(next) {
    if (this.state?.id === next.id && next.revision < this.state.revision)
      return;
    this.state = next;
    this.scene.render(next.world, this.selected);
    this.renderObject();
    const w = next.world;
    this.status(
      "#water-status",
      w.bucket === "catch",
      "水已接住",
      "漏水还没接住",
    );
    this.status(
      "#records-status",
      w.records_safe,
      "账册已在干处",
      "账册仍在窗边",
    );
    this.status("#counter-status", !w.puddle, "积水已擦掉", "柜台上还有积水");
    document.querySelector("#settled").textContent = w.settled
      ? "这边终于安顿好了。雨还在下，你们还有时间说说话。"
      : "不用急着寻找标准答案。你们可以一起想办法。";
    document.querySelector("#npc-status").textContent = next.npc_error
      ? "回应暂时中断 · 你仍可行动"
      : next.pending
        ? "正在回应 · 你可以继续行动"
        : "在你身旁";
    document
      .querySelector("#thinking-dot")
      .classList.toggle("busy", next.pending);
    if (this.conversationRevision !== next.revision) {
      const conversation = document.querySelector("#conversation");
      conversation.replaceChildren();
      for (const event of next.events.slice(-8)) {
        const node = document.createElement("p");
        node.className = `event ${event.kind} ${event.actor === "你" ? "player" : ""}`;
        if (event.kind === "say") {
          const who = document.createElement("span");
          who.className = "who";
          who.textContent = event.actor;
          node.append(who);
        }
        node.append(document.createTextNode(event.text));
        conversation.append(node);
      }
      if (next.npc_error) {
        const node = document.createElement("p");
        node.className = "event error";
        node.textContent = next.npc_error;
        conversation.append(node);
      }
      conversation.scrollTop = conversation.scrollHeight;
      this.conversationRevision = next.revision;
    }
    this.renderVideo();
  }

  status(selector, done, yes, no) {
    const node = document.querySelector(selector);
    node.textContent = (done ? "✓ " : "○ ") + (done ? yes : no);
    node.classList.toggle("done", done);
  }

  select(name) {
    this.selected = name;
    if (this.state) {
      this.scene.render(this.state.world, name);
      this.renderObject();
    }
  }

  renderObject() {
    const w = this.state.world;
    const descriptions = {
      bucket:
        w.bucket === "catch"
          ? "桶正在接水。移走它，水就会重新落到柜台上。"
          : "一只空铁桶。把它放到窗边柜台的漏水处，就能接住水。",
      crate:
        w.crate === "safe"
          ? "木箱已经在干处。"
          : "木箱挨着漏水处，可以整个搬走，也可以只取出里面的账册。",
      ledger:
        w.ledger === "shelf"
          ? "你们把账册单独放到了干燥的柜台上。"
          : `一本旧的手写账册，还在${w.crate === "safe" ? "干处的" : "窗边的"}木箱里。搬箱子会带着它一起移动。`,
      leak: "窗框上方还在漏水，关着的窗户挡不住它。可以先接水、保护账册，再处理积水。",
      cassian:
        "他在意这些留下来的旧账册。你可以请他帮忙，也可以问问原因；他会自己判断接下来做什么。",
    };
    for (const [name, condition] of Object.entries(w.towels))
      descriptions[name] = {
        dry: "这条毛巾还是干的，可以用来擦水。",
        wet: "它已经湿透了。拧掉一些水后，还可以继续用。",
        damp: "它拧过了，仍然潮湿，但还可以吸水。",
      }[condition];
    document.querySelector("#object-title").textContent = names[this.selected];
    document.querySelector("#object-description").textContent =
      descriptions[this.selected];
    const container = document.querySelector("#object-actions");
    container.replaceChildren();
    for (const choice of this.state.choices.filter(
      (c) => c.object === this.selected,
    )) {
      const button = document.createElement("button");
      button.textContent = choice.label;
      button.dataset.action = choice.kind;
      button.disabled = this.actionBusy;
      button.onclick = () =>
        this.act({ kind: choice.kind, target: choice.target || "" });
      container.append(button);
    }
    if (this.selected === "cassian") {
      const button = document.createElement("button");
      button.textContent = "请他看看现在能帮什么";
      button.onclick = () =>
        this.act({
          kind: "talk",
          text: "你觉得现在最需要做什么？能帮我一下吗？",
        });
      container.append(button);
    }
  }

  async act(action) {
    if (!this.state || this.actionBusy) return false;
    this.actionBusy = true;
    this.renderObject();
    const id = this.state.id;
    try {
      const next = await this.request(`/api/session/${id}/act`, {
        method: "POST",
        body: JSON.stringify(action),
      });
      if (this.state.id !== id) return false;
      this.accept(next);
      const event = [...next.events].reverse().find((e) => e.actor === "你");
      this.notice(
        action.kind === "talk"
          ? "你说的话已传达。等待回应时，可以继续操作物品。"
          : event.text,
      );
      return true;
    } catch (error) {
      this.notice(error.message);
      return false;
    } finally {
      this.actionBusy = false;
      this.renderObject();
    }
  }

  notice(text) {
    document.querySelector("#notice").textContent = text;
  }

  openHistory() {
    if (!this.state) return;
    this.historyEvents = this.state.events.slice();
    const slider = document.querySelector("#timeline");
    slider.max = String(this.historyEvents.length - 1);
    slider.value = slider.max;
    const list = document.querySelector("#history-list");
    list.replaceChildren();
    this.historyEvents.forEach((event, index) => {
      const button = document.createElement("button");
      button.className = "history-entry";
      button.textContent = `${event.actor} · ${event.text}`;
      button.onclick = () => {
        slider.value = index;
        this.showMoment(index);
      };
      list.append(button);
    });
    this.showMoment(this.historyEvents.length - 1);
    document.querySelector("#history").showModal();
  }

  showMoment(index) {
    const event = this.historyEvents[index];
    if (!event) return;
    this.replayScene.render(event.world);
    document.querySelector("#replay-caption").textContent =
      `${index + 1} / ${this.historyEvents.length} · ${event.text}`;
    document
      .querySelectorAll(".history-entry")
      .forEach((node, i) => node.classList.toggle("active", i === index));
  }

  async generateVideo() {
    if (!this.state || !this.videoEnabled) return;
    const id = this.state.id;
    try {
      const next = await this.request(`/api/session/${id}/replay`, {
        method: "POST",
      });
      if (this.state.id === id) this.accept(next);
    } catch (error) {
      document.querySelector("#video-status").textContent = error.message;
    }
  }

  renderVideo() {
    const replay = this.state.replay;
    const button = document.querySelector("#generate-video");
    if (!this.videoEnabled) {
      button.disabled = true;
      button.textContent = "视频回放暂未开启";
      document.querySelector("#video-status").textContent =
        "视频生成已暂停。可以拖动时间线，立即回看每次操作和物品变化。";
      document.querySelector("#replay-video").hidden = true;
      return;
    }
    button.disabled = ["queued", "generating"].includes(replay.status);
    button.textContent = button.disabled
      ? "短片制作中…"
      : replay.status === "ready"
        ? "根据最新经历再生成一段"
        : "把这段经历生成短片";
    document.querySelector("#video-status").textContent = {
      idle: "短片根据经历改编，生成期间仍可继续玩。",
      queued: "已记录此刻的经历，正在准备短片。你可以关闭这里继续玩。",
      generating:
        "正在生成几秒钟的经历短片，可能需要一分钟。不会阻塞酒馆里的操作。",
      ready:
        "根据生成时记录的经历改编。精确的行动与物品状态，可以在左侧时间线回看。",
      failed: replay.error,
    }[replay.status];
    const video = document.querySelector("#replay-video");
    video.hidden = replay.status !== "ready";
    if (replay.status === "ready" && video.getAttribute("src") !== replay.url)
      video.src = replay.url;
  }
}

const app = new TavernApp();
await app.start();
app.poll();
