# liyue-tools-comfy

ComfyUI 提示词 / LoRA 工具节点：从图片元数据读取提示词与 LoRA 组合，并可直接应用 LoRA。

分类：`漓月`

## 节点

### 图库提取

从图片中读取提示词、负向提示词和 LoRA 组合。

- 节点上点击「打开图库面板」浏览图片库
- 三栏面板：左侧文件夹树、中间瀑布流、右侧预览与提示词 / LoRA
- 左侧支持多个图库：`output`、自定义文件夹（可添加任意目录），以及子文件夹层级
- 支持把图片拖到节点上，或拖到文件夹树的具体文件夹里导入
- 图片可来自 output、自定义图库，或拖入后自动暂存到 `input/prompt_vault`

输出：

| 输出 | 说明 |
| --- | --- |
| image | 图片 |
| 正向提示词 | 正向提示词（已剔除 `<lora:...>` 标签） |
| 负向提示词 | 负向提示词 |
| LoRA组合 | `<lora:名字:权重>` 文本，可直接接 LoraManager 的语法输入或本插件的「应用 LoRA 组合」 |
| 元数据(JSON) | 来源文件、checkpoint、seed、尺寸等 |

### 应用 LoRA 组合

按 `LoRA组合` 文本加载 LoRA。

- 输入：`model`（必填）、`loras`、可选 `clip`
- 输出：叠加后的模型、CLIP、应用报告
- 缺失的 LoRA 默认跳过并在报告中列出；关闭 `skip_missing` 会直接报错
- 查找顺序：完整相对路径 → 自动补扩展名 → 按文件名在所有子目录中匹配

## 提示词解析支持

- 本插件保存的 PNG 元数据
- ComfyUI 原生 PNG 内嵌工作流（含提示词来自 K2、MiniMax 导入、PrimitiveString 等节点的链路）
- A1111 / WebUI 的 `parameters` 文本块（正向、负向、Seed、模型、LoRA 哈希名）
- 同名 `.txt` 文件

## LoRA 解析支持

- 官方 `LoraLoader` / `LoraLoaderModelOnly`
- rgthree `Power Lora Loader`（`lora_N`）与 `Lora Loader Stack`（`lora_01`）
- ComfyUI-Lora-Manager（`loras` 列表，按 `active` 过滤；`text` 语法）
- WeiLin `WeiLinPromptUIOnlyLoraStack`（`lora_str` JSON）
- `LoRA名称_N` 等字符串堆叠写法
- 提示词中的 `<lora:名:权重>` 标签

## 安装

把整个 `liyue-tools-comfy` 文件夹放进：

```
ComfyUI/custom_nodes/liyue-tools-comfy
```

重启 ComfyUI。

## 目录说明

- 图库配置：`ComfyUI/user/prompt_vault/sources.json`
- 缩略图缓存：`ComfyUI/user/prompt_vault/thumbs`
- 拖入 / 导入暂存：`ComfyUI/input/prompt_vault`

## 兼容性

- ComfyUI 0.45+（前端 1.58+）
- Windows / Linux / macOS
