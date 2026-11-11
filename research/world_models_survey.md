# 世界模型调研:面向回合制交互式叙事角色扮演的可玩底座

> **2026-09-22 更新：** 当前产品已转向即时点选交互与异步角色反馈，以下“每轮等视频”的早期假设不再作为实现依据。最新模型复核见 [固定微场景调研更新](world_models_update_20260922.md)：LingBot 1.3B 已发布；SolarWM-H3 有新阶段权重；本地 Echo-WM Flash 尚需补测。历史 FPS 与一致性结论不可当作当前酒馆实测。

> 记录 2026-09-04。融合四路调研:①开源可跑(证据级实查) ②前沿闭源对标 ③叙事文本驱动 ④分类校准。
>
> **⚠️ 可信度分层(本文最重要的一件事):**
> - **A 段「已核实」** = 基于真实键盘/文本输入 loop 的证据判定,核心模型为截止前(≤2026-01)已知真实项目
>   或经 web 实查。**可信,可据此动手。**
> - **B 段「待核实」** = 早期 web 搜索合成,含大量 2026 arXiv 号 / 仓库名,**有被编造的风险,押注前必须逐条实拉**。
> - 教训:helixworld.org 官网"可交互"是营销话术,实为预渲染视频循环。**"README/demo 页看着能玩" ≠ "代码能玩"。**

## 背景与定位

Ludens 图片壳 demo(`demo-image-shell` 分支)被判"顶多算玩具":每帧独立重 roll,
**人物变脸、世界不连续**——本质是"叙事幻灯片"。pivot 目标是换一个**能跨拍锁住身份/状态**
的可玩底座。方向在 Unity(工程重)与世界模型(研究赌注)之间,用户倾向世界模型。

## 硬约束(用户 2026-09-03/04 定,含 09-04 更正)

1. **不商业化** —— 内部黑客松,非商用许可(CC BY-NC-SA / 学术)全部可用。
2. **必须有交互 action(硬需求,09-04 更正)** —— 可玩 = 有 action 闭环。**action 形式不限于 WASD**:
   叙事动作、WASD 移动、点选、或其组合都算;**WASD 类模型不因"是 WASD"被排除**——它们本就是现成的交互底座,
   缺的是叙事层(可叠加)。不需要自由漫游,但**不能没有交互**——纯 CANNED、纯离线批渲不可注入的出局。
3. **回合制 OK** —— 不需要电影级实时逐帧;"你写一句 beat / 做一个 action → 世界渲一段"的节奏可接受。
4. **不能幻灯片** —— **决定性质量线**:必须**跨拍锁住角色身份 + 世界状态**。图片壳的病根,筛选第一标准。

## 分类框架(实时性)

| 档 | 含义 |
|---|---|
| **LIVE** | 真实时输入 loop,live 输入 → 下一帧即时生成。证据:可玩链接或 `play.py` 式脚本。 |
| **beat-pace LIVE** | 增量:一条文本事件/action → 生成一个 chunk,几秒一段。**回合制角色扮演甜区。** |
| **OFFLINE** | 预设完整动作/prompt → 批渲出 MP4,过程中不可注入。做 demo 视频可以,不可玩。 |
| **CANNED** | 官网只有预渲染 demo 视频,无可下权重,无从自建。 |
| **CLOSED LIVE** | 真实时可交互,但仅云端,无法自建。 |

**决策轴:** 有交互 action(硬) × 开放可跑(单卡 H100) × 实时档 × **身份/状态跨拍一致(反幻灯片)**。

## 核心结论(经 09-04 更正后重排)

1. **WASD 一放开,格局全变:** 出现了**已核实、开源、单卡 H100、真 LIVE** 的干净交集 ——
   **Matrix-Game 2.0**(MIT、25FPS 单卡实测、任意图当起始世界)是当下最强可落地 LIVE 底座;
   **DIAMOND**(MIT、单卡秒跑、~10FPS)是轻量确定能跑的备选。**这条路比 B 段那套 2026 叙事栈稳得多。**
2. 这两者的短板是**只有键鼠、无叙事控制** → 需一层 **LLM→action 桥**(叙事 beat 翻成 WASD/动作),
   或用 **LingBot-World 2.0** 的"文本事件 + WASD"路子(但公开版要 8 卡)。
3. **反幻灯片(跨拍一致)在已核实模型里已有解:** Matrix-Game 3.0 的 **>1 分钟记忆 + 相机感知检索防空间漂移**、
   LingBot 的 1 小时零退化;注意这些是**世界/空间一致**,不等于人脸身份一致——但第一人称/图内世界里
   人脸漂移远比图片壳(第三人称角色立绘)轻。
4. 若坚持**纯自由叙事 NL 控制**:开源里只有 **Open-Pandora**(纯文本动作、任意域),代价是非实时
   (round-trip,每 clip 几秒)——适合脚本化叙事 demo,不适合 live play。

---

## 陆续新增:用户持续投喂的新模型(2026-09-07 起,滚动追加)

> Sean 会陆续甩来新发布的世界模型链接,这里逐个按同一把尺子(**LIVE × 叙事驱动 × 跨拍锁身份 × 开放可跑**)
> 记一笔并给"**记录 / 试**"判定。绝大多数是"记录备查"——真正过三难初筛的才升进上面的核实流程。新条目往表里追加即可。

| 模型 | 记录日 | 档 | 控制输入 | 跨拍身份 | 叙事 / 语音 | 开放 / 许可 | 对 Ludens 判定 |
|---|---|---|---|---|---|---|---|
| **SolarWM** | 09-07 | **LIVE**(长时长,分钟/小时级 rollout) | 相机轨迹 + 文本 | ❌ | ❌ / ❌ | 代码 Apache-2.0;权重 HF(部分底座 LTX-2.5 / MiniMax-H3 社区许可,地域+商用受限) | **记录**:未来"世界连续性层"真候选(真·实时长时长),但无身份/叙事/唇形,非角色叙事模型 |
| **Puffin-World** | 09-07 | **OFFLINE**(交互仅轨道浏览预建点云) | 文本 + 相机位姿 + 初始图 | ❌(演示全空房间,无人) | ❌ / ❌ | 代码 + HF 模型 + 数据集有链接,**许可未标** | **记录(仅备查)**:环境/几何类,离 Ludens 比 SolarWM 更远 |
| **MiniMax-H3**(本体,官方) | 09-11 | **OFFLINE**(4–15s clip 出片,非 live) | 文/图/视频/音频多模态参考(Ref2VA ≤9图+≤3视频+≤3音频)、首尾帧(FL2VA) | ✅**强**(多参考图钉外形 + video-to-video 可续接) | ✅原生视频+32k立体声+语音,**11 语种含中文** | 权重开(HF,508万下载/likes 全 org 第一);**minimax-h3 社区许可**(商用审);2K 需闭源 Context-IR+Regenerate-2K API | **记录+重点盯**:当前最强开源 OMNI 出片底座;本机 H100×4 跑得动 H3-Base(768p);比 JoyAI-Echo 更强的参考锁身份 + 原生音频 + 多语种。**非 live,是高质量 clip 出片** |

- **SolarWM**(junchao-cs.github.io/SolarWM-Web;arXiv/HF 见项目页,未二次核对 ID):开放**长时长实时**视频世界模型,
  5s clip 训练 → 分钟/小时级 rollout。4 个 backbone 5B–33B(Wan2.2 / LTX-2.5 / MiniMax-H3),含蒸馏 "Wan-5B Causal Student (4 steps)";
  数据集 1.43M clips / 25TB。控制**只有相机轨迹 + 文本**,无身份锚 / 叙事 / 唇形;**FPS / 显存均未公布**。
  **定位:跨拍世界连续性层的真候选(值得盯),但落不到角色叙事主线。**
- **Puffin-World**(kangliao929.github.io/projects/puffin-world):**离线**;把重力/地平线/稠密深度当"原生世界状态",
  相机控制**物理接地**;一模型统一感知 + 自由视角仿真 + 重建。架构=几何对齐视觉编码器 + LLM + 扩散 + 轻连接器
  (参数量/底座/显存未标);数据 Puffin-16M(15M vision-language-camera triplets + 1M 相机轨迹)。演示全是空室内场景,
  **无人物/对话/语音**。**定位:相机自洽的空场景/环境生成器,与角色叙事无关,仅备查。**

### MiniMax-H3(本体 · 2026-09-11 亲自核实:HF API + README + tree size)

- 页/仓:`hf.co/MiniMaxAI/MiniMax-H3` · `github.com/MiniMax-AI/MiniMax-H3` · `hailuoai.video`。**≠ H3-World / SolarWM**——那俩是拿 H3 当底座的第三方世界模型;这里是**官方通用 omni 视频生成本体**(别混)。
- 定性:`image-text-to-video` 的 omni 生成系统,吃 文/图/视频/音频 混合,出**自带 32kHz 立体声的视频**;4–15s / 24FPS / 短边 768p(2K 需 Regenerate)。稳定 11 语种对话(**含中文**)。
- 规模(实测 tree,全仓 **498.5GB** = FL2VA+Ref2VA+顶层+ref 四套叠一起;单任务族 **~150GB**):核心 **H3-Omni-Transformer = 33B dense single-stream**(~66GB/套 BF16),**text encoder = Qwen3-VL-32B**(取第 50 层,~68GB/套),video_vae 10.4GB + vae 15GB。
- 三模块:**H3-Context-IR**(自由多模态输入→结构化 Context Intermediate Representation,**闭源**,要调官方 API 或按 prompting guidance 自建)+ **H3-Base**(开源,出 768p)+ **H3-Regenerate-2K**(768p+原始上下文→升 2K,靠 API)。原生支持稀疏注意力,但**首个开源版只放 full-attention 推理**。
- 部署:官方推荐 **SGLang / vLLM,`--num-gpus 4`**;有 vllm recipes + sglang cookbook。BF16。
- 许可:`minimax-h3-community-license`(社区版,商用/公开须审条款);内容有官方审核护栏。
- 对 Ludens(三难):**锁身份 ✅✅**(Ref2VA ≤9 参考图,比 JoyAI-Echo memory_slots 更强)· **首帧→视频 ✅**(FL2VA 首帧模式,正好接我们"离线开场图当 condition_img 首帧")· **原生音视频 + 11 语种 ✅✅**(中文可能救回来)· **跨拍连续 ?**(有 video-to-video,可拿上一 clip 尾续下一 clip,待验)· **LIVE ❌**(clip 出片非实时交互流,区别于 Matrix-Game-2.0)。
- **本机可行性(H100 80G×8 已确认)**:H3-Base 单族 ~150GB / 官方 4 卡(4×80=320GB)本机富余,3 卡(240GB)也够。门槛=①下载(单族 ~150GB / 全量 498GB,**大规模下载须 Sean 授权**);②2K 靠闭源 API,本地到 768p;③license 商用审。**定位:OFFLINE 高质量出片底座头号候选,值得实跑 smoke。**

---

## 核实结果(2026-09-04 逐条实拉,`verify_sources.sh` + README 实读)

### 第 1 层:存在性 —— **全部真实,无一编造(推翻我原来的"高编造风险"担忧)**

`verify_sources.sh` 对 30 项 curl GitHub/HF/arXiv API,**A 段 + B 段全部返回 EXISTS**,且是差异化真实元数据
(DreamX 765 星、SlotMem 13 星、JoyAI-Echo 2002 星 / HF 62750 次下载、H3-World 2026-09-03 仍在推)。
**负控**(故意编造的假 ID/假仓库)全部正确返回 404/401,真实对照(1706.03762)返回 200 → 核实逻辑可信。
所以 B 段那批 2026 项目**真实存在**,搜索 agent 没编造仓库名。但存在 ≠ 可玩,继续第 2 层。

### 第 2 层:frontrunner 深度核实(README 实读,纠正了 agent 合成的若干说法)

| 模型 | 核实结论 | 相对原判 |
|---|---|---|
| **Matrix-Game 2.0** | ✅**站住**:`inference_streaming.py` 是真交互流式脚本(vs batch `inference.py`);**25fps 实时**、键鼠输入;**单卡 ≥24GB,A100/H100 tested、不需多卡**;传**任意图**当起始世界;**MIT**。底座 SkyReels-V2(参数量未标)。**无叙事/文本控制**(证实需 LLM→action 桥)。**跨帧记忆 2.0 未提**(>1min 记忆是 3.0 的特性)。 | 维持首选 |
| **DreamX-World-5B** | ✅**升级(B→已核实)**:**MIT**(原记 Apache 有误,09-05 纠正);权重已发(HF GD-ML/DreamX-World-5B/-5B-Cam,需另下 Wan2.2-5B-TI2V 底座);**单卡装得下**(1×H20 峰值 38/40/72G,80G 够);**NL 事件 + 相机驱动**;**几何记忆检索** + 训练"缓解 identity/背景/风格/颜色漂移"(比原判"无身份锚"强,但named-character 脸锁未明说)。**但非实时**:5s@720P 要 26s、60s 要 342s → **慢速批渲,正好回合制,不是 live**。 | 上调:比预期可信 |
| **H3-World** | ⚠️**降级**:底座 MiniMax-H3 **33B / ~135GB,单卡 80G 装不下**(默认 4 卡);`infer.py` **批渲** 5.2s、无实时 loop;控制是**移动预设**(still/forward/strafe/pan→latent 语言指令),`--scene-prompt` 静态,**自由叙事直驱"未说明"** → 实为**移动世界模型,非叙事驱动**;**无 LICENSE 文件**;LoRA 权重已发(hf DANNY621/H3-World step-10000.safetensors,65.6M)。 | 下调:比 memory 预期弱 |
| **JoyAI-Echo-1.5** | ✅**黑马 + 纠错**:实为**两个项目**——**Echo-WM**(交互世界模型!LTX-2.3 底、`echo_wm/inference_wm.py` Gradio demo、导航→6-DoF 相机、**视频+环境音+音乐+语音齐生**)+ **Echo-LongVideo**(10+min 多镜批渲)。**反幻灯片机制全场最强**:"composable cross-shot memory" 跨镜聚合视觉证据 + speaker cue,**同锁角色外形与嗓音身份**;**唯一带语音**。权重已发(HF,62750 下载)。许可=**LTX-2 Community License**(学术/非商用,够用)。**未知:显存/FPS 全无数**(FP8/TensorRT 是 roadmap 非现货)、Director Agent 接口未述。 | 上调:从"纯 OFFLINE"改判,含交互 WM 分支 |

### 剩余待核实(下一步,按需)

Matrix-Game 参数量/3.0 单卡实时 · **JoyAI-Echo 显存/FPS**(README/arXiv 均未标,需查 HF 或子目录 README)· Incantation 权重是否真未发 ·
身份适配器(SlotMem/Memento/IAMFlow)实测集成难度 · LingBot 1.3B 单卡变体是否发布 · **LLM→action 桥可行性**(Matrix-Game action 格式能否被 LLM 稳定翻译)。

### 第 3 层:本地权重深核(2026-09-05,5 个模型已下载,读 README/推理脚本源码/config/LICENSE)

**已下载**(`/mnt/local/sean/models/`,共 ~300GiB,脚本 `research/download_models.sh` 断点续传):
Matrix-Game-2.0 27G · DreamX-World-5B 20G · Wan2.2-TI2V-5B 32G(DreamX 底座) · Echo-WM 89G · JoyAI-Echo 133G。零 incomplete,文件数全对。

| 模型 | 档位 | 单卡推理峰值 | 单卡 80G | 控制面 | 许可 | 反幻灯片 | FPS |
|---|---|---|---|---|---|---|---|
| **Matrix-Game-2.0** | **LIVE**(`inference_streaming.py` 真流式) | ~11G(蒸馏6.1+CLIP4.5+VAE0.5) | 轻松 | WASD+鼠标,**无 NL 叙事** | **MIT** | 帧级自回归 ObjConsist 0.64;**无跨拍 ID bank** | **25** |
| **DreamX-World-5B** | **OFFLINE**(action_seq 预写死,中途不可注入) | ~34G(+Wan 底座 T5/VAE) | 可 | 相机键序预设+场景文本 | **MIT**(纠正) | KV cache+PRoPE 空间记忆;**无 character ID 锁** | 16 |
| Wan2.2-TI2V-5B | OFFLINE | 32.5G | 轻松 | 仅文本/图 | Apache 2.0 | 无 | 24 |
| **Echo-WM** | beat-pace(Flash)/OFFLINE(Base) | **69G**(45G ckpt + Gemma-3-12B 24G) | 紧(贴顶,需 offload) | DSL 相机序列 + **6 场文本(含 Character/Speech)** | LTX-2 Community(学术非商用) | 单 clip 内 Consist **89.8**(榜一);无跨拍 ID bank | **未知** |
| **JoyAI-Echo** | **OFFLINE 纯批渲** | FP8 52G / BF16 69G(+Gemma-3-12B) | FP8 可 | 文本 + **7-slot memory**;Director Agent(LLM 编剧) | LTX-2 Community | **全场最强**:cross-modal memory 同锁**外形+嗓音**跨镜 | **未知** |

**悬案关闭:** Matrix-Game=**1.8B**(config 确认);DreamX 许可=**MIT**(原记 Apache 有误);Echo-WM/JoyAI 显存已估(见表)。
**悬案仍开:** Echo-WM / JoyAI **FPS README 均无数**,只能跑 benchmark 或读 arXiv 才知。
**两个下载缺口(2026-09-05 已补齐):** ①推理代码已 clone 到 `/mnt/local/sean/wm_repos/`(`Matrix-Game` / `DreamX-World` / `JoyAI-Echo`,后者含 `echo_wm` 交互分支 + `echo_longvideo` 批渲分支;脚本 `research/download` 无涉,clone 命令见 memory)。②两个 gemma-3 文字编码器已下(`download_text_encoders.sh`):`gemma-3-12b-it`(JoyAI LongVideo 用)+ `gemma-3-12b-it-qat-q4_0-unquantized`(Echo-WM 用),各 23G,落 `models/`;token=EvilYam@kaonai 有 gated 访问权。**至此代码+权重+文字编码器全齐,任一模型只差 GPU + Sean 发话即可 smoke。** 已知运行入口:Echo-WM=`echo_wm/run_gradio.sh` / `gradio_echo_wm.py` / `inference_wm.py`+`configs/inference_wm_causal.yaml`;JoyAI=`echo_longvideo/inference.py --config configs/inference.bf16.yaml`;Matrix-Game=`inference_streaming.py`(LIVE)/`inference.py`(批渲);DreamX=`inference_ar_forcing.sh/.py`。

**核后重排「三难」(可玩=LIVE交互 × 叙事驱动 × 跨拍锁身份 —— 单个下载模型无全解):**
- **LIVE 真交互**:只有 Matrix-Game-2.0(键鼠实时,但无叙事、无跨拍 ID)。
- **跨拍锁身份(外形+嗓音)**:只有 JoyAI-Echo 有显式机制(但纯 OFFLINE,须叠交互层)。
- **beat-pace + 角色/语音文本条件**:Echo-WM 最接近叙事 RP(Consist 榜一),但动作仍预写死、69G 紧、FPS 未知、非商用。
- DreamX 深核后**降级**(OFFLINE + 无 ID 锁),方案二核心地位动摇。

---

## A 段:已核实开源可跑(证据级,✅=截止前真实 / 🔶=web 实查)

### A1. LIVE + 单卡 H100 —— 最可落地

| 模型 | 域 | 控制 | 档 | 单卡 H100 FPS | 参数/许可 | 一致性 | 核实 |
|---|---|---|---|---|---|---|---|
| **Matrix-Game 2.0**<br>Skywork | 通用(传任意图进去玩) | WASD+鼠标 | **LIVE** | **25FPS 实测** | 1.8B / **MIT** | 分钟级;上移偶发黑帧 | 🔶2025-08,机器之心实测 |
| **DIAMOND (CS:GO)**<br>Geneva/MSR | CS:GO Dust2(+Atari) | 键鼠 `play.py` | **LIVE** | ~10FPS(3090 实测,H100 更快) | 381M / **MIT** | 物理幻觉(穿墙)、域锁 | ✅NeurIPS2024 |
| **Matrix-Game 3.0**<br>Skywork | 第一人称(UE+真实) | WASD+鼠标 `--interactive` | LIVE | 40FPS@720p 需 8 卡;单卡实时未证 | 5B / ? | **>1min 记忆+相机检索防漂移** | 🔶2026-03,2604.08995 |

### A2. LIVE + 带文本事件 —— 叙事最好,但要多卡

| 模型 | 控制 | 档 | 许可 | 一致性 | 核实 |
|---|---|---|---|---|---|
| **LingBot-World 2.0**<br>Robbyant/蚂蚁 | **WASD + 文本事件**("起暴风雪""城→林""召唤龙")+ Pilot/Director Agent | LIVE(公开版 480p 8 卡 torchrun) | 14B / **CC BY-NC-SA(非商用,可用)** | 1 小时零退化;无超上下文长记忆 | 🔶2026-07 |

> LingBot 1.3B 单卡变体"承诺但未确认发布"——**待核实**;若真发布,它是"单卡+文本事件+LIVE"的孤例最优解。

### A3. OFFLINE(批渲,不可 live play,可做叙事 demo 视频)

| 模型 | 控制 | 许可 | 备注 | 核实 |
|---|---|---|---|---|
| **Open-Pandora**<br>maitrix/OpenSparseLLMs | **纯 NL 动作**("红车左转"),任意域,Gradio 每轮 ~2s 视频 | 权重开 | 开源里 **NL 控制最灵活**;round-trip 非实时 | ✅2024 |
| **Hunyuan-GameCraft 1.0**<br>腾讯 | `--action-list` 预设键序批渲 | 未确认宽松 | ~30B,画质最强(1M+ AAA 录像);单卡慢(FP8+offload) | ✅2025-08,2506.17201 |
| **Oasis-500M**<br>Decart/Etched | 开源版仅批渲→MP4(live 版在云端不可自建) | **MIT** | 500M 单卡轻;转身场景重置 | ✅2024-11 |
| **NVIDIA Cosmos 1.0/2.5** | 文本→视频(非游戏控制) | **NVIDIA OML(可商用)** | 2B~14B 均装得下(14B~57G);228s/720p clip | ✅2025-01 |

### A4. 闭源/未开(仅对标,不可自建)

| 模型 | 档 | 说明 | 核实 |
|---|---|---|---|
| **Hunyuan-GameCraft 2**(腾讯) | CLOSED LIVE | 全场最强 NL 接口("开门""触发爆炸")+键鼠,16FPS@480p,**无权重** | 🔶2025-11,2511.23429 |
| **Mirage / Mirage 2**(Dynamics Lab) | CLOSED LIVE | WASD+会话内文本改世界("下雨""切冬天"),~16FPS 云端,**无权重** | 🔶2025-07/08,多家实测 |
| **Genie 2/3**(DeepMind) | CANNED | 均不开源;Genie3 仅限美区 AI Ultra | ✅Genie2 2024-12 |
| **GameNGen**(Google) | CANNED | 无权重无码,仅 demo | ✅2024-08 |
| **Yan**(腾讯) | CANNED | 仅 paper+页面,12–17FPS@单 H20 主张,无权重 | 🔶2025-08,2508.08601 |
| **GameGen-X**(HKUST) | CANNED | "code coming soon",仅数据集 | ✅2024-11 |

### 已排除(既非交互又不符)

- 纯 OFFLINE 批渲无 mid-gen 注入 + 无叙事:**Vista(驾驶)/ PlayerOne(动捕输入)** —— 域/输入不适配角色扮演。
- (WASD-only 类**不再排除** —— 09-04 更正后 action 允许 WASD,它们回到 A1/A2 当交互底座。)

---

## B 段:待核实线索(2026,高编造风险,押注前必须逐条实拉)

> **存在性已核实(2026-09-04):以下 arXiv/仓库/权重全部真实存在**(见上方"核实结果")——早期"高编造风险"担忧已推翻。
> 但**能否可跑/是否 LIVE/单卡装得下,仍需逐条深读**。其中 **DreamX-World 已深核 → 升级为已核实(见"核实结果")**;
> **H3-World 已深核 → 降级(33B/135G 多卡、移动预设非叙事)**。其余仍待深读。

### B1. 叙事驱动 + 反幻灯片机制(若为真,架构最契合)

| 模型 | 控制面 | 声称亮点 | 待核实 |
|---|---|---|---|
| **DreamX-World-5B**(高德 AMAP) | 文本事件 5 级 + 相机 | 5B/Apache、beat-pace、**几何位置记忆**(无角色身份锚,重入画漂脸) | ⚠️2606.16993 · github AMAP-ML/DreamX-World · hf GD-ML/DreamX-World-5B |
| **Incantation**(SJTU+HKU+NV) | **逐帧 0.25s 逐角色 NL** | 19.7FPS/480p、2h rollout、语义跨角色迁移;**无权重(仅数据集)** | ⚠️2605.18601 |
| **H3-World**(腾讯+NUS) | 键位→组合文本指令绑时间区间 | LoRA 65.6M/Apache 开;**底座 MiniMax-H3 33B**(单卡 80G 边缘) | ⚠️2609.01560 · github Danzer1xxxxChan/H3-World · **=memory 里的模板** |
| **JoyAI-Echo-1.5**(京东)**→已深核,见"核实结果"** | Echo-WM 导航/相机 + Echo-LongVideo 多镜文本 | LTX-2.3 底,LTX-2 Community 非商用,**同锁外形+嗓音**;**含交互 WM 分支(非纯 OFFLINE)** | ✅2608.23383 · github jd-opensource/JoyAI-Echo |

### B2. 身份适配器(补"锁脸",挂 Wan2.1/2.2 底座)

SlotMem(2607.15772,每角色 slot)· Memento(hf ernie-research/Memento,双查询)· StoryMem(hf Kevin-thu/StoryMem)·
IAMFlow(github Eddie0521/IAMFlow,**免训练**最易集成)· IP-Adapter-WAN(github kaaskoek232/IPAdapterWAN)。**全待核实。**

### B3. 文本状态大脑(纯文本,追档案/规则,决定下一 beat)

EvolvingWorld(2607.17250,Character Agent+World LLM 共演化,hidden tracker 证据门控)· AdaMARP(ACL2026,显式 Scene Manager)。**待核实。**

---

## 两条 pivot 路线

- **路线 A —— LLM 当导演,上游驱动现成世界模型底座**("brain+cerebellum")。黑客松内可落地。
- **路线 B —— 重绑 conditioning,让叙事文本本身成为原生动作空间**(LoRA,memory 里 H3-World 模板)。更原创更重,研究赌注。

## 落地栈

### 方案一(已核实,推荐先搭):LIVE 世界模型 + LLM→action 桥

```
角色扮演 LLM(出叙事 beat)
      │  ← LLM→action 桥:beat 翻成 WASD/动作序列(+ 可选文本事件)
      ▼
Matrix-Game 2.0(MIT,单卡 25FPS,任意图起始世界)  ← 真 LIVE,已核实可跑
      │  或 DIAMOND(轻量确定能跑,域锁 CS:GO)
      │  或 LingBot-World 2.0(文本事件+WASD,但 8 卡)
      ▼
可玩交互世界(跨拍空间一致靠 MG3.0 记忆/LingBot 长稳)
```
起始世界一致性种子:用文生图/StoryDiffusion 出一张定妆世界图 → 传进 Matrix-Game 当 world init。

### 方案二(叙事更纯,依赖 B 段核实):DreamX-World-5B + 身份适配器

```
角色扮演 LLM → EvolvingWorld 式文本状态大脑 → DreamX-World-5B(文本事件+位置记忆,beat-pace)
                                              + SlotMem/Memento/IAMFlow(补角色身份锚)
```
**前提:B 段这些 2026 项目先核实为真且可跑。** 否则退回方案一。

---

## 核实 TODO(下一步)

**A 段开放可跑轴基本已核实**(证据级 + 截止前真实)。剩余核实集中在 **B 段** 与两处关键可行性:

1. **B 段存在性批量核实(最高优先,先滤编造):** DreamX-World / Incantation / H3-World / JoyAI-Echo /
   SlotMem / Memento / StoryMem / IAMFlow / EvolvingWorld / LingBot 1.3B 变体 ——
   逐条 curl GitHub API + HF API + arXiv,分出"真实存在"与"疑似编造"。
2. **对存活者:** 许可文本 → HF 有无 safetensors 及大小 → 单卡 H100 80G 是否装得下 → 代码里有无真推理 loop(LIVE/beat-pace)还是只有 demo(CANNED)。
3. **可行性验证(方案一):** LLM→action 桥的可行度 —— Matrix-Game 的 action 空间格式、能否被 LLM 稳定翻译。
4. **单卡确认:** Matrix-Game 3.0 / LingBot 单卡实时到底行不行(公开数字都是多卡)。

**核实次序:** B 段存在性批量筛 → DreamX(方案二核心) → 身份适配器(SlotMem/IAMFlow) → H3-World(+MiniMax-H3 底座可得性) → JoyAI-Echo → EvolvingWorld → LingBot 1.3B。

## 关键 URL

**已核实(A 段):**
- Matrix-Game 2.0: hf.co/Skywork/Matrix-Game-2.0 · github.com/SkyworkAI/Matrix-Game (MIT)
- Matrix-Game 3.0: hf.co/Skywork/Matrix-Game-3.0 · arXiv 2604.08995
- DIAMOND: github.com/eloialonso/diamond (csgo 分支, MIT)
- Oasis: hf.co/Etched/oasis-500m · github.com/etched-ai/open-oasis (MIT)
- Hunyuan-GameCraft 1.0: hf.co/tencent/Hunyuan-GameCraft-1.0 · arXiv 2506.17201
- Open-Pandora: github.com/OpenSparseLLMs/Open-Pandora
- Cosmos: hf.co/collections/nvidia/cosmos · github.com/NVIDIA/Cosmos (Apache)
- LingBot-World 2.0: hf.co/robbyant/lingbot-world-v2-14b-causal-fast-diffusers (CC BY-NC-SA)

**待核实(B 段,不保证真实):**
- DreamX 2606.16993 · Incantation 2605.18601 · H3-World 2609.01560 · JoyAI-Echo 2608.23383
- SlotMem 2607.15772 · Memento hf ernie-research/Memento · IAMFlow github Eddie0521/IAMFlow · EvolvingWorld 2607.17250
