#pragma once
#include <Eigen/Dense>
#include <algorithm>
#include <cmath>
#include <limits>
#include <vector>

namespace loonar {
inline float nan() { return std::numeric_limits<float>::quiet_NaN(); }
inline double median(std::vector<double> values) {
  if (values.empty())
    return std::numeric_limits<double>::quiet_NaN();
  const auto n = values.size() / 2;
  std::nth_element(values.begin(), values.begin() + n, values.end());
  const double upper = values[n];
  if (values.size() % 2)
    return upper;
  return .5 * (upper + *std::max_element(values.begin(), values.begin() + n));
}
inline double mad(const std::vector<double> &a, double center) {
  std::vector<double> d;
  d.reserve(a.size());
  for (double v : a)
    d.push_back(std::abs(v - center));
  return median(d);
}
struct Fused {
  float depth = nan(), confidence = 0, deviation = nan();
};
inline Fused fuse(const std::vector<double> &depths, int required, int total,
                  double mad_limit) {
  if (int(depths.size()) < required)
    return {};
  double m = median(depths), d = mad(depths, m);
  return {float(m),
          float(double(depths.size()) / total * std::exp(-d / mad_limit)),
          float(d)};
}
struct Cell {
  float elevation = nan(), elevation_min = nan(), elevation_max = nan(),
        elevation_variance = nan(), elevation_mad = nan();
  unsigned point_count = 0;
  float confidence = 0, slope = nan(), gradient_x = nan(), gradient_y = nan(),
        cross_slope = nan(), roughness = nan();
  float step_up = 0, step_down = 0, depression_depth = 0;
  bool drop_suspect = false, observed = false, unknown = true;
  float traversability = 0;
};
struct Grid {
  double resolution = .05, x_min = -.5, x_max = 2., y_min = -1., y_max = 1.;
  int nx = 0, ny = 0;
  std::vector<Cell> cells;
  void reset() {
    nx = int(std::ceil((x_max - x_min) / resolution));
    ny = int(std::ceil((y_max - y_min) / resolution));
    cells.assign(nx * ny, {});
  }
  int index(double x, double y) const {
    const int i = int(std::floor((x - x_min) / resolution)),
              j = int(std::floor((y - y_min) / resolution));
    return i >= 0 && j >= 0 && i < nx && j < ny ? i * ny + j : -1;
  }
  Eigen::Vector2d position(int k) const {
    return {x_min + (k / ny + .5) * resolution,
            y_min + (k % ny + .5) * resolution};
  }
};
struct TerrainParams {
  int min_points = 3, min_neighbors = 6, step_support = 2;
  double plane_radius = .15, step_noise = .015, min_confidence = .6;
  double max_slope = .22, max_roughness = .012, max_step_up = .035,
         max_step_down = .035, max_drop_depth = .035;
};
inline Eigen::Vector3d
robust_plane(const std::vector<Eigen::Vector3d> &points) {
  if (points.size() < 3)
    return Eigen::Vector3d::Constant(nan());
  Eigen::MatrixXd a(points.size(), 3);
  Eigen::VectorXd b(points.size()),
      weights = Eigen::VectorXd::Ones(points.size());
  for (size_t i = 0; i < points.size(); ++i) {
    a.row(i) << points[i].x(), points[i].y(), 1.;
    b[i] = points[i].z();
  }
  if (a.colPivHouseholderQr().rank() < 3)
    return Eigen::Vector3d::Constant(nan());
  Eigen::Vector3d fit = Eigen::Vector3d::Zero();
  for (int iteration = 0; iteration < 4; ++iteration) {
    auto w = weights.asDiagonal();
    fit = (a.transpose() * w * a).ldlt().solve(a.transpose() * w * b);
    Eigen::VectorXd residual = b - a * fit;
    std::vector<double> rr(residual.data(), residual.data() + residual.size());
    const double scale = std::max(.002, 1.4826 * mad(rr, median(rr)));
    for (int i = 0; i < weights.size(); ++i)
      weights[i] =
          std::min(1., 1.345 * scale / std::max(1e-9, std::abs(residual[i])));
  }
  return fit;
}
inline void build_grid(Grid &g, const std::vector<Eigen::Vector3d> &points,
                       const std::vector<float> &confidence,
                       const TerrainParams &p) {
  g.reset();
  std::vector<std::vector<double>> bins(g.cells.size()), conf(g.cells.size());
  for (size_t i = 0; i < points.size(); ++i) {
    if (!points[i].allFinite())
      continue;
    int k = g.index(points[i].x(), points[i].y());
    if (k >= 0) {
      bins[k].push_back(points[i].z());
      conf[k].push_back(confidence[i]);
    }
  }
  for (size_t k = 0; k < bins.size(); ++k) {
    auto &c = g.cells[k];
    auto &z = bins[k];
    c.point_count = z.size();
    if (int(z.size()) < p.min_points)
      continue;
    c.elevation = median(z);
    c.elevation_min = *std::min_element(z.begin(), z.end());
    c.elevation_max = *std::max_element(z.begin(), z.end());
    c.elevation_mad = mad(z, c.elevation);
    double sum = 0;
    for (auto v : z)
      sum += (v - c.elevation) * (v - c.elevation);
    c.elevation_variance = sum / z.size();
    c.confidence = median(conf[k]);
    c.observed = true;
  }
  const int radius = std::ceil(p.plane_radius / g.resolution);
  for (int k = 0; k < int(g.cells.size()); ++k) {
    auto &c = g.cells[k];
    if (!c.observed)
      continue;
    const int x = k / g.ny, y = k % g.ny;
    auto xy = g.position(k);
    std::vector<Eigen::Vector3d> nearby;
    std::vector<double> heights, ups, downs;
    for (int i = std::max(0, x - radius); i <= std::min(g.nx - 1, x + radius);
         ++i)
      for (int j = std::max(0, y - radius); j <= std::min(g.ny - 1, y + radius);
           ++j) {
        const auto &n = g.cells[i * g.ny + j];
        if (!n.observed)
          continue;
        Eigen::Vector2d pos = g.position(i * g.ny + j) - xy;
        if (pos.norm() > p.plane_radius + 1e-6)
          continue;
        nearby.emplace_back(pos.x(), pos.y(), n.elevation);
        heights.push_back(n.elevation);
      }
    if (int(nearby.size()) < p.min_neighbors)
      continue;
    auto plane = robust_plane(nearby);
    if (!plane.allFinite())
      continue;
    c.gradient_x = plane.x();
    c.gradient_y = plane.y();
    c.slope = std::atan(std::hypot(plane.x(), plane.y()));
    c.cross_slope = std::atan(std::abs(plane.y()));
    std::vector<double> residual;
    for (const auto &v : nearby) {
      double e = v.z() - (plane.x() * v.x() + plane.y() * v.y() + plane.z());
      residual.push_back(e);
      // Remove local slope before detecting steps; require repeated support.
      double delta =
          v.z() - c.elevation - plane.x() * v.x() - plane.y() * v.y();
      if (delta > p.step_noise)
        ups.push_back(delta);
      if (delta < -p.step_noise)
        downs.push_back(-delta);
    }
    c.roughness =
        std::max(double(c.elevation_mad), mad(residual, median(residual)));
    // Include within-cell relief: median alone would hide rocks occupying part
    // of a cell.
    c.step_up = std::max(0.f, c.elevation_max - c.elevation);
    c.step_down = std::max(0.f, c.elevation - c.elevation_min);
    if (int(ups.size()) >= p.step_support)
      c.step_up = std::max(double(c.step_up), median(ups));
    if (int(downs.size()) >= p.step_support)
      c.step_down = std::max(double(c.step_down), median(downs));
    c.depression_depth = std::max(0., plane.z() - c.elevation);
    c.unknown = c.confidence < p.min_confidence;
    c.traversability =
        (!c.unknown && c.slope <= p.max_slope &&
         c.roughness <= p.max_roughness && c.step_up <= p.max_step_up &&
         c.step_down <= p.max_step_down &&
         c.depression_depth <= p.max_drop_depth)
            ? 1.f
            : 0.f;
  }
  // A measured ground boundary followed by unknown is suspect, never a guessed
  // depth.
  for (int x = 0; x < g.nx - 1; ++x)
    for (int y = 0; y < g.ny; ++y) {
      int k = x * g.ny + y;
      if (g.cells[k].observed && !g.cells[k].unknown &&
          !g.cells[k + g.ny].observed) {
        g.cells[k + g.ny].drop_suspect = true;
        g.cells[k + g.ny].traversability = 0;
      }
    }
}
} // namespace loonar
