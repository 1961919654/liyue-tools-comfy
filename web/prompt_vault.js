import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const NODE_NAME = "PromptVaultLoad";
const PAGE_SIZE = 60;

const STYLE = `
.pv-mask {
  position: fixed; inset: 0; z-index: 100000;
  display: none; align-items: center; justify-content: center;
  background: rgba(0, 0, 0, .65); backdrop-filter: blur(2px);
}
.pv-dialog {
  position: relative;
  width: min(1180px, 96vw); height: min(820px, 92vh);
  min-width: min(760px, 96vw); min-height: min(460px, 92vh);
  max-width: 98vw; max-height: 96vh;
  display: flex; flex-direction: column; gap: 10px;
  padding: 12px 14px; box-sizing: border-box;
  background: var(--comfy-menu-bg, #1c1c1c);
  border: 1px solid var(--border-color, #3a3a3a);
  border-radius: 12px;
  box-shadow: 0 24px 70px rgba(0, 0, 0, .6);
  color: var(--input-text, #e6e6e6);
  font: 13px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif;
  overflow: hidden;
}
.pv-resize { position: absolute; z-index: 3; }
.pv-resize-e { top: 10px; right: 0; width: 6px; height: calc(100% - 20px); cursor: ew-resize; }
.pv-resize-s { left: 10px; bottom: 0; height: 6px; width: calc(100% - 20px); cursor: ns-resize; }
.pv-resize-se {
  right: 2px; bottom: 2px; width: 18px; height: 18px; border-radius: 3px;
  cursor: nwse-resize; opacity: .5;
  background:
    linear-gradient(135deg, transparent 0 55%, #9a9a9a 55% 62%, transparent 62% 70%, #9a9a9a 70% 77%, transparent 77% 85%, #9a9a9a 85% 92%, transparent 92%);
}
.pv-resize-se:hover { opacity: 1; }
.pv-node-preview {
  width: 100%; height: 100%; min-height: 210px;
  display: flex; align-items: center; justify-content: center;
  background: #111; border-radius: 6px; overflow: hidden;
}
.pv-node-preview img {
  max-width: 100%; max-height: 100%; object-fit: contain; display: block;
}
.pv-head { display: flex; align-items: center; justify-content: space-between; }
.pv-head h3 { margin: 0; font-size: 15px; font-weight: 600; }
.pv-close {
  width: 28px; height: 28px; border-radius: 6px; cursor: pointer;
  background: transparent; color: inherit; border: 1px solid transparent;
  font-size: 18px; line-height: 1;
}
.pv-close:hover { border-color: #555; background: #ffffff10; }
.pv-btn {
  padding: 6px 10px; border-radius: 7px; cursor: pointer; white-space: nowrap;
  background: var(--comfy-input-bg, #2a2a2a); color: inherit;
  border: 1px solid var(--border-color, #3d3d3d);
}
.pv-btn:hover:not(:disabled) { border-color: #5b9dff; color: #fff; }
.pv-btn:disabled { opacity: .45; cursor: default; }
.pv-search {
  flex: 1 1 auto; min-width: 120px; padding: 6px 10px; border-radius: 7px;
  background: var(--comfy-input-bg, #262626); color: inherit;
  border: 1px solid var(--border-color, #3d3d3d); outline: none;
}
.pv-count { opacity: .6; font-variant-numeric: tabular-nums; font-size: 12px; }
.pv-body { flex: 1 1 auto; display: flex; gap: 12px; min-height: 0; }

.pv-tree {
  width: 210px; flex: 0 0 210px; overflow-y: auto; min-height: 0;
  border-right: 1px solid #ffffff12; padding-right: 8px;
}
.pv-tree-head { display: flex; align-items: center; justify-content: space-between; padding: 2px 4px 6px; }
.pv-tree-actions { display: flex; align-items: center; gap: 2px; }
.pv-tree-title {
  font-size: 11px; text-transform: uppercase; letter-spacing: .6px; opacity: .45;
}
.pv-tree-add {
  width: 22px; height: 22px; border-radius: 5px; cursor: pointer;
  background: transparent; color: #9bbcff; border: 1px solid transparent;
  font-size: 15px; line-height: 1; padding: 0;
}
.pv-tree-add:hover { border-color: #555; background: #ffffff10; }
.pv-tree-item {
  display: flex; align-items: center; gap: 5px;
  padding: 4px 6px; border-radius: 6px; cursor: pointer;
  color: #cfcfcf; font-size: 12px; user-select: none;
}
.pv-tree-item:hover { background: #ffffff10; color: #fff; }
.pv-tree-item.is-active { background: #2f6fdd33; color: #fff; }
.pv-tree-item.is-drop { background: #2f6fdd55; outline: 1px dashed #5b9dff; }
.pv-tree-arrow {
  width: 12px; flex: 0 0 12px; text-align: center;
  opacity: .7; font-size: 10px;
}
.pv-tree-name { flex: 1 1 auto; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pv-tree-count { font-size: 10px; opacity: .5; font-variant-numeric: tabular-nums; }
.pv-tree-add-item {
  width: 16px; flex: 0 0 16px; text-align: center; font-size: 12px;
  color: #9bbcff; opacity: 0; cursor: pointer; transition: opacity .12s;
}
.pv-tree-item:hover .pv-tree-add-item { opacity: .95; }
.pv-tree-del {
  width: 14px; flex: 0 0 14px; text-align: center; font-size: 13px;
  color: #ff9b9b; opacity: 0; cursor: pointer; transition: opacity .12s;
}
.pv-tree-item:hover .pv-tree-del { opacity: .95; }
.pv-tree-empty { padding: 14px 6px; opacity: .4; font-size: 12px; }

.pv-main {
  flex: 1 1 auto; min-width: 0; min-height: 0; overflow: hidden;
  display: flex; flex-direction: column; gap: 8px;
}
.pv-masonry {
  flex: 1 1 0; min-height: 0; overflow-y: auto; overflow-x: hidden;
  columns: 4 140px; column-gap: 8px; padding: 2px 2px 6px;
}
.pv-masonry.is-grid {
  columns: auto; display: grid; align-content: start; gap: 8px;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
}
.pv-masonry.is-grid .pv-card { margin: 0; display: flex; flex-direction: column; }
.pv-masonry.is-grid .pv-card img { aspect-ratio: 1 / 1; object-fit: cover; }
.pv-masonry.is-grid .pv-card-meta { flex: 1 1 auto; }
.pv-card {
  break-inside: avoid; margin: 0 0 10px; padding: 3px;
  border: 2px solid transparent; border-radius: 8px;
  background: #ffffff05; cursor: pointer;
}
.pv-card:hover { border-color: #5b9dff66; }
.pv-card.is-active { border-color: #5b9dff; box-shadow: 0 0 0 2px #5b9dff33; }
.pv-card.is-selected { border-color: #ff9b5b; box-shadow: 0 0 0 2px #ff9b5b44; }
.pv-btn-danger { color: #ffb3b3; }
.pv-btn-danger:not(:disabled):hover { border-color: #ff7b7b; color: #fff; }
.pv-card img { width: 100%; display: block; border-radius: 6px; background: #111; }
.pv-card.is-broken img { min-height: 90px; }
.pv-card-meta { padding: 4px 2px 0; font-size: 10px; color: #8f8f8f; line-height: 1.5; }
.pv-card-name { color: #c8c8c8; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pv-tag {
  display: inline-block; margin-left: 4px; padding: 0 4px;
  border-radius: 3px; background: #2f6fdd55; color: #cfe0ff; font-size: 9px;
}
.pv-empty { padding: 34px 10px; text-align: center; opacity: .55; column-span: all; }
.pv-bottom { display: flex; gap: 8px; align-items: center; }
.pv-bottom .pv-btn { flex: 0 0 auto; padding: 6px 16px; }
.pv-view-toggle, .pv-order-toggle {
  flex: 0 0 auto; width: 30px;
  display: inline-flex; align-items: center; justify-content: center;
}
.pv-bottom .pv-view-toggle, .pv-bottom .pv-order-toggle { padding: 6px 0; }
.pv-sort {
  flex: 0 0 auto; padding: 6px 8px; border-radius: 7px; cursor: pointer;
  background: var(--comfy-input-bg, #262626); color: inherit;
  border: 1px solid var(--border-color, #3d3d3d); outline: none; font-size: 12px;
}
.pv-sort:hover { border-color: #5b9dff; }
.pv-sort option { background: #262626; color: #e6e6e6; }

.pv-side {
  width: 330px; flex: 0 0 330px; display: flex; flex-direction: column; gap: 8px;
  border-left: 1px solid #ffffff12; padding-left: 12px; min-height: 0;
}
.pv-preview {
  flex: 0 0 auto; height: 220px; border-radius: 8px; overflow: hidden;
  background: #111; display: flex; align-items: center; justify-content: center;
}
.pv-preview img { max-width: 100%; max-height: 100%; object-fit: contain; }
.pv-label {
  font-size: 11px; text-transform: uppercase; letter-spacing: .6px;
  opacity: .45; margin-top: 2px;
}
.pv-prompt-head { display: flex; align-items: center; justify-content: space-between; gap: 6px; }
.pv-copy-btn {
  display: inline-flex; align-items: center; justify-content: center;
  padding: 2px 4px; border: none; border-radius: 4px; background: transparent;
  color: inherit; opacity: .45; cursor: pointer;
}
.pv-copy-btn:hover { opacity: 1; background: #ffffff14; }
.pv-copy-btn:disabled { opacity: .18; cursor: default; background: transparent; }
.pv-prompt-blocks {
  flex: 1 1 auto; min-height: 0;
  display: flex; flex-direction: column; gap: 6px;
}
.pv-prompt-block {
  flex: 1 1 0; min-height: 0;
  display: flex; flex-direction: column; gap: 4px;
}
.pv-prompt-block.is-negative { flex: 0 0 96px; }
.pv-prompt-block.is-negative .pv-prompt-box { min-height: 0; }
.pv-prompt-box {
  flex: 1 1 0; min-height: 44px; overflow-y: auto; white-space: pre-wrap;
  word-break: break-word; font-size: 12px; line-height: 1.55;
  background: #ffffff08; border-radius: 7px; padding: 8px;
}
.pv-prompt-box.is-empty, .pv-loras.is-empty { opacity: .45; font-style: italic; }
.pv-head-actions { display: flex; align-items: center; gap: 4px; }
.pv-dialog.is-full {
  width: 100vw !important; height: 100vh !important;
  max-width: 100vw; max-height: 100vh;
  border-radius: 0; border: none;
}
.pv-loras {
  flex: 0 1 auto; max-height: 30vh; overflow-y: auto;
  background: #ffffff08; border-radius: 7px; padding: 6px 8px;
  font-size: 12px; display: flex; flex-direction: column; gap: 4px;
}
.pv-dialog.is-full .pv-loras { max-height: 36vh; }
.pv-dialog.is-full .pv-preview { height: 34vh; }
.pv-lora-row { display: flex; align-items: flex-start; gap: 6px; min-width: 0; }
.pv-lora-name {
  flex: 1 1 auto; min-width: 0; line-height: 1.35;
  white-space: normal; word-break: break-all; color: #d6d6d6;
}
.pv-lora-strength { flex: 0 0 auto; font-size: 10px; opacity: .65; font-variant-numeric: tabular-nums; }
.pv-footer {
  display: flex; align-items: center; justify-content: space-between; gap: 10px;
  border-top: 1px solid #ffffff12; padding-top: 9px;
}
.pv-selected { font-size: 12px; opacity: .65; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pv-confirm {
  padding: 7px 16px; border-radius: 7px; cursor: pointer; white-space: nowrap;
  background: #2f6fdd; color: #fff; border: 1px solid #2f6fdd; font-weight: 600;
}
.pv-confirm:hover { background: #3b7be8; }
.pv-confirm:disabled { opacity: .45; cursor: default; }
`;

function installStyle() {
  if (document.getElementById("pv-panel-style")) return;
  const style = document.createElement("style");
  style.id = "pv-panel-style";
  style.textContent = STYLE;
  document.head.appendChild(style);
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

const ICON_COPY =
  '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>';
const ICON_DONE =
  '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>';
const ICON_MASONRY =
  '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><rect x="3" y="3" width="7" height="10" rx="1"/><rect x="14" y="3" width="7" height="6" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/></svg>';
const ICON_GRID =
  '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>';

async function copyToClipboard(text) {
  try {
    await navigator.clipboard.writeText(text);
  } catch (error) {
    const area = document.createElement("textarea");
    area.value = text;
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.append(area);
    area.select();
    document.execCommand("copy");
    area.remove();
  }
}

function makeCopyButton(getText) {
  const button = el("button", "pv-copy-btn");
  button.type = "button";
  button.title = "复制";
  button.disabled = true;
  button.innerHTML = ICON_COPY;
  button.addEventListener("click", async (event) => {
    event.stopPropagation();
    const text = String(getText() || "").trim();
    if (!text) return;
    await copyToClipboard(text);
    button.innerHTML = ICON_DONE;
    button.title = "已复制";
    setTimeout(() => {
      button.innerHTML = ICON_COPY;
      button.title = "复制";
    }, 1200);
  });
  return button;
}

function imageUrl(route) {
  try {
    if (typeof api.apiURL === "function") return api.apiURL(route);
  } catch (error) {
    /* 旧前端没有 apiURL 时退回原路径 */
  }
  return route;
}

function baseName(path) {
  return String(path || "").split(/[\\/]/).pop() || "";
}

function isImageFile(file) {
  return !!file && (file.type?.startsWith("image/")
    || /\.(png|jpe?g|webp|bmp|gif|tiff?)$/i.test(file.name || ""));
}

function joinPath(root, relative) {
  const base = String(root || "").replace(/[\\/]+$/, "");
  const tail = String(relative || "").replace(/^[\\/]+/, "").replace(/\//g, "\\");
  return tail ? `${base}\\${tail}` : base;
}

function formatSize(bytes) {
  if (!bytes) return "";
  const units = ["B", "KB", "MB", "GB"];
  let value = Number(bytes);
  let index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  return `${value.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

function formatDate(timestamp) {
  const date = new Date(Number(timestamp || 0) * 1000);
  if (Number.isNaN(date.getTime())) return "";
  const pad = value => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

// ---------------------------------------------------------------------------
// 节点外观：按钮 + 已选图片预览
// ---------------------------------------------------------------------------
function installNode(node) {
  installStyle();
  const pathWidget = node.widgets?.find(widget => widget.name === "image_path");
  if (!pathWidget) return;

  pathWidget.computeSize = () => [0, -4];
  pathWidget.draw = () => {};
  if (pathWidget.inputEl) pathWidget.inputEl.style.display = "none";
  if (pathWidget.element) pathWidget.element.style.display = "none";

  const button = node.addWidget("button", "打开图库面板", null, () => openPanel(node, pathWidget), { serialize: false });
  button.serialize = false;

  let hasImage = false;
  const previewWrap = document.createElement("div");
  previewWrap.className = "pv-node-preview";
  previewWrap.style.display = "none";
  const previewImage = document.createElement("img");
  previewWrap.append(previewImage);
  node.addDOMWidget("pv_preview", "prompt_vault_preview", previewWrap, {
    serialize: false,
    hideOnZoom: false,
    margin: 8,
    getMinHeight: () => (hasImage ? 230 : 0),
    getMaxHeight: () => 230,
  });

  let currentPath = "";
  function updatePreview(path) {
    const text = String(path || "").trim();
    if (text === currentPath) return;
    currentPath = text;
    const next = !!text;
    const changed = next !== hasImage;
    hasImage = next;
    if (!text) {
      previewImage.removeAttribute("src");
      previewWrap.style.display = "none";
    } else {
      previewWrap.style.display = "flex";
      previewImage.src = imageUrl(`/prompt_vault/thumb?path=${encodeURIComponent(text)}&v=${Date.now()}&s=1024`);
    }
    if (changed) {
      node.setSize([node.size[0], hasImage ? 360 : 96]);
      node.setDirtyCanvas(true, true);
    }
  }

  node.__pvPathWidget = pathWidget;
  node.__pvUpdatePreview = updatePreview;
  updatePreview(pathWidget.value);

  async function loadDroppedFile(file) {
    if (!file) return;
    const form = new FormData();
    form.append("image", file);
    form.append("type", "input");
    form.append("subfolder", "prompt_vault");
    let data;
    try {
      const response = await api.fetchApi("/upload/image", { method: "POST", body: form });
      if (!response.ok) {
        alert("图片上传失败");
        return;
      }
      data = await response.json();
    } catch (error) {
      alert(`图片上传失败：${error}`);
      return;
    }
    try {
      const resolved = await api.fetchApi(`/prompt_vault/stage_path?name=${encodeURIComponent(data.name)}`);
      const info = await resolved.json();
      if (!resolved.ok || !info.path) {
        alert(info.error || "获取图片路径失败");
        return;
      }
      pathWidget.value = info.path;
      try {
        pathWidget.callback?.(info.path);
      } catch (error) {
        /* 忽略 widget 回调异常 */
      }
      node.__pvUpdatePreview?.(info.path);
      node.setDirtyCanvas(true, true);
    } catch (error) {
      alert(`获取图片路径失败：${error}`);
    }
  }

  previewWrap.addEventListener("dragover", event => {
    event.preventDefault();
    event.stopPropagation();
  });
  previewWrap.addEventListener("drop", event => {
    event.preventDefault();
    event.stopPropagation();
    const file = [...(event.dataTransfer?.files || [])].find(isImageFile);
    if (file) void loadDroppedFile(file);
  });

  node.onDragOver = function () { return true; };
  const dragDrop = node.onDragDrop;
  node.onDragDrop = function (event) {
    const file = [...(event.dataTransfer?.files || [])].find(isImageFile);
    if (!file) return dragDrop?.apply(this, arguments) ?? false;
    void loadDroppedFile(file);
    return true;
  };

  node.setSize([Math.max(node.size?.[0] ?? 320, 360), hasImage ? 360 : 96]);
}

// ---------------------------------------------------------------------------
// 图库面板（全局单例）
// ---------------------------------------------------------------------------
let PANEL = null;
let CURRENT = null;

function ensurePanel() {
  if (PANEL) return PANEL;
  installStyle();

  const mask = el("div", "pv-mask");
  const dialog = el("div", "pv-dialog");

  const head = el("div", "pv-head");
  head.append(el("h3", null, "漓月 · 图库"));
  const closeButton = el("button", "pv-close", "×");
  closeButton.title = "关闭";
  const fullscreenButton = el("button", "pv-close", "⛶");
  fullscreenButton.title = "网页全屏";
  const headActions = el("div", "pv-head-actions");
  headActions.append(fullscreenButton, closeButton);
  head.append(headActions);

  const body = el("div", "pv-body");

  const tree = el("aside", "pv-tree");
  const treeHead = el("div", "pv-tree-head");
  treeHead.append(el("div", "pv-tree-title", "文件夹"));
  const treeActions = el("div", "pv-tree-actions");
  const addSourceButton = el("button", "pv-tree-add", "＋");
  addSourceButton.title = "添加图库文件夹";
  const refreshTreeButton = el("button", "pv-tree-add", "↻");
  refreshTreeButton.title = "刷新文件夹";
  treeActions.append(addSourceButton, refreshTreeButton);
  treeHead.append(treeActions);
  tree.append(treeHead);

  const main = el("div", "pv-main");
  const masonry = el("div", "pv-masonry");
  const bottomBar = el("div", "pv-bottom");
  const searchInput = el("input", "pv-search");
  searchInput.type = "search";
  searchInput.placeholder = "搜索文件名…";
  const countLabel = el("span", "pv-count", "0 / 0");
  const viewButton = el("button", "pv-btn pv-view-toggle");
  viewButton.type = "button";
  const sortSelect = el("select", "pv-sort");
  sortSelect.title = "排序方式";
  for (const [value, label] of [
    ["date", "修改日期"], ["name", "文件名"], ["size", "文件大小"], ["resolution", "分辨率"],
  ]) {
    const option = el("option", null, label);
    option.value = value;
    sortSelect.append(option);
  }
  const orderButton = el("button", "pv-btn pv-order-toggle");
  orderButton.type = "button";
  const deleteButton = el("button", "pv-btn pv-btn-danger", "删除");
  deleteButton.title = "删除选中的图片（Ctrl 多选 / Shift 连选）";
  deleteButton.disabled = true;
  const refreshButton = el("button", "pv-btn", "↻");
  refreshButton.title = "刷新图库";
  bottomBar.append(searchInput, viewButton, sortSelect, orderButton,
    countLabel, deleteButton, refreshButton);
  main.append(masonry, bottomBar);

  const side = el("aside", "pv-side");
  const previewBox = el("div", "pv-preview");
  const previewImage = el("img");
  previewBox.append(previewImage);
  side.append(previewBox);

  let currentPositive = "";
  let currentNegative = "";
  const positiveCopyButton = makeCopyButton(() => currentPositive);
  const negativeCopyButton = makeCopyButton(() => currentNegative);

  const promptBlocks = el("div", "pv-prompt-blocks");
  const positiveBlock = el("div", "pv-prompt-block is-positive");
  const positiveHead = el("div", "pv-prompt-head");
  positiveHead.append(el("div", "pv-label", "正向提示词"), positiveCopyButton);
  positiveBlock.append(positiveHead);
  const positiveBox = el("div", "pv-prompt-box is-empty", "选择中间图片后显示正向提示词。");
  positiveBlock.append(positiveBox);
  const negativeBlock = el("div", "pv-prompt-block is-negative");
  const negativeHead = el("div", "pv-prompt-head");
  negativeHead.append(el("div", "pv-label", "负向提示词"), negativeCopyButton);
  negativeBlock.append(negativeHead);
  const negativeBox = el("div", "pv-prompt-box is-empty", "这张图没有负向提示词。");
  negativeBlock.append(negativeBox);
  promptBlocks.append(positiveBlock, negativeBlock);
  side.append(promptBlocks);

  side.append(el("div", "pv-label", "LoRA"));
  const loraBox = el("div", "pv-loras is-empty", "选择图片后显示所用 LoRA。");
  side.append(loraBox);

  const footer = el("div", "pv-footer");
  const selectedLabel = el("span", "pv-selected", "未选择图片");
  const confirmButton = el("button", "pv-confirm", "使用这张图");
  confirmButton.disabled = true;
  footer.append(selectedLabel, confirmButton);
  side.append(footer);

  body.append(tree, main, side);

  const fileInput = el("input");
  fileInput.type = "file";
  fileInput.accept = "image/*";
  fileInput.multiple = true;
  fileInput.hidden = true;

  dialog.append(head, body, fileInput);

  const resizeE = el("div", "pv-resize pv-resize-e");
  const resizeS = el("div", "pv-resize pv-resize-s");
  const resizeSE = el("div", "pv-resize pv-resize-se");
  resizeSE.title = "拖动调整面板大小";
  dialog.append(resizeE, resizeS, resizeSE);

  function saveSize() {
    try {
      localStorage.setItem("pv.panel.size", JSON.stringify({
        width: dialog.style.width,
        height: dialog.style.height,
      }));
    } catch (error) {
      /* 无痕模式等场景忽略 */
    }
  }

  function restoreSize() {
    try {
      const raw = localStorage.getItem("pv.panel.size");
      if (!raw) return;
      const data = JSON.parse(raw);
      if (data.width) dialog.style.width = data.width;
      if (data.height) dialog.style.height = data.height;
    } catch (error) {
      /* 损坏数据忽略 */
    }
  }

  function attachResize(handle, directions) {
    handle.addEventListener("pointerdown", event => {
      if (event.button !== 0) return;
      event.preventDefault();
      event.stopPropagation();
      const rect = dialog.getBoundingClientRect();
      const startX = event.clientX;
      const startY = event.clientY;
      const startWidth = rect.width;
      const startHeight = rect.height;
      const move = moveEvent => {
        if (directions.includes("e")) {
          const maxWidth = window.innerWidth - 32;
          const width = Math.max(Math.min(760, maxWidth), Math.min(maxWidth, startWidth + moveEvent.clientX - startX));
          dialog.style.width = `${width}px`;
        }
        if (directions.includes("s")) {
          const maxHeight = window.innerHeight - 32;
          const height = Math.max(Math.min(460, maxHeight), Math.min(maxHeight, startHeight + moveEvent.clientY - startY));
          dialog.style.height = `${height}px`;
        }
      };
      const up = () => {
        window.removeEventListener("pointermove", move);
        window.removeEventListener("pointerup", up);
        saveSize();
      };
      window.addEventListener("pointermove", move);
      window.addEventListener("pointerup", up);
    });
  }

  attachResize(resizeE, "e");
  attachResize(resizeS, "s");
  attachResize(resizeSE, "es");
  restoreSize();

  mask.append(dialog);
  document.body.append(mask);

  const state = {
    source: "output", folder: "", query: "", offset: 0, total: 0, busy: false,
    importTarget: "", selected: new Set(), lastPath: "",
    view: "masonry", sort: "date", order: "desc",
  };
  const panel = {
    mask, state, selectedPath: "", sources: [], expanded: new Set([""]), items: [],
  };
  let searchTimer = 0;

  // 恢复上次的视图与排序偏好
  try {
    state.view = localStorage.getItem("pv.view") === "grid" ? "grid" : "masonry";
    const savedSort = localStorage.getItem("pv.sort");
    if (["date", "name", "size", "resolution"].includes(savedSort)) state.sort = savedSort;
    const savedOrder = localStorage.getItem("pv.order");
    if (savedOrder === "asc" || savedOrder === "desc") state.order = savedOrder;
  } catch (error) {
    /* 本地存储不可用时使用默认值 */
  }

  function savePrefs() {
    try {
      localStorage.setItem("pv.view", state.view);
      localStorage.setItem("pv.sort", state.sort);
      localStorage.setItem("pv.order", state.order);
    } catch (error) {
      /* 无痕模式等场景忽略 */
    }
  }

  function applyView() {
    const grid = state.view === "grid";
    masonry.classList.toggle("is-grid", grid);
    viewButton.innerHTML = grid ? ICON_MASONRY : ICON_GRID;
    viewButton.title = grid ? "切换为瀑布流视图" : "切换为平铺视图";
    sortSelect.value = state.sort;
    orderButton.textContent = state.order === "asc" ? "↑" : "↓";
    orderButton.title = state.order === "asc"
      ? "当前升序，点击切换为降序"
      : "当前降序，点击切换为升序";
  }

  applyView();

  let promptToken = 0;

  function currentSource() {
    return panel.sources.find(source => source.id === state.source) || null;
  }

  function refreshFooter() {
    selectedLabel.textContent = panel.selectedPath ? baseName(panel.selectedPath) : "未选择图片";
    selectedLabel.title = panel.selectedPath || "";
    confirmButton.disabled = !panel.selectedPath;
  }

  function refreshSelection() {
    for (const cell of masonry.querySelectorAll(".pv-card")) {
      cell.classList.toggle("is-active", cell.dataset.path === panel.selectedPath);
      cell.classList.toggle("is-selected", state.selected.has(cell.dataset.path));
    }
    deleteButton.disabled = state.selected.size === 0;
    deleteButton.textContent = state.selected.size ? `删除 (${state.selected.size})` : "删除";
  }

  function selectRange(fromPath, toPath) {
    const entries = [...masonry.querySelectorAll(".pv-card")]
      .map(card => ({ card, rect: card.getBoundingClientRect() }))
      .filter(entry => entry.rect.height > 0);

    // 按顶部位置分组为视觉行，行内从左到右
    entries.sort((a, b) => a.rect.top - b.rect.top || a.rect.left - b.rect.left);
    const rows = [];
    for (const entry of entries) {
      const row = rows[rows.length - 1];
      if (row && Math.abs(entry.rect.top - row.top) <= 40) {
        row.items.push(entry);
      } else {
        rows.push({ top: entry.rect.top, items: [entry] });
      }
    }
    for (const row of rows) row.items.sort((a, b) => a.rect.left - b.rect.left);

    let fromRow = -1;
    let fromCol = -1;
    let toRow = -1;
    let toCol = -1;
    rows.forEach((row, rowIndex) => {
      row.items.forEach((entry, colIndex) => {
        if (entry.card.dataset.path === fromPath) {
          fromRow = rowIndex;
          fromCol = colIndex;
        }
        if (entry.card.dataset.path === toPath) {
          toRow = rowIndex;
          toCol = colIndex;
        }
      });
    });
    if (fromRow < 0 || toRow < 0) return;

    if (fromRow > toRow || (fromRow === toRow && fromCol > toCol)) {
      [fromRow, toRow] = [toRow, fromRow];
      [fromCol, toCol] = [toCol, fromCol];
    }

    state.selected.clear();
    for (let rowIndex = fromRow; rowIndex <= toRow; rowIndex += 1) {
      const start = rowIndex === fromRow ? fromCol : 0;
      const end = rowIndex === toRow ? toCol : rows[rowIndex].items.length - 1;
      for (let colIndex = start; colIndex <= end; colIndex += 1) {
        state.selected.add(rows[rowIndex].items[colIndex].card.dataset.path);
      }
    }
  }

  function showInfo(info) {
    const loras = Array.isArray(info.loras) ? info.loras : [];
    const positive = String(info.positive || "").trim();
    const negative = String(info.negative || "").trim();
    currentPositive = positive;
    currentNegative = negative;
    positiveBox.textContent = positive || "这张图没有正向提示词。";
    positiveBox.classList.toggle("is-empty", !positive);
    positiveCopyButton.disabled = !positive;
    negativeBox.textContent = negative || "这张图没有负向提示词。";
    negativeBox.classList.toggle("is-empty", !negative);
    negativeCopyButton.disabled = !negative;

    loraBox.innerHTML = "";
    if (!loras.length) {
      loraBox.append(el("div", null, "这张图没有 LoRA 信息。"));
      loraBox.classList.add("is-empty");
    } else {
      loraBox.classList.remove("is-empty");
      for (const lora of loras) {
        const row = el("div", "pv-lora-row");
        const name = String(lora.name || "");
        const strength = Number(lora.strength_model ?? 1);
        const nameNode = el("span", "pv-lora-name", baseName(name));
        nameNode.title = name;
        row.append(nameNode);
        row.append(el("span", "pv-lora-strength",
          Number.isFinite(strength) ? strength.toFixed(2) : "1.00"));
        loraBox.append(row);
      }
    }
  }

  async function showPrompt(path) {
    const token = ++promptToken;
    try {
      const response = await api.fetchApi(`/prompt_vault/prompt?path=${encodeURIComponent(path)}`);
      const data = await response.json();
      if (token !== promptToken) return;
      if (!response.ok) {
        positiveBox.textContent = data.error || "读取提示词失败";
        positiveBox.classList.add("is-empty");
        negativeBox.textContent = "—";
        negativeBox.classList.add("is-empty");
        loraBox.innerHTML = "";
        loraBox.append(el("div", null, data.error || "读取失败"));
        loraBox.classList.add("is-empty");
        return;
      }
      showInfo(data);
    } catch (error) {
      if (token === promptToken) {
        positiveBox.textContent = String(error);
        positiveBox.classList.add("is-empty");
      }
    }
  }

  function selectItem(item) {
    panel.selectedPath = item.path;
    previewImage.src = imageUrl(`/prompt_vault/file?path=${encodeURIComponent(item.path)}`);
    refreshSelection();
    refreshFooter();
    void showPrompt(item.path);
  }

  function makeCard(item) {
    const card = el("div", "pv-card");
    card.dataset.path = item.path;
    card.title = item.rel || item.name;
    const image = el("img");
    image.loading = "lazy";
    image.decoding = "async";
    image.src = imageUrl(`/prompt_vault/thumb?path=${encodeURIComponent(item.path)}&v=${item.mtime}&s=1024`);
    image.addEventListener("error", () => card.classList.add("is-broken"));
    card.append(image);

    const meta = el("div", "pv-card-meta");
    const dimensions = item.width && item.height ? `${item.width} × ${item.height}` : "";
    const top = el("div");
    top.append(document.createTextNode(dimensions || "—"));
    if (item.has_prompt) top.append(el("span", "pv-tag", "TXT"));
    meta.append(top);
    meta.append(el("div", "pv-card-name", item.name || baseName(item.path)));
    const bottom = [formatSize(item.size), formatDate(item.mtime)].filter(Boolean).join("  ·  ");
    if (bottom) meta.append(el("div", null, bottom));
    card.append(meta);

    card.addEventListener("click", event => {
      if (event.shiftKey && state.lastPath) {
        selectRange(state.lastPath, item.path);
        selectItem(item);
        return;
      }

      if (event.ctrlKey || event.metaKey) {
        if (state.selected.has(item.path)) state.selected.delete(item.path);
        else state.selected.add(item.path);
        state.lastPath = item.path;
        refreshSelection();
        return;
      }

      state.selected.clear();
      state.selected.add(item.path);
      state.lastPath = item.path;
      selectItem(item);
    });
    card.addEventListener("dblclick", () => {
      selectItem(item);
      applySelection();
    });
    return card;
  }

  function toggleExpanded(key) {
    if (panel.expanded.has(key)) panel.expanded.delete(key);
    else panel.expanded.add(key);
    renderForest(panel.sources);
  }

  function isActive(sourceId, folder) {
    return state.source === sourceId && state.folder === (folder || "");
  }

  function renderFolders(source, nodes, depth) {
    for (const node of nodes) {
      const key = `${source.id}:${node.path}`;
      const hasChildren = (node.children || []).length > 0;
      const expanded = panel.expanded.has(key);
      const row = el("div", "pv-tree-item");
      row.style.paddingLeft = `${8 + depth * 13}px`;
      if (isActive(source.id, node.path)) row.classList.add("is-active");
      const arrow = el("span", "pv-tree-arrow", hasChildren ? (expanded ? "▾" : "▸") : "");
      row.append(arrow);
      row.append(el("span", "pv-tree-name", node.name));
      row.append(el("span", "pv-tree-count", String(node.count ?? 0)));
      const addItem = el("span", "pv-tree-add-item", "＋");
      addItem.title = "导入图片到这个文件夹";
      addItem.addEventListener("click", event => {
        event.stopPropagation();
        importTo(joinPath(source.path, node.path));
      });
      row.append(addItem);
      row.addEventListener("click", event => {
        if (event.target === arrow && hasChildren) {
          toggleExpanded(key);
          return;
        }
        state.source = source.id;
        state.folder = node.path;
        if (hasChildren && !panel.expanded.has(key)) panel.expanded.add(key);
        renderForest(panel.sources);
        void loadItems(true);
      });
      row.dataset.dropTarget = joinPath(source.path, node.path);
      tree.append(row);
      if (hasChildren && expanded) renderFolders(source, node.children, depth + 1);
    }
  }

  function renderForest(sources) {
    tree.innerHTML = "";
    tree.append(treeHead);
    if (!sources.length) {
      tree.append(el("div", "pv-tree-empty", "还没有图库"));
      return;
    }
    for (const source of sources) {
      const key = `src:${source.id}`;
      const hasChildren = (source.folders || []).length > 0;
      const expanded = panel.expanded.has(key);
      const row = el("div", "pv-tree-item");
      row.style.paddingLeft = "6px";
      if (isActive(source.id, "")) row.classList.add("is-active");
      const arrow = el("span", "pv-tree-arrow", hasChildren ? (expanded ? "▾" : "▸") : "");
      row.append(arrow);
      row.append(el("span", "pv-tree-name", source.name));
      row.append(el("span", "pv-tree-count", String(source.total ?? 0)));
      if (source.removable) {
        const remove = el("span", "pv-tree-del", "−");
        remove.title = "移除这个图库";
        remove.addEventListener("click", event => {
          event.stopPropagation();
          void removeSource(source);
        });
        row.append(remove);
      }
      const addItem = el("span", "pv-tree-add-item", "＋");
      addItem.title = "导入图片到这个图库";
      addItem.addEventListener("click", event => {
        event.stopPropagation();
        importTo(source.path);
      });
      row.append(addItem);
      row.addEventListener("click", event => {
        if (event.target === arrow && hasChildren) {
          toggleExpanded(key);
          return;
        }
        state.source = source.id;
        state.folder = "";
        if (hasChildren && !panel.expanded.has(key)) panel.expanded.add(key);
        renderForest(panel.sources);
        void loadItems(true);
      });
      row.dataset.dropTarget = source.path;
      tree.append(row);
      if (hasChildren && expanded) renderFolders(source, source.folders, 1);
    }
  }

  async function loadForest() {
    try {
      const response = await api.fetchApi("/prompt_vault/forest");
      const data = await response.json();
      if (!response.ok) {
        panel.sources = [];
        renderForest([]);
        return;
      }
      panel.sources = data.sources || [];
      if (!panel.sources.some(source => source.id === state.source)) {
        state.source = panel.sources[0]?.id || "output";
        state.folder = "";
      }
      renderForest(panel.sources);
    } catch (error) {
      panel.sources = [];
      renderForest([]);
    }
  }

  async function removeSource(source) {
    if (!source.removable) return;
    if (!window.confirm(`从图库列表移除「${source.name}」？（不会删除文件夹里的图片）`)) return;
    try {
      const response = await api.fetchApi(`/prompt_vault/source_remove?id=${encodeURIComponent(source.id)}`);
      const data = await response.json();
      if (!response.ok) {
        alert(data.error || "移除失败");
        return;
      }
      if (state.source === source.id) {
        state.source = "output";
        state.folder = "";
      }
      await loadForest();
      await loadItems(true);
    } catch (error) {
      alert(`移除失败：${error}`);
    }
  }

  async function loadItems(reset) {
    if (state.busy) return;
    state.busy = true;
    try {
      if (reset) {
        state.offset = 0;
        masonry.innerHTML = "";
        masonry.scrollTop = 0;
        panel.items = [];
        state.selected.clear();
        state.lastPath = "";
        refreshSelection();
      }
      const url = `/prompt_vault/items?source=${encodeURIComponent(state.source)}`
        + `&folder=${encodeURIComponent(state.folder)}`
        + `&q=${encodeURIComponent(state.query)}&offset=${state.offset}&limit=${PAGE_SIZE}`
        + `&sort=${encodeURIComponent(state.sort)}&order=${encodeURIComponent(state.order)}`;
      const response = await api.fetchApi(url);
      const data = await response.json();
      if (!response.ok) {
        masonry.innerHTML = "";
        masonry.append(el("div", "pv-empty", data.error || "图库加载失败"));
        countLabel.textContent = "0 / 0";
        return;
      }
      const items = data.items || [];
      state.total = Number(data.total) || 0;
      state.offset += items.length;
      if (reset && !items.length) {
        masonry.innerHTML = "";
        masonry.append(el("div", "pv-empty", "这个文件夹还没有图片。"));
      }
      for (const item of items) {
        panel.items.push(item);
        masonry.append(makeCard(item));
      }
      countLabel.textContent = `${state.offset} / ${state.total}`;
      refreshSelection();
      // 内容不足一屏时自动补下一页，保证能继续滚动
      if (items.length && state.offset < state.total && masonry.scrollHeight <= masonry.clientHeight + 20) {
        setTimeout(() => void loadItems(false), 0);
      }
    } catch (error) {
      masonry.innerHTML = "";
      masonry.append(el("div", "pv-empty", `加载失败：${error}`));
    } finally {
      state.busy = false;
    }
  }

  function importTo(folderPath) {
    const source = currentSource();
    state.importTarget = folderPath || (source ? source.path : "");
    fileInput.click();
  }

  async function handleFiles(files) {
    if (!files.length) return;
    const target = state.importTarget || (currentSource() ? currentSource().path : "");
    for (const file of files) {
      const form = new FormData();
      form.append("image", file);
      form.append("type", "input");
      form.append("subfolder", "prompt_vault");
      const response = await api.fetchApi("/upload/image", { method: "POST", body: form });
      if (!response.ok) {
        alert(`导入 ${file.name} 失败`);
        continue;
      }
      const data = await response.json();
      if (target && data.name) {
        const moved = await api.fetchApi(
          `/prompt_vault/import?name=${encodeURIComponent(data.name)}&dest=${encodeURIComponent(target)}`
        );
        if (!moved.ok) {
          const payload = await moved.json().catch(() => ({}));
          alert(payload.error || `导入 ${file.name} 到目标文件夹失败`);
        }
      }
    }
    await loadForest();
    await loadItems(true);
  }

  function fallbackDropTarget() {
    const source = currentSource();
    if (!source) return "";
    return state.folder ? joinPath(source.path, state.folder) : source.path;
  }

  function applySelection() {
    if (!CURRENT || !panel.selectedPath) return;
    const { node, pathWidget } = CURRENT;
    pathWidget.value = panel.selectedPath;
    try {
      pathWidget.callback?.(panel.selectedPath);
    } catch (error) {
      /* 回调异常不影响选择 */
    }
    node.__pvUpdatePreview?.(panel.selectedPath);
    node.setDirtyCanvas(true, true);
    closePanel();
  }

  function closePanel() {
    mask.style.display = "none";
    CURRENT = null;
  }

  panel.loadForest = loadForest;
  panel.loadItems = loadItems;

  closeButton.addEventListener("click", closePanel);
  fullscreenButton.addEventListener("click", () => {
    const full = dialog.classList.toggle("is-full");
    fullscreenButton.title = full ? "退出全屏" : "网页全屏";
    fullscreenButton.textContent = full ? "⤡" : "⛶";
  });
  mask.addEventListener("mousedown", event => {
    if (event.target === mask) closePanel();
  });
  document.addEventListener("keydown", event => {
    if (event.key === "Escape" && mask.style.display === "flex") closePanel();
  });
  confirmButton.addEventListener("click", applySelection);

  let dropRow = null;
  function clearDropHighlight() {
    if (dropRow) dropRow.classList.remove("is-drop");
    dropRow = null;
  }

  function onPanelDragOver(event) {
    event.preventDefault();
    event.stopPropagation();
    const row = event.target?.closest?.(".pv-tree-item") || null;
    if (row !== dropRow) {
      if (dropRow) dropRow.classList.remove("is-drop");
      dropRow = row;
      if (dropRow) dropRow.classList.add("is-drop");
    }
    if (event.dataTransfer) event.dataTransfer.dropEffect = "copy";
  }

  async function filesFromEntries(entries) {
    const files = [];
    const walk = async entry => {
      if (entry.isFile) {
        const file = await new Promise(resolve => entry.file(resolve, () => resolve(null)));
        if (file) files.push(file);
        return;
      }
      if (entry.isDirectory) {
        const reader = entry.createReader();
        while (true) {
          const batch = await new Promise(resolve => reader.readEntries(resolve, () => resolve([])));
          if (!batch.length) break;
          for (const child of batch) await walk(child);
        }
      }
    };
    for (const entry of entries) await walk(entry);
    return files;
  }

  function onPanelDrop(event) {
    event.preventDefault();
    event.stopPropagation();

    const row = event.target?.closest?.(".pv-tree-item") || null;
    const target = row?.dataset?.dropTarget || fallbackDropTarget();
    clearDropHighlight();

    const transfer = event.dataTransfer;
    const entries = [];
    for (const item of [...(transfer?.items || [])]) {
      const entry = item.webkitGetAsEntry?.();
      if (entry) entries.push(entry);
    }

    const collect = async () => {
      // 拖入单个文件夹：浏览器拿不到绝对路径，弹系统选择框按「引用」注册
      const directories = entries.filter(entry => entry.isDirectory);
      if (directories.length === 1 && entries.length === 1) {
        const folder = (window.prompt(
          `浏览器无法读取拖入文件夹「${directories[0].name}」的完整路径。请粘贴该文件夹的绝对路径（仅引用，不复制）：`,
          ""
        ) || "").trim();
        if (folder) await addSource(folder);
        return;
      }

      const files = entries.length
        ? await filesFromEntries(entries)
        : [...(transfer?.files || [])];
      const images = files.filter(isImageFile);
      if (!images.length || !target) return;
      state.importTarget = target;
      void handleFiles(images);
    };
    void collect();
  }

  function onPanelDragLeave(event) {
    if (!mask.contains(event.relatedTarget)) clearDropHighlight();
  }

  mask.addEventListener("dragover", onPanelDragOver, true);
  mask.addEventListener("drop", onPanelDrop, true);
  mask.addEventListener("dragleave", onPanelDragLeave, true);

  viewButton.addEventListener("click", () => {
    state.view = state.view === "grid" ? "masonry" : "grid";
    applyView();
    savePrefs();
  });

  sortSelect.addEventListener("change", () => {
    state.sort = sortSelect.value;
    savePrefs();
    void loadItems(true);
  });

  orderButton.addEventListener("click", () => {
    state.order = state.order === "asc" ? "desc" : "asc";
    applyView();
    savePrefs();
    void loadItems(true);
  });

  searchInput.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      state.query = searchInput.value.trim();
      void loadItems(true);
    }, 300);
  });

  masonry.addEventListener("scroll", () => {
    if (state.busy || state.offset >= state.total) return;
    if (masonry.scrollTop + masonry.clientHeight >= masonry.scrollHeight - 240) {
      void loadItems(false);
    }
  });

  refreshButton.addEventListener("click", async () => {
    refreshButton.disabled = true;
    try {
      await loadForest();
      await loadItems(true);
    } finally {
      refreshButton.disabled = false;
    }
  });

  refreshTreeButton.addEventListener("click", async () => {
    refreshTreeButton.disabled = true;
    try {
      await loadForest();
    } finally {
      refreshTreeButton.disabled = false;
    }
  });

  async function addSource(folder) {
    try {
      const response = await api.fetchApi(`/prompt_vault/source_add?path=${encodeURIComponent(folder)}`);
      const data = await response.json();
      if (!response.ok) {
        alert(data.error || "添加图库失败");
        return;
      }
      state.source = data.source?.id || state.source;
      state.folder = "";
      panel.expanded = new Set([`src:${state.source}`]);
      await loadForest();
      await loadItems(true);
    } catch (error) {
      alert(`添加图库失败：${error}`);
    }
  }

  addSourceButton.addEventListener("click", async () => {
    const folder = (window.prompt("请粘贴图库文件夹的绝对路径（仅引用，不复制）：", "") || "").trim();
    if (folder) await addSource(folder);
  });

  async function deleteSelected() {
    const paths = [...state.selected];
    if (!paths.length) return;
    if (!window.confirm(`删除选中的 ${paths.length} 张图片？同名 txt/json 会一起删除，无法恢复。`)) return;

    deleteButton.disabled = true;
    let failed = 0;
    for (const path of paths) {
      try {
        const response = await api.fetchApi(`/prompt_vault/delete?path=${encodeURIComponent(path)}`);
        if (!response.ok) failed += 1;
      } catch (error) {
        failed += 1;
      }
    }

    if (paths.includes(panel.selectedPath)) {
      panel.selectedPath = "";
      previewImage.removeAttribute("src");
      refreshFooter();
    }
    state.selected.clear();
    state.lastIndex = -1;
    if (failed) alert(`有 ${failed} 张删除失败`);
    await loadForest();
    await loadItems(true);
  }

  deleteButton.addEventListener("click", () => void deleteSelected());

  fileInput.addEventListener("change", async () => {
    const files = [...(fileInput.files || [])];
    fileInput.value = "";
    if (!files.length) return;
    await handleFiles(files);
  });

  PANEL = panel;
  return panel;
}

function openPanel(node, pathWidget) {
  const panel = ensurePanel();
  CURRENT = { node, pathWidget };
  panel.selectedPath = String(pathWidget.value || "");
  panel.mask.style.display = "flex";
  panel.state.query = "";
  panel.state.folder = "";
  panel.state.offset = 0;
  panel.state.importTarget = "";
  const search = panel.mask.querySelector(".pv-search");
  if (search) search.value = "";
  refreshPreview(panel);
  panel.expanded.add(`src:${panel.state.source}`);
  void panel.loadForest().then(() => panel.loadItems(true));
}

function refreshPreview(panel) {
  const preview = panel.mask.querySelector(".pv-preview img");
  if (!preview) return;
  preview.removeAttribute("src");
  if (panel.selectedPath) {
    preview.src = imageUrl(`/prompt_vault/file?path=${encodeURIComponent(panel.selectedPath)}`);
  }
}

app.registerExtension({
  name: "liyue.tools.comfy",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== NODE_NAME) return;
    const created = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      created?.apply(this, arguments);
      if (this.__pvPanel) return;
      this.__pvPanel = true;
      try {
        installNode(this);
      } catch (error) {
        console.error("[liyue-prompt-comfy] 节点初始化失败", error);
      }
    };
    const configured = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function () {
      configured?.apply(this, arguments);
      setTimeout(() => {
        this.setDirtyCanvas(true, true);
        this.__pvUpdatePreview?.(this.__pvPathWidget?.value);
      }, 60);
    };
  },
});
