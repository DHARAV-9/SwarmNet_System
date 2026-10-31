FROM ubuntu:22.04@sha256:a8fb2ba88181746111cbbe2969826d6546b71226785b196c93d2c3445a25000d

SHELL ["/bin/bash", "-o", "pipefail", "-c"]
ENV DEBIAN_FRONTEND=noninteractive
ENV PATH="/root/.local/bin:${PATH}"
ENV PX4_DIR=/opt/PX4-Autopilot
ENV CMAKE_BUILD_PARALLEL_LEVEL=2

RUN test "$(dpkg --print-architecture)" = arm64 \
    && apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --branch v1.16.0 --depth 1 https://github.com/PX4/PX4-Autopilot.git ${PX4_DIR} \
    && test "$(git -C ${PX4_DIR} rev-parse HEAD)" = 6ea3539157ca358c70a515878b77077af7d4611d

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       gnupg gosu lsb-release software-properties-common sudo wget \
    && bash ${PX4_DIR}/Tools/setup/ubuntu.sh --no-nuttx \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/PX4-Autopilot
RUN make px4_sitl_default -j2 \
    && test -x build/px4_sitl_default/bin/px4 \
    && gz sim --versions

LABEL org.opencontainers.image.version="PX4-v1.16.0-gazebo-harmonic" \
      org.opencontainers.image.revision="6ea3539157ca358c70a515878b77077af7d4611d"
CMD ["sleep", "infinity"]
