# 📱 AI守秘人 — Android APK 构建指南

本文档指导你如何使用 **Capacitor** 将 [`coc_ai`](../) 项目打包为 Android APK。

> ⚠️ **如果你在国内无法访问 Android Studio 官网**，请优先使用 **方式一（GitHub Actions 云构建）** 或 **方式三（PWA）**，无需安装任何 Android 开发工具。

---

## 📋 先决条件

| 工具 | 版本要求 | 国内下载 |
|------|---------|---------|
| **Node.js** | ≥ 18 | https://nodejs.org/zh-cn/ |
| **Java JDK** | ≥ 17 | https://www.oracle.com/cn/java/technologies/downloads/ |
| **Android Studio** | 最新版 | [腾讯镜像](https://androidmirrors.tianyu.net/) / [阿里云镜像](https://mirrors.aliyun.com/android.googlesource.com/) |
| **Android SDK** | API 34+ | 通过 Android Studio SDK Manager 安装 |

---

## 🚀 方式一：GitHub Actions 云构建（无需本地 Android Studio）

**不需要安装 Android Studio 和 Android SDK**，只需将代码推送到 GitHub，APK 就会在 GitHub 的云服务器上自动构建。

### 步骤

1. **在 GitHub 上创建一个仓库**（如 `coc-keeper`）

2. **将项目推送到 GitHub**（在项目目录下执行）：
   ```bash
   git init
   git add .
   git commit -m "初始化项目"
   git remote add origin https://github.com/你的用户名/coc-keeper.git
   git push -u origin main
   ```

3. **进入 GitHub 仓库页面** → 点击 **Actions** 选项卡

4. **在左侧找到「构建 Android APK」** → 点击 **Run workflow** → 点击绿色 **Run workflow** 按钮

5. **等待 5-10 分钟**，构建完成后会出现一个名为 `coc-keeper-debug-apk` 的 Artifact

6. **下载 APK**：点击 Artifact 名称即可下载 `app-debug.apk`

### 后续更新

每次推送代码到 `main` 分支，或手动点击 **Run workflow**，都会自动重新构建最新 APK。

> 💡 **原理**：工作流定义在 [`.github/workflows/build-apk.yml`](.github/workflows/build-apk.yml)，GitHub 的 Ubuntu 运行环境已预装 Android SDK，无需你本地配置任何东西。

---

## 🚀 方式二：本地 Android Studio 构建

### 第 1 步：安装 Android Studio

由于官方网站在国内访问不稳定，可以使用以下国内镜像：

| 镜像源 | 地址 | 说明 |
|-------|------|------|
| **Android Studio 中文社区** | https://www.android-studio.cn/ | 提供官方安装包国内网盘 |
| **腾讯云镜像** | https://mirrors.cloud.tencent.com/AndroidSDK/ | SDK 组件镜像 |
| **阿里云镜像** | https://mirrors.aliyun.com/android.googlesource.com/ | AOSP 源码镜像 |

### 第 2 步：打开 Android Studio

```bash
# 在 android-app 目录下执行
cd android-app
npx cap open android
```

这会自动用 Android Studio 打开项目。

### 第 3 步：在 Android Studio 中构建 APK

1. **等待 Gradle 同步完成**
2. 连接安卓手机（开启 **USB 调试**），或启动模拟器
3. 点击顶部工具栏的 **Run ▶** 按钮（绿色三角）
4. 选择目标设备 → 等待构建安装

### 第 4 步：生成 APK 文件

菜单栏 → **Build** → **Build Bundle(s) / APK(s)** → **Build APK(s)**

构建完成后，APK 文件位于：
```
android\app\build\outputs\apk\debug\app-debug.apk
```

---

## 🌐 方式三：PWA 渐进式 Web 应用（零安装，推荐体验）

**PWA 不需要任何构建工具**，coc_ai 项目已经内置了 PWA 支持。

### 在 Android 手机上使用 PWA

1. **确保 Flask 后端在运行**（电脑或服务器上执行）：
   ```bash
   python app.py
   ```

2. **在手机 Chrome 浏览器中打开地址**：
   - 同一 Wi-Fi 下：`http://电脑IP:5000`（如 `http://192.168.1.100:5000`）
   - 本地运行：`http://localhost:5000`

3. **添加到主屏幕**：
   - 点击 Chrome 右上角菜单（⋮）
   - 选择 **「添加到主屏幕」**（Add to Home Screen）
   - 点击 **「添加」**

4. **使用体验**：
   - 桌面会出现应用图标，看起来和原生 App 一样
   - 全屏运行，无浏览器地址栏
   - 支持离线访问（缓存了核心资源）
   - 应用大小仅几百 KB

> 💡 **PWA 优势**：无需安装任何开发工具，无需构建，体验接近原生 App。适合日常使用。

---

## 📱 方式四：Termux 手机端直接运行（适合有编程基础的用户）

在 **手机端直接运行 Flask 后端**，无需额外电脑。

1. 安装 [Termux](https://f-droid.org/packages/com.termux/)（F-Droid 源，国内可访问）
2. 安装 [Termux:Widget](https://f-droid.org/packages/com.termux.widget/)（可选，用于快捷启动）
3. 在 Termux 中：
   ```bash
   # 更新包管理器
   pkg update && pkg upgrade -y
   
   # 安装 Python 和相关依赖
   pkg install python git -y
   pip install flask flask-cors openai zhipuai python-dotenv gunicorn
   
   # 克隆项目
   git clone https://github.com/你的用户名/coc-keeper.git
   cd coc-keeper
   
   # 配置 API 密钥（编辑 .env 文件）
   nano .env
   
   # 运行服务器
   python app.py
   ```
4. 手机浏览器打开 `http://localhost:5000` 即可使用
5. 配合 **PWA 添加到主屏幕**，体验接近原生 App

---

## ⚙️ 配置 Flask 后端地址

首次启动应用时，会显示**连接设置页面**，你可以选择：

### 📱 模式一：Termux 本地模式（推荐）

1. 在手机上安装 [Termux](https://f-droid.org/packages/com.termux/)
2. 将项目文件复制到手机
3. 在 Termux 中运行：
   ```bash
   pkg install python -y
   pip install flask flask-cors openai zhipuai python-dotenv
   cd /path/to/coc_ai
   python app.py
   ```
4. 在 App 中选择 **Termux 本地模式** → 连接

### ☁️ 模式二：云服务器模式

1. 将 Flask 后端部署到云服务器（如 阿里云、腾讯云）
2. 使用 gunicorn 部署：
   ```bash
   pip install gunicorn
   gunicorn -w 2 -b 0.0.0.0:5000 app:app
   ```
3. 在 App 中选择 **云服务器模式** → 输入服务器地址 → 连接

### 🔧 模式三：自定义地址

适用于局域网内调试（电脑运行 Flask，手机连接）：
1. 电脑运行 `python app.py`
2. 查看电脑局域网 IP（如 `192.168.1.100`）
3. 在 App 中选择 **自定义地址** → 输入 `http://192.168.1.100:5000`

---

## 🏗️ 从零开始创建项目（开发参考）

如果你需要**重新创建** Android 项目：

```bash
# 1. 进入项目根目录
cd coc_ai

# 2. 创建 android-app 目录
mkdir android-app
cd android-app

# 3. 初始化 npm 项目
npm init -y

# 4. 安装 Capacitor
npm install @capacitor/core @capacitor/cli @capacitor/android

# 5. 初始化 Capacitor
npx cap init "AI守秘人" "com.coc.keeper" --web-dir www

# 6. 准备 Web 资源（www 目录已有 index.html、manifest.json 等）
# 7. 添加 Android 平台
npx cap add android

# 8. 同步代码
npx cap sync android

# 9. 用 Android Studio 打开
npx cap open android
```

---

## 📂 项目结构

```
android-app/
├── package.json              # Node.js 项目配置
├── capacitor.config.json     # Capacitor 配置
├── .github/workflows/
│   └── build-apk.yml         # GitHub Actions 自动构建（云构建）
├── www/                      # Web 前端（入口页面）
│   ├── index.html           # 主页面（连接配置 + WebView 加载器）
│   ├── manifest.json        # PWA 清单
│   ├── icon-192.png         # 应用图标
│   └── icon-512.png         # 应用图标
├── android/                  # Android 原生项目
│   ├── build.gradle         # 顶层构建配置
│   ├── gradle.properties    # Gradle 属性
│   ├── gradlew / .bat       # Gradle 包装器
│   ├── settings.gradle      # 项目设置
│   ├── app/
│   │   ├── build.gradle     # 应用模块构建配置
│   │   └── src/main/
│   │       ├── AndroidManifest.xml    # 清单文件（已配置网络权限）
│   │       ├── java/com/coc/keeper/
│   │       │   └── MainActivity.java  # 主 Activity
│   │       ├── res/
│   │       │   ├── values/
│   │       │   │   ├── styles.xml     # 主题样式（暗黑主题）
│   │       │   │   ├── colors.xml     # 颜色定义
│   │       │   │   └── strings.xml    # 字符串
│   │       │   ├── xml/
│   │       │   │   ├── config.xml              # Cordova 配置
│   │       │   │   ├── file_paths.xml          # 文件路径配置
│   │       │   │   └── network_security_config.xml  # 网络安全配置（允许 HTTP）
│   │       │   ├── drawable*/splash.png       # 启动画面
│   │       │   └── mipmap*/ic_launcher*.png   # 应用图标
│   │       └── assets/
│   │           └── public/    # 自动同步的 Web 资源
└── BUILD_ANDROID.md          # 本构建指南
```

---

## ❓ 常见问题

### Q: 国内无法访问 Android Studio 官网怎么办？
**A:** 使用以下方式之一：
- ✅ **方式一**：使用 GitHub Actions 云构建（推荐，详见上方）
- ✅ **方式三**：直接使用 PWA 添加到主屏幕，无需安装任何东西
- 🔗 Android Studio 中文社区：https://www.android-studio.cn/
- 🔗 腾讯软件中心：https://pc.qq.com/ 搜索 "Android Studio"

### Q: 构建时提示 `SDK location not found`
**A:** 打开 Android Studio → **SDK Manager** → 安装 Android SDK（API 34+），并设置环境变量：
```
ANDROID_HOME=C:\Users\用户名\AppData\Local\Android\Sdk
```

### Q: 连接本地 Flask 失败
**A:**
- 确保手机和电脑在同一 Wi-Fi 网络
- 关闭电脑防火墙或添加 5000 端口例外
- Flask 运行在 `0.0.0.0:5000`（已在 app.py 中配置）
- 在 WebView 入口页选择正确的连接模式

### Q: 如何修改应用名称/图标？
**A:**
- 名称：修改 [`res/values/strings.xml`](android/app/src/main/res/values/strings.xml) 中的 `app_name`
- 图标：替换 `res/mipmap-*/ic_launcher*.png` 各尺寸图标

### Q: 如何修改版本号？
**A:** 修改 [`app/build.gradle`](android/app/build.gradle) 中的：
```groovy
defaultConfig {
    versionCode 2          # 每次上传商店递增
    versionName "1.0.1"    # 显示给用户的版本号
}
```

### Q: GitHub Actions 构建失败怎么办？
**A:**
1. 点击 Actions 页面中失败的运行记录
2. 查看具体的错误日志
3. 常见问题：`gradlew` 权限不足 → 工作流已自动修复
4. 如果持续失败，请在 GitHub 提交 Issue

---

> 💡 **提示**：如果没有 Android Studio，也可以使用命令行构建（需安装 Android SDK）：
> ```bash
> cd android
> gradlew assembleDebug
> ```
> APK 产出：`app/build/outputs/apk/debug/app-debug.apk`
