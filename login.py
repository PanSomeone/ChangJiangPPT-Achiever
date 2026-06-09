import sys, time, json, subprocess, os, socket
from pathlib import Path

HERE = Path(__file__).parent
CONFIG_PATH = HERE / "config.json"

PYPI_MIRRORS = [
    ("清华源", "https://pypi.tuna.tsinghua.edu.cn/simple"),
    ("阿里源", "https://mirrors.aliyun.com/pypi/simple/"),
    ("中科大源", "https://pypi.mirrors.ustc.edu.cn/simple/"),
    ("官方源", "https://pypi.org/simple/"),
]


def install_playwright():
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright
    except ImportError:
        print("正在安装 Playwright（国内镜像加速）...")
        for name, mirror in PYPI_MIRRORS:
            host = mirror.split("//")[1].split("/")[0]
            try:
                print(f"  尝试 {name} ({host})...")
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", "playwright",
                     "-i", mirror, "--trusted-host", host],
                    check=True, timeout=120
                )
                print(f"  安装完成（{name}）")
                from playwright.sync_api import sync_playwright
                return sync_playwright
            except subprocess.TimeoutExpired:
                print(f"  超时，切换下一个源...")
            except subprocess.CalledProcessError:
                print(f"  失败，切换下一个源...")
        raise RuntimeError("所有镜像源均安装失败，请检查网络连接")


def find_playwright_chromium():
    local_app = os.environ.get("LOCALAPPDATA", "")
    ms_dir = Path(local_app) / "ms-playwright"
    matches = sorted(ms_dir.glob("chromium-*/chrome-win/chrome.exe")) if ms_dir.exists() else []
    return str(matches[-1]) if matches else None


def install_chromium():
    print()
    print("正在下载 Chromium 浏览器（约 150MB），请稍候...")
    try:
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            check=True, timeout=300
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("Chromium 下载超时，请检查网络")
    except subprocess.CalledProcessError:
        raise RuntimeError("Chromium 下载失败")

    path = find_playwright_chromium()
    if path:
        print(f"  [OK] Chromium: {path}")
        return path
    raise RuntimeError("未找到 Chromium 安装路径，请手动输入")


def get_browser_path():
    print("=" * 50)
    print("  雨课堂 Cookie 自动获取")
    print("=" * 50)
    print()

    default_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]

    auto_path = None
    for p in default_paths:
        if Path(p).exists():
            auto_path = p
            break

    if not auto_path:
        auto_path = find_playwright_chromium()

    if auto_path:
        print(f"检测到浏览器: {auto_path}")
        user_input = input("按回车使用此路径，或输入其他浏览器路径: ").strip()
        if user_input:
            return user_input
        return auto_path
    else:
        print("未检测到浏览器")
        print("  [1] 手动输入浏览器路径")
        print("  [2] 自动下载 Chromium（推荐）")
        while True:
            choice = input("请选择 (1/2): ").strip()
            if choice == "1":
                print("示例: C:\\Users\\Name\\AppData\\Local\\Google\\Chrome\\Application\\chrome.exe")
                while True:
                    path = input("浏览器路径: ").strip()
                    if Path(path).exists():
                        return path
                    print("路径不存在，请重新输入")
            elif choice == "2":
                return install_chromium()
            else:
                print("请输入 1 或 2")


def start_browser_debug(browser_path):
    debug_port = 9222
    user_data_dir = Path.home() / "ChromeDebug"
    user_data_dir.mkdir(exist_ok=True)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    port_available = sock.connect_ex(("127.0.0.1", debug_port)) != 0
    sock.close()

    if not port_available:
        print(f"端口 {debug_port} 已被占用，尝试连接现有浏览器...")
        return debug_port

    print()
    print("正在启动浏览器调试模式...")
    print(f"用户数据目录: {user_data_dir}")

    cmd = [
        browser_path,
        f"--remote-debugging-port={debug_port}",
        f"--user-data-dir={user_data_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "https://changjiang.yuketang.cn/v2/web/studentLog"
    ]

    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    print("等待浏览器启动", end="")
    for _ in range(15):
        time.sleep(0.5)
        print(".", end="", flush=True)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if sock.connect_ex(("127.0.0.1", debug_port)) == 0:
            sock.close()
            print("  [OK]")
            return debug_port
        sock.close()

    print("  [超时]")
    raise RuntimeError("浏览器启动失败，请检查路径是否正确")


def auto_detect_and_extract(sync_playwright, port, timeout=300):
    """连接浏览器并自动检测登录，提取 Cookie"""
    cdp_url = f"http://127.0.0.1:{port}"

    print()
    print("=" * 50)
    print("  请在浏览器中扫码登录雨课堂")
    print(f"  自动检测登录中（超时 {timeout} 秒）...")
    print("=" * 50)
    print()

    with sync_playwright() as p:
        print(f"连接到浏览器: {cdp_url}")
        browser = p.chromium.connect_over_cdp(cdp_url)

        contexts = browser.contexts
        if not contexts:
            print("  未找到浏览器上下文，尝试新建...")
            ctx = browser.new_context()
        else:
            ctx = contexts[0]

        pages = ctx.pages
        if pages:
            page = pages[0]
            print(f"  已连接到页面: {page.url[:60]}...")
        else:
            page = ctx.new_page()
            page.goto("https://changjiang.yuketang.cn/v2/web/studentLog")
            time.sleep(2)

        found_session = False
        for t in range(timeout):
            dots = "." * ((t % 3) + 1)
            print(f"\r  等待扫码登录{dots:4}  {t} 秒", end="", flush=True)
            time.sleep(1)

            try:
                cks = ctx.cookies("https://changjiang.yuketang.cn")
                if not cks:
                    cks = ctx.cookies()
                if any(c["name"] == "sessionid" for c in cks):
                    print(f"\n\n  [OK] 检测到登录成功！（{t} 秒）")
                    found_session = True
                    break
            except:
                pass

        if not found_session:
            print("\n\n  [超时] 未检测到登录，请重试。")
            return False

        print()
        print("登录成功，正在导航到课程页面...")

        # 登录后可能停在 errpage，主动跳转到首页
        try:
            print("  跳转到首页...")
            page.goto("https://changjiang.yuketang.cn/v2/web/index",
                      wait_until="domcontentloaded", timeout=15000)
            time.sleep(2)
        except Exception:
            print("  [提示] 首页跳转失败，尝试继续...")

        # 点击“课程班级”触发完整 Cookie 写入
        try:
            print("  点击「课程班级」...")
            page.click("text=课程班级", timeout=5000)
            time.sleep(2)
        except Exception:
            try:
                page.click("a:has-text('课程')", timeout=3000)
                time.sleep(2)
            except Exception:
                print("  [提示] 未找到课程入口，直接提取 Cookie...")

        print()
        print("正在提取 Cookie...")
        cks = ctx.cookies("https://changjiang.yuketang.cn")
        if not cks:
            cks = ctx.cookies()

        if not cks:
            print("  [错误] 未获取到任何 Cookie")
            return False

        parts = []
        uid = ""
        for c in cks:
            if c.get("name") and c.get("value"):
                parts.append(f'{c["name"]}={c["value"]}')
            if c["name"] == "university_id":
                uid = c["value"]

        cookie_str = "; ".join(parts)

        cfg = {"cookie": cookie_str, "uid": uid}
        CONFIG_PATH.write_text(
            json.dumps(cfg, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        print()
        print("=" * 50)
        print("  提取结果")
        print("=" * 50)
        print(f"  Cookie 数量: {len(parts)} 项")
        print(f"  学校 ID: {uid if uid else '(未获取)'}")
        print(f"  已保存到: {CONFIG_PATH}")
        print()
        print("  [成功] Cookie 已保存！")

        return True


def main():
    try:
        sync_playwright = install_playwright()

        browser_path = get_browser_path()
        print(f"使用浏览器: {browser_path}")

        port = start_browser_debug(browser_path)

        if auto_detect_and_extract(sync_playwright, port):
            print()
            input("按回车退出...")
        else:
            print()
            input("提取失败，按回车退出...")

    except Exception as e:
        print()
        print(f"[错误] {e}")
        print()
        input("按回车退出...")


if __name__ == "__main__":
    main()
