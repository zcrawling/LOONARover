"""Write a Korean evidence report from the pooled, version-2 benchmark runs."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'output/video-latency-pi-20260926'
data=json.loads((OUT/'pooled.json').read_text());by={d['profile']:d for d in data}
labels={'low1_current':'360p / 1T / 기존 수신','low1_lowdelay':'360p / 1T / low_delay',
 'low1_directio':'360p / 1T / low_delay + decoder direct I/O', 'low1_nobuffer':'360p / 1T / low_delay + decoder nobuffer',
 'low2_lowdelay':'360p / 2T / low_delay','low4_lowdelay':'360p / 4T / low_delay',
 'medium2_lowdelay':'720p / 2T / low_delay','high4_lowdelay':'1080p / 4T / low_delay',
 'high4_passthrough':'1080p / 4T / low_delay + fps passthrough',
 'high4_unsynced':'1080p / 4T / low_delay + sync=false',
 'low1_nv12':'360p / 1T / NV12 직접 인코딩 + low_delay',
 'medium2_nv12':'720p / 2T / NV12 직접 인코딩 + low_delay',
 'high4_nv12':'1080p / 4T / NV12 직접 인코딩 + low_delay',
 'low2_unsynced':'360p / 2T / low_delay + sync=false'}
f=lambda n:f'{n:.1f}'
lines=['# Pi 실제 카메라 영상 지연 비교 — 2026-09-26','',
 '## 측정 범위와 조건','',
 '- 측정 시작: Pi x264 인코더 입력 직전의 프레임 시간 표식.',
 '- 측정 종료: 노트북에서 디코딩·회전·리사이즈한 PPM 프레임 전체를 읽은 시점.',
 '- **센서 노출/ISP/인코더 이전 큐, Tk 렌더링, 모니터 물리 표시 시간은 포함하지 않는다. 카메라-to-화면의 정확한 전체 지연으로 해석하면 안 된다.**',
 '- 실제 IMX708 카메라, Pi 5 / 8GB, LOONAR 5GHz Wi-Fi. 노트북 i7-1165G7 / 8 logical CPUs.',
 '- 정적인 실내 장면 기준. 로버 주행/고속 움직임/혼잡 RF 환경의 최대치를 보장하지 않는다.',
 '- 360p=640×360/1Mbps, 720p=1280×720/3Mbps, 1080p=1920×1080/5Mbps. 30fps 요청, x264 ultrafast/zerolatency/B프레임 0, GOP 30.',
 '- 노트북 녹화+중간 MPEG-TS 재전송+기존 회전/scale/PPM 필터를 사용. 실제 Tk UI 대신 측정 리더로 수신.',
 '- CPU 100%=논리 코어 하나. CPU/RSS는 0.5초 간격 표본. Pi 전체 용량은 CPU 400%.',
 '- CRC16으로 타임스탬프 판독 검증. 프레임 순번으로 반복/누락을 확인.',
 '- 각 시험 전후 25회 시계 교환 중 최소 RTT 표본으로 오프셋을 구하고 시간에 따라 보간.',
 f'- 최종 포함 시험의 시계 비대칭 추정 불확실성: 최대 ±{max(d["clock_uncertainty_ms"] for d in data):.3f}ms. 이는 양 끝 보정 표본의 값이며 광학 측정 오차가 아니다.',
 '- 정상 구간: 첫 유효 프레임부터 3초 제외. 초기 포함 최대도 별도로 기재. 관측 최대는 시험 중 관측값이며 최악 지연의 보장 상한이 아니다.',
 '', '## 지연 결과','',
 '| 옵션 | 정상 구간 표본 수 | 정상 평균 ms | p95 ms | 정상 최대 ms | 초기 포함 최대 ms | 실제 새 프레임/s | 중복 프레임 |',
 '|---|---:|---:|---:|---:|---:|---:|---:|']
for d in data:
 s=d['latency_ms'];lines.append(f"| {labels[d['profile']]} | {s['n']} | {f(s['mean'])} | {f(s['p95'])} | {f(s['maximum'])} | {f(d['including_startup_ms']['maximum'])} | {d['unique_fps']:.2f} | {d['duplicates']} |")
lines += ['', '## CPU / 메모리','',
 '| 옵션 | Pi CPU 평균/최대 % | Pi RSS 평균/최대 MiB | PC FFmpeg CPU 평균/최대 % | PC FFmpeg RSS 평균/최대 MiB | Pi 최고 온도 °C |',
 '|---|---:|---:|---:|---:|---:|']
for d in data:
 pair=lambda k:f"{f(d[k]['mean'])} / {f(d[k]['maximum'])}"
 lines.append(f"| {labels[d['profile']]} | {pair('pi_cpu_percent')} | {pair('pi_rss_mib')} | {pair('laptop_ffmpeg_cpu_percent')} | {pair('laptop_ffmpeg_rss_mib')} | {f(d['pi_temperature_c']['maximum'])} |")
lines += ['', 'PC 수치는 수신/녹화 FFmpeg와 디코딩 FFmpeg 두 프로세스의 합이다. Python 측정 리더, SSH, 실제 Tk 화면의 비용은 제외한다.', '', '## 반복 및 무결성','']
for d in data:lines.append(f"- {d['profile']}: {', '.join(d['runs'])}; 정상 구간 {d['steady_seconds']}초; CRC 실패 {d['invalid']}, 순번 누락 {d['sequence_gaps']}.")
lines += ['', '## 해석','']
if 'low1_current' in by and 'low1_lowdelay' in by:
 a,b=by['low1_current']['latency_ms']['mean'],by['low1_lowdelay']['latency_ms']['mean']
 lines.append(f'- 같은 Pi 1스레드 송신에서 수신 low_delay만 적용하면 평균 {a:.1f} → {b:.1f}ms, {a-b:.1f}ms ({100*(a-b)/a:.1f}%) 감소했다. CPU가 크게 줄어서가 아니라 디코딩 대기 지연을 줄인 효과와 부합한다.')
lines += ['- 1080p는 요청한 30fps와 실제 새 프레임 속도를 구분해야 한다. 기존 FFmpeg 출력은 부족한 프레임을 반복할 수 있다.',
 '- 인코더 입력 시점부터 이미 새 프레임 간격이 늘어난 경우, 디코더만으로 실제 촬영 FPS를 복원할 수 없다.',
 '- sync=false는 실제 수치로 판단해야 한다. 동기화를 끄면 무조건 개선된다는 가정을 사용하지 않는다.',
 '- 측정은 /tmp의 별도 송신기로 수행했다. 이후 사용자 요청에 따라 검증된 NV12 직접 인코딩을 설치 송신기에 반영하고 지상국에 low_delay를 적용했다. 배포 상태는 deployment.txt를 참조한다.',
 '', '## 재현 및 증거','',
 '- [측정 도구 설명](../../tools/video_latency/README.md)',
 '- `pooled.json`: 이 표의 계산 근거.',
 '- 각 시험의 `raw.json`: 프레임별 보정 지연, 시계 교환, 자원 표본.',
 '- `encode.csv`: Pi에서 측정한 인코딩 시간; `record.ts`: 실제 수신 영상; `sender.log`, `process*.log`: 오류 기록.',
 '- instrument_version=2만 최종 집계. 초기 pilot/r1 및 중단된 r2는 탐색 자료이며 최종 비교에서 제외. v2는 gst-launch와 같이 GST_MESSAGE_LATENCY 때 지연 재계산을 수행한다.',
 '', '## 남은 검증','',
 '실제 센서부터 디스플레이까지의 전체 지연은 밀리초 타이머 또는 점멸 LED와 표시 화면을 동일한 고속 카메라로 촬영해 추가 측정해야 한다. 이번 수치를 그 값으로 대신하지 않는다.', '']
(OUT/'REPORT.md').write_text('\n'.join(lines))
