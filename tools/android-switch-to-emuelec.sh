#!/system/bin/sh
# Switch to EmuELEC
#   写 misc 标记 product-test -> 原厂 U-Boot mode2 -> 从 p10(58MiB) 启动 EmuELEC
#   （旧实现是刷 env 到 p2；原厂 U-Boot 不读 env 的 bootcmd，已废弃）
exec /data/a4/a4-os-switch emuelec
