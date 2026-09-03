# LOONAR System Architecture

The authoritative detailed specification is [project.md](../project.md).

```text
Ground Station -> cFS -> mission intent -> ROS 2
                       authority/manual motion -> vehicle_gatewayd
ROS 2 autonomy -> AUTO motion -------------> vehicle_gatewayd
vehicle_gatewayd -> VehicleBackend -> LIMO or final Teensy RS-485 MCU
```

- cFS owns mission sequencing, ground command and telemetry.
- ROS 2 owns localization, perception and autonomous navigation.
- `vehicle_gatewayd` owns authority (`AUTO`, `MANUAL`, `NONE`), zero transition,
  epoch, sequence, TTL, validation and the sole vehicle interface.
- The Control MCU owns real-time actuation and independent local safety.

No cFS or ROS 2 process may directly open the final rover Control MCU UART/RS-485 link.
