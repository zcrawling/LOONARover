#include <cassert>
#include <cstdint>
#include <cstring>
#include <vector>
#include <cstdio>
constexpr int LOW=0,HIGH=1,MSBFIRST=1,SPI_MODE3=3,SH2_ERR_TIMEOUT=-6;
struct sh2_Hal_t {};
struct SPISettings { SPISettings(int,int,int) {} };
uint8_t diag_int_pin=9,diag_cs_pin=10;
int interrupt_level=HIGH,cs=HIGH,selects=0;
uint32_t now=0;
uint32_t micros(){return now++;}
void delayMicroseconds(unsigned n){now+=n;}
int digitalRead(uint8_t){return interrupt_level;}
void digitalWrite(uint8_t pin,int level){assert(pin==10);cs=level;if(!level)++selects;}
struct MockSPI {
  std::vector<uint8_t> rx,tx;
  unsigned pos=0;
  void beginTransaction(SPISettings){assert(cs==HIGH);}
  void endTransaction(){assert(cs==HIGH);}
  uint8_t transfer(uint8_t value){
    assert(cs==LOW);interrupt_level=HIGH; // INT is acknowledged by CS.
    tx.push_back(value);return pos<rx.size()?rx[pos++]:0;
  }
} spi;
MockSPI *diag_spi=&spi;
struct {unsigned reads=0,writes=0,int_timeouts=0,zero_headers=0,oversized=0;
 uint8_t headers[8][4]{},tx[8]{};unsigned tx_size=0;} trace;
#include "../spi_transport.inc"
int main(){
 uint8_t out[16]{};uint32_t stamp=0;
 assert(spihal_open(nullptr)==0);spihal_close(nullptr);
 assert(spihal_read(nullptr,out,16,&stamp)==0 && selects==0);
 interrupt_level=LOW;spi.rx={6,0,2,3,0xf8,0x01};
 assert(spihal_read(nullptr,out,16,&stamp)==6);
 assert(selects==1 && spi.pos==6 && out[4]==0xf8 && out[5]==1);
 interrupt_level=LOW;spi.pos=0;spi.rx={0xff,0xff,0xff,0xff};
 assert(spihal_read(nullptr,out,16,&stamp)==0 && trace.oversized==1 && cs==HIGH);
 auto start=now;interrupt_level=HIGH;
 assert(spihal_write(nullptr,out,6)==SH2_ERR_TIMEOUT);
 assert(now-start>=100000 && now-start<100100);
 interrupt_level=LOW;spi.tx.clear();out[0]=6;out[4]=0xf9;
 assert(spihal_write(nullptr,out,6)==6 && spi.tx.size()==6 && spi.tx[4]==0xf9);
 puts("PASS: idle read, single-CS packet with INT deassertion, bounds, write timeout, write packet");
}
