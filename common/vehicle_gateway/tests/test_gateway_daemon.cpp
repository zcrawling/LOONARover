#include <array>
#include <cassert>
#include <chrono>
#include <cstring>
#include <filesystem>
#include <thread>
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/wait.h>
#include <unistd.h>
#include "loonar/gateway/protocol.hpp"
namespace protocol=loonar::gateway::protocol; using loonar::gateway::MotionCommand; using loonar::gateway::Source;
int conn(const std::string& p){int f=socket(AF_UNIX,SOCK_SEQPACKET|SOCK_CLOEXEC,0);sockaddr_un a{};a.sun_family=AF_UNIX;std::strncpy(a.sun_path,p.c_str(),sizeof(a.sun_path)-1);return connect(f,reinterpret_cast<sockaddr*>(&a),sizeof(a))<0?(close(f),-1):f;} bool sendp(int f,const std::vector<std::uint8_t>& b){return send(f,b.data(),b.size(),MSG_NOSIGNAL)==static_cast<ssize_t>(b.size());}
int main(int argc,char**argv){assert(argc==2);const std::string r="/tmp/loonar-gateway-test-"+std::to_string(getpid());std::filesystem::remove_all(r);const auto child=fork();assert(child>=0);if(child==0){execl(argv[1],argv[1],"--runtime-dir",r.c_str(),static_cast<char*>(nullptr));_exit(127);}const auto cpath=r+"/cfs.sock",bpath=r+"/backend.sock";for(int i=0;i<100&&!std::filesystem::exists(cpath);++i)std::this_thread::sleep_for(std::chrono::milliseconds(10));const int c=conn(cpath),b=conn(bpath);assert(c>=0&&b>=0);assert(sendp(c,protocol::encode({protocol::Type::kHello,{}})));assert(sendp(b,protocol::encode({protocol::Type::kHello,{}})));assert(sendp(c,protocol::encode_motion(protocol::Type::kMotion,{Source::kManual,.05,0.})));std::array<std::uint8_t,protocol::kMaxPacketSize>x{};assert(recv(b,x.data(),x.size(),0)>0);assert(sendp(c,protocol::encode({protocol::Type::kStop,{}})));assert(recv(b,x.data(),x.size(),0)>0);close(c);close(b);kill(child,SIGTERM);int s{};assert(waitpid(child,&s,0)==child);std::filesystem::remove_all(r);}
