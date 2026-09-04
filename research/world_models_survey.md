# 世界模型调研:面向回合制交互式叙事角色扮演的可玩底座

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

> 以下来自早期 web 搜索合成,arXiv 号/仓库名/HF 权重**均未经实拉验证**。若为真,它们比 A 段更贴"叙事驱动 + 反幻灯片";
> 若为假(编造),则忽略。**核实优先级见文末 TODO。** 保留在此是为了不丢线索,不是为了背书。

### B1. 叙事驱动 + 反幻灯片机制(若为真,架构最契合)

| 模型 | 控制面 | 声称亮点 | 待核实 |
|---|---|---|---|
| **DreamX-World-5B**(高德 AMAP) | 文本事件 5 级 + 相机 | 5B/Apache、beat-pace、**几何位置记忆**(无角色身份锚,重入画漂脸) | ⚠️2606.16993 · github AMAP-ML/DreamX-World · hf GD-ML/DreamX-World-5B |
| **Incantation**(SJTU+HKU+NV) | **逐帧 0.25s 逐角色 NL** | 19.7FPS/480p、2h rollout、语义跨角色迁移;**无权重(仅数据集)** | ⚠️2605.18601 |
| **H3-World**(腾讯+NUS) | 键位→组合文本指令绑时间区间 | LoRA 65.6M/Apache 开;**底座 MiniMax-H3 33B**(单卡 80G 边缘) | ⚠️2609.01560 · github Danzer1xxxxChan/H3-World · **=memory 里的模板** |
| **JoyAI-Echo-1.5**(京东) | 每 shot 文本+跨 shot 记忆库 | 基于 LTX-2.3,非商用可用,**视觉+声音身份跨 shot**;OFFLINE | ⚠️2608.23383 · github jd-opensource/JoyAI-Echo |

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
