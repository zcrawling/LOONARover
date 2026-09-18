# Local vendor SDK provisioning

The CubeEye SDK is an external deployment input, not a Git source artifact.
The local archive is retained on the development computer and excluded from commits.

| Field | Value |
| --- | --- |
| Archive | `arm64-pi5-linux-ubuntu_24_04_v2.5.9_20250311.tar.gz` |
| Expected location | `platforms/loonar/` |
| SHA256 | `e7055c03d3d6638683f37c2d10236a8ba23d8cecb277f6858a608653a1061ea3` |
| Unpacked SDK root | `arm64-pi5-linux-ubuntu_24_04/release/` |
| Target | Raspberry Pi 5, Ubuntu 24.04, AArch64 |

Provision this exact vendor archive separately on a new checkout/Pi and verify
the checksum before extracting it. The archive is approximately 129.4 MiB and
is not included in an ordinary source checkout. No public download URL or
permission to redistribute the vendor bundle has been established here.

The source bridge lives in `tools/cubeeye_ros/`. SDK shared libraries must be
loaded only in its isolated acquisition helper, not globally into ROS Python
or the camera-streaming service. See the
[porting plan](porting/limo_to_loonar_plan.md) for the runtime checks.
