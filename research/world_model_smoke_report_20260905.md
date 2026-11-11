# Ludens 世界模型 Smoke 实测 + 语音验证报告

- **日期**:2026-09-05
- **目的**:体验优先——先验证世界模型的**沉浸效果本身**(视觉连续性、跨镜头身份/世界状态一致 = 反"幻灯片"),以及**台词内容能否被正确承载**(模型自带语音 / 字幕)。为 Ludens 可玩 demo 选型 + 定架构。
- **硬件**:GPU7 串行 smoke(GPU0-3 为训练占用,勿动)。

---

## 1. 结论速览(TL;DR)

- 三个世界模型**全部 smoke 成功**,产物 mp4 已落盘、已抽帧肉眼判读。
- **JoyAI-Echo**:黑白电影质感、写实人脸、**跨 shot 身份一致、叙事最强**;且**自带语音内容 100% 正确**(ASR 逐字验证)。→ **选为渲染层主力**。
- **Echo-WM**:奇幻手绘、有角色、**WASD 可交互**、跨帧身份锁、世界一致。→ 交互原型候选。
- **DreamX-World**:写实海岸、**相机运动连续性极佳**,但此 case 无人物。→ 空镜/运镜候选。
- 三者均为**离线 batch 生成(非实时)**;真 live(25FPS)的 Matrix-Game2.0 未在本轮。

---

## 2. 测试环境(一模型一独立 env)

| 模型 | env | torch / py | 关键依赖 | 在线/离线 | 范式 |
|---|---|---|---|---|---|
| DreamX-World-5B | `/mnt/local/envs/conda_envs/dreamx-world` | 2.5.1/cu124, 3.10 | tv 0.20.1, **av 降到 13.1.0** | 离线 | AR 分块相机-forcing 视频生成(base Wan2.2-TI2V-5B) |
| Echo-WM | `/mnt/local/envs/conda_envs/echo-wm` | 2.9.1/cu128, 3.11 | av≥14 原生 API | 离线(可交互) | I2V 世界模型,文本(6 字段含 Sounds/Speech)+ WASD action |
| JoyAI-Echo | `/mnt/local/envs/conda_envs/joyai-echo` | 2.8.0/cu128, 3.11 | **tv 0.23.0 + av 16.1.0** | 离线 | 长视频 + 跨模态记忆(≤7 槽)锁跨镜身份/嗓音 |

**av 关键结论**:torchvision **0.23.0** + av 16.1.0 的 `write_video` **正常**(CPU 探针 `write_video OK, size 792718`);只有 DreamX 的**旧** torchvision 0.20.1 有 `pict_type="NONE"` bug 才需把 av 降到 13.1.0。JoyAI/Echo-WM 无需改 av,且 `ltx-pipelines/media_io.py` 用 av≥14 原生 `av.open`,av 不能降。

---

## 3. Smoke 结果对比

| 维度 | DreamX-World | Echo-WM | JoyAI-Echo |
|---|---|---|---|
| 画风 | 写实海岸 photoreal | 奇幻手绘 painterly | 黑白电影 film noir,写实人脸 |
| 人物 | 无(此 case) | 有(探险者:背包/法杖/斗篷) | 有(Nathan Vale) |
| 跨帧/跨镜身份 | — | **锁定**(跨帧一致) | **锁定**(跨 shot 一致) |
| 世界一致性 | 相机运动连续性极佳 | 一致 | 一致 |
| 交互 | 相机轨迹 | **WASD 动作驱动** | 无(离线长视频) |
| 叙事 | 弱(纯运镜) | 中 | **最强** |
| 自带语音 | 无 | prompt 可含 Sounds/Speech(未验) | **有,内容已验正确** |
| 屏幕文字 | — | — | 有乱码(prompt 已要求"无字幕"仍出) |
| 生成耗时(smoke) | ~7 步 <10s | 30 步 ×~21s ≈ 10.5 min | 单 shot 数分钟 |

### 产物 mp4 路径
- DreamX:`/mnt/local/sean/Ludens/research/smoke_out/dreamx/0_demo_36_Tilt_Down.mp4`
- Echo-WM:`/mnt/local/sean/Ludens/research/smoke_out/echowm/0010/result.mp4`
- JoyAI:`/mnt/local/sean/Ludens/research/smoke_out/joyai/memory-agent-last-visa-0802-en/shot_001/inference_20260905_034904/result.mp4`
  - 音频单独:同目录 `result.wav`(未 mux 进 mp4,因无系统 ffmpeg);`result_silent.mp4` 为无音轨视觉判读版。

---

## 4. 语音内容验证(JoyAI)

- 工具:`faster-whisper` 1.2.1(装在 joyai-echo env,CPU int8,`base.en`);内部用 av 解码,不依赖系统 ffmpeg。
- 结果(一字不差):

```
ASR 转录 result.wav → In San Cordoba, every table orders coffee and asks for a border.
原台词(request)     → In San Cordoba, every table orders coffee and asks for a border.
detected_lang en | duration 9.64s
```

- **结论**:JoyAI 自己生成的语音**念的就是我们给的台词,内容准确** → 语音从"可选"升为"可用加分项"。
- **环境事实(避免重踩)**:无系统 ffmpeg;`result.wav` 为 IEEE-float 格式(python `wave` 模块读不了 `unknown format: 3`,用 av / faster-whisper / soundfile 可读)。

---

## 5. Ludens 架构映射(本次实测确立)

roleplay 本质是**轮次文本对话,信息主要在文本里**。据此定三层,**文本流是唯一事实源,画面/字幕/语音全从它派生**,从根上避免"画面与故事不一致":

| 层 | 角色 | 产出方 |
|---|---|---|
| **主干:文本流** | 每轮 **autoreply 出台词 + 下一步 action**(剧情走向、镜头/人物动作) | davr_mt agency 核心 ←**信息主体** |
| 渲染层:世界模型 | 把每轮文本变成**连续画面**(锁跨镜身份/世界状态 = 反幻灯片) | JoyAI(叙事)/ Echo-WM(交互) |
| 呈现层 | 台词 → **字幕(必做,内容永对)** + 语音(JoyAI 自带,已验证可用) | 直接取文本流的台词 |

---

## 6. 下一步:最小闭环(方向已定 2026-09-05)

1. **文本流 LLM**:主 `gemini38_flash_state`(`google/gemini-3.8-flash`),兜底 `deepseek_v4`(`kaon/deepseek-v4-pro`);**复用 data_pipeline `llm.py`,不手写**。
2. 逐 shot 拼 prompt(参考 `the_last_visa` request 结构:人物外形 ID 锁定 + 台词 + lip-sync + voice + 镜头 + 无字幕要求)→ JoyAI 逐镜生成 → **字幕烧录(必做)**。
3. **后续**:专门针对视频模型训练一个 **aim**,场景换成**我们自家的 bot**(不再用 the_last_visa 英文示例)。

### 端点配置固化(llm.yaml)
```yaml
gemini38_flash_state:            # 文本流主力
  model: google/gemini-3.8-flash
  api_base: https://kaon-router.kaonai.com/v1
  api_key_env: KAON_STATE_KEY
  max_tokens: 16384; temperature: 0.0; reasoning_effort: low

deepseek_v4:                     # 兜底
  model: kaon/deepseek-v4-pro
  api_base: http://staging-kaon-router.flow.chat/v1
  api_key_env: KAON_KEY
  enable_thinking: false; max_tokens: 16384
```
