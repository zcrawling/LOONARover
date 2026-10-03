# Laptop payload START/STOP test

Run from the repository root on Windows:

```powershell
python -m pip install pyserial
python -m serial.tools.list_ports
python platforms/loonar/tools/payload_pca_desktop.py --device COM5
```

Replace COM5 with the Teensy's port. Close PlatformIO Serial Monitor first.
Upload the current payload firmware with START/STOP and CTRL acknowledgements;
older firmware that emits PCA automatically is incompatible.

The buttons feed the same `<QHH` payload (opcode 1/2) into the Pi service's
`client_event`. The desktop adapter replaces only USB transport and event output.
It does not run GroundLink, cFS, or the actual GCS network backend.

Expected sequence:

1. START: STARTING, then RUNNING after MCU acknowledgement. A CSV opens.
2. STOP: STOPPING, then one PCA event and IDLE after MCU acknowledgement.
3. Repeat: next MCU station ID and a new CSV.
4. STOP while IDLE: already_stopped; START while active: already_started.

Logs default to `platforms/loonar/firmware/payload/logs/desktop/`.
STOP may wait for the firmware's minimum measurement duration. An old firmware,
missing acknowledgement, or missing PCA produces ERROR rather than success.
Closing the window requests STOP and waits for completion/timeout.
This verifies the existing manual station handshake, not rover motion/stabilization
filtering or physical power switching. The USB connection supplies power throughout.
