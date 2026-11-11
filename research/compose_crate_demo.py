import argparse
import json
import shutil
from pathlib import Path

import av
import cv2
import numpy as np
from PIL import Image

from video_matting import VideoMatting


parser = argparse.ArgumentParser()
parser.add_argument('--joint-only', action='store_true')
parser.add_argument('--push-model', choices=['ltx_full', 'joy'])
parser.add_argument('--person-masks', type=Path)
parser.add_argument('--soft-edges', action='store_true')
parser.add_argument('--source', type=Path)
parser.add_argument('--out-dir', type=Path)
parser.add_argument('--site', type=Path)
parser.add_argument('--original-url')
args = parser.parse_args()
root = Path('/mnt/sv0/sean/Ludens')
out = root / 'research/out/crate_interaction_20260923'
site = root / 'pipeline/tavern/static/crate-interaction-20260923'
site.mkdir(parents=True, exist_ok=True)
source = root / 'research/out/video_quality_20260922/joy_character.mp4'
if args.push_model:
    out = root / 'research/out/crate_push_20260923' / f'{args.push_model}_layers'
    site = root / 'pipeline/tavern/static/crate-handoff-20260923' / args.push_model
    site.mkdir(parents=True, exist_ok=True)
    source = out.parent / f'{args.push_model}_character.mp4'
source = args.source or source
out = args.out_dir or out
site = args.site or site
site.mkdir(parents=True, exist_ok=True)
background = root / 'research/out/character_layers_20260923/inputs/background_empty_generated.png'
masks = np.load(out / 'crate_masks.npz')['masks']
tracking = json.loads((out / 'tracking.json').read_text())
assert len(tracking['frames']) == len(masks) == 121
contact_masks = np.zeros_like(masks, dtype=np.uint8)
for index, mask in enumerate(masks):
    # This crate is approximately convex; retain contact pixels inside its outer envelope.
    hull = cv2.convexHull(cv2.findNonZero(mask.astype(np.uint8)))
    cv2.fillConvexPoly(contact_masks[index], hull, 1)
contact_masks = contact_masks.astype(bool)
render_masks = contact_masks
joint_name = 'joint_contact'
if args.person_masks:
    person_masks = np.load(args.person_masks)['masks']
    assert person_masks.shape == contact_masks.shape
    person_masks = np.stack([cv2.erode(mask.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool) for mask in person_masks])
    render_masks = contact_masks | person_masks
    joint_name = 'joint_person'
if args.soft_edges:
    render_masks = np.stack([cv2.GaussianBlur(mask.astype(np.float32), (3, 3), 0) for mask in render_masks])
    joint_name += '_soft'
plate = Image.open(background).convert('RGBA')
plate.alpha_composite(Image.open(out / 'crate_000.png').convert('RGBA'))
plate.convert('RGB').save(out / 'background_fixed_crate.png')
matting = VideoMatting(root / 'research/out/character_layers_20260922/rvm_mobilenetv3_fp32.onnx')
routes = [(joint_name, background, render_masks)]
if not args.joint_only and not args.push_model:
    routes.insert(0, ('separate', out / 'background_fixed_crate.png', None))
for route, canvas, objects in routes:
    matting(source, out / route, canvas, object_masks=objects)
    shutil.copyfile(out / route / 'composite.mp4', site / f'{route}.mp4')
for index in (0, 120):
    image = Image.open(out / joint_name / f'frame_{index:03d}.png')
    opaque = contact_masks[index] & (render_masks[index] == 1)
    assert np.all(np.asarray(image)[..., 3][opaque] == 255)
    image.save(site / f'{joint_name}_{index:03d}.png')
    if not args.push_model:
        shutil.copyfile(out / 'separate' / f'frame_{index:03d}.png', site / f'person_separate_{index:03d}.png')
    shutil.copyfile(out / f'crate_{index:03d}.png', site / f'crate_{index:03d}.png')
shutil.copyfile(background, site / 'background.png')
shutil.copyfile(out / 'tracking.json', site / 'tracking.json')
if args.push_model:
    joint = np.asarray(Image.open(site / f'{joint_name}_120.png')).copy()
    crate, person = joint.copy(), joint.copy()
    split_mask = cv2.dilate(contact_masks[-1].astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool) if args.soft_edges else contact_masks[-1]
    crate[..., 3][~split_mask] = 0
    person[..., 3][split_mask] = 0
    suffix = ('_personfix' if args.person_masks else '') + ('_soft' if args.soft_edges else '')
    Image.fromarray(crate).save(site / f'crate_released{suffix}.png')
    Image.fromarray(person).save(site / f'person_released{suffix}.png')
    recombined = Image.alpha_composite(Image.fromarray(person), Image.fromarray(crate))
    plate = Image.open(background).convert('RGBA')
    actual = np.asarray(Image.alpha_composite(plate, recombined)).astype(int)
    expected = np.asarray(Image.alpha_composite(plate, Image.fromarray(joint))).astype(int)
    difference = int(np.abs(actual - expected).max())
    assert difference <= 1, difference
    (site / f'handoff{suffix}.json').write_text(json.dumps(dict(model=args.push_model,
        object_id='tavern_crate', release_frame=120, split_max_pixel_error=difference,
        original=args.original_url or f'../crate-push-20260923/{args.push_model}_character.mp4'), indent=2))
for route, _, _ in routes:
    with av.open(str(site / f'{route}.mp4')) as reader:
        assert reader.streams.video[0].average_rate == 24 and len(reader.streams.audio) == 1
        count = 0
        for index, frame in enumerate(reader.decode(video=0)):
            count += 1
            if index in (0, 60, 120):
                frame.to_image().save(out / f'{route}_{index:03d}.jpg')
        assert count == 121
print(f'{len(routes)} composites published and all 121 frames decoded; audio streams preserved.')
