# Sourced only by camera commands, never globally by ROS or the CubeEye helper.
LOONAR_CAMERA_PREFIX=/opt/loonar/camera-stack/current
export LD_LIBRARY_PATH="$LOONAR_CAMERA_PREFIX/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export GST_PLUGIN_PATH="$LOONAR_CAMERA_PREFIX/lib/gstreamer-1.0${GST_PLUGIN_PATH:+:$GST_PLUGIN_PATH}"
export LIBCAMERA_IPA_MODULE_PATH="$LOONAR_CAMERA_PREFIX/lib/libcamera/ipa"
export LIBCAMERA_IPA_CONFIG_PATH="$LOONAR_CAMERA_PREFIX/share/libcamera/ipa"
export LIBCAMERA_IPA_PROXY_PATH="$LOONAR_CAMERA_PREFIX/libexec/libcamera"
export GST_REGISTRY="${XDG_CACHE_HOME:-$HOME/.cache}/loonar/camera-registry.bin"
mkdir -p "$(dirname -- "$GST_REGISTRY")"
