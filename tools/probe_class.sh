#!/bin/bash
# 用 dalvikvm 验证某个类能否在 bootclasspath 中被找到（零风险，不改系统）
# 用法: probe_class.sh <完整类名>
CLS="$1"
cat > /data/local/tmp/Probe.java << 'EOF'
import java.lang.reflect.Class;
public class Probe {
  public static void main(String[] a) {
    String n = a[0];
    try {
      Class<?> c = Class.forName(n);
      System.out.println("FOUND: " + c.getName());
      System.out.println("  loader: " + c.getClassLoader());
      java.lang.reflect.Method[] ms = c.getDeclaredMethods();
      System.out.println("  methods: " + ms.length);
      for (int i = 0; i < ms.length && i < 12; i++) {
        System.out.println("    " + ms[i].getName());
      }
    } catch (Throwable t) {
      System.out.println("NOT FOUND: " + t);
    }
  }
}
EOF
echo "=== 编译 Probe ==="
CLASSPATH="$BOOTCLASSPATH" /system/bin/dalvikvm -cp /system/framework/core.jar \
  -d /data/local/tmp /data/local/tmp/Probe.java 2>&1 | head -5
ls -l /data/local/tmp/Probe.dex 2>&1 | head -2
echo
echo "=== 运行，探测 $CLS ==="
CLASSPATH="$BOOTCLASSPATH" /system/bin/dalvikvm -cp /data/local/tmp/Probe.dex /data/local/tmp/Probe "$CLS" 2>&1 | head -18