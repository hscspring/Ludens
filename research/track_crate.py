import argparse
import json
import os
import subprocess
from pathlib import Path
from time import perf_counter

parser = argparse.ArgumentParser()
parser.add_argument('--host', default='doams-187', choices=['doams-187', 'am4g1r4bm1', 'am4g1r21bm1', 'doams-179', 'am4g1r24bm2'])
parser.add_argument('--source', type=Path, default=Path('/mnt/sv0/sean/Ludens/research/out/video_quality_20260922/joy_character.mp4'))
parser.add_argument('--output', type=Path, default=Path('/mnt/sv0/sean/Ludens/research/out/crate_interaction_20260923'))
parser.add_argument('--prompt-file', type=Path)
parser.add_argument('--subject', choices=['crate', 'person'], default='crate')
args = parser.parse_args()
gpu = os.environ['CUDA_VISIBLE_DEVICES']
assert os.uname().nodename == args.host
assert gpu.isdigit() and 0 <= int(gpu) < 8
if subprocess.check_output(['nvidia-smi', f'--id={gpu}', '--query-compute-apps=pid', '--format=csv,noheader,nounits'], text=True).strip():
    raise SystemExit(f'GPU {gpu} occupied; tracking did not start.')

import av
import cv2
import numpy as np
import torch
from PIL import Image
from transformers import Sam2VideoModel, Sam2VideoProcessor


class VideoObjectTracking:
    def __init__(self, weights: Path) -> None:
        self.model = Sam2VideoModel.from_pretrained(weights).to('cuda', dtype=torch.bfloat16).eval()
        self.processor = Sam2VideoProcessor.from_pretrained(weights)

    @torch.inference_mode()
    def __call__(self, source: Path, output: Path, prompts: dict | None = None, subject: str = 'crate') -> None:
        output.mkdir(parents=True, exist_ok=True)
        started = perf_counter()
        if source.suffix.lower() in {'.png', '.jpg'}:
            fps, frames = 24.0, [np.asarray(Image.open(source).convert('RGB'))]
        else:
            with av.open(str(source)) as reader:
                fps = float(reader.streams.video[0].average_rate)
                frames = [frame.to_ndarray(format='rgb24') for frame in reader.decode(video=0)]
        height, width = frames[0].shape[:2]
        session = self.processor.init_video_session(video=frames, inference_device='cuda', video_storage_device='cpu', dtype=torch.bfloat16)
        if prompts is None:
            prompts = dict(input_boxes=[[[580, 294, 887, 484]]],
                input_points=[[[[770, 420], [620, 368], [737, 338], [665, 340], [654, 440], [604, 311], [895, 445], [720, 510]]]],
                input_labels=[[[1, 1, 1, 1, 0, 0, 0, 0]]])
        self.processor.add_inputs_to_inference_session(session, frame_idx=0, obj_ids=1, **prompts)
        masks = np.zeros((len(frames), height, width), dtype=bool)
        records = []
        self.model(inference_session=session, frame_idx=0)
        for result in self.model.propagate_in_video_iterator(session):
            index = result.frame_idx
            mask = self.processor.post_process_masks([result.pred_masks], original_sizes=[[height, width]], binarize=True)[0][0, 0].cpu().numpy().astype(bool)
            masks[index] = mask
            contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            contour = max(contours, key=cv2.contourArea)
            polygon = cv2.approxPolyDP(contour, 2.0, True).reshape(-1, 2).tolist()
            records.append(dict(frame=index, polygon=polygon, area=int(mask.sum())))
            if index in (0, 60, len(frames) - 1):
                rgba = np.concatenate((frames[index], (mask[..., None] * 255).astype(np.uint8)), axis=2)
                Image.fromarray(rgba).save(output / f'{subject}_{index:03d}.png')
            if index % 30 == 0:
                print(f'Tracked frame {index}', flush=True)
        np.savez_compressed(output / f'{subject}_masks.npz', masks=masks)
        (output / 'tracking.json').write_text(json.dumps(dict(object_id='cassian' if subject == 'person' else 'tavern_crate', source=str(source), fps=fps, width=width, height=height, frames=records, seconds=perf_counter()-started), ensure_ascii=False) + '\n')
        print(f'Tracked {len(records)} frames in {perf_counter()-started:.2f}s', flush=True)


if __name__ == '__main__':
    torch.set_num_threads(4)
    root = Path('/mnt/sv0/sean')
    prompts = json.loads(args.prompt_file.read_text()) if args.prompt_file else None
    VideoObjectTracking(root / 'models/sam2.1-hiera-tiny')(args.source, args.output, prompts, args.subject)
