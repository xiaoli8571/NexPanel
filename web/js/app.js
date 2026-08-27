/* ═══════════════════ NexPanel · 前端 SPA ═══════════════════ */
"use strict";

/* ---------- 小工具 ---------- */
const $  = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"']/g,
  m => ({ "&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;" }[m]));
const fmtGB  = mb => mb >= 1024 ? (mb/1024).toFixed(mb%1024?1:0)+" GB" : mb+" MB";
const fmtKb  = k => k >= 1024 ? (k/1024).toFixed(1)+" Mbps" : Math.round(k)+" Kbps";
const fmtUp  = s => { if(!s) return "—";
  const d=Math.floor(s/86400),h=Math.floor(s%86400/3600),m=Math.floor(s%3600/60);
  return d?`${d}天${h}时`:h?`${h}时${m}分`:`${m}分钟`; };
const fmtNum = v => v>=1e6?(v/1e6).toFixed(1)+"M":v>=1000?(v/1000).toFixed(1)+"k":Math.round(v);
const barColor = p => p<50?"var(--ok)":p<80?"var(--warn)":"var(--err)";

function toast(msg, type="info", ms=2600){
  const t = document.createElement("div");
  t.className = `toast ${type}`;
  t.innerHTML = `<span>${{ok:"✅",err:"⛔",info:"ℹ️"}[type]}</span><span>${esc(msg)}</span>`;
  $("#toasts").appendChild(t);
  setTimeout(()=>{ t.style.opacity=0; t.style.transition=".3s"; setTimeout(()=>t.remove(),300); }, ms);
}

/* ---------- 图标(feather 风格) ---------- */
const P = {
  grid:`<rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/>`,
  box:`<path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/>`,
  layers:`<polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/>`,
  disc:`<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="3"/>`,
  clock:`<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>`,
  globe:`<circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>`,
  users:`<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>`,
  file:`<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>`,
  sliders:`<line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/>`,
  term:`<polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/>`,
  play:`<polygon points="6 4 20 12 6 20"/>`,
  stop:`<rect x="6" y="6" width="12" height="12" rx="1"/>`,
  rotate:`<polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>`,
  trash:`<polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>`,
  camera:`<path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/>`,
  plus:`<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>`,
  search:`<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>`,
  cpu:`<rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><line x1="9" y1="1" x2="9" y2="4"/><line x1="15" y1="1" x2="15" y2="4"/><line x1="9" y1="20" x2="9" y2="23"/><line x1="15" y1="20" x2="15" y2="23"/><line x1="20" y1="9" x2="23" y2="9"/><line x1="20" y1="14" x2="23" y2="14"/><line x1="1" y1="9" x2="4" y2="9"/><line x1="1" y1="14" x2="4" y2="14"/>`,
  drive:`<line x1="22" y1="12" x2="2" y2="12"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/><line x1="6" y1="16" x2="6.01" y2="16"/><line x1="10" y1="16" x2="10.01" y2="16"/>`,
  activity:`<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>`,
  zap:`<polygon points="13 2 3 14 12 14 11 22 21 10 12 10"/>`,
  link:`<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>`,
  server:`<rect x="2" y="2" width="20" height="8" rx="2"/><rect x="2" y="14" width="20" height="8" rx="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/>`,
};
const MEM_PRESETS = [64,128,256,384,512,768,1024,1536,2048,3072,4096,6144,8192,12288,16384];
const icon = (n,s=16)=>`<svg viewBox="0 0 24 24" width="${s}" height="${s}">${P[n]||""}</svg>`;

/* ---------- 全局状态 ---------- */
const state = {
  token: localStorage.getItem("lxcp_token") || "",
  user: null, meta: null,
  hist: { cpu:[], mem:[], rx:[], tx:[] },   // 面板历史曲线(最多120点)
  ctFilters: { q:"", status:"all" },
  auditQ: "", snapFilter: "",
};
let tickHandle = null, wsRef = null;

async function api(path, { method="GET", body }={}){
  const headers = {};
  if(state.token) headers.Authorization = "Bearer "+state.token;
  if(body !== undefined) headers["Content-Type"] = "application/json";
  const r = await fetch("/api"+path, { method, headers, body: body!==undefined?JSON.stringify(body):undefined });
  if(r.status === 401){ doLogout(); throw new Error("登录已过期"); }
  const data = await r.json().catch(()=>({}));
  if(!r.ok) throw new Error(data.detail || `请求失败(${r.status})`);
  return data;
}

/* ══════════════ 启动 / 登录 ══════════════ */
(async function boot(){
  // 支持 ?token=xxx 快捷登录(用于演示/截图)，用完立即从地址栏移除
  const qp = new URLSearchParams(location.search);
  if(qp.get("token")){ state.token = qp.get("token");                       // 同步内存态
    localStorage.setItem("lxcp_token", state.token); qp.delete("token");
    history.replaceState({}, "", location.pathname + (qp.toString()?"?"+qp:"") + location.hash); }

  try{ state.meta = await api("/meta"); }catch(e){}
  if(state.token){
    try{ state.user = await api("/me"); enterApp(); return; }catch(e){}
  }
  showLogin();
})();

function showLogin(){ $("#login").classList.remove("hidden"); $("#app").classList.add("hidden"); }

$("#login-form").addEventListener("submit", async e=>{
  e.preventDefault();
  const err = $("#login-error"); err.textContent = "";
  try{
    const data = await api("/login", { method:"POST",
      body:{ username:$("#login-user").value.trim(), password:$("#login-pass").value } });
    state.token = data.token; localStorage.setItem("lxcp_token", data.token);
    state.user = await api("/me");
    enterApp();
    toast(`欢迎回来，${data.user.username}`, "ok");
  }catch(ex){ err.textContent = ex.message; }
});

function doLogout(){
  localStorage.removeItem("lxcp_token"); state.token=""; state.user=null;
  clearInterval(tickHandle); closeWS();
  location.hash = "";
  showLogin();
}
$("#btn-logout").addEventListener("click", doLogout);

/* ---------- 浅色 / 深色主题 ---------- */
function chartTheme(){
  const s = getComputedStyle(document.documentElement), g = k => s.getPropertyValue(k).trim();
  return { axis:g("--chart-axis")||"#5b6b85", grid:g("--chart-grid")||"rgba(148,163,184,.15)",
           text:g("--chart-text")||"#e6ebf4", muted:g("--chart-muted")||"#8b98ad" };
}
function applyTheme(t){
  document.documentElement.classList.toggle("light", t==="light");
  const m=$("#ic-moon"), s=$("#ic-sun");           // 月亮=当前深色(点击切浅色)，太阳=当前浅色
  if(m&&s){ m.classList.toggle("hidden",t==="light"); s.classList.toggle("hidden",t!=="light"); }
  const tc=document.querySelector('meta[name="theme-color"]');   // 手机状态栏跟随主题
  if(tc) tc.setAttribute("content", t==="light" ? "#f3f5fa" : "#0b0f17");
}
const initTheme = localStorage.getItem("nexp_theme") ||
  (window.matchMedia && matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark");
applyTheme(initTheme);
$("#btn-theme").addEventListener("click", ()=>{
  const t = document.documentElement.classList.contains("light") ? "dark" : "light";
  localStorage.setItem("nexp_theme", t);
  applyTheme(t);
  if(!$("#app").classList.contains("hidden")) nav();   // 立即重绘当前页(canvas 配色跟随)
});

async function enterApp(){
  $("#login").classList.add("hidden");
  $("#app").classList.remove("hidden");
  $("#who-name").textContent = state.user.username;
  $("#who-role").textContent = state.user.role==="admin" ? "管理员" : "普通用户";
  $("#who-avatar").textContent = state.user.username[0].toUpperCase();
  buildNav();
  window.addEventListener("hashchange", nav);
  updateNodeBadge(); setInterval(updateNodeBadge, 12000);
  nav();
}

async function updateNodeBadge(){
  const b = $("#mode-badge");
  try{
    const list = await api("/nodes");
    const online = list.filter(n=>n.status==="online"||n.status==="nolxc").length;
    if(!list.length){ b.textContent = "⊕ 尚未接入服务器节点"; b.classList.add("demo"); return; }
    b.classList.remove("demo");
    b.innerHTML = `<span style="color:${online?'var(--ok)':'var(--err)'}">●</span> ${online}/${list.length} 节点在线`;
  }catch(e){}
}

/* ══════════════ 导航 ══════════════ */
const NAV = [
  { id:"dashboard", label:"概览",     icon:"grid",    title:"资源概览" },
  { id:"nodes",     label:"节点管理", icon:"server",  title:"服务器节点" },
  { id:"containers",label:"容器实例", icon:"box",     title:"容器实例管理" },
  { id:"apps",      label:"一键部署", icon:"zap",     title:"应用一键部署" },
  { id:"templates", label:"镜像模板", icon:"layers",  title:"系统模板库" },
  { id:"snapshots", label:"快照备份", icon:"camera",  title:"快照与回滚" },
  { id:"network",   label:"网络拓扑", icon:"globe",   title:"网络与 IP 分配" },
  { id:"traffic",   label:"流量统计", icon:"activity",title:"节点流量统计" },
  { id:"probes",    label:"主机探针", icon:"activity",title:"探针监控" },
  { id:"users",     label:"用户管理", icon:"users",   title:"用户与权限" },
  { id:"audit",     label:"审计日志", icon:"file",    title:"操作审计日志" },
  { id:"settings",  label:"系统设置", icon:"sliders", title:"系统设置" },
];

function buildNav(){
  $("#nav").innerHTML = NAV.map(n=>
    `<div class="nav-item" data-id="${n.id}" onclick="location.hash='${n.id}'">
       ${icon(n.icon)}<span class="lbl">${n.label}</span></div>`).join("");
}

function nav(){
  clearInterval(tickHandle); closeWS();
  const id = location.hash.slice(1) || "dashboard";
  const item = NAV.find(n=>n.id===id) || NAV[0];
  $$(".nav-item").forEach(el=>el.classList.toggle("active", el.dataset.id===item.id));
  $("#page-title").textContent = item.title;
  const fn = { dashboard:viewDashboard, nodes:viewNodes, containers:viewContainers,
    apps:viewApps, probes:viewProbes, templates:viewTemplates,
    snapshots:viewSnapshots, network:viewNetwork, traffic:viewTraffic,
    users:viewUsers, audit:viewAudit,
    settings:viewSettings }[item.id];
  (fn || viewDashboard)();
}
window.nav = nav;

/* ══════════════ Canvas 图表 ══════════════ */
function setupCanvas(c){
  const r = window.devicePixelRatio || 1;
  const w = c.clientWidth, h = c.clientHeight;
  c.width = w*r; c.height = h*r;
  const ctx = c.getContext("2d");
  ctx.setTransform(r,0,0,r,0,0);
  return { ctx, w, h };
}
function lineChart(canvas, series, opt={}){
  if(!canvas || !canvas.clientWidth) return;
  const { ctx, w, h } = setupCanvas(canvas);
  ctx.clearRect(0,0,w,h);
  const padL=38, padR=10, padT=12, padB=20, iw=w-padL-padR, ih=h-padT-padB;
  let max = opt.max;
  if(!max){
    max = Math.max(10, ...series.flatMap(s=>s.data)) * 1.15;
    if(max < 1) max = 1;
  }
  const T = chartTheme();
  ctx.font = "10px ui-monospace"; ctx.fillStyle=T.axis; ctx.strokeStyle=T.grid;
  for(let i=0;i<=4;i++){
    const y = padT + ih*i/4;
    ctx.beginPath(); ctx.moveTo(padL,y); ctx.lineTo(w-padR,y); ctx.stroke();
    ctx.textAlign="left"; ctx.fillText(fmtNum(max*(1-i/4)), 4, y+3);
    if(opt.xLabels && i%2===0){
      const idx = Math.round((i/4)*(opt.xLabels.length-1));
      ctx.textAlign="center";
      ctx.fillText(opt.xLabels[idx]||"", padL+iw*i/4, h-6);
    }
  }
  for(const s of series){
    if(s.data.length < 2) continue;
    const pts = s.data.map((v,i)=>[padL + iw*i/(s.data.length-1), padT + ih*(1-Math.min(v,max)/max)]);
    if(opt.fill!==false){
      const g = ctx.createLinearGradient(0,padT,0,padT+ih);
      g.addColorStop(0, s.color+"33"); g.addColorStop(1, s.color+"00");
      ctx.beginPath(); ctx.moveTo(pts[0][0], padT+ih);
      pts.forEach(p=>ctx.lineTo(p[0],p[1]));
      ctx.lineTo(pts.at(-1)[0], padT+ih); ctx.closePath();
      ctx.fillStyle=g; ctx.fill();
    }
    ctx.strokeStyle=s.color; ctx.lineWidth=1.8; ctx.lineJoin="round"; ctx.beginPath();
    pts.forEach((p,i)=> i?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1])); ctx.stroke();
  }
}
function gauge(canvas, pct, color){
  if(!canvas || !canvas.clientWidth) return;
  pct = Math.max(0, Math.min(100, pct));
  const { ctx } = setupCanvas(canvas);
  const w = canvas.clientWidth, h = canvas.clientHeight;
  ctx.clearRect(0,0,w,h);
  const cx=w/2, cy=h/2, r=Math.min(w,h)/2-7;
  ctx.lineWidth=8; ctx.lineCap="round";
  const T = chartTheme();
  ctx.strokeStyle=T.grid;
  ctx.beginPath(); ctx.arc(cx,cy,r,0,Math.PI*2); ctx.stroke();
  ctx.strokeStyle=color;
  ctx.beginPath(); ctx.arc(cx,cy,r,-Math.PI/2,-Math.PI/2+Math.PI*2*pct/100); ctx.stroke();
  ctx.fillStyle=T.text; ctx.font="600 17px system-ui"; ctx.textAlign="center";
  ctx.fillText(pct.toFixed(1)+"%", cx, cy+1);
  ctx.fillStyle=T.muted; ctx.font="10.5px system-ui";
  ctx.fillText(canvas.dataset.label||"", cx, cy+18);
}

/* ══════════════ 视图：概览(多节点聚合) ══════════════ */
function viewDashboard(){
  $("#content").innerHTML = `
  <div class="grid stat-grid">
    <div class="card gauge-row"><div class="gauge-box"><canvas id="g-cpu" data-label="CPU 均值"></canvas></div>
      <div style="text-align:center;color:var(--muted);font-size:12px;margin-top:6px">全部在线节点</div></div>
    <div class="card gauge-row"><div class="gauge-box"><canvas id="g-mem" data-label="内存使用率"></canvas></div>
      <div style="text-align:center;color:var(--muted);font-size:12px;margin-top:6px">节点内存合计</div></div>
    <div class="card gauge-row"><div class="gauge-box"><canvas id="g-disk" data-label="磁盘使用率"></canvas></div>
      <div style="text-align:center;color:var(--muted);font-size:12px;margin-top:6px">根分区合计</div></div>
    <div class="card">
      <h4><span class="dot"></span>实例概览</h4>
      <div class="kv" style="margin-top:4px">
        <dt>运行中</dt><dd id="ov-run">—</dd>
        <dt>已停止</dt><dd id="ov-stop">—</dd>
        <dt>实例总数</dt><dd id="ov-total">—</dd>
        <dt>在线节点</dt><dd id="ov-nodes">—</dd>
      </div>
    </div>
  </div>

  <div class="card" style="margin-top:16px">
    <h4><span class="dot"></span>节点资源
      <button class="btn sm ghost" style="margin-left:auto" onclick="location.hash='nodes'">${icon("server",13)} 管理节点</button></h4>
    <div class="grid tpl-grid" id="dash-nodes"><div class="empty">加载中…</div></div>
  </div>

  <div class="cols-2-1" style="margin-top:16px">
    <div class="card">
      <h4><span class="dot"></span>负载趋势（全部节点均值）<span class="tag" style="margin-left:auto">每 2.5s 刷新</span></h4>
      <div class="chart-box"><canvas id="chart-main"></canvas></div>
      <div class="legend">
        <span><b style="background:#6366f1"></b>CPU %</span>
        <span><b style="background:#22d3ee"></b>内存 %</span>
      </div>
    </div>
    <div class="card">
      <h4><span class="dot"></span>面板信息</h4>
      <dl class="kv" style="margin-top:4px">
        <dt>面板版本</dt><dd>NexPanel ${esc(state.meta?.version||"")}</dd>
        <dt>架构模式</dt><dd>中心面板 · SSH 多节点</dd>
        <dt>接入节点</dt><dd id="hi-nodes">—</dd>
        <dt>登录账号</dt><dd>${esc(state.user?.username||"-")}（${state.user?.role==="admin"?"管理员":"普通用户"}）</dd>
        <dt>数据库</dt><dd>SQLite</dd>
      </dl>
    </div>
  </div>

  <div class="grid stat-grid" style="grid-template-columns:1.35fr 1fr;margin-top:16px">
    <div class="card">
      <h4><span class="dot"></span>CPU 占用 TOP 5</h4>
      <div class="table-wrap"><table><thead><tr>
        <th>实例</th><th>节点</th><th>状态</th><th style="width:32%">CPU 占用</th><th>内存</th></tr></thead>
        <tbody id="top-body"></tbody></table></div>
    </div>
    <div class="card">
      <h4><span class="dot"></span>最近动态</h4>
      <div class="table-wrap"><table><tbody id="recent-body"></tbody></table></div>
    </div>
  </div>`;

  const tick = async ()=>{
    try{
      const o = await api("/overview");
      const a = o.agg;
      const memPct = a.mem_total_mb ? a.mem_used_mb/a.mem_total_mb*100 : 0;
      const diskPct = a.disk_total_gb ? a.disk_used_gb/a.disk_total_gb*100 : 0;

      gauge($("#g-cpu"), a.cpu_pct, barColor(a.cpu_pct));
      gauge($("#g-mem"), memPct, barColor(memPct));
      gauge($("#g-disk"), diskPct, barColor(diskPct));

      $("#ov-run").innerHTML   = `<b style="color:var(--ok)">${o.counts.running}</b>`;
      $("#ov-stop").innerHTML  = `<b style="color:var(--muted)">${o.counts.stopped}</b>`;
      $("#ov-total").innerHTML = `<b>${o.counts.total}</b>`;
      $("#ov-nodes").innerHTML = `<b>${a.nodes_online}/${a.nodes_total}</b>`;
      $("#hi-nodes").textContent = `${a.nodes_online} 在线 / 共 ${a.nodes_total}`;

      const H = state.hist, push=(arr,v,n=120)=>{ arr.push(v); if(arr.length>n)arr.shift(); };
      push(H.cpu, a.cpu_pct); push(H.mem, memPct);
      lineChart($("#chart-main"), [
        { color:"#6366f1", data:H.cpu }, { color:"#22d3ee", data:H.mem }], { max:100 });

      // 节点卡片
      const NS = {online:["var(--ok)","在线"],nolxc:["var(--warn)","未装LXC"],
                  offline:["var(--err)","离线"],unknown:["var(--muted)","待探测"]};
      $("#dash-nodes").innerHTML = o.nodes_summary.map(n=>{
        const [c,lbl] = NS[n.status]||NS.unknown;
        const L=n.live, memP=L.mem_total_mb?L.mem_used_mb/L.mem_total_mb*100:0,
              diskP=L.disk_total_gb?L.disk_used_gb/L.disk_total_gb*100:0;
        return `<div class="card tpl-card" style="cursor:pointer" onclick="location.hash='nodes'">
          <div class="stripe" style="background:${c}"></div>
          <div class="tpl-head">
            <span class="tpl-logo" style="width:36px;height:36px;font-size:14px;background:#334155">${icon("server",15)}</span>
            <div><b>${esc(n.name)}</b>
              <div style="font-size:11px;color:var(--muted)" class="mono">${esc(n.os_info||n.host_addr||n.kind)}</div></div>
            <span class="badge" style="margin-left:auto"><span class="dot" style="background:${c};animation:none"></span>${lbl}</span>
          </div>
          ${miniBar("CPU", L.cpu_pct)}
          ${miniBar("内存", memP, fmtGB(L.mem_used_mb)+" / "+fmtGB(L.mem_total_mb))}
          ${miniBar("磁盘", diskP, L.disk_used_gb+"G / "+L.disk_total_gb+"G")}
          <div style="display:flex;gap:8px;margin-top:10px">
            <span class="tag">${n.counts.total} 台实例</span>
            <span class="tag" style="color:${n.counts.running?'var(--ok-strong)':'inherit'}">${n.counts.running} 运行中</span>
          </div>
        </div>`;
      }).join("") || `<div class="empty" style="grid-column:1/-1">
        还没有接入任何服务器 — <a href="#nodes" style="cursor:pointer">去添加节点 →</a></div>`;

      $("#top-body").innerHTML = o.top.map(t=>`
        <tr><td><b>${esc(t.name)}</b></td>
        <td><span class="tag">${esc(t.node)}</span></td>
        <td><span class="badge ${t.status}"><span class="dot"></span>${t.status==="running"?"运行中":"已停止"}</span></td>
        <td><div style="display:flex;align-items:center;gap:10px">
          <div class="bar" style="flex:1"><i style="width:${Math.min(t.cpu_pct,100)}%;background:${barColor(t.cpu_pct)}"></i></div>
          <span class="mono" style="width:52px;text-align:right">${t.cpu_pct.toFixed(1)}%</span></div></td>
        <td class="mono">${t.mem_used_mb?fmtGB(t.mem_used_mb)+" / "+fmtGB(t.mem_mb):"—"}</td></tr>`).join("")
        || `<tr><td colspan="5" class="empty">暂无数据</td></tr>`;
    }catch(e){}
  };
  loadRecentAudit();
  tick(); tickHandle = setInterval(tick, 2500);
}

function miniBar(label, pct, right){
  pct = Math.max(0, Math.min(100, pct||0));
  return `<div style="display:flex;align-items:center;gap:9px;margin-top:7px;font-size:11.5px;color:var(--muted)">
    <span style="width:30px">${label}</span>
    <div class="bar" style="flex:1"><i style="width:${pct}%;background:${barColor(pct)}"></i></div>
    ${right?`<span class="mono" style="min-width:86px;text-align:right">${right}</span>`
           :`<span class="mono" style="width:44px;text-align:right">${pct.toFixed(0)}%</span>`}
  </div>`;
}

async function loadRecentAudit(){
  try{
    const logs = await api("/audit?limit=6");
    $("#recent-body").innerHTML = logs.map(a=>`
      <tr><td style="white-space:normal">
        <div><b>${esc(a.action)}</b>
        ${a.target&&a.target!=="system"?`<span class="tag">${esc(a.target)}</span>`:""}</div>
        <div style="color:var(--muted);font-size:11.5px">${esc(a.created_at)} · ${esc(a.username||"-")}</div>
      </td></tr>`).join("") || `<tr><td class="empty">暂无记录</td></tr>`;
  }catch(e){}
}

/* ══════════════ 视图：节点管理 ══════════════ */
const NODE_ST = {
  online:  ["var(--ok)",   "在线"],
  nolxc:   ["var(--warn)", "未装 LXC"],
  offline: ["var(--err)",  "离线"],
  unknown:  ["var(--muted)",  "待探测"],
};
async function viewNodes(){
  $("#content").innerHTML = `
  <div class="page-head">
    <span class="sub">面板通过 SSH 接入任意服务器并管理其上的 LXC，面板自身无需安装 LXC</span>
    <span class="spacer"></span>
    <button class="btn primary" id="btn-add-node">${icon("plus")} 接入服务器</button>
  </div>
  <div class="grid tpl-grid" id="node-grid"><div class="empty">加载中…</div></div>`;

  const render = async ()=>{
    try{
      const list = await api("/nodes");
      $("#node-grid").innerHTML = list.map((n,i)=>{
        const isProbe = n.role==="probe";
        // SSH 节点不要求装 LXC，nolxc 直接按“在线”显示
        const rawSt = n.status;
        const st = (n.kind==="ssh" && rawSt==="nolxc") ? "online" : rawSt;
        const [c,lbl] = NODE_ST[st]||NODE_ST.unknown;
        const L=n.live, memP=L.mem_total_mb?L.mem_used_mb/L.mem_total_mb*100:0,
              diskP=L.disk_total_gb?L.disk_used_gb/L.disk_total_gb*100:0;
        return `<div class="card tpl-card">
          <div class="stripe" style="background:${c}"></div>
          <div class="tpl-head">
            <span class="tpl-logo" style="background:#334155">${icon(isProbe?"activity":"server",17)}</span>
            <div><b>${esc(n.name)}</b>
              <div class="mono" style="font-size:11px;color:var(--muted)">
                ${n.kind==="demo"?"🎮 演示节点":n.kind==="agent"?(isProbe?"📡 探针 · ":"⚡ Agent · ")+esc(n.os_info||"等待接入"):esc(n.username+"@"+n.host+":"+n.port)}</div></div>
            <span class="badge" style="margin-left:auto"><span class="dot" style="background:${c};animation:none"></span>${lbl}</span>
          </div>
          ${isProbe ? `
            <div class="lat-row">${Object.entries(n.latency||{}).map(([k,v])=>
              `<span class="tag" style="color:${v==null?"var(--err)":"var(--ok-strong)"}">${k} ${v==null?"×":v+"ms"}</span>`).join("") || '<span class="tag">延迟采集中…</span>'}</div>`
          : `<div style="font-size:12px;color:var(--muted);margin-bottom:10px" class="mono">
              ${esc(n.os_info || (n.error?n.error.slice(0,60):"—"))}</div>`}
          ${n.public_ip?`<div class="mono" style="font-size:11.5px;color:var(--muted);margin-bottom:8px">🌐 ${esc(n.public_ip)}</div>`:""}
          ${miniBar("CPU", L.cpu_pct)}
          ${isProbe ? miniBar("内存", memP, fmtGB(L.mem_used_mb)+" / "+fmtGB(L.mem_total_mb))
                    : miniBar("内存", memP, fmtGB(L.mem_used_mb)+" / "+fmtGB(L.mem_total_mb))}
          ${miniBar("磁盘", diskP, L.disk_used_gb+"G / "+L.disk_total_gb+"G")}
          <div style="display:flex;gap:8px;margin-top:10px;flex-wrap:wrap">
            <span class="tag">↑${fmtUp(L.uptime_s||0)}</span>
            ${!isProbe?`<span class="tag">${n.counts.total} 台实例</span>
            <span class="tag" style="color:${n.counts.running?'var(--ok-strong)':'inherit'}">${n.counts.running} 运行</span>
            ${n.install_lxc||n.lxc_ok?`<span class="tag" style="color:var(--accent-2)">🖥 母机</span>`:""}
            ${n.kind==="agent"&&!n.lxc_ok&&n.status==="online"?`<button class="btn sm primary" data-install="${n.id}">⚡ 安装 LXC</button>`:""}`:""}
          </div>
          <div class="actions-cell" style="margin-top:12px">
            <button class="btn sm" data-move="${i}" data-dir="-1" title="上移">↑</button>
            <button class="btn sm" data-move="${i}" data-dir="1" title="下移">↓</button>
            <button class="btn sm" data-probe="${n.id}">${icon("activity",12)} 测试</button>
            <button class="btn sm" data-rename="${n.id}" data-name="${esc(n.name)}" title="重命名节点">✏️ 重命名</button>
            ${n.kind==="agent"?`<button class="btn sm" data-agent-cmd="${n.id}" title="查看接入命令">${icon("term",12)} 接入</button>`:""}
            ${(n.kind==="ssh"||n.kind==="agent")&&(n.status==="online"||n.status==="nolxc")?`<button class="btn sm" data-term="${n.id}" data-name="${esc(n.name)}" title="母机控制台">${icon("server",12)} 终端</button>`:""}
            ${n.kind==="demo"?`<button class="btn sm" data-term="${n.id}" data-name="${esc(n.name)}" title="演示控制台">${icon("server",12)} 终端</button>`:""}
            ${(n.kind==="agent"||n.kind==="ssh")&&!isProbe?`<button class="btn sm" data-import-lxc="${n.id}" title="把宿主机已有的 LXC 容器导入面板">${icon("server",12)} 导入LXC</button>`:""}
            ${(n.kind==="agent"||n.kind==="ssh")&&!isProbe?`<button class="btn sm" data-swap="${n.id}" title="管理宿主机 Swap（给 LXC 小鸡提供内存补充）">${icon("activity",12)} Swap</button>`:""}
            ${n.kind==="agent"?`<button class="btn sm" data-uninst="${n.id}" title="生成一键清理命令">${icon("trash",12)} 卸载</button>`:""}
            <button class="btn sm danger" data-del="${n.id}" data-name="${esc(n.name)}">${icon("trash",12)} 删除</button>
          </div>
        </div>`;
      }).join("") || `<div class="empty" style="grid-column:1/-1;padding:60px 0">
        <p style="font-size:15px;margin-bottom:8px">还没有接入任何服务器</p>
        <p>点击右上角「接入服务器」，Agent 一行命令即可接管 VPS（支持 NAT），或添加仅监控探针</p></div>`;

      $$("#node-grid [data-probe]").forEach(b=>b.onclick=async()=>{
        b.disabled=true; b.textContent="测试中…";
        try{ const r=await api(`/nodes/${b.dataset.probe}/probe`,{method:"POST"});
          toast(`✓ ${r.hostname||""} · ${r.os} · LXC ${r.lxc_installed?("已安装 "+(r.lxc_version||"")):"未安装"}`,"ok",4200);
        }catch(e){ toast(e.message,"err",4200); }
        render();
      });
      $$("#node-grid [data-move]").forEach(b=>b.onclick=async()=>{
        const idx = +b.dataset.move, dir = +b.dataset.dir;
        const nodes = await api("/nodes");
        const newIdx = idx + dir;
        if(newIdx < 0 || newIdx >= nodes.length) return;
        const ids = nodes.map(x=>x.id);
        [ids[idx], ids[newIdx]] = [ids[newIdx], ids[idx]];
        try{ await api("/nodes/reorder",{method:"POST",body:{ids}}); render(); }
        catch(e){ toast(e.message,"err"); }
      });
      $$("#node-grid [data-rename]").forEach(b=>b.onclick=()=>renameNode(+b.dataset.rename, b.dataset.name));
      $$("#node-grid [data-del]").forEach(b=>b.onclick=()=>deleteNode(+b.dataset.del,b.dataset.name));
      $$("#node-grid [data-agent-cmd]").forEach(b=>b.onclick=async()=>{
        const n = (await api("/nodes")).find(x=>String(x.id)===b.dataset.agentCmd);
        if(!n?.install_cmd){ toast("未生成安装命令","err"); return; }
        showAgentCmdModal(n);
      });
      $$("#node-grid [data-uninst]").forEach(b=>b.onclick=async()=>{
        const n = (await api("/nodes")).find(x=>String(x.id)===b.dataset.uninst);
        if(!n){ toast("节点不存在","err"); return; }
        showUninstallModal(n);
      });
      $$("#node-grid [data-term]").forEach(b=>b.onclick=()=>openNodeTerminal(+b.dataset.term, b.dataset.name));
      $$("#node-grid [data-import-lxc]").forEach(b=>b.onclick=async()=>{
        if(!(await confirmModal("从宿主机扫描并导入已有 LXC 容器？已存在的容器不会重复导入。", true))) return;
        b.disabled=true; b.textContent="导入中…";
        try{
          const r = await api(`/nodes/${b.dataset.importLxc}/import-lxc`,{method:"POST"});
          toast(`已导入 ${r.imported} 个容器`,"ok",4000); render();
        }catch(e){ toast(e.message,"err"); }
        b.disabled=false; b.textContent="导入LXC";
      });
      $$("#node-grid [data-install]").forEach(b=>b.onclick=async()=>{
        b.disabled=true; b.textContent="安装中…";
        toast("正在通过 SSH 安装 LXC，可能需要几分钟…","info",6000);
        try{ const r=await api(`/nodes/${b.dataset.install}/install`,{method:"POST"});
          toast(r.output.split("\n")[0],"ok",5000); }catch(e){ toast(String(e.message).slice(0,120),"err",5000); }
        render();
      });
      $$("#node-grid [data-swap]").forEach(b=>b.onclick=()=>openSwapModal(+b.dataset.swap));
    }catch(e){ $("#node-grid").innerHTML=`<div class="empty">${esc(e.message)}</div>`; }
  };

  $("#btn-add-node").onclick = openNodeModal;
  render();
  tickHandle = setInterval(render, 5000);
}

window.openSwapModal = async function(nid){
  let nodeName = "节点";
  try{ nodeName = (await api("/nodes")).find(n=>+n.id===+nid)?.name || "节点"; }catch(e){}
  let status = {total_mb:0, used_mb:0, swappiness:60, files:[], raw:""};
  try{ status = await api(`/nodes/${nid}/swap`); }catch(e){}

  const ov = openModal(`💾 Swap 管理 — <b>${esc(nodeName)}</b>`, `
    <p style="color:var(--muted);font-size:12.5px;line-height:1.7;margin-bottom:12px">
      在宿主机上创建 swap 文件，给 LXC 小鸡提供内存补充。<br>
      创建后还需在「容器实例 → 编辑配置 → Swap MB」中给具体容器分配 swap。</p>
    <dl class="kv" style="margin-bottom:12px">
      <dt>当前 Swap</dt><dd>${status.total_mb? fmtGB(status.total_mb)+" / 已用 "+fmtGB(status.used_mb) : "未启用"}</dd>
      <dt>Swappiness</dt><dd>${status.swappiness}</dd>
      ${status.files.map(f=>`<dt>${esc(f.path)}</dt><dd>${esc(f.size)}</dd>`).join("")}
    </dl>
    <div class="form-grid" style="grid-template-columns:1fr">
      <label>创建 Swap 大小（GB）<input id="sw-size" type="number" min="1" max="64" value="1"></label>
    </div>
    <div style="display:flex;gap:8px;margin-top:12px">
      <button class="btn primary" id="sw-create">创建/扩容</button>
      <button class="btn danger" id="sw-delete">删除 Swap</button>
    </div>
    <pre class="term" style="margin-top:12px;height:auto;max-height:160px;font-size:11px;white-space:pre-wrap" id="sw-out">${esc(status.raw||"暂无输出")}</pre>`,
    ()=>closeModal(), "关闭");

  $("#sw-create").onclick = async ()=>{
    const size = parseInt($("#sw-size").value)||1;
    if(size < 1 || size > 64) return toast("Swap 大小需在 1-64 GB 之间","err");
    if(!(await confirmModal(`确定在宿主机创建/扩容为 <b>${size}GB</b> swap 文件？会占用磁盘空间。`, true))) return;
    const btn = $("#sw-create"); const delBtn = $("#sw-delete");
    btn.disabled=true; btn.textContent="⏳ 创建中…"; delBtn.disabled=true;
    const outBox = $("#sw-out");
    outBox.textContent = "正在执行创建 Swap 操作…\n如果节点 IO 繁忙（Agent 正在创建 swap），可能需要几分钟，请耐心等待。";
    try{
      const r = await api(`/nodes/${nid}/swap`, {method:"POST", body:{size_gb:size}});
      outBox.textContent = r.output || "完成";
      toast("Swap 创建成功","ok",5000);
    }catch(e){
      outBox.textContent = "❌ 创建失败：\n" + e.message;
      toast(e.message,"err",6000);
    }
    btn.disabled=false; btn.textContent="重新创建/扩容";
    delBtn.disabled=false;
  };

  $("#sw-delete").onclick = async ()=>{
    if(!(await confirmModal("确定删除宿主机 swap 文件？已配置使用 swap 的容器将失去 swap 补充。", true))) return;
    const btn = $("#sw-delete"); const createBtn = $("#sw-create");
    btn.disabled=true; btn.textContent="⏳ 删除中…"; createBtn.disabled=true;
    const outBox = $("#sw-out");
    outBox.textContent = "正在删除 Swap…";
    try{
      const r = await api(`/nodes/${nid}/swap`, {method:"DELETE"});
      outBox.textContent = r.output || "完成";
      toast("Swap 已删除","ok",5000);
    }catch(e){
      outBox.textContent = "❌ 删除失败：\n" + e.message;
      toast(e.message,"err",6000);
    }
    btn.disabled=false; btn.textContent="删除 Swap";
    createBtn.disabled=false;
  };
};

window.renameNode = async function(id, oldName){
  const ov = openModal(`重命名节点`, `
    <label>新名称 *
      <input id="rn-name" value="${esc(oldName)}" style="margin-top:8px" autocomplete="off">
    </label>`,
    async ()=>{
      const nn = $("#rn-name").value.trim();
      if(!nn || nn.length<2 || nn.length>32) return toast("名称需 2-32 个字符","err");
      try{
        await api(`/nodes/${id}`, {method:"PUT", body:{name: nn}});
        closeModal(); toast("节点已重命名","ok"); viewNodes();
      }catch(e){ toast(e.message,"err"); }
    }, "保存");
};

window.deleteNode = async function(id, name){
  let node = null;
  try{ node = (await api("/nodes")).find(x=>+x.id===+id); }catch(e){}
  const isAgent = node && node.kind === "agent";
  const base = location.origin;
  const ucmd = (node && node.uninstall_cmd) || `curl -fsSL ${base}/api/agent/uninstall.sh | sh`;
  const extra = isAgent ? `
    <p style="color:var(--muted);font-size:12px;line-height:1.8;margin-top:10px">
      若还要清理目标机上的 Agent/探针程序，请先在目标服务器以 root 执行：</p>
    <div class="term" style="height:auto;padding:10px;user-select:all;word-break:break-all" id="del-uninst-cmd">${esc(ucmd)}</div>
    <button class="btn sm block" style="margin-top:8px" onclick="copyText(document.getElementById('del-uninst-cmd').textContent)">📋 复制清理命令</button>` : "";
  const ok = await confirmModal(
    `确定删除节点 <b>${esc(name)}</b>？其下实例将被一并删除。<span style="color:var(--muted);font-size:12px">（仅移除面板记录，不改变目标机上的程序）</span>${extra}`,
    true);
  if(!ok) return;
  try{
    await api(`/nodes/${id}`, {method:"DELETE"});       // 先尝试普通删除
    toast(isAgent?"节点已删除。如需彻底清除目标机程序，请执行上方清理命令":"节点已删除","ok",isAgent?6000:3000); viewNodes();
  }catch(e){
    if(String(e.message).includes("强制删除")){
      if(await confirmModal("该节点下仍有实例，确认<b>连同全部实例一起删除</b>？",true)){
        try{ await api(`/nodes/${id}?force=1`,{method:"DELETE"}); toast("节点及实例已删除","ok"); viewNodes(); }
        catch(e2){ toast(e2.message,"err"); }
      }
    } else toast(e.message,"err");
  }
};

function openNodeModal(){
  openModal("接入服务器", `
    <div class="form-grid">
      <label>节点名称 *<input id="n-name" placeholder="如 node-shanghai"></label>
      <label>接入方式 *
        <select id="n-kind">
          <option value="agent">⚡ Agent 接管（推荐·可装LXC/下发）</option>
          <option value="probe">📡 仅监控探针（只看负载）</option>
          <option value="ssh">SSH 远程（免安装）</option>
          <option value="demo">演示节点</option>
        </select></label>
      <label class="full check-line" id="wrap-lxc" style="display:none">
        <input type="checkbox" id="n-lxc" style="accent-color:var(--accent)">
        作为母机（接入后自动安装 LXC，用于创建/管理容器；不勾选则仅用于下发部署节点）
      </label>
      <div id="ssh-only" class="full hidden" style="display:contents">
        <label>主机地址 / 端口 *
          <div style="display:flex;gap:8px">
            <input id="n-host" placeholder="IP 或域名" style="flex:1">
            <input id="n-port" type="number" value="22" min="1" max="65535" style="width:88px">
          </div></label>
        <label>SSH 用户名 *<input id="n-user" value="root"></label>
        <label>认证方式 *
          <select id="n-auth"><option value="password">密码</option><option value="key">私钥</option></select></label>
        <label class="full" id="lbl-secret">密码 *<input id="n-secret" type="password"></label>
        <label class="full hidden" id="lbl-key">私钥（PEM）*
          <textarea id="n-keytext" rows="5" class="input mono"
            style="resize:vertical;font-family:var(--mono);font-size:11.5px"></textarea></label>
      </div>
      <p class="sub full" style="color:var(--muted);font-size:12px;line-height:1.7" id="kind-hint">
        Agent 反向连接面板，支持 NAT 后的 VPS；接入后可一键安装 LXC、下发容器/主机应用、实时查看负载。</p>
    </div>`,
    async ()=>{
      const kind=$("#n-kind").value;
      const role = kind==="probe" ? "probe" : "manage";
      const body={ name:$("#n-name").value.trim(), kind, role,
        install_lxc: (kind==="agent"||kind==="ssh") && $("#n-lxc").checked };
      if(kind==="ssh"){
        Object.assign(body,{ host:$("#n-host").value.trim(), port:+$("#n-port").value||22,
          username:$("#n-user").value.trim()||"root", auth_type:$("#n-auth").value });
        body.secret = body.auth_type==="key" ? $("#n-keytext").value.trim()
                                             : $("#n-secret").value;
        if(!body.host) return toast("请填写主机地址","err");
        if(!body.secret) return toast("请填写密码或私钥","err");
      }
      try{
        if(kind==="ssh"){
          toast("正在测试连接…","info");
          await api("/nodes/test",{method:"POST",body});
        }
        const created = await api("/nodes",{method:"POST",body});
        closeModal();
        viewNodes();
        if(created.agent_token){
          showAgentCmdModal(created);           // 自动弹出安装命令
        } else toast(`节点 ${created.name} 已添加`,"ok");
      }catch(e){ toast(String(e.message).slice(0,150),"err",4500); }
    }, "下一步");
  const kindSel=$("#n-kind"), authSel=$("#n-auth");
  const HINTS={
    agent:"Agent 反向连接面板，支持 NAT 后的 VPS；不装 LXC 也能向主机直接下发部署节点，勾选“作为母机”才会自动安装 LXC。支持 Debian/Ubuntu/CentOS/Rocky/Alpine。",
    probe:"轻量探针模式：只上报 CPU/内存/磁盘/负载/网络延迟，用于纯监控场景。不提供任何管理能力。",
    ssh:"传统 SSH 方式：面板通过用户名密码/私钥远程执行命令，无需在目标机安装任何东西。",
    demo:"虚拟演示节点：无需真实服务器，用于体验面板全部功能。"};
  const syncUI=()=>{
    const k=kindSel.value;
    // 必须同时移除 hidden class，否则 CSS .hidden[style*="contents"] 会强制隐藏
    $("#ssh-only").classList.toggle("hidden", k!=="ssh");
    $("#ssh-only").style.display = k==="ssh" ? "contents" : "none";
    $("#wrap-lxc").style.display = (k==="agent"||k==="ssh") ? "" : "none";
    if(k==="probe"||k==="demo") $("#n-lxc").checked = false;
    $("#kind-hint").textContent = HINTS[k]||"";
  };
  kindSel.onchange=syncUI; authSel.onchange=syncUI; syncUI();
}

function showAgentCmdModal(node){
  const base = location.origin;
  const cmd = node.install_cmd ||
    `curl -fsSL ${base}/api/agent/install.sh | sh -s -- --api ${base} --token ${node.agent_token}`;
  const ov = openModal(`⚡ 接入 <b>${esc(node.name)}</b> — 在目标 VPS 执行`, `
    <p style="color:var(--muted);font-size:12.5px;line-height:1.7;margin-bottom:10px">
      SSH 登录目标 VPS，以 root 运行以下<b>一行命令</b>（需 curl）。执行完成后本节点将自动上线，
      支持一键安装 LXC、下发应用到容器/主机、实时负载监控。</p>
    <div class="term" style="height:auto;padding:14px;user-select:all;word-break:break-all" id="agent-cmd-box">${esc(cmd)}</div>
    <button class="btn primary block" style="margin-top:12px" onclick="copyText(document.getElementById('agent-cmd-box').textContent)">📋 复制命令</button>
    <p style="color:var(--muted);font-size:11.5px;margin-top:10px;line-height:1.7">
      · Agent 每 3 秒心跳上报，Token 可随时轮换吊销<br>
      · 支持 Debian/Ubuntu/CentOS/Rocky/Alpine 等主流系统<br>
      · 接入后可在节点卡片「⚡ 安装 LXC」给母鸡装上 LXC 管理能力</p>`,
    null, "", {wide:true});
  ov.querySelector(".modal-foot").remove();
}

/* ── Agent / 探针 一键清理命令 ── */
window.showUninstallModal = function(node){
  const base = location.origin;
  const cmd = node.uninstall_cmd || `curl -fsSL ${base}/api/agent/uninstall.sh | sh`;
  const ov = openModal(`🧹 清理 Agent/探针 — <b>${esc(node.name)}</b>`, `
    <p style="color:var(--muted);font-size:12.5px;line-height:1.7;margin-bottom:10px">
      SSH 登录目标服务器，以 root 运行以下<b>一行命令</b>，即可停止并彻底清除面板部署在该机器上的
      Agent / 探针（停止服务 → 删除 systemd 单元 → 删除程序目录）：</p>
    <div class="term" style="height:auto;padding:14px;user-select:all;word-break:break-all" id="uninst-cmd-box">${esc(cmd)}</div>
    <button class="btn primary block" style="margin-top:12px" onclick="copyText(document.getElementById('uninst-cmd-box').textContent)">📋 复制清理命令</button>
    <p style="color:var(--muted);font-size:11.5px;margin-top:10px;line-height:1.7">
      · 仅移除目标机上的 lxcdeck-agent，不影响系统其他部分<br>
      · 执行后节点转为离线，随后可在面板中删除该节点记录<br>
      · 探针与 Agent 为同一程序，清理命令相同</p>`,
    null, "", {wide:true});
  ov.querySelector(".modal-foot").remove();
};

/* ══════════════ 视图：容器实例 ══════════════ */
const DISTRO_META = {
  ubuntu:{ name:"Ubuntu", bg:"#E95420" }, debian:{ name:"Debian", bg:"#A81D33" },
  alpine:{ name:"Alpine", bg:"#0D597F" }, rocky:{  name:"Rocky",  bg:"#10B981" },
  centos:{ name:"CentOS", bg:"#9333EA" }, fedora:{ name:"Fedora", bg:"#294172" },
  arch:{   name:"Arch",   bg:"#1793D1" },
};

function viewContainers(){
  $("#content").innerHTML = `
  <div class="page-head">
    <button class="btn primary" id="btn-create">${icon("plus")} 创建实例</button>
    <select class="select" id="f-status">
      <option value="all">全部状态</option><option value="running">仅运行中</option>
      <option value="stopped">仅已停止</option>
    </select>
    <select class="select" id="f-node"><option value="all">全部节点</option></select>
    <div style="position:relative">
      <input class="input" id="f-q" placeholder="搜索名称 / IP / 模板…" style="padding-left:32px;width:240px">
      <span style="position:absolute;left:10px;top:50%;transform:translateY(-50%);color:var(--muted)">
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor"
          stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg></span>
    </div>
    <span class="spacer"></span>
    <span class="sub" id="ct-count"></span>
  </div>
  <div class="card" style="padding:6px 12px">
    <div class="table-wrap"><table>
      <thead><tr><th>实例</th><th>节点</th><th>状态</th><th>IP 地址</th><th>vCPU</th>
        <th style="min-width:150px">内存占用</th><th>磁盘配额</th><th>快照</th><th>运行时长</th><th style="min-width:210px">操作</th></tr></thead>
      <tbody id="ct-body"></tbody></table></div>
  </div>`;

  $("#f-status").value = state.ctFilters.status;
  $("#f-status").onchange = e=>{ state.ctFilters.status=e.target.value; loadCT(); };
  // 节点筛选下拉
  api("/nodes").then(ns=>{
    const sel=$("#f-node");
    ns.forEach(n=>{ const o=document.createElement("option"); o.value=n.id; o.textContent=n.name; sel.appendChild(o); });
    if(state.ctFilters.node) sel.value=state.ctFilters.node;
    sel.onchange=e=>{ state.ctFilters.node=e.target.value; loadCT(); };
  }).catch(()=>{});
  let deb; $("#f-q").oninput = e=>{ clearTimeout(deb);
    deb=setTimeout(()=>{ state.ctFilters.q=e.target.value.trim(); loadCT(); },300); };
  $("#btn-create").onclick = openCreateModal;
  loadCT();
  tickHandle = setInterval(loadCT, 4000);
}

let _lastCTKey = "";
async function loadCT(){
  try{
    const f = state.ctFilters;
    let list = await api(`/containers?q=${encodeURIComponent(f.q)}&status=${f.status}`);
    if(f.node && f.node!=="all") list = list.filter(c=>String(c.node_id)===String(f.node));
    $("#ct-count").textContent = `共 ${list.length} 台`;
    // 数据没变化就跳过重绘，避免打断按钮点击
    const key = JSON.stringify(list.map(c=>c.id+c.status+c.live.cpu_pct+c.live.mem_used_mb));
    if(key === _lastCTKey) return; _lastCTKey = key;

    $("#ct-body").innerHTML = list.map(c=>{
      const d = DISTRO_META[c.distro] || { name:c.distro, bg:"#64748b" };
      const run = c.status === "running";
      const memPct = c.live.mem_used_mb ? c.live.mem_used_mb/c.mem*100 : 0;
      return `<tr>
      <td><div style="display:flex;gap:11px;align-items:center">
        <span class="tpl-logo" style="width:34px;height:34px;font-size:13px;background:${d.bg}">${d.name.slice(0,2).toUpperCase()}</span>
        <div><b>${esc(c.name)}</b>
          <div style="font-size:11.5px;color:var(--muted)" class="mono">${c.uuid.slice(0,8)} · ${esc(c.template)}</div></div>
      </div></td>
      <td>${c.node_kind==="demo"?`<span class="tag" title="演示节点">🎮 ${esc(c.node_name)}</span>`
                                 :`<span class="tag" title="${esc(c.node_name)}">${icon("server",11)} ${esc(c.node_name)}</span>`}</td>
      <td><span class="badge ${c.status}"><span class="dot"></span>${run?"运行中":"已停止"}</span></td>
      <td class="mono">${esc(c.live?.ip || c.ip || "—")}${c.node_kind==="demo"?' <span style="color:var(--muted);font-size:10px">(演示)</span>':""}</td>
      <td>${c.cpu} 核</td>
      <td>${run?`<div style="display:flex;align-items:center;gap:9px">
          <div class="bar" style="flex:1"><i style="width:${memPct}%;background:${barColor(memPct)}"></i></div>
          <span class="mono" style="font-size:11.5px;color:var(--muted)">${fmtGB(c.live.mem_used_mb)}/${fmtGB(c.mem)}${c.swap?`+${fmtGB(c.swap)}S`:""}</span>
        </div>`:`<span style="color:var(--muted)">— / ${fmtGB(c.mem)}${c.swap?`+${fmtGB(c.swap)}S`:""}</span>`}</td>
      <td>${c.disk} GB</td>
      <td>${c.snapshots?`<span class="tag">${icon("camera",11)} ${c.snapshots}</span>`:"—"}</td>
      <td class="mono" style="font-size:12px">${fmtUp(c.live.uptime_s)}</td>
      <td><div class="actions-cell">
        <button class="act-btn ok" title="启动" ${run?"disabled":""} onclick="ctAction(${c.id},'start')">${icon("play")}</button>
        <button class="act-btn warn" title="停止" ${!run?"disabled":""} onclick="ctAction(${c.id},'stop')">${icon("stop")}</button>
        <button class="act-btn warn" title="重启" ${!run?"disabled":""} onclick="ctAction(${c.id},'restart')">${icon("rotate")}</button>
        <button class="act-btn" title="控制台" onclick="openConsole(${c.id},'${esc(c.name)}')">${icon("term")}</button>
        <button class="act-btn" title="编辑配置(需停止)" ${run?"disabled":""} onclick="editContainerConfig(${c.id},'${esc(c.name)}',${c.cpu},${c.mem},${c.swap||0},${c.disk})">${icon("cpu")}</button>
        <button class="act-btn" title="创建快照" onclick="openSnapModal(${c.id},'${esc(c.name)}')">${icon("camera")}</button>
        <button class="act-btn err" title="删除(需管理员)" onclick="deleteContainer(${c.id},'${esc(c.name)}')">${icon("trash")}</button>
      </div></td></tr>`;
    }).join("") || `<tr><td colspan="10" class="empty">
      没有实例。${state.user.role==="admin"?'<a href="#nodes" style="cursor:pointer">先接入服务器节点 →</a>':""}</td></tr>`;
  }catch(e){}
}

window.ctAction = async (id, action)=>{
  try{
    await api(`/containers/${id}/action`, { method:"POST", body:{ action } });
    toast({ start:"启动指令已下发", stop:"停止指令已下发", restart:"重启指令已下发" }[action], "ok");
    _lastCTKey=""; loadCT();
  }catch(e){ toast(e.message,"err"); }
};

window.editContainerConfig = async function(id, name, cpu, mem, swap, disk){
  swap = swap || 0;
  const ov = openModal(`编辑配置 — <b>${esc(name)}</b>`, `
    <p style="color:var(--muted);font-size:12.5px;line-height:1.7;margin-bottom:12px">
      修改前请先停止容器。CPU/内存/Swap 会同步到 LXC 配置，磁盘为面板配额（dir 类型根目录不实际扩容）。</p>
    <div class="form-grid">
      <label>vCPU 核数<input id="ec-cpu" type="number" min="1" max="16" value="${cpu}"></label>
      <label>内存 MB<input id="ec-mem" type="number" min="64" step="64" value="${mem}"></label>
      <label>Swap MB<input id="ec-swap" type="number" min="0" max="1048576" value="${swap}"></label>
      <label>磁盘 GB<input id="ec-disk" type="number" min="1" max="2048" value="${disk}"></label>
    </div>`,
    async ()=>{
      try{
        await api(`/containers/${id}/config`, {method:"PUT", body:{
          cpu:+$("#ec-cpu").value||cpu, mem:+$("#ec-mem").value||mem,
          swap:+$("#ec-swap").value||0, disk:+$("#ec-disk").value||disk
        }});
        closeModal(); toast("配置已更新","ok"); _lastCTKey=""; loadCT();
      }catch(e){ toast(e.message,"err"); }
    }, "保存");
};

window.deleteContainer = async (id, name)=>{
  if(!(await confirmModal(`确定删除实例 <b>${esc(name)}</b> ？其磁盘、快照与 IP 将被一并释放，此操作不可恢复！`, true))) return;
  try{ await api(`/containers/${id}`, { method:"DELETE" }); toast(`${name} 已删除`,"ok"); _lastCTKey=""; loadCT(); }
  catch(e){ toast(e.message,"err"); }
};

/* ── 创建实例弹窗（多节点 + 内存 64M 粒度） ── */
async function openCreateModal(preTpl, preNode){
  let templates=[], nodes=[];
  try{
    [templates, nodes] = await Promise.all([api("/templates"), api("/nodes")]);
  }catch(e){ toast(e.message,"err"); return; }
  const usable = nodes.filter(n=>n.kind==="demo"||n.lxc_ok);
  if(!usable.length){
    confirmModal(`还没有可用的服务器节点。<br>创建实例前需要先<b>接入至少一台服务器</b>（或添加演示节点体验）。`,
      false).then(()=>location.hash="nodes");
    return;
  }
  const m = openModal("创建新实例", `
    <div class="form-grid">
      <label>主机名 *<input id="c-name" placeholder="如 my-app"></label>
      <label>目标节点 *
        <select id="c-node">${usable.map(n=>
          `<option value="${n.id}" ${String(n.id)===String(preNode)?"selected":""}>
            ${esc(n.name)}${n.kind==="demo"?"（演示）":n.lxc_ok?"":" ⚠未装LXC"}</option>`).join("")}
        </select></label>
      <label>选择模板 *
        <select id="c-tpl">${templates.filter(t=>t.supported!==false).map(t=>
          `<option value="${t.key}" ${t.key===preTpl?"selected":""}>${esc(t.name)} · ${t.size_mb}MB</option>`).join("")}
        </select></label>
      <label>vCPU 核数<input id="c-cpu" type="number" min="1" max="16" value="1"></label>
      <label class="full">内存 MB *
        <div class="mem-picker">
          <input id="c-mem" type="number" min="64" step="64" value="512">
          <div class="mem-chips" id="mem-chips">
            ${MEM_PRESETS.slice(0,9).map(v=>`<button type="button" class="chip-btn${v===512?" on":""}" data-v="${v}">${v>=1024?(v/1024)+"G":v+"M"}</button>`).join("")}
          </div>
        </div></label>
      <label>Swap MB<input id="c-swap" type="number" min="0" max="1048576" value="0" title="为容器分配 swap 作为内存补充，0=不额外设置"></label>
      <label>磁盘 GB<input id="c-disk" type="number" min="1" max="2048" value="10"></label>
      <label>备注<input id="c-note" placeholder="选填"></label>
      <label class="full check-line"><input type="checkbox" id="c-auto" checked style="accent-color:var(--accent)">
        创建完成后立即启动</label>
      <p class="sub full" style="color:var(--muted);font-size:12px">
        内存支持 64MB 起步、64MB 步进；Swap 可让 LXC 小鸡把磁盘当内存补充（0=不额外设置）。</p>
    </div>`,
    async ()=>{
      const memV = +$("#c-mem").value;
      if(!memV || memV < 64) return toast("内存最低 64 MB","err");
      if(memV % 64 !== 0) return toast("内存需为 64 的整数倍","err");
      try{
        await api("/containers", { method:"POST", body:{
          name:$("#c-name").value.trim().toLowerCase(), template:$("#c-tpl").value,
          node_id:+$("#c-node").value,
          cpu:+$("#c-cpu").value, mem:memV, swap:+$("#c-swap").value||0, disk:+$("#c-disk").value,
          note:$("#c-note").value.trim(), autostart:$("#c-auto").checked }});
        closeModal();
        toast("创建指令已下发，镜像下载可能需要一些时间","ok",4000);
        _lastCTKey="";
        if(location.hash!=="#containers") location.hash="containers"; else loadCT();
      }catch(e){ toast(String(e.message).slice(0,180),"err",5000); }
    }, "开始创建");
  m.querySelector("#c-name").focus();
  // 内存快捷档位
  $$("#mem-chips .chip-btn").forEach(b=>b.onclick=()=>{
    $("#c-mem").value=b.dataset.v;
    $$("#mem-chips .chip-btn").forEach(x=>x.classList.remove("on"));
    b.classList.add("on");
  });
  $("#c-mem").addEventListener("input",()=>{
    const v=+$("#c-mem").value;
    $$("#mem-chips .chip-btn").forEach(x=>x.classList.toggle("on", +x.dataset.v===v));
  });
}
window.openCreateModal = openCreateModal;

/* ── 快照弹窗 ── */
function openSnapModal(cid, name){
  openModal(`为 <b>${esc(name)}</b> 创建快照`, `
    <div class="form-grid">
      <label class="full">快照名称
        <input id="s-name" value="snap-${new Date().toISOString().slice(0,10)}"></label>
      <p class="sub full" style="color:var(--muted);font-size:12.5px;line-height:1.7">
        快照将冻结文件系统并生成一致性时间点，可用于一键回滚。生产环境建议在低峰期执行。</p>
    </div>`,
    async ()=>{
      try{
        const r = await api(`/containers/${cid}/snapshots`, { method:"POST", body:{ name:$("#s-name").value.trim() }});
        closeModal(); toast(`快照 ${r.name} 创建完成 (${fmtGB(r.size_mb)})`,"ok"); _lastCTKey="";
      }catch(e){ toast(e.message,"err"); }
    }, "创建快照");
}
window.openSnapModal = openSnapModal;

/* ══════════════ 视图：一键部署(X-UI 移植) ══════════════ */
const SNI_PRESETS = ["addons.mozilla.org","www.apple.com","gateway.icloud.com",
  "itunes.apple.com","www.microsoft.com","www.yahoo.com"];
let deployJob = null;

async function viewApps(){
  $("#content").innerHTML = `
  <div class="page-head">
    <span class="sub">把代理协议栈一键下发到指定 LXC 容器或 VPS 主机（sing-box 内核 · 支持 8合1）</span>
    <span class="spacer"></span>
    <button class="btn primary" id="btn-sub">${icon("link",14)} 🔗 订阅</button>
  </div>
  <div class="cols-2-1">
    <div>
      <div class="card">
        <h4><span class="dot"></span>选择目标</h4>
        <div class="form-grid">
          <label>部署目标 *
            <select id="d-target-type">
              <option value="container">📦 部署到 LXC 容器</option>
              <option value="host">🖥 部署到主机（VPS 直装）</option>
            </select></label>
          <label id="wrap-container">目标容器 *
            <select id="d-container"><option value="">加载中…</option></select></label>
          <label id="wrap-host" class="hidden">目标主机 *
            <select id="d-host"><option value="">加载中…</option></select></label>
          <label>应用模板 *
            <select id="d-app">
              <option value="xui-8in1">🚀 极速全量节点 (8合1)</option>
              <option value="xtls-reality">XTLS + Reality</option>
              <option value="hysteria2">Hysteria2 (极速)</option>
              <option value="tuic">TUIC v5 (高并发)</option>
              <option value="trojan">Trojan</option>
              <option value="h2-reality">H2 + Reality</option>
              <option value="grpc-reality">gRPC + Reality</option>
              <option value="anytls">AnyTLS</option>
              <option value="naive">Naive</option>
              <option value="vless-ws">VLESS + WS</option>
              <option value="vmess-ws">VMess + WS</option>
              <option value="ss-2022">Shadowsocks 2022</option>
            </select></label>
          <label>起始端口 *<input id="d-port" type="number" value="8881" min="1024" max="65528"></label>
          <label>SNI 伪装域名<input id="d-sni" list="sni-list" placeholder="addons.mozilla.org"></label>
          <datalist id="sni-list">${SNI_PRESETS.map(s=>`<option value="${s}">`).join("")}</datalist>
        </div>
        <p class="sub" style="color:var(--muted);font-size:12px;margin-top:10px;line-height:1.7" id="d-desc"></p>
        <button class="btn primary block" id="btn-deploy" style="margin-top:12px">${icon("zap",14)} 🚀 立即下发</button>
      </div>
      <div class="card" style="margin-top:16px">
        <h4><span class="dot"></span>部署日志</h4>
        <div class="term" style="height:200px;overflow-y:auto" id="deploy-log">等待发起部署…</div>
      </div>
    </div>
    <div>
      <div class="card">
        <h4><span class="dot"></span>8合1 协议矩阵</h4>
        <table style="font-size:12.5px"><tbody>
          ${[["XTLS-Reality",8881,"tcp"],["Hysteria2",8882,"udp"],["TUIC",8883,"udp"],["Trojan",8884,"tcp"],
             ["H2-Reality",8885,"tcp"],["gRPC-Reality",8886,"tcp"],["AnyTLS",8887,"tcp"],["Naive",8888,"tcp"]]
            .map(p=>`<tr><td><b>${p[0]}</b></td><td class="mono">${p[1]}<span style="color:var(--muted)">/${p[2]}</span></td></tr>`).join("")}
        </tbody></table>
        <p style="color:var(--muted);font-size:11.5px;margin-top:8px">共用 UUID · Reality 密钥对自动生成 · 容器模式自动 DNAT 映射</p>
      </div>
      <div class="card" style="margin-top:16px;padding:6px 12px">
        <h4 style="padding:10px 6px 0;display:flex;align-items:center;gap:8px"><span class="dot"></span>已部署节点
          <select id="machine-filter" class="select" style="margin-left:auto;width:auto;max-width:240px">
            <option value="all">全部机器</option>
          </select>
          <button class="btn sm ghost" id="btn-toggle-apps" title="展开/收起全部机器分组">展开全部</button>
          <button class="btn sm" id="btn-sync-machine" title="按机器合并重建 sing-box 配置，修复协议不通/互相覆盖">🔄 同步配置</button>
        </h4>
        <div id="apps-container" style="margin-top:8px"></div>
      </div>
    </div>
  </div>
  <div class="card" style="margin-top:16px" id="links-card">
    <h4><span class="dot"></span>分享链接 <button class="btn sm ghost" id="btn-copy-all" style="margin-left:auto;display:none">📋 复制全部</button></h4>
    <div id="links-box" style="display:flex;flex-direction:column;gap:8px;margin-top:10px">
      <span class="empty">尚无部署结果</span></div>
  </div>`;

  try{
    const [cts, ns] = await Promise.all([api("/containers"), api("/nodes")]);
    const usableCts = cts.filter(c=>c.node_kind!=="demo");
    $("#d-container").innerHTML = usableCts.map(c=>
      `<option value="${c.id}">${esc(c.name)} · ${esc(c.node_name)}</option>`).join("")
      || `<option value="">暂无容器，请先创建</option>`;
    const hosts = ns.filter(n=>n.role!=="probe"&&n.kind!=="demo");
    $("#d-host").innerHTML = hosts.map(n=>
      `<option value="${n.id}">${esc(n.name)} · ${n.kind==="agent"?"Agent":"SSH"}${n.lxc_ok?"":" ⚠未装LXC(不影响直装)"}</option>`).join("")
      || `<option value="">暂无可用节点</option>`;
    $("#d-host").dataset.loaded = "1";
  }catch(e){}

  const DESC = {
    "xui-8in1":"将向目标一次性下发 8 个防封协议（起始端口连续占用 8 个），自动生成 Reality 密钥对、自签证书；容器模式还会在宿主节点配置 DNAT 端口映射。"};
  $("#d-app").onchange = e=>{
    $("#d-desc").textContent = DESC[e.target.value] || "将在目标以 sing-box 内核部署该单协议，并自动完成端口映射。";
  };
  $("#d-app").dispatchEvent(new Event("change"));

  // 切换部署目标：容器 / VPS 主机
  const syncDeployTarget = ()=>{
    const isHost = $("#d-target-type").value === "host";
    $("#wrap-container").classList.toggle("hidden", isHost);
    $("#wrap-host").classList.toggle("hidden", !isHost);
  };
  $("#d-target-type").onchange = syncDeployTarget;
  syncDeployTarget();

  loadApps();
  $("#btn-sub").onclick = openSubModal;
  $("#btn-deploy").onclick = async ()=>{
    const isHost = $("#d-target-type").value==="host";
    const appLabel = $("#d-app").options[$("#d-app").selectedIndex].text;
    const body = { app_type:$("#d-app").value,
      start_port:+$("#d-port").value||8881, sni:$("#d-sni").value.trim(),
      target_type: isHost ? "host" : "container" };
    let targetName="";
    if(isHost){
      body.node_id = +$("#d-host").value;
      targetName = $("#d-host")?.selectedOptions?.[0]?.textContent || "";
      if(!body.node_id) return toast("请选择目标主机","err");
    } else {
      body.container_id = +$("#d-container").value;
      targetName = $("#d-container")?.selectedOptions?.[0]?.textContent || "";
      if(!body.container_id) return toast("请先选择目标容器","err");
    }
    if(!(await confirmModal(`确认下发 <b>${appLabel}</b> 到<br><b>${esc(targetName)}</b> ？`))) return;
    try{
      const r = await api("/deploy",{method:"POST",body});
      deployJob = r.job_id;
      toast("部署指令已下发，日志实时滚动中…","info");
      pollDeploy();
    }catch(e){ toast(e.message,"err"); }
  };
}

function pollDeploy(){
  clearInterval(tickHandle);
  const logBox = $("#deploy-log");
  tickHandle = setInterval(async ()=>{
    if(!deployJob) return;
    try{
      const d = await api(`/deploy/${deployJob}`);
      logBox.textContent = d.log || "…";
      logBox.scrollTop = logBox.scrollHeight;
      if(d.status==="done"){
        clearInterval(tickHandle);
        deployJob = null;
        renderLinks(d.result?.links||[]);
        toast("✅ 部署完成！","ok"); loadApps();
      } else if(d.status==="failed"){
        clearInterval(tickHandle);
        deployJob = null;
        toast("部署失败，详见日志","err");
      }
    }catch(e){}
  }, 1500);
}

function renderLinks(links){
  const box = $("#links-box");
  window._lastLinks = links;
  if(!links.length){ box.innerHTML = '<span class="empty">尚无部署结果</span>'; return; }
  box.innerHTML = links.map((l,i)=>`
    <div style="display:flex;gap:8px;align-items:center;background:var(--bg-soft);
      border:1px solid var(--line);border-radius:9px;padding:9px 12px">
      <span class="mono" style="flex:1;font-size:11.5px;word-break:break-all;color:var(--accent-2)">${esc(l)}</span>
      <button class="btn sm" onclick="copyText(window._lastLinks[${i}])">复制</button>
    </div>`).join("");
  const btn = $("#btn-copy-all");
  btn.style.display = "inline-flex";
  btn.onclick = ()=>copyText(links.join("\n"));
}

window.copyText = t=>{
  navigator.clipboard?.writeText(t).then(()=>toast("已复制","ok"))
    .catch(()=>{
      const ta=document.createElement("textarea"); ta.value=t; document.body.appendChild(ta);
      ta.select(); document.execCommand("copy"); ta.remove(); toast("已复制","ok");
    });
};

async function loadApps(){
  try{
    const list = await api("/apps");
    const sel = $("#machine-filter");
    // 机器列表（容器 / 主机）
    const machines = new Map();
    list.forEach(a=>{
      const key = a.container_id ? `c-${a.container_id}` : `h-${a.node_id}`;
      const name = a.container_id ? (a.container || a.name || "容器") : (a.node_name || a.name || "主机");
      if(!machines.has(key)) machines.set(key, name);
    });
    if(sel){
      const cur = sel.value;
      sel.innerHTML = `<option value="all">全部机器</option>` +
        [...machines.entries()].map(([k,v])=>`<option value="${k}">${esc(v)}</option>`).join("");
      if(cur && machines.has(cur)) sel.value = cur;
    }
    const selected = sel ? sel.value : "all";

    const isAll = selected === "all";
    const groups = new Map();
    list.forEach(a=>{
      const mkey = a.container_id ? `c-${a.container_id}` : `h-${a.node_id}`;
      if(!isAll && mkey !== selected) return;
      const machineName = a.container_id ? (a.container || a.name || "容器") : (a.node_name || a.name || "主机");
      if(!groups.has(mkey)) groups.set(mkey, {name:machineName, rows:[]});
      const rows = groups.get(mkey).rows;
      (a.spec || []).forEach((s,i)=>{
        const link = (a.links || [])[i] || "";
        const proto = s.protocol || s.type || "?";
        const port = s.port || "";
        rows.push(`<tr>
          <td><span class="tag">${esc(proto)}</span></td>
          <td class="mono">${port}</td>
          <td><span class="badge running"><span class="dot"></span>运行中</span></td>
          <td><div class="actions-cell">
            ${link?`<button class="btn sm" onclick='copyText(${JSON.stringify(link)})'>复制</button>`:""}
            <button class="btn sm warn" data-del-node="${a.id}" data-idx="${i}" title="删除该单个节点">${icon("trash",12)} 删除</button>
            <button class="btn sm ghost" data-del-app="${a.id}" title="删除整组(该应用全部节点)">整组</button>
          </div></td></tr>`);
      });
    });
    let appsHtml = "";
    for(const [mkey, g] of groups){
      const open = !isAll;
      appsHtml += `<details class="machine-group" ${open?"open":""} data-mkey="${mkey}">
        <summary>
          <span class="mg-title">${icon("server",14)} ${esc(g.name)}</span>
          <span class="tag mg-count">${g.rows.length} 节点</span>
          <span class="spacer"></span>
          <span class="mg-chevron">${open?"▾":"▸"}</span>
        </summary>
        <div class="table-wrap"><table>
          <thead><tr><th>协议</th><th>端口</th><th>状态</th><th>操作</th></tr></thead>
          <tbody>${g.rows.join("")}</tbody>
        </table></div>
      </details>`;
    }
    $("#apps-container").innerHTML = appsHtml || `<div class="empty">暂无部署记录</div>`;
    const btnToggle = $("#btn-toggle-apps");
    if(btnToggle){
      btnToggle.textContent = isAll ? "展开全部" : "收起全部";
      btnToggle.onclick = ()=>{
        const all = $$("#apps-container details.machine-group");
        const anyOpen = [...all].some(d=>d.open);
        all.forEach(d=>{ d.open = !anyOpen; d.querySelector(".mg-chevron").textContent = d.open?"▾":"▸"; });
        btnToggle.textContent = anyOpen ? "展开全部" : "收起全部";
      };
    }

    if(sel) sel.onchange = loadApps;

    $("#btn-sync-machine").onclick = async ()=>{
      const selVal = sel ? sel.value : "all";
      const targets = [];
      if(selVal === "all"){
        // 全部机器：每个有应用的 node/container 同步一次
        const seen = new Set();
        list.forEach(a=>{
          if(a.container_id && !seen.has(`c${a.container_id}`)){ seen.add(`c${a.container_id}`); targets.push({container_id:a.container_id}); }
          else if(a.node_id && !seen.has(`h${a.node_id}`)){ seen.add(`h${a.node_id}`); targets.push({node_id:a.node_id}); }
        });
      } else if(selVal.startsWith("c-")){
        targets.push({container_id: +selVal.slice(2)});
      } else if(selVal.startsWith("h-")){
        targets.push({node_id: +selVal.slice(2)});
      }
      if(!targets.length) return toast("没有可同步的机器","info");
      try{
        for(const t of targets){
          await api("/apps/sync-machine",{method:"POST",body:t});
        }
        toast(`已同步 ${targets.length} 台机器配置`,"ok",4000);
      }catch(e){ toast(e.message,"err",5000); }
    };

    $$("#apps-container [data-del-node]").forEach(b=>b.onclick=async()=>{
      const appId = +b.dataset.delNode, idx = +b.dataset.idx;
      if(!(await confirmModal("删除该单个代理节点？将重新生成 sing-box 配置并重启，只移除这一个节点。", true))) return;
      try{
        const r = await api(`/apps/${appId}/nodes/${idx}`,{method:"DELETE"});
        toast(r.app_deleted ? "该节点是最后节点，整组已删除" : "单个节点已删除","ok");
        loadApps();
      }catch(e){ toast(e.message,"err"); }
    });

    $$("#apps-container [data-del-app]").forEach(b=>b.onclick=async()=>{
      if(!(await confirmModal("删除整组应用？将停止 sing-box 并移除全部端口映射。",true))) return;
      try{ await api(`/apps/${b.dataset.delApp}`,{method:"DELETE"}); toast("整组已删除","ok"); loadApps(); }
      catch(e){ toast(e.message,"err"); }
    });
  }catch(e){}
}

/* ── 订阅中心弹窗 ── */
window.openSubModal = async function(){
  try{
    const info = await api("/apps/sub-info");
    const ov = openModal(`🔗 订阅中心`, `
      <p style="color:var(--muted);font-size:12.5px;line-height:1.7;margin-bottom:10px">
        将以下<b>一个订阅链接</b>导入任意客户端即可自动同步面板下发的全部节点（当前 <b>${info.nodes}</b> 个）。
        链接会自动适配：Clash/Mihomo 客户端返回 YAML，其他客户端返回 Base64，无需区分软件。</p>
      <label style="display:block;font-size:12px;color:var(--muted)">统一订阅链接（所有客户端通用）</label>
      <div class="term" style="height:auto;padding:12px;user-select:all;word-break:break-all" id="sub-url-box">${esc(info.url)}</div>
      <button class="btn sm block" style="margin-top:8px" onclick="copyText(document.getElementById('sub-url-box').textContent)">📋 复制订阅链接</button>
      <p style="color:var(--muted);font-size:11.5px;margin-top:12px;line-height:1.7">
        · 新部署节点后客户端刷新订阅即可拉取<br>
        · Token 泄露时可重置，旧链接立即失效<br></p>
      <button class="btn danger sm block" style="margin-top:10px" id="btn-sub-reset">♻️ 重置订阅令牌</button>`,
      null, "", {wide:true});
    ov.querySelector(".modal-foot").remove();
    ov.querySelector("#btn-sub-reset").onclick = async ()=>{
      if(!(await confirmModal("确定重置订阅令牌？所有已分发的旧订阅链接将立即失效。",true))) return;
      try{
        const r = await api("/apps/sub-reset",{method:"POST"});
        closeModal(); toast("订阅令牌已重置","ok"); openSubModal();
      }catch(e){ toast(e.message,"err"); }
    };
  }catch(e){ toast(e.message,"err"); }
};

/* ══════════════ 视图：主机探针 ══════════════ */
async function viewProbes(){
  $("#content").innerHTML = `
  <div class="page-head">
    <span class="sub">轻量探针只做监控不上传任何管理能力 —— 适合纯看板的服务器</span>
    <span class="spacer"></span>
    <button class="btn primary" id="btn-add-probe">${icon("plus")} 添加探针</button>
    <button class="btn ghost" id="btn-refresh-probe">${icon("rotate",13)} 刷新</button>
  </div>
  <div class="grid tpl-grid" id="probe-grid"><div class="empty">加载中…</div></div>`;

  const render = async ()=>{
    try{
      const list = await api("/probes");
      $("#probe-grid").innerHTML = list.map(p=>{
        const [c,lbl] = NODE_ST[p.online?"online":"offline"];
        const memP = p.mem_total_mb? p.mem_used_mb/p.mem_total_mb*100 : 0;
        const diskP = p.disk_total_gb? p.disk_used_gb/p.disk_total_gb*100 : 0;
        return `<div class="card tpl-card">
          <div class="stripe" style="background:${c}"></div>
          <div class="tpl-head">
            <span class="tpl-logo" style="background:#334155;width:38px;height:38px">${icon("activity",16)}</span>
            <div><b>${esc(p.hostname||p.name)}</b>
              <div class="mono" style="font-size:11px;color:var(--muted)">${esc(p.os)}</div>
              ${p.public_ip?`<div class="mono" style="font-size:10.5px;color:var(--muted);margin-top:2px">🌐 ${esc(p.public_ip)}</div>`:""}</div>
            <span class="badge" style="margin-left:auto"><span class="dot" style="background:${c};animation:${p.online?'pulse 1.6s infinite':'none'}"></span>${p.online?"在线":"离线"}</span>
          </div>
          ${miniBar("CPU", p.cpu_pct, (p.cpu_pct||0).toFixed(1)+"% / "+p.cores+"核")}
          ${miniBar("内存", memP, fmtGB(p.mem_used_mb)+" / "+fmtGB(p.mem_total_mb))}
          ${miniBar("磁盘", diskP, p.disk_used_gb+"G / "+p.disk_total_gb+"G")}
          <div style="display:flex;gap:6px;margin-top:10px;flex-wrap:wrap">
            <span class="tag">⏱ ↑${fmtUp(p.uptime_s)}</span>
            <span class="tag mono">↓${fmtKb(p.rx_kbps)} ↑${fmtKb(p.tx_kbps)}</span>
            ${Object.entries(p.latency||{}).map(([k,v])=>
              `<span class="tag" style="color:${v==null?"var(--err)":"var(--ok-strong)"}">${k} ${v==null?"×":v+"ms"}</span>`).join("")}
          </div>
          <div class="actions-cell" style="margin-top:12px">
            <button class="btn sm" data-term="${p.id}" data-name="${esc(p.hostname||p.name)}" title="探针终端">${icon("server",12)} 终端</button>
            <button class="btn sm" data-show-cmd="${p.id}">${icon("term",12)} 接入命令</button>
            <button class="btn sm" data-uninst-cmd="${p.id}" title="生成一键清理命令">${icon("trash",12)} 卸载</button>
            <button class="btn sm danger" data-del="${p.id}" data-name="${esc(p.name)}">${icon("trash",12)} 删除</button>
          </div></div>`;
      }).join("") || `<div class="empty" style="grid-column:1/-1;padding:60px 0">
        <p style="font-size:15px;margin-bottom:8px">还没有探针节点</p>
        <p>有些服务器既不想装节点也不想装 LXC —— 添加「仅监控探针」即可实时查看负载与延迟</p></div>`;
      $$("#probe-grid [data-del]").forEach(b=>b.onclick=()=>deleteNode(+b.dataset.del,b.dataset.name));
      $$("#probe-grid [data-term]").forEach(b=>b.onclick=()=>openNodeTerminal(+b.dataset.term, b.dataset.name));
      $$("#probe-grid [data-show-cmd]").forEach(async b=>{
        b.onclick=async()=>{
          const n=(await api("/nodes")).find(x=>String(x.id)===b.dataset.showCmd);
          if(n) showAgentCmdModal(n);
        };
      });
      $$("#probe-grid [data-uninst-cmd]").forEach(async b=>{
        b.onclick=async()=>{
          const n=(await api("/nodes")).find(x=>String(x.id)===b.dataset.uninstCmd);
          if(n) showUninstallModal(n); else toast("节点不存在","err");
        };
      });
      $$("#probe-grid .card")[0]?.classList.add("done");
    }catch(e){ $("#probe-grid").innerHTML=`<div class="empty">${esc(e.message)}</div>`; }
  };
  $("#btn-add-probe").onclick=()=>{
    openNodeModal();
    setTimeout(()=>{ const s=$("#n-kind"); if(s){ s.value="probe"; s.dispatchEvent(new Event("change")); } },50);
  };
  $("#btn-refresh-probe").onclick=render;
  render(); tickHandle=setInterval(render,5000);
}

/* ══════════════ 视图：模板 ══════════════ */
async function viewTemplates(){
  $("#content").innerHTML = `<div class="page-head">
      <span class="sub">官方源同步的精简系统镜像，开箱即用</span></div>
    <div class="grid tpl-grid" id="tpl-grid"><div class="empty">加载中…</div></div>`;
  try{
    const list = await api("/templates");
    $("#tpl-grid").innerHTML = list.map(t=>{
      const d = DISTRO_META[t.distro] || { name:t.distro, bg:"#64748b" };
      return `<div class="card tpl-card">
        <div class="stripe" style="background:${d.bg}"></div>
        <div class="tpl-head">
          <span class="tpl-logo" style="background:${d.bg}">${d.name.slice(0,2).toUpperCase()}</span>
          <div><b>${esc(t.name)}</b>
            <div class="mono" style="font-size:11px;color:var(--muted)">${t.key}</div></div>
        </div>
        <div class="tpl-meta">
          <span class="tag">v${esc(t.version)}</span>
          <span class="tag">${t.arch}</span>
          <span class="tag">${t.size_mb} MB</span>
        </div>
        <button class="btn sm block" onclick="openCreateModal('${t.key}')">${icon("zap",13)} 使用该模板创建</button>
      </div>`;
    }).join("");
  }catch(e){ $("#tpl-grid").innerHTML = `<div class="empty">${esc(e.message)}</div>`; }
}

/* ══════════════ 视图：快照 ══════════════ */
async function viewSnapshots(){
  $("#content").innerHTML = `
    <div class="card" style="padding:6px 12px">
    <div class="table-wrap"><table>
      <thead><tr><th>#</th><th>所属实例</th><th>快照名称</th><th>大小</th><th>创建时间</th><th>操作</th></tr></thead>
      <tbody id="snap-body"></tbody></table></div></div>`;
  try{
    const list = await api("/snapshots");
    $("#snap-body").innerHTML = list.map(s=>`
      <tr><td class="mono">#${s.id}</td>
      <td><b>${esc(s.container||"(已删除)")}</b></td>
      <td>${icon("camera",13)} ${esc(s.name)}</td>
      <td class="mono">${fmtGB(s.size_mb)}</td>
      <td class="mono" style="font-size:12px">${esc(s.created_at)}</td>
      <td><div class="actions-cell">
        <button class="btn sm" onclick="restoreSnap(${s.id})">${icon("rotate",12)} 回滚</button>
        <button class="btn sm danger" onclick="delSnap(${s.id})">${icon("trash",12)} 删除</button>
      </div></td></tr>`).join("") ||
      `<tr><td colspan="6" class="empty">还没有任何快照 — 在实例列表点击 📷 创建</td></tr>`;
  }catch(e){ $("#snap-body").innerHTML = `<tr><td class="empty">${esc(e.message)}</td></tr>`; }
}
window.restoreSnap = async id=>{
  if(!(await confirmModal("回滚后，实例在该快照之后的所有数据变更都将丢失。确认继续？",true))) return;
  try{ const r = await api(`/snapshots/${id}/restore`,{method:"POST"}); toast(r.message,"ok"); }
  catch(e){ toast(e.message,"err"); }
};
window.delSnap = async id=>{
  if(!(await confirmModal("确定删除该快照？"))) return;
  try{ await api(`/snapshots/${id}`,{method:"DELETE"}); toast("快照已删除","ok"); viewSnapshots(); }
  catch(e){ toast(e.message,"err"); }
};

/* ══════════════ 视图：IP 分配 ══════════════ */
async function viewNetwork(){
  $("#content").innerHTML = `
  <div class="grid stat-grid" id="br-grid"></div>
  <div class="card" style="margin-top:16px;padding:6px 12px">
    <h4 style="padding:12px 6px 0"><span class="dot"></span>IP 地址分配明细
      <span class="tag" style="margin-left:auto">真实节点 IP 由各节点 lxcnet DHCP 分配，自动回填</span></h4>
    <div class="table-wrap" style="margin-top:10px"><table>
      <thead><tr><th>所属节点</th><th>IP 地址</th><th>实例</th><th>状态</th></tr></thead>
      <tbody id="ip-body"></tbody></table></div></div>`;
  try{
    const n = await api("/network");
    const ST={online:["var(--ok)","在线"],nolxc:["var(--warn)","未装LXC"],
              offline:["var(--err)","离线"],unknown:["var(--muted)","待探测"]};
    $("#br-grid").innerHTML = n.bridges.map(b=>{
      const [c,lbl]=ST[b.state]||ST.unknown;
      return `<div class="card">
        <h4><span class="dot" style="background:${c}"></span>${esc(b.name)}
          <span class="tag">${b.kind==="demo"?"演示":"SSH 节点"}</span></h4>
        <dl class="kv">
          <dt>连接状态</dt><dd>${lbl}</dd>
          <dt>已分配 IP</dt><dd>${b.used} 台</dd>
          <dt>网络模式</dt><dd>${b.kind==="demo"?"模拟 NAT":"lxcnet DHCP"}</dd>
        </dl></div>`;
    }).join("") || `<div class="empty">暂无节点</div>`;
    $("#ip-body").innerHTML = n.allocations.map(a=>`
      <tr><td><span class="tag">${esc(a.node)}</span></td>
      <td class="mono">${a.ip?esc(a.ip):'<span style="color:var(--muted)">待分配</span>'}</td>
      <td><b>${esc(a.container)}</b></td>
      <td><span class="badge ${a.status}"><span class="dot"></span>${a.status==="running"?"运行中":"已停止"}</span></td></tr>`).join("")
      || `<tr><td colspan="4" class="empty">暂无实例</td></tr>`;
  }catch(e){ toast(e.message,"err"); }
}

/* ══════════════ 视图：用户 ══════════════ */
async function viewUsers(){
  const isAdmin = state.user.role === "admin";
  $("#content").innerHTML = `
    <div class="page-head">
      ${isAdmin?`<button class="btn primary" id="u-add">${icon("plus")} 新增用户</button>`:
      `<span class="sub">仅管理员可管理用户账号</span>`}
    </div>
    <div class="card" style="padding:6px 12px"><div class="table-wrap"><table>
      <thead><tr><th>ID</th><th>用户名</th><th>角色</th><th>创建时间</th><th>操作</th></tr></thead>
      <tbody id="u-body"></tbody></table></div></div>`;
  if(isAdmin) $("#u-add").onclick = ()=>{
    openModal("新增用户", `<div class="form-grid">
      <label>用户名<input id="nu-name" placeholder="字母开头，2-24位"></label>
      <label>角色<select id="nu-role"><option value="user">普通用户</option><option value="admin">管理员</option></select></label>
      <label class="full">初始密码<input id="nu-pass" type="password" placeholder="至少 6 位"></label>
    </div>`, async ()=>{
      try{
        await api("/users",{method:"POST",body:{username:$("#nu-name").value.trim(),
          role:$("#nu-role").value,password:$("#nu-pass").value}});
        closeModal(); toast("用户已创建","ok"); viewUsers();
      }catch(e){ toast(e.message,"err"); }
    },"创建");
  };
  try{
    const list = await api("/users");
    $("#u-body").innerHTML = list.map(u=>`
      <tr><td class="mono">${u.id}</td>
      <td><b>${esc(u.username)}</b>${u.username===state.user.username?' <span class="tag">当前账号</span>':""}</td>
      <td><span class="badge ${u.role==="admin"?"frozen":"stopped"}"><span class="dot"></span>${u.role==="admin"?"管理员":"普通用户"}</span></td>
      <td class="mono" style="font-size:12px">${esc(u.created_at)}</td>
      <td>${isAdmin && u.username!=="admin" ? `<button class="btn sm danger" onclick="delUser(${u.id},'${esc(u.username)}')">${icon("trash",12)} 删除</button>`:"—"}</td>
      </tr>`).join("");
  }catch(e){ toast(e.message,"err"); }
}
window.delUser = async (id,name)=>{
  if(!(await confirmModal(`确定删除用户 <b>${esc(name)}</b>？`,true))) return;
  try{ await api(`/users/${id}`,{method:"DELETE"}); toast("已删除","ok"); viewUsers(); }
  catch(e){ toast(e.message,"err"); }
};

/* ══════════════ 视图：审计日志 ══════════════ */
const ACTION_COLOR = {
  "登录":"stopped","创建实例":"running","删除实例":"stopped","启动":"running",
  "停止":"frozen","重启":"frozen","创建快照":"running","恢复快照":"frozen",
  "删除快照":"stopped","创建用户":"running","删除用户":"stopped","修改密码":"frozen",
  "重置演示数据":"stopped",
};
async function viewAudit(){
  $("#content").innerHTML = `
  <div class="page-head">
    <select class="select" id="a-type">
      <option value="">全部动作</option>${Object.keys(ACTION_COLOR).map(k=>`<option>${k}</option>`).join("")}
    </select>
    <span class="spacer"></span><span class="sub" id="a-count"></span>
  </div>
  <div class="card" style="padding:6px 12px"><div class="table-wrap"><table>
    <thead><tr><th>时间</th><th>操作人</th><th>动作</th><th>对象</th><th>详情</th><th>来源 IP</th></tr></thead>
    <tbody id="a-body"></tbody></table></div></div>`;
  $("#a-type").onchange = ()=>renderAudit();
  await renderAudit();
  tickHandle = setInterval(renderAudit, 6000);
}
async function renderAudit(){
  try{
    let logs = await api("/audit?limit=200");
    const t = $("#a-type")?.value;
    if(t) logs = logs.filter(l=>l.action===t);
    $("#a-count").textContent = `${logs.length} 条记录`;
    $("#a-body").innerHTML = logs.map(a=>`
      <tr><td class="mono" style="font-size:12px">${esc(a.created_at)}</td>
      <td><b>${esc(a.username||"-")}</b></td>
      <td><span class="badge ${ACTION_COLOR[a.action]||"stopped"}"><span class="dot"></span>${esc(a.action)}</span></td>
      <td>${esc(a.target)&&a.target!=="system"?`<span class="tag">${esc(a.target)}</span>`:'<span style="color:var(--muted)">system</span>'}</td>
      <td style="color:var(--muted)">${esc(a.detail)||"—"}</td>
      <td class="mono" style="font-size:12px">${esc(a.ip)||"—"}</td></tr>`).join("")
      || `<tr><td colspan="6" class="empty">暂无日志</td></tr>`;
  }catch(e){}
}

/* ══════════════ 视图：设置 ══════════════ */
async function viewSettings(){
  let nodesInfo = {total:0, online:0};
  try{ const ns=await api("/nodes");
    nodesInfo = {total:ns.length, online:ns.filter(n=>n.status==="online").length};
  }catch(e){}
  const isAdmin = state.user.role === "admin";

  // 加载 Telegram 配置
  let tgCfg = {bot_token:"", chat_id:"", enabled:false, events:"node_offline,container_crash"};
  try{ tgCfg = await api("/notify/settings"); }catch(e){}

  // 加载备份配置
  let bkCfg = {backup_enabled:"0", backup_interval_hours:"24", backup_type:"s3",
               backup_endpoint:"", backup_region:"us-east-1", backup_bucket:"nexpanel-backup",
               backup_access_key:"", backup_secret_key:"", backup_retention_days:"30",
               backup_last_run:"", backup_last_result:""};
  try{ bkCfg = await api("/backup/settings"); }catch(e){}

  $("#content").innerHTML = `
  <div class="grid stat-grid" style="grid-template-columns:repeat(auto-fit,minmax(300px,1fr))">
    <div class="card"><h4><span class="dot"></span>运行环境</h4>
      <dl class="kv">
        <dt>面板版本</dt><dd>NexPanel ${esc(state.meta?.version||"v0.2.0")}</dd>
        <dt>架构模式</dt><dd><span style="color:var(--ok)">中心面板 · SSH 多节点</span></dd>
        <dt>接入节点</dt><dd>${nodesInfo.online} 在线 / 共 ${nodesInfo.total}</dd>
        <dt>数据库</dt><dd>SQLite · data/panel.db</dd>
        <dt>令牌有效期</dt><dd>7 天</dd>
      </dl>
      <p style="color:var(--muted);font-size:12.5px;margin-top:14px;line-height:1.8">
        面板可安装在任何服务器上；LXC 运行在被接入的目标节点。<br>
        SSH 凭据经面板密钥（Fernet）加密后入库。</p>
    </div>
    <div class="card"><h4><span class="dot"></span>修改当前账号密码</h4>
      <div class="form-grid" style="grid-template-columns:1fr">
        <label>原密码<input id="pw-old" type="password"></label>
        <label>新密码<input id="pw-new" type="password" placeholder="至少 6 位"></label>
        <label>确认新密码<input id="pw-new2" type="password"></label>
      </div>
      <button class="btn primary" id="pw-save" style="margin-top:14px">保存修改</button>
    </div>
    ${isAdmin ? `
    <div class="card"><h4><span class="dot" style="background:#34d399"></span>🤖 Telegram 告警</h4>
      <div class="form-grid" style="grid-template-columns:1fr">
        <label>Bot Token<input id="tg-token" value="${esc(tgCfg.bot_token)}" placeholder="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"></label>
        <label>目标 Chat ID<input id="tg-chat" value="${esc(tgCfg.chat_id)}" placeholder="群组 / 用户 ID（数字）"></label>
        <label>告警事件<select id="tg-events" style="margin-top:4px">
          <option value="node_offline,container_crash" ${tgCfg.events==="node_offline,container_crash"?"selected":""}>离线 + 容器异常</option>
          <option value="all" ${tgCfg.events==="all"?"selected":""}>全部事件</option>
          <option value="node_offline" ${tgCfg.events==="node_offline"?"selected":""}>仅节点离线</option>
          <option value="node_offline,container_crash,backup_fail" ${tgCfg.events==="node_offline,container_crash,backup_fail"?"selected":""}>离线 + 容器 + 备份</option>
        </select></label>
        <label style="flex-direction:row;align-items:center;gap:8px;margin-top:6px">
          <input type="checkbox" id="tg-enable" ${tgCfg.enabled?"checked":""} style="width:18px;height:18px">
          <span>启用 Telegram 告警</span>
        </label>
      </div>
      <div style="display:flex;gap:8px;margin-top:12px">
        <button class="btn primary" id="tg-save">保存</button>
        <button class="btn" id="tg-test">测试发送</button>
      </div>
    </div>
    <div class="card"><h4><span class="dot" style="background:#fbbf24"></span>💾 自动备份</h4>
      <div class="form-grid" style="grid-template-columns:1fr">
        <label style="flex-direction:row;align-items:center;gap:8px">
          <input type="checkbox" id="bk-enable" ${bkCfg.backup_enabled?"checked":""} style="width:18px;height:18px">
          <span>启用自动备份</span>
        </label>
        <label>备份间隔（小时）
          <input id="bk-interval" type="number" value="${esc(bkCfg.backup_interval_hours||"24")}" min="1" max="720">
        </label>
        <label>存储类型
          <select id="bk-type">
            <option value="s3" ${bkCfg.backup_type==="s3"?"selected":""}>S3 兼容存储</option>
            <option value="webdav" ${bkCfg.backup_type==="webdav"?"selected":""}>WebDAV</option>
          </select>
        </label>
        <label>Endpoint / URL
          <input id="bk-endpoint" value="${esc(bkCfg.backup_endpoint)}" placeholder="https://s3.amazonaws.com">
        </label>
        <label>Region
          <input id="bk-region" value="${esc(bkCfg.backup_region||"us-east-1")}" placeholder="us-east-1">
        </label>
        <label>Bucket / 路径
          <input id="bk-bucket" value="${esc(bkCfg.backup_bucket||"nexpanel-backup")}" placeholder="nexpanel-backup">
        </label>
        <label>Access Key / 用户名
          <input id="bk-ak" value="${esc(bkCfg.backup_access_key)}" placeholder="S3 Access Key / WebDAV 用户名">
        </label>
        <label>Secret Key / 密码
          <input id="bk-sk" type="password" value="${esc(bkCfg.backup_secret_key)}" placeholder="S3 Secret Key / WebDAV 密码">
        </label>
        <label>保留天数
          <input id="bk-retention" type="number" value="${esc(bkCfg.backup_retention_days||"30")}" min="0" max="365">
        </label>
      </div>
      <div style="display:flex;gap:8px;margin-top:12px;align-items:center;flex-wrap:wrap">
        <button class="btn primary" id="bk-save">保存</button>
        <button class="btn" id="bk-run">立即备份</button>
        <button class="btn warn" id="bk-restore">↩ 恢复备份</button>
        <span style="color:var(--muted);font-size:12px">
          ${bkCfg.backup_last_run ? `上次：${esc(bkCfg.backup_last_run)}` : '尚未执行过'}
          ${bkCfg.backup_last_result ? ` · 结果：${bkCfg.backup_last_result === 'ok' ? '✅ 成功' : '❌ ' + esc(bkCfg.backup_last_result)}` : ''}
        </span>
      </div>
      <input type="file" id="bk-restore-file" accept=".tar.gz,.tgz" style="display:none">
    </div>
    ` : ""}
    ${isAdmin ? `
    <div class="card"><h4><span class="dot" style="background:#38bdf8"></span>🔁 订阅转换</h4>
      <p style="color:var(--muted);font-size:12.5px;margin-bottom:10px">导入其他机场/面板的订阅，自动转成 Clash / V2Ray 订阅地址，直接填进客户端即可。</p>
      <div id="subconv-list" style="display:flex;flex-direction:column;gap:10px"></div>
      <div class="form-grid" style="grid-template-columns:1fr 2fr;margin-top:12px">
        <input class="input" id="subconv-name" placeholder="名称（如 机场A）">
        <input class="input" id="subconv-url" placeholder="https://机场订阅链接（粘贴多行节点内容也行）">
      </div>
      <div style="display:flex;gap:8px;margin-top:8px;flex-wrap:wrap">
        <button class="btn primary" id="btn-subconv-add">＋ 导入</button>
        <button class="btn ghost" id="btn-subconv-preview">粘贴内容预览（不保存）</button>
      </div>
    </div>
    <div class="card" style="border-color:rgba(239,68,68,.35)">
      <h4><span class="dot" style="background:var(--err)"></span>危险操作</h4>
      <p style="color:var(--muted);font-size:12.5px;margin-bottom:14px">
        清空所有节点上的全部实例与快照记录（保留节点、用户与模板）。</p>
      <button class="btn danger" id="reset-demo">${icon("rotate",13)} 清空全部实例数据</button>
    </div>`:""}
  </div>`;
  $("#pw-save").onclick = async ()=>{
    const o=$("#pw-old").value, n1=$("#pw-new").value, n2=$("#pw-new2").value;
    if(n1!==n2) return toast("两次输入的新密码不一致","err");
    try{ await api("/me/password",{method:"POST",body:{old_password:o,new_password:n1}});
      toast("密码修改成功","ok"); $("#pw-old").value=$("#pw-new").value=$("#pw-new2").value=""; }
    catch(e){ toast(e.message,"err"); }
  };

  // Telegram 配置
  const tgSave = $("#tg-save");
  if(tgSave) tgSave.onclick = async ()=>{
    try{
      await api("/notify/settings", {method:"POST", body:{
        bot_token: $("#tg-token").value.trim(),
        chat_id: $("#tg-chat").value.trim(),
        enabled: $("#tg-enable").checked,
        events: $("#tg-events").value,
      }});
      toast("Telegram 告警配置已保存","ok"); viewSettings();
    }catch(e){ toast(e.message,"err"); }
  };
  const tgTest = $("#tg-test");
  if(tgTest) tgTest.onclick = async ()=>{
    try{
      await api("/notify/test", {method:"POST", body:{
        bot_token: $("#tg-token").value.trim(),
        chat_id: $("#tg-chat").value.trim(),
      }});
      toast("测试消息已发送，请检查 Telegram","ok",5000);
    }catch(e){ toast(e.message,"err",5000); }
  };

  // 备份配置
  const bkSave = $("#bk-save");
  if(bkSave) bkSave.onclick = async ()=>{
    try{
      await api("/backup/settings", {method:"POST", body:{
        enabled: $("#bk-enable").checked,
        interval_hours: parseInt($("#bk-interval").value) || 24,
        type: $("#bk-type").value,
        endpoint: $("#bk-endpoint").value.trim(),
        region: $("#bk-region").value.trim(),
        bucket: $("#bk-bucket").value.trim(),
        access_key: $("#bk-ak").value.trim(),
        secret_key: $("#bk-sk").value.trim(),
        retention_days: parseInt($("#bk-retention").value) || 30,
      }});
      toast("备份配置已保存","ok"); viewSettings();
    }catch(e){ toast(e.message,"err"); }
  };
  const bkRun = $("#bk-run");
  if(bkRun) bkRun.onclick = async ()=>{
    bkRun.disabled=true; bkRun.textContent="备份中…";
    const btn = bkRun;
    try{
      const r = await api("/backup/run", {method:"POST"});
      toast(r.message||"备份完成","ok",5000); viewSettings();
    }catch(e){ toast(e.message,"err",5000); }
    btn.disabled=false; btn.textContent="立即备份";
  };

  // 恢复备份：选择本地 .tar.gz 文件上传，覆盖当前数据库
  const bkRestore = $("#bk-restore");
  const bkRestoreFile = $("#bk-restore-file");
  if(bkRestore && bkRestoreFile){
    bkRestore.onclick = ()=>{
      bkRestoreFile.value = "";
      bkRestoreFile.click();
    };
    bkRestoreFile.onchange = async ()=>{
      const file = bkRestoreFile.files && bkRestoreFile.files[0];
      if(!file) return;
      if(!(await confirmModal(
        `<p>⚠️ 确定从备份文件 <b>${esc(file.name)}</b> 恢复数据库？</p>
        <p style="color:var(--muted);font-size:12px;margin-top:8px">
        当前数据库将被覆盖，恢复前会自动备份当前数据到 data/panel.db.bak.*。<br>
        建议恢复完成后重启面板服务。</p>`, true))) { bkRestoreFile.value=""; return; }
      const fd = new FormData();
      fd.append("file", file);
      const btn = bkRestore;
      btn.disabled = true; btn.textContent = "恢复中…";
      try{
        const r = await fetch("/api/backup/restore", {
          method:"POST",
          headers:{ Authorization: "Bearer "+state.token },
          body: fd,
        });
        const data = await r.json().catch(()=>({}));
        if(!r.ok) throw new Error(data.detail || `恢复失败(${r.status})`);
        toast(data.message || "恢复成功，建议重启面板","ok",6000);
        setTimeout(()=>location.reload(), 800);
      }catch(e){ toast(e.message,"err",6000); }
      btn.disabled = false; btn.textContent = "↩ 恢复备份";
      bkRestoreFile.value = "";
    };
  }


  // 订阅转换
  const subconvList = $("#subconv-list");
  if(subconvList){
    const loadSubConv = async ()=>{
      try{
        const list = await api("/conv/sources");
        subconvList.innerHTML = list.length ? list.map(s=>`
          <div style="display:flex;flex-direction:column;gap:6px;background:var(--panel-2);border:1px solid var(--line);border-radius:10px;padding:10px 12px">
            <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
              <b>${esc(s.name)}</b>
              <span class="tag">${s.node_count} 节点</span>
              ${s.error?`<span style="color:var(--err);font-size:12px">${esc(s.error)}</span>`:""}
              <span class="spacer"></span>
              <button class="btn sm ghost" data-subconv-refresh="${s.id}">${icon("rotate",12)} 刷新</button>
              <button class="btn sm warn" data-subconv-del="${s.id}">${icon("trash",12)} 删除</button>
            </div>
            <div style="display:flex;flex-wrap:wrap;gap:6px;align-items:center">
              <input class="input mono" readonly value="${esc(s.clash_url)}" onclick="this.select()" style="flex:1;min-width:170px;font-size:12px">
              <button class="btn sm" data-copy="${esc(s.clash_url)}">复制 Clash</button>
              <input class="input mono" readonly value="${esc(s.v2ray_url)}" onclick="this.select()" style="flex:1;min-width:170px;font-size:12px">
              <button class="btn sm" data-copy="${esc(s.v2ray_url)}">复制 V2Ray</button>
            </div>
          </div>`).join("") : `<span class="empty">还没有订阅源，贴一个机场链接或点“粘贴内容预览”</span>`;
        subconvList.querySelectorAll("[data-subconv-refresh]").forEach(b=>b.onclick=async ()=>{
          try{ await api(`/conv/sources/${b.dataset.subconvRefresh}/refresh`,{method:"POST"}); toast("已刷新","ok"); loadSubConv(); }catch(e){ toast(e.message,"err"); }
        });
        subconvList.querySelectorAll("[data-subconv-del]").forEach(b=>b.onclick=async ()=>{
          if(!(await confirmModal("删除该订阅源？转换链接将立即失效。",true))) return;
          try{ await api(`/conv/sources/${b.dataset.subconvDel}`,{method:"DELETE"}); toast("已删除","ok"); loadSubConv(); }catch(e){ toast(e.message,"err"); }
        });
        subconvList.querySelectorAll("[data-copy]").forEach(b=>b.onclick=()=>copyText(b.dataset.copy));
      }catch(e){}
    };
    $("#btn-subconv-add").onclick = async ()=>{
      const name=$("#subconv-name").value.trim();
      const url=$("#subconv-url").value.trim();
      if(!name && !url) return toast("请填名称或订阅链接","err");
      try{
        const r = await api("/conv/sources",{method:"POST",body:{name,url,content:""}});
        if(r.node_count) toast(`导入成功：${r.node_count} 个节点`,"ok",4000);
        else toast(r.error||"未解析到节点","err",5000);
        $("#subconv-name").value=""; $("#subconv-url").value="";
        loadSubConv();
      }catch(e){ toast(e.message,"err"); }
    };
    $("#btn-subconv-preview").onclick = async ()=>{
      const content=$("#subconv-url").value.trim();
      if(!content) return toast("请先在上面的输入框粘贴订阅内容或链接","err");
      try{
        const r = await api("/conv/preview",{method:"POST",body:{content}});
        openModal("订阅解析预览", `
          <p>识别到 <b>${r.node_count}</b> 个节点</p>
          <div class="term" style="height:auto;max-height:280px;overflow:auto;font-size:12px">${(r.names||[]).map(x=>`<div>· ${esc(x)}</div>`).join("")||'<div style="color:var(--muted)">暂无</div>'}</div>
          <p style="color:var(--muted);font-size:11.5px;margin-top:8px">这是临时预览，不保存。确认可用后点「导入」即可生成 Clash / V2Ray 订阅链接。</p>`, closeModal, "关闭");
      }catch(e){ toast(e.message,"err"); }
    };
    loadSubConv();
  }

  const rd = $("#reset-demo");
  if(rd) rd.onclick = async ()=>{
    if(!(await confirmModal("⚠ 确定清空所有节点上的全部实例与快照？",true))) return;
    try{ await api("/admin/reset-instances",{method:"POST"}); toast("已清空全部实例数据","ok");
      setTimeout(()=>location.reload(), 800); }
    catch(e){ toast(e.message,"err"); }
  };
}

/* ══════════════ 视图：流量统计 ══════════════ */
async function viewTraffic(){
  const isAdmin = state.user.role === "admin";
  $("#content").innerHTML = `
    <div class="page-head">
      <span class="sub">节点流量统计 · 最近 30 天</span>
      <span class="spacer"></span>
      <button class="btn" id="tf-refresh">${icon("rotate",13)} 刷新</button>
    </div>
    <div class="card" style="padding:6px 12px"><div class="table-wrap"><table>
      <thead><tr><th>节点名称</th><th>类型</th><th>下载 (RX)</th><th>上传 (TX)</th><th>合计</th></tr></thead>
      <tbody id="tf-body"><tr><td colspan="5" class="empty">加载中…</td></tr></tbody>
    </table></div></div>
    <div style="margin-top:16px" class="grid stat-grid" style="grid-template-columns:repeat(auto-fit,minmax(300px,1fr))">
      <div class="card"><h4><span class="dot" style="background:var(--ok)"></span>每日流量明细</h4>
        <div class="table-wrap" style="max-height:400px;overflow-y:auto"><table>
          <thead><tr><th>日期</th><th>节点</th><th>RX</th><th>TX</th></tr></thead>
          <tbody id="tf-daily"></tbody>
        </table></div>
      </div>
    </div>`;

  const load = async ()=>{
    try{
      const list = await api("/traffic/nodes");
      let totalRx=0, totalTx=0;
      $("#tf-body").innerHTML = list.map(n=>{
        totalRx += n.total_rx_mb; totalTx += n.total_tx_mb;
        return `<tr>
          <td><b>${esc(n.name)}</b></td>
          <td><span class="badge">节点 #${n.node_id}</span></td>
          <td class="mono">${fmtGB(n.total_rx_mb)}</td>
          <td class="mono">${fmtGB(n.total_tx_mb)}</td>
          <td class="mono"><b>${fmtGB(n.total_mb)}</b></td>
        </tr>`;
      }).join("") + `<tr style="font-weight:bold;border-top:2px solid var(--border)">
        <td colspan="2">总计</td>
        <td class="mono">${fmtGB(totalRx)}</td>
        <td class="mono">${fmtGB(totalTx)}</td>
        <td class="mono">${fmtGB(totalRx+totalTx)}</td>
      </tr>`;
    }catch(e){ $("#tf-body").innerHTML=`<tr><td colspan="5" class="empty">${esc(e.message)}</td></tr>`; }

    // 加载每日明细
    try{
      const today = new Date().toISOString().slice(0,10);
      const daily = await api("/traffic/daily?date="+today);
      $("#tf-daily").innerHTML = daily.map(d=>
        `<tr><td class="mono">${esc(d.date)}</td>
        <td>${esc(d.name||"#"+d.node_id)}</td>
        <td class="mono">${fmtGB(d.rx_bytes/1048576)}</td>
        <td class="mono">${fmtGB(d.tx_bytes/1048576)}</td></tr>`
      ).join("") || `<tr><td colspan="4" class="empty">暂无数据</td></tr>`;
    }catch(e){ $("#tf-daily").innerHTML=`<tr><td colspan="4" class="empty">${esc(e.message)}</td></tr>`; }
  };
  load();
  $("#tf-refresh").onclick = load;
}

/* ══════════════ 弹窗框架 ══════════════ */
function openModal(title, bodyHTML, onOk, okText="确定", opts={}){
  const ov = document.createElement("div");
  ov.className="overlay"; ov.dataset.modal="1";
  ov.innerHTML = `
    <div class="modal ${opts.wide?"wide":""}">
      <div class="modal-head"><h3>${title}</h3>
        <button class="modal-x" data-x>&times;</button></div>
      <div class="modal-body">${bodyHTML}</div>
      <div class="modal-foot">
        <button class="btn ghost" data-x>取消</button>
        <button class="btn primary" data-ok>${okText}</button>
      </div>
    </div>`;
  if(opts.onclose) ov._onclose = opts.onclose;
  document.getElementById("modals").appendChild(ov);
  // 只关闭/移除自己这一层弹窗，不影响其他层叠打开的弹窗
  const closeSelf = ()=>{ try{ ov._onclose && ov._onclose(); }catch(e){} ov.remove(); };
  ov.addEventListener("click", e=>{ if(e.target===ov) closeSelf(); });
  ov.querySelectorAll("[data-x]").forEach(b=>b.onclick=closeSelf);
  if(onOk) ov.querySelector("[data-ok]").onclick = onOk;
  return ov;
}
function closeModal(){
  $$("#modals .overlay").forEach(o=>{
    try{ o._onclose && o._onclose(); }catch(e){}
    o.remove();
  });
}

function confirmModal(msgHTML, danger=false){
  return new Promise(resolve=>{
    let done = false;   // 防止 resolve 多次触发
    const finish = v =>{ if(done) return; done=true; resolve(v); };
    const ov = openModal("请确认", `<p style="font-size:13.5px;line-height:1.8">${msgHTML}</p>`,
      ()=>{ ov.remove(); finish(true); }, danger?"确认执行":"确定");
    if(danger) ov.querySelector("[data-ok]").className="btn danger";
    // 只关闭/移除自己这一层，不影响底下还开着的弹窗（如 Swap 管理窗口）
    ov.querySelectorAll("[data-x]").forEach(b=>{
      b.removeEventListener("click", window._noop||(()=>{}));
      b.addEventListener("click", ()=>{ ov.remove(); finish(false); });
    });
    ov.addEventListener("click", e=>{ if(e.target===ov){ ov.remove(); finish(false); } });
  });
}

/* ══════════════ WebSocket 终端（原始模式 + 轻量 ANSI 渲染） ══════════════ */
function closeWS(){ if(wsRef){ try{ wsRef.close(); }catch(e){} wsRef=null; } }

/* 迷你终端仿真器：字符网格 + 常用 ANSI/VT 序列 */
class MiniTerm {
  /* 行内容用单调递增 id 标记，html 渲染按 id 缓存：
     只有真正变化的行才重新生成字符串/DOM —— 空闲时零渲染开销（移动端卡顿修复） */
  constructor(el, cols=120, rows=32){
    this.el = el; this.cols = cols; this.rows = rows;
    this.grid = []; this.cr = 0; this.cc = 0;
    this.fg = ""; this.bold = false;
    this.alt = null;
    for(let r=0;r<rows;r++) this.grid.push(new Array(cols).fill(null));
    this.verSeq = 0;
    this.rowVer = new Array(rows).fill(0);   // 行号 -> 内容 id
    this._htmlMap = new Map();               // 内容 id -> 已渲染 html
    this._dirtySet = null;                   // feed 过程中收集被写的行
  }
  resize(cols, rows){
    this.cols = cols; this.rows = rows;
    const ng = [];
    for(let r=0;r<rows;r++){
      const src = this.grid[r] || [];
      const line = new Array(cols).fill(null);
      for(let c=0;c<Math.min(cols, src.length);c++) line[c]=src[c];
      ng.push(line);
    }
    this.grid = ng; this.cr = Math.min(this.cr, rows-1); this.cc = Math.min(this.cc, cols-1);
    this._bumpAll();
  }
  clear(){ for(let r=0;r<this.rows;r++) this.grid[r].fill(null); this.cr=0; this.cc=0; this._bumpAll(); }
  _bumpAll(){
    const v = ++this.verSeq;
    this.rowVer = new Array(this.rows).fill(v);
    if(this._htmlMap.size > 64) this._htmlMap.clear();   // 全量失效后旧缓存无保留价值
  }
  _touchDirty(){                        // feed 结束统一结算：每行只分配一个新 id
    if(!this._dirtySet) return;
    for(const r of this._dirtySet){
      if(r>=0 && r<this.rows) this.rowVer[r] = ++this.verSeq;
    }
    this._dirtySet.clear();
  }
  _put(ch){
    if(this.cc >= this.cols){ this.cc = 0; this._lf(); }
    if(this.cr >= this.rows) this.cr = this.rows-1;
    if(!this._dirtySet) this._dirtySet = new Set();
    this._dirtySet.add(this.cr);
    this.grid[this.cr][this.cc] = { ch, fg:this.fg, b:this.bold };
    this.cc++;
  }
  _lf(){
    if(this.cr >= this.rows-1){
      // 屏幕滚动：网格与内容 id 数组同步上移，未变行仍能命中 id 缓存
      this.grid.shift(); this.grid.push(new Array(this.cols).fill(null));
      this.rowVer.shift(); this.rowVer.push(++this.verSeq);
    }
    else this.cr++;
  }
  _sgr(ps){
    for(const n of ps){
      if(n===0){ this.fg=""; this.bold=false; }
      else if(n===1) this.bold=true;
      else if(n===22) this.bold=false;
      else if((n>=30&&n<=37)||n===39||(n>=90&&n<=97)){
        // 两套调色板：深色终端用亮字，浅色终端用可读的深色变体
        const dark={30:"#64748b",31:"#ef4444",32:"#22c55e",33:"#eab308",34:"#3b82f6",35:"#d946ef",36:"#06b6d4",37:"#e2e8f0",90:"#94a3b8",91:"#f87171",92:"#4ade80",93:"#facc15",94:"#60a5fa",95:"#e879f9",96:"#22d3ee",97:"#f1f5f9"};
        const lite={30:"#334155",31:"#dc2626",32:"#16a34a",33:"#b45309",34:"#2563eb",35:"#9333ea",36:"#0891b2",37:"#64748b",90:"#64748b",91:"#ef4444",92:"#15803d",93:"#d97706",94:"#4f46e5",95:"#c026d3",96:"#0e7490",97:"#1e293b"};
        const map = document.documentElement.classList.contains("light") ? lite : dark;
        this.fg = n===39 ? "" : (map[n]||"");
      }
    }
  }
  feed(text){
    let i = 0;
    while(i < text.length){
      const ch = text[i];
      if(ch === "\x1b"){
        // CSI / OSC / ESC 序列
        if(text[i+1] === "["){
          let j = i+2;
          while(j < text.length && !/[A-Za-z@]/.test(text[j])) j++;
          if(j >= text.length) break;
          const seq = text.slice(i+2, j), fin = text[j]; i = j+1;
          const ps = seq.split(";").map(x=>parseInt(x)||0);
          switch(fin){
            case "A": this.cr = Math.max(0, this.cr-(ps[0]||1)); break;
            case "B": this.cr = Math.min(this.rows-1, this.cr+(ps[0]||1)); break;
            case "C": this.cc = Math.min(this.cols-1, this.cc+(ps[0]||1)); break;
            case "D": this.cc = Math.max(0, this.cc-(ps[0]||1)); break;
            case "E": this.cr = Math.min(this.rows-1, this.cr+(ps[0]||1)); this.cc=0; break;
            case "F": this.cr = Math.max(0, this.cr-(ps[0]||1)); this.cc=0; break;
            case "G": this.cc = Math.min(this.cols-1, Math.max(0,(ps[0]||1)-1)); break;
            case "H": case "f":
              this.cr = Math.min(this.rows-1, Math.max(0,(ps[0]||1)-1));
              this.cc = Math.min(this.cols-1, Math.max(0,(ps[1]||1)-1)); break;
            case "J":
              if(!this._dirtySet) this._dirtySet = new Set();
              if(!ps[0]||ps[0]===0){ for(let c=this.cc;c<this.cols;c++) this.grid[this.cr][c]=null;
                this._dirtySet.add(this.cr);
                for(let r=this.cr+1;r<this.rows;r++){ this.grid[r].fill(null); this._dirtySet.add(r); } }
              else { for(let r=0;r<this.rows;r++) this.grid[r].fill(null); this._bumpAll(); }
              break;
            case "K":
              if(!this._dirtySet) this._dirtySet = new Set();
              if(!ps[0]){ for(let c=this.cc;c<this.cols;c++) this.grid[this.cr][c]=null; }
              else if(ps[0]===1){ for(let c=0;c<=this.cc;c++) this.grid[this.cr][c]=null; }
              else this.grid[this.cr].fill(null);
              this._dirtySet.add(this.cr);
              break;
            case "m": this._sgr(seq===""?[0]:ps); break;
            case "h": case "l":
              if(/1049|1047|1048/.test(seq)){   // 备选屏幕：直接清屏
                this.clear();
              }
              break;
            default: break;
          }
        } else if(text[i+1] === "]"){           // OSC: 跳过直到 BEL/ST
          let j = text.indexOf("\x07", i+2);
          const st = text.indexOf("\x1b\\", i+2);
          if(j === -1 && st !== -1) j = st+1;
          if(j === -1){ break; }                // 不完整，丢弃剩余
          i = j+1;
        } else {
          i += 2;                               // 其他两字节转义忽略
        }
      } else if(ch === "\r"){ this.cc = 0; i++; }
      else if(ch === "\n"){ this._lf(); i++; }
      else if(ch === "\b" || ch === "\x7f"){ this.cc = Math.max(0, this.cc-1); i++; }
      else if(ch === "\t"){
        const nxt = Math.min(this.cols-1, (Math.floor(this.cc/8)+1)*8);
        while(this.cc < nxt){ this._put(" "); }
        i++;
      } else if(ch === "\x07"){ i++; }
      else if(ch < " "){ i++; }
      else {
        // UTF-8 多字节字符按码点处理
        const cp = text.codePointAt(i);
        const width = String.fromCodePoint(cp);
        this._put(width);
        if(cp > 0xFFFF){                        // 代理对占两列
          if(this.cc < this.cols) this.grid[this.cr][this.cc] = {ch:"",fg:"",b:false};
          this.cc++;
        }
        i += width.length;
      }
    }
    this._touchDirty();
  }
  /* 渲染一行（caretCol>=0 时在该列插入光标；带光标的行不进缓存） */
  lineHTML(r, caretCol=-1){
    const id = this.rowVer[r];
    let cached;
    if(caretCol < 0 && (cached = this._htmlMap.get(id)) !== undefined) return cached;
    const row = this.grid[r];
    const parts = [];
    let run = "", cfg = "", cb = false;
    const flush = ()=>{
      if(run){
        const style = cfg ? `color:${cfg}` : "";
        parts.push((style||cb) ? `<span style="${style}${cb?";font-weight:600":""}">${run}</span>` : run);
      }
      run = "";
    };
    for(let c=0;c<this.cols;c++){
      if(c === caretCol){ flush(); parts.push(`<span class="t-caret"></span>`); }
      const cell = row[c];
      const f = cell ? cell.fg : "", b = cell ? cell.b : false;
      if(f!==cfg || b!==cb){ flush(); cfg=f; cb=b; }
      run += (cell && cell.ch) ? esc(cell.ch) : " ";
    }
    flush();
    const html = parts.join("");
    if(caretCol < 0){
      this._htmlMap.set(id, html);
      if(this._htmlMap.size > 512){               // 防止 id 无限增长
        this._htmlMap.delete(this._htmlMap.keys().next().value);
      }
    }
    return html;
  }
}

/* 终端弹窗通用骨架：raw 按键 → JSON 信封；输出 → MiniTerm 渲染 */
function openTermModal(title, wsUrl, opts={}){
  const ov = openModal(`<span style="display:inline-flex;gap:8px;align-items:center">
      ${icon("term",16)} ${esc(title)}</span>`,
    `<div class="term" id="term-out" style="overflow:auto"></div>
     <textarea id="term-input" autocomplete="off" autocorrect="off" autocapitalize="off" spellcheck="false"
       style="position:fixed;left:-9999px;top:0;width:1px;height:1px;opacity:0;border:0;padding:0;outline:none;resize:none;font-size:16px"></textarea>
     <p class="sub" style="color:var(--muted);font-size:11.5px;margin-top:8px">
       原始终端模式：支持 <code>Ctrl+C</code> / <code>Ctrl+L</code> / 方向键 / Tab 补全，
       可直接运行 <code>top</code> 等全屏程序。点击终端区域获取焦点（手机可唤起键盘）。</p>`,
    null, "", { wide:true, onclose: ()=>{
      closeWS(); clearInterval(repaint); clearTimeout(rsTimer);
      window.removeEventListener("keydown", keyHandler, true);
      window.removeEventListener("resize", onViewportResize);
      if(window.visualViewport) window.visualViewport.removeEventListener("resize", onViewportResize);
    } });
  ov.querySelector(".modal-foot").remove();

  const out = ov.querySelector("#term-out");
  const input = ov.querySelector("#term-input");
  out.style.whiteSpace = "pre";
  out.style.fontFamily = "var(--mono)";
  out.style.fontSize = "12px";
  out.tabIndex = 0;

  const term = new MiniTerm(out, 120, 32);
  let repaint = null;
  let dirtyTerm = true;                 // 脏标记：仅内容变化时才重绘（空闲零开销）
  let lineEls = [];                     // 每行一个 <div.t-line>，行级增量更新

  const buildRows = ()=>{
    out.textContent = ""; lineEls = [];
    for(let r=0;r<term.rows;r++){
      const d = document.createElement("div");
      d.className = "t-line"; d._h = null;
      out.appendChild(d); lineEls.push(d);
    }
  };
  buildRows();

  const sendRaw = data =>{ if(wsRef && wsRef.readyState===1)
    wsRef.send(JSON.stringify({type:"input", data})); };
  const doResize = ()=>{
    const cw = measure(), rect = out.getBoundingClientRect();
    const cols = Math.max(40, Math.min(500, Math.floor(rect.width/cw.w)));
    const rows = Math.max(8, Math.min(300, Math.floor(rect.height/cw.h)));
    if(cols===term.cols && rows===term.rows) return;
    term.resize(cols, rows);
    buildRows();                        // 行数变化 → 重建行元素
    dirtyTerm = true;
    if(wsRef && wsRef.readyState===1)
      wsRef.send(JSON.stringify({type:"resize", cols, rows}));
  };

  function measure(){
    const probe = document.createElement("span");
    probe.textContent = "M".repeat(20);
    probe.style.cssText = "position:absolute;visibility:hidden;font-family:var(--mono);font-size:12px;white-space:pre";
    document.body.appendChild(probe);
    const w = probe.getBoundingClientRect().width/20, h = 18;
    probe.remove();
    return {w, h};
  }

  /* 只重绘变化的行：光标所在行每次重建（带 caret），其余按内容 id 命中缓存 */
  const paint = ()=>{
    if(!ov.isConnected){ clearInterval(repaint); return; }
    if(!dirtyTerm || document.hidden) return;
    dirtyTerm = false;
    const atBottom = out.scrollTop + out.clientHeight >= out.scrollHeight - 24;
    for(let r=0;r<term.rows;r++){
      const h = (r===term.cr) ? term.lineHTML(r, term.cc) : term.lineHTML(r);
      const el = lineEls[r];
      if(el._h !== h){ el._h = h; el.innerHTML = h; }
    }
    if(atBottom) out.scrollTop = out.scrollHeight;
  };
  repaint = setInterval(paint, 120);

  // 视口变化（旋转/软键盘弹出）→ 防抖重新适配终端尺寸
  let rsTimer = null;
  const onViewportResize = ()=>{
    clearTimeout(rsTimer);
    rsTimer = setTimeout(()=>{ if(ov.isConnected){ doResize(); paint(); } }, 250);
  };
  window.addEventListener("resize", onViewportResize);
  if(window.visualViewport) window.visualViewport.addEventListener("resize", onViewportResize);

  function keyHandler(e){
    if(wsRef !== ws || !ov.isConnected) return;
    if(document.activeElement !== input && !out.contains(document.activeElement)) return;
    const k = e.key;
    let data = null;
    if(k === "Enter") data = "\r";
    else if(k === "Backspace") data = "\x7f";
    else if(k === "Tab") data = "\t";
    else if(k === "Escape") data = "\x1b";
    else if(k === "ArrowUp") data = "\x1b[A";
    else if(k === "ArrowDown") data = "\x1b[B";
    else if(k === "ArrowRight") data = "\x1b[C";
    else if(k === "ArrowLeft") data = "\x1b[D";
    else if(k === "Home") data = "\x1b[H";
    else if(k === "End") data = "\x1b[F";
    else if(k === "Delete") data = "\x1b[3~";
    else if(k === "PageUp") data = "\x1b[5~";
    else if(k === "PageDown") data = "\x1b[6~";
    else if(e.ctrlKey && !e.altKey && !e.metaKey && k.length===1){
      const key = k.toLowerCase();
      // Ctrl+V：不拦截，交给浏览器默认粘贴（textarea 的 input 事件会把内容发给终端）
      if(key === "v") return;
      // Ctrl+C：终端里有选中文本时走浏览器复制；没有选中才发送中断信号
      if(key === "c" && window.getSelection && window.getSelection().toString()){
        e.preventDefault(); e.stopPropagation();
        try{ document.execCommand("copy"); }catch(_){}
        return;
      }
      const c = k.toUpperCase().charCodeAt(0)-64;
      if(c > 0 && c < 27) data = String.fromCharCode(c);
    }
    // 普通可打印字符不在这里处理，交给 input 事件（兼容手机键盘/中文输入法）
    if(data !== null){
      e.preventDefault(); e.stopPropagation();
      input.value = "";
      sendRaw(data);
    }
  }

  // 手机/触屏键盘：通过 textarea 的 input 事件发送新增字符
  let composing = false;
  let lastInput = "";
  input.addEventListener("compositionstart", ()=>{ composing = true; });
  input.addEventListener("compositionend", (e)=>{
    composing = false;
    const d = e.data || "";
    if(d){ sendRaw(d); }
    input.value = ""; lastInput = "";
  });
  input.addEventListener("input", ()=>{
    if(composing) return;
    const v = input.value;
    const diff = v.startsWith(lastInput) ? v.slice(lastInput.length) : v;
    if(diff) sendRaw(diff);
    input.value = ""; lastInput = "";
  });
  input.addEventListener("keydown", keyHandler);

  window.addEventListener("keydown", keyHandler, true);
  out.addEventListener("click", ()=>{
    // 终端里有选中的文字时先不抢焦点，方便 Ctrl+C 复制；再次点击才进入输入
    if(window.getSelection && window.getSelection().toString()) return;
    input.focus();
  });

  const proto = location.protocol==="https:"?"wss":"ws";
  const ws = new WebSocket(`${proto}://${location.host}${wsUrl}`);
  wsRef = ws;
  ws.onopen = ()=>{ input.focus(); doResize(); dirtyTerm = true; paint(); };
  ws.onmessage = ev=>{
    let m; try{ m = JSON.parse(ev.data); }catch(_){ return; }
    if(m.type === "out"){ term.feed(m.text); dirtyTerm = true; }
    else if(m.type === "clear"){ term.clear(); dirtyTerm = true; }
    else if(m.type === "closed"){ term.feed("\r\n\x1b[33m— 连接已断开 —\x1b[0m\r\n"); dirtyTerm = true; }
  };
  ws.onclose = ()=>{
    if(wsRef === ws) wsRef = null;
    term.feed("\r\n\x1b[33m— 会话结束 —\x1b[0m\r\n");
    dirtyTerm = true;
  };
  return ov;
}

/* 容器控制台（小鸡） */
window.openConsole = function(cid, name){
  openTermModal(`root@${name} — 容器控制台`, `/ws/terminal/${cid}?token=${encodeURIComponent(state.token)}`);
};

/* 母机控制台 */
window.openNodeTerminal = function(nid, name){
  openTermModal(`${name} — 母机控制台`, `/ws/node-terminal/${nid}?token=${encodeURIComponent(state.token)}`);
};
