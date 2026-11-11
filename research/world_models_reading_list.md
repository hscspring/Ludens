# 世界模型 学习 / 精读清单(面向 Ludens)

> 与 `world_models_survey.md` 分工:survey 管"选型 / 能不能落地 / 三难初筛(LIVE×叙事×锁身份×开放)";
> 本文管"系统学习、精读 paper"。Sean 持续投喂的参考资料在此登记 + 标注待读 paper。
> **去重原则:已在 survey 记过或已在用的模型本体不重复展开,只登记新出现的 paper 与新机制。**

## 待读 paper(按优先级)

| 优先级 | Paper | arXiv | 一句话 | 为何要读(对 Ludens) |
|---|---|---|---|---|
| ★★★ | **PTD · Parametric Trajectory Distillation** | [2610.11498](https://arxiv.org/abs/2610.11498) | MiniMax-H3 的 4／6 步 LoRA 蒸馏，保持原生声画生成 | 现有 H3 Turbo 8 步路线的后续对照候选；截至 2026-10-14，官方代码与权重均标为 Coming soon |
| ★★★ | **WorldCast** | 2610.12412 | 共享人物状态与场景记忆，分布式生成多人视角 | 优先读状态约束与场景记忆机制；当前 CS2 权重不能直接替代通用 Roleplay 视频模型，见下方初读 |
| ★★★ | **ReWorld** | 2608.23565 | 实时交互 + 长程记忆世界模型 | landmark bank 固定 KV 预算的长程记忆 + control/memory 路由头解耦 + 4-step 蒸馏实时——正击我们"反幻灯片 / 跨拍连续 / 离开再回来"痛点 |
| ★★★ | **EchoWM(Echo 1.5 = 在用的 JoyAI-Echo)** | 2608.23189 | 可进入式生成媒体世界模型,视频+环境音+语音联合 | 我们出片底座的本尊论文;1.5 能力已扩到 camera-intent 6-DoF + 长程多轮;读它=吃透在用工具的机制与边界 |
| ★★★ | **MiniMax-H3**(本体,很爆) | 待查(model card 未直接给号) | 开源 omni 视频生成大模型,33B Omni-Transformer + Qwen3-VL-32B encoder,联合出视频+立体声+语音 | 出片底座头号候选;读它吃透 Context-IR(自由多模态→中间表示)+ Omni-Transformer 单流联合音视频生成的机制 |

> 号差备注:survey B 段曾把 JoyAI-Echo 记为 arXiv 2608.23383,与官方页 EchoWM = **2608.23189** 不一致,**以官方页为准**。

---

## 条目详述

### ReWorld — "the world remembers"(2026-09-09 投喂)

- 页:`zhifeichen097.github.io/ReWorld` · paper arXiv **2608.23565**(**仅 paper + BibTeX,无 code / weights / demo 源**)
- 机构:HKUST(GZ) & 阿里 ATH。Zhifei Chen\* / Luozhou Wang\* 等(\* equal)。
- 机制要点:
  - **window-split 训练**:control 在短窗学、memory 在长窗学,per-step 头路由决定哪些注意力头看远处过去——control 与 memory 不再抢同一段上下文窗口。
  - **bounded memory**:odometer(里程)准入的 landmark bank + 按相机位姿检索,固定 KV 预算 → 任意长轨迹显存**常数**。
  - **实时**:多源轨迹对齐到统一 metric scale + 4-step 蒸馏 → 实时流式 **704×1280**。
  - **metric-scale 动作**:同一按键恒定覆盖相同米数(远景"几乎不动"、近景"飞驰而过"),内化了真实尺度。
  - 能力:键盘 live 输入驱动一 / 三人称;**离开再回来场景不变**(start⇌return);**单帧分钟级 rollout**(示例 30s / 64s);多场景(奇幻 / 科幻 / 水下 / 微缩 / 写实),含传送门 / 叙事式推进。
- **对 Ludens**:长程连续性层的强候选**思路**。我们最大痛点是"幻灯片 / 跨拍不连续 / 回不到原场景",landmark 记忆 + 常数显存正是这条线的机制答案。**无 code / weights → 短期不能直接跑,先读 paper 学机制。**

### EchoWM / Echo 1.5(= 在用的 JoyAI-Echo,2026-09-09 投喂 paper)

- 页:`echo-team-joy-future-academy-jd.github.io/Echo-1.5-Page/wm` · paper arXiv **2608.23189** · code `github.com/jd-opensource/JoyAI-Echo`(**=我们在用的**) · weights 页面未给
- 机构:HKUST / PKU / JD Future Academy / HKU / THU / USTC / FDU / Beihang / Stanford 等;project lead Zeyue Xue,corr Anyi Rao / Nan Duan。含 EchoWM 与 EchoWM-Flash 两档。
- 机制要点:
  - **camera-intent 统一接口**:一 / 三人称统一成 metric-scale 相对 **6-DoF** 轨迹,数据集级标定运动幅度,无需 per-view 控制器。
  - **视听联合原生生成**:720p 视频 + 环境音 + 音乐 + 语音一起生成(非后挂配音)。
  - 数据引擎 + 渐进训练 + 自回归后训练做长程。
  - 输入:参考图 + 结构化场景描述(文本) + 相机意图控制信号。
  - benchmark:WBench 导航 158 例 **81.7** 均分(交互 87.2)领先(Flash 81.0);user study 对 LingBot 46.5% / 对 HappyOyster 63.13%。
- **对 Ludens**:这是我们出片底座的**本尊论文**,必读——吃透 camera-intent / memory_slots / 视听联合的机制与边界,才能把 R2V 的 prompt / 锚定 / 长程用到位。**模型本体不重复记入 survey A 段(已在用)。**

### MiniMax-H3(本体 · 2026-09-11 投喂,很爆)

- 页/仓:`hf.co/MiniMaxAI/MiniMax-H3` · `github.com/MiniMax-AI/MiniMax-H3` · `hailuoai.video`。arXiv / tech report **待查**(model card 未直接给号)。
- 一句话:官方通用 **omni 视频生成**(`image-text-to-video`),33B Omni-Transformer + Qwen3-VL-32B encoder,联合出 视频 + 32k 立体声 + 语音;4–15s / 768p(2K 需 Regenerate)。
- 精读焦点:①**H3-Context-IR** 怎么把自由多模态输入序列化成结构化中间表示(闭源,但 prompting guidance 可学思路)——正是我们"文本流 → 视频条件"最缺的一环;②Omni-Transformer 单流联合建模 video+audio latent 的 packing / RoPE / 稀疏注意力;③FL2VA / Ref2VA 参考锁身份机制 vs JoyAI-Echo memory。
- **落地细节(规模/显存/部署/许可/本机可行性)全在 `world_models_survey.md` 滚动区详条**,此处只列精读点,不重复。关联 [[project-ludens-playable-pivot]]。

---

## 后续投喂追加区

> Sean 陆续甩来新的世界模型 / paper 链接,新条目往这里追加;过三难初筛的才升进 survey 的核实流程。

### PTD：Parametric Trajectory Distillation for Few-Step Video Generation（2026-10-14，登记）

- 来源：[论文](https://arxiv.org/abs/2610.11498)、[作者项目页](https://alan-lanfeng.github.io/PTD/)。Sean提供，核对摘要与项目页，尚未全文精读或部署。
- 与H3的关系：基于33B MiniMax-H3训练LoRA，支持4／6步声画生成；同一LoRA展示了文本、图像、首尾帧和参考图条件。属于少步蒸馏，不是把H3缩成更小参数量的模型。方法也在Wan2.1-14B上验证。
- 方法概要：用多项式参数化教师轨迹片段，在学生预测路径上获得教师监督；曲率头只用于训练，推理保留原骨干架构。作者强调动态自然度与多样性，效果仍需在本项目场景复验。
- **开放状态：截至2026-10-14，项目页明确标注Code Coming soon、Weights Coming soon。当前不可直接下载部署。**
- 对Ludens：记为现有MiniMax-H3 FL2VA Turbo 8步的后续对照候选，开放后再比较画质、台词、人物／物品一致性与端到端耗时。4／6步不代表相对当前链路按比例加速；本次只登记，不更换模型、不启动测试。

### SceneLM（2026-09-22，初读）

- 论文：[A Scene Language Model for Open-Vocabulary Scene Mapping](https://arxiv.org/html/2609.21400v1)，arXiv:2609.21400。
- 维护对象级文本场景记忆，通过 ADD / EDIT / REMOVE 增量更新；使用 Qwen3-VL 2B/4B 训练，重点包括纠正错误、合并重复和保留正确记录。
- 实际三维建图仍依赖深度和相机位姿；长期动态环境尚待扩展。它是感知与记忆方法，不能替代视频生成底座。
- 对 Ludens 的启发（我们的推断）：以后可从生成画面提取“实际呈现了什么”，与剧情规定的世界事实对照；视觉误生成不能直接覆盖剧情事实。当前先记入学习方向，不新增 Demo 依赖。

### WorldCast（2026-10-10，初读）

- 来源：[项目页](https://ziyang-ye.github.io/WorldCast-Page/)、[论文](https://arxiv.org/html/2610.12412v1)、[官方代码](https://github.com/Ziyang-Ye/WorldCast)、[权重](https://huggingface.co/ZiyangYe/WorldCast)。本次阅读页面、论文与推理文档，未部署实测。
- 机制：每位玩家独立生成视角，交换人物位置等状态和场景记忆；将人物状态投影成相机对齐的条件场，约束人物出现的位置。状态模型从生成画面和控制信号估计位置、深度；场景记忆供后续视角复用。[论文 §3](https://arxiv.org/html/2610.12412v1#S3)
- 效率口径：基于 Wan2.2-TI2V-5B，四步蒸馏，每块约 1 秒、16 帧。论文 H200 测试为每玩家一张卡，2–16 客户端时每客户端约 18.7–23.4 FPS、27 GiB 显存，含解码但不含同步等待。不能等同于端到端交互延迟或 H100 实测速度。[论文 Table 7](https://arxiv.org/html/2610.12412v1#A2.T7)
- 边界：只在 CS2 的训练地图上验证；新地图需要位置数据训练。官网多段演示标明使用给定玩家位置，默认复现实验也使用 GT 状态，预测状态闭环需另行启用。小时级画质稳定不代表剧情、身份和物理状态长期正确；模型也不判定命中、伤害、死亡。[论文 Appendix G](https://arxiv.org/html/2610.12412v1#A7)、[推理说明](https://github.com/Ziyang-Ye/WorldCast/blob/main/docs/inference.md)
- 开放情况（查询日）：代码、模型权重、训练与评估入口已公开，仓库许可 Apache-2.0；README 仍将可部署推理标为 coming soon。现有录制回合复现入口不能直接视为通用在线交互服务。[官方仓库](https://github.com/Ziyang-Ye/WorldCast)
- **对 Ludens 的判断（我们的推断）**：值得精读“状态如何约束画面”和“已有场景如何复用”，尤其对应物品移动后要记住、再次观察仍一致的问题。但没有证明任意角色卡、二次元场景、对话语音或箱子交互可直接泛化。当前继续“交互 + 场景图片 + 按需视频”；保留明确的剧情与物品事实，避免生成画面反过来无条件覆盖事实。暂不替换现有底座。
