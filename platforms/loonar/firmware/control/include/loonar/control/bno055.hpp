#pragma once
#include <cstdint>
namespace loonar::control {
// BNO055 page0 burst 0x08..0x3A, matching bno055_uart_test.
struct Bno055Values {
  float accel[3], gyro[3], quaternion[4], linear[3], gravity[3];
  std::uint8_t calibration, status, error;
};
inline Bno055Values decodeBno055(const std::uint8_t *p) {
  auto word = [](const std::uint8_t *v) {
    return static_cast<std::int16_t>(std::uint16_t(v[0]) | (std::uint16_t(v[1]) << 8));
  };
  Bno055Values v{};
  for (unsigned i=0;i<3;++i) {
    v.accel[i]=word(p+2*i)/100.0F;
    v.gyro[i]=word(p+12+2*i)/16.0F * 0.017453292519943295F; // deg/s -> rad/s
    v.linear[i]=word(p+32+2*i)/100.0F;
    v.gravity[i]=word(p+38+2*i)/100.0F;
    v.quaternion[i]=word(p+26+2*i)/16384.0F; // x,y,z
  }
  v.quaternion[3]=word(p+24)/16384.0F; // w
  v.calibration=p[45]; v.status=p[49]; v.error=p[50];
  return v;
}
// IO provides available/read/write/now/sleep. Only the IMU task owns it.
template<class IO> class Bno055 {
  IO &io;
  bool byte(std::uint8_t &v, std::uint32_t start) {
    while (!io.available()) {
      if (std::uint32_t(io.now()-start)>=150) return false;
      io.sleep(1);
    }
    v=io.read(); return true;
  }
public:
  std::uint32_t errors=0;
  explicit Bno055(IO &port):io(port){}
  bool transaction(std::uint8_t reg, std::uint8_t *data, std::uint8_t n, bool reading) {
    for (unsigned attempt=0;attempt<3;++attempt) {
      for (unsigned i=0;i<256 && io.available();++i) io.read();
      const std::uint8_t cmd[]={0xAA,std::uint8_t(reading?1:0),reg,n};
      bool ok=io.write(cmd,4)==4;
      if (!reading) ok=ok && io.write(data,n)==n;
      const auto start=io.now();
      std::uint8_t header=0,status=0;
      ok=ok && byte(header,start) && byte(status,start);
      if (ok && !reading && header==0xEE && status==1) return true;
      if (ok && reading && header==0xBB && status==n) {
        for (unsigned i=0;i<n && ok;++i) ok=byte(data[i],start);
        if (ok) return true;
      }
      ++errors; io.sleep(200); // drain late responses before next attempt
    }
    return false;
  }
  bool write(std::uint8_t reg,std::uint8_t value) { return transaction(reg,&value,1,false); }
  bool read(std::uint8_t reg,std::uint8_t *p,std::uint8_t n) { return transaction(reg,p,n,true); }
  bool begin() {
    std::uint8_t id=0,mode=0;
    if (!read(0,&id,1) || !write(7,0) || !read(0,&id,1) || id!=0xA0 || !write(0x3D,0)) return false;
    io.sleep(30);
    if (!write(0x3E,0) || !write(0x3B,0) || !write(0x41,0x24) || !write(0x42,0) || !write(0x3D,0x0C)) return false;
    io.sleep(30);
    return read(0x3D,&mode,1) && mode==0x0C;
  }
};
}
