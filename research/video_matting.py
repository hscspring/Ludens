import argparse
import json
import subprocess
from contextlib import ExitStack
from pathlib import Path
from time import perf_counter

import av
import cv2
import numpy as np
import onnxruntime as ort
from PIL import Image


class VideoMatting:
    def __init__(self, weights: Path) -> None:
        options = ort.SessionOptions()
        options.intra_op_num_threads = 4
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(str(weights), options, providers=['CPUExecutionProvider'])
        self.recurrent = [np.zeros((1, 1, 1, 1), dtype=np.float32) for _ in range(4)]

    def extract(self, image: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        inputs = {f'r{i + 1}i': value for i, value in enumerate(self.recurrent)}
        inputs.update(src=image.transpose(2, 0, 1)[None], downsample_ratio=np.array([0.5], dtype=np.float32))
        foreground, alpha, *self.recurrent = self.session.run(None, inputs)
        return foreground[0].transpose(1, 2, 0), alpha[0].transpose(1, 2, 0)

    @staticmethod
    def composite(foreground: np.ndarray, alpha: np.ndarray, background: np.ndarray) -> np.ndarray:
        return np.uint8(np.clip(foreground * alpha + background * (1 - alpha), 0, 1) * 255)

    def __call__(self, source: Path, output: Path, background: Path, object_masks: np.ndarray | None = None,
                 person_masks: np.ndarray | None = None) -> dict:
        output.mkdir(parents=True, exist_ok=True)
        self.recurrent = [np.zeros((1, 1, 1, 1), dtype=np.float32) for _ in range(4)]
        started = perf_counter()
        with av.open(str(source)) as reader:
            video = reader.streams.video[0]
            width, height, fps = video.width, video.height, video.average_rate
            has_audio = bool(reader.streams.audio)
        plate = np.asarray(Image.open(background).convert('RGB').resize((width, height), Image.Resampling.LANCZOS), dtype=np.float32) / 255
        yy, xx = np.indices((height, width))
        board = np.repeat((0.25 + 0.12 * ((xx // 24 + yy // 24) % 2))[..., None], 3, axis=2)
        with ExitStack() as stack:
            reader = stack.enter_context(av.open(str(source)))
            writers = []
            for name in ('matte', 'composite'):
                writer = stack.enter_context(av.open(str(output / f'{name}_silent.mp4'), 'w'))
                stream = writer.add_stream('libx264', rate=fps)
                stream.width, stream.height, stream.pix_fmt = width, height, 'yuv420p'
                stream.codec_context.thread_count = 2
                writers.append((writer, stream))
            for index, frame in enumerate(reader.decode(video=0)):
                rgb = frame.to_ndarray(format='rgb24').astype(np.float32) / 255
                foreground, alpha = self.extract(rgb)
                if person_masks is not None:
                    mask = person_masks[index].astype(np.uint8)
                    inside = cv2.erode(mask, np.ones((3, 3), np.uint8)).astype(bool)[..., None]
                    outside = (cv2.dilate(mask, np.ones((3, 3), np.uint8)) == 0)[..., None]
                    foreground = np.where(inside, rgb, foreground)
                    alpha = np.where(outside, 0, np.where(inside, 1, alpha))
                if object_masks is not None:
                    mask = object_masks[index, ..., None]
                    foreground = np.where(mask, rgb, foreground)
                    alpha = np.maximum(alpha, mask)
                for (writer, stream), canvas in zip(writers, (board, plate)):
                    image = self.composite(foreground, alpha, canvas)
                    for packet in stream.encode(av.VideoFrame.from_ndarray(image, format='rgb24')):
                        writer.mux(packet)
                if index in (0, 60, 120):
                    rgba = np.uint8(np.clip(np.concatenate((foreground, alpha), axis=2), 0, 1) * 255)
                    Image.fromarray(rgba).save(output / f'frame_{index:03d}.png')
            for writer, stream in writers:
                for packet in stream.encode():
                    writer.mux(packet)
            rgba = np.uint8(np.clip(np.concatenate((foreground, alpha), axis=2), 0, 1) * 255)
            Image.fromarray(rgba).save(output / f'frame_{index:03d}.png')
            if person_masks is not None:
                assert len(person_masks) == index + 1
        ffmpeg = Path(__file__).parent / 'out/video_quality_20260922/bin/ffmpeg'
        for name in ('matte', 'composite'):
            command = [str(ffmpeg), '-nostdin', '-v', 'error', '-y', '-i', str(output / f'{name}_silent.mp4'), '-i', str(source), '-map', '0:v:0']
            if has_audio:
                command += ['-map', '1:a:0']
            subprocess.run(command + ['-c', 'copy', str(output / f'{name}.mp4')], check=True)
        metrics = dict(frames=index + 1, fps=float(fps), width=width, height=height, audio=has_audio, seconds=perf_counter() - started, source=str(source), background=str(background))
        (output / 'matting.json').write_text(json.dumps(metrics, indent=2) + '\n')
        return metrics


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--background', type=Path, required=True)
    parser.add_argument('--person-masks', type=Path)
    parser.add_argument('--weights', type=Path, default=Path(__file__).parent / 'out/character_layers_20260922/rvm_mobilenetv3_fp32.onnx')
    args = parser.parse_args()
    person_masks = np.load(args.person_masks)['masks'] if args.person_masks else None
    print(json.dumps(VideoMatting(args.weights)(args.source, args.output, args.background,
                                               person_masks=person_masks)), flush=True)
