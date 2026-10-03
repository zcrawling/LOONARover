#include "../src/gyro_bias.hpp"
#include <cassert>
#include <cstdio>
int main() {
  const double a[]={0,0,1}, g[]={-2.4,1.1,-1.9};
  GyroBias c;c.start(0);
  c.add(2999,a,g);assert(c.count==0);
  for(unsigned t=3000;t<=8000;t+=20)c.add(t,a,g);
  assert(c.state==GyroBias::Valid && c.count==251);
  for(unsigned i=0;i<3;++i)assert(std::fabs(c.bias[i]-g[i])<1e-10);
  c.start(0);double fast[]={0,0,11};c.add(3000,a,fast);assert(c.state==GyroBias::Failed);
  c.start(0);c.add(3000,a,g);c.tick(3101);assert(c.state==GyroBias::Failed);
  c.start(0);c.tick(12001);assert(c.state==GyroBias::Failed);
  c.start(0);
  for(unsigned t=3000;t<=8000;t+=20){double jitter[]={double((t/20)%2 ? 2 : -2),0,0};c.add(t,a,jitter);}
  assert(c.state==GyroBias::Failed);
  c.start(0);assert(c.state==GyroBias::Settling && c.count==0 && c.bias[0]==0);
  c.fail("I2C");assert(c.state==GyroBias::Failed);
  c.start(0);double tilt[]={0,0,0.5};c.add(3000,tilt,g);assert(c.state==GyroBias::Failed);
  puts("PASS: bias recovery, warmup, motion/noise rejection, missing data, restart, I2C failure");
}
