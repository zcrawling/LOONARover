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
        self.frame = self.photo = None
        self.last_size = None
        self.stop = threading.Event()
        self.video_done = threading.Event()
        filters = (['transpose=cclock'] if rotate_left else []) + [
            'scale=960:720:force_original_aspect_ratio=decrease']
        self.decoder = subprocess.Popen([
            'ffmpeg', '-hide_banner', '-loglevel', 'warning', '-nostdin',
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
            self.samples.append((time.monotonic(), state))
            self.stop.wait(0.05)

    def draw(self):
        if self.video_done.is_set():
            self.root.quit()
            return
        width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
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
            if new_frame or size != self.last_size:
                self.photo = ImageTk.PhotoImage(self.frame.resize(size, Image.Resampling.BILINEAR))
                self.last_size = size
            self.canvas.delete('video')
            self.canvas.create_image(x, y, image=self.photo, anchor='nw', tags='video')
        self.canvas.delete('compass')
        self.canvas.create_rectangle(*box, outline='#525252', width=1, tags='compass')
        sample = self.samples[-1] if self.samples else None
        yaw = self.heading.update(sample[1]) if sample and time.monotonic()-sample[0] < 0.5 else None
        if yaw is None:
            self.status.config(text='Relative compass · IMU unavailable / waiting')
        else:
            for name, position in border_positions(yaw, box).items():
                self.canvas.create_text(*position, text=name, font=('DejaVu Sans', 18, 'bold'),
                                        fill='#78a9ff' if name == 'N' else '#f4f4f4', tags='compass')
            heading = (-math.degrees(yaw)) % 360
            self.status.config(text=f'Start=N · Gyro relative · {heading:05.1f}°')
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
