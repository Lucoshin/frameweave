# 映织 · Frameweave

面向多账号内容运营的 Windows 桌面工具，将账号管理、素材整理、文案生成、视频处理与发布准备放在同一个工作台中。

基于 Electron、Vue 3 和 Flask 构建，复用并修改了 `social-auto-upload-web-ui` 的平台适配代码。当前公开版本为 **0.1.0 源码版**，需要自行安装依赖并准备视频引擎。

## 功能

- **账号与素材管理**：管理平台账号、素材、草稿和发布记录；账号操作使用本机 Edge / Chrome 的独立持久浏览器环境。
- **视频处理**：通过外部 `MaterialHarvester.Cli` 和 FFmpeg 执行镜头分割、固定时长分割及组合混剪。
- **动画生成**：将 AI 生成的结构化分镜交给 Remotion 固定模板渲染为 MP4，支持图文动画、本地图片或 AI 配图，以及可选语音配音。
- **文案与 Word**：支持 AI 批量生成文字或图文 Word，也支持 `.docx` 模板与 JSON 数据的本地批量合并。
- **发布准备**：抖音、小红书、哔哩哔哩视频支持人工确认与自动发布两种模式，默认人工确认。其他平台能力以实际适配情况为准。
- **AI 服务配置**：支持兼容 OpenAI 接口格式的文本服务、图片服务，以及通用语音接口或 GPT-SoVITS v2。

自动发布返回“已提交”不等于平台审核通过。平台页面变化可能影响自动化；结果不确定时，应到平台核实后再操作。

## 环境准备

当前开发启动脚本使用 Windows 的 Python 虚拟环境路径。源码验证使用了 **Node.js 24.12.0、Python 3.14.0**，其他环境尚未完成同等验证。

开始前准备：

- Git、Node.js（含 npm）、Python。
- 已安装的 Microsoft Edge 或 Google Chrome。
- 可用的 `MaterialHarvester.Cli.exe`，以及它所需的 `ffmpeg.exe`、`ffprobe.exe`。这些文件不在本仓库中；自行构建视频引擎时还需要对应的 .NET SDK。
- 使用 AI 功能时所需的服务地址、模型和密钥。仓库不附带 AI 服务额度、模型权重或音色包。

## 从源码启动

以下命令在 **PowerShell** 中执行。

### 1. 获取代码并安装依赖

```powershell
git clone https://github.com/Lucoshin/frameweave.git
cd frameweave

npm ci
npm --prefix vendor/social-auto-upload-web-ui/frontend ci
npm --prefix apps/animation-renderer ci

python -m venv vendor/social-auto-upload-web-ui/backend/.venv
./vendor/social-auto-upload-web-ui/backend/.venv/Scripts/python.exe -m pip install -r vendor/social-auto-upload-web-ui/backend/requirements.txt
./vendor/social-auto-upload-web-ui/backend/.venv/Scripts/python.exe -m pip install -r vendor/social-auto-upload-web-ui/backend/requirements-dev.txt
```

### 2. 配置视频引擎并启动

将下面的示例路径替换为本机实际路径。开发环境必须显式指定视频引擎位置。

```powershell
$env:MATRIX_VIDEO_ENGINE = 'C:\tools\MaterialHarvester\MaterialHarvester.Cli.exe'
npm run dev
```

确保视频引擎能找到 FFmpeg 与 ffprobe。该命令同时启动 Flask 后端、Vite 开发界面与 Electron 桌面窗口，界面默认使用 `5173` 端口，后端连接默认使用 `5409` 端口。启动前请确保这两个端口可用。

进入设置页后，按需填写文本、图片及语音服务配置。AI 服务密钥需在页面会话中输入；刷新页面后需重新填写。不开启配音时，动画可以输出静音视频。

### 3. 可选运行配置

| 环境变量 | 用途 |
| --- | --- |
| `MATRIX_VIDEO_ENGINE` | 开发环境视频 CLI 可执行文件的绝对路径 |
| `MATRIX_RENDER_BROWSER` | 动画渲染使用的浏览器可执行文件路径 |
| `MATRIX_NODE_EXECUTABLE` | 动画渲染使用的 Node.js 可执行文件路径 |
| `MATRIX_ANIMATION_RENDERER` | 动画渲染工程目录 |
| `SAU_DATA_DIR` | 后端数据目录；开发环境默认位于 `vendor/social-auto-upload-web-ui/data/` |
| `FEEDBACK_APP_KEY` / `FEEDBACK_APP_SECRET` | 反馈服务凭据，公开源码不携带共享凭据 |

如需使用反馈服务，还可通过 `FEEDBACK_API_BASE_URL` 指定服务地址。这些环境变量应在启动应用前设置；根项目没有自动加载 `.env` 的启动步骤。

## 验证与构建

完成依赖安装后运行：

```powershell
npm test
npm run test:backend
npm --prefix apps/animation-renderer test
npm run build:ui:desktop
```

`npm run build` 会依次执行桌面测试、后端回归测试和桌面界面构建，不会自动下载或构建外部视频引擎与 Python 运行时。真实视频引擎集成测试需要额外的环境配置；普通代码测试不会向用户的平台账号发稿。

仓库提供 `build:video-engine`、`stage:video-engine` 和 `build:backend-runtime` 脚本用于准备打包资源，参数定义见 [scripts](scripts/)。准备好资源后，可使用 `npm run pack:win` 生成应用目录，或使用 `npm run dist:win` 生成 Windows 安装包。

**打包限制**：当前动画渲染主要面向开发环境。完整分发动画功能还需纳入动画渲染工程及其依赖、Node.js 运行时，并配置相应路径；仅执行安装包命令不会自动完成这些工作。

## 代码结构

```text
apps/
  desktop/                    Electron 主进程、共享契约与桌面测试
  animation-renderer/         Remotion 动画渲染工程
scripts/                     开发启动、构建与运行时准备脚本
vendor/social-auto-upload-web-ui/
  backend/                   Flask 后端与平台适配
  frontend/                  Vue 3 界面
  backend-mcp/               MCP（模型上下文协议）服务
```

账号会话、素材与数据库属于本地运行数据，不应提交到仓库。AI 请求会发送给所配置的服务；本项目并非完全离线运行。后端当前监听所有网络接口，适用于可信本机开发环境，请勿直接暴露到公网。

## 反馈与贡献

欢迎通过 [Issues](https://github.com/Lucoshin/frameweave/issues) 提交问题或功能建议。报告问题时，请附上系统版本、复现步骤和脱敏日志，不要上传平台 Cookie、账号数据库或服务密钥。

提交代码前，请运行与改动相关的测试，并说明实际验证过的功能和平台。

## 许可证与致谢

本项目新增代码采用 [MIT 许可证](LICENSE)。第三方代码与依赖保留各自的许可证，不因本项目使用 MIT 而改变。

感谢 `DevilJie/social-auto-upload-web-ui` 及其来源项目 `dreammis/social-auto-upload`。保留的上游许可证见 [vendor/social-auto-upload-web-ui/LICENSE](vendor/social-auto-upload-web-ui/LICENSE)，其他依赖说明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。Remotion 与独立分发的 FFmpeg 等组件需遵循各自适用的许可条款。
