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

RUN geographiclib-get-geoids egm96-5 \
    && test -s /usr/share/GeographicLib/geoids/egm96-5.pgm

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake git libasio-dev libtinyxml2-dev libssl-dev \
    && rm -rf /var/lib/apt/lists/* \
    && git clone --depth 1 --branch v2.4.3 https://github.com/eProsima/Micro-XRCE-DDS-Agent.git /opt/Micro-XRCE-DDS-Agent \
    && test "$(git -C /opt/Micro-XRCE-DDS-Agent rev-parse HEAD)" = 73622810d984349b80bbac0ef55fc0b694d62222 \
    && cmake -S /opt/Micro-XRCE-DDS-Agent -B /opt/Micro-XRCE-DDS-Agent/build -DCMAKE_BUILD_TYPE=Release \
    && cmake --build /opt/Micro-XRCE-DDS-Agent/build --parallel 2 \
    && cmake --install /opt/Micro-XRCE-DDS-Agent/build \
    && ldconfig

RUN git init /ros2_ws/src/px4_msgs \
    && git -C /ros2_ws/src/px4_msgs remote add origin https://github.com/PX4/px4_msgs.git \
    && git -C /ros2_ws/src/px4_msgs fetch --depth 1 origin 392e831c1f659429ca83902e66820d7094591410 \
    && git -C /ros2_ws/src/px4_msgs checkout --detach FETCH_HEAD \
    && source /opt/ros/humble/setup.bash \
    && colcon build --base-paths /ros2_ws/src/px4_msgs --packages-select px4_msgs
