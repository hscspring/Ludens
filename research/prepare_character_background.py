import argparse
import os
import subprocess
from pathlib import Path
from time import perf_counter

parser = argparse.ArgumentParser()
parser.add_argument('--empty-crate', action='store_true')
args = parser.parse_args()
assert os.uname().nodename in {'doams-185', 'doams-187'}
assert os.environ['CUDA_VISIBLE_DEVICES'] == '2'
if subprocess.check_output(['nvidia-smi', '--id=2', '--query-compute-apps=pid', '--format=csv,noheader,nounits'], text=True).strip():
    raise SystemExit('GPU 2 is occupied; image generation was not started.')

from PIL import Image
from renderers import Flux2Renderer

out = Path('/mnt/sv0/sean/Ludens/research/out/character_layers_20260923/inputs')
prompt = ('Remove the blond man completely from this tavern photograph. No people, no human silhouettes, no hands, no coat. '
          'Reconstruct the wooden bar, shelves and floor behind him naturally. Keep the identical camera, composition, '
          'warm amber lighting, rain window, wooden crate full of papers with burgundy ledger, metal bucket and folded towels. '
          'The crate stays on the counter in exactly the same position. Do not add or remove any objects except the man.')
(out / 'background.prompt.txt').write_text(prompt + '\n')
if args.empty_crate:
    prompt = ('Remove the blond man AND the wooden crate with all of its papers and burgundy ledger completely. '
              'Show an empty uninterrupted wooden counter where the crate stood. No people, hands, human silhouettes, boxes, papers or books. '
              'Reconstruct the background behind the man. Preserve the original camera, warm lighting, rain window, metal bucket, folded towels and all other furniture. '
              'Do not change the positions, scale or design of the remaining objects. Photorealistic tavern background plate.')
    (out / 'background_empty.prompt.txt').write_text(prompt + '\n')
started = perf_counter()
renderer = Flux2Renderer('/mnt/sv0/sean/models/FLUX.2-klein-4B', size=(1280, 704))
image = renderer.edit(Image.open(out / 'scene_reference.png').convert('RGB'), prompt, seed=7)
image.save(out / ('background_empty_generated.png' if args.empty_crate else 'background_generated.png'))
print(f'Background generated in {perf_counter() - started:.2f}s', flush=True)
