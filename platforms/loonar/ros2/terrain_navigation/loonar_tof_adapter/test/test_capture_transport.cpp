#include "capture_transport.hpp"
#include <cassert>
#include <chrono>
#include <csignal>
#include <fcntl.h>
#include <iostream>

using namespace std::chrono_literals;
enum class Error { FrameDropped, IO, NoFramesReceived };
constexpr size_t packet_size = 120 + 640 * 480 * 4;

template <typename Predicate> void wait_for(Predicate predicate) {
  auto until = std::chrono::steady_clock::now() + 2s;
  while (!predicate()) {
    assert(std::chrono::steady_clock::now() < until);
    std::this_thread::sleep_for(1ms);
  }
}
std::vector<uint8_t> read_packet(int fd) {
  std::vector<uint8_t> result(packet_size);
  size_t offset = 0;
  wait_for([&] {
    auto n = read(fd, result.data() + offset, result.size() - offset);
    if (n > 0) offset += size_t(n);
    else assert(n < 0 && errno == EAGAIN);
    return offset == result.size();
  });
  return result;
}
int main() {
  signal(SIGPIPE, SIG_IGN);
  int pipefd[2];
  assert(pipe2(pipefd, O_NONBLOCK) == 0);
  loonar::CaptureHealth<Error> health;
  loonar::CaptureTransport writer(pipefd[1]);
  writer.submit(std::vector<uint8_t>(packet_size, 11));
  // Wait until the first packet is actually in flight, then stall the reader.
  wait_for([&] { pollfd p{pipefd[0], POLLIN, 0}; return poll(&p, 1, 0) == 1; });
  for (int i = 0; i < 100; ++i) {
    health.error(Error::FrameDropped);
    writer.submit(std::vector<uint8_t>(packet_size, 22));
  }
  writer.submit(std::vector<uint8_t>(packet_size, 33));
  assert(!health.fatal() && health.dropped() == 100);
  assert(!writer.failed() && writer.replaced() == 100);
  assert(read_packet(pipefd[0]) == std::vector<uint8_t>(packet_size, 11));
  assert(read_packet(pipefd[0]) == std::vector<uint8_t>(packet_size, 33));
  // Streaming continues after recoverable errors and reader backpressure.
  writer.submit(std::vector<uint8_t>(packet_size, 44));
  assert(read_packet(pipefd[0]) == std::vector<uint8_t>(packet_size, 44));
  close(pipefd[0]);
  writer.submit(std::vector<uint8_t>(packet_size, 55));
  wait_for([&] { return writer.failed(); });
  writer.stop();
  close(pipefd[1]);
  health.error(Error::IO);
  assert(health.fatal());
  loonar::CaptureHealth<Error> no_frames;
  no_frames.error(Error::NoFramesReceived);
  assert(no_frames.fatal());
  // A permanently stalled reader cannot hang shutdown.
  assert(pipe2(pipefd, O_NONBLOCK) == 0);
  {
    loonar::CaptureTransport blocked(pipefd[1]);
    blocked.submit(std::vector<uint8_t>(packet_size, 66));
    wait_for([&] { pollfd p{pipefd[0], POLLIN, 0}; return poll(&p, 1, 0) == 1; });
    auto start = std::chrono::steady_clock::now();
    blocked.stop();
    assert(std::chrono::steady_clock::now() - start < 500ms);
  }
  close(pipefd[0]); close(pipefd[1]);
  std::cout << "PASS: drop recovery, bounded latest queue, whole packets, EPIPE, bounded shutdown\n";
}
