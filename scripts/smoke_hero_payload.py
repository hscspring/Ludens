"""Smoke:hero 卡开场首拍 payload 结构验证(不出片,不碰 GPU)。

核验风险点:RosterExtractor 抽出的角色名是否字面匹配 assets 的 key —— 匹配上 memory_slots 才非空、锚图才真喂进去。
"""
import json
import sys

sys.path.insert(0, "/mnt/local/sean/Ludens")

from pipeline.story_feed import StoryFeed

CARDS = "/mnt/local/sean/Ludens/seed_cards.json"


def main() -> None:
    cards = json.load(open(CARDS))
    card = next(c for c in cards if c["id"] == "hero")

    feed = StoryFeed(card)
    print("[roster] 抽出的角色名:", list(feed.content.roster.keys()))
    print("[assets] 卡里配的 key :", list(card["assets"].keys()))

    unit = feed.advance(None)  # 开场首拍
    p = unit.payload
    chars = next(t["content"]["characters"] for t in unit.turns if t["role"] == "state")

    print("\n[state.characters] 在场角色:", list(chars.keys()))
    print("[renderer.ids] ID 分配   :", feed.renderer.ids)
    print("\nshot_id       :", p["shot_id"])
    print("size          :", p["width"], "x", p["height"])
    print("condition_img :", p["condition_img"])
    print("memory_slots  :", json.dumps(p["memory_slots"], ensure_ascii=False))
    print("\nprompt:\n", p["prompt"])

    assert p["width"] == 736 and p["height"] == 1280, "尺寸不是竖屏 736x1280"
    assert p["condition_img"] is None, "condition_img 应保持 None(走 memory_slots 路线)"
    assert p["memory_slots"], "❌ memory_slots 为空:角色名没匹配上 assets,锚图没喂进去"
    assert p["memory_slots"][0]["image_url"].endswith("anchor_hero.png"), "锚图路径不对"
    assert "semi-realistic" in p["prompt"].lower(), "半写实 style 没注入 prompt"
    assert "warm skin tones" in p["prompt"].lower(), "统一色调 grade 没注入 prompt"
    print("\n✅ OK: memory_slots 非空 + 锚图正确 + 竖屏 + 半写实 style + 统一色调 grade 已注入")


if __name__ == "__main__":
    main()
