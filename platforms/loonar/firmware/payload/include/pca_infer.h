#pragma once

#include <cmath>

namespace loonar_pca {

// Input order: magnetic field magnitude [uT], IR object temperature [C],
// probe temperature [C]. This is independent of the older 8-station firmware.
struct PcaModel {
  int components_used;
  float mean[3];
  float scale[3];
  float axes[2][3];
  float pc_variance[2];
  float q_scale;
  float t2_scale;
  float threshold;
};

struct PcaResult {
  float q_residual;
  float t2_distance;
  float novelty;
  bool candidate;
};

inline PcaResult score(const PcaModel &model, const float input[3]) {
  float standardized[3] = {};
  float projected[2] = {};
  float reconstructed[3] = {};
  for (int j = 0; j < 3; ++j) {
    standardized[j] = (input[j] - model.mean[j]) / model.scale[j];
  }
  for (int i = 0; i < model.components_used; ++i) {
    for (int j = 0; j < 3; ++j)
      projected[i] += standardized[j] * model.axes[i][j];
  }
  float t2 = 0.0f;
  for (int i = 0; i < model.components_used; ++i) {
    t2 += projected[i] * projected[i] / model.pc_variance[i];
    for (int j = 0; j < 3; ++j)
      reconstructed[j] += projected[i] * model.axes[i][j];
  }
  float q = 0.0f;
  for (int j = 0; j < 3; ++j) {
    const float residual = standardized[j] - reconstructed[j];
    q += residual * residual;
  }
  const float q_ratio = q / model.q_scale;
  const float t2_ratio = t2 / model.t2_scale;
  const float novelty = q_ratio > t2_ratio ? q_ratio : t2_ratio;
  return {q, t2, novelty, novelty > model.threshold};
}

} // namespace loonar_pca
