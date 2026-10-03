# Pi 카메라

Camera Module 3 Wide를 Pi의 libcamera/GStreamer로 연다.
현재 구현은 `libcamerasrc → NV12 → x264enc → MPEG-TS`이며 H.264 소프트웨어 인코딩이다.
ROS 영상 분기, 하드웨어 H.265 인코더, stream token 제어는 구현된 경로가 아니다.

- [송신기와 프로필](../../../common/video/README.md)
- [Pi 실행·로컬 녹화](../porting/ground_control_runbook.md)
- [카메라 스택 설치](../deploy/README.md)
- [지상국 수신](../../../GCS/README.md)

카메라는 송신 프로세스 하나가 소유한다. bench 영상과 `loonar-video.service`를
동시에 실행하지 않는다. 지상국 표시의 90° 회전은 PC에서 적용하며 Pi 녹화는 원본 방향이다.
