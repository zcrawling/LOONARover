#pragma once
#include "pca_infer.h"

namespace loonar_pca {
// BENCH ONLY: fitted from 126 quiet, five-second observations across seven
// sensor-test log sessions (2026-09-27 and 2026-09-29; 18 per session).
// No labeled field sites or independent science validation are available.
// The threshold is the in-sample 95th percentile, not a field false-alarm rate.
static constexpr char kModelId[] = "BENCH_FIT_261019";
static constexpr bool kGroundModel = true;
static constexpr bool kDemoModel = true;
static constexpr PcaModel kModel = {
    2,
    {31.7438316f, 26.4642067f, 26.6014290f},
    {2.79888272f, 1.35770774f, 2.09772944f},
    {{0.562430441f, 0.584474444f, 0.584860384f},
     {0.826815128f, -0.403529465f, -0.391842753f}},
    {2.83516455f, 0.150898173f},
    0.0440246016f,
    5.45617676f,
    1.46362305f
};
}  // namespace loonar_pca
