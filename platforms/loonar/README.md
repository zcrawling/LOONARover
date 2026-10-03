# LOONAR 로버

Raspberry Pi 5 / Ubuntu 24.04 / ROS 2 Jazzy와 두 Teensy 4.1을 사용한다.
Control은 FreeRTOS·LNR2 USB, Payload는 별도 센서 펌웨어·USB ASCII 경로다.

- [실행·로그·기록](porting/ground_control_runbook.md)
- [Pi 설치](deploy/README.md)
- [배선](hardware/hardware_baseline.md)
- [Control 펌웨어](firmware/control/README.md) · [wire v2](porting/mcu_wire_v2.md)
- [Payload 펌웨어](firmware/payload/README.md) · [운용](porting/payload_pca_runbook.md)
- [CubeEye 공급 SDK](vendor-assets.md) · [ToF 기록](porting/tof_recording_runbook.md)

`interfaces/control_mcu_wire_v1.md`와 C 기반 control core는 이전 프로토콜의
회귀시험 자료다. 현재 `src/v2/runtime.cpp`와 혼동하지 않는다.
