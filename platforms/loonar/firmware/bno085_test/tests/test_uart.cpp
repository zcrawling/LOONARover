#include <cassert>
#include <cstdint>
#include <cstring>
#include <deque>
#include <vector>
#include <cstdio>
struct sh2_Hal_t {};
struct MockSerial {
 std::deque<uint8_t> rx; std::vector<uint8_t> tx;
 int available(){return rx.size();} int read(){int c=rx.front();rx.pop_front();return c;}
 void write(uint8_t c){tx.push_back(c);} void flush(){} void end(){}
 template<class... T> void printf(const char*,T...){}
} port,Serial;
MockSerial *uart_dev=&port;
uint32_t micros(){return 123;}
void delayMicroseconds(unsigned n){assert(n>=100);}
#include "../uart_transport.inc"
void feed(std::initializer_list<uint8_t> b){for(auto c:b)port.rx.push_back(c);}
int main(){
 uint8_t out[16];uint32_t stamp=0;
 uarthal_open(nullptr);
 assert(uarthal_read(nullptr,out,sizeof out,&stamp)==0);
 feed({0x7e,1,6,0,2,0,0x7d});
 assert(uarthal_read(nullptr,out,sizeof out,&stamp)==0);
 feed({0x5e,0x7d,0x5d,0x7e});
 assert(uarthal_read(nullptr,out,sizeof out,&stamp)==6);
 assert(out[4]==0x7e && out[5]==0x7d && stamp==123);
 feed({1,6,0,2,0,0,0,0x7e});
 assert(uarthal_read(nullptr,out,4,&stamp)==0);
 feed({1,4,0,2,0,0x7e});
 assert(uarthal_read(nullptr,out,sizeof out,&stamp)==4);
 uint8_t data[]={0x7e,0x7d};
 assert(uarthal_write(nullptr,data,2)==2);
 assert((port.tx==std::vector<uint8_t>{0x7e,1,0x7d,0x5e,0x7d,0x5d,0x7e}));
 uarthal_close(nullptr);
 puts("PASS UART: idle returns, partial escaped frame, capacity rejection/recovery, TX escaping");
}
