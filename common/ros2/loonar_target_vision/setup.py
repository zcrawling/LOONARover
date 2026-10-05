from setuptools import find_packages, setup

setup(
    name="loonar_target_vision",
    version="0.1.0",
    packages=find_packages(),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/loonar_target_vision"]),
        ("share/loonar_target_vision", ["package.xml"]),
        ("share/loonar_target_vision/config", ["config/vision.yaml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="LOONAR",
    maintainer_email="noreply@example.invalid",
    description="RGB-only rover target cues",
    entry_points={"console_scripts": ["target_vision = loonar_target_vision.node:main"]},
)
