from setuptools import find_packages, setup


package_name = "loonar_limo_rgbd_odom"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml", "README.md"]),
        ("share/" + package_name + "/launch", [
            "launch/limo_rgbd_camera.launch.py",
            "launch/limo_rgbd_odom.launch.py",
        ]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="LOONAR",
    maintainer_email="noreply@example.invalid",
    description="Isolated RGB-D odometry experiment for the LIMO platform.",
    license="MIT",
    entry_points={
        "console_scripts": [
            "rgbd_input_probe = loonar_limo_rgbd_odom.rgbd_input_probe:main",
        ],
    },
)
