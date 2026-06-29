# 前端「灵动」Polish — 给 Codex 的改动说明

> 范围：**只动 `frontend/src/App.jsx` 与 `frontend/src/styles.css` 的视觉 / 布局 / 交互层。**
> 不改后端接口、`request()` 逻辑、数据结构、`normalizeXxx()` 字段、SSE 事件、业务规则。
> 组织方式保持单文件组件，不拆架构。
>
> 可视参考（同一套 design token，已做好目标效果）：
> - 桌面：`Companion Agent.dc.html`
> - 移动：`Companion Agent Android.dc.html`
>
> 设计基调不变：graphite / oklch 低饱和。本次只加**动效层 + 细节打磨**：列表错峰入场、tab/面板/坞切换过渡、成员浮层与弹窗入场、hover 抬升、打字气泡弹跳、聚焦光环、移动端右栏可达。

---

## 0. 一次性：在 `styles.css` 末尾追加「动效层」

整段粘到 `styles.css` 末尾即可。它只引用**已有的类名**，不新增 DOM。

```css
/* ============================================================
   Motion layer —— 灵动动效（只加过渡/入场，不改布局）
   ============================================================ */

/* 1) 全局过渡：按钮、输入框 */
.app-root button {
  transition: background .16s ease, color .16s ease, border-color .16s ease,
    transform .24s cubic-bezier(.34, 1.35, .5, 1), box-shadow .22s ease, opacity .16s ease;
}
.app-root button:active { transform: scale(.96); }
.app-root input,
.app-root textarea,
.app-root select {
  transition: border-color .18s ease, box-shadow .18s ease, background .18s ease;
}
.app-root input:focus,
.app-root textarea:focus,
.composer-box:focus-within,
.steward-input:focus-within {
  border-color: var(--border-strong);
  box-shadow: 0 0 0 3px var(--accent-soft);
}
/* 输入框本体无边框时（composer/steward 内的 input），把光环交给外壳 */
.composer-box input:focus, .steward-input input:focus { box-shadow: none; }

/* 2) 卡片 hover 抬升 */
.focus-card, .todo-card, .habit-card, .relation-card,
.steward-note, .role-stats > div, .stat-grid > div, .member-pick {
  transition: transform .24s cubic-bezier(.34, 1.35, .5, 1),
    box-shadow .22s ease, border-color .18s ease, background .16s ease;
}
.focus-card:hover, .todo-card:hover, .habit-card:hover,
.relation-card:hover, .role-stats > div:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 22px rgba(0, 0, 0, .07);
}
.app-root[data-theme="dark"] .focus-card:hover,
.app-root[data-theme="dark"] .todo-card:hover,
.app-root[data-theme="dark"] .habit-card:hover,
.app-root[data-theme="dark"] .relation-card:hover,
.app-root[data-theme="dark"] .role-stats > div:hover {
  box-shadow: 0 8px 22px rgba(0, 0, 0, .32);
}

/* 3) 发送按钮：彩色光晕抬升 */
.send-button:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 6px 16px color-mix(in oklch, var(--accent) 35%, transparent);
}

/* 4) 频道行 / 角色行：左侧 active 指示条（不改高度，纯视觉） */
.channel-row { position: relative; }
.channel-row::before {
  content: ""; position: absolute; left: 2px; top: 50%;
  width: 3px; height: 0; border-radius: 3px; background: var(--accent);
  transform: translateY(-50%); transition: height .2s cubic-bezier(.34, 1.3, .5, 1);
}
.channel-row.active::before { height: 18px; }

/* 5) 入场关键帧 */
@keyframes ccMsgIn   { from { opacity: .4; transform: translateY(12px) scale(.99); } to { opacity: 1; transform: none; } }
@keyframes ccRowIn   { from { opacity: .4; transform: translateY(8px); }            to { opacity: 1; transform: none; } }
@keyframes ccPanelIn { from { opacity: 0;  transform: translateY(10px); }           to { opacity: 1; transform: none; } }
@keyframes ccPopIn   { from { opacity: 0;  transform: translateY(-10px) scale(.96); } to { opacity: 1; transform: none; } }
@keyframes ccFadeIn  { from { opacity: 0; }                                          to { opacity: 1; } }
@keyframes ccSheetIn { from { opacity: 0;  transform: translateX(24px); }           to { opacity: 1; transform: none; } }
@keyframes ccModalIn { from { opacity: 0;  transform: translate(-50%, -50%) scale(.95); } to { opacity: 1; transform: translate(-50%, -50%) scale(1); } }
@keyframes ccDockIn  { from { opacity: 0;  transform: translateY(8px); }             to { opacity: 1; transform: none; } }
@keyframes ccBob     { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-3px); } }

/* 6) 消息入场：用 keyed 节点天然只对“新插入”的气泡生效（见 §3 说明），
   不用 nth-child 错峰，避免新消息被延迟。 */
.message-row { animation: ccMsgIn .42s cubic-bezier(.22, .7, .3, 1) both; }

/* 7) 频道 / 角色行入场（同上，keyed 节点只对新行触发） */
.channel-list .channel-row { animation: ccRowIn .38s ease both; }

/* 8) 右栏面板切换入场：给三个 Panel 组件的根容器加 .side-panel-anim（见 §4 App.jsx） */
.side-panel-anim { animation: ccPanelIn .34s cubic-bezier(.22, .7, .3, 1) both; }

/* 9) 成员浮层入场 */
.member-popover { animation: ccPopIn .22s cubic-bezier(.34, 1.4, .5, 1) both; transform-origin: top right; }
.member-pick:hover { transform: translateY(-1px); }

/* 10) 设置抽屉 / 弹窗 / 遮罩入场 */
.sheet-overlay { animation: ccFadeIn .2s ease both; }
.sheet  { animation: ccSheetIn .3s cubic-bezier(.22, .7, .3, 1) both; }
.modal  { animation: ccModalIn .26s cubic-bezier(.34, 1.3, .5, 1) both; }

/* 11) 管家坞展开入场 */
.steward-panel-body { animation: ccDockIn .3s cubic-bezier(.22, .7, .3, 1) both; }
.steward-panel.open .steward-panel-head > svg:last-child { transition: transform .26s cubic-bezier(.34, 1.3, .5, 1); }

/* 12) 打字气泡：闪烁 + 上下弹跳 */
.typing-bubble i, .steward-mini-typing i { animation: blink 1.3s infinite, ccBob 1.3s ease-in-out infinite; }

/* 13) 进度/熟悉度条：宽度变化补间 */
.role-familiarity span, .progress i, .habit-days i { transition: width .5s cubic-bezier(.22, .7, .3, 1), background .2s ease; }

/* 14) 尊重「减少动态效果」 */
@media (prefers-reduced-motion: reduce) {
  .app-root *, .message-row, .channel-list .channel-row, .side-panel-anim,
  .member-popover, .sheet, .modal, .sheet-overlay, .steward-panel-body {
    animation: none !important;
    transition: none !important;
  }
}
```

> **为什么消息/行入场可以纯 CSS：** React 给消息按 `message.id`、频道按 `channel.id` 设 key，重渲染时复用同一 DOM 节点 —— CSS 动画**只在节点插入时**触发。于是「老消息重渲染不重播、只有新到的消息/新建频道才入场」，正是想要的效果。**所以这里不要用 `nth-child` 错峰**（错峰会让新消息被延迟 0.2s+ 才出现）。错峰只在 DC 演示里用于首屏展示。

---

## 1. 群聊成员 + 面板（`MemberSheet`，重点）

`App.jsx` 里的 `MemberSheet` 结构已经齐了（真人/AI 双 tab、我的 AI / 娱乐 AI 分组、搜索、当前成员+移除）。**只做视觉打磨，逻辑不动。**

### styles.css

1. 入场动效已在 §0(9) 加好（`.member-popover` 的 `ccPopIn` + `transform-origin: top right`）。
2. `.member-popover` 阴影/圆角微调，更轻：
   ```css
   .member-popover { border-radius: 13px; gap: 10px; }
   ```
3. 触发按钮的「打开态」反馈 —— 给 `+` 图标按钮一个 active 视觉。当前是裸 `.icon-button`，加一个状态类：
   - **App.jsx**：`MemberSheet` 打开时给那颗按钮加 `aria-expanded` / `data-open`。把
     ```jsx
     <button className="icon-button" onClick={() => setSheet(sheet === "members" ? null : "members")} title="添加成员">
     ```
     改为
     ```jsx
     <button className={sheet === "members" ? "icon-button is-open" : "icon-button"}
             onClick={() => setSheet(sheet === "members" ? null : "members")} title="添加成员">
     ```
   - **styles.css**：
     ```css
     .icon-button.is-open { background: var(--active-bg); color: var(--text); border-color: var(--border-strong); }
     ```
4. 给 `+` 图标按钮换更贴切的「加人」图标（可选）：当前用的是 `Plus`，建议用 `UserPlus`（lucide 已在依赖里）。在 `App.jsx` 顶部 import 增加 `UserPlus`，把那颗按钮的 `<Plus size={17} />` 换成 `<UserPlus size={17} />`。

### 当前成员行：移除按钮的禁用态更清楚（styles.css）

```css
.member-row.compact button:disabled { opacity: .4; }
.member-row.compact button:not(:disabled):hover { color: var(--danger); border-color: var(--danger); }
```

---

## 2. 聊天主界面（styles.css，少量 App.jsx）

### styles.css

1. **消息入场** —— §0(6) 已覆盖。
2. **气泡进入时的轻微方向感**（可选增强，区分收/发）：
   ```css
   .message-row.incoming { animation-name: ccMsgInLeft; }
   .message-row.outgoing { animation-name: ccMsgInRight; }
   @keyframes ccMsgInLeft  { from { opacity: .4; transform: translateY(10px) translateX(-6px); } to { opacity: 1; transform: none; } }
   @keyframes ccMsgInRight { from { opacity: .4; transform: translateY(10px) translateX(6px); }  to { opacity: 1; transform: none; } }
   ```
3. **输入框聚焦光环** —— §0(1) 已覆盖（`.composer-box:focus-within`）。
4. **建议 chips / @ 提及条** 过渡顺滑（已有 hover，过渡由 §0(1) 补上）。再给 chips 一点 hover 抬升：
   ```css
   .suggestions button:hover { transform: translateY(-1px); border-color: var(--border-strong); }
   .mention-strip > button:hover { background: var(--accent-soft); color: var(--text); }
   ```
5. **空状态更精致**（`.empty`）：
   ```css
   .empty { border-style: dashed; background: var(--subtle); }
   ```

### 图片气泡点击放大（可选，纯前端）

`BubbleContent` 的 `<img className="bubble-image">` 可加 `style={{ cursor: "zoom-in" }}`，并在 `MessageBubble` 里加一个本地 `useState` 的 lightbox（点击全屏遮罩看大图）。属于交互增强，不接后端。若不想加，跳过。

---

## 3. 角色页（`RolePage`，styles.css）

1. 头像/统计卡 hover 抬升 —— §0(2) 已覆盖（`.role-stats > div`）。
2. **熟悉度条补间** —— §0(13) 已覆盖（`.role-familiarity span`）。首次进入时让它从 0 涨到目标值更灵动：
   - **App.jsx**（`RolePage` 内，纯展示，不碰数据）：用一个 `useEffect` 在挂载后下一帧把宽度从 0 设到 `pct`。最简做法是给 `.role-familiarity span` 加 `key={activePersona.id}` 触发重挂载 + CSS transition；或保持现状只享受 hover 外的静态展示。建议低成本版：
     ```jsx
     <div><span key={activePersona.id} style={{ width: `${pct}%` }} /></div>
     ```
     配合 §0(13) 的 `transition: width .5s`，切换角色时会有补间。
3. **性格标签**：hover/删除反馈
   ```css
   .trait-row button:hover { background: var(--active-bg); border-color: var(--border-strong); }
   .trait-row button:hover::after { content: " ×"; color: var(--text-3); }
   ```
4. 「发起对话 / 保存角色卡」主按钮 hover —— §0(3) 同理，给它们补：
   ```css
   .role-hero > button:hover, .role-actions button:first-child:hover {
     transform: translateY(-1px);
     box-shadow: 0 6px 16px color-mix(in oklch, var(--accent) 30%, transparent);
   }
   ```

---

## 4. 管家 dock（`StewardDock`，styles.css + App.jsx）

1. **展开入场** —— §0(11) 已覆盖（`.steward-panel-body` 的 `ccDockIn`）。
2. **chevron 旋转补间** —— §0(11) 已加 transition；现有 `.steward-panel.open ... svg:last-child{transform:rotate(180deg)}` 会顺滑旋转。
3. **坞头像在线点** 呼吸（可选）：
   ```css
   @keyframes ccPulse { 0%,100% { box-shadow: 0 0 0 0 color-mix(in oklch, var(--low) 60%, transparent); } 50% { box-shadow: 0 0 0 4px transparent; } }
   ```
   配一个绿点元素使用 `animation: ccPulse 2.4s infinite;`（当前 dock 头部已有头像，可在其右下角加一个 `<span>` 状态点）。
4. **快捷 chip** hover 抬升：
   ```css
   .steward-chip-row button:hover { transform: translateY(-1px); }
   ```
5. **迷你消息入场**：给 `.steward-mini-row` 加和消息一致的入场（同 keyed 规则）：
   ```css
   .steward-mini-row { animation: ccMsgIn .4s cubic-bezier(.22,.7,.3,1) both; }
   ```

---

## 5. 右栏面板切换动效（App.jsx + styles.css）

让「今日 / 事项 / 记忆」切换时有入场。`.side-panel-anim` 的样式已在 §0(8)。**App.jsx**：给三个面板组件最外层各包一层带 key 的容器（key 用 tab 名，切 tab 即重挂载触发动画）。

在主组件 `.side-scroll` 内，把
```jsx
{tab === "today" && (<TodayPanel ... />)}
{tab === "tasks" && (<TasksPanel ... />)}
{tab === "memory" && <MemoryPanel ... />}
```
改为
```jsx
<div className="side-panel-anim" key={tab}>
  {tab === "today" && (<TodayPanel ... />)}
  {tab === "tasks" && (<TasksPanel ... />)}
  {tab === "memory" && <MemoryPanel ... />}
</div>
```
`key={tab}` 保证切换时整块重挂载 → 播放 `ccPanelIn`。这层 `div` 不影响现有间距（`.side-scroll` 的 gap 仍作用于它与上方 `.debug-panel` 之间；面板内部各自有自己的 gap）。

---

## 6. 弱点：右栏顶部「催化剂读数 / compare() JSON」调试块（App.jsx + styles.css）

`.debug-panel` 里直接 `<pre>{JSON.stringify(metrics)}</pre>`，很「dev」，拉低成品感。**做成可折叠的开发者抽屉，默认收起。**

**App.jsx**：在主组件加一个本地 state `const [showDebug, setShowDebug] = useState(false);`，把那段 `<section className="debug-panel">` 改成：

```jsx
<section className={showDebug ? "debug-panel open" : "debug-panel"}>
  <button className="debug-head" onClick={() => setShowDebug((v) => !v)}>
    <span><strong>催化剂读数</strong> · {activeChannel?.aiEnabled ? "AI 在场" : "AI 缺席"}</span>
    <ChevronDown size={15} />
  </button>
  {showDebug && (
    <>
      <button className="debug-refresh" onClick={loadMetricsCompare}>刷新 compare()</button>
      {metrics && <pre>{JSON.stringify(metrics, null, 2)}</pre>}
    </>
  )}
</section>
```

**styles.css**（替换/补充 `.debug-panel` 相关规则）：
```css
.debug-panel { padding: 0; gap: 0; overflow: hidden; }
.debug-head {
  width: 100%; display: flex; align-items: center; justify-content: space-between;
  padding: 11px 12px; border: 0; background: transparent; color: var(--text);
  font-size: 13px; cursor: pointer;
}
.debug-head:hover { background: var(--subtle); }
.debug-panel.open .debug-head > svg { transform: rotate(180deg); }
.debug-head > svg { color: var(--text-3); transition: transform .26s cubic-bezier(.34,1.3,.5,1); }
.debug-refresh { margin: 0 12px 10px; }
.debug-panel pre { margin: 0 12px 12px; }
```
> 这样默认只剩一行「催化剂读数 · AI 在场 ▾」，干净；需要时点开看 JSON。不动 `loadMetricsCompare()` 和接口。

---

## 7. 移动端布局（styles.css，关键一处 App.jsx）

> 现状：`@media (max-width: 880px)` 直接 `.right-pane { display: none }` —— **今日/事项/记忆 + 管家坞在手机上整块不可达**。这是移动端最大缺口。

### 7a.（关键）让右栏在手机上可达：底部「工作台」抽屉

最小改动方案：手机下显示一个浮动按钮，点开把 `.right-pane` 作为**全屏 slide-over** 升起。

**App.jsx**：
1. 加 state：`const [paneOpen, setPaneOpen] = useState(false);`
2. 给 `.right-pane` 容器加状态类：
   ```jsx
   <aside className={paneOpen ? "right-pane mobile-open" : "right-pane"}>
   ```
3. 在 `.workspace` 末尾（`.right-pane` 之后）加一颗只在手机显示的 FAB + 关闭按钮：
   ```jsx
   <button className="pane-fab" onClick={() => setPaneOpen(true)} aria-label="打开工作台">
     <Bell size={20} />
   </button>
   ```
   并在 `.right-pane` 顶部 `.tabs` 旁加一个移动端可见的关闭按钮（`onClick={() => setPaneOpen(false)}`，类名 `pane-close`）。

**styles.css**（替换原 `@media (max-width: 880px)` 里那条 `.right-pane{display:none}`）：
```css
.pane-fab { display: none; }
.pane-close { display: none; }

@media (max-width: 880px) {
  .topbar-actions select, .topbar-actions > button:not(.icon-button) { display: none; }

  /* 右栏改为可升起的 slide-over，而不是直接隐藏 */
  .right-pane {
    position: fixed; inset: 0; left: auto; width: min(420px, 100%);
    z-index: 45; transform: translateX(100%);
    transition: transform .32s cubic-bezier(.22, .8, .3, 1);
    box-shadow: var(--shadow-lg); display: flex;
  }
  .right-pane.mobile-open { transform: none; }

  .pane-fab {
    display: inline-flex; align-items: center; justify-content: center;
    position: fixed; right: 16px; bottom: calc(78px + env(safe-area-inset-bottom));
    width: 52px; height: 52px; border-radius: 50%; z-index: 44;
    background: var(--accent); color: var(--accent-text); border: 0;
    box-shadow: 0 8px 24px rgba(0, 0, 0, .22); cursor: pointer;
  }
  .pane-close { display: inline-flex; }
}
```
> 若想更彻底（像 `Companion Agent Android.dc.html` 那样的原生四 tab 底栏），是更大改动，建议作为后续单独迭代；本次先把右栏「可达」补上。

### 7b. 移动端触感 / 间距打磨（styles.css，已有 `@media (max-width:560px)` 内补充）

```css
@media (max-width: 560px) {
  /* 命中区不小于 44px */
  .composer-icon { width: 40px; height: 40px; }
  .channel-row { padding: 11px 12px; }
  /* 气泡两端留白更舒展 */
  .message-list { padding: 16px 14px; }
  /* 顶部横排频道头像点选反馈 */
  .channel-row:active { transform: scale(.94); }
}
```

### 7c. 移动端成员面板

`MemberSheet` 当前是绝对定位浮层（`.member-popover` `position:absolute; right:0; top:42px`），在窄屏会顶到边。手机下改为**底部抽屉**更顺手：

**styles.css**：
```css
@media (max-width: 560px) {
  .member-popover {
    position: fixed; left: 0; right: 0; bottom: 0; top: auto;
    width: 100%; max-height: 80vh; border-radius: 16px 16px 0 0;
    animation: ccSheetUp .32s cubic-bezier(.22, .8, .3, 1) both;
  }
  @keyframes ccSheetUp { from { transform: translateY(100%); } to { transform: none; } }
}
```
> `MemberSheet` 的 JSX 不用改，纯靠媒体查询切换定位形态。

---

## 8. 验收清单

- [ ] 桌面：消息逐条淡入；切频道时新列表入场；老消息重渲染不重播（验证发新消息时旧气泡不闪）。
- [ ] 成员浮层从右上角弹性展开；`+` 按钮有打开态；真人/AI 双 tab、我的 AI / 娱乐 AI 分组、当前成员移除态正确。
- [ ] 卡片（聚焦/待办/习惯/关系/统计）hover 抬升；发送/主按钮彩色光晕。
- [ ] 输入框聚焦有 accent 光环；打字气泡上下弹跳。
- [ ] 管家坞展开有入场 + chevron 旋转；快捷 chip 抬升。
- [ ] 右栏「今日/事项/记忆」切 tab 有入场过渡。
- [ ] 调试块默认收起为一行，可点开看 JSON。
- [ ] 手机（<880px）：右下角 FAB 可升起「工作台」slide-over；成员面板在 <560px 走底部抽屉。
- [ ] `prefers-reduced-motion` 下全部动效关闭。
- [ ] `cd frontend && npm run build` 通过。

> 不确定的取舍（如气泡 lightbox、坞呼吸点、原生底栏）都标了「可选」，可按时间裁剪，不影响主链路。
