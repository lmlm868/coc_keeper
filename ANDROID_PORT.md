# 🚀 AI守秘人 — 安卓移植方案

本项目是 **Flask + Python** 的 Web 应用，前端为 HTML/CSS/JS。  
以下是 **4 种** 将其移植到安卓设备上运行和使用的方法，按推荐程度排序。

---

## 方案一：PWA 渐进式 Web 应用 ⭐ 推荐

**原理**：给现有 Web 前端添加 PWA 支持（`manifest.json` + Service Worker），部署到服务器后，用户用 Chrome 访问即可「添加到主屏幕」，体验接近原生 App。

### 优点
- ✅ 无需写任何 Java/Kotlin 代码
- ✅ 前端代码几乎不用改（已适配 mobile viewport）
- ✅ 更新即时，无需通过应用商店
- ✅ 支持离线缓存（可选）
- ✅ 可以调用安卓硬件（麦克风语音输入等）

### 缺点
- ❌ 后台 Python 服务仍需部署在云端
- ❌ 无法使用系统级 API（通知栏、蓝牙等）

### 实施步骤

#### 1. 创建 [`manifest.json`](static/manifest.json)（见下方）

```json
{
  "name": "AI守秘人 - 克苏鲁呼唤",
  "short_name": "AI守秘人",
  "description": "克苏鲁跑团AI守秘人助手",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#1a1a1a",
  "theme_color": "#0a6cff",
  "icons": [
    { "src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png" },
    { "src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png" },
    { "src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable" }
  ]
}
```

#### 2. 创建 [`static/sw.js`](static/sw.js) Service Worker

```javascript
const CACHE_NAME = 'coc-keeper-v1';
const ASSETS = ['/', '/static/manifest.json'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE_NAME).then(c => c.addAll(ASSETS)));
});

self.addEventListener('fetch', (e) => {
  e.respondWith(
    caches.match(e.request).then(r => r || fetch(e.request))
  );
});
```

#### 3. 在 [`templates/index.html`](templates/index.html) 的 `<head>` 中添加

```html
<link rel="manifest" href="/static/manifest.json">
<meta name="theme-color" content="#0a6cff">
<meta name="apple-mobile-web-app-capable" content="yes">
```

#### 4. 部署到云服务器

```bash
# 可以用 gunicorn 部署
pip install gunicorn
gunicorn -w 2 -b 0.0.0.0:5000 app:app

# 或用 ngrok 临时暴露本地服务供测试
ngrok http 5000
```

#### 5. 在安卓上使用
- 打开 Chrome → 访问部署后的 URL
- 点击菜单 → **添加到主屏幕**
- 以后即可像原生 App 一样从桌面启动

---

## 方案二：Termux 本地运行 ⭐ 推荐

**原理**：在安卓上安装 Termux（Linux 模拟终端），直接运行 Python Flask 服务，通过浏览器访问 `http://localhost:5000`。

### 优点
- ✅ 完全本地运行，无需网络（除 API 调用外）
- ✅ 数据保存在本地 SQLite
- ✅ 所有 Python 代码无需改动
- ✅ 零成本

### 缺点
- ❌ 需要手动安装配置环境
- ❌ 每次使用需先启动服务
- ❌ 无法后台常驻（需保持 Termux 在前台或使用 Termux:Tasker）

### 实施步骤

#### 第 1 步：安装 Termux

从 [F-Droid](https://f-droid.org/packages/com.termux/) 下载 Termux（推荐）或 GitHub Release。

> ⚠️ 不要从 Google Play 安装，版本过旧且维护不善。

#### 第 2 步：安装 Python 和依赖

```bash
# 更新包管理器
pkg update && pkg upgrade -y

# 安装 Python 和必要系统库
pkg install python clang python-pip libxml2 libxslt -y

# 安装项目依赖
pip install flask flask-cors openai zhipuai python-dotenv websocket-client
# 如果用到 tts 模块的额外依赖：
pip install pycryptodome
```

#### 第 3 步：传输项目文件

方式 A — 用 USB 数据线复制项目文件夹到手机：

```
手机存储/Download/coc_ai/
├── app.py
├── db_manager.py
├── tts.py
├── .env
├── templates/
│   ├── index.html
│   └── create_character.html
└── static/
```

方式 B — 用 Git 克隆：

```bash
pkg install git -y
git clone <你的仓库地址>
```

方式 C — 用 `scp` 或 `rsync` 通过网络传输。

#### 第 4 步：修改 `.env` 确保密钥已配置

```bash
cd /storage/emulated/0/Download/coc_ai
# 或 cd ~/coc_ai
nano .env   # 确认 API 密钥已填写
```

#### 第 5 步：运行服务

```bash
python app.py
```

#### 第 6 步：在安卓浏览器访问

打开 Chrome → 访问 `http://127.0.0.1:5000`

> 💡 建议用 Termux 的「锁定 Wakelock」功能防止息屏后断连：  
> 下拉通知栏 → Termux 通知 → 点击「Acquire wakelock」

---

## 方案三：WebView 封装 APK

**原理**：用 Android Studio 创建一个极简的 Android App，内嵌 WebView 加载 Flask 服务（需配合方案二 Termux 或部署到云端）。

### 优点
- ✅ 看起来像真正的 App
- ✅ 可以上架应用商店
- ✅ 可定制启动画面、标题栏

### 缺点
- ❌ 需要编写少量 Java/Kotlin 代码
- ❌ 需要安装 Android Studio（数 GB）
- ❌ 如果后端在云端仍需网络

### 简易代码

创建 `MainActivity.kt`：

```kotlin
package com.coc.keeper

import android.os.Bundle
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.appcompat.app.AppCompatActivity

class MainActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val webView = WebView(this)
        setContentView(webView)
        
        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            setSupportZoom(true)
            builtInZoomControls = true
            displayZoomControls = false
        }
        
        webView.webViewClient = WebViewClient()
        webView.loadUrl("http://<你的服务器IP>:5000")
    }
}
```

### ✅ 已完成：Capacitor WebView APK（推荐）

项目已使用 [Capacitor](https://capacitorjs.com/) 创建了完整的 Android 项目，位于 [`android-app/`](android-app/) 目录。

#### 特性
- ✅ 内置连接配置界面（支持 Termux 本地 / 云服务器 / 自定义地址）
- ✅ 暗黑主题风格
- ✅ HTTP 明文网络已配置（兼容 Flask）
- ✅ 启动画面
- ✅ PWA 支持（manifest.json）

#### 构建 APK

详细构建指南请见 [`android-app/BUILD_ANDROID.md`](android-app/BUILD_ANDROID.md)

快速开始：

```bash
# 打开 Android Studio
cd android-app
npx cap open android

# 或者直接构建（需安装 Android SDK）
cd android
gradlew assembleDebug
```

APK 产出：`android-app/android/app/build/outputs/apk/debug/app-debug.apk`

---

## 方案四：Flutter 重写前端（进阶）

**原理**：用 Flutter 完全重写前端 UI，后端仍使用现有 Flask API。

### 优点
- ✅ 真正的原生体验
- ✅ 可调用所有安卓 API（通知、蓝牙、文件系统等）
- ✅ 高性能

### 缺点
- ❌ 需要重写整个前端（数百行 Dart 代码）
- ❌ 需要学习 Flutter/Dart
- ❌ 维护两套前端代码

**推荐度**：仅当你有 Flutter 开发经验时考虑此方案。

---

## 功能兼容性对照表

| 功能                | PWA | Termux | WebView APK | Flutter |
|-------------------|:---:|:------:|:-----------:|:-------:|
| AI 对话            | ✅  | ✅     | ✅          | ✅      |
| 角色卡创建/编辑     | ✅  | ✅     | ✅          | ✅      |
| 语音合成 (TTS)     | ✅  | ⚠️¹    | ⚠️¹         | ✅²     |
| 骰子检定           | ✅  | ✅     | ✅          | ✅      |
| 数据库持久化        | ✅  | ✅     | ✅          | ✅      |
| 离线可用           | ❌³ | ✅⁴    | ❌³         | ❌³     |
| 安装大小           | 0KB | ~200MB | ~5MB        | ~20MB   |
| 开发成本           | 低   | 低     | 中          | 高      |

> ¹ Termux/WebView 中的 TTS 需要额外配置音频输出路由  
> ² Flutter 可调用原生 TTS 引擎  
> ³ 除非配置 Service Worker 离线缓存  
> ⁴ 不含外部 API 调用（DeepSeek/ZhipuAI 需联网）

---

## 推荐路线

1. **短期（立即可用）** → 使用 **Termux** 方案，零成本在手机上运行
2. **中期（分享给他人）** → 添加 **PWA** 支持 + 部署到云服务器
3. **长期（上架商店）** → **PWA + WebView 封装** 或 **Flutter 重写**

---

## 常见问题

### Q：安卓上 SQLite 兼容吗？
完全兼容。Python 的 `sqlite3` 模块在 Termux 中工作正常，数据库文件可直接复制迁移。

### Q：API 密钥放在 `.env` 里安全吗？
在 Termux 本地运行是安全的。如果部署到云端，**建议改用环境变量**而非文件存储，或使用服务端密钥管理服务。

### Q：语音合成（TTS）在安卓上能用吗？
- **Termux 方案**：Xunfei TTS 通过 WebSocket 调用，生成音频文件，可以在浏览器中播放
- **PWA 方案**：需要浏览器支持 `AudioContext` 播放 WAV，Chrome 安卓完全支持
- **Flutter 方案**：可直接调用安卓原生 TTS 引擎

### Q：如何在安卓上调试 Python 代码？
Termux 中可以用 `nano` 或 `vim` 编辑代码，也可以用 `python -c "..."` 快速测试。建议安装 VS Code 的 Remote SSH 插件远程开发。
