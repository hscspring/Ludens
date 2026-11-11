# 三个候选的推理加速调查

2026-09-24。Sean 要求同时调查 MiniMax-H3、LTX-2.5 Distilled、JoyAI-Echo 1.5；三个暂时保留，后续可能按场景混用，也可能继续淘汰。以下为源码／发布资料调查，不是本地加速实测。

## MiniMax-H3

首选 [ModelTC MiniMax-H3 Turbo](https://github.com/ModelTC/Minimax-H3-Turbo)。已经发布 FL2VA 的 8 步和 4 步 LoRA，支持图片条件与音视频输出，另外有 Ref2VA 4 步版本。先测 8 步质量，再比较 4 步；需使用各权重配套的采样日程与 video/audio shift，不能只把原模型步数改小。544p 和 768p 版本分开记录。现有 Diffusers 入口可作为接入调查起点，实际兼容尚未验证。

[FastH3 8-Step V2 模型卡](https://huggingface.co/FastVideo/FastVideo-FastH3-8-Step-V2) 明确只蒸馏了 T2VA，未蒸馏 FL2VA／Ref2VA，所以不作为当前参考图交互场景的直接替代。其动作、细节和部分音频也可能弱于原模型。

[vLLM-Omni 报告](https://vllm-project.github.io/2026/09/01/minimax-h3-production-serving.html) 的约 8.7 秒生成 10.1 秒完整 MP4，来自 8×B300、T2VA、预热后的 FastH3 配置，不代表单张 H100 的图生视频延迟，也不代表流式首帧延迟。常驻、编码、解码与导出优化值得参考。

## LTX-2.5 Distilled

我们已经使用蒸馏模型，不能把“改用蒸馏”重复算作新的加速收益。[官方推理仓库](https://github.com/Lightricks/LTX-2#-optimization-tips) 已提供 Hopper 的 FlashAttention 3 和原生 FP8 scaled-matmul 路线；优先核对当前 Diffusers 入口与官方实现差异，再测试这两项和减少 CPU/GPU 搬运。FP8 存储／转换与真正使用 FP8 矩阵计算需要区分。

[NVIDIA Sol Engine 的 LTX-2.5 报告](https://nvlabs.github.io/Sana/Sol-Engine/LTX25/) 有蒸馏管线加速结果：NVFP4、4K、5 秒视频，单 B200 端到端 1.53×，单 RTX 5090 为 1.90×，主要优化高分辨率第二阶段。对我们的低分辨率 H100 单卡不能直接套用；也不能拿多步管线的 4.68× 当成蒸馏版收益。列为第二阶段研究项，尚未验证完整实现的可复现性。

## JoyAI-Echo 1.5

优先采用 [1.5 官方实现](https://github.com/jd-opensource/JoyAI-Echo/blob/main/echo_longvideo/README.md)，已有 BF16、FP8 scaled-matmul、ModelOpt FP4 权重和配置；仍提供参考图、音视频记忆及原生音视频生成。官方本地服务可在显存允许时保留模型，适合后续测热运行。H100 先比较 BF16 与 FP8，FP4 的硬件／算子支持另验，不承诺收益。

[官方 FP8 配置](https://github.com/jd-opensource/JoyAI-Echo/blob/main/echo_longvideo/configs/inference.fp8.yaml) 保留八次去噪更新以及音频记忆。实测时沿用我们的帧率、输入、片长和记忆条件，不能直接换用配置默认值造成对照失真。低显存 consumer 配置靠逐层搬运换显存，并不等于更快。

[社区 ComfyUI 补丁](https://github.com/jlucasmcrell/joyai-echo-multishot-patch) 报告 RTX 5090 上原生 FP8 计算约 1.5× 端到端收益，同时有常驻块等优化。但涉及旧版封装与混合权重，尚未确认对当前 1.5 兼容；优先级低于官方 FP8，不把该数字当成 H100 保证。

## 接下来的比较口径

先各自测试：MiniMax Turbo 8 步、Joy 官方 FP8、LTX Distilled 的 H100 优化，再视质量测试更激进配置。复用酒馆的同一段“说话 → 操作箱子 → 接着回应”，保持参考图、台词、片长和展示尺寸可比。每个模型保留未加速对照。

记录冷启动、热运行完整响应、生成／播放时长比、峰值显存，并评估中文语音、人物与箱子一致性、动作遵循及连续交接。先筛选各自可用配置；跨模型混用还需单独验证末帧与声音参考能否保持同一角色，不因接口接通就宣称连续性通过。

## 当前低分辨率基线

`out/native_reply_20260924/probe1` 已完成 MiniMax 原生音视频生成。输入是可玩场景的真实操作后参考及真实聊天回复，672×384、124 帧、原生 24 FPS、50 步。指标文件记录 pipeline 321.260 秒、模型脚本 350.175 秒，外层运行日志 370.0 秒，峰值 allocated 63.668 GiB。这是单次冷调用中的 pipeline 计时，不是常驻服务的热运行结果。

该结果说明仅降低分辨率仍不足以支撑快速交互。视频观感和台词遵循尚待验收；新的原生动态回应尚未接入在线可玩页面，现网后续仍是 TTS 与静止人物。调查没有下载新权重或启动额外 GPU 任务。

## 加速评测已接入并启动

Sean 确认超过 50 行的实现结构：沿用 `StoryEvaluation`，增加 `VideoInference` 持有生成模型并连续调用，沿用现有轻量视频导出。六个配置分别在独立进程中运行三轮，各自承接实际末帧；首轮加载单列，第二、三轮不重新实例化生成模型。Joy 仍按官方接口重新准备条件、加载条件编码器，因此不宣称所有组件均已常驻。

183 / GPU 6 后来被占用，未在其上启动新任务。Sean 改指定 183 / GPU 3，检查为空后启动 `scripts/run_acceleration.sh`。顺序：Joy FP8、Joy BF16、MiniMax Turbo 8、MiniMax BF16、LTX Distilled FP8、LTX Distilled BF16。运行输出 `out/acceleration_20260924/`。每个配置启动前检查指定卡，占用则退出 75；任一推理失败则停止批次，不静默换模型。

MiniMax 下载了 1,383,677,768 字节的 FL2VA Turbo 8-step v1.0 BF16 LoRA；此版本训练分辨率为 544p，alpha 8、video/audio shift 12/3。采样传入 9 个 sigma grid points，执行 8 次去噪；原版保留原先 50 grid points / 49 次。LoRA 使用上游校验及融合函数，源码与许可证保存在本轮 `upstream/`。

Joy 官方 FP8 权重已有，不重复下载。LTX 先使用 TorchAO 0.18.0 动态 FP8 权重及激活量化，记录实际量化模块数；没有安装或启用 FlashAttention 3，不能将结果标为 FA3 加速。PEFT 0.21.0、TorchAO 安装在本轮独立依赖目录，不改线上服务环境。

共同目标 672×384、原生 24 FPS；MiniMax 124 帧，LTX/Joy 121 帧。仍输出 640×352 / 16 FPS 的轻量播放副本。三轮输入和预期台词复用旧故事；本轮不增加 Joy 音频记忆槽，以免与原对照改变两种条件。后续跨模型声音连续性仍需另测。

已验证：核心测试检查模型只实例化一次、三轮参考确实使用上轮解码末帧，以及仅首轮计入加载开销；Python 语法和 shell 语法检查通过。MiniMax LoRA 和 TorchAO 依赖可导入，CPU 小矩阵确认 FP8 权重转换与 CPU 存放可行，不能代替实际 GPU 算子验收。浏览器读取六组结果和对照页面无应用错误，80 端口资源 HTTP 200。

评测导航新增“三模型加速 · 质量与等待时间”，入口 `/static/acceleration-20260924/index.html`。启动时 Joy FP8 尚在权重加载，未宣称任何新加速视频已通过生成或质量评测。现网可玩页面的后续 TTS／静止人物问题仍待完成原生音视频接入。

### Joy FP8 首组结果

三轮已生成，日志确认 `full_prequant_e4m3_scaled_mm`，1344 个量化模块，missing=0、unexpected=0。首次加载 400.478 秒；首轮回应另需 92.535 秒（含条件编码 49.776 秒）。后两轮完整回应分别 33.496、29.085 秒，对应约 5.04 秒视频。首轮去噪 5.578 秒、第二轮去噪 5.439 秒；去噪之外的条件处理、模型搬运和导出仍占显著开销。回应阶段峰值 allocated 22.503 GiB，未计独立初始化峰值。此时尚无同尺寸 BF16 结果，不能据此宣称 FP8 的加速倍数。

助手检查搬箱轮实际末帧：双手仍扶箱，没有完成要求的松手；不能标为动作遵循通过。尚未完成语音听感、逐字台词或整段动作的人工评测。后续批次继续执行 Joy BF16 和其余四个配置。

### 本机分担剩余评测

Sean 授权本机也可运行。检查本机 doams-187：GPU 0 被占用，GPU 1–7 空闲。此时 183 已完成 Joy 两组和 MiniMax 两组，正在生成 LTX FP8。将尚未开始的 LTX BF16 指定到 doams-187 / GPU 1，保留相同输入与推理配置。

`StoryEvaluation` 按故事配置核对目标主机；183 后续读到已分给本机的 LTX BF16 时正常跳过，不加载模型，也不修改本机结果。确认远端已读到新配置及跳过逻辑后启动本机任务。单独使用 `run_local.log`，避免旧队列重定向覆盖活动日志；远端已有任务未终止。

启动命令：`CUDA_VISIBLE_DEVICES=1 LUDENS_CACHE_TAG=187_gpu1 LUDENS_LOG_NAME=run_local.log bash scripts/run_acceleration.sh ltx_bf16`。网页增加节点／GPU 列。LTX 两组现在跨节点，耗时只能作为各自部署表现，不直接归因于 FP8；纯量化加速倍数需同机对照。MiniMax 已有两组完整结果，第二／三轮原版为 196.383／205.858 秒，Turbo 8 步为 169.620／192.211 秒，整条回应链路收益明显小于步数减少比例，未宣称实时。

### 六组生成完成

18 段均已生成，六条完整三轮视频也已发布。实际回应耗时（秒，不含单列的首次模型初始化）：

| 配置 | 第一轮 | 第二轮 | 第三轮 | 节点 |
| --- | ---: | ---: | ---: | --- |
| Joy BF16 | 103.08 | 48.83 | 54.54 | 183 / 3 |
| Joy FP8 | 92.53 | 33.50 | 29.08 | 183 / 3 |
| MiniMax 原版 | 257.76 | 196.38 | 205.86 | 183 / 3 |
| MiniMax Turbo 8 | 255.79 | 169.62 | 192.21 | 183 / 3 |
| LTX Distilled BF16 | 134.88 | 61.48 | 50.00 | 本机 187 / 1 |
| LTX Distilled FP8 | 83.18 | 34.71 | 28.91 | 183 / 3 |

这是一轮固定故事样本，后续画面由各自输出承接，尚无重复统计。Joy 有明显端到端时间下降，MiniMax 的端到端收益较小。LTX 跨节点，不能把表中差异直接称为 FP8 加速倍数。所有质量结论仍待人工验收。

验证：18 条播放副本及 6 条整段故事全部完整解码，音轨可解码、非零采样；HTTP 文件长度与本地一致。检查记录 `out/acceleration_20260924/media_validation.json`。GPU 187 / 1 和 183 / 3 在结束检查时均为 0 MiB、0% 利用率，所有任务自然结束，没有终止进程。

远端旧 wrapper 完成 LTX FP8 并按新主机配置跳过 LTX BF16 后，日志出现 shell 尾部解析错误；该 wrapper 运行期间改写了脚本，属于本次运行管理问题。六组模型结果不依赖该尾部，均已单独核实完成；本机 wrapper 正常退出 0。后续不在执行中的 shell 文件上改写内容，使用独立启动脚本版本。

### Sean 本轮反馈（版本待确认）

原文记录：

- MiniMax：“整体可以，第二段声音稍不一样”
- Joy 1.5：“整体其实不错，问题是第二段把箱子搬起来往外走了一下又放回去了”
- LTX：“整体可以，第二段箱子转了一圈”

已询问这三条对应加速版、BF16 原版还是两者综合；确认前不挂到某个具体配置，也不据此宣称量化或蒸馏质量已通过。结构化原文保存为评测页 `reviews.json`，不覆盖此前 Sean 或钦语的评价。

助手判断：三者整体观感均获正面反馈，暂不因本轮直接淘汰。MiniMax 需继续验证音色一致性；Joy 与 LTX 的主要问题是物品交互动作偏离预期。视频中的抬箱／转箱不能自动视为符合状态里的沿桌面平移；动作遵循与画面自然分别评价。后续优先用相同起终位置、明确的小幅平移和松手要求测试接触动作；声音参考／记忆条件另作对照，不能混入本轮纯加速结论。
