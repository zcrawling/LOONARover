#pragma once
#include "pca_infer.h"

namespace loonar_pca {
// DEMO ONLY: center values were rounded from the early stable part of
// device-monitor-260927-141232.log. All spreads, axes and threshold below
// are illustrative and were NOT fitted or validated on normal sessions.
static constexpr char kModelId[] = "DEMO_ONLY_260927";
static constexpr bool kGroundModel = true;
static constexpr bool kDemoModel = true;
static constexpr PcaModel kModel = {
    2,
    {34.25f, 27.20f, 27.88f},
    {2.0f, 1.0f, 1.0f},
    {{1.0f, 0.0f, 0.0f}, {0.0f, 0.70710678f, 0.70710678f}},
    {1.0f, 1.0f},
    1.0f,
    1.0f,
    9.0f
};
}  // namespace loonar_pca
