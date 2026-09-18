#include <array>
#include <chrono>
#include <cstring>
#include <iostream>
#include <string>
#include <thread>
#include <poll.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
#include "loonar/gateway/protocol.hpp"

namespace {
namespace protocol = loonar::gateway::protocol;
using loonar::gateway::Mode; using loonar::gateway::MotionCommand; using loonar::gateway::Source;
int connect_socket(const std::string& path) { int fd = socket(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0); if (fd < 0) return -1; sockaddr_un a{}; a.sun_family = AF_UNIX; std::strncpy(a.sun_path, path.c_str(), sizeof(a.sun_path)-1); if (connect(fd, reinterpret_cast<const sockaddr*>(&a), sizeof(a)) < 0) { close(fd); return -1; } return fd; }
bool send_packet(int fd, const std::vector<std::uint8_t>& b) { return send(fd, b.data(), b.size(), MSG_NOSIGNAL) == static_cast<ssize_t>(b.size()); }
void show(const loonar::gateway::Status& s) { const char* m=s.mode==Mode::kStop?"STOP":s.mode==Mode::kManual?"MANUAL":s.mode==Mode::kAuto?"AUTO":s.mode==Mode::kPayload?"PAYLOAD":"REACTION"; std::cout<<"mode="<<m; if(s.last_received) std::cout<<" last="<<(s.last_received->source==Source::kManual?"manual":s.last_received->source==Source::kAuto?"auto":"stop")<<" linear="<<s.last_received->linear_mps<<" angular="<<s.last_received->angular_radps; std::cout<<'\n'; }
}
int main(int argc, char** argv) {
  if (argc < 3) { std::cerr << "usage: vehicle_gatewayctl {manual|stop|auto|payload|reaction|monitor|vehicle-status} SOCKET [ARGS]\n"; return 2; }
  const std::string action=argv[1]; const int fd=connect_socket(argv[2]); if(fd<0){std::perror("connect");return 1;} if(!send_packet(fd,protocol::encode({protocol::Type::kHello,{}})))return 1;
  if(action=="stop") return send_packet(fd,protocol::encode({protocol::Type::kStop,{}}))?0:1;
  if(action=="auto") return send_packet(fd,protocol::encode({protocol::Type::kSelectAuto,{}}))?0:1;
  if(action=="payload") return send_packet(fd,protocol::encode({protocol::Type::kSelectPayload,{}}))?0:1;
  if(action=="reaction") return send_packet(fd,protocol::encode({protocol::Type::kSelectReaction,{}}))?0:1;
  if(action=="manual"&&(argc==5||argc==6)){ MotionCommand c{Source::kManual,std::stod(argv[3]),std::stod(argv[4])}; const int duration=argc==6?std::stoi(argv[5]):0; const auto end=std::chrono::steady_clock::now()+std::chrono::milliseconds(duration); do { if(!send_packet(fd,protocol::encode_motion(protocol::Type::kMotion,c)))return 1; if(duration>0)std::this_thread::sleep_for(std::chrono::milliseconds(50)); } while(duration>0&&std::chrono::steady_clock::now()<end); return 0; }
  if(action=="vehicle-status"&&argc==4){const auto now=std::chrono::system_clock::now().time_since_epoch();loonar::gateway::VehicleStatus status{};status.timestamp_ms=static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::milliseconds>(now).count());status.valid_flags=loonar::gateway::kBatteryVoltageValid;status.battery_voltage=std::stod(argv[3]);return send_packet(fd,protocol::encode_vehicle_status(status))?0:1;}
  if(action=="monitor"&&argc==3) for(;;){ pollfd p{fd,POLLIN,0}; if(poll(&p,1,1000)>0){std::array<std::uint8_t,protocol::kMaxPacketSize>b{};const auto n=recv(fd,b.data(),b.size(),0);if(n<=0)break;const auto q=protocol::decode(std::span<const std::uint8_t>(b.data(),static_cast<std::size_t>(n)));if(q)if(const auto s=protocol::decode_status(*q))show(*s);} }
  return action=="monitor"?0:2;
}
