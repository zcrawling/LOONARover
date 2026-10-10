#pragma once

#include <atomic>
#include <cerrno>
#include <condition_variable>
#include <cstdint>
#include <mutex>
#include <poll.h>
#include <thread>
#include <unistd.h>
#include <vector>

namespace loonar {
// One packet in flight and one pending. The SDK callback only copies/enqueues;
// a slow ROS reader cannot hold up camera acquisition. Never replace a packet
// already being written: the length-prefixed stream must remain aligned.
class CaptureTransport {
  int fd_;
  std::mutex mutex_;
  std::condition_variable ready_;
  std::vector<uint8_t> pending_;
  std::atomic<bool> stopping_{false}, failed_{false};
  std::atomic<uint64_t> replaced_{0};
  std::thread worker_;

  bool write_packet(const std::vector<uint8_t> &packet) {
    size_t offset = 0;
    while (offset < packet.size() && !stopping_) {
      auto n = ::write(fd_, packet.data() + offset, packet.size() - offset);
      if (n < 0 && errno == EINTR) continue;
      if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) {
        pollfd output{fd_, POLLOUT, 0};
        if (::poll(&output, 1, 50) < 0 && errno != EINTR) return false;
        continue;
      }
      if (n <= 0) return false;
      offset += static_cast<size_t>(n);
    }
    return offset == packet.size();
  }
  void run() {
    for (;;) {
      std::vector<uint8_t> packet;
      {
        std::unique_lock<std::mutex> lock(mutex_);
        ready_.wait(lock, [&] { return stopping_ || !pending_.empty(); });
        if (stopping_) return;
        packet.swap(pending_);
      }
      if (!write_packet(packet)) {
        if (!stopping_) failed_ = true;
        return;
      }
    }
  }

public:
  // fd must be O_NONBLOCK; caller owns it and ignores SIGPIPE.
  explicit CaptureTransport(int fd) : fd_(fd), worker_([this] { run(); }) {}
  ~CaptureTransport() { stop(); }
  void submit(std::vector<uint8_t> packet) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (stopping_ || failed_) return;
    if (!pending_.empty()) ++replaced_;
    pending_ = std::move(packet);
    ready_.notify_one();
  }
  void stop() {
    {
      std::lock_guard<std::mutex> lock(mutex_);
      stopping_ = true;
    }
    ready_.notify_one();
    if (worker_.joinable()) worker_.join();
  }
  bool failed() const { return failed_; }
  uint64_t replaced() const { return replaced_; }
};

// Use the SDK enum at the call site, not a hardcoded numeric error value.
template <typename CameraError> class CaptureHealth {
  std::atomic<uint64_t> dropped_{0};
  std::atomic<bool> fatal_{false};
public:
  void error(CameraError error) {
    if (error == CameraError::FrameDropped) ++dropped_;
    else fatal_ = true;
  }
  uint64_t dropped() const { return dropped_; }
  bool fatal() const { return fatal_; }
};
} // namespace loonar
