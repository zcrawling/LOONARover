#!/usr/bin/env python3
"""Ground-station-controlled, one-PCA-result-per-stop USB payload logger."""

import argparse
import os
import selectors
import socket
import struct
import termios
import time
from pathlib import Path

COMMAND = struct.Struct("<QHH")
START, STOP = 1, 2


class Service:
    def __init__(self, socket_path, device, log_dir):
        self.socket_path = Path(socket_path)
        self.device = device
        self.log_dir = Path(log_dir)
        self.listener = None
        self.clients = set()
        self.serial_fd = None
        self.log_file = None
        self.selector = selectors.DefaultSelector()
        self.request_id = 0
        self.serial_buffer = bytearray()
        self.running = False
        self.starting_request = None
        self.stopping_request = None
        self.active_station = None
        self.pca_received = False
        self.command_deadline = None

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

    def open_serial(self):
        deadline = time.monotonic() + 15
        while True:
            try:
                fd = os.open(self.device, os.O_RDWR | os.O_NONBLOCK | os.O_NOCTTY)
                break
            except FileNotFoundError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.25)
        try:
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
        except Exception:
            if self.serial_fd is None:
                os.close(fd)
            raise

    def close_capture(self):
        if self.serial_fd is not None:
            self.selector.unregister(self.serial_fd)
            os.close(self.serial_fd)
            self.serial_fd = None
        self.serial_buffer.clear()
        if self.log_file:
            self.log_file.close()
            self.log_file = None
        self.running = False
        self.starting_request = None
        self.stopping_request = None
        self.active_station = None
        self.command_deadline = None

    def send_serial(self, command):
        data = (command + "\n").encode("ascii")
        if os.write(self.serial_fd, data) != len(data):
            raise OSError("short USB command write")

    def fail_capture(self, request_id, detail):
        self.close_capture()
        self.request_id = request_id
        self.broadcast(f"ERROR,{request_id},STATION,{detail}")
        self.broadcast(f"STATE,{request_id},ERROR,{detail}")

    def start(self, request_id):
        if self.serial_fd is not None:
            self.broadcast(f"ERROR,{request_id},START,already_started")
            return
        try:
            self.open_serial()
            self.request_id = request_id
            self.starting_request = request_id
            self.command_deadline = time.monotonic() + 20
            self.send_serial("START")
            self.broadcast(f"STATE,{request_id},STARTING,reinitializing")
        except Exception as exc:
            self.fail_capture(request_id, f"START:{type(exc).__name__}:{exc}")

    def stop(self, request_id):
        if self.serial_fd is None:
            self.broadcast(f"STATE,{request_id},IDLE,already_stopped")
            return
        if self.starting_request is not None or self.stopping_request is not None:
            self.broadcast(f"ERROR,{request_id},STOP,station_busy")
            return
        self.stopping_request = request_id
        self.pca_received = False
        self.command_deadline = time.monotonic() + 20
        try:
            self.send_serial("STOP")
            self.request_id = request_id
            self.broadcast(f"STATE,{request_id},STOPPING,station_{self.active_station:02d}")
        except Exception as exc:
            self.fail_capture(request_id, f"STOP:{type(exc).__name__}:{exc}")

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
        try:
            data = os.read(self.serial_fd, 4096)
        except OSError as exc:
            self.fail_capture(self.request_id, f"USB:{type(exc).__name__}:{exc}")
            return
        if not data:
            self.fail_capture(self.request_id, "USB:disconnected")
            return
        self.serial_buffer.extend(data)
        if len(self.serial_buffer) > 65536:
            self.fail_capture(self.request_id, "USB:line_too_long")
            return
        while b"\n" in self.serial_buffer:
            raw, _, remainder = self.serial_buffer.partition(b"\n")
            self.serial_buffer = bytearray(remainder)
            line = raw.rstrip(b"\r").decode("ascii", "replace")
            if self.log_file:
                self.log_file.write(line + "\n")
                self.log_file.flush()
            if line.startswith("CTRL,START,") and self.starting_request is not None:
                try:
                    self.active_station = int(line.split(",", 2)[2])
                except ValueError:
                    self.fail_capture(self.starting_request, "START:bad_station_id")
                    return
                request_id = self.starting_request
                self.starting_request = None
                self.command_deadline = None
                self.running = True
                self.broadcast(f"STATE,{request_id},RUNNING,station_{self.active_station:02d}")
            elif line.startswith("CTRL,ERROR,"):
                self.fail_capture(self.request_id, line.replace(",", ":", 2))
                return
            if line.startswith("PCA,"):
                fields = line.split(",")
                if (len(fields) == 16 and self.stopping_request is not None
                        and fields[2].isdigit() and int(fields[2]) == self.active_station):
                    # Fit the existing bounded GroundLink EVENT text field.
                    self.broadcast(",".join(("PCA", fields[2], fields[8],
                                             fields[9], fields[10], fields[11],
                                             fields[12], fields[13], fields[14],
                                             fields[15], fields[1])))
                    self.pca_received = True
                else:
                    self.fail_capture(self.request_id, "PCA:bad_station_or_fields")
                    return
            elif line.startswith("CTRL,STOP,") and self.stopping_request is not None:
                try:
                    completed_station = int(line.split(",", 2)[2])
                except ValueError:
                    completed_station = -1
                request_id = self.stopping_request
                if not self.pca_received or completed_station != self.active_station:
                    self.fail_capture(request_id, "STOP:missing_pca_or_bad_station")
                    return
                self.close_capture()
                self.request_id = request_id
                self.broadcast(f"STATE,{request_id},IDLE,station_{completed_station:02d}_complete")
                return

    def check_deadline(self):
        if self.command_deadline is not None and time.monotonic() >= self.command_deadline:
            self.fail_capture(self.request_id, "MCU:command_timeout")

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
                for key, _ in self.selector.select(timeout=0.2):
                    if key.data == "listen":
                        client, _ = self.listener.accept()
                        client.setblocking(False)
                        self.clients.add(client)
                        self.selector.register(client, selectors.EVENT_READ, "client")
                        state = ("STARTING" if self.starting_request is not None else
                                 "STOPPING" if self.stopping_request is not None else
                                 "RUNNING" if self.running else "IDLE")
                        detail = (f"station_{self.active_station:02d}" if self.active_station is not None
                                  else "connected")
                        client.send(f"STATE,{self.request_id},{state},{detail}".encode())
                    elif key.data == "client":
                        self.client_event(key.fileobj)
                    else:
                        self.serial_event()
                self.check_deadline()
        finally:
            if self.serial_fd is not None:
                self.close_capture()
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
    Service(args.socket, args.device, args.log_dir).run()


if __name__ == "__main__":
    main()
