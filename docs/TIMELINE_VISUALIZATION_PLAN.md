# Winflow 活动带时间轴可视化开发文档

> 本文档是 Winflow “活动带可视化”阶段的开发总纲。目标是在现有 `/api/bands` 和活动带列表基础上，增加一套类似 Git graph 的多轨时间轴，让用户能从时间轴角度直观看到一天中不同应用/网站活动的持续区间。

---

## 1. 背景与目标

当前 Winflow 已具备：

- 原始事件采集：前台窗口、浏览器访问历史
- 活动带聚合：15 分钟窗口、3 分钟阈值、5 次访问阈值、3 分钟间隔合并
- Web UI：活动带 / 原始事件切换
- API：`/api/bands`

当前实现补充：Web UI 已在活动带模式中加入多轨“活动带时间轴”，默认使用紧凑范围展示，并提供“全天”范围切换；原始事件模式仍用于查看未聚合事件。

此前 Web UI 主要还是列表视图。列表能看详情，但不够直观，难以回答：

```text
上午 10 点左右，我同时在看哪些东西？
某个应用/网站从什么时候持续到什么时候？
哪些活动是并行发生的？
```

本阶段目标：

> 在 Web UI 中新增“多轨活动带时间轴”，用横向时间轴展示不同事件的持续区间，让用户像看 Git graph 一样回看自己一天中的活动流。

---

## 2. 产品理念

### 2.1 时间轴优先

用户不是先关心列表，而是关心：

```text
某个时间点我在做什么？
这段时间内有哪些活动线？
```

因此时间轴应成为活动带视图的主视觉。

### 2.2 多轨而非单轨

Winflow 的活动带允许并行存在。

例如：

```text
09:00 - 10:00 Code.exe
09:10 - 09:45 github.com
09:30 - 09:55 PowerShell.exe
```

这些不是互斥关系，而是同一时间段内共同构成用户上下文的多条活动线。

所以可视化应采用多轨设计：

```text
09:00      09:15      09:30      09:45      10:00
│─────────│─────────│─────────│─────────│
Code.exe        ██████████████████████████
github.com          ███████████
PowerShell                    █████████
```

### 2.3 保留详情列表

时间轴负责“看整体”，列表负责“看细节”。

因此本阶段不是删除活动带列表，而是在活动带列表上方增加时间轴图。

---

## 3. 需求范围

### 3.1 必做需求

1. 活动带时间轴组件
   - 使用 `/api/bands` 返回的 `bands` 绘制
   - 每个 `event_key` 一行轨道
   - 每条活动带用横向色块表示
   - 色块位置由 `start_ts` / `end_ts` 映射到时间轴百分比

2. 时间刻度
   - 根据当前显示范围生成小时刻度
   - 刻度显示 `HH:MM`
   - 刻度线贯穿时间轴区域

3. 紧凑视图 / 全天视图
   - 默认紧凑视图
   - 紧凑视图范围：第一条活动开始时间向前取整到小时，最后一条活动结束时间向后取整到小时
   - 全天视图范围：当天 `start_ts` 到 `end_ts`
   - UI 提供切换按钮

4. Hover / title 详情
   - 鼠标悬停活动块时显示原生 `title` 或自定义 tooltip
   - 内容包含：
     - 标题
     - 时间范围
     - 估算活跃分钟
     - 命中次数
     - 样本标题 / URL

5. 与现有视图集成
   - 仅在 `mode === 'bands'` 时显示时间轴
   - 原始事件视图不显示或隐藏时间轴
   - 日期切换后时间轴自动刷新
   - 自动刷新仍可用

6. 不引入新依赖
   - 使用原生 HTML / CSS / JavaScript
   - 不使用 ECharts、D3、React 等

### 3.2 可选需求

如果时间允许可做：

1. 点击活动带，在列表中定位对应项
2. 按 event_type 分组：应用 / 网页
3. 左侧轨道名称过长时省略并 hover 显示完整名称
4. 活动块最小宽度，避免短活动不可见
5. 空状态提示

### 3.3 暂不做需求

本阶段不做：

- 缩放 / 拖拽时间轴
- Canvas 绘图
- SVG 图表
- AI 自动主题聚合
- 截图采集或截图预览
- 按分类自动配色
- 周视图 / 月视图

文档和 README 应只描述当前已实现能力，不承诺缩放、拖拽、AI 或截图相关功能。

---

## 4. 当前相关文件

主要文件：

```text
C:\Users\28377\Desktop\winflow\app\main.py
```

当前 Web UI 是 `main.py` 中的 `HTML` 字符串。

当前活动带 API：

```text
GET /api/bands?day=YYYY-MM-DD
```

返回结构示例：

```json
{
  "day": "2026-05-18",
  "start_ts": 1779033600,
  "end_ts": 1779119999,
  "bands": [
    {
      "event_key": "app:Code.exe",
      "event_type": "app",
      "start_ts": 1779040800,
      "end_ts": 1779046200,
      "title": "Code.exe",
      "subtitle": "main.py - winflow",
      "detail": "C:\\...\\Code.exe",
      "total_active_seconds": 3300,
      "hit_count": 14,
      "sample_titles": ["main.py - winflow"],
      "sample_details": []
    }
  ]
}
```

---

## 5. UI 设计方案

### 5.1 页面布局

活动带模式下推荐布局：

```text
┌──────────────────────────────────────────────┐
│ 日期选择 / 活动带 / 原始事件 / 紧凑 / 全天 / 导出 │
└──────────────────────────────────────────────┘

┌─────────────┐ ┌──────────────────────────────┐
│ 统计排行     │ │ 活动带时间轴                  │
│             │ │ 09:00  10:00  11:00          │
│             │ │ Code.exe      ███████        │
│             │ │ github.com       ████        │
└─────────────┘ └──────────────────────────────┘

┌──────────────────────────────────────────────┐
│ 活动带详情列表                                │
└──────────────────────────────────────────────┘
```

### 5.2 DOM 建议

在活动带列表上方增加：

```html
<div id="timelineViz" class="timeline-viz panel">
  <div class="timeline-viz-header">
    <div>
      <p class="stat-title">活动带时间轴</p>
      <div class="sub">多条活动可并行出现，长度表示持续区间。</div>
    </div>
    <div class="view-toggle">
      <button id="compactRangeBtn">紧凑</button>
      <button id="fullRangeBtn">全天</button>
    </div>
  </div>
  <div id="timelineChart" class="timeline-chart"></div>
</div>
```

也可以直接放在现有右侧 `.panel.timeline` 内部：

```html
<section class="panel timeline">
  <div id="timelineViz">...</div>
  <p class="stat-title" id="timeline-title">时间线</p>
  <div id="items"></div>
</section>
```

第一版建议放在现有右侧 panel 内，减少布局改动。

---

## 6. 时间轴计算逻辑

### 6.1 显示范围

定义全局变量：

```js
let rangeMode = 'compact'; // compact | full
```

#### 全天视图

```js
rangeStart = data.start_ts;
rangeEnd = data.end_ts;
```

#### 紧凑视图

如果有活动带：

```js
minStart = Math.min(...bands.map(b => b.start_ts));
maxEnd = Math.max(...bands.map(b => b.end_ts));
rangeStart = floorToHour(minStart);
rangeEnd = ceilToHour(maxEnd);
```

如果没有活动带，则 fallback：

```js
rangeStart = data.start_ts;
rangeEnd = data.end_ts;
```

### 6.2 时间到百分比

```js
function pct(ts, rangeStart, rangeEnd) {
  return (ts - rangeStart) / (rangeEnd - rangeStart) * 100;
}
```

活动块：

```js
left = pct(band.start_ts)
right = pct(band.end_ts)
width = right - left
```

注意：

```js
left = Math.max(0, Math.min(100, left))
width = Math.max(0.6, Math.min(100 - left, width))
```

加最小宽度是为了短活动也可见。

### 6.3 小时刻度

```js
function buildTicks(rangeStart, rangeEnd) {
  let ticks = [];
  let cursor = ceilToHour(rangeStart);
  while (cursor <= rangeEnd) {
    ticks.push(cursor);
    cursor += 3600;
  }
  return ticks;
}
```

每个 tick 渲染为绝对定位竖线：

```html
<div class="tick" style="left: 23%">
  <span>10:00</span>
</div>
```

---

## 7. 轨道设计

### 7.1 每个 event_key 一条轨道

将 bands 分组：

```js
const lanes = new Map();
for (const band of bands) {
  if (!lanes.has(band.event_key)) lanes.set(band.event_key, []);
  lanes.get(band.event_key).push(band);
}
```

排序建议：

1. 先按最早开始时间
2. 再按总活跃时长倒序

```js
lanes.sort((a, b) => {
  return a.firstStart - b.firstStart || b.totalSeconds - a.totalSeconds;
});
```

### 7.2 轨道名称

显示建议：

- 应用：`Code.exe`
- 网页：`github.com`

可以从 `band.title` 取。

如果太长：

```css
.lane-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
```

### 7.3 活动块样式

```css
.timeline-band {
  position: absolute;
  top: 7px;
  height: 18px;
  border-radius: 999px;
  cursor: pointer;
}
.timeline-band.app { background: linear-gradient(90deg, #c47a31, #9b5c25); }
.timeline-band.web { background: linear-gradient(90deg, #4e91ad, #315f7d); }
```

---

## 8. 交互设计

### 8.1 Hover 详情

第一版可以直接使用原生 `title` 属性。

内容：

```text
Code.exe
09:12 - 10:04
估算活跃：42 分钟
命中：18 次
样本：
main.py - winflow
activity_bands.py - winflow
```

生成：

```js
function bandTooltip(band) { ... }
```

### 8.2 点击定位列表项（可选）

给每个列表项加 id：

```html
<div id="band-${index}">
```

活动块点击：

```js
document.getElementById(`band-${band._index}`).scrollIntoView({ behavior: 'smooth' })
```

本阶段可选，但建议实现，成本低。

### 8.3 视图切换

现有：

```js
mode = 'bands' | 'raw'
```

新增：

```js
rangeMode = 'compact' | 'full'
```

当 `mode === 'raw'`：

```js
document.getElementById('timelineViz').style.display = 'none'
```

当 `mode === 'bands'`：

```js
document.getElementById('timelineViz').style.display = ''
```

---

## 9. CSS 建议

建议新增样式：

```css
.timeline-viz { margin-bottom: 18px; padding-bottom: 12px; }
.timeline-viz-header { display:flex; justify-content:space-between; gap:12px; align-items:center; margin-bottom:12px; }
.timeline-chart { overflow-x:auto; padding-bottom:8px; }
.timeline-scale { position:relative; height:28px; margin-left:140px; border-bottom:1px solid var(--line); min-width:720px; }
.tick { position:absolute; top:0; bottom:0; border-left:1px solid rgba(121,108,95,.35); }
.tick span { position:absolute; top:0; transform:translateX(-50%); font-size:11px; color:var(--muted); }
.lane { display:grid; grid-template-columns:130px minmax(720px, 1fr); min-height:34px; align-items:center; }
.lane-label { font-size:12px; color:var(--muted); padding-right:10px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.lane-track { position:relative; height:32px; border-bottom:1px dashed rgba(227,214,197,.8); }
.timeline-band { position:absolute; top:7px; height:18px; border-radius:999px; min-width:6px; box-shadow:0 2px 8px rgba(36,28,22,.12); }
.timeline-band.app { background:linear-gradient(90deg,#c47a31,#9b5c25); }
.timeline-band.web { background:linear-gradient(90deg,#4e91ad,#315f7d); }
```

---

## 10. 测试策略

当前主要是前端渲染逻辑，无浏览器自动化测试框架。第一阶段采用：

### 10.1 后端不破坏测试

必须通过：

```powershell
python -m unittest discover -s tests
python -m compileall -q app tests
```

### 10.2 API 手工验证

```powershell
python -m app.main bands
python -m app.main serve
```

访问：

```text
http://127.0.0.1:8765/api/bands
http://127.0.0.1:8765
```

### 10.3 前端手工验证清单

1. 活动带模式下显示时间轴
2. 原始事件模式下隐藏时间轴
3. 日期切换后时间轴刷新
4. 紧凑 / 全天按钮可切换
5. 时间刻度合理
6. 活动块位置和长度随时间变化
7. Hover 有详情
8. 无活动带时显示空状态
9. 小屏幕下不崩，允许横向滚动

---

## 11. 子模块拆分与 subagent 任务

由于当前 Web UI 仍在 `app/main.py` 的 HTML 字符串中，多个 agent 同时修改会冲突。建议串行开发，或者严格拆分。

---

### Agent F：时间轴数据与渲染函数

#### 负责文件

```text
C:\Users\28377\Desktop\winflow\app\main.py
```

#### 分支建议

```text
feature/timeline-viz-core
```

#### 任务

1. 在 HTML 中增加时间轴容器 `timelineViz` / `timelineChart`
2. 在 JS 中新增：
   - `rangeMode`
   - `setRangeMode(next)`
   - `floorToHour(ts)`
   - `ceilToHour(ts)`
   - `buildTimelineRange(data)`
   - `buildTicks(rangeStart, rangeEnd)`
   - `renderTimelineViz(data)`
   - `bandTooltip(band)`
3. 在 `loadData()` 中，当 `mode === 'bands'` 时调用 `renderTimelineViz(data)`
4. 当 `mode === 'raw'` 时隐藏时间轴

#### 验收标准

- `python -m app.main serve` 页面中可看到时间轴区域
- `/api/bands` 有数据时，时间轴能渲染轨道和活动块
- 没有 bands 时显示空状态
- 不破坏活动带列表和原始事件列表

---

### Agent G：时间轴样式与交互优化

#### 负责文件

```text
C:\Users\28377\Desktop\winflow\app\main.py
```

#### 分支建议

```text
feature/timeline-viz-style
```

#### 任务

必须在 Agent F 合入后再进行。

1. 优化 CSS：
   - 时间轴刻度
   - 轨道标签
   - app/web 不同颜色
   - 横向滚动
   - 小屏适配
2. 增加紧凑 / 全天按钮样式
3. 活动块 hover / title 信息优化
4. 可选：点击活动块定位到活动带列表项

#### 验收标准

- 页面视觉清晰
- 活动块颜色区分 app/web
- 长名称不会撑破布局
- 小屏幕可横向滚动

---

### Agent H：文档更新

#### 负责文件

```text
C:\Users\28377\Desktop\winflow\README.md
C:\Users\28377\Desktop\winflow\docs\TIMELINE_VISUALIZATION_PLAN.md
```

#### 分支建议

```text
feature/timeline-viz-docs
```

#### 任务

1. 更新 README，说明时间轴视图
2. 说明：
   - 活动带模式
   - 原始事件模式
   - 紧凑 / 全天视图
3. 不承诺未实现的缩放、AI、截图功能

#### 验收标准

- README 中能指导用户启动并理解时间轴
- 文档与实际功能一致

---

## 12. 推荐开发顺序

```text
1. Agent F：时间轴核心渲染
2. 主控审核并合并
3. Agent G：样式与交互优化
4. 主控审核并合并
5. Agent H：文档更新
6. 主控最终测试
```

不建议 F 和 G 并行，因为都会修改 `app/main.py`。

---

## 13. 代码质量要求

1. 不引入第三方依赖
2. 不破坏现有 API
3. 不破坏现有 CLI
4. `mode === 'raw'` 时原始事件视图保持可用
5. `mode === 'bands'` 时列表仍保持可用
6. 时间计算统一使用 Unix seconds
7. UI 中所有用户数据必须经过 `esc()` 转义
8. 长 URL / 长窗口标题必须可换行或省略
9. CSS 命名避免与现有 `.timeline`、`.item` 产生过度冲突

---

## 14. 风险点

### 14.1 全天视图太拥挤

全天 24 小时会让活动块很短。

解决：默认紧凑视图，并保留全天视图按钮。

### 14.2 活动带太多导致页面很长

解决：第一版允许纵向滚动。后续再做折叠 / top N / 搜索。

### 14.3 同一轨道多个活动块重叠

理论上同 `event_key` 已经经过合并，通常不会重叠。

如果出现重叠，第一版允许覆盖或相邻显示，后续再做 lane 内避让。

### 14.4 纯 HTML 字符串继续膨胀

当前为了 MVP 速度继续修改 `main.py`。

后续建议拆分：

```text
app/web_ui.py
static/index.html
static/app.js
static/styles.css
```

本阶段暂不拆，避免扩大改动范围。

---

## 15. 完成标准

本阶段完成后，应满足：

- Web UI 默认活动带模式下显示多轨时间轴
- 时间轴有小时刻度
- 活动块位置和宽度对应时间范围
- 每个事件一条轨道
- app/web 颜色不同
- 支持紧凑 / 全天范围切换
- Hover 可以查看活动带详情
- 原始事件模式仍可正常查看
- 所有现有单元测试通过
- `python -m compileall -q app tests` 通过

---

## 16. 给 subagent 的通用提示词

```text
你正在开发 C:\Users\28377\Desktop\winflow。请先阅读 docs\TIMELINE_VISUALIZATION_PLAN.md 和 docs\DEVELOPMENT_PLAN.md。
只修改你负责的文件，不要重写无关模块。
保持现有 CLI 可用：python -m app.main init/once/collect/serve/export/bands。
保持现有测试通过：python -m unittest discover -s tests。
本阶段不引入新依赖，使用原生 HTML/CSS/JavaScript。
完成后说明你使用的 git 分支、commit、修改文件、实现内容和验证方式。
```
