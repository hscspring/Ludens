#!/usr/bin/env python
# 通用抽帧:读视频 → 均匀抽 N 帧 → 写 PNG 供肉眼判连续性/沉浸感。纯 CPU。
# 用法:CUDA_VISIBLE_DEVICES= python extract_frames.py <video.mp4> [-n 8] [-o out_dir]
import argparse
from pathlib import Path

import imageio.v3 as iio
import numpy as np


def probe(video_path: str, n: int, out_dir: str | None) -> None:
    vid = iio.imread(video_path, plugin="pyav")  # (T, H, W, C)
    t = vid.shape[0]
    out = Path(out_dir) if out_dir else Path(video_path).parent
    out.mkdir(parents=True, exist_ok=True)
    stem = Path(video_path).stem
    idxs = np.linspace(0, t - 1, min(n, t)).astype(int)
    print(f"{video_path}: T={t} shape={tuple(vid.shape)} -> {len(idxs)} probes")
    for i in idxs:
        p = out / f"probe_{stem}_{int(i):04d}.png"
        iio.imwrite(p, vid[int(i)])
        print(" ", p)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("-n", type=int, default=8)
    ap.add_argument("-o", "--out-dir", default=None)
    a = ap.parse_args()
    probe(a.video, a.n, a.out_dir)


if __name__ == "__main__":
    main()
