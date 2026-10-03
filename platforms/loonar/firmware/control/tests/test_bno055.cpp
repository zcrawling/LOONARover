#include "loonar/control/bno055.hpp"
#include <cassert>
#include <cmath>
#include <deque>
#include <vector>
struct Port {
  std::uint32_t time=0;
  std::deque<unsigned char> rx;
  std::vector<unsigned char> regs=std::vector<unsigned char>(256,0);
  unsigned pending=0, requests=0;
  bool silent=false, malformed=false;
  int available(){return rx.size();}
  int read(){int x=rx.front();rx.pop_front();return x;}
  std::uint32_t now(){return time;}
  void sleep(unsigned t){time+=t;}
  std::size_t write(const std::uint8_t *p,std::size_t n){
    if(n==4){
      assert(p[0]==0xAA);++requests;
      if(silent)return n;
      if(p[1]){rx.push_back(malformed?0xCC:0xBB);rx.push_back(p[3]);
        for(unsigned i=0;i<p[3];++i)rx.push_back(regs[p[2]+i]);}
      else pending=p[2];
    }else {regs[pending]=p[0];if(!silent){rx.push_back(0xEE);rx.push_back(1);}}
    return n;
  }
};
int main(){
  std::uint8_t p[51]{};
  auto put=[&](int offset,std::int16_t v){p[offset]=v&255;p[offset+1]=std::uint16_t(v)>>8;};
  put(0,-981);put(12,1440);put(24,16384);put(32,-100);put(42,981);
  p[45]=0xFF;p[49]=5;
  auto v=loonar::control::decodeBno055(p);
  assert(std::fabs(v.accel[0]+9.81F)<.0001F);
  assert(std::fabs(v.gyro[0]-1.5707963F)<.0001F);
  assert(v.quaternion[3]==1 && v.quaternion[0]==0);
  assert(v.linear[0]==-1 && std::fabs(v.gravity[2]-9.81F)<.0001F);
  Port port;port.regs[0]=0xA0;
  loonar::control::Bno055<Port> bno(port);
  assert(bno.begin());assert(port.regs[0x3D]==12);assert(port.regs[0x3B]==0);
  port.silent=true;auto start=port.time;std::uint8_t id;
  assert(!bno.read(0,&id,1));assert(port.time-start==1050);assert(bno.errors==3);
  port.silent=false;port.rx={0xBB,1,0x99}; // discard late reply
  assert(bno.read(0,&id,1) && id==0xA0);
  port.malformed=true;assert(!bno.read(0,&id,1));assert(bno.errors==6);
  port.malformed=false;assert(bno.begin());
}
