#!/usr/bin/env bash
# 世界模型调研来源存在性核实：arXiv / GitHub / HuggingFace 逐条实拉，分出真实 vs 疑似编造。
# 只读网络，无 GPU。GitHub 未认证限 60 次/时，本表 ~30 项在限内。
set -u

UA="ludens-survey-verify"

hr() { printf '%s\n' "----------------------------------------------------------------------"; }

check_arxiv() {  # arXiv abs 页 200=存在
  local id="$1" code
  code=$(curl -s -o /dev/null -w "%{http_code}" -A "$UA" "https://arxiv.org/abs/$id")
  case "$code" in
    200) printf "  ✅ arXiv %-12s EXISTS\n" "$id" ;;
    *)   printf "  ❌ arXiv %-12s HTTP %s (疑似不存在)\n" "$id" "$code" ;;
  esac
}

check_github() {  # GitHub API 200=存在，附 full_name + pushed_at + stars
  local repo="$1" body code meta
  body=$(curl -s -w "\n%{http_code}" -A "$UA" "https://api.github.com/repos/$repo")
  code=$(printf '%s' "$body" | tail -1)
  if [ "$code" = "200" ]; then
    meta=$(printf '%s' "$body" | rg -o '"(full_name|pushed_at|stargazers_count)": ?"?[^",}]*"?' | tr '\n' ' ')
    printf "  ✅ gh   %-32s EXISTS  %s\n" "$repo" "$meta"
  elif [ "$code" = "404" ]; then
    printf "  ❌ gh   %-32s 404 (疑似编造)\n" "$repo"
  else
    printf "  ⚠️  gh   %-32s HTTP %s\n" "$repo" "$code"
  fi
}

check_hf() {  # HuggingFace API 200=存在。$1=models|datasets $2=repo
  local kind="$1" repo="$2" body code meta
  body=$(curl -s -w "\n%{http_code}" -A "$UA" "https://huggingface.co/api/$kind/$repo")
  code=$(printf '%s' "$body" | tail -1)
  if [ "$code" = "200" ]; then
    meta=$(printf '%s' "$body" | rg -o '"(modelId|id|lastModified|downloads)": ?"?[^",}]*"?' | head -3 | tr '\n' ' ')
    printf "  ✅ hf/%-8s %-42s EXISTS  %s\n" "$kind" "$repo" "$meta"
  elif [ "$code" = "401" ] || [ "$code" = "404" ]; then
    printf "  ❌ hf/%-8s %-42s %s (疑似编造/私有)\n" "$kind" "$repo" "$code"
  else
    printf "  ⚠️  hf/%-8s %-42s HTTP %s\n" "$kind" "$repo" "$code"
  fi
}

echo "== A 段（应已核实，做对照基线）=="
hr
check_github SkyworkAI/Matrix-Game
check_hf models Skywork/Matrix-Game-2.0
check_hf models Skywork/Matrix-Game-3.0
check_github eloialonso/diamond
check_hf models Etched/oasis-500m
check_github etched-ai/open-oasis
check_hf models tencent/Hunyuan-GameCraft-1.0
check_arxiv 2506.17201
check_github OpenSparseLLMs/Open-Pandora
check_github NVIDIA/Cosmos
check_hf models robbyant/lingbot-world-v2-14b-causal-fast-diffusers
check_arxiv 2604.08995
check_arxiv 2508.08601
check_arxiv 2511.23429

echo; echo "== B 段（高编造风险，核实重点）=="
hr
echo "[DreamX-World]"
check_arxiv 2606.16993
check_github AMAP-ML/DreamX-World
check_hf models GD-ML/DreamX-World-5B
echo "[Incantation]"
check_arxiv 2605.18601
check_hf datasets zhush/incantation-elden-ring-scenes
echo "[H3-World]"
check_arxiv 2609.01560
check_github Danzer1xxxxChan/H3-World
echo "[JoyAI-Echo]"
check_arxiv 2608.23383
check_github jd-opensource/JoyAI-Echo
check_hf models jdopensource/JoyAI-Echo
echo "[身份适配器]"
check_arxiv 2607.15772
check_github YilaiLiu-HKU/SlotMem
check_hf models ernie-research/Memento
check_hf models Kevin-thu/StoryMem
check_arxiv 2605.18733
check_github Eddie0521/IAMFlow
check_github kaaskoek232/IPAdapterWAN
echo "[文本状态大脑]"
check_arxiv 2607.17250
echo "[前序 memory 提到的]"
check_github NoizAI/HelixWorld
check_github GameGen-X/GameGen-X
hr
echo "完成。"
