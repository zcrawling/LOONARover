#pragma once
#include <cmath>
#include <cstdint>

// Stillness thresholds are conservative bench defaults, not proof of no rotation.
struct GyroBias {
  enum State { Idle, Settling, Collecting, Valid, Failed } state = Idle;
  uint32_t started=0, first=0, last=0;
  unsigned count=0;
  double mean[6]{}, m2[6]{}, bias[3]{};
  const char *reason="not started";
  void start(uint32_t now) {
    *this=GyroBias{}; started=now; state=Settling; reason="keep stationary";
  }
  bool active() const { return state==Settling || state==Collecting; }
  void fail(const char *why) { if(active()) {state=Failed; reason=why;} }
  void tick(uint32_t now) {
    if (!active()) return;
    if (now-started>12000) fail("sample timeout");
    else if (state==Collecting && count && now-last>100) fail("sample gap >100ms");
  }
  void add(uint32_t now, const double a[3], const double g[3]) {
    tick(now);
    if (!active() || now-started<3000) return;
    if(state==Settling) {state=Collecting; first=now;}
    double norm=0;
    for(unsigned i=0;i<3;++i) {
      if(!std::isfinite(a[i]) || !std::isfinite(g[i])) {fail("nonfinite sample");return;}
      norm+=a[i]*a[i];
      if(std::fabs(g[i])>10) {fail("gyro >10deg/s");return;}
    }
    if(norm<0.85*0.85 || norm>1.15*1.15) {fail("accel magnitude outside 0.85..1.15g");return;}
    last=now; ++count;
    for(unsigned i=0;i<6;++i) {
      double v=i<3 ? a[i] : g[i-3];
      const double d=v-mean[i]; mean[i]+=d/count; m2[i]+=d*(v-mean[i]);
    }
    if(count<250 || now-first<5000) return;
    for(unsigned i=0;i<6;++i) {
      double limit=i<3 ? 0.03 : 0.5;
      if(m2[i]/(count-1)>limit*limit) {fail(i<3 ? "accel variation" : "gyro variation");return;}
    }
    for(unsigned i=0;i<3;++i) bias[i]=mean[i+3];
    state=Valid; reason="OK";
  }
  const char *name() const {
    switch(state) {
      case Settling:return "SETTLING"; case Collecting:return "COLLECTING";
      case Valid:return "OK"; case Failed:return "FAILED"; default:return "IDLE";
    }
  }
};
