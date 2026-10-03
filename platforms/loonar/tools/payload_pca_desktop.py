#!/usr/bin/env python3
"""Windows USB bench UI using the production payload service state machine."""
import argparse
import time
from pathlib import Path
import tkinter as tk
from tkinter.scrolledtext import ScrolledText

from payload_pca_service import Service, COMMAND, START, STOP


class DesktopService(Service):
    def __init__(self, device, log_dir, emit):
        super().__init__("unused", device, log_dir)
        self.emit = emit
        self.port = None

    def broadcast(self, text):
        self.emit(text)

    def open_serial(self):
        import serial
        self.port = serial.Serial(self.device, 115200, timeout=0, write_timeout=1)
        self.serial_fd = self.port
        self.port.reset_input_buffer()

    def close_serial(self):
        self.port.close()
        self.port = None
        self.serial_fd = None

    def send_serial(self, command):
        data = (command + "\n").encode("ascii")
        if self.port.write(data) != len(data):
            raise OSError("short USB command write")

    def read_serial(self):
        return self.port.read(4096)

    def poll(self):
        if self.port is not None:
            try:
                if self.port.in_waiting:
                    self.serial_event()
            except OSError as exc:
                self.disconnect("read_failed")
        self.check_deadline()


class CommandPacket:
    """Feed the same <QHH command payload used by GCS into client_event."""
    def __init__(self, request_id, opcode):
        self.data = COMMAND.pack(request_id, opcode, 0)

    def recv(self, size):
        return self.data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", required=True, help="USB serial port, e.g. COM5")
    parser.add_argument("--log-dir", default="platforms/loonar/firmware/payload/logs/desktop")
    args = parser.parse_args()
    root = tk.Tk()
    root.title(f"Payload START / STOP — {args.device}")
    status = tk.StringVar(value="IDLE")
    tk.Label(root, textvariable=status).pack(padx=12, pady=8)
    output = ScrolledText(root, width=100, height=20, state="disabled")
    output.pack(padx=12, pady=8)

    def emit(text):
        output.configure(state="normal")
        output.insert("end", text + "\n")
        output.see("end")
        output.configure(state="disabled")
        if text.startswith("STATE,"):
            status.set(text)

    service = DesktopService(args.device, Path(args.log_dir), emit)
    request_id = 0

    def command(opcode):
        nonlocal request_id
        request_id += 1
        service.client_event(CommandPacket(request_id, opcode))

    buttons = tk.Frame(root)
    buttons.pack(pady=8)
    tk.Button(buttons, text="START", command=lambda: command(START)).pack(side="left", padx=10)
    tk.Button(buttons, text="STOP", command=lambda: command(STOP)).pack(side="left", padx=10)

    def poll():
        service.poll()
        root.after(50, poll)

    close_deadline = [None]

    def close():
        close_deadline[0] = time.monotonic() + 22
        if service.serial_fd is not None:
            command(STOP)
            # Keep polling until STOP/PCA completes or the shared timeout fires.
            root.after(100, finish_close)
        else:
            root.destroy()

    def finish_close():
        if (not service.pending and not service.running) or time.monotonic() >= close_deadline[0]:
            service.close_capture()
            service.close_serial()
            root.destroy()
        else:
            if service.running and not any(item[1] == "STOP" for item in service.pending.values()):
                command(STOP)
            root.after(100, finish_close)

    root.protocol("WM_DELETE_WINDOW", close)
    poll()
    root.mainloop()


if __name__ == "__main__":
    main()
