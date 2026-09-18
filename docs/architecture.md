# LOONAR System Architecture

현재 구조의 source of truth는 [`project.md`](../project.md)다.

```text
Ground Station -- TCP --> cFS -- local socket --> vehicle_gatewayd
ROS 2 AUTO -------------------------------> vehicle_gatewayd
vehicle_gatewayd --> LIMO ROS backend 또는 LOONAR serial backend

Camera -- H.264/MPEG-TS/UDP -----------------> Ground Station
ROS topics/TF/map -- same LAN ----------------> RViz2
```

- cFS는 지상국 명령과 운용 telemetry를 담당한다.
- ROS 2는 perception, localization, mapping, autonomous motion을 담당한다.
- Gateway는 `STOP`, `MANUAL`, `AUTO`, `PAYLOAD`, `REACTION`을 명시적으로
  선택하고 공통 차량 interface를 제공한다.
- PAYLOAD와 REACTION은 먼저 정지한 후 전용 cFS 실행 경로로 넘긴다.
- 최종 MCU/serial 구현은 `platforms/loonar/` 자료를 기준으로 backend만
  교체한다.

Gateway에 암묵적인 authority/TTL/속도 제한/health gate를 추가하지 않는다.
