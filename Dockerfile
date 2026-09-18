FROM osrf/ros:humble-desktop-full

ENV DEBIAN_FRONTEND=noninteractive
ENV ROS_DISTRO=humble

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    python3-colcon-common-extensions \
    python3-rosdep \
    ros-humble-gazebo-ros-pkgs \
    ros-humble-gazebo-plugins \
    ros-humble-robot-localization \
    ros-humble-xacro \
    ros-humble-tf2-tools \
    && rm -rf /var/lib/apt/lists/*

RUN rosdep init || true

WORKDIR /ws
CMD ["bash"]
