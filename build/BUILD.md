# 构建配方（Build Recipe）

本仓库只发「源码 + 补丁 + 设备覆盖 + 本配方」。专有二进制必须**你自己**从合法拥有的
设备或官方 SDK 提取（见 `fetch-blobs.sh`），不随仓库分发。

## 前置条件
- 一台能跑 Linux 构建的环境（实测在 WSL + AOSP 树内，`/home/mxz/aosp`）。
- OpenJDK 8（`signapk.jar` 需要）。
- AOSP 提供的签名工具：
  - `out/host/linux-x86/bin/signapk.jar`（或 `prebuilts/sdk/...`）
  - `prebuilts/sdk/19/android.jar`、`build/target/product/security/testkey.*`
- 上游 *EmuELEC for hi3798mv100* 源码（0BSD/GPLv2，请自行 clone 上游）。

## 步骤
1. **准备上游**
   ```
   git clone <上游 EmuELEC for hi3798mv100> upstream
   ```
2. **套用本仓库的修改**
   - 把 `ee_files/` 整目录作为设备覆盖合并进待构建的 rootfs 骨架；
   - 把 `tools/es-gamelist-highlight.py` 等方法用于对应的补丁（详见 `docs/32-*`）。
3. **获取专有 blob**（仅你自己的设备/SDK）
   ```
   bash build/fetch-blobs.sh /mount/point/of/device  blobs/
   ```
   该脚本把 libMali、海思 OMX、预编译内核模块、libretro 核心等复制到本地
   `blobs/`（已在 `.gitignore` 排除，不会误提交）。
4. **生成独立 EmuELEC recovery 包**
   ```
   python3 tools/build_emuelec_standalone.py \
       --rootfs 干净rootfs.img \
       --eefiles ee_files \
       --out    update_a4_emuelec.zip
   ```
   脚本只写 `backup`(p13) 上的 EmuELEC rootfs + ee_files 覆盖，**不碰安卓
   /system、不 format userdata**。
5. **整包签名（必须）**
   recovery 校验要求整包签名且 EOCD 注释格式固定（原厂 1738 字节）。
   ```
   java -jar signapk.jar -w \
        build/target/product/security/testkey.x509.pem \
        build/target/product/security/testkey.pk8 \
        update_a4_emuelec.unsigned.zip update_a4_emuelec.zip
   ```
   校验：`python3 tools/verify_zip.py update_a4_emuelec.zip`。

## 备注
- 老 `repack_ee*.py` 系列用于从现有 `update.zip` 增改条目后重签；新的独立包走
  `build_emuelec_standalone.py` 更直接。
- 整盘 p1–p9 镜像、双系统 U-Boot (`fastboot_a4.img`) 等因含固定标识/专有权，
  **不在此开源范围内**，请使用你自己设备导出的干净副本。
