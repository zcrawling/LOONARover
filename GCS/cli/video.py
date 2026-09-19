"""Independent GStreamer receiver; never uses the rover TCP connection."""
import argparse
import os
import shutil
import subprocess
from backend.config import DEFAULT_CONFIG, ROOT, load


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--config', default=str(DEFAULT_CONFIG))
    p.add_argument('--check', action='store_true', help='Check GStreamer elements without opening video')
    args = p.parse_args()
    config = load(args.config)
    runtime = ROOT / '.runtime'
    runtime.mkdir(exist_ok=True)
    env = dict(os.environ, GST_REGISTRY=str(runtime / 'gstreamer-registry.bin'), XDG_CACHE_HOME=str(runtime))
    for executable in ('gst-launch-1.0', 'gst-inspect-1.0'):
        if not shutil.which(executable):
            p.exit(1, f'{executable}가 없습니다. docs/run-guide.md의 패키지를 확인하세요.\n')
    for element in ('udpsrc', 'tsdemux', 'h264parse', 'avdec_h264', 'videoconvert', 'autovideosink'):
        result = subprocess.run(['gst-inspect-1.0', element], env=env, capture_output=True)
        if result.returncode:
            p.exit(1, f'GStreamer element 누락: {element}\n')
    if args.check:
        print('GStreamer 수신 요소 6개 확인 완료 (실제 영상 수신은 별도 시험 필요)')
        return
    port = config['video']['port']
    print(f'GStreamer UDP {port} → MPEG-TS → H.264 디코딩 → 영상 창', flush=True)
    cmd = ['gst-launch-1.0', '-v', 'udpsrc', f'port={port}',
           'caps=video/mpegts,systemstream=(boolean)true,packetsize=(int)188',
           '!', 'tsdemux', '!', 'h264parse', '!', 'avdec_h264', '!', 'videoconvert',
           '!', 'autovideosink', 'sync=false']
    process = subprocess.Popen(cmd, env=env)
    try:
        code = process.wait()
    except KeyboardInterrupt:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        return
    if code:
        p.exit(code, 'GStreamer가 오류로 종료되었습니다.\n')


if __name__ == '__main__':
    main()
