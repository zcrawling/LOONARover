from setuptools import find_packages, setup

setup(name='loonar_imu_vibration', version='0.1.0', packages=find_packages(),
      data_files=[('share/ament_index/resource_index/packages', ['resource/loonar_imu_vibration']),
                  ('share/loonar_imu_vibration', ['package.xml', 'README.md'])],
      install_requires=['setuptools', 'numpy'],
      extras_require={'bag': ['rosbags>=0.10,<0.12']},
      entry_points={'console_scripts': [
          'vibration_tool = loonar_imu_vibration.cli:main',
          'vibration_record = loonar_imu_vibration.record:main',
          'imu_vibration_correction_node = loonar_imu_vibration.node:main']},
      maintainer='LOONAR', maintainer_email='noreply@example.invalid', license='MIT')
