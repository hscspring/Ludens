# 固定微场景中的人物与环境：模型调研更新

日期：2026-09-22。基于官方仓库、论文及模型卡重新核实；社区优化单独标注。调研阶段未下载权重、启动推理或占用 GPU。随后经 Sean 指定，在 180 / GPU 1 完成了 [人物效果测试](character_test_180_20260922.md)，下文调研判断需结合该结果阅读。性能数字均为发布方报告，不是本机实测；生成吞吐也不等于用户输入到第一帧的延迟。

## 场景理解与当前建议

Sean 提出的“大场景一般不切换，里面的人物动”适合作为当前产品方案：固定一个空间与主要视角，人物说话、转头或行动，物品及局部环境随互动变化。这是本项目的范围选择，并非世界模型只能这样工作。

场景固定不意味着只有人物能动：桶的位置、毛巾干湿、水迹、门窗与光线都可能改变。物品继续点选后选择动作，不增加拖拽。画面必须与最新状态一致。

换到新地点时，可以准备或生成新场景图作为起始画面；不必每次实时生成。已设计的地点可提前制作，即将进入的地点可按已知条件提前准备，临时出现的地点再按需生成。返回酒馆时应恢复此前状态，不能把账册和桶重置。角色外观、随身物品与已发生事件要跨场景保留。

场景图只解决外观。新场景仍需定义或验证可点击对象、位置、可执行动作及遮挡；生成一张漂亮图片不等于自动获得可玩场景。若未来要求从酒馆连续走到街上，还需要连贯过渡或可探索空间的方案，不是简单切换首帧就能完成。

建议先区分三个具体问题：人物说话和表情；人物触碰、搬动物品；换地点及空间移动。它们需要的控制能力不同，不强求一个模型同时解决。

## 本轮最值得关注的结果

### 1. Echo-WM Flash Preview：先补测已有资产

官方提供 4 步自回归版本，输入首帧、文本与 Action DSL，联合输出视频和音频；长时版本与在线流式 demo 仍列为后续发布。没有据此确认可中途自由修改角色行为，也没有本场景实时性证据。[官方说明](https://github.com/jd-opensource/JoyAI-Echo/blob/main/echo_wm/README_CAUSAL.md)。

本地已存在 `/mnt/sv0/sean/models/Echo-WM/echo-wm-flash.safetensors`，且 `/mnt/sv0/sean/wm_repos/JoyAI-Echo/echo_wm/` 已有对应代码。原 `research/smoke_echowm.sh` 明确使用 `echo-wm-base.safetensors`；因此此前约 10.5 分钟的 Base 样例不能直接当作 Flash 耗时。

判断：按“先用咱们已有模型”的顺序，优先补测固定镜头、Cassian 小幅反应和短中文对白。4 步不等于端到端延迟必然降低到可交互程度，动作 DSL 的导航控制也不等于能精确搬账册。它不是本月新发现的发布，而是现有资产中尚未充分验证的一条路径。

### 2. LingBot-World 2.0 1.3B：9 月的新发布改变了旧结论

官方 9 月 10 日宣布发布 1.3B causal-fast，已提供模型卡。官方快速启动仍给出 1.3B 四卡、14B 八卡示例，并明确不发布自身部署代码；不能直接套用整套系统的高帧率宣传。[官方仓库](https://github.com/robbyant/lingbot-world-v2)、[1.3B 模型卡](https://huggingface.co/robbyant/lingbot-world-v2-1.3b-causal-fast)。

独立开发者的实现报告：9 月 17 日，单 RTX 5090，约 16.1 FPS、每 16 帧块约 0.98 秒；提供键盘和鼠标交互。该数据是社区作者自己的测试，优化包含针对 5090 的内核，不能直接推算到本机 H100。[社区实现与测试条件](https://github.com/kaarelkaarelson/lingbot-world-v2-realtime)。

判断：值得列为新世界模型候选，尤其用于后续视角和空间变化。尚未证明能保持 Cassian 身份、按自由文本准确操作指定物品，也不能把系列整体的文本事件能力自动归给每个 1.3B 部署。原文“1.3B 未确认发布”已过期。

### 3. SoulX-FlashHead：固定场景人物说话的轻量候选

不是本月新品，是本轮针对新需求补查的模型。1.3B，已有 Lite/Pro 权重与流式 Gradio；官方报告 Lite 在单 RTX 4090 达到 96 FPS，Pro 单 4090 为 10.8 FPS。这些是不同质量配置，不能混为一谈。[官方仓库](https://github.com/Soul-AILab/SoulX-FlashHead)、[权重](https://huggingface.co/Soul-AILab/SoulX-FlashHead-1_3B)。

判断：参考角色图与语音驱动的说话、表情适合做小范围候选，语音由已有音频或 TTS 提供。它主要是头部肖像生成，不能据此承诺全身行动、搬桶或递物。若接入酒馆，需要验证角色在画面中的尺寸、头身衔接与遮罩；不默认能生成透明人物层。

### 4. SolarWM-H3：9 月 13 日新增流式训练阶段与权重

官方更新发布 H3 的 Stage0.5、Stage1、Stage2 代码与权重，推进相机条件下的少步自回归生成。当前示例仍是多卡推理命令，不能仅凭“streaming”认定用户可以实时追加任意角色动作。[官方仓库](https://github.com/Junchao-cs/SolarWM)。

判断：是有实质更新的世界模型研究方向，但当前更贴近相机与空间连续性。还没有本酒馆中物品交互、人物身份和对白控制的验证；暂不排在已有 Echo Flash 与人物反馈之前。本地 MiniMax-H3 基础模型目录存在，不代表已经具备 SolarWM-H3 的派生权重。

## 其他复核项

| 模型 | 已核实情况 | 对当前项目的判断 |
|---|---|---|
| Hallo-Live | 已有代码与权重，文本驱动联合声画；官方报告双 H200 上 20.38 FPS、0.94 秒延迟 | 可研究原生声画路线；H100 表现待测，精确角色图条件下的速度也不能直接套用 |
| LiveAvatar | 已有权重和推理；音频、参考图及可选提示驱动人物；官方实时 TPP 路径使用五卡，单卡另有离线入口 | 人物动作候选，但“能单卡运行”不能解读为“单卡实时” |
| OmniForcing | 已有因果推理代码，论文报告流式联合声画；本轮 README 中未找到明确的因果生成器权重下载链接 | 暂记研究候选，先核对权重可获得性，不算即刻可跑 |
| Omni-LiveAvatar | 8 月论文研究分钟级联合声画；官方仓库明确代码与 checkpoint 尚未发布 | 暂不列入可部署候选 |
| LTX-2.5 / MiniMax-H3 | 官方均提供音视频推理；本地已有相关资产 | 继续作为已有通用声画底座，不能因原生音频或少步推理就认定为交互世界模型 |

来源：[Hallo-Live](https://github.com/fudan-generative-vision/Hallo-Live)、[Hallo 权重](https://huggingface.co/fudan-generative-ai/Hallo-Live/tree/main)、[LiveAvatar](https://github.com/Alibaba-Quark/LiveAvatar)、[OmniForcing](https://github.com/OmniForcing/OmniForcing)、[Omni-LiveAvatar 发布状态](https://github.com/Aoko955/Omni-LiveAvatar)、[LTX 官方](https://github.com/Lightricks/LTX-2)、[MiniMax H3 官方](https://github.com/MiniMax-AI/MiniMax-H3)。

Hallo-Live 的当前推理入口另有明确限制：I2V 分支不支持其 parallel VAE decode 选项。这进一步说明，用角色参考图接入时不能照搬 T2V 加速配置。[推理源码](https://github.com/fudan-generative-vision/Hallo-Live/blob/main/inference.py)。

## 对 Ludens 的取舍

优先复用已有 Echo-WM Flash，明确它在固定镜头人物反馈上的质量与实际等待。若核心瓶颈仍是让 Cassian 及时说话、有表情，SoulX-FlashHead + TTS 可作为专项对照，但不应把整个玩法缩成头像聊天。LingBot 1.3B 留作真正的连续世界实验，SolarWM-H3 暂列研究储备。

在固定酒馆里，先让生成的人物反馈与可点击物品共存，再尝试人物与物品接触。保持基础操作即时生效；避免生成一整帧旧世界覆盖玩家刚做出的变化。一般视频输出不会自动提供物品 ID、碰撞或透明前景，素材分层与状态同步仍是应用侧需要实测解决的部分。

最小后续验证可使用同一酒馆画面：Cassian 短句回应并转头；玩家在回应期间移动桶；观察视频是否篡改桶的位置、角色身份或中文台词，同时分别记录首次可见反馈和整段耗时。此处仅记录候选与验证问题，尚未实施或启动模型。
