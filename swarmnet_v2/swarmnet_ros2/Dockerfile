FROM ros:humble-ros-base-jammy@sha256:48435c01f2876ff519a0d07edf8dd3ab29a8106c907965c64385a14c76470d6b

SHELL ["/bin/bash", "-c"]

RUN test "$(dpkg --print-architecture)" = arm64 \
    && apt-get update && apt-get install -y --no-install-recommends \
    python3-colcon-common-extensions \
    python3-pip \
    python3-yaml \
    ros-humble-mavros \
    ros-humble-mavros-extras \
    ros-humble-rmw-cyclonedds-cpp \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /ros2_ws/src /ros2_ws/logs

WORKDIR /ros2_ws
