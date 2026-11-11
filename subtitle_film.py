"""把 aim 的 beats 台词烧成字幕、并把多片拼成一支样片。纯 PyAV+Pillow,不依赖系统 ffmpeg。

SubtitleBurner —— 单片:逐帧在底部画 `Who: line`(shot 内按 beat 均分时间),音频原样 remux 保真。
FilmStitcher   —— 多片:规格一致,直接 stream-copy 首尾相接(累加 pts 偏移;不重编码、不掉画质)。
main 读 aim_data_sample.json 的 beats + JoyAI 出的 result.mp4,先逐片烧字幕,再拼成一支片。
"""
from __future__ import annotations

import glob
import json
import os
import textwrap

import av
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.join(HERE, "research", "aim_data_sample.json")
JOYAI_OUT = os.path.join(HERE, "research", "smoke_out", "joyai", "ludens-denji-demo")
OUT_DIR = os.path.join(HERE, "research", "out")
SUBBED_DIR = os.path.join(OUT_DIR, "subbed")
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


class SubtitleBurner:
    def __init__(self, font_size: int = 34, margin: int = 40, wrap: int = 52, crf: str = "18"):
        self.font = ImageFont.truetype(FONT, font_size)
        self.lh = font_size + 8
        self.margin = margin
        self.wrap = wrap
        self.crf = crf

    def burn(self, mp4_in: str, beats: list[dict], mp4_out: str) -> int:
        inp = av.open(mp4_in)
        vin = inp.streams.video[0]
        ain = inp.streams.audio[0]
        total = vin.frames or self._count(mp4_in)
        caps = self._caps(beats, total)

        out = av.open(mp4_out, "w")
        vout = out.add_stream("libx264", rate=vin.average_rate)
        vout.width, vout.height, vout.pix_fmt = vin.width, vin.height, "yuv420p"
        vout.options = {"crf": self.crf}
        aout = out.add_stream_from_template(ain)  # 音频原样 remux,不重编码

        i = 0
        for packet in inp.demux(vin, ain):  # 音视频按原交错顺序过,dts 保持单调
            if packet.dts is None:
                continue
            if packet.stream.type == "video":
                for frame in packet.decode():
                    img = frame.to_image()
                    if cap := caps[min(i, total - 1)]:
                        self._draw(img, cap)
                    for pkt in vout.encode(av.VideoFrame.from_image(img)):
                        out.mux(pkt)
                    i += 1
            else:
                packet.stream = aout
                out.mux(packet)
        for pkt in vout.encode():
            out.mux(pkt)
        inp.close()
        out.close()
        return i

    def _count(self, mp4_in: str) -> int:
        tmp = av.open(mp4_in)
        n = sum(1 for p in tmp.demux(tmp.streams.video[0]) if p.pts is not None)
        tmp.close()
        return n

    def _caps(self, beats: list[dict], total: int) -> list[str | None]:
        caps: list[str | None] = [None] * total
        n = len(beats)
        for i, b in enumerate(beats):
            text = f'{b["who"]}: {b["line"]}'
            for f in range(i * total // n, (i + 1) * total // n):
                caps[f] = text
        return caps

    def _draw(self, img: Image.Image, text: str) -> None:
        draw = ImageDraw.Draw(img, "RGBA")
        w_img, h_img = img.size
        lines = textwrap.wrap(text, self.wrap)
        box_h = self.lh * len(lines) + 24
        y0 = h_img - box_h - self.margin
        draw.rectangle([0, y0, w_img, y0 + box_h], fill=(0, 0, 0, 140))
        y = y0 + 12
        for ln in lines:
            x = (w_img - draw.textlength(ln, font=self.font)) / 2
            for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2)):  # 描边
                draw.text((x + dx, y + dy), ln, font=self.font, fill=(0, 0, 0, 255))
            draw.text((x, y), ln, font=self.font, fill=(255, 255, 255, 255))
            y += self.lh


class FilmStitcher:
    """三片规格一致,直接 stream-copy 首尾相接:不重编码(不掉画质、快),按累积 pts 偏移拼接。"""

    def stitch(self, mp4s: list[str], out_path: str) -> None:
        out = av.open(out_path, "w")
        vout = aout = None
        v_off = a_off = 0  # 下一片相对整片起点的偏移(各自 time_base 单位)
        for mp4 in mp4s:
            inp = av.open(mp4)
            vin, ain = inp.streams.video[0], inp.streams.audio[0]
            if vout is None:
                vout = out.add_stream_from_template(vin)
                aout = out.add_stream_from_template(ain)
            v_end = a_end = 0
            for pkt in inp.demux(vin, ain):  # 按原交错顺序搬包,dts 单调
                if pkt.dts is None:
                    continue
                dur = pkt.duration or 0
                if pkt.stream.type == "video":
                    pkt.pts += v_off; pkt.dts += v_off; pkt.stream = vout
                    v_end = max(v_end, pkt.pts + dur)
                else:
                    pkt.pts += a_off; pkt.dts += a_off; pkt.stream = aout
                    a_end = max(a_end, pkt.pts + dur)
                out.mux(pkt)
            inp.close()
            v_off, a_off = v_end, a_end
        out.close()


def _mp4(index: int) -> str:
    hits = sorted(glob.glob(os.path.join(JOYAI_OUT, f"shot_{index:03d}", "inference_*", "result.mp4")))
    if not hits:
        raise FileNotFoundError(f"no result.mp4 for shot {index}")
    return hits[-1]  # 取最新一次推理


def _beats(shot: dict) -> list[dict]:
    return next(t["content"]["beats"] for t in shot["turns"] if t["role"] == "assistant")


def main():
    data = json.load(open(SAMPLE))
    os.makedirs(SUBBED_DIR, exist_ok=True)
    burner = SubtitleBurner()

    subbed = []
    for shot in data["shots"]:
        dst = os.path.join(SUBBED_DIR, f"shot_{shot['index']:03d}.mp4")
        n = burner.burn(_mp4(shot["index"]), _beats(shot), dst)
        print(f"[shot {shot['index']}] burned {n} frames -> {dst}")
        subbed.append(dst)

    film = os.path.join(OUT_DIR, "ludens_denji_film.mp4")
    FilmStitcher().stitch(subbed, film)
    print(f"film -> {film}")


if __name__ == "__main__":
    main()
