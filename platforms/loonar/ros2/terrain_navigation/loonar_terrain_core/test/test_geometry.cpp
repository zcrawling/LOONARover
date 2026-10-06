#include <gtest/gtest.h>
#include <loonar_terrain_core/geometry.hpp>
TEST(Fusion, MedianInvalidAndOutliers) {
  EXPECT_DOUBLE_EQ(loonar::median({1., 2., 3., 4.}), 2.5);
  auto f = loonar::fuse({1., 1.01, 1., 20.}, 3, 4, .025);
  EXPECT_NEAR(f.depth, 1.005, .0001);
  EXPECT_GT(f.confidence, .8);
  EXPECT_TRUE(std::isnan(loonar::fuse({1., 1.}, 3, 4, .025).depth));
}
static loonar::Grid terrain(double slope, double step, bool pit = false) {
  loonar::Grid g;
  g.x_min = -.5;
  g.x_max = 1.;
  g.y_min = -.5;
  g.y_max = .5;
  std::vector<Eigen::Vector3d> points;
  std::vector<float> confidence;
  for (double x = -.49; x < .99; x += .012)
    for (double y = -.49; y < .49; y += .012) {
      double z = slope * x + (x > .45 ? step : 0.);
      if (pit && x > .25 && x < .5 && std::abs(y) < .15)
        z -= .1;
      points.emplace_back(x, y, z);
      confidence.push_back(1.);
    }
  loonar::TerrainParams p;
  loonar::build_grid(g, points, confidence, p);
  return g;
}
TEST(Terrain, FlatAndSlope) {
  auto flat = terrain(0, 0);
  auto c = flat.cells[flat.index(.2, 0)];
  EXPECT_FALSE(c.unknown);
  EXPECT_NEAR(c.elevation, 0, 1e-6);
  EXPECT_NEAR(c.slope, 0, 1e-6);
  auto slope = terrain(.2, 0);
  c = slope.cells[slope.index(.2, 0)];
  EXPECT_NEAR(c.slope, std::atan(.2), .025);
}
TEST(Terrain, StepAndDepressionReject) {
  auto step = terrain(0, .1);
  bool danger = false;
  for (const auto &c : step.cells)
    if (c.observed && !c.unknown && c.traversability == 0)
      danger = true;
  EXPECT_TRUE(danger);
  auto pit = terrain(0, 0, true);
  double deepest = 0;
  for (const auto &c : pit.cells)
    deepest = std::max(deepest, double(c.depression_depth));
  EXPECT_GT(deepest, .03);
}
TEST(Terrain, SmallStepRemainsTraversable) {
  auto step = terrain(0, .03);
  int observed = 0;
  for (int x = 0; x < step.nx; ++x)
    for (int y = 0; y < step.ny; ++y) {
      const double px = step.x_min + (x + .5) * step.resolution;
      const double py = step.y_min + (y + .5) * step.resolution;
      if (px < .25 || px > .65 || std::abs(py) > .2)
        continue;
      const auto &c = step.cells[x * step.ny + y];
      ASSERT_TRUE(c.observed);
      EXPECT_FALSE(c.unknown);
      EXPECT_EQ(c.traversability, 1.f) << "x=" << px << " y=" << py;
      ++observed;
    }
  EXPECT_GT(observed, 0);
}
TEST(Terrain, MissingIsNotFlat) {
  loonar::Grid g;
  std::vector<Eigen::Vector3d> points;
  std::vector<float> conf;
  for (double x = 0; x < .7; x += .01)
    for (double y = -.4; y < .4; y += .01) {
      points.emplace_back(x, y, 0);
      conf.push_back(1);
    }
  loonar::build_grid(g, points, conf, {});
  EXPECT_TRUE(g.cells[g.index(1., 0)].unknown);
  int drops = 0;
  for (const auto &c : g.cells)
    drops += c.drop_suspect;
  EXPECT_GT(drops, 0);
}
