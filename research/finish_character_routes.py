import argparse
import json
import shutil
from pathlib import Path

from video_matting import VideoMatting


parser = argparse.ArgumentParser()
parser.add_argument('--route', choices=['scene', 'person'], required=True)
parser.add_argument('--background', type=Path, required=True)
args = parser.parse_args()
root = Path('/mnt/sv0/sean/Ludens')
out = root / 'research/out/character_layers_20260923'
site = root / 'pipeline/tavern/static/character-routes-20260923'
source = root / 'research/out/video_quality_20260922' if args.route == 'scene' else out / 'person'
models = ['ltx_full', 'joy', 'minimax', 'echo_flash', 'ltx_distilled']
assert args.background.is_file()
assert all((source / f'{model}_character.mp4').is_file() for model in models)
shutil.copyfile(args.background, site / 'inputs/background.png')
(site / 'inputs/assets.json').write_text(json.dumps(dict(background='background.png', note='共用去人物背景；请与原始场景对照检查背景及道具变化。'), ensure_ascii=False, indent=2) + '\n')
matting = VideoMatting(root / 'research/out/character_layers_20260922/rvm_mobilenetv3_fp32.onnx')
records = site / args.route / 'results.json'
rows = json.loads(records.read_text())
for model in models:
    target = out / 'composited' / args.route / model
    metrics = matting(source / f'{model}_character.mp4', target, args.background)
    published = site / args.route / model
    published.mkdir(parents=True, exist_ok=True)
    for name in ('matte.mp4', 'composite.mp4', 'frame_000.png', 'frame_060.png', 'frame_120.png'):
        shutil.copyfile(target / name, published / name)
    row = next(row for row in rows if row['id'] == model)
    row.update(status='complete', matte=f'{model}/matte.mp4', composite=f'{model}/composite.mp4', frames=[f'{model}/frame_{i:03d}.png' for i in (0, 60, 120)], note='RVM 提取与固定背景合成已完成，保留原片音轨；待检查边缘、遮挡和接触位置。', matting_seconds=round(metrics['seconds'], 2))
    records.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + '\n')
    print(f'{args.route}/{model}: composite published', flush=True)
