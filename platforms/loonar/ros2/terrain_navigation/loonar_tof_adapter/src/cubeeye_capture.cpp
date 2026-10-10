// SDK ownership stays in this isolated helper. Binary pipe, no ROS
// dependencies.
// Vendor headers are not self-contained; preserve their required include order.
// clang-format off
#include <cstdint>
#include "CubeEyeCamera.h"
#include "CubeEyeSink.h"
#include "CubeEyeBasicFrame.h"
// clang-format on
#include "capture_transport.hpp"
#include <cstring>
#include <atomic>
#include <cerrno>
#include <chrono>
#include <csignal>
#include <cstdlib>
#include <fcntl.h>
#include <iostream>
#include <poll.h>
#include <thread>
#include <unistd.h>
namespace cu = meere::sensor;
static volatile sig_atomic_t stopping = 0;
static void interrupt(int) { stopping = 1; }
class Receiver : public cu::sink {
  loonar::CaptureTransport transport_;
  loonar::CaptureHealth<cu::CameraError> health_;
  std::atomic<uint32_t> sequence_{0};
  double calibration_[12];

public:
  Receiver(int fd, const cu::IntrinsicParameters &i,
           const cu::DistortionCoefficients &d)
      : transport_(fd),
        calibration_{i.focal.fx,  i.focal.fy,  i.principal.cx,  i.principal.cy,
                     d.radial.k1, d.radial.k2, d.tangential.p1, d.tangential.p2,
                     d.radial.k3, d.radial.k4, d.radial.k5,     d.radial.k6} {}
  std::string name() const override { return "loonar_terrain_acquisition"; }
  void onCubeEyeCameraState(cu::ptr_source, cu::CameraState state) override {
    std::cerr << "CubeEye state " << int(state) << std::endl;
  }
  void onCubeEyeCameraError(cu::ptr_source, cu::CameraError e) override {
    health_.error(e);
    if (e == cu::CameraError::FrameDropped) {
      const auto count = health_.dropped();
      if (count == 1 || count % 100 == 0)
        std::cerr << "CubeEye FrameDropped (recoverable), count=" << count
                  << "; continuing acquisition\n";
    } else {
      std::cerr << "CubeEye fatal error " << int(e) << '\n';
    }
  }
  void onCubeEyeFrameList(cu::ptr_source,
                          const cu::sptr_frame_list &frames) override {
    if (!frames || stopping || failed())
      return;
    cu::sptr_frame depth, amplitude;
    for (const auto &f : *frames) {
      if (f->frameDataType() != cu::DataType::U16)
        continue;
      if (f->frameType() == cu::FrameType::Depth)
        depth = f;
      if (f->frameType() == cu::FrameType::Amplitude)
        amplitude = f;
    }
    if (!depth || !amplitude || depth->timestamp() != amplitude->timestamp() ||
        depth->frameWidth() != amplitude->frameWidth() ||
        depth->frameHeight() != amplitude->frameHeight())
      return;
    uint32_t header[] = {0x4c544f46, static_cast<uint32_t>(depth->frameWidth()),
                         static_cast<uint32_t>(depth->frameHeight()),
                         ++sequence_};
    const uint64_t timestamp =
        std::chrono::duration_cast<std::chrono::nanoseconds>(
            std::chrono::system_clock::now().time_since_epoch())
            .count();
    const size_t pixels = size_t(header[1]) * header[2];
    auto d = cu::frame_cast_basic16u(depth),
         a = cu::frame_cast_basic16u(amplitude);
    if (d->frameData()->size() != pixels || a->frameData()->size() != pixels)
      return;
    // SDK buffers are only borrowed for this callback. Copy both planes into
    // one owned packet before returning; a worker serializes the whole packet.
    std::vector<uint8_t> packet(sizeof(header) + sizeof(timestamp) +
                                sizeof(calibration_) + pixels * 4);
    size_t offset = 0;
    auto append = [&](const void *data, size_t size) {
      std::memcpy(packet.data() + offset, data, size);
      offset += size;
    };
    append(header, sizeof(header));
    append(&timestamp, sizeof(timestamp));
    append(calibration_, sizeof(calibration_));
    append(d->frameData()->data(), pixels * 2);
    append(a->frameData()->data(), pixels * 2);
    transport_.submit(std::move(packet));
  }
  bool failed() const { return health_.fatal() || transport_.failed(); }
  void stopOutput() { transport_.stop(); }
  void report() const {
    std::cerr << "CubeEye capture: sdk_frame_dropped=" << health_.dropped()
              << " pending_frames_replaced=" << transport_.replaced() << '\n';
  }
};
int main(int argc, char **argv) {
  if (argc != 2) {
    std::cerr << "usage: cubeeye_capture PIPE_FD\n";
    return 2;
  }
  signal(SIGINT, interrupt);
  signal(SIGTERM, interrupt);
  signal(SIGPIPE, SIG_IGN);
  char *end = nullptr;
  long output_fd = std::strtol(argv[1], &end, 10);
  if (!end || *end || output_fd < 0 || output_fd > 0x7fffffff) {
    std::cerr << "Invalid output pipe FD" << std::endl;
    return 2;
  }
  int flags = fcntl(int(output_fd), F_GETFL);
  if (flags < 0 || fcntl(int(output_fd), F_SETFL, flags | O_NONBLOCK) < 0) {
    std::cerr << "Cannot set nonblocking output pipe" << std::endl;
    return 2;
  }
  std::cerr << "CubeEye: searching for USB camera" << std::endl;
  auto sources = cu::search_camera_source();
  if (!sources || sources->size() != 1) {
    std::cerr << "Expected exactly one CubeEye\n";
    return 1;
  }
  std::cerr << "CubeEye: creating " << (*sources)[0]->name() << std::endl;
  auto camera = cu::create_camera((*sources)[0]);
  if (!camera)
    return 1;
  std::cerr << "CubeEye: preparing camera" << std::endl;
  auto rc = camera->prepare();
  std::cerr << "CubeEye: prepare returned " << int(rc) << std::endl;
  if (rc != cu::success) {
    cu::destroy_camera(camera);
    std::_Exit(1);
  }
  cu::IntrinsicParameters i{};
  cu::DistortionCoefficients d{};
  auto irc = camera->intrinsicParameters(i);
  auto drc = camera->distortionCoefficients(d);
  if (irc != cu::success || drc != cu::success) {
    std::cerr << "Cannot read calibration: prepare=" << int(rc)
              << " intrinsics=" << int(irc) << " distortion=" << int(drc)
              << std::endl;
    cu::destroy_camera(camera);
    std::_Exit(1);
  }
  Receiver receiver(int(output_fd), i, d);
  camera->addSink(&receiver);
  std::cerr << "CubeEye: starting depth/amplitude" << std::endl;
  rc = camera->run(cu::FrameType::Depth | cu::FrameType::Amplitude);
  if (rc != cu::success) {
    std::cerr << "CubeEye: run failed " << int(rc) << std::endl;
    return 1;
  }
  auto next_report = std::chrono::steady_clock::now() + std::chrono::seconds(5);
  while (!stopping && !receiver.failed()) {
    std::this_thread::sleep_for(std::chrono::milliseconds(30));
    if (std::chrono::steady_clock::now() >= next_report) {
      receiver.report();
      next_report = std::chrono::steady_clock::now() + std::chrono::seconds(5);
    }
  }
  const int exit_code = receiver.failed() ? 1 : 0;
  receiver.stopOutput();
  receiver.report();
  // On Pi SDK 2.5.9 destroy_camera can hang after reporting Released, even
  // though stop() returned. Bound vendor teardown inside this isolated process;
  // the OS closes its USB handles. A hung stop remains a failed exit.
  std::atomic<bool> stopped{false};
  std::thread([&stopped, exit_code] {
    std::this_thread::sleep_for(std::chrono::seconds(2));
    std::cerr << "CubeEye: SDK teardown timeout; exiting isolated helper"
              << std::endl;
    std::_Exit(stopped.load() ? exit_code : 1);
  }).detach();
  camera->stop();
  stopped = true;
  std::cerr << "CubeEye: stopped, destroying camera" << std::endl;
  cu::destroy_camera(camera);
  camera.reset();
  std::cerr << "CubeEye: shutdown complete" << std::endl;
  std::_Exit(exit_code);
}
