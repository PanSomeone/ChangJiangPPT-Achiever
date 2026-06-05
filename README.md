# 长江雨课堂 PPT 批量下载器

批量下载长江雨课堂某门课程的全部课件，自动合并为 PDF。

## 功能

- 列出全部课程，勾选下载
- 内容指纹去重 — 同一份 PPT 不重复下载
- PPT 真实标题作为文件名
- 断点续传，中断后可继续
- 一键浏览器自动登录

## 使用

双击 `点我运行.bat`，或：

```bash
pip install -r requirements.txt
playwright install chromium
python gui.py
```

首次运行点击「粘贴 Cookie」粘贴，或点击「浏览器登录」扫码自动获取。

## 文件

| 文件 | 说明 |
|------|------|
| `gui.py` | 主程序 |
| `login.py` | Playwright 自动登录 |
| `点我运行.bat` | 一键启动 |

---

@PanSomeone
