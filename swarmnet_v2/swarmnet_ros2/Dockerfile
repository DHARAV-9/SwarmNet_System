FROM osrf/ros:humble-desktop

SHELL ["/bin/bash", "-c"]

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-colcon-common-extensions \
    python3-pip \
    python3-yaml \
    ros-humble-mavros \
    ros-humble-mavros-extras \
    ros-humble-rmw-cyclonedds-cpp \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /ros2_ws/src /ros2_ws/logs

WORKDIR /ros2_ws
