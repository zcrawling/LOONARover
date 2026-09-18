#include <array>
#include <cerrno>
#include <chrono>
#include <csignal>
#include <cstring>
#include <filesystem>
#include <iostream>
#include <optional>
#include <string>

#include <fcntl.h>
#include <poll.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <unistd.h>

#include "loonar/gateway/core.hpp"
#include "loonar/gateway/protocol.hpp"

namespace {
using loonar::gateway::Action;
using loonar::gateway::GatewayCore;
using loonar::gateway::MotionCommand;
using loonar::gateway::Source;
namespace protocol = loonar::gateway::protocol;

volatile std::sig_atomic_t g_running = 1;
void signal_handler(int) { g_running = 0; }

struct Peer { int fd{-1}; bool hello{false}; Source source{Source::kStop}; };

const char* mode_name(loonar::gateway::Mode mode) {
  switch (mode) {
    case loonar::gateway::Mode::kAuto: return "AUTO";
    case loonar::gateway::Mode::kManual: return "MANUAL";
    case loonar::gateway::Mode::kStop: return "STOP";
    case loonar::gateway::Mode::kPayload: return "PAYLOAD";
    case loonar::gateway::Mode::kReaction: return "REACTION";
  }
  return "UNKNOWN";
}

const char* packet_name(protocol::Type type) {
  switch (type) {
    case protocol::Type::kHello: return "HELLO";
    case protocol::Type::kMotion: return "MOTION";
    case protocol::Type::kStop: return "STOP";
    case protocol::Type::kSelectAuto: return "AUTO";
    case protocol::Type::kSelectPayload: return "PAYLOAD";
    case protocol::Type::kSelectReaction: return "REACTION";
    case protocol::Type::kStatus: return "STATUS";
    case protocol::Type::kBackendMotion: return "BACKEND_MOTION";
    case protocol::Type::kBackendStatus: return "BACKEND_STATUS";
  }
  return "UNKNOWN";
}

void print_status(const loonar::gateway::Status& status) {
  std::cout << "gateway mode=" << mode_name(status.mode);
  if (status.last_received) {
    std::cout << " last_linear=" << status.last_received->linear_mps
              << " last_angular=" << status.last_received->angular_radps;
  }
  std::cout << '\n' << std::flush;
}

int listener(const std::string& path) {
  if (path.size() >= sizeof(sockaddr_un::sun_path)) return -1;
  const int fd = socket(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC | SOCK_NONBLOCK, 0);
  if (fd < 0) return -1;
  sockaddr_un address{}; address.sun_family = AF_UNIX;
  std::strncpy(address.sun_path, path.c_str(), sizeof(address.sun_path) - 1);
  unlink(path.c_str());
  if (bind(fd, reinterpret_cast<const sockaddr*>(&address), sizeof(address)) < 0 || listen(fd, 4) < 0) {
    close(fd); return -1;
  }
  chmod(path.c_str(), 0660); return fd;
}

void close_peer(Peer& peer) { if (peer.fd >= 0) close(peer.fd); peer = {}; }

bool send_bytes(int fd, const std::vector<std::uint8_t>& bytes) {
  return fd >= 0 && send(fd, bytes.data(), bytes.size(), MSG_NOSIGNAL) == static_cast<ssize_t>(bytes.size());
}

void send_status(const Peer& peer, const loonar::gateway::Status& status) {
  if (peer.hello) (void)send_bytes(peer.fd, protocol::encode_status(status));
}

void send_backend(const Peer& backend, const Action& action) {
  if (!backend.hello) return;
  MotionCommand command{};
  if (action.motion.has_value()) command = *action.motion;
  else {
    command.source = Source::kStop;
  }
  (void)send_bytes(backend.fd, protocol::encode_motion(protocol::Type::kBackendMotion, command));
}

void distribute(const Peer& cfs, const Peer& ros, const Peer& backend, const Action& action) {
  send_status(cfs, action.status); send_status(ros, action.status);
  if (action.send_zero || action.motion.has_value()) send_backend(backend, action);
}

void accept_peer(int listener_fd, Peer& peer, Source source, GatewayCore& core) {
  sockaddr_un address{}; socklen_t size = sizeof(address);
  const int fd = accept4(listener_fd, reinterpret_cast<sockaddr*>(&address), &size, SOCK_CLOEXEC | SOCK_NONBLOCK);
  if (fd < 0) return;
  close_peer(peer); peer = {.fd = fd, .hello = false, .source = source};
  send_status(peer, core.status());
}

void process_peer(Peer& peer, bool is_backend, GatewayCore& core, const Peer& cfs, const Peer& ros, const Peer& backend) {
  std::array<std::uint8_t, protocol::kMaxPacketSize> buffer{};
  const auto received = recv(peer.fd, buffer.data(), buffer.size(), MSG_DONTWAIT);
  if (received <= 0) {
    if (received == 0 || (errno != EAGAIN && errno != EWOULDBLOCK)) {
      close_peer(peer);
    }
    return;
  }
  const auto packet = protocol::decode(std::span<const std::uint8_t>(buffer.data(), static_cast<std::size_t>(received)));
  if (!packet) { close_peer(peer); return; }
  std::cout << "received source=" << (is_backend ? "backend" : peer.source == Source::kManual ? "cfs" : "ros")
            << " command=" << packet_name(packet->type) << '\n' << std::flush;
  if (!peer.hello) {
    if (packet->type != protocol::Type::kHello || !packet->payload.empty()) { close_peer(peer); return; }
    peer.hello = true; send_status(peer, core.status()); return;
  }
  if (is_backend) {
    if (packet->type == protocol::Type::kBackendStatus && protocol::decode_vehicle_status(*packet) && cfs.hello) {
      (void)send_bytes(cfs.fd, protocol::encode(*packet));
    }
    return;
  }
  if (peer.source == Source::kManual && packet->type == protocol::Type::kStop && packet->payload.empty()) {
    distribute(cfs, ros, backend, core.stop());
    return;
  }
  if (peer.source == Source::kManual && packet->type == protocol::Type::kSelectAuto && packet->payload.empty()) {
    distribute(cfs, ros, backend, core.select_auto());
    return;
  }
  if (peer.source == Source::kManual && packet->type == protocol::Type::kSelectPayload && packet->payload.empty()) {
    distribute(cfs, ros, backend, core.select_payload());
    return;
  }
  if (peer.source == Source::kManual && packet->type == protocol::Type::kSelectReaction && packet->payload.empty()) {
    distribute(cfs, ros, backend, core.select_reaction());
    return;
  }
  const auto motion = protocol::decode_motion(*packet);
  if (motion && motion->source == peer.source) distribute(cfs, ros, backend, core.submit(*motion));
}
}  // namespace

int main(int argc, char** argv) {
  std::string runtime_dir = "/run/loonar/vehicle-gateway";
  if (argc == 3 && std::string(argv[1]) == "--runtime-dir") runtime_dir = argv[2];
  else if (argc != 1) { std::cerr << "usage: vehicle_gatewayd [--runtime-dir PATH]\n"; return 2; }
  std::filesystem::create_directories(runtime_dir);
  const std::string cfs_path = runtime_dir + "/cfs.sock";
  const std::string ros_path = runtime_dir + "/ros.sock";
  const std::string backend_path = runtime_dir + "/backend.sock";
  const int cfs_listener = listener(cfs_path), ros_listener = listener(ros_path), backend_listener = listener(backend_path);
  if (cfs_listener < 0 || ros_listener < 0 || backend_listener < 0) { std::cerr << "failed to create gateway sockets\n"; return 1; }
  std::signal(SIGINT, signal_handler); std::signal(SIGTERM, signal_handler);
  GatewayCore core; Peer cfs{.source = Source::kManual}, ros{.source = Source::kAuto}, backend{.source = Source::kStop};
  auto next_status = std::chrono::steady_clock::now();
  while (g_running != 0) {
    std::array<pollfd, 6> fds{{{cfs_listener, POLLIN, 0}, {ros_listener, POLLIN, 0}, {backend_listener, POLLIN, 0},
                                {cfs.fd, POLLIN | POLLHUP, 0}, {ros.fd, POLLIN | POLLHUP, 0}, {backend.fd, POLLIN | POLLHUP, 0}}};
    (void)poll(fds.data(), static_cast<nfds_t>(fds.size()), 20);
    if ((fds[0].revents & POLLIN) != 0) accept_peer(cfs_listener, cfs, Source::kManual, core);
    if ((fds[1].revents & POLLIN) != 0) accept_peer(ros_listener, ros, Source::kAuto, core);
    if ((fds[2].revents & POLLIN) != 0) accept_peer(backend_listener, backend, Source::kStop, core);
    if (cfs.fd >= 0 && fds[3].revents != 0) process_peer(cfs, false, core, cfs, ros, backend);
    if (ros.fd >= 0 && fds[4].revents != 0) process_peer(ros, false, core, cfs, ros, backend);
    if (backend.fd >= 0 && fds[5].revents != 0) process_peer(backend, true, core, cfs, ros, backend);
    const auto now = std::chrono::steady_clock::now();
    if (now >= next_status) {
      print_status(core.status());
      next_status = now + std::chrono::seconds(1);
    }
  }
  close_peer(cfs); close_peer(ros); close_peer(backend); close(cfs_listener); close(ros_listener); close(backend_listener);
  unlink(cfs_path.c_str()); unlink(ros_path.c_str()); unlink(backend_path.c_str()); return 0;
}
