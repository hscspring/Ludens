import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

import av
from PIL import Image


class StoryEvaluation:
    def __init__(self, story_path: Path, site: Path) -> None:
        self.story_path = story_path.resolve()
        self.out = self.story_path.parent
        self.site = site.resolve()
        self.project = Path('/mnt/sv0/sean/Ludens')
        self.story = json.loads(self.story_path.read_text())
        self.ffmpeg = self.project / 'research/out/video_quality_20260922/bin/ffmpeg'
        labels = {'ltx_full': 'LTX-2.5 Full/SFT', 'joy': 'JoyAI-Echo 1.5 BF16',
                  'minimax': 'MiniMax-H3 FL2VA', 'echo_flash': 'Echo-WM Flash',
                  'ltx_distilled': 'LTX-2.5 Distilled', 'minimax_base': 'MiniMax · 原版 BF16',
                  'minimax_turbo8': 'MiniMax · Turbo 8 步', 'joy_bf16': 'Joy 1.5 · BF16',
                  'joy_fp8': 'Joy 1.5 · 官方 FP8', 'ltx_bf16': 'LTX Distilled · BF16',
                  'ltx_fp8': 'LTX Distilled · TorchAO FP8'}
        self.inference = None
        self.first_call = True
        self.results = dict(title=self.story['title'], status='prepared', node=self.story['node'],
                            gpu=self.story['gpu'], scenes=self.story['scenes'], models=[
            dict(id=model, label=labels[model], rounds=[
                dict(id=scene['id'], status='pending') for scene in self.story['scenes']])
            for model in self.story['models']])

    def __call__(self) -> None:
        host = self.story.get('host', 'am4g1r24bm2')
        if self.story.get('acceleration_profile') and os.uname().nodename != host:
            print(f'This profile is assigned to {host}; skipped on {os.uname().nodename}.', flush=True)
            return
        assert os.uname().nodename == host
        assert os.environ['CUDA_VISIBLE_DEVICES'] == str(self.story['gpu'])
        occupants = subprocess.check_output(
            ['nvidia-smi', f'--id={self.story["gpu"]}', '--query-compute-apps=pid',
             '--format=csv,noheader,nounits'], text=True).strip()
        if occupants:
            self.results.update(status='waiting', note=f'指定 GPU 被占用：{occupants}')
            self._publish()
            raise SystemExit(75)
        self.results.update(status='running', started_at=datetime.now(timezone.utc).isoformat())
        self._publish()
        if profile := self.story.get('acceleration_profile'):
            from video_inference import VideoInference

            self.inference = VideoInference(profile, self.story['target_width'],
                                            self.story['target_height'], self.story['seed'])
            self.results.update(load_seconds=self.inference.load_seconds, configuration=self.inference.details)
            self._publish()
        for model in self.results['models']:
            reference = Path(self.story['initial_reference'])
            for scene, row in zip(self.story['scenes'], model['rounds'], strict=True):
                reference = self._scene(model['id'], scene, row, Path(scene.get('reference', reference)))
            self._join(model)
            self._publish()
        self.results['status'] = 'generated'
        self._publish()

    def _scene(self, model: str, scene: dict, row: dict, reference: Path) -> Path:
        out = self.out / model / scene['id']
        site = self.site / model / scene['id']
        out.mkdir(parents=True, exist_ok=False)
        site.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(reference, out / 'reference.png')
        Image.open(reference).convert('RGB').save(site / 'reference.webp', quality=90)
        prompt = out / 'prompt.txt'
        prompt.write_text(scene['prompt'] + '\n')
        (site / 'results.json').write_text(json.dumps([dict(id=model, status='pending')]))
        prefix = f'{model}/{scene["id"]}'
        row.update(status='running', reference=f'{prefix}/reference.webp',
                   reference_source=str(reference), started_at=datetime.now(timezone.utc).isoformat())
        if target := scene.get('target_image'):
            Image.open(target).convert('RGB').save(site / 'target.webp', quality=90)
            row['target'] = f'{prefix}/target.webp'
        self._publish()
        if self.inference is not None:
            self.inference.seed = scene.get('seed', self.story['seed'])
            options = {'last_image': Path(scene['last_image'])} if scene.get('last_image') else {}
            metrics = self.inference(out / 'reference.png', scene['prompt'], out, **options)
            shutil.copyfile(out / f'{model}_character.mp4', site / f'{model}_character.mp4')
            load = self.inference.load_seconds if self.first_call else 0
            row.update(response_seconds=metrics['response_seconds'], load_seconds=load,
                       cold_seconds=metrics['response_seconds'] + load, first_call=self.first_call)
            row.update(seed=self.inference.seed, end_frame_condition=bool(options))
            self.first_call = False
        else:
            with (out / 'runner.log').open('w') as log:
                result = subprocess.run([
                    sys.executable, str(self.project / 'research/run_video_quality.py'), model,
                    '--host', 'am4g1r24bm2', '--out-dir', str(out), '--site', str(site),
                    '--image', str(out / 'reference.png'), '--prompt-file', str(prompt),
                ], stdout=log, stderr=subprocess.STDOUT)
            run = json.loads((site / 'results.json').read_text())[0]
            if result.returncode:
                row.update(status=run['status'] if run['status'] == 'waiting' else 'failed',
                           note=run.get('note', '运行失败，见 runner.log'), log=str(out / 'runner.log'))
                self.results['status'] = row['status']
                self._publish()
                raise subprocess.CalledProcessError(result.returncode, model)
            row['cold_seconds'] = run['wall_seconds']
        row['status'] = 'processing'
        self._publish()
        self._collect(model, out, site, row)
        row.update(status='generated', quality='待人工评价')
        self._publish()
        print(f'{model}/{scene["id"]}: {row["cold_seconds"]}s, {row["video_seconds"]:.2f}s video', flush=True)
        return out / 'last.png'

    def _collect(self, model: str, out: Path, site: Path, row: dict) -> None:
        started = perf_counter()
        raw = site / f'{model}_character.mp4'
        with av.open(str(raw)) as container:
            stream = container.streams.video[0]
            fps = float(stream.average_rate)
            frames = 0
            last = None
            for frame in container.decode(video=0):
                frames += 1
                last = frame
            if last is None:
                raise ValueError(f'No decoded frames in {raw}')
            last.to_image().save(out / 'last.png')
            last.to_image().save(site / 'last.webp', quality=90)
            row.update(frames=frames, fps=fps, width=last.width, height=last.height,
                       video_seconds=frames / fps, has_audio=bool(container.streams.audio),
                       raw_bytes=raw.stat().st_size)
        metrics = json.loads((out / f'{model}_metrics.json').read_text())
        row.update(peak_allocated_gib=metrics['peak_allocated_gib'],
                   pipeline_seconds=metrics.get('inference_seconds'))
        if 'joy_native_timing' in metrics:
            row.update(joy_native_timing=metrics['joy_native_timing'], condition_seconds=metrics['condition_seconds'])
        if model == 'joy':
            metadata, = (out / 'joy/seed7-quality/joy_character').glob('inference_*/run_metadata.json')
            row['joy_native_timing'] = json.loads(metadata.read_text())['timing']
        prefix = str(site.relative_to(self.site))
        row.update(raw=f'{prefix}/{raw.name}', last=f'{prefix}/last.webp')
        self._playback(site, row)
        row.update(
                   postprocess_seconds=round(perf_counter() - started, 2),
                   cold_rtf=round(row['cold_seconds'] / row['video_seconds'], 2))

    def _playback(self, site: Path, row: dict) -> None:
        target = site / 'play_640_16.mp4'
        with (site / 'playback_640_16.log').open('w') as log:
            subprocess.run([str(self.ffmpeg), '-nostdin', '-n', '-i', str(self.site / row['raw']),
                            '-vf', 'scale=640:352:force_original_aspect_ratio=decrease:force_divisible_by=2,'
                            'pad=640:352:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=16',
                            '-c:v', 'libx264', '-threads', '4', '-crf', '27',
                            '-maxrate', '500k', '-bufsize', '1000k', '-pix_fmt', 'yuv420p',
                            '-c:a', 'aac', '-b:a', '64k', '-movflags', '+faststart', str(target)],
                           stdout=log, stderr=subprocess.STDOUT, check=True)
        row.update(video=str(target.relative_to(self.site)), playback_bytes=target.stat().st_size,
                   playback_width=640, playback_height=352, playback_fps=16)

    def _join(self, model: dict) -> None:
        playlist = self.out / model['id'] / 'concat.txt'
        playlist.write_text(''.join(f"file '{self.site / row['video']}'\n" for row in model['rounds']))
        target = self.site / model['id'] / 'story_640_16.mp4'
        with (playlist.parent / 'concat.log').open('w') as log:
            subprocess.run([str(self.ffmpeg), '-nostdin', '-n', '-f', 'concat', '-safe', '0',
                            '-i', str(playlist), '-c', 'copy', '-movflags', '+faststart', str(target)],
                           stdout=log, stderr=subprocess.STDOUT, check=True)
        model.update(video=str(target.relative_to(self.site)), playback_bytes=target.stat().st_size,
                     cold_seconds=round(sum(row['cold_seconds'] for row in model['rounds']), 2))

    def _publish(self) -> None:
        self.site.mkdir(parents=True, exist_ok=True)
        self.results['updated_at'] = datetime.now(timezone.utc).isoformat()
        pending = self.site / 'results.next.json'
        pending.write_text(json.dumps(self.results, ensure_ascii=False, indent=2) + '\n')
        pending.replace(self.site / 'results.json')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--story', type=Path, required=True)
    parser.add_argument('--site', type=Path, required=True)
    args = parser.parse_args()
    StoryEvaluation(args.story, args.site)()
