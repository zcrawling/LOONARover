# Pi CPU 배치

Ubuntu Pi 커널 `6.8.0-1065-raspi`의 cpuset, NO_HZ_FULL, RCU_NOCB 지원을 확인했다.
커널 재빌드는 필요 없다. 전체 배치의 소스는 이 폴더에 모은다.

| CPU | 담당 |
|---|---|
| 0 | 기본 IRQ, 이동 가능한 커널 workqueue, MCU backend 송수신/명령 전달, vehicle gateway |
| 1–3 | 센서, ToF SDK, ROS, 지형 처리, 카메라, 녹화/압축, 기록 저장 프로세스 |
| 0–3 | 일반 OS 서비스·사용자 세션: 필요에 따라 스케줄러가 배치 |

단순 taskset 대신 systemd의 별도 최상위 `loonar.slice`와 cpuset을 사용한다.
일반 `system.slice`, `user.slice`, `init.scope`와 systemd 기본 affinity는 CPU 0–3을
허용한다. 이는 CPU 0이 바쁠 때만 이동하는 엄격한 우선순위 규칙이 아니며,
일반 OS 프로세스는 스케줄러 판단으로 CPU 1–3에서도 실행될 수 있다.
`loonar-control.slice`는 CPU 0만 쓰며, `loonar-work.slice`는 CPU 1–3만 허용하여
센서·ROS·녹화 프로세스가 CPU 0을 사용할 수 없게 한다. 상위 `loonar.slice`는
두 그룹을 모두 포함하므로 CPU 0–3을 허용한다.
실행기는 자기 PID를 `loonar-work.slice` 또는 `loonar-control.slice`의 transient
scope로 옮긴 뒤 원래 사용자로 계속 실행한다. 기존 PID, signal, Ctrl+C 동작을
유지한다. root helper는 설정된 사용자가 소유한 PID의 CPU 배치만 변경하며
사용자가 넘긴 명령을 root로 실행하지 않는다.

## 설치 및 실행

Pi에서 한 번 설치한다. 실행 중인 로버가 있으면 먼저 종료한다.

```bash
sudo python3 ~/LOONAR/platforms/loonar/ros2/terrain_navigation/runtime/install_cpu_layout.py
```

현재 프로세스 그룹·IRQ·workqueue 배치는 즉시 적용한다. 아래 부팅 옵션은
`/boot/firmware/cmdline.txt`에 추가되어 **다음 재부팅부터** 적용된다.

```text
nohz_full=1-3 rcu_nocbs=1-3 irqaffinity=0 isolcpus=managed_irq,1-3
```

설치기는 자동 재부팅하거나 주행을 시작하지 않는다. 기존 PC 신경망 실행 명령과
Pi의 `recording/run_pi.sh --mode fly` 또는 `fly_brain/run_pi.sh --drive`를 사용한다.
`deploy_pi.sh`가 사용하는 배포 경로는 CPU 배치가 추가된 `motor_bench.py`도 복사한다.

모터 구동 없이 센서·기록을 시험하려면:

```bash
bash ~/LOONAR/platforms/loonar/ros2/terrain_navigation/recording/run_pi.sh --mode observe --seconds 30
```

`/etc/loonar/cpu-layout.json`이 없는 PC/Pi에서는 실행기의 배치 기능이 비활성이다.

## 커널 격리 범위

MCU `4-2`와 ToF `5-1`은 같은 xHCI 컨트롤러를 공유한다. 공유 USB IRQ와 MCU
사용자 프로세스를 모두 CPU 0에 둔다. 드라이버가
affinity 변경을 거절한 IRQ는 `/run/loonar-cpu-housekeeping.json`에 표시한다.
30초마다 장치 IRQ와 이동 가능한 workqueue의 배치를 유지한다.

CPU별 timer/IPI/묶인 kernel thread, 실행 중인 태스크의 syscall/page fault까지
모두 CPU 0으로 이동하는 것은 아니다. 이 구성은 커널을 별도 CPU에서만 실행하는
방식이나 hard real-time 보장이 아니다. CPU 1–3은 서로 부하 분산한다. 해당 CPU에
둘 이상의 runnable thread가 있으면 NO_HZ_FULL이어도 scheduler tick이 필요할 수 있다.

MCU 기록은 디스크 쓰기와 분리했지만 저장 처리량이 계속 부족하면 제한된 큐가
넘칠 수 있다. 손실은 검증 오류로 남긴다. 모터 경고 비트 해석 문제는 CPU 구성과
독립적이며 이 작업에서 바꾸지 않는다.

## 확인 및 복구

현재 **OS=0–3, work=1–3, control=0** 구성은 Pi에 적용했다. 실제 scope에서
부모·자식 프로세스 affinity와 cpuset을 확인했고, work 프로세스가 CPU 0으로
이동하려는 요청과 control 프로세스가 CPU 1–3으로 이동하려는 요청이 모두
거절되는 것을 확인했다. 기존 부팅 옵션은 그대로 유효하므로 추가 재부팅은
필요 없다. 이 변경 후 주행 성능 시험은 하지 않았다.
[현재 배치 검증](validation/20261007/shared_cpu0.json)을 참고한다.

아래는 변경 전 **OS=0, work=1–2, control=3** 구성의 기록이다.
2026-10-07 실제 Pi에서 재부팅 후 부팅 옵션과 각 프로세스·스레드의 CPU 배치를
확인했다. 60초 `observe` 시험에서 MCU 수신 최대 공백 15.55ms, 파서 오류 0회,
capture 구간 sequence 누락 0회, MCU/gateway 기록 큐 손실 0건이었다. 필수 bag
스트림과 원본 journal 대조도 통과했다. 모터 주행 명령은 보내지 않았다.

다만 CPU 1–2의 경합이 크고 ROS 메시지의 header 간격이 최대 2.96초였다.
ToF stream-stale 오류 2회와 pending 프레임 교체 29회도 관측했다. 기록 무결성
통과는 생성된 journal이 bag에 저장됐다는 뜻이며, 센서 내부부터 모든 프레임이
보존됐거나 자율주행 지연이 해결됐다는 뜻은 아니다. 코어 배치·비동기 기록·카메라
5fps 변경을 함께 시험했으므로 개별 효과는 분리하지 않았다.
세부 결과는 [validation/20261007/report.json](validation/20261007/report.json)에 있다.

```bash
cat /proc/cmdline
cat /sys/fs/cgroup/system.slice/cpuset.cpus.effective
cat /sys/fs/cgroup/user.slice/cpuset.cpus.effective
cat /sys/fs/cgroup/loonar.slice/loonar-work.slice/cpuset.cpus.effective
cat /sys/fs/cgroup/loonar.slice/loonar-control.slice/cpuset.cpus.effective
cat /run/loonar-cpu-housekeeping.json
```

원본 설정은 `/var/lib/loonar-cpu-layout/original.json`에 보존한다. 로버를 종료한 뒤:

```bash
sudo python3 ~/LOONAR/platforms/loonar/ros2/terrain_navigation/runtime/install_cpu_layout.py --remove
```

원본 파일·cgroup 제한·IRQ/workqueue 마스크를 복원한다. 부팅 옵션과 이미 생성된
kernel thread의 완전한 원복은 이후 재부팅 시 적용된다.

## Pi CPU 온도

인자 없는 `start-ground-support.sh`의 gcs 기록 세션은 `thermal_sensor.py`를
함께 시작한다. `/sys/class/thermal/thermal_zone0/temp`의 밀리도 값을 °C로
변환해 읽기 전용 TCP 7445로 1초마다 보낸다. 기존 지상국 backend가 같은 Pi
주소로 연결해 제어 MCU 온도 옆에 표시한다. 3초 이상 미수신 또는 센서 읽기
실패 시 `—`를 표시한다. AUTO/STOP과 독립적으로 동작하며 온도 서비스 오류는
주행 스택을 중지시키지 않는다. 변경 후 Pi 지원 스택과 PC 지상국을 재시작한다.
