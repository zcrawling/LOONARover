#!/usr/bin/env python3
"""Mission-controlled USB payload logger for the PCA trial firmware."""

import argparse
import os
import selectors
import shlex
import socket
import struct
import subprocess
import termios
import time
from pathlib import Path

COMMAND = struct.Struct("<QHH")
START, STOP = 1, 2


class Service:
    def __init__(self, socket_path, device, log_dir, power_on, power_off):
        self.socket_path = Path(socket_path)
        self.device = device
        self.log_dir = Path(log_dir)
        self.power_on = power_on
        self.power_off = power_off
        self.listener = None
        self.clients = set()
        self.serial_fd = None
        self.log_file = None
        self.selector = selectors.DefaultSelector()
        self.request_id = 0
        self.serial_buffer = bytearray()
        self.running = False

    def broadcast(self, text):
        payload = text.encode("utf-8")[:127]
        dead = []
        for client in self.clients:
            try:
                client.send(payload)
            except OSError:
                dead.append(client)
        for client in dead:
            self.drop(client)

    def drop(self, client):
        try:
            self.selector.unregister(client)
        except Exception:
            pass
        self.clients.discard(client)
        client.close()

    @staticmethod
    def run_power(command):
        if not command:
            raise RuntimeError("physical power command is not configured")
        subprocess.run(shlex.split(command), check=True, timeout=15)

    def open_serial(self):
        deadline = time.monotonic() + 15
        while True:
            try:
                fd = os.open(self.device, os.O_RDONLY | os.O_NONBLOCK | os.O_NOCTTY)
                break
            except FileNotFoundError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.25)
        attrs = termios.tcgetattr(fd)
        attrs[0] = attrs[0] & ~(termios.IGNBRK | termios.BRKINT | termios.PARMRK | termios.ISTRIP | termios.INLCR | termios.IGNCR | termios.ICRNL | termios.IXON)
        attrs[1] = attrs[1] & ~termios.OPOST
        attrs[2] = attrs[2] & ~(termios.CSIZE | termios.PARENB)
        attrs[2] = attrs[2] | termios.CS8 | termios.CLOCAL | termios.CREAD
        attrs[3] = attrs[3] & ~(termios.ECHO | termios.ECHONL | termios.ICANON | termios.ISIG | termios.IEXTEN)
        attrs[4] = termios.B115200
        attrs[5] = termios.B115200
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
        self.serial_fd = fd
        self.selector.register(fd, selectors.EVENT_READ, "serial")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        path = self.log_dir / time.strftime("payload-pca-%Y%m%d-%H%M%S.csv", time.gmtime())
        self.log_file = path.open("a", encoding="utf-8", newline="")

    def start(self, request_id):
        if self.serial_fd is not None:
            self.broadcast(f"STATE,{request_id},RUNNING,already_started")
            return
        try:
            self.run_power(self.power_on)
            self.open_serial()
            self.request_id = request_id
            self.running = True
            self.broadcast(f"STATE,{request_id},RUNNING,power_on")
        except Exception as exc:
            try:
                self.run_power(self.power_off)
            except Exception:
                pass
            self.running = False
            self.broadcast(f"ERROR,{request_id},START,{type(exc).__name__}:{exc}")

    def stop(self, request_id):
        if self.serial_fd is not None:
            self.selector.unregister(self.serial_fd)
            os.close(self.serial_fd)
            self.serial_fd = None
        self.serial_buffer.clear()
        if self.log_file:
            self.log_file.close()
            self.log_file = None
        self.running = False
        self.request_id = request_id
        try:
            self.run_power(self.power_off)
            self.broadcast(f"STATE,{request_id},IDLE,power_off")
        except Exception as exc:
            self.broadcast(f"ERROR,{request_id},STOP,{type(exc).__name__}:{exc}")

    def client_event(self, client):
        data = client.recv(256)
        if not data:
            self.drop(client)
            return
        if len(data) < COMMAND.size:
            self.broadcast("ERROR,0,COMMAND,bad_length")
            return
        request_id, opcode, parameter_length = COMMAND.unpack_from(data)
        if len(data) != COMMAND.size + parameter_length:
            self.broadcast(f"ERROR,{request_id},COMMAND,bad_parameters")
        elif opcode == START:
            self.start(request_id)
        elif opcode == STOP:
            self.stop(request_id)
        else:
            self.broadcast(f"ERROR,{request_id},COMMAND,unknown_opcode_{opcode}")

    def serial_event(self):
        data = os.read(self.serial_fd, 4096)
        if not data:
            return
        self.serial_buffer.extend(data)
        while b"\n" in self.serial_buffer:
            raw, _, remainder = self.serial_buffer.partition(b"\n")
            self.serial_buffer = bytearray(remainder)
            line = raw.rstrip(b"\r").decode("ascii", "replace")
            if self.log_file:
                self.log_file.write(line + "\n")
                self.log_file.flush()
            if line.startswith("PCA,"):
                fields = line.split(",")
                if len(fields) == 17:
                    # Fit the existing bounded GroundLink EVENT text field.
                    self.broadcast(",".join(("PCA", fields[2], fields[8],
                                             fields[9], fields[10], fields[11],
                                             fields[12], fields[14], fields[15],
                                             fields[16], fields[1])))
                else:
                    self.broadcast("ERROR,0,PCA,bad_field_count")

    def run(self):
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.socket_path.unlink()
        except FileNotFoundError:
            pass
        self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        self.listener.bind(str(self.socket_path))
        os.chmod(self.socket_path, 0o660)
        self.listener.listen(4)
        self.listener.setblocking(False)
        self.selector.register(self.listener, selectors.EVENT_READ, "listen")
        try:
            while True:
                for key, _ in self.selector.select():
                    if key.data == "listen":
                        client, _ = self.listener.accept()
                        client.setblocking(False)
                        self.clients.add(client)
                        self.selector.register(client, selectors.EVENT_READ, "client")
                        client.send(f"STATE,{self.request_id},{'RUNNING' if self.running else 'IDLE'},connected".encode())
                    elif key.data == "client":
                        self.client_event(key.fileobj)
                    else:
                        self.serial_event()
        finally:
            if self.serial_fd is not None:
                self.stop(0)
            for client in list(self.clients):
                self.drop(client)
            self.listener.close()
            self.socket_path.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--socket", default=os.getenv("PAYLOAD_PCA_SOCKET", "/run/loonar/payload-pca.sock"))
    parser.add_argument("--device", default=os.getenv("PAYLOAD_DEVICE"), required=os.getenv("PAYLOAD_DEVICE") is None)
    parser.add_argument("--log-dir", default=os.getenv("PAYLOAD_LOG_DIR", "/var/lib/loonar/payload"))
    args = parser.parse_args()
    Service(args.socket, args.device, args.log_dir, os.getenv("PAYLOAD_POWER_ON_COMMAND", ""), os.getenv("PAYLOAD_POWER_OFF_COMMAND", "")).run()


if __name__ == "__main__":
    main()
