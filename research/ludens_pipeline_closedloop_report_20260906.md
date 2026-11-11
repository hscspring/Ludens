# Ludens 可玩 Demo — 内容→运镜→视频 闭环里程碑

日期:2026-09-06
产物样片:`research/out/ludens_denji_film.mp4`(Denji 卡,3 镜,28.98s,带字幕带音频)

## 一句话结论

三模型串行链路(aim 内容 → 运镜 → JoyAI 视频)已端到端跑通,并在链路末端补上字幕烧录 + 拼片。**最大的未知——"不给任何图/音锚点,纯 prompt 能不能出连贯带音频的视频"——已验证成立**,demo 的可玩雏形成立。

## 链路

```
seed card (Denji)
   │
   ├─ RosterExtractor   跨镜常量(角色外形/嗓音,一次性)         ┐
   ├─ ContentDirector   每 shot 多 role 内容                    │ aim 侧,纯 LLM,快
   │     state 轮 = 场景规格 / assistant 轮 = 分角色 beats       │
   └─ CameraDirector    每 shot 运镜决策                        ┘
   │
   ▼
ShotRenderer   确定性胶水(非模型):多 role + 运镜 → 一条 R2V payload
   │           (name→ID_x 跨镜稳定累积;assets 空→纯 prompt 弱锁)
   ▼
JoyAI-Echo     R2V → 视频(单卡/片,多片独立可多卡并行)
   │
   ├─ SubtitleBurner   逐帧烧 `Who: line` 字幕(shot 内按 beat 均分时间)
   └─ FilmStitcher     规格一致 → stream-copy 首尾相接(不重编码)
   ▼
整片样片 ludens_denji_film.mp4
```

各段脚本(全部已固化):
- `smoke_aim.py` → `aim_directors.py`(RosterExtractor / ContentDirector / CameraDirector)+ `llm_client.py`
- `smoke_shot_render.py` → `shot_renderer.py`
- `research/run_joyai_shots.sh`(多卡 round-robin 出片)
- `subtitle_film.py`(SubtitleBurner + FilmStitcher)

## 关键验证结论

1. **纯 prompt 弱锁成立(最大未知已解)。** 三条 R2V 请求全部 `memory_slots=[]` + `condition_img=null`,无任何定妆图/参考音,JoyAI 依然出了合法、带音轨的视频。跨镜身份靠 prompt 里的 `ID_x + 外形/嗓音` 文字锁维持。
   - 局限:文字锁**不保证跨镜像素级同一张脸/同一身形**。像素级锁定是后续"强锁"(每角色 canonical 图/音 → memory_slots 强锚)的活,已 defer 为优化项。ShotRenderer 已预留 assets 表,填了就自动升级成强锚,无需改结构。

2. **三片结构全部有效。** 1280×736 / 241 帧 / 25fps / 1 音轨 / 9.64s。

3. **字幕 + 拼片保真。** 整片 717 帧(3×239,首尾各丢 1 个 `dts=None` 包,-0.08s/片,无感)、28.98s、音轨保真。

## 真实耗时(BF16 smoke 权重,单卡/片)

| 阶段 | 耗时 | 备注 |
|---|---|---|
| JoyAI 出片 | denoise ~34.6s + decode ~4.3s ≈ **39s/片** | 片长 9.64s → ~4× 实时 |
| 三片并行(GPU 0/1/7) | 总 ~**40s** | 三片独立,一卡一片 |
| 字幕烧录 | **~5.2s / 239 帧** | 纯 CPU,PyAV + Pillow |
| 拼片 | **0.1s** | stream-copy,不重编码不掉画质 |

JoyAI 的 39s 是当前唯一大头:BF16 smoke 配置,未上量化。FP8 / tensorrt 量化可再压;剩余延迟靠工程(转场、异步流水线)藏。

## 字幕方案

- 底部居中 `Who: line`,白字 + 黑描边 + 半透明黑底条(DejaVuSans-Bold)。
- **时间轴是 shot 内按 beat 均分的近似**:JoyAI 生成的音频没有逐行时间码,拿不到"这句从第几秒到第几秒",只能按 beat 数均分。精确对齐需 JoyAI 吐 per-line timestamp 或事后 ASR 强对齐——后续优化。
- 音频原样 remux(不重编码),视频逐帧重编码(libx264/crf18)。

## 环境

- `joyai-echo`(`/mnt/local/envs/conda_envs/joyai-echo`):JoyAI 出片 + 字幕(av 16.1.0 + Pillow,PyAV 自带 libav,系统无需 ffmpeg)。
- `scene_service`:directors / renderer(torch-free,纯 LLM + CPU)。
- GPU:0-3 是 Sean 训练区,4-7 授权 Ludens;本次 Sean 显式授权 0/1/7。

## 下一步

**异步流水线**(优先):把 39s/片 的延迟藏进播放里,让单故事 demo 跑流畅——aim/运镜提前 buffer,JoyAI 多卡流式出片,首片出来即可播,后续无缝续上。先只用 Denji 这一个故事跑通流畅度。
其后:转场(消硬切)、强锁(定妆锚点)、JoyAI 量化(FP8/tensorrt)。
