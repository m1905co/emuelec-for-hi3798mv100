#!/bin/bash
W=/home/mxz/hijack
mkdir -p $W
cat > $W/T.java << 'JEOF'
public class T {
  public static void main(String[] a) {
    try {
      Class<?> c = Class.forName("org.jf.baksmali.Main");
      System.out.println("LOADED: " + c);
    } catch (Throwable t) {
      Throwable r = t;
      while (r != null) { System.out.println("  -> " + r.getClass().getName() + ": " + r.getMessage()); r = r.getCause(); }
    }
  }
}
JEOF
cd $W
echo "=== lib 内容 ==="; ls lib/ 2>&1
CP=$(ls lib/*.jar 2>/dev/null | tr '\n' ':')
echo "CP=$CP" | head -c 300; echo
echo "=== 编译 ==="
javac -cp "$CP" T.java 2>&1 | head -5
echo "=== 运行 ==="
java -cp "${CP}." T 2>&1 | head -12