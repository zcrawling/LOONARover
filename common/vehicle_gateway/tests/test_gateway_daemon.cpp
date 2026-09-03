#include <array>
#include <cassert>
#include <chrono>
#include <cstring>
#include <filesystem>
#include <optional>
#include <thread>
#include <vector>

#include <poll.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/wait.h>
#include <unistd.h>

#include "loonar/gateway/protocol.hpp"

namespace protocol = loonar::gateway::protocol;
using loonar::gateway::MotionCommand;
using loonar::gateway::Source;

namespace {
int connect_socket(const std::string& path) {
  const int fd = socket(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0);
  sockaddr_un address{};
  address.sun_family = AF_UNIX;
  std::strncpy(address.sun_path, path.c_str(), sizeof(address.sun_path) - 1);
  if (connect(fd, reinterpret_cast<sockaddr*>(&address), sizeof(address)) < 0) {
    close(fd);
    return -1;
  }
  return fd;
}

bool send_packet(int fd, const std::vector<std::uint8_t>& bytes) {
  return send(fd, bytes.data(), bytes.size(), MSG_NOSIGNAL) == static_cast<ssize_t>(bytes.size());
}

std::optional<protocol::Packet> receive_packet(int fd, int timeout_ms) {
  pollfd descriptor{fd, POLLIN, 0};
  if (poll(&descriptor, 1, timeout_ms) <= 0) return std::nullopt;
  std::array<std::uint8_t, protocol::kMaxPacketSize> bytes{};
  const auto size = recv(fd, bytes.data(), bytes.size(), 0);
  if (size <= 0) return std::nullopt;
  return protocol::decode(std::span<const std::uint8_t>(bytes.data(), static_cast<std::size_t>(size)));
}

MotionCommand receive_backend_motion(int backend) {
  const auto packet = receive_packet(backend, 500);
  assert(packet);
  assert(packet->type == protocol::Type::kBackendMotion);
  const auto motion = protocol::decode_motion(*packet);
  assert(motion);
  return *motion;
}
}  // namespace

int main(int argc, char** argv) {
  assert(argc == 2);
  const std::string runtime = "/tmp/loonar-gateway-test-" + std::to_string(getpid());
  std::filesystem::remove_all(runtime);
  const auto child = fork();
  assert(child >= 0);
  if (child == 0) {
    execl(argv[1], argv[1], "--runtime-dir", runtime.c_str(), static_cast<char*>(nullptr));
    _exit(127);
  }

  const auto cfs_path = runtime + "/cfs.sock";
  const auto ros_path = runtime + "/ros.sock";
  const auto backend_path = runtime + "/backend.sock";
  for (int i = 0; i < 100 && !std::filesystem::exists(cfs_path); ++i) {
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
  }
  const int cfs = connect_socket(cfs_path);
  const int ros = connect_socket(ros_path);
  const int backend = connect_socket(backend_path);
  assert(cfs >= 0 && ros >= 0 && backend >= 0);
  assert(send_packet(cfs, protocol::encode({protocol::Type::kHello, {}})));
  assert(send_packet(ros, protocol::encode({protocol::Type::kHello, {}})));
  assert(send_packet(backend, protocol::encode({protocol::Type::kHello, {}})));
  assert(receive_packet(cfs, 500)->type == protocol::Type::kStatus);
  assert(receive_packet(ros, 500)->type == protocol::Type::kStatus);
  assert(receive_packet(backend, 500)->type == protocol::Type::kStatus);

  const loonar::gateway::VehicleStatus vehicle{1000, loonar::gateway::kBatteryVoltageValid,
                                                11.7, 0.0, 1.0, 2.0, 0.5, 0.4, 1.0, 0.1, 0.2, 0.3};
  assert(send_packet(backend, protocol::encode_vehicle_status(vehicle)));
  const auto forwarded_status = receive_packet(cfs, 500);
  assert(forwarded_status && forwarded_status->type == protocol::Type::kBackendStatus);
  const auto decoded_status = protocol::decode_vehicle_status(*forwarded_status);
  assert(decoded_status && decoded_status->battery_voltage == 11.7);

  assert(send_packet(cfs, protocol::encode_motion(protocol::Type::kMotion, {Source::kManual, 0.4, 1.0})));
  const auto manual = receive_backend_motion(backend);
  assert(manual.source == Source::kManual && manual.linear_mps == 0.4 && manual.angular_radps == 1.0);

  assert(send_packet(ros, protocol::encode_motion(protocol::Type::kMotion, {Source::kAuto, 0.2, 0.3})));
  assert(!receive_packet(backend, 100));

  assert(send_packet(cfs, protocol::encode({protocol::Type::kStop, {}})));
  const auto stopped = receive_backend_motion(backend);
  assert(stopped.source == Source::kStop && stopped.linear_mps == 0.0 && stopped.angular_radps == 0.0);
  assert(send_packet(cfs, protocol::encode({protocol::Type::kSelectPayload, {}})));
  assert(!receive_packet(backend, 100));
  assert(send_packet(ros, protocol::encode_motion(protocol::Type::kMotion, {Source::kAuto, 0.2, 0.3})));
  assert(!receive_packet(backend, 100));

  assert(send_packet(cfs, protocol::encode({protocol::Type::kStop, {}})));
  assert(receive_backend_motion(backend).source == Source::kStop);
  assert(send_packet(cfs, protocol::encode({protocol::Type::kSelectReaction, {}})));
  assert(!receive_packet(backend, 100));

  assert(send_packet(cfs, protocol::encode({protocol::Type::kSelectAuto, {}})));
  assert(send_packet(ros, protocol::encode_motion(protocol::Type::kMotion, {Source::kAuto, 0.2, 0.3})));
  const auto automatic = receive_backend_motion(backend);
  assert(automatic.source == Source::kAuto && automatic.linear_mps == 0.2 && automatic.angular_radps == 0.3);

  close(cfs);
  close(ros);
  close(backend);
  kill(child, SIGTERM);
  int status{};
  assert(waitpid(child, &status, 0) == child);
  assert(WIFEXITED(status) && WEXITSTATUS(status) == 0);
  std::filesystem::remove_all(runtime);
}
