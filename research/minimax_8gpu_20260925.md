# MiniMax Turbo 本机八卡延迟验证

Sean 确认用本机八卡测试 MiniMax；LTX 物品交互路线维持暂停。

设备：doams-187，8×H100 80GB，GPU 0–7；启动前检查空闲，全卡 NVLink 互联。

复用已获 Sean 整体认可的复杂三轮场景：挪箱松手 → 指向毛巾 → 转回交流。初始参考图、提示、seed7 与原 MiniMax 实验相同，后续轮次继承真实末帧。生成 672×384、24 FPS、约5秒，网页播放副本 640×352、16 FPS。

拟测配置：vLLM-Omni，DiT TP2×USP4、文本编码 TP8、VAE 并行8；BF16，现有 FL2VA Turbo 8step v1.0 LoRA，scale1、alpha8、视频 shift12、音频 shift3。当前代码接口传 num_inference_steps=8，内部使用9个 sigma 点。官方 recipe 仍写9；首个请求在生成前被校验拒绝，已按代码修正，拒绝请求单独保留。使用 FLASH_ATTN、eager；不以长时间编译作为首次可用结果的前置条件。

原基准为183上的单卡 Diffusers CPU offload：加载123.17秒；三轮回应271.91、146.42、146.77秒。新实验同时改变运行框架、硬件型号及卡数，因此只比较方案端到端表现，不将差异解释成纯8卡扩展比。首次请求与后续请求分开记录，画质仍需独立验收。

状态：隔离缓存版本已完成三轮生成，Sean已认可整体效果，无明显瑕疵。

环境：`/mnt/sv0/sean/envs/ludens-vllm-omni`。
输出：`research/out/minimax_8gpu_20260925/`。
vLLM 0.30.0；vLLM-Omni commit `69de153f6e2db7454021d4966d641e50a96d0212`；PyTorch 2.13.0+cu130。
浅克隆的 setuptools-scm 将 Omni 版本标为0.1.dev1，复现实验以 commit 为准。

官方入口与参数说明：<https://github.com/vllm-project/vllm-omni/blob/69de153f6e2db7454021d4966d641e50a96d0212/recipes/MiniMaxAI/MiniMax-H3.md>。

## 首次启动受阻及修复准备

服务08:08:39 UTC就绪，8个worker完成模型与Turbo LoRA加载。首个请求按recipe传9被代码校验拒绝；已改8。下一请求在rank6首次加载Triton cuda_utils动态库时失败，随后7卡停在集体通信等待；重发请求未推进，不能作为推理测速。未产出视频。

已在本实验独立vLLM-Omni checkout中将Triton缓存按rank隔离到输出目录triton_workers/rank_0…7，8份CudaUtils预编译/导入均验证成功。运行中的旧worker不会自动应用初始化补丁，需人工结束后重新启动。服务PID3759958，其直接子worker PID3768454–3768461；未执行任何终止命令。

后续：确认旧worker已退出，再用server_command.json记录的相同参数和research/ludens_env.sh启动，重新三轮测量。保留拒绝请求与首次缓存失败目录。当前benchmark客户端等待旧服务返回，旧服务退出后客户端应自然失败；确认其结束后才能重跑benchmark.py，已有未完成目录另名保留。新cache修复尚待完整八卡推理验证。

## 旧进程退出，等待资源

08:18 UTC复查确认：用户结束旧MiniMax服务，PID3759958消失，worker转入退出回收状态，benchmark客户端3836946也因连接断开自然结束。未完成输出与日志分别保留为interrupted_after_triton_error/和同名.log。

GPU0–7当前各约16–18GiB被另一项aim_state_sufficiency p1i-audit-generate评测使用，PID3761853–3761860，父进程3761842。它不是本次MiniMax服务，未操作。为避免资源竞争与测速失真，未重新启动MiniMax，等待8卡空闲。隔离缓存补丁、8份CudaUtils预编译及修正为8步的benchmark.py均已准备完成。

## 授权共用本机八卡

Sean明确要求继续在本机运行，接受与现有任务共用GPU。启动前每卡剩余约61–63GiB、利用率约49–54%。已按原TP2×USP4配置启动隔离缓存版本，日志server_isolated_cache.log。测量标记为共享负载，不能当作独占硬件延迟。未改动其他任务。

## 成功结果

隔离缓存版本服务08:44:37 UTC就绪，三次请求均HTTP200。客户端请求到完整MP4耗时41.771、11.910、9.056秒；服务端stage生成41.207、11.682、8.823秒。每段672×384、24FPS、124帧（5.167秒），原生音频32kHz。第一段包含首次运行开销，后两段约9–12秒，尚未达到实时生成。该对比同时改变框架、GPU型号和卡数，并处于共享GPU负载，不能解读成纯8卡加速比。

三轮实际参考图链逐字节验证；3个原片、3个播放副本和1个连续视频均完整解码视频与音频。网页播放640×352/16FPS，连续版651245字节；HTTP获取一致。浏览器验证已显示三次耗时、连续视频及三段视频，无数据加载错误。导航默认进入本轮页面：/static/minimax-8gpu-20260925/index.html。

Codex九帧抽样：首段箱子向左靠近人物，末尾双手离开；后两段箱子位置基本保持。未见LTX举箱摇晃的明显问题。抽帧不替代完整运动/声音验收；Sean尚未评价。observations.json单独记录助手观察。

服务仍常驻，主PID4151266，workers4157243、4157244、4157245、4157246、4157247、4157264、4157265、4157266。本任务结束采样时每worker约50GiB显存；总卡占用约68–70GiB，另一评测仍运行。benchmark进程已自然结束，未执行任何终止命令。

## Sean 整体验收

原话：“感觉各方面都还行，没有啥明显瑕疵”。记录本机8×H100、vLLM-Omni、Turbo8复杂三轮整体效果通过验收，作为后续MiniMax交互测试基准。未将整体认可扩展成逐项动作精确遵循、任意场景可靠性或实时性能通过。性能仍按共享负载记录：首次41.8秒，后两次11.9/9.1秒，各生成5.17秒视频。页面、导航及reviews.json已同步，验收前Codex观察原样保留。

## 流式能力与物品状态交接

Sean希望支持流式推理，并在播放结束后异步处理物品状态。已核对本次vLLM-Omni commit的MiniMaxH3Pipeline：forward先完成整段diffuse再decode，step执行也在post_decode返回最终结果；decode_to_mp4虽内部按时间块解码/编码，仍返回完整bytes。因此当前MiniMax FL2VA Turbo8没有已实现的提前输出最终视频片段能力，不能把框架streaming开关或分块解码当成原生流式生成。官方execution_modes文档也明确final-only pipeline即使开启streaming仍只返回最终输出。

后续交接建议：完整视频生成后，浏览器播放与实际末帧分析/物品提取/状态候选计算并行；播放结束时提交本轮结果并恢复相关物品点选。若分析未完成，保持末帧等该轮结果，不将提示中的预期动作直接写成实际物品状态；异步结果需对应本轮，不能覆盖之后的新操作。该流程是拟实施方向，尚未接入在线demo。

来源：本地pipeline_minimax_h3.py的forward、decode_to_mp4、post_decode；https://docs.vllm.ai/projects/vllm-omni/en/latest/user_guide/diffusion/execution_modes/ 。
