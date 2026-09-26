"""Publish bench MCU samples to ROS without starting a recorder."""

import logging
from pathlib import Path
import signal
import socket
import subprocess


class RosSamples:
    def __init__(self, runtime, registry, environment):
        self.tools = Path(__file__).resolve().parents[1]
        self.runtime = runtime
        self.registry = registry
        self.environment = environment
        self.sample_path = runtime / "ros-samples.sock"
        self.child = None
        self.log = None
        self.reported = False
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.socket.setblocking(False)
        self.forward_errors = 0

    def start(self):
        command = ["bash", str(self.tools / "run-bench-sensors.sh"),
                   str(self.registry), str(self.sample_path)]
        self.log = open(self.runtime / "sensors.log", "w")
        self.child = subprocess.Popen(command, env=self.environment,
                                      stdout=self.log, stderr=subprocess.STDOUT)
        print(f"ROS sample publisher started; log: {self.runtime}/sensors.log\n"
              "No rosbag recording started. Run record-drive.sh separately to save data.", flush=True)

    def forward(self, raw):
        try:
            self.socket.sendto(raw, str(self.sample_path))
        except OSError:
            self.forward_errors += 1
            if self.forward_errors == 1:
                logging.warning("ROS sample consumer unavailable; check %s/sensors.log",
                                self.runtime)

    def poll(self):
        if self.child is not None:
            code = self.child.poll()
            if code is not None and not self.reported:
                self.reported = True
                logging.error("ROS sample publisher exited (%s); check %s/sensors.log. "
                              "Driving processes remain running.", code, self.runtime)

    def close(self):
        if self.child is not None and self.child.poll() is None:
            self.child.send_signal(signal.SIGTERM)
            try:
                self.child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.child.kill()
                self.child.wait()
        if self.log is not None:
            self.log.close()
        self.socket.close()
        if self.forward_errors:
            logging.warning("ROS sample forwarding missed %s packets (including startup).",
                            self.forward_errors)
