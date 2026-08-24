# LOONAR Interface Catalog

## 1. 목적

이 문서는 공개 경계의 owner, producer, consumer, queue, freshness를 한 곳에 모은다. 내부 함수 호출과 중간 판단은 catalog 대상이 아니다.

## 2. 실행영역과 owner

| 실행영역 | Owner | 외부 경계 |
| --- | --- | --- |
| `mcu-io.service` | Control/Payload serial | wire, local IPC |
| `cfs.service` | mode, authority, safety, GCS control | cFS SB, local IPC, TLS |
| `ros2.service` | sensor conversion, localization, navigation, perception | DDS, local IPC |
| `camera.service` | Camera capture와 encoder | video, Vision frame, local control |

## 3. Hardware ownership

| 장치 | 유일한 owner | 금지된 직접 접근 |
| --- | --- | --- |
| Control serial | `mcu-io` | cFS, ROS, GCS |
| Payload serial | `mcu-io` | cFS, ROS, GCS |
| Camera device | `camera.service` | ROS Vision, GCS |
| I200DK USB/device | I200DK ROS driver | cFS, GCS |
| Motor output | Control MCU | MPU 전체 |

## 4. Control MCU wire

| ID | Message | Producer | Consumer | Rate/Policy |
| ---: | --- | --- | --- | --- |
| `0x10` | `MPU_HEALTH` | `mcu-io` | Control MCU | 10 Hz |
| `0x20` | `MOTION_CMD` | `mcu-io` | Control MCU | latest, 20~50 Hz |
| `0x80` | `MCU_STATUS` | Control MCU | `mcu-io` | 20 Hz |

정확한 byte layout은 `control_mpu_if.md`가 권위 문서다.

## 5. Local IPC

| Endpoint | 주요 message | Producer | Consumer | Queue |
| --- | --- | --- | --- | --- |
| `control.sock` | approved motion, MCU status | `LNR_IO`/`mcu-io` | 상대 peer | latest 1 |
| `sensors.sock` | IMU, encoder sample | `mcu-io` | `loonar_bridge` | bounded sensor ring |
| `payload.sock` | command, status | `LNR_IO`/`mcu-io` | 상대 peer | command FIFO/status latest |
| `ros-cfs.sock` | AUTO candidate, system status | bridge/`LNR_IO` | 상대 peer | latest + event FIFO |

모든 endpoint는 `SOCK_SEQPACKET`, 8-byte header, `SO_PEERCRED`, connection `HELLO`를 사용한다.

## 6. cFS Software Bus

| Message | Producer | Consumer | Queue/Freshness |
| --- | --- | --- | --- |
| `AUTO_CANDIDATE` | `LNR_IO` | `LNR_CTRL` | latest 1 + TTL |
| `MANUAL_CANDIDATE` | `GCS_IF` | `LNR_CTRL` | latest 1 + lease/TTL |
| `MODE_REQUEST` | `GCS_IF`/mission | `LNR_CTRL` | FIFO + request dedup |
| `APPROVED_MOTION` | `LNR_CTRL` | `LNR_IO` | latest 1 + epoch/TTL |
| `MCU_STATUS` | `LNR_IO` | `LNR_CTRL` | latest 1 + receive age |
| `PAYLOAD_REQUEST` | `GCS_IF`/mission | `LNR_CTRL` | FIFO + request dedup |
| `PAYLOAD_STATUS` | `LNR_IO`/`LNR_CTRL` | `GCS_IF` | latest + transition |
| `SYSTEM_STATUS` | `LNR_CTRL` | `GCS_IF`/`LNR_IO` | latest 1 |
| `PLATFORM_ACTION` | `LNR_CTRL` | `LNR_IO` | FIFO + request dedup |
| `EVENT` | 모든 App | EVS/`GCS_IF` | bounded FIFO/rate limit |

## 7. ROS 2 topics

| Topic | Type | Producer | Consumer | QoS |
| --- | --- | --- | --- | --- |
| `/imu/data` | `sensor_msgs/Imu` | bridge | localization | SENSOR |
| `/odom/wheel` | `nav_msgs/Odometry` | bridge | localization | SENSOR |
| `/points` | `sensor_msgs/PointCloud2` | I200DK driver | mapper/registration | SENSOR |
| `/odometry/filtered` | `nav_msgs/Odometry` | localization | Nav2/mapper | STATE |
| `/cmd_vel_nav` | `geometry_msgs/TwistStamped` | Nav2 | bridge | STATE |
| `/loonar/system_status` | custom status | bridge | ROS diagnostics | STATE |
| `/loonar/payload_status` | custom status | bridge | mission/UI | STATE |
| Vision input | image transport | Camera pipeline | Vision node | latest 1 |

`odom -> base_link` TF producer는 localization 하나다.

## 8. GCS 경계

| 경계 | Owner | 내용 | 혼잡 정책 |
| --- | --- | --- | --- |
| Authenticated control/tlm | `GCS_IF` | lease, mode, request, status, event | priority bounded queue |
| Video | `camera.service` | encoded live stream | old frame drop |
| Bulk/File | common worker | opaque file range | bandwidth limit/resume |

## 9. Queue class

| Class | 사용처 | overflow |
| --- | --- | --- |
| latest 1 | motion, status, periodic state | 이전 값 대체 |
| bounded FIFO | discrete request, fault/event | reject/drop counter 또는 peer disconnect |
| bounded ring | sensor sample | 가장 오래된 sample drop |
| bounded byte queue | Payload record, network | byte 상한 후 drop/degrade |

## 10. Catalog 관리

숫자 ID와 schema version은 `interfaces/catalog/`에서 관리하고 `tools/gen_catalog.py`로 C/C++ 상수와 Markdown을 생성한다. 변경 후 다음을 통과해야 한다.

```sh
python3 tools/gen_catalog.py
python3 tools/gen_catalog.py --check
```

생성 파일은 직접 수정하지 않는다.
