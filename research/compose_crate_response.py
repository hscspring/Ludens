import argparse
import shutil
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

parser = argparse.ArgumentParser()
parser.add_argument('--round-dir', type=Path, required=True)
parser.add_argument('--round-number', type=int, required=True)
parser.add_argument('--dx', type=int, required=True)
parser.add_argument('--site', type=Path, required=True)
args = parser.parse_args()
root = Path('/mnt/sv0/sean/Ludens')
prior = root / 'pipeline/tavern/static/crate-handoff-20260923/ltx_b_right_rim'
mask = np.load(args.round_dir / 'person/person_masks.npz')['masks'][0].astype(np.uint8)
inside = cv2.erode(mask, np.ones((3, 3), np.uint8)).astype(bool)
outside = cv2.dilate(mask, np.ones((3, 3), np.uint8)) == 0
raw = Image.open(args.round_dir / 'raw_120.png').convert('RGB')
rgba = np.asarray(Image.open(args.round_dir / 'rvm/frame_120.png')).copy()
rgba[..., :3][inside] = np.asarray(raw)[inside]
rgba[..., 3][inside] = 255
rgba[..., 3][outside] = 0
person = Image.fromarray(rgba)
person.save(args.round_dir / 'person_end.png')
crate = Image.new('RGBA', person.size)
crate.alpha_composite(Image.open(prior / 'crate_released.png'), (args.dx, 0))
crate.save(args.round_dir / 'crate_static.png')
assert not np.any((rgba[..., 3] > 0) & (np.asarray(crate)[..., 3] > 0))
scene = Image.open(prior / 'background.png').convert('RGBA')
scene.alpha_composite(person)
scene.alpha_composite(crate)
scene.convert('RGB').save(args.round_dir / 'end.png')
prefix = f'round{args.round_number}'
for source, target in [('end.png', f'{prefix}_end.png'), ('reference.png', f'{prefix}_reference.png'), ('ltx_full_character.mp4', f'{prefix}_raw.mp4'), ('contact_sheet.jpg', f'{prefix}_sheet.jpg'), ('action.prompt.txt', f'{prefix}.prompt.txt')]:
    shutil.copyfile(args.round_dir / source, args.site / target)
comparison = Image.new('RGB', (1280, 382), '#171513')
for col, image in enumerate((raw, scene.convert('RGB'))):
    comparison.paste(image.resize((640, 352)), (col * 640, 30))
    ImageDraw.Draw(comparison).text((col * 640 + 8, 8), ('SOURCE END', 'INTERACTIVE SCENE')[col], fill='white')
comparison.save(args.site / f'{prefix}_handoff.jpg')
