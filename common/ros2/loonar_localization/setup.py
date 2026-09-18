from setuptools import setup, find_packages
setup(name='loonar_localization', version='0.1.0', packages=find_packages(),
      data_files=[('share/ament_index/resource_index/packages',['resource/loonar_localization']),
                  ('share/loonar_localization',['package.xml','README.md','C_ACCEL_EXPERIMENT.md']),
                  ('share/loonar_localization/launch',['launch/localization.launch.py', 'launch/tof_translation.launch.py'])],
      install_requires=['setuptools','numpy','scipy'], zip_safe=True,
      maintainer='LOONAR', maintainer_email='noreply@example.invalid', license='MIT',
      description='Platform-independent V1 DR and stop-keyframe correction',
      entry_points={'console_scripts':['odom_c_test = loonar_localization.c_accel_node:main',
                                      'c_ramp = loonar_localization.c_ramp:main','primitive_manager = loonar_localization.ros_nodes:primitive_main',
                                      'dead_reckoning = loonar_localization.ros_nodes:dr_main',
                                      'stop_registration = loonar_localization.ros_nodes:registration_main']})
