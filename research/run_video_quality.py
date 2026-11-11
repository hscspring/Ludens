import argparse
import fcntl
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from time import perf_counter


class EvaluationResults:
    def __init__(self, path: Path) -> None:
        self.path = path

    def update(self, model: str, **changes: object) -> dict:
        with self.path.with_suffix('.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            records = json.loads(self.path.read_text())
            row = next(x for x in records if x['id'] == model)
            row.update(changes)
            pending = self.path.with_suffix('.next.json')
            pending.write_text(json.dumps(records, ensure_ascii=False, indent=2) + '\n')
            pending.replace(self.path)
            return row


parser = argparse.ArgumentParser()
parser.add_argument('models', nargs='+')
parser.add_argument('--host', default='doams-187', choices=['doams-187', 'doams-185', 'am4g1r24bm2'])
parser.add_argument('--out-dir', type=Path)
parser.add_argument('--site', type=Path)
parser.add_argument('--image', type=Path)
parser.add_argument('--prompt-file', type=Path)
parser.add_argument('--width', type=int)
parser.add_argument('--height', type=int)
args = parser.parse_args()
root = Path('/mnt/sv0/sean')
project = root / 'Ludens'
dependencies = project / 'research/out/video_quality_20260922'
out = (args.out_dir or dependencies).resolve()
out.mkdir(parents=True, exist_ok=True)
site = (args.site or project / 'pipeline/tavern/static/video-quality-20260922').resolve()
python = str(root / 'runtimes/cpython-3.11-ludens/bin/python3.11')
results = EvaluationResults(site / 'results.json')
env = os.environ.copy()
gpu = env['CUDA_VISIBLE_DEVICES']
assert gpu.isdigit() and 0 <= int(gpu) < 8, 'Specify one local GPU explicitly'
assert os.uname().nodename == args.host, 'Run on the explicitly selected node'
env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONUNBUFFERED='1', HF_HUB_OFFLINE='1', OMP_NUM_THREADS='8')
cache = str(out / ('cache_' + args.host.replace('-', '')))
Path(cache).mkdir(exist_ok=True)
env.update(XDG_CACHE_HOME=cache, HF_HOME=cache + '/huggingface', CUDA_CACHE_PATH=cache + '/cuda',
           TRITON_CACHE_DIR=cache + '/triton', TORCHINDUCTOR_CACHE_DIR=cache + '/inductor',
           TORCH_HOME=cache + '/torch', NUMBA_CACHE_DIR=cache + '/numba', MPLCONFIGDIR=cache + '/matplotlib')
env['TMPDIR'] = cache

for model in args.models:
    occupants = subprocess.check_output(
        ['nvidia-smi', f'--id={gpu}', '--query-compute-apps=pid', '--format=csv,noheader,nounits'], text=True).strip()
    if occupants:
        results.update(model, status='waiting', note='指定 GPU 已被占用，未启动；等待资源确认')
        print(f'GPU {gpu} is occupied by PID(s) {occupants}; batch did not start the next model.', flush=True)
        sys.exit(75)
    results.update(model, status='running', gpu=int(gpu), node=args.host, note='生成中，尚未验收', wall_seconds=None, exit_code=None)
    backend = 'ludens-flux' if model.startswith('ltx_') or model == 'minimax' else 'ludens-joyai'
    env['PYTHONPATH'] = ':'.join([str(dependencies / 'network-deps'), str(dependencies / 'extras'), str(dependencies.parent / 'character_180_20260922/extras'),
                                str(root / f'envs/{backend}/lib/python3.11/site-packages')])
    if model in {'dreamx', 'matrix', 'wan', 'flashhead', 'liveavatar', 'hallo', 'hallo_t2v', 'lingbot'}:
        env['PYTHONPATH'] = str(dependencies / 'portrait-deps') + ':' + env['PYTHONPATH']
    env['PATH'] = str(dependencies / 'bin') + ':' + os.environ['PATH']
    started = perf_counter()
    with (out / f'{model}_character.log').open('w') as log:
        command = [python, str(project / 'research/video_quality_model.py'), model, '--out-dir', str(out)]
        for flag, value in (('--image', args.image), ('--prompt-file', args.prompt_file)):
            if value is not None:
                command += [flag, str(value.resolve())]
        if args.width is not None and args.height is not None:
            command += ['--width', str(args.width), '--height', str(args.height)]
        result = subprocess.run(command,
                                env=env, stdout=log, stderr=subprocess.STDOUT)
    changes = dict(status='generated' if result.returncode == 0 else 'waiting' if result.returncode == 75 else 'failed',
               wall_seconds=round(perf_counter() - started, 2), exit_code=result.returncode,
               note='原片已生成，待人工验收' if result.returncode == 0 else '指定 GPU 被占用，等待资源确认' if result.returncode == 75 else '运行失败，见日志；不代表画质结论')
    if result.returncode == 0:
        filename = f'{model}_character.mp4'
        shutil.copyfile(out / filename, site / filename)
        changes['video'] = filename
    row = results.update(model, **changes)
    print(f'{model}: {row["status"]} ({row["wall_seconds"]}s)', flush=True)
    if result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, model)
