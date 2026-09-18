// SDK-only acquisition process. Image display lives in a separate process.
#include <atomic>
#include <chrono>
#include <csignal>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <thread>
#include <unistd.h>
#include "CubeEyeCamera.h"
#include "CubeEyeSink.h"
#include "CubeEyeBasicFrame.h"
namespace cu = meere::sensor;
static volatile sig_atomic_t stopping = 0;
static void interrupt(int) { stopping = 1; }
static bool send_bytes(int fd, const void* data, size_t size) {
    auto p = static_cast<const char*>(data);
    while (size) { auto n = write(fd, p, size); if (n <= 0) return false; p += n; size -= n; }
    return true;
}
class Receiver : public cu::sink {
    int fd_;
public:
    std::atomic<unsigned> count{0};
    explicit Receiver(int fd) : fd_(fd) {}
    std::string name() const override { return "loonar_depth_viewer"; }
    void onCubeEyeCameraState(cu::ptr_source, cu::CameraState state) override {
        std::cerr << "Camera state: " << static_cast<int>(state) << std::endl;
    }
    void onCubeEyeCameraError(cu::ptr_source, cu::CameraError error) override {
        std::cerr << "Camera error: " << static_cast<int>(error) << std::endl;
    }
    void onCubeEyeFrameList(cu::ptr_source, const cu::sptr_frame_list& frames) override {
        if (!frames || stopping) return;
        for (const auto& frame : *frames) {
            if (frame->frameType() != cu::FrameType::Depth || frame->frameDataType() != cu::DataType::U16) continue;
            auto depth = cu::frame_cast_basic16u(frame);
            uint32_t header[] = {0x43554245, static_cast<uint32_t>(frame->frameWidth()), static_cast<uint32_t>(frame->frameHeight())};
            const size_t pixels = static_cast<size_t>(header[1])*header[2];
            if (depth->frameData()->size() != pixels) continue;
            if (!send_bytes(fd_,header,sizeof(header)) || !send_bytes(fd_,depth->frameData()->data(),pixels*2)) { stopping=1; return; }
            ++count;
        }
    }
};
int main(int argc, char** argv) {
    if (argc != 2) { std::cerr << "Expected output pipe fd\n"; return 2; }
    signal(SIGINT,interrupt); signal(SIGTERM,interrupt); signal(SIGPIPE,SIG_IGN);
    auto sources=cu::search_camera_source();
    if (!sources || sources->size()!=1) { std::cerr << "Expected exactly one CubeEye camera; check USB/power/permissions\n"; return 1; }
    auto source=(*sources)[0];
    std::cerr << "Camera: " << source->name() << " serial=" << source->serialNumber() << std::endl;
    auto camera=cu::create_camera(source);
    if (!camera) return 1;
    Receiver receiver(std::atoi(argv[1])); camera->addSink(&receiver);
    auto rc=camera->prepare();
    if (rc==cu::success) rc=camera->run(cu::FrameType::Depth);
    if (rc!=cu::success) { std::cerr << "Prepare/run failed: " << static_cast<int>(rc) << std::endl; cu::destroy_camera(camera); return 1; }
    while (!stopping) std::this_thread::sleep_for(std::chrono::milliseconds(50));
    camera->stop(); cu::destroy_camera(camera); camera.reset();
    std::cerr << "Depth frames: " << receiver.count << std::endl;
    // v2.5.11's process-global teardown hangs on this Ubuntu 26 host after
    // stop/destroy have returned. The isolated helper has no pending file data;
    // exit after explicit camera cleanup rather than invoke SDK global teardown.
    std::_Exit(0);
}
