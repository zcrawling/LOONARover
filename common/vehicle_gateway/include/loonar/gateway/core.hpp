#pragma once

#include "loonar/gateway/types.hpp"

namespace loonar::gateway {

class GatewayCore {
 public:
  [[nodiscard]] const Status& status() const noexcept { return status_; }
  Action submit(const MotionCommand& command);
  Action stop();
  Action select_auto();

 private:
  [[nodiscard]] Action ignored() const;
  Status status_{};
};

}  // namespace loonar::gateway
