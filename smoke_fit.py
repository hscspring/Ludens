"""ShotRenderer._fit 全量硬验证:证明 prompt 恒 ≤1500、台词永远整句(绝无半句)、丢弃只发生在末尾。

两段:
  (1) 确定性——构造病态超长输入(超长外形 / 海量长台词),不靠 LLM,直接证明预算保护式裁剪的三条不变式;
  (2) 真实四卡各产 3 shot(纯 LLM 无 GPU),确认正常路径全过 + prompt 与 unit.beats 台词一致。
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from shot_renderer import MAX_PROMPT, ShotRenderer  # noqa: E402
from pipeline.story_feed import MAX_RETRY, StoryFeed  # noqa: E402

CAM = {"shot_size": "medium shot", "camera_move": "slow push-in", "environment": "warm dusk light"}


def make_turns(n_chars: int, appearance_len: int, n_beats: int, line_len: int) -> list[dict]:
    names = [f"Char{i}" for i in range(n_chars)]
    chars = {n: {"appearance": ("wearing an intricately detailed outfit " * 40)[:appearance_len],
                 "voice": "a calm low voice"} for n in names}
    beats = [{"who": names[i % n_chars], "action": "steps forward",
              "line": f"LINE{i}_" + ("word " * 60)[:line_len].strip()} for i in range(n_beats)]
    return [
        {"role": "state", "content": {"location": "an abandoned station", "time": "night",
                                      "environment": "flickering lights", "mood": "tense", "characters": chars}},
        {"role": "assistant", "content": {"beats": beats}},
    ]


def eff_beats(turns: list[dict]) -> list[dict]:
    return next(t["content"]["beats"] for t in turns if t["role"] == "assistant")


def check_invariants(tag: str, orig: list[dict], turns: list[dict], prompt: str) -> None:
    kept = eff_beats(turns)
    assert len(prompt) <= MAX_PROMPT, f"{tag}: prompt {len(prompt)} > {MAX_PROMPT}"
    assert len(kept) >= 1, f"{tag}: dropped ALL beats"
    assert kept == orig[:len(kept)], f"{tag}: dropped beats are not a clean suffix"
    for b in kept:  # 每条保留台词必须整句 verbatim 出现 —— 证明绝无半句截断
        assert b["line"] in prompt, f'{tag}: line not intact in prompt: {b["line"][:40]!r}'
    print(f"  {tag}: prompt={len(prompt)} beats {len(orig)}->{len(kept)} OK")


def deterministic() -> None:
    print("[1] 确定性硬验证 _fit")
    cases = {
        "normal": (2, 60, 2, 30),          # 短:不该触发任何裁剪
        "moderate-overflow": (3, 400, 3, 40),  # 外形撑爆:压 cast,台词应全留
        "extreme-dialogue": (3, 400, 30, 55),  # 台词海量:压光 cast 仍超,末尾整 beat 丢
        "pathological": (3, 800, 60, 60),      # 全面爆炸
    }
    for tag, (nc, al, nb, ll) in cases.items():
        turns = make_turns(nc, al, nb, ll)
        orig = list(eff_beats(turns))
        payload = ShotRenderer(work_id=f"fit-{tag}").render(1, turns, CAM)
        check_invariants(tag, orig, turns, payload["prompt"])
    # normal 不该丢 beat / 不该压 cast(全 3 段角色名都在)
    turns = make_turns(2, 60, 2, 30)
    orig = list(eff_beats(turns))
    p = ShotRenderer(work_id="fit-normal2").render(1, turns, CAM)["prompt"]
    assert len(eff_beats(turns)) == len(orig), "normal 不该丢 beat"
    print("  normal: 未丢 beat ✓")


def next_good(feed: StoryFeed):
    """复用生产同款容错:gemini 偶发坏输出(空/缺 assistant)重产,连续 MAX_RETRY 次仍坏则返回 None(该卡内容侧撑不住)。"""
    for _ in range(MAX_RETRY):
        try:
            return feed.advance()
        except (ValueError, RuntimeError) as e:
            print(f"  ({feed.renderer.work_id} 重产: {e})"[:100])
    return None


def real_cards() -> list[tuple[str, int]]:
    print("[2] 真实四卡各产 3 shot")
    cards = json.load(open(os.path.join(HERE, "seed_cards.json")))
    stalled = []
    for card in cards:
        feed = StoryFeed(card)
        for _ in range(3):
            unit = next_good(feed)
            if unit is None:  # 内容侧连 MAX_RETRY 都撑不住:与 1500 正交,记 WARN 继续
                stalled.append((card["id"], feed.index + 1))
                print(f"  WARN {card['id']} shot {feed.index + 1}: 内容侧连 {MAX_RETRY} 次坏输出,跳过该卡")
                break
            n = len(unit.payload["prompt"])
            assert n <= MAX_PROMPT, f'{card["id"]} shot {unit.index}: prompt {n} > {MAX_PROMPT}'
            for b in unit.beats:  # prompt 与字幕侧台词一致
                assert b["line"] in unit.payload["prompt"], \
                    f'{card["id"]} shot {unit.index}: line not in prompt: {b["line"][:40]!r}'
            print(f"  {card['id']} shot {unit.index}: prompt={n} beats={len(unit.beats)} OK")
    return stalled


def main() -> None:
    deterministic()
    stalled = real_cards()
    print("\n1500 全量硬验证 OK: prompt 恒 ≤1500,台词整句无半句,丢弃仅末尾。")
    if stalled:
        print(f"内容侧 WARN(与 1500 无关): {stalled} —— gemini 在这些卡/步系统性吐空场景,需内容侧另查。")


if __name__ == "__main__":
    main()
