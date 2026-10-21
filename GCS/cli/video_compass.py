"""Camera player with moving relative compass labels OUTSIDE the video rectangle."""
import argparse
from collections import deque
import math
import signal
import subprocess
import sys
import threading
import time
import tkinter as tk

from PIL import Image, ImageTk
from cli.common import request
from cli.compass import Heading, border_positions
from cli.vision_overlay import VisionCache, canvas_box
from cli.local_vision import LocalVision


def read_ppm(stream):
    """Read one FFmpeg P6 frame; EOF returns None, without partial images."""
    magic = stream.readline()
    if not magic:
        return None
    if magic.strip() != b'P6':
        raise ValueError('Expected an FFmpeg RGB frame')
    width, height = map(int, stream.readline().split())
    if stream.readline().strip() != b'255' or not (0 < width <= 960 and 0 < height <= 720):
        raise ValueError('Invalid video frame dimensions')
    size = width * height * 3
    data = bytearray()
    while len(data) < size:
        chunk = stream.read(size-len(data))
        if not chunk:
            return None
        data.extend(chunk)
    return Image.frombytes('RGB', (width, height), bytes(data))


def orient_frame(frame, flipped):
    return frame.transpose(Image.Transpose.ROTATE_180) if flipped else frame


class Player:
    BORDER = 48

    def __init__(self, root, rotate_left=False):
        self.root = root
        root.title('LOONAR · Camera / Relative compass')
        root.geometry('1056x760')
        root.minsize(360, 300)
        self.canvas = tk.Canvas(root, background='#161616', highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        bar = tk.Frame(root, background='#262626')
        bar.pack(fill=tk.X)
        self.status = tk.Label(bar, text='Waiting for video and IMU', background='#262626',
                               foreground='#c6c6c6', anchor='w', padx=12, pady=8)
        self.status.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(bar, text='Set start=N (R)', command=self.reset_reference,
                  background='#393939', foreground='#f4f4f4', relief=tk.FLAT).pack(side=tk.RIGHT)
        self.heading = Heading()
        self.samples = deque(maxlen=1)
        self.frames = deque(maxlen=1)
        self.vision = VisionCache()
        self.detector = LocalVision(self.vision)
        self.detector.start()
        self.frame = self.photo = None
        self.last_size = None
        self.flipped = False
        self.last_flip = None
        self.stop = threading.Event()
        self.video_done = threading.Event()
        filters = (['transpose=cclock'] if rotate_left else []) + [
            "scale='min(iw,960)':'min(ih,720)':force_original_aspect_ratio=decrease"]
        self.decoder = subprocess.Popen([
            'ffmpeg', '-hide_banner', '-loglevel', 'warning', '-nostdin',
            '-flags', 'low_delay', '-threads', '2', '-filter_threads', '1',
            '-probesize', '32768', '-analyzeduration', '100000', '-i', 'pipe:0',
            '-an', '-vf', ','.join(filters), '-fpsmax', '30', '-f', 'image2pipe',
            '-c:v', 'ppm', 'pipe:1'], stdin=sys.stdin.buffer, stdout=subprocess.PIPE)
        self.video_thread = threading.Thread(target=self.receive_video, daemon=True)
        self.video_thread.start()
        threading.Thread(target=self.receive_imu, daemon=True).start()
        root.protocol('WM_DELETE_WINDOW', root.quit)
        root.bind('<Key-r>', lambda _: self.reset_reference())
        root.bind('<Key-R>', lambda _: self.reset_reference())
        root.after(30, self.draw)

    def reset_reference(self):
        self.heading.reference = None

    def receive_video(self):
        try:
            while not self.stop.is_set():
                frame = read_ppm(self.decoder.stdout)
                if frame is None:
                    break
                self.frames.append(frame)
                flipped = self.flipped
                self.detector.submit(orient_frame(frame, flipped), flipped=flipped)
        except (OSError, ValueError) as error:
            print(f'Video decode: {error}', file=sys.stderr)
        finally:
            self.video_done.set()

    def receive_imu(self):
        while not self.stop.is_set():
            try:
                state = request({'action': 'state'}, timeout=0.3)
            except (OSError, ValueError):
                state = {}
            if type(state.get('flipped')) is bool:
                self.flipped = state['flipped']
            self.samples.append((time.monotonic(), state))
            self.stop.wait(0.05)

    def draw(self):
        if self.video_done.is_set():
            self.root.quit()
            return
        width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
        flipped = self.flipped
        new_frame = bool(self.frames)
        if new_frame:
            self.frame = self.frames.pop()
        box = (self.BORDER, self.BORDER, width-self.BORDER, height-self.BORDER)
        if self.frame is not None:
            scale = min(max(1, width-2*self.BORDER)/self.frame.width,
                        max(1, height-2*self.BORDER)/self.frame.height)
            size = (max(1, round(self.frame.width*scale)), max(1, round(self.frame.height*scale)))
            x, y = (width-size[0])/2, (height-size[1])/2
            box = (x, y, x+size[0], y+size[1])
            if new_frame or size != self.last_size or flipped != self.last_flip:
                display_frame = orient_frame(self.frame, flipped)
                self.photo = ImageTk.PhotoImage(display_frame.resize(size, Image.Resampling.BILINEAR))
                self.last_size = size
                self.last_flip = flipped
            self.canvas.delete('video')
            self.canvas.create_image(x, y, image=self.photo, anchor='nw', tags='video')
        self.canvas.delete('compass')
        self.canvas.delete('vision')
        snapshot = self.vision.snapshot()
        if snapshot is not None and snapshot[0].get('flipped', False) != flipped:
            snapshot = None  # Never overlay boxes inferred in the old orientation.
        vision_text = self.detector.status
        if snapshot is not None:
            result, age_ms = snapshot
            mode = '목표 모델' if result.get('model_mode') == 'MISSION' else '범용 모델 데모'
            if result['state'] in ('DETECTED', 'NOT_DETECTED'):
                if self.frame is not None and (result['width'], result['height']) == self.frame.size:
                    for detection in result['detections']:
                        color = '#59ef9b' if detection['class_name'] == 'target_rover' else '#ffb454'
                        coordinates = canvas_box(detection['xyxy'], result['width'],
                                                 result['height'], box)
                        self.canvas.create_rectangle(*coordinates, outline=color, width=2, tags='vision')
                        self.canvas.create_text(coordinates[0], coordinates[1],
                            text=f"{detection['class_name']} {detection['confidence']:.2f}",
                            anchor='sw', fill=color, tags='vision')
                    labels = {'LEFT': '좌', 'CENTER': '중앙', 'RIGHT': '우'}
                    vision_text = (f"PC 인식 · {mode} · 목표: {labels.get(result['direction'], '미검출')} · "
                                   f"결과 나이 {age_ms:.0f}ms")
                else:
                    vision_text = 'PC 인식 영상 크기 불일치'
            elif result['state'] == 'MODEL_UNAVAILABLE':
                vision_text = 'PC 인식 모델 사용 불가'
        self.canvas.create_rectangle(*box, outline='#525252', width=1, tags='compass')
        sample = self.samples[-1] if self.samples else None
        yaw = self.heading.update(sample[1]) if sample and time.monotonic()-sample[0] < 0.5 else None
        if yaw is None:
            compass_text = 'Relative compass · IMU unavailable / waiting'
        else:
            for name, position in border_positions(yaw, box).items():
                self.canvas.create_text(*position, text=name, font=('DejaVu Sans', 18, 'bold'),
                                        fill='#78a9ff' if name == 'N' else '#f4f4f4', tags='compass')
            heading = (-math.degrees(yaw)) % 360
            compass_text = f'Start=N · Gyro relative · {heading:05.1f}°'
        orientation = 'FLIP ON · 뒤집힘 보정' if flipped else 'FLIP OFF · 정상 방향'
        self.status.config(text=f'{orientation}  |  {compass_text}  |  {vision_text}')
        self.root.after(30, self.draw)

    def close(self):
        self.stop.set()
        if self.decoder.poll() is None:
            self.decoder.terminate()
            try:
                self.decoder.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.decoder.kill()
                self.decoder.wait()
        self.video_thread.join(timeout=1)
        self.detector.close()
        self.decoder.stdout.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rotate-left', action='store_true')
    args = parser.parse_args()
    root = tk.Tk()
    player = Player(root, args.rotate_left)
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, lambda *_: root.quit())
    try:
        root.mainloop()
    finally:
        player.close()
        root.destroy()


if __name__ == '__main__':
    main()
