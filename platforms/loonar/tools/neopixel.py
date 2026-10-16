#!/usr/bin/env python3
"""Pi 5 NeoPixel: 16 RGB LEDs, BCM GPIO22 (physical pin 15), white at 30/255.

Setup on a Pi 5 with RP1 PIO support (/dev/pio0):
  python3 -m venv ~/.venvs/loonar-neopixel
  ~/.venvs/loonar-neopixel/bin/pip install Adafruit-Blinka-Raspberry-Pi5-Neopixel

  python3 neopixel.py --check                 # Diagnose without driving GPIO
  ~/.venvs/loonar-neopixel/bin/python neopixel.py       # Set white; LEDs stay on after exit
  ~/.venvs/loonar-neopixel/bin/python neopixel.py --off # Turn all LEDs off
  ~/.venvs/loonar-neopixel/bin/python neopixel.py --hold # Stay running; Ctrl+C turns off

Driver: https://github.com/adafruit/Adafruit_Blinka_Raspberry_Pi5_Neopixel
Brightness is a byte value (30/255), NOT 30 percent. RGB WS2812/NeoPixel,
800 kHz, GRB order by default. This does not use software GPIO bit-banging.
"""
import argparse
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import platform
import signal
import sys
import time
from types import SimpleNamespace

# Standard Raspberry Pi 40-pin header, BCM numbers -> physical pin numbers.
HEADER_PINS = {0:27, 1:28, 2:3, 3:5, 4:7, 5:29, 6:31, 7:26, 8:24,
               9:21, 10:19, 11:23, 12:32, 13:33, 14:8, 15:10, 16:36,
               17:11, 18:12, 19:35, 20:38, 21:40, 22:15, 23:16,
               24:18, 25:22, 26:37, 27:13}


class Pixels:
    """Single GPIO owner shared by manual diagnostics and the mode LED service."""
    def __init__(self, gpio=22, count=16, brightness=30, order='GRB'):
        folder = Path.home()/'.cache/loonar-neopixel'
        folder.mkdir(parents=True, exist_ok=True)
        self.lock = (folder/f'gpio{gpio}.lock').open('a')
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            from adafruit_raspberry_pi5_neopixel_write import neopixel_write, free_pio
        except BlockingIOError:
            self.lock.close()
            raise RuntimeError('GPIO is owned by the mode LED service or another LED process; '
                               'stop loonar-mode-led.service before manual LED control') from None
        except BaseException:
            self.lock.close()
            raise
        self.transmit, self.release = neopixel_write, free_pio
        self.pin = SimpleNamespace(id=gpio)
        self.count, self.brightness, self.order = count, brightness, order

    def write(self, rgb):
        self.write_frame([rgb]*self.count)

    def write_frame(self, colors):
        if len(colors) != self.count:
            raise ValueError('LED frame length differs from configured count')
        data = bytearray()
        for rgb in colors:
            scaled = dict(zip('RGB', ((v*self.brightness+127)//255 for v in rgb)))
            data.extend(scaled[c] for c in self.order)
        self.transmit(self.pin, data)
        time.sleep(.01)

    def close(self):
        try:
            self.release()
        finally:
            self.lock.close()


def byte(value):
    number = int(value)
    if not 0 <= number <= 255:
        raise argparse.ArgumentTypeError('must be 0..255')
    return number


def diagnostics():
    model = Path('/proc/device-tree/model')
    model_name = model.read_text().rstrip('\x00') if model.exists() else 'not a Raspberry Pi'
    errors = []
    if 'Raspberry Pi 5' not in model_name and 'Raspberry Pi 500' not in model_name:
        errors.append('This driver is for Raspberry Pi 5 / RP1 hardware.')
    pio = Path('/dev/pio0')
    if not pio.exists():
        errors.append('/dev/pio0 is missing: this Pi needs a kernel/firmware with RP1 PIO support. '
                      'Installing Python packages or running sudo alone will not add PIO support. '
                      'No kernel/firmware update or reboot is performed by this script.')
    elif not os.access(pio, os.R_OK | os.W_OK):
        errors.append('No read/write access to /dev/pio0: check its gpio-group/udev permissions.')
    for module, package in [('adafruit_raspberry_pi5_neopixel_write', 'Adafruit-Blinka-Raspberry-Pi5-Neopixel')]:
        if importlib.util.find_spec(module) is None:
            errors.append(f'Missing {package}; install it in the Python environment used to run this script.')
    return dict(model=model_name, kernel=platform.release(), python=sys.executable,
                pio_device=str(pio), errors=errors)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--gpio', type=int, choices=sorted(HEADER_PINS), default=22,
                        help='BCM GPIO number, not physical pin number (default: 22 = pin 15)')
    parser.add_argument('--count', type=int, default=16)
    parser.add_argument('--brightness', type=byte, default=30, help='0..255, default 30')
    parser.add_argument('--rgb', type=byte, nargs=3, default=(255,255,255), metavar=('R','G','B'))
    parser.add_argument('--order', choices=['GRB','RGB','RBG','GBR','BRG','BGR'], default='GRB')
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--off', action='store_true', help='Send black to every LED and exit')
    action.add_argument('--hold', action='store_true', help='Keep process running; clear LEDs on Ctrl+C/SIGTERM')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--check', action='store_true', help='Check platform/PIO/libraries; no GPIO output')
    mode.add_argument('--dry-run', action='store_true', help='Show settings and wire bytes; no hardware imports')
    args = parser.parse_args(argv)
    if not 1 <= args.count <= 4096:
        parser.error('--count must be 1..4096')
    scaled = (0,0,0) if args.off else tuple((value*args.brightness+127)//255 for value in args.rgb)
    channels = dict(zip('RGB', scaled))
    payload = bytearray(channels[c] for _ in range(args.count) for c in args.order)
    settings = dict(gpio_bcm=args.gpio, physical_pin=HEADER_PINS[args.gpio], count=args.count,
                    brightness_255=args.brightness, scaled_rgb=scaled, order=args.order,
                    wire_bytes=len(payload), off=args.off, hold=args.hold)
    if args.dry_run:
        print(json.dumps(settings, indent=2))
        return 0
    venv = Path.home()/'.venvs/loonar-neopixel'
    if (importlib.util.find_spec('adafruit_raspberry_pi5_neopixel_write') is None
            and sys.prefix != str(venv) and (venv/'bin/python').is_file()):
        # Keep `python3 neopixel.py` usable after the isolated dependency setup.
        os.execv(str(venv/'bin/python'), [str(venv/'bin/python'), str(Path(__file__).resolve()),
                                       *(sys.argv[1:] if argv is None else argv)])
    info = diagnostics()
    if args.check:
        print(json.dumps(dict(settings=settings, **info), indent=2))
        return int(bool(info['errors']))
    if info['errors']:
        for error in info['errors']:
            print(error, file=sys.stderr)
        return 1
    pixels = Pixels(args.gpio, args.count, args.brightness, args.order)

    old_handlers = {}
    def interrupted(*_):
        raise KeyboardInterrupt
    try:
        if args.hold:
            for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
                old_handlers[sig] = signal.signal(sig, interrupted)
        pixels.write((0,0,0) if args.off else args.rgb)
        print(f"{args.count} LEDs {'OFF' if args.off else 'ON'} | BCM GPIO{args.gpio} "
              f"(physical pin {HEADER_PINS[args.gpio]}) | RGB={scaled} | brightness={args.brightness}/255",
              flush=True)
        if args.hold:
            print('Ctrl+C to turn off and exit.', flush=True)
            while True:
                signal.pause()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            if args.hold:
                for sig in old_handlers:
                    signal.signal(sig, signal.SIG_IGN)
                try:
                    pixels.write((0,0,0))
                finally:
                    for sig, handler in old_handlers.items():
                        signal.signal(sig, handler)
        finally:
            pixels.close()
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ImportError) as exc:
        print(f'NeoPixel error: {exc}', file=sys.stderr)
        raise SystemExit(1)
