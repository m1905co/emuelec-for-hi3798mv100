#!/system/bin/sh
# Switch to Android
#   清空 misc 标记 -> 原厂 U-Boot mode0 -> 从 p11(82MiB) 启动 Android
#   （旧实现是刷 env 到 p2；原厂 U-Boot 不读 env 的 bootcmd，已废弃）
exec /data/a4/a4-os-switch android
