from glob import glob
from setuptools import setup


package_name = "loonar_limo_tof"

setup(
    name=package_name,
    version="0.1.0",
    packages=[],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/loonar_limo_tof"]),
        (f"share/{package_name}", ["package.xml"]),
        (f"share/{package_name}/launch", glob("launch/*.launch.py")),
        (f"share/{package_name}/config", glob("config/*.yaml")),
    ],
    zip_safe=True,
    maintainer="LOONAR",
    maintainer_email="noreply@example.invalid",
    description="Fixed depth-only Orbbec DaBai bringup for the LIMO validation platform.",
    license="MIT",
)
