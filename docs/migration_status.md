# Restructure Status

The old Jazzy/Gazebo SIL and cFS final-motion-arbitration layout were removed from
the active tree because they modelled a different command authority path.

Retained final-rover assets are now under `platforms/loonar/`. They remain active
engineering reference material, not legacy material. Their interfaces must be
adapted through `TeensyRs485Backend` rather than accessed by cFS or ROS 2.

The pre-restructure workspace snapshot is stored outside this repository at
`/home/sb/LOONAR-backups/loonar-pre-limo-restructure-20260902.tar.gz`.
