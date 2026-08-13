"""把某块硬盘的索引导出为单个离线 HTML 文件（自带搜索/排序/筛选）。"""

from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from . import db


def _fmt_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    units = ["KB", "MB", "GB", "TB", "PB"]
    value = float(size)
    for unit in units:
        value /= 1024.0
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}"
    return f"{size} B"


def _fmt_time(ts: Optional[int]) -> str:
    if not ts:
        return "-"
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "-"


def _html_escape(text: str) -> str:
    return html.escape(str(text), quote=True)


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
* {{ box-sizing: border-box; }}
body {{ font-family: "Microsoft YaHei", "Segoe UI", Arial, sans-serif; margin: 0; background: #f5f6f8; color: #222; }}
.wrap {{ max-width: 1200px; margin: 0 auto; padding: 16px; }}
h1 {{ font-size: 20px; margin: 0 0 4px; }}
.meta {{ color: #666; font-size: 13px; margin-bottom: 14px; }}
.card {{ background: #fff; border: 1px solid #e2e4e8; border-radius: 8px; padding: 12px; margin-bottom: 14px; }}
.filters {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }}
input, select {{ padding: 6px 8px; border: 1px solid #c9cdd4; border-radius: 5px; font-size: 13px; }}
input[type=text] {{ min-width: 140px; }}
.btn {{ padding: 6px 14px; border: 1px solid #2f6fed; background: #2f6fed; color: #fff; border-radius: 5px; cursor: pointer; font-size: 13px; }}
.btn:hover {{ background: #255ed6; }}
table {{ width: 100%; border-collapse: collapse; background: #fff; font-size: 13px; }}
th, td {{ padding: 7px 10px; border-bottom: 1px solid #edf0f3; text-align: left; white-space: nowrap; }}
th {{ position: sticky; top: 0; background: #f0f3f7; cursor: pointer; user-select: none; }}
th:hover {{ background: #e5eaf1; }}
tr:hover td {{ background: #f8faff; }}
.dir td:first-child {{ color: #1756c4; font-weight: 600; }}
.size {{ text-align: right; }}
.mtime {{ color: #555; }}
.path {{ color: #888; font-size: 12px; }}
.pager {{ display: flex; justify-content: space-between; align-items: center; margin-top: 10px; font-size: 13px; color: #555; }}
.pager button {{ padding: 5px 12px; }}
.empty {{ padding: 30px; text-align: center; color: #999; }}
.hint {{ color: #999; font-size: 12px; margin-top: 8px; }}
.cap {{ display: flex; align-items: center; gap: 12px; margin: 8px 0; flex-wrap: wrap; }}
.cap-bar {{ flex: 1; min-width: 220px; max-width: 420px; height: 14px; background: #e8ebef; border-radius: 7px; overflow: hidden; }}
.cap-used {{ height: 100%; background: linear-gradient(90deg, #2f6fed, #63a1ff); border-radius: 7px; }}
.cap span {{ font-size: 13px; color: #333; white-space: nowrap; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>{title}</h1>
  <div class="meta">{meta}</div>
  <div class="card filters">
    <input type="text" id="q" placeholder="搜索文件名 / 路径" oninput="onFilter()">
    <input type="text" id="ext" placeholder="类型，如 mp4" oninput="onFilter()" style="width:90px">
    <input type="text" id="sizeMin" placeholder="最小大小 KB" oninput="onFilter()" style="width:110px">
    <input type="text" id="sizeMax" placeholder="最大大小 KB" oninput="onFilter()" style="width:110px">
    <input type="date" id="dateFrom" onchange="onFilter()">
    <span style="color:#999">至</span>
    <input type="date" id="dateTo" onchange="onFilter()">
    <input type="text" id="folder" placeholder="路径前缀，如 照片/2024" oninput="onFilter()">
    <select id="sort" onchange="onFilter()">
      <option value="path">按路径</option>
      <option value="name">按名称</option>
      <option value="size">按大小</option>
      <option value="mtime">按修改时间</option>
      <option value="ext">按类型</option>
    </select>
    <button class="btn" onclick="toggleDir()" id="dirBtn">只看文件</button>
    <button class="btn" onclick="reset()">重置</button>
  </div>
  <div class="card" style="padding:0; overflow:auto; max-height:70vh;">
    <table>
      <thead>
        <tr>
          <th data-col="name" onclick="setSort('name')">名称</th>
          <th data-col="size" onclick="setSort('size')">大小</th>
          <th data-col="mtime" onclick="setSort('mtime')">修改时间</th>
          <th data-col="ext" onclick="setSort('ext')">类型</th>
          <th data-col="path" onclick="setSort('path')">完整路径</th>
        </tr>
      </thead>
      <tbody id="tbody"></tbody>
    </table>
    <div id="empty" class="empty" style="display:none">没有符合条件的文件</div>
  </div>
  <div class="pager">
    <span id="info"></span>
    <span>
      <button class="btn" onclick="page(-1)">上一页</button>
      <span id="pageInfo"></span>
      <button class="btn" onclick="page(1)">下一页</button>
    </span>
  </div>
  <div class="hint">此报告由硬盘目录助手离线生成，数据仅保存在本文件内，可复制到任何设备使用。</div>
</div>
<script>
const DATA = {data};
const PAGE_SIZE = 200;
let state = {{ q: "", ext: "", sizeMin: "", sizeMax: "", dateFrom: "", dateTo: "", folder: "", sort: "path", dirs: true, page: 0 }};
let filtered = [];

function sizeKB(v) {{
  const n = parseFloat(v);
  return isNaN(n) ? null : n * 1024;
}}

function apply() {{
  const s = state;
  filtered = DATA.filter(r => {{
    const [path, name, parent, isDir, size, mtime, ext] = r;
    if (!s.dirs && isDir) return false;
    if (s.q) {{
      const q = s.q.toLowerCase();
      if (name.toLowerCase().indexOf(q) < 0 && path.toLowerCase().indexOf(q) < 0) return false;
    }}
    if (s.ext && (ext || "").toLowerCase() !== s.ext.trim().toLowerCase()) return false;
    const min = sizeKB(s.sizeMin), max = sizeKB(s.sizeMax);
    if (min !== null && size < min) return false;
    if (max !== null && size > max) return false;
    if (s.dateFrom) {{
      const t = new Date(mtime * 1000);
      const d = t.getFullYear() + "-" + String(t.getMonth()+1).padStart(2,"0") + "-" + String(t.getDate()).padStart(2,"0");
      if (d < s.dateFrom) return false;
    }}
    if (s.dateTo) {{
      const t = new Date(mtime * 1000);
      const d = t.getFullYear() + "-" + String(t.getMonth()+1).padStart(2,"0") + "-" + String(t.getDate()).padStart(2,"0");
      if (d > s.dateTo) return false;
    }}
    if (s.folder && parent.indexOf(s.folder.trim()) !== 0) return false;
    return true;
  }});
  sortData();
  if (state.page >= Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))) state.page = 0;
  render();
}}

function sortData() {{
  const col = state.sort;
  const dirs = col === "path" || col === "name";
  filtered.sort((a, b) => {{
    if (dirs && a[3] !== b[3]) return a[3] ? -1 : 1;
    let av, bv;
    if (col === "size") {{ av = a[4]; bv = b[4]; }}
    else if (col === "mtime") {{ av = a[5]; bv = b[5]; }}
    else if (col === "ext") {{ av = a[6] || ""; bv = b[6] || ""; }}
    else if (col === "name") {{ av = a[1]; bv = b[1]; }}
    else {{ av = a[0]; bv = b[0]; }}
    if (av < bv) return -1;
    if (av > bv) return 1;
    return a[0] < b[0] ? -1 : 1;
  }});
}}

function fmtSize(n) {{
  if (n < 1024) return n + " B";
  const units = ["KB","MB","GB","TB"];
  let v = n;
  for (const u of units) {{
    v /= 1024;
    if (v < 1024 || u === "TB") return v.toFixed(1) + " " + u;
  }}
}}

function fmtTime(ts) {{
  if (!ts) return "-";
  const d = new Date(ts * 1000);
  const p = x => String(x).padStart(2, "0");
  return d.getFullYear() + "-" + p(d.getMonth()+1) + "-" + p(d.getDate()) + " " + p(d.getHours()) + ":" + p(d.getMinutes());
}}

function render() {{
  const tb = document.getElementById("tbody");
  tb.innerHTML = "";
  const start = state.page * PAGE_SIZE;
  const rows = filtered.slice(start, start + PAGE_SIZE);
  document.getElementById("empty").style.display = filtered.length ? "none" : "block";
  for (const r of rows) {{
    const [path, name, parent, isDir, size, mtime, ext] = r;
    const tr = document.createElement("tr");
    if (isDir) tr.className = "dir";
    const tdName = document.createElement("td");
    tdName.textContent = (isDir ? "📁 " : "") + name;
    const tdSize = document.createElement("td");
    tdSize.className = "size";
    tdSize.textContent = isDir ? "-" : fmtSize(size);
    const tdTime = document.createElement("td");
    tdTime.className = "mtime";
    tdTime.textContent = fmtTime(mtime);
    const tdExt = document.createElement("td");
    tdExt.textContent = isDir ? "目录" : (ext || "-");
    const tdPath = document.createElement("td");
    tdPath.className = "path";
    tdPath.textContent = path;
    tr.append(tdName, tdSize, tdTime, tdExt, tdPath);
    tb.appendChild(tr);
  }}
  const total = filtered.length;
  document.getElementById("info").textContent = "共 " + total + " 条";
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  document.getElementById("pageInfo").textContent = (state.page + 1) + " / " + pages;
}}

function onFilter() {{
  state.q = document.getElementById("q").value;
  state.ext = document.getElementById("ext").value;
  state.sizeMin = document.getElementById("sizeMin").value;
  state.sizeMax = document.getElementById("sizeMax").value;
  state.dateFrom = document.getElementById("dateFrom").value;
  state.dateTo = document.getElementById("dateTo").value;
  state.folder = document.getElementById("folder").value;
  state.sort = document.getElementById("sort").value;
  state.page = 0;
  apply();
}}

function setSort(col) {{
  document.getElementById("sort").value = col;
  state.sort = col;
  state.page = 0;
  apply();
}}

function toggleDir() {{
  state.dirs = !state.dirs;
  document.getElementById("dirBtn").textContent = state.dirs ? "只看文件" : "显示目录";
  state.page = 0;
  apply();
}}

function reset() {{
  for (const id of ["q","ext","sizeMin","sizeMax","dateFrom","dateTo","folder"]) document.getElementById(id).value = "";
  document.getElementById("sort").value = "path";
  state = {{ q:"", ext:"", sizeMin:"", sizeMax:"", dateFrom:"", dateTo:"", folder:"", sort:"path", dirs:true, page:0 }};
  document.getElementById("dirBtn").textContent = "只看文件";
  apply();
}}

function page(d) {{
  const pages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  state.page = Math.min(pages - 1, Math.max(0, state.page + d));
  render();
}}

apply();
</script>
</body>
</html>
"""


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
* {{ box-sizing: border-box; }}
body {{ font-family: "Microsoft YaHei", "Segoe UI", Arial, sans-serif; margin: 0; background: #f5f6f8; color: #222; }}
.wrap {{ max-width: 1400px; margin: 0 auto; padding: 16px; }}
h1 {{ font-size: 20px; margin: 0 0 4px; }}
.meta {{ color: #666; font-size: 13px; margin-bottom: 14px; }}
.card {{ background: #fff; border: 1px solid #e2e4e8; border-radius: 8px; padding: 12px; margin-bottom: 14px; }}
.filters {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }}
input, select {{ padding: 6px 8px; border: 1px solid #c9cdd4; border-radius: 5px; font-size: 13px; }}
input[type=text] {{ min-width: 120px; }}
.btn {{ padding: 6px 14px; border: 1px solid #2f6fed; background: #2f6fed; color: #fff; border-radius: 5px; cursor: pointer; font-size: 13px; }}
.btn:hover {{ background: #255ed6; }}
.layout {{ display: flex; gap: 12px; align-items: flex-start; }}
.layout {{ overflow: visible; }}
.tree-panel {{ width: 300px; min-width: 240px; max-height: 74vh; overflow: auto; background: #fff; border: 1px solid #e2e4e8; border-radius: 8px; padding: 8px; }}
.tree-panel h3 {{ margin: 4px 6px 8px; font-size: 14px; color: #333; }}
#tree ul {{ list-style: none; margin: 0; padding: 0; }}
#tree li {{ margin: 0; }}
.tree-item {{ display: flex; align-items: center; gap: 3px; padding: 3px 6px; border-radius: 5px; cursor: pointer; white-space: nowrap; font-size: 13px; }}
.tree-item:hover {{ background: #eef3fc; }}
.tree-item.active {{ background: #dbe7fd; color: #0f3f9c; font-weight: 600; }}
.twist {{ display: inline-block; width: 14px; color: #888; }}
.splitter {{ width: 7px; cursor: col-resize; background: #e2e4e8; border-radius: 4px; align-self: stretch; flex: 0 0 auto; }}
.splitter:hover {{ background: #9abaf5; }}
.table-panel {{ flex: 1; min-width: 0; }}
.panel-frame {{ position: relative; display: flex; height: 62vh; }}
.panel-frame .card {{ flex: 1; overflow: auto; max-height: none; }}
.resize-east {{ position: absolute; top: 0; right: -5px; width: 10px; height: 100%; cursor: ew-resize; z-index: 6; background: transparent; }}
.resize-east:hover {{ background: #9abaf5; }}
.resize-south {{ position: absolute; left: 0; bottom: -5px; width: 100%; height: 10px; cursor: ns-resize; z-index: 6; background: transparent; }}
.resize-south:hover {{ background: #9abaf5; }}
.resize-se {{ position: absolute; right: -5px; bottom: -5px; width: 18px; height: 18px; cursor: nwse-resize; z-index: 7; background: linear-gradient(135deg, transparent 50%, #9aa5b1 50%); border-bottom-right-radius: 8px; }}
.resize-se:hover {{ background: linear-gradient(135deg, transparent 50%, #2f6fed 50%); }}
#crumbs {{ padding: 6px 8px; font-size: 13px; color: #2f6fed; }}
#crumbs span.crumb {{ cursor: pointer; }}
#crumbs span.crumb:hover {{ text-decoration: underline; }}
#crumbs span.sep {{ color: #aaa; margin: 0 4px; }}
table {{ width: 100%; border-collapse: collapse; background: #fff; font-size: 13px; }}
th, td {{ padding: 7px 10px; border-bottom: 1px solid #edf0f3; text-align: left; white-space: nowrap; }}
th {{ position: sticky; top: 0; background: #f0f3f7; cursor: pointer; user-select: none; }}
th:hover {{ background: #e5eaf1; }}
th {{ position: relative; }}
.resizer {{ position: absolute; right: -2px; top: 0; width: 7px; height: 100%; cursor: col-resize; z-index: 2; background: #d7dce3; }}
.resizer:hover {{ background: #2f6fed; }}
body.resizing {{ user-select: none; cursor: col-resize; }}
tr:hover td {{ background: #f8faff; }}
tr.dir-row {{ cursor: pointer; }}
tr.dir-row td:first-child {{ color: #1756c4; font-weight: 600; }}
.name-wrap {{ display: inline-flex; align-items: center; gap: 8px; }}
.name-block {{ min-width: 0; }}
.file-icon {{ position: relative; display: inline-flex; width: 34px; height: 34px; align-items: center; justify-content: center; border-radius: 7px; font-size: 17px; flex: 0 0 auto; }}
.file-icon .ext-badge {{ position: absolute; right: -4px; bottom: -4px; background: #333; color: #fff; font-size: 9px; font-weight: 600; padding: 1px 4px; border-radius: 4px; line-height: 1.1; max-width: 44px; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }}
.sub {{ color: #777; font-size: 11px; margin-top: 2px; white-space: nowrap; }}
.type-dir {{ background: #fff2d9; }}
.type-video {{ background: #ffe2e2; }}
.type-audio {{ background: #e6e1ff; }}
.type-image {{ background: #dff2e8; }}
.type-text {{ background: #e7edf5; }}
.type-doc {{ background: #e8f0fe; }}
.type-archive {{ background: #fdeadd; }}
.type-code {{ background: #e9f2e4; }}
.type-exe {{ background: #ffe8d6; }}
.type-other {{ background: #f0f1f3; }}
#tableView.mode-list .col-size,
#tableView.mode-list .col-mtime,
#tableView.mode-list .col-ext,
#tableView.mode-list .col-path {{ display: none; }}
.grid-view {{ display: none; gap: 12px; padding: 12px; }}
.grid-view.show {{ display: grid; }}
.view-small {{ grid-template-columns: repeat(auto-fill, minmax(76px, 1fr)); }}
.view-medium {{ grid-template-columns: repeat(auto-fill, minmax(104px, 1fr)); }}
.view-large {{ grid-template-columns: repeat(auto-fill, minmax(132px, 1fr)); }}
.view-tiles {{ grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); }}
.grid-item {{ background: #fff; border: 1px solid #edf0f3; border-radius: 8px; padding: 10px; cursor: pointer; text-align: center; overflow: hidden; }}
.grid-item:hover {{ background: #f3f7ff; border-color: #bcd3f7; }}
.grid-item .gi-icon {{ position: relative; display: inline-flex; width: 48px; height: 48px; align-items: center; justify-content: center; border-radius: 9px; font-size: 26px; }}
.grid-item .gi-name {{ margin-top: 6px; font-size: 12px; word-break: break-all; line-height: 1.3; }}
.grid-item .gi-meta {{ margin-top: 3px; font-size: 11px; color: #888; }}
.view-small .grid-item .gi-icon {{ width: 34px; height: 34px; font-size: 18px; }}
.view-medium .grid-item .gi-icon {{ width: 44px; height: 44px; font-size: 24px; }}
.view-large .grid-item .gi-icon {{ width: 60px; height: 60px; font-size: 34px; }}
.view-tiles {{ align-items: stretch; }}
.view-tiles .grid-item {{ display: flex; gap: 12px; align-items: center; text-align: left; }}
.view-tiles .grid-item .gi-icon {{ flex: 0 0 auto; width: 48px; height: 48px; font-size: 26px; }}
.view-tiles .grid-item .gi-name {{ margin-top: 0; font-size: 13px; }}
.view-tiles .grid-item .gi-meta {{ margin-top: 4px; }}
.cap {{ display: flex; align-items: center; gap: 12px; margin: 8px 0; flex-wrap: wrap; }}
.cap-bar {{ flex: 1; min-width: 220px; max-width: 420px; height: 14px; background: #e8ebef; border-radius: 7px; overflow: hidden; }}
.cap-used {{ height: 100%; background: linear-gradient(90deg, #2f6fed, #63a1ff); border-radius: 7px; }}
.cap span {{ font-size: 13px; color: #333; white-space: nowrap; }}
table {{ table-layout: fixed; }}
th, td {{ overflow: visible; text-overflow: clip; white-space: normal; word-break: break-all; }}
th {{ white-space: nowrap; }}
th.col-name, td.col-name {{ width: 38%; min-width: 160px; }}
th.col-size, td.col-size {{ width: 90px; }}
th.col-mtime, td.col-mtime {{ width: 140px; }}
th.col-ext, td.col-ext {{ width: 80px; }}
th.col-path, td.col-path {{ width: 28%; }}
.name-wrap {{ max-width: 100%; }}
.name-block {{ overflow: visible; }}
.name-block > span {{ display: block; white-space: normal; word-break: break-all; }}
.sub {{ max-width: 100%; white-space: normal; word-break: break-all; }}
.size {{ text-align: right; }}
.mtime {{ color: #555; }}
.path {{ color: #888; font-size: 12px; }}
.pager {{ display: flex; justify-content: space-between; align-items: center; margin-top: 10px; font-size: 13px; color: #555; }}
.pager button {{ padding: 5px 12px; }}
.empty {{ padding: 30px; text-align: center; color: #999; }}
.hint {{ color: #999; font-size: 12px; margin-top: 8px; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>{title}</h1>
  <div class="meta">{meta}</div>
  <div class="card filters">
    <input type="text" id="q" placeholder="搜索文件名 / 路径" oninput="onFilter()">
    <input type="text" id="ext" placeholder="类型，如 mp4" oninput="onFilter()" style="width:90px">
    <input type="text" id="sizeMin" placeholder="最小大小 KB" oninput="onFilter()" style="width:110px">
    <input type="text" id="sizeMax" placeholder="最大大小 KB" oninput="onFilter()" style="width:110px">
    <input type="date" id="dateFrom" onchange="onFilter()">
    <span style="color:#999">至</span>
    <input type="date" id="dateTo" onchange="onFilter()">
    <select id="view" onchange="onViewChange()">
      <option value="details">详细信息</option>
      <option value="list">列表</option>
      <option value="content">内容</option>
      <option value="tiles">平铺</option>
      <option value="small">小图标</option>
      <option value="medium">中图标</option>
      <option value="large">大图标</option>
    </select>
    <select id="sort" onchange="onFilter()">
      <option value="name">按名称</option>
      <option value="size">按大小</option>
      <option value="mtime">按修改时间</option>
      <option value="ext">按类型</option>
    </select>
    <button class="btn" onclick="toggleDirOnly()" id="dirBtn">只看文件</button>
    <button class="btn" onclick="reset()">回到根目录</button>
  </div>
  <div class="layout">
    <div class="tree-panel">
      <h3>目录</h3>
      <div id="tree"></div>
    </div>
    <div class="splitter" id="splitter" title="拖动调整目录宽度"></div>
    <div class="table-panel">
      <div class="panel-frame">
        <div class="card" style="padding:0; overflow:auto;">
          <div id="crumbs"></div>
          <table id="tableView">
            <thead>
              <tr>
                <th class="col-name" data-col="name" onclick="setSort('name')">名称</th>
                <th class="col-size" data-col="size" onclick="setSort('size')">大小</th>
                <th class="col-mtime" data-col="mtime" onclick="setSort('mtime')">修改时间</th>
                <th class="col-ext" data-col="ext" onclick="setSort('ext')">类型</th>
                <th class="col-path" data-col="path" onclick="setSort('path')">完整路径</th>
              </tr>
            </thead>
            <tbody id="tbody"></tbody>
          </table>
          <div id="gridView" class="grid-view"></div>
          <div id="empty" class="empty" style="display:none">这个目录是空的，或没有符合条件的文件</div>
        </div>
        <div class="resize-east" id="resizeEast" title="拖动调整文件区宽度"></div>
        <div class="resize-south" id="resizeSouth" title="拖动调整文件区高度"></div>
        <div class="resize-se" id="panelResize" title="拖动调整文件区大小"></div>
      </div>
      <div class="pager">
        <span id="info"></span>
        <span>
          <button class="btn" onclick="page(-1)">上一页</button>
          <span id="pageInfo"></span>
          <button class="btn" onclick="page(1)">下一页</button>
        </span>
      </div>
    </div>
  </div>
  <div class="hint">此报告由目录导出管家离线生成，数据仅保存在本文件内，可复制到任何设备使用。点击左侧目录或右侧文件夹可逐层浏览。<br>提示：拖动文件区右边框调整宽度、下边框调整高度、右下角同时调整；拖动中间分隔条调整左右宽度；拖动表头竖线调整列宽。</div>
</div>
<script>
const DATA = {data};
const PAGE_SIZE = 200;
const byParent = {{}};
const dirsByParent = {{}};
for (const r of DATA) {{
  const [path, name, par, isDir] = r;
  (byParent[par] = byParent[par] || []).push(r);
  if (isDir) (dirsByParent[par] = dirsByParent[par] || []).push(r);
}}
let state = {{ q: "", ext: "", sizeMin: "", sizeMax: "", dateFrom: "", dateTo: "", sort: "name", dirOnly: false, view: "details", page: 0 }};
const expanded = new Set();
let currentPath = "";
let filtered = [];

const EXT_SETS = {{
  video: new Set(["mp4","mkv","avi","mov","wmv","flv","webm","m4v","ts","mpg","mpeg","3gp","rmvb","rm"]),
  audio: new Set(["mp3","wav","flac","aac","ogg","m4a","wma","ape","opus"]),
  image: new Set(["jpg","jpeg","png","gif","bmp","webp","svg","ico","tif","tiff","heic","raw","cr2","nef","arw"]),
  text: new Set(["txt","md","log","ini","cfg","csv","tsv","json","xml","yaml","yml","toml","srt","ass","vtt","nfo"]),
  doc: new Set(["pdf","doc","docx","odt","ppt","pptx","xls","xlsx","odp","ods","rtf"]),
  archive: new Set(["zip","rar","7z","tar","gz","bz2","xz","iso","cab"]),
  code: new Set(["py","js","ts","c","cpp","h","hpp","java","html","htm","css","sh","bat","cmd","ps1","sql","php","rb","go","rs","lua","json5"]),
  exe: new Set(["exe","msi","app","apk","com"]),
}};
const TYPE_META = {{
  video: {{ emoji: "🎬", label: "视频" }},
  audio: {{ emoji: "🎵", label: "音频" }},
  image: {{ emoji: "🖼️", label: "图片" }},
  text: {{ emoji: "📄", label: "文本" }},
  doc: {{ emoji: "📑", label: "文档" }},
  archive: {{ emoji: "🗜️", label: "压缩包" }},
  code: {{ emoji: "💻", label: "代码" }},
  exe: {{ emoji: "⚙️", label: "程序" }},
  other: {{ emoji: "📄", label: "文件" }},
}};

function fileType(ext) {{
  ext = (ext || "").toLowerCase();
  for (const key of Object.keys(EXT_SETS)) {{
    if (EXT_SETS[key].has(ext)) return key;
  }}
  return "other";
}}

function parentOf(path) {{
  if (!path) return "";
  const parts = path.split("/");
  parts.pop();
  return parts.join("/");
}}

function sizeKB(v) {{
  const n = parseFloat(v);
  return isNaN(n) ? null : n * 1024;
}}

function apply() {{
  const s = state;
  let base = byParent[currentPath] || [];
  if (s.q) base = DATA;
  filtered = base.filter(r => {{
    const [path, name, par, isDir, size, mtime, ext] = r;
    if (s.dirOnly && isDir) return false;
    if (s.q) {{
      const q = s.q.toLowerCase();
      if (name.toLowerCase().indexOf(q) < 0 && path.toLowerCase().indexOf(q) < 0) return false;
    }}
    if (s.ext && (ext || "").toLowerCase() !== s.ext.trim().toLowerCase()) return false;
    const min = sizeKB(s.sizeMin), max = sizeKB(s.sizeMax);
    if (min !== null && size < min) return false;
    if (max !== null && size > max) return false;
    if (s.dateFrom) {{
      const d = new Date(mtime * 1000);
      const ds = d.getFullYear() + "-" + String(d.getMonth()+1).padStart(2,"0") + "-" + String(d.getDate()).padStart(2,"0");
      if (ds < s.dateFrom) return false;
    }}
    if (s.dateTo) {{
      const d = new Date(mtime * 1000);
      const ds = d.getFullYear() + "-" + String(d.getMonth()+1).padStart(2,"0") + "-" + String(d.getDate()).padStart(2,"0");
      if (ds > s.dateTo) return false;
    }}
    return true;
  }});
  sortData();
  const pages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  if (state.page >= pages) state.page = 0;
  renderRows();
  renderTree();
  renderCrumbs();
}}

function sortData() {{
  const col = state.sort;
  filtered.sort((a, b) => {{
    const isDirSort = col === "name" || col === "path";
    if (isDirSort && a[3] !== b[3]) return a[3] ? -1 : 1;
    let av, bv;
    if (col === "size") {{ av = a[4]; bv = b[4]; }}
    else if (col === "mtime") {{ av = a[5]; bv = b[5]; }}
    else if (col === "ext") {{ av = a[6] || ""; bv = b[6] || ""; }}
    else if (col === "name") {{ av = a[1]; bv = b[1]; }}
    else {{ av = a[0]; bv = b[0]; }}
    if (av < bv) return -1;
    if (av > bv) return 1;
    return a[0] < b[0] ? -1 : 1;
  }});
}}

function fmtSize(n) {{
  if (n < 1024) return n + " B";
  const units = ["KB","MB","GB","TB"];
  let v = n;
  for (const u of units) {{
    v /= 1024;
    if (v < 1024 || u === "TB") return v.toFixed(1) + " " + u;
  }}
}}

function fmtTime(ts) {{
  if (!ts) return "-";
  const d = new Date(ts * 1000);
  const p = x => String(x).padStart(2, "0");
  return d.getFullYear() + "-" + p(d.getMonth()+1) + "-" + p(d.getDate()) + " " + p(d.getHours()) + ":" + p(d.getMinutes());
}}

function addRow(tb, r, isUp) {{
  const [path, name, par, isDir, size, mtime, ext] = r;
  const tr = document.createElement("tr");
  if (isUp || isDir) tr.className = "dir-row";
  const tdName = document.createElement("td");
  const nameWrap = document.createElement("span");
  nameWrap.className = "name-wrap";
  const icon = document.createElement("span");
  icon.className = "file-icon " + (isDir ? "type-dir" : "type-" + fileType(ext));
  const iconFace = document.createElement("span");
  if (isUp) {{
    iconFace.textContent = "⬆";
  }} else if (isDir) {{
    iconFace.textContent = "📁";
  }} else {{
    iconFace.textContent = TYPE_META[fileType(ext)].emoji;
    const badge = document.createElement("span");
    badge.className = "ext-badge";
    badge.textContent = ext || "文件";
    icon.appendChild(badge);
  }}
  icon.appendChild(iconFace);
  const nameSpan = document.createElement("span");
  nameSpan.textContent = name;
  const nameBlock = document.createElement("span");
  nameBlock.className = "name-block";
  nameBlock.appendChild(nameSpan);
  if (state.view === "content") {{
    const sub = document.createElement("div");
    sub.className = "sub";
    sub.textContent = (isDir ? "目录" : TYPE_META[fileType(ext)].label) + " · " +
      (isDir ? "-" : fmtSize(size)) + " · " + fmtTime(mtime) + " · " + path;
    nameBlock.appendChild(sub);
  }}
  nameWrap.append(icon, nameBlock);
  tdName.className = "col-name";
  tdName.title = name;
  tdName.appendChild(nameWrap);
  const tdSize = document.createElement("td");
  tdSize.className = "size col-size";
  tdSize.textContent = isDir ? "-" : fmtSize(size);
  const tdTime = document.createElement("td");
  tdTime.className = "mtime col-mtime";
  tdTime.textContent = fmtTime(mtime);
  const tdExt = document.createElement("td");
  tdExt.className = "col-ext";
  tdExt.textContent = isDir ? "目录" : (TYPE_META[fileType(ext)].label);
  const tdPath = document.createElement("td");
  tdPath.className = "path col-path";
  tdPath.textContent = path;
  tdPath.title = path;
  tr.append(tdName, tdSize, tdTime, tdExt, tdPath);
  if (!isUp && isDir) tr.onclick = () => navigateTo(path);
  if (isUp) tr.onclick = () => navigateTo(par);
  tb.appendChild(tr);
}}

function renderRows() {{
  const start = state.page * PAGE_SIZE;
  const rows = filtered.slice(start, start + PAGE_SIZE);
  const gridModes = ["small", "medium", "large", "tiles"];
  const tableView = document.getElementById("tableView");
  const gridView = document.getElementById("gridView");
  tableView.className = "mode-" + state.view;
  if (gridModes.indexOf(state.view) >= 0) {{
    tableView.style.display = "none";
    gridView.style.display = "";
    renderGrid(rows);
  }} else {{
    tableView.style.display = "";
    gridView.style.display = "none";
    const tb = document.getElementById("tbody");
    tb.innerHTML = "";
    if (!state.q && currentPath !== "") {{
      addRow(tb, ["..", "返回上一级", parentOf(currentPath), 1, 0, 0, ""], true);
    }}
    for (const r of rows) addRow(tb, r, false);
  }}
  const total = filtered.length;
  document.getElementById("empty").style.display = (total === 0 && !(currentPath === "" && !state.q)) ? "block" : "none";
  document.getElementById("info").textContent = state.q ? ("搜索到 " + total + " 条") : ("共 " + total + " 条");
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  document.getElementById("pageInfo").textContent = (state.page + 1) + " / " + pages;
}}

function renderGrid(rows) {{
  const grid = document.getElementById("gridView");
  grid.className = "grid-view show view-" + state.view;
  grid.innerHTML = "";
  const addItem = (r, isUp) => {{
    const [path, name, par, isDir, size, mtime, ext] = r;
    const item = document.createElement("div");
    item.className = "grid-item";
    const icon = document.createElement("div");
    icon.className = "file-icon " + (isDir ? "type-dir" : "type-" + fileType(ext));
    const face = document.createElement("span");
    if (isUp) face.textContent = "⬆";
    else if (isDir) face.textContent = "📁";
    else {{
      face.textContent = TYPE_META[fileType(ext)].emoji;
      const badge = document.createElement("span");
      badge.className = "ext-badge";
      badge.textContent = ext || "文件";
      icon.appendChild(badge);
    }}
    icon.appendChild(face);
    const nameDiv = document.createElement("div");
    nameDiv.className = "gi-name";
    nameDiv.textContent = isUp ? "返回上一级" : name;
    const meta = document.createElement("div");
    meta.className = "gi-meta";
    meta.textContent = isDir ? ("目录 · " + fmtTime(mtime)) : (TYPE_META[fileType(ext)].label + " · " + fmtSize(size) + " · " + fmtTime(mtime));
    item.append(icon, nameDiv, meta);
    if (!isUp && isDir) item.onclick = () => navigateTo(path);
    if (isUp) item.onclick = () => navigateTo(par);
    grid.appendChild(item);
  }};
  if (!state.q && currentPath !== "") {{
    addItem(["..", "返回上一级", parentOf(currentPath), 1, 0, 0, ""], true);
  }}
  for (const r of rows) addItem(r, false);
}}

function onViewChange() {{
  state.view = document.getElementById("view").value;
  state.page = 0;
  apply();
}}

function renderTree() {{
  const root = document.getElementById("tree");
  root.innerHTML = "";
  const rootUl = document.createElement("ul");
  renderDirList(rootUl, "", 0);
  root.appendChild(rootUl);
}}

function renderDirList(parentUl, parentPath, depth) {{
  const dirs = (dirsByParent[parentPath] || []).slice().sort((a, b) => a[1].localeCompare(b[1], "zh-CN"));
  for (const d of dirs) {{
    const path = d[0], name = d[1];
    const li = document.createElement("li");
    const row = document.createElement("div");
    row.className = "tree-item" + (path === currentPath ? " active" : "");
    row.style.paddingLeft = (10 + depth * 14) + "px";
    const hasSub = (dirsByParent[path] || []).length > 0;
    const twist = document.createElement("span");
    twist.className = "twist";
    twist.textContent = hasSub ? (expanded.has(path) ? "▾" : "▸") : "";
    twist.onclick = (e) => {{ e.stopPropagation(); if (hasSub) toggleExpand(path); }};
    const label = document.createElement("span");
    label.textContent = "📁 " + name;
    row.append(twist, label);
    row.onclick = () => {{ if (hasSub) toggleExpand(path); selectFolder(path); }};
    li.appendChild(row);
    if (expanded.has(path) && hasSub) {{
      const sub = document.createElement("ul");
      renderDirList(sub, path, depth + 1);
      li.appendChild(sub);
    }}
    parentUl.appendChild(li);
  }}
}}

function toggleExpand(path) {{
  if (expanded.has(path)) expanded.delete(path); else expanded.add(path);
  renderTree();
}}

function collapseTo(path) {{
  expanded.clear();
  let cur = "";
  for (const seg of path ? path.split("/") : []) {{
    cur = cur ? cur + "/" + seg : seg;
    expanded.add(cur);
  }}
}}

function selectFolder(path) {{
  currentPath = path;
  state.page = 0;
  collapseTo(path);
  renderCrumbs();
  renderTree();
  apply();
}}

function navigateTo(path) {{
  currentPath = path;
  state.page = 0;
  collapseTo(path);
  renderTree();
  renderCrumbs();
  apply();
}}

function renderCrumbs() {{
  const box = document.getElementById("crumbs");
  box.innerHTML = "";
  const add = (text, path, first) => {{
    const span = document.createElement("span");
    span.textContent = text;
    span.className = "crumb";
    span.onclick = () => navigateTo(path);
    if (!first) {{
      const sep = document.createElement("span");
      sep.className = "sep";
      sep.textContent = "/";
      box.appendChild(sep);
    }}
    box.appendChild(span);
  }};
  add("根目录", "", true);
  let cur = "";
  for (const seg of currentPath ? currentPath.split("/") : []) {{
    cur = cur ? cur + "/" + seg : seg;
    add(seg, cur, false);
  }}
}}

function onFilter() {{
  state.q = document.getElementById("q").value;
  state.ext = document.getElementById("ext").value;
  state.sizeMin = document.getElementById("sizeMin").value;
  state.sizeMax = document.getElementById("sizeMax").value;
  state.dateFrom = document.getElementById("dateFrom").value;
  state.dateTo = document.getElementById("dateTo").value;
  state.sort = document.getElementById("sort").value;
  state.page = 0;
  apply();
}}

function setSort(col) {{
  document.getElementById("sort").value = col;
  state.sort = col;
  state.page = 0;
  apply();
}}

function toggleDirOnly() {{
  state.dirOnly = !state.dirOnly;
  document.getElementById("dirBtn").textContent = state.dirOnly ? "显示目录" : "只看文件";
  state.page = 0;
  apply();
}}

function reset() {{
  for (const id of ["q","ext","sizeMin","sizeMax","dateFrom","dateTo"]) document.getElementById(id).value = "";
  document.getElementById("sort").value = "name";
  const keepView = state.view;
  state = {{ q:"", ext:"", sizeMin:"", sizeMax:"", dateFrom:"", dateTo:"", sort:"name", dirOnly:false, view: keepView, page:0 }};
  document.getElementById("dirBtn").textContent = "只看文件";
  navigateTo("");
}}

function page(d) {{
  const pages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  state.page = Math.min(pages - 1, Math.max(0, state.page + d));
  renderRows();
}}

function setupResize() {{
  const splitter = document.getElementById("splitter");
  if (splitter) {{
    splitter.addEventListener("mousedown", (e) => {{
      e.preventDefault();
      const tree = document.querySelector(".tree-panel");
      const tablePanel = document.querySelector(".table-panel");
      const startX = e.clientX;
      const startW = tree.getBoundingClientRect().width;
      tree.style.flex = "0 0 auto";
      document.body.classList.add("resizing");
      const onMove = (ev) => {{
        const w = Math.min(700, Math.max(160, startW + (ev.clientX - startX)));
        tree.style.width = w + "px";
        tablePanel.style.flex = "1 1 auto";
        tablePanel.style.width = "auto";
      }};
      const onUp = () => {{
        document.body.classList.remove("resizing");
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup", onUp);
      }};
      document.addEventListener("mousemove", onMove);
      document.addEventListener("mouseup", onUp);
    }});
  }}
  const panelResize = document.getElementById("panelResize");
  if (panelResize) {{
    panelResize.addEventListener("mousedown", (e) => {{
      e.preventDefault();
      e.stopPropagation();
      const frame = panelResize.parentElement;
      const card = frame.querySelector(".card");
      const panel = document.querySelector(".table-panel");
      const startX = e.clientX;
      const startY = e.clientY;
      const startW = panel.getBoundingClientRect().width;
      const startH = frame.getBoundingClientRect().height;
      document.body.classList.add("resizing");
      const onMove = (ev) => {{
        const w = Math.max(320, startW + (ev.clientX - startX));
        const h = Math.max(220, startH + (ev.clientY - startY));
        panel.style.flex = "0 0 " + w + "px";
        frame.style.height = h + "px";
      }};
      const onUp = () => {{
        document.body.classList.remove("resizing");
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup", onUp);
      }};
      document.addEventListener("mousemove", onMove);
      document.addEventListener("mouseup", onUp);
    }});
  }}
  const resizeEast = document.getElementById("resizeEast");
  if (resizeEast) {{
    resizeEast.addEventListener("mousedown", (e) => {{
      e.preventDefault();
      e.stopPropagation();
      const panel = document.querySelector(".table-panel");
      const startX = e.clientX;
      const startW = panel.getBoundingClientRect().width;
      document.body.classList.add("resizing");
      const onMove = (ev) => {{
        const w = Math.max(320, startW + (ev.clientX - startX));
        panel.style.flex = "0 0 " + w + "px";
      }};
      const onUp = () => {{
        document.body.classList.remove("resizing");
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup", onUp);
      }};
      document.addEventListener("mousemove", onMove);
      document.addEventListener("mouseup", onUp);
    }});
  }}
  const resizeSouth = document.getElementById("resizeSouth");
  if (resizeSouth) {{
    resizeSouth.addEventListener("mousedown", (e) => {{
      e.preventDefault();
      e.stopPropagation();
      const frame = document.querySelector(".panel-frame");
      const startY = e.clientY;
      const startH = frame.getBoundingClientRect().height;
      document.body.classList.add("resizing");
      const onMove = (ev) => {{
        const h = Math.max(220, startH + (ev.clientY - startY));
        frame.style.height = h + "px";
      }};
      const onUp = () => {{
        document.body.classList.remove("resizing");
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup", onUp);
      }};
      document.addEventListener("mousemove", onMove);
      document.addEventListener("mouseup", onUp);
    }});
  }}
  document.querySelectorAll("#tableView th").forEach((th) => {{
    const res = document.createElement("span");
    res.className = "resizer";
    res.title = "拖动调整列宽";
    th.appendChild(res);
    res.addEventListener("mousedown", (e) => {{
      e.preventDefault();
      e.stopPropagation();
      const idx = th.cellIndex;
      const startX = e.clientX;
      const startW = th.getBoundingClientRect().width;
      document.body.classList.add("resizing");
      const onMove = (ev) => {{
        const w = Math.max(50, startW + (ev.clientX - startX));
        document.querySelectorAll(
          "#tableView th:nth-child(" + (idx + 1) + "), #tableView td:nth-child(" + (idx + 1) + ")"
        ).forEach((c) => {{ c.style.width = w + "px"; }});
      }};
      const onUp = () => {{
        document.body.classList.remove("resizing");
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup", onUp);
      }};
      document.addEventListener("mousemove", onMove);
      document.addEventListener("mouseup", onUp);
    }});
  }});
}}

setupResize();
apply();
</script>
</body>
</html>
"""


def export_html(
    db_path: Optional[str],
    disk_id: str,
    out_path: str | Path,
) -> tuple[bool, str]:
    conn = db.connect(db_path)
    try:
        disk = db.get_disk(conn, disk_id)
        if disk is None:
            return False, "未找到该硬盘的索引"
        rows = conn.execute(
            "SELECT path, name, parent, is_dir, size, mtime, ext "
            "FROM files WHERE disk_id=? ORDER BY path",
            (disk_id,),
        ).fetchall()
        data = [
            [r["path"], r["name"], r["parent"], int(r["is_dir"]), int(r["size"] or 0), int(r["mtime"] or 0), r["ext"]]
            for r in rows
        ]
        title = _html_escape((disk["label"].strip() or "硬盘") + " 文件目录")
        meta_text = _html_escape(
            f"盘符 {disk['drive_letter']} · 序列号 {disk['volume_serial'] or '-'} · "
            f"文件 {disk['total_files']:,} 个 · 总大小 {_fmt_size(disk['total_size'] or 0)} · "
            f"最近扫描 {_fmt_time(disk['last_scan_finished'])} · 导出时间 {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )
        total_cap = int(disk["volume_size"] or 0)
        free = int(disk["volume_free"] or 0)
        if total_cap > 0:
            used = max(0, total_cap - free)
            pct = min(100.0, used * 100.0 / total_cap)
            cap_html = (
                f'<div class="cap"><div class="cap-bar">'
                f'<div class="cap-used" style="width:{pct:.1f}%"></div></div>'
                f"<span>已用 {_fmt_size(used)} / 共 {_fmt_size(total_cap)}（{pct:.1f}%）</span></div>"
            )
        else:
            cap_html = ""
        meta = meta_text + cap_html
        data_json = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
        html_text = HTML_TEMPLATE.format(title=title, meta=meta, data=data_json)
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html_text, encoding="utf-8")
        return True, str(out.resolve())
    finally:
        conn.close()
