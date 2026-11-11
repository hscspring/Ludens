# Ludens — 走进一个活的世界去 Play 的 Roleplay

**2026-10-16 本机演示部署：** 入口 http://24.144.74.187/ ，网页服务为 `8794`。同一交互输入实测，Gemini 两次为 5.08 / 7.74 秒，本地双卡 SFT 为 16.48 / 17.07 秒；输出长度不同，属于端到端体验对照，样本量仅一条输入各两次。按 Sean 决定取消文本四卡试验，已重新启动网页服务，默认 Gemini 主用、DeepSeek 兜底。自研 SFT 权重和验收结果保留，短 RL 未显示优于 SFT。

视频保持 MiniMax-H3 Turbo8，GPU 2–5（`8800`）；图片为 FLUX.2 Klein4B 与 SAM2，GPU 6（`18781`）。视频原生语音配已有背景音乐，无独立音频模型。相同输入的 4 秒视频首次约 23.97 秒、第二次约 3.84 秒（包含后处理，单次测量）；播放文件为 640×366、16 fps。旧文本服务已停止。验收记录位于 `/mnt/sv0/sean/outputs/ludens/local-demo-20261016/`。

**2026-09-30 当前产品基准：[暂定最终产品设计 v0.1](research/roleplay_product_v0_1.md)。** 已确认按此调整酒馆Demo：交互与图片为主，视频由用户按需展开，事后回看完整经历。以下旧版本说明保留为历史记录，当前实现与服务状态以本轮验收为准。

> **2026-09-22 产品方向：交互与参与感优先。当前微场景已获 Sean 试玩认可；下一步复用已有开源模型，让画面与声音随对话、行动变化。影游可以是副产品。** 当前共识、验证标准与伙伴分工见 [团队讨论稿](research/hackathon_team_brief.md)。下文保留早期静帧原型的说明，不代表当前产品定位与交互 Demo 的运行方式。

**目标流程：** 输入现有角色卡的 `personality`、`scenario`、`welcomeMessage` → 初始化场景图、人物图、相关物品与状态 → 点选操作和自由交流 → 人物回应、状态延续及以人物为主的实时视频反馈。完整自动初始化与实时人物视频尚未实现。

模块按物品、背景、人物相对独立：物品生成、新增和变化由专门代码统一管理，背景由生图模型生成，人物模块承接人物形象与动态表现。**图里的东西就是能互动的东西，互动造成的变化会被记住。** 完整主线与职责以 [产品共识](research/hackathon_team_brief.md) 为准。

当前可试玩版本为「雨夜打烊」网页交互场景：物品通过点选与动作选择操作，不需要拖拽，状态由规则直接更新，Cassian 通过 Gemini 异步回应，等待期间仍可操作；经历时间线可立即回看。无需游戏引擎或本地 GPU。视频生成当前暂停，为 Sean 的 8 卡训练留出资源。

```bash
cd /mnt/sv0/sean/Ludens
source research/ludens_env.sh
LUDENS_PORT=8792 /mnt/sv0/sean/envs/ludens-joyai/bin/python -m pipeline.ludens_pipeline
```

已有进程运行时无需重复启动。使用与验证见 [交互版记录](research/interactive_tavern_20260922.md)。此前的视频驱动原型保存在 `pipeline/video_demo.py`。

是否需要明确目标，还是自由 Roleplay，保留为团队讨论项。后续声画增强优先复用已有开源模型：Joy 可直出语音，不带语音的模型可配 TTS；连续动作与场景演化重点探索世界模型。这些新能力尚未接入，基础操作仍应持续可用。

## 早期原型记录

> **名字**：Ludens 取自 *Homo Ludens*（《游戏的人》，把"扮演/游戏"视作一种文明媒介的奠基之作），
> 意为"正在 Play 的人"。它刻意跳出"一轮一轮的对话框"——哪怕带多模态，聊天框终究还是聊天框；
> Ludens 让你**真的进到一个 state、一个虚拟世界里去玩**：文本流照常刷，画面随剧情长出来。
> 静帧只是起点，往后是动态转场，再往后是 AR/VR——一个可进入、可玩的世界，而不是一个回答框。

非 Agentic roleplay：文本流照常刷，**画面随剧情变**。aim 单模型同时产出角色台词 + 世界状态，
状态驱动一致场景图（klein 图像编辑环），做成可玩的视觉小说 demo 给同事试。

- **Tier 0（当前）**：状态驱动的一致静帧（klein，~0.3s/帧）—— 可玩/交互层。
- **Tier 1（后续）**：重要转场的动态视频（LTX-2.5 I2V，~2.5min/clip）—— 异步 wow 层，接口已留。

延迟分工：静帧即时可玩，视频离线/异步预渲。

---

## 架构（3 进程，web 不背 torch）

```
浏览器 ──:8765──> demo_server.py   (torch-free)
                    │  裸 /completions（gemma4 五轮型）
                    ▼
                 live-aim  kaonai/kaon-mia-v0   → prose + 世界 state
                    │  POST /render {session_id, state}
                    ▼
                 render_server.py  (torch, cuda:0)  常驻 klein + 每会话 SceneState
                    │  create/edit → PNG 落 out/live/{sid}/
                    ▼
                 demo_server 的 StaticFiles 把图喂回浏览器做背景（同机同盘，不代理）
```

| 文件 | 角色 |
|---|---|
| `demo_server.py` | 零 torch。`Aim` 类=单模型 serving 核心（搬自 davr_mt `serve_demo.py` 单模型路径，判据未改）+ `Scene` 类=render HTTP 客户端 + `CardMaker` 类=自定义卡初始化（init-LLM 主/兜底）+ VN 前端（内联 HTML）+ 会话落盘 |
| `render_server.py` | torch。常驻 `Flux2Renderer`(klein) + 每会话一台 `SceneState`；`POST /render` 决策 create/edit/none → 落盘 → 返回图 URL + caption |
| `scene_state.py` | 纯逻辑：state 快照 → 场景 prompt / 编辑指令 / 运动段落；`SceneState` 状态机（live 与离线共用）；`first_json_object` 括号配平提取器；`normalize` 形状保险 |
| `renderers.py` | `Flux2Renderer`(默认 klein) / `KontextRenderer`(备选) / `MotionRenderer`(LTX I2V) |
| `replay.py` | 离线：读一个 session 的 `state_history.jsonl` → 重渲帧/clip + index.html（Tier 1 LTX 动态也从这里出） |
| `seed_cards.json` | 4 张角色卡（自 davr_mt 拷入，项目自包含；均带 `scene` 视觉短语） |

---

## 跑法

```bash
export AIM_KEY=<key>              # ⚠️ key 只从环境变量读，绝不写进任何文件
PY=/mnt/local/envs/conda_envs/scene_service/bin/python

$PY render_server.py             # cuda:0 常驻 klein，:8781（首次载模型 ~30-60s）
$PY demo_server.py               # 零 torch，:8765；自定义卡的 key 默认从 data_pipeline/.env 加载

# 自定义卡 init-LLM 的 key 从 data_pipeline/.env 自动读入环境（值不落任何新文件）：
#   KAON_STATE_KEY → gemini-3.8-flash（主，默认）      KAON_KEY → deepseek-v4-pro（兜底）
#   不设 KAON_STATE_KEY 就自动降级到 deepseek；换/关这个 .env： --env_file <path> / --env_file ''

# 浏览器打开  http://<本机IP>:8765  ，选预设角色 或 用「自定义」框输入 personality+scenario 开玩
```

环境：`/mnt/local/envs/conda_envs/scene_service`（torch + diffusers-from-main + fastapi）。
权重：`/mnt/local/sean/models/FLUX.2-klein-4B`。准备见 `setup.sh`。

### 关键默认值（都在脚本 argparse 里，不靠记忆）

| 项 | 默认 |
|---|---|
| aim base_url | `http://model-test-kaon-mia-v0-yotta2.flow.chat/v1` |
| aim model | `kaonai/kaon-mia-v0` |
| aim key | 环境变量 `AIM_KEY`（`--aim_key_env` 可改） |
| 自定义卡 init-LLM | 主 `google/gemini-3.8-flash`(`KAON_STATE_KEY`) → 兜底 `kaon/deepseek-v4-pro`(`KAON_KEY`)；对齐 `data_pipeline/configs/llm.yaml` |
| init-LLM key 来源 | `--env_file` 默认 `/mnt/local/sean/data_pipeline/.env`（自动读入环境，不落新文件；`''` 关闭） |
| render device / size | `cuda:0` / `1024x1024` |
| block_turns / max_model_len / state_max_chars | 10 / 8192 / 3000 |
| 端口 | demo 8765 / render 8781 |
| 会话落盘 | `sessions/{sid}/`（state.json + state_history.jsonl + transcript.jsonl） |
| 场景图 | `out/live/{sid}/NNNN.png` |

---

## 设计要点

**state 用 aim 原生**（不另做提取器）。`Aim` 类整套搬 `serve_demo.py` 单模型路径，判据一字未改：
- **块跳跃上下文**：`[system] + [call_state+锚 state] + 最近一块轮次`；真人 user 轮渲染为 autoreply。
- **块边界写 state**：token 预算优先坍缩、轮数只作上限；写 state 用受限视图保证请求永远发得出去。
- **clamp 兜底**：state 超预算按 key 占比收缩内容，**绝不删 key**（删 key = 替模型做灾难性遗忘）。
- **state 采样**：`temperature=0.5 + repetition_penalty=1.08`，压长 JSON 的 token 循环。
- **解析失败保留旧 state**（自愈，下个块边界再写）。

在此之上只加了三处轻量保险：
1. `first_json_object`：括号配平提取，替掉贪婪 `{.*}`（fat characters dict 偶发多闭/少闭括号；实测 4/5 vs 贪婪 1/5）。
2. `normalize`：`characters/character` 的 list↔dict、`location` 的 `{current}`↔str 形状归一（存进 history 的仍是模型原生 state，只在下游/校验用归一结果）。
3. 解析出的对象若 location 和 characters 都没有 → 判失败、保留旧 state。

**前端=视觉小说**：渲染图做背景（双层交叉淡入）、prose 原样展示、caption=`location · time` 叠角、
autoreply 三选项 +「附身」输入框 + 世界状态侧栏。

**开场**：session 起手先对 `[system+welcome]` 强制写一份 initial_state → 第一帧立刻出，不用等块边界。

**自定义卡**：start 页除预设角色外留一个输入框，用户填 personality + scenario → `CardMaker` 调 init-LLM
（gemini-3.8-flash 主 / deepseek-v4 兜底，主挂自动降级）**只生成可变三块**（角色正文 / welcome / scene），
护栏 boilerplate（roleplay guideline + Role Override Defense）从预设卡原样复用 → 拼成一张临时卡，
走与预设卡**完全相同**的开场链路（initial_state → 第一帧 → 三选项）。key 只从环境变量读。

**渲染 fail-soft**：render 挂了不打断剧情轮，前端保留上一帧背景。

**会话落盘格式与 `replay.py` 完全一致** → 任何 live session 事后可 `replay.py --animate N` 离线重渲
LTX 动态。Tier 0 → Tier 1 的接口就在这。

```bash
# 离线把某个 live session 的前 3 个转场另渲成 LTX 动态 clip
$PY replay.py --session sessions/<sid> --out out/<sid> --animate 3
```
