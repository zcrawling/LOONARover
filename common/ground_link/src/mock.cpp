#include "loonar/ground_link/frame.hpp"

#include <array>
#include <cerrno>
#include <cstring>
#include <iostream>
#include <string>

#include <netdb.h>
#include <sys/socket.h>
#include <unistd.h>

namespace gl = loonar::ground_link;
namespace {
int connect_tcp(const char* host, const char* port) {
  addrinfo hints{}; hints.ai_family=AF_UNSPEC; hints.ai_socktype=SOCK_STREAM;
  addrinfo* addresses=nullptr; if (getaddrinfo(host,port,&hints,&addresses)!=0) return -1;
  int fd=-1; for(auto* at=addresses;at;at=at->ai_next){fd=socket(at->ai_family,at->ai_socktype|SOCK_CLOEXEC,at->ai_protocol);if(fd>=0&&connect(fd,at->ai_addr,at->ai_addrlen)==0)break;if(fd>=0)close(fd);fd=-1;}
  freeaddrinfo(addresses); return fd;
}
bool send_all(int fd,const std::vector<std::uint8_t>& bytes){std::size_t at{};while(at<bytes.size()){const auto n=send(fd,bytes.data()+at,bytes.size()-at,MSG_NOSIGNAL);if(n<0&&errno==EINTR)continue;if(n<=0)return false;at+=static_cast<std::size_t>(n);}return true;}
const char* type_name(gl::Type type){switch(type){case gl::Type::kStopCommand:return"STOP_CMD";case gl::Type::kManualCommand:return"MANUAL_CMD";case gl::Type::kAutoCommand:return"AUTO_CMD";case gl::Type::kPayloadCommand:return"PAYLOAD_CMD";case gl::Type::kReactionCommand:return"REACTION_CMD";case gl::Type::kCommandResult:return"COMMAND_RESULT";case gl::Type::kGatewayStatus:return"GATEWAY_STATUS";case gl::Type::kVehicleStatus:return"VEHICLE_STATUS";case gl::Type::kLoonarMcuStatus:return"LOONAR_MCU_STATUS";case gl::Type::kDeviceStatus:return"DEVICE_STATUS";case gl::Type::kEvent:return"EVENT";}return"UNKNOWN";}
}
int main(int argc,char**argv){
  if(argc<4){std::cerr<<"usage: ground_link_mock HOST PORT {stop|manual|auto|payload|reaction|monitor} [args]\n";return 2;}
  const int fd=connect_tcp(argv[1],argv[2]);if(fd<0){std::perror("connect");return 1;}const std::string command=argv[3];gl::Frame frame{};frame.sequence=1;
  if(command=="stop")frame.type=gl::Type::kStopCommand;
  else if(command=="auto")frame.type=gl::Type::kAutoCommand;
  else if(command=="manual"&&argc==6){frame.type=gl::Type::kManualCommand;frame.payload=gl::encode_manual({std::stod(argv[4]),std::stod(argv[5])});}
  else if((command=="payload"||command=="reaction")&&argc>=5){
    frame.type=command=="payload"?gl::Type::kPayloadCommand:gl::Type::kReactionCommand;
    const auto opcode = argc>=6 ? static_cast<std::uint16_t>(std::stoul(argv[5])) : std::uint16_t{};
    frame.payload=gl::encode_activity({std::stoull(argv[4]),opcode,{}});
  }
  else if(command!="monitor"){std::cerr<<"invalid command arguments\n";return 2;}
  if(command!="monitor"&&!send_all(fd,gl::encode(frame))){std::perror("send");return 1;}
  gl::StreamDecoder decoder;std::array<std::uint8_t,1024> bytes{};
  for(;;){const auto n=recv(fd,bytes.data(),bytes.size(),0);if(n==0)break;if(n<0){if(errno==EINTR)continue;std::perror("recv");return 1;}if(!decoder.append(std::span<const std::uint8_t>(bytes.data(),static_cast<std::size_t>(n)))){std::cerr<<"receive buffer overflow\n";return 1;}while(const auto received=decoder.next()){std::cout<<"type="<<type_name(received->type)<<" sequence="<<received->sequence<<" payload_bytes="<<received->payload.size();if(received->type==gl::Type::kCommandResult){if(const auto result=gl::decode_command_result(received->payload))std::cout<<" cfs_received="<<result->cfs_received<<" forwarded="<<result->adapter_forwarded<<" mode="<<static_cast<unsigned>(result->current_mode)<<" result="<<static_cast<unsigned>(result->result_code);}else if(received->type==gl::Type::kGatewayStatus){if(const auto status=gl::decode_gateway_status(received->payload))std::cout<<" mode="<<static_cast<unsigned>(status->mode)<<" linear="<<status->last_linear_mps<<" angular="<<status->last_angular_radps;}else if(received->type==gl::Type::kVehicleStatus){if(const auto status=gl::decode_vehicle_status(received->payload))std::cout<<" valid=0x"<<std::hex<<status->valid_flags<<std::dec<<" battery_voltage="<<status->battery_voltage<<" odom=("<<status->odom_x<<','<<status->odom_y<<','<<status->odom_yaw<<')';}std::cout<<'\n'<<std::flush;}}
}
