#include "loonar/control/reaction_wheel.hpp"
#include "loonar/control/board_pins.h"
#include <cassert>
#include <cstdint>
#include <iostream>
using namespace loonar::mcu;
static void cycle(unsigned side, std::uint32_t origin) {
  ReactionWheel w; w.begin(origin);
  assert(!w.start(side,origin));
  w.tick(origin+4999,true); assert(!w.start(side,origin+4999));
  auto now=origin+5000;
  w.tick(now,true); assert(w.start(side,now));
  assert(w.esc_us==(side==1?1513:1463) && w.servo_us==1500);
  assert(!w.start(side==1?2:1,now));
  const auto first=side==1?5000U:10000U;
  w.tick(now+first-1,true); assert(w.state==ReactionWheel::State::First);
  now+=first; w.tick(now,true); assert(w.esc_us==(side==1?1538:1438));
  w.tick(now+9999,true); assert(w.state==ReactionWheel::State::Second);
  now+=10000; w.tick(now,true); assert(w.esc_us==1488 && w.servo_us==1500);
  w.tick(now+9,true); assert(w.servo_us==1500);
  now+=10; w.tick(now,true); assert(w.servo_us==(side==1?800:2200));
  w.tick(now+2999,true); assert(w.active());
  now+=3000; w.tick(now,true); assert(!w.active() && w.esc_us==1488 && w.servo_us==1500);
  w.tick(now+100000,true); assert(!w.active());
}
int main() {
  static_assert(loonar::control::pins::kReactionEsc==2);
  static_assert(loonar::control::pins::kReactionServo==6);
  cycle(1,0); cycle(2,0); cycle(1,0xfffffff0U); cycle(2,0xfffffff0U);
  for(unsigned phase=0;phase<4;++phase) {
    ReactionWheel w; w.begin(0); w.tick(5000,true); assert(w.start(1,5000));
    if(phase>=1) w.tick(10000,true);
    if(phase>=2) w.tick(20000,true);
    if(phase>=3) w.tick(20010,true);
    auto bad=w.config; bad.servo_left=799; assert(!w.configure(bad));
    assert(!w.configure(w.config));
    w.stop(); assert(w.esc_us==1488 && w.servo_us==1500 && !w.active());
    assert(w.start(2,50000)); w.tick(50001,false);
    assert(!w.active() && w.esc_us==1488 && w.servo_us==1500);
    w.tick(100000,true); assert(!w.active());
  }
  ReactionWheel w; auto c=w.config; assert(c.valid());
  c.left_second_offset=1000; assert(!w.configure(c));
  c=w.config; c.servo_delay_ms=0; assert(!c.valid());
  c=w.config; c.servo_hold_ms=10001; assert(!c.valid());
  c=w.config; c.left_first_offset=30; assert(w.configure(c));
  w.begin(0); w.stop(); w.tick(4999,true); assert(!w.start(1,4999));
  std::cout << "REACTION_WHEEL_OK: left/right timing, neutral, STOP, inhibit, busy, wrap, config\n";
}
