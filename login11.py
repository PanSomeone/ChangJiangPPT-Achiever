#!/usr/bin/env python3
"""雨课堂 Cookie 自动获取"""

import sys, time, json
from pathlib import Path

HERE = Path(__file__).parent
CONFIG_PATH = HERE / "config.json"

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    import subprocess
    print("正在安装 Playwright...")
    subprocess.run([sys.executable,"-m","pip","install","playwright"],check=True)
    print("正在安装 Chromium 浏览器...")
    subprocess.run([sys.executable,"-m","playwright","install","chromium"],check=True)
    from playwright.sync_api import sync_playwright

def main():
    print("=" * 50)
    print("  雨课堂 Cookie 自动获取")
    print("=" * 50)
    print()
    print("即将打开浏览器，请扫码登录。")
    print("登录成功后会自动保存 Cookie。")
    print()

    try:
        with sync_playwright() as p:
            ctx = p.chromium.launch(
                headless=False,
                args=["--disable-blink-features=AutomationControlled"],
            ).new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"
            )
            page = ctx.new_page()
            page.goto("https://changjiang.yuketang.cn/v2/web/studentLog")

            found = False
            for t in range(600):
                dots = "." * ((t % 3) + 1)
                print(f"\r  等待扫码登录{dots}  {t} 秒", end="", flush=True)
                time.sleep(1)

                try:
                    cks = ctx.cookies()
                    if any(c["name"] == "sessionid" for c in cks):
                        print(f"\n\n  [OK] 检测到登录成功！({t} 秒)")
                        found = True
                        break
                except:
                    pass

            if not found:
                print("\n\n  [超时] 未检测到登录，请重试。")
                print()
                input("按回车关闭...")
                ctx.close()
                return

            # 提取 Cookie
            try:
                cks = ctx.cookies("https://changjiang.yuketang.cn")
                if not cks:
                    cks = ctx.cookies()
            except:
                cks = ctx.cookies()

            parts = []
            uid = ""
            for c in cks:
                if c.get("name") and c.get("value"):
                    parts.append(f'{c["name"]}={c["value"]}')
                if c["name"] == "university_id":
                    uid = c["value"]

            cookie_str = "; ".join(parts)

            cfg = {"cookie": cookie_str, "uid": uid}
            CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

            print(f"  Cookie 数量: {len(parts)} 项")
            print(f"  学校 ID: {uid}")
            print(f"  已保存到: {CONFIG_PATH}")
            print()
            print("  [成功] 3 秒后自动关闭...")
            time.sleep(3)
            ctx.close()

    except Exception as e:
        print(f"\n[错误] {e}")
        print()
        input("按回车关闭...")

if __name__ == "__main__":
    main()
