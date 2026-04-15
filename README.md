# UnityApkBuilder

桌面小工具，用于对 Unity Android 工程执行命令行打包，并可将生成的 APK 安装到已连接的 Android 设备。

## 已跟踪文件

- `启动打包器.cmd`
- `apk_builder_gui.py`
- `build-and-install-android.ps1`
- `AndroidBuildTools.cs`
- `AndroidBuildTools.cs.meta`

## 不跟踪的本地文件

这些文件或目录是本机状态、输出物或缓存，不进入 git：

- `apk/`
- `configs/`
- `__pycache__/`
- `app_state.json`
- `last_session.json`
- `*.pyc`

## 已验证版本

- 该小工具已在 Unity 2022.3.62f2c1 环境下测试成功。
- 其他 Unity 版本理论上可能可用，但当前流程未做验证。

## 运行前提

目标电脑需要具备以下环境：

1. Python
- 需要能运行 `python`
- 需要带 Tkinter

2. Unity Editor
- 需要安装目标项目对应版本的 Unity
- 需要包含 Android Build Support

3. Android SDK
- 需要可用的 `adb.exe`

4. Unity 项目
- 目标目录必须是标准 Unity 工程
- 至少包含 `Assets/` 和 `ProjectSettings/`

5. 签名文件
- 如果项目构建需要自定义签名，需要准备 keystore、alias 和密码

## 启动方式

双击：

- `启动打包器.cmd`

它会启动 Python GUI。

## 首次配置

换一台电脑后，首次打开需要手动确认这些路径：

- `Project Path`
- `Unity.exe`
- `adb.exe`
- `Output Dir`
- `Keystore`
- `Alias Name`
- `Keystore Pass`
- `Alias Pass`

默认值是当前开发机上的路径，不能假设在别的电脑上仍然有效。

## 配置保存

工具支持两种配置保存方式：

1. 自动恢复上次会话
- 关闭工具时自动保存当前参数
- 下次启动自动恢复

2. 保存多套配置
- 点击 `Save Config` 保存当前参数为 `.json`
- 点击 `Load Config` 加载配置文件
- 菜单栏 `File -> Recent Configs` 可快速切换最近配置

说明：
- 配置文件目录默认是 `configs/`
- `configs/` 默认不进入 git
- 如果要共享某套配置，请手动拷贝对应 `.json`

## 构建流程

点击 `Start Build` 后，工具执行以下流程：

1. `Sync Build Script`
- 将 `AndroidBuildTools.cs` 注入到目标 Unity 工程的 `Assets/Editor/`

2. `Precompile`
- 启动一次 Unity `-batchmode`
- 让 Unity 导入并编译注入的 Editor 构建脚本

3. `Build APK`
- 第二次启动 Unity `-batchmode`
- 执行 `-executeMethod AndroidBuildTools.BuildAndroidRelease`

4. `Install`
- 如果没有勾选 `Build only, do not install to device`
- 则构建完成后自动检查 USB 设备并安装 APK

## 预编译复用

如果满足以下条件，工具会尝试跳过前两步中的部分步骤：

- 目标工程中的注入脚本与工具模板一致
- 已存在可复用的预编译标记
- Unity 路径未变化

建议：
- 如果希望后续重复打包更快，不要勾选 `Cleanup injected build script after build`
- 如果勾选了清理，工具仍会尽量保留预编译标记，但 `Sync Build Script` 通常更难跳过

## 独立安装按钮

工具提供独立的 `Install APK` 按钮。

点击后会依次检查：

1. `adb.exe` 是否存在
2. 当前 `Output Dir` + `APK Name` 对应的 APK 是否存在
3. 是否检测到已连接 Android 设备

任一步失败，都会弹窗提示原因。

## 日志与状态

- 窗口下方日志区会显示构建和安装输出
- 构建进行中时：
  - `Start Build`
  - `Install APK`
  - `Save Config`
  - `Load Config`
  会被禁用
- 构建结束后会恢复

## 常见问题

### 1. 别的电脑拉下来能不能直接用？
可以继续用，但通常需要先改路径。

原因：
- `Unity.exe`、`adb.exe`、项目路径、keystore 路径都是机器相关配置
- 工具源码可移植，不代表本机路径可移植

### 2. 为什么没有自动构建成功？
优先检查：

- Unity 版本是否匹配
- Android Build Support 是否安装
- keystore / alias / 密码是否正确
- 目标项目本身是否能在 Unity 命令行模式正常编译

### 3. 构建日志在哪？
默认写入目标 Unity 工程：

- `Logs/unity-android-precompile.log`
- `Logs/unity-android-build.log`

## 建议提交方式

建议在这个工具目录单独维护 git 仓库，不要混进 Unity 项目仓库。

原因：
- 它是一个独立工具
- 它有自己的本地状态文件和输出物
- 与具体 Unity 工程不是一一绑定关系

