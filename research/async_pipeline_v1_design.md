# 异步流水线 v1 设计 —— 在线·自动单故事

日期:2026-09-06
定位:把 aim→运镜→JoyAI 闭环([[ludens_pipeline_closedloop_report_20260906]])串成**边生成边播、连播不卡**的常驻 demo。v1 不做玩家交互,自动推进一个故事。

## 目标与验收

浏览器打开 → 一个故事的**视频背景连续播放** + 剧情文本流,镜头(clip)一个接一个**无缝续播**,JoyAI 的 39s/片延迟被"超前生成 + 缓冲"藏进播放时间里。
- 播放节奏由**片长 9.64s/shot** 主导(视频是背景,一段播完切下一段 + 换该 shot 的剧情文本)。
- 验收:开播前先囤够 buffer;之后连播**不出现"等生成"的黑屏/卡顿**;字幕正确;剧情文本随镜头推进。

## 进程拓扑(单进程,简化版)

joyai-echo / scene_service 两个 env 都齐 `fastapi/uvicorn/jinja2/av/pillow/requests`
→ **单进程,joyai-echo env**(有 torch),同时跑:JoyAI engine + FastAPI web/SSE + 字幕(av)+ StoryFeed(LLM via requests)。**无需跨进程 HTTP**(旧 demo 的 web↔render_server 拆分在这里不再需要)。

- **JoyAI worker**:N 个后台线程,每线程持有一个**常驻** `InferenceEngine`(`load_generator()` 一次)绑一张卡,阻塞跑 `run_request` → 多卡真并行。
- **队列**:`request_q`(StoryFeed→worker)、`ready_q`(worker→播放),线程安全。
- **FastAPI**:web + SSE 直接在本进程。

JoyAI 侧几乎零改动(已核实 `inference.py`):`InferenceEngine.__init__ → prepare_conditions → load_generator → 循环 run_request`,engine 天然可复用;`run_request` 自带 `stage_callback("inferring"/"decoding"/"writing")` 可做进度反馈。

## 三组件 + 编排器(谁持有谁)

1. **StoryFeed**(`pipeline/story_feed.py`)——持有 `aim_directors`(RosterExtractor/ContentDirector/CameraDirector)+ `ShotRenderer`。自动往前推剧情,持续把下一 shot 的 (剧情文本 + R2V request) 塞进 `request_q`,永远领先视频侧。
2. **ClipFactory**(`pipeline/clip_factory.py`)——持有 N 个常驻 JoyAI engine(worker pool)+ `SubtitleBurner`。从 `request_q` 取 → `run_request` 出片 → 烧字幕 → 塞 `ready_q`;维持超前缓冲深度 K。
3. **播放层**(在 `pipeline/ludens_pipeline.py` 内,复用 `demo_server` 前端)——背景 `<div bg>` 换 `<video>`,连续播放 `ready_q` 的 clip(交叉淡入无缝切);SSE 吐"剧情文本 + 下一片 clip url"。
4. **LudensPipeline**(`pipeline/ludens_pipeline.py`)——编排器,持上述三者 + 两个队列 + FastAPI app;`main()` 只实例化 + 启动。

**复用(不重写)**:`aim_directors.py` / `shot_renderer.py` / `llm_client.py` / `subtitle_film.py`(SubtitleBurner)/ `demo_server.py` 的 HTML 前端骨架。

## 吞吐算术(流不流畅的命门)

| | 值 |
|---|---|
| JoyAI 单卡 | 39s/片(denoise ~34.6 + decode ~4.3) |
| 片长 | 9.64s → 单卡 4× 实时,**单卡跟不上** |
| 4 卡并行 | ≈ 39/4 ≈ **9.75s/片 ≈ 片长** → 勉强跟上,先囤 2 片再开播兜抖动 |
| 量化后(FP8/tensorrt) | 单片 ~15–20s → 吞吐翻倍,彻底宽松(后续) |

结论:v1 用 **4 张空卡 + buffer** 就能流畅;量化留作后续加速。

## 里程碑(每步可独立验证)

- **M1**(核心风险,**需空卡**):ClipFactory 常驻 worker pool —— load 一次 / 多片复用 / 多卡并行 / 出片+字幕,量真实吞吐(4 卡是否 ≈9.75s/片、常驻显存是否稳)。
- **M2**(纯 LLM,**不吃 GPU**):StoryFeed 自动推 N shot 产 request,验证生成侧永远领先。
- **M3**(编排):LudensPipeline + buffer,连播不断流(可先用**假 clip**占位验证队列/缓冲/切片逻辑,不吃 GPU)。
- **M4**(web):video 背景 + SSE 连播,浏览器端验证无缝切 + 字幕 + 文本流。

先写顺序建议:**M2 →(假 clip 版)M3/M4 → M1**。前三块不吃 GPU,能立即 smoke;M1 真 worker 代码同期写好,等空卡再 smoke。

## 当前阻塞:GPU

2026-09-06:8×H100 全部显存 78–79G 占满、util 5–8%(idle 占卡),**无整张空卡**。常驻 worker 每 engine 需 ~80G/卡 → M1 暂无法 smoke。
- 不阻塞写码;先推进 M2/M3/M4(不吃 GPU)。
- 需 Sean 定夺:等卡释放,还是协调腾出 4 张给 Ludens。
