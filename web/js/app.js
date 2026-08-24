/* ═══════════════════ LXC Deck · 前端 SPA ═══════════════════ */
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
    const online = list.filter(n=>n.status==="online").length;
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
    apps:viewApps, templates:viewTemplates, snapshots:viewSnapshots,
    network:viewNetwork, users:viewUsers, audit:viewAudit,
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
  ctx.font = "10px ui-monospace"; ctx.fillStyle="#5b6b85"; ctx.strokeStyle="rgba(148,163,184,.12)";
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
  ctx.strokeStyle="rgba(148,163,184,.15)";
  ctx.beginPath(); ctx.arc(cx,cy,r,0,Math.PI*2); ctx.stroke();
  ctx.strokeStyle=color;
  ctx.beginPath(); ctx.arc(cx,cy,r,-Math.PI/2,-Math.PI/2+Math.PI*2*pct/100); ctx.stroke();
  ctx.fillStyle="#e6ebf4"; ctx.font="600 17px system-ui"; ctx.textAlign="center";
  ctx.fillText(pct.toFixed(1)+"%", cx, cy+1);
  ctx.fillStyle="#8b98ad"; ctx.font="10.5px system-ui";
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
        <dt>面板版本</dt><dd>LXC Deck ${esc(state.meta?.version||"")}</dd>
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
                  offline:["var(--err)","离线"],unknown:["#94a3b8","待探测"]};
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
            <span class="tag" style="color:${n.counts.running?'#86efac':'inherit'}">${n.counts.running} 运行中</span>
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
  unknown: ["#94a3b8",     "待探测"],
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
      $("#node-grid").innerHTML = list.map(n=>{
        const [c,lbl] = NODE_ST[n.status]||NODE_ST.unknown;
        const L=n.live, memP=L.mem_total_mb?L.mem_used_mb/L.mem_total_mb*100:0,
              diskP=L.disk_total_gb?L.disk_used_gb/L.disk_total_gb*100:0;
        return `<div class="card tpl-card">
          <div class="stripe" style="background:${c}"></div>
          <div class="tpl-head">
            <span class="tpl-logo" style="background:#334155">${icon("server",17)}</span>
            <div><b>${esc(n.name)}</b>
              <div class="mono" style="font-size:11px;color:var(--muted)">
                ${n.kind==="demo"?"🎮 演示节点":n.kind==="agent"?"⚡ Agent · "+esc(n.os_info||"等待接入"):esc(n.username+"@"+n.host+":"+n.port)}</div></div>
            <span class="badge" style="margin-left:auto"><span class="dot" style="background:${c};animation:none"></span>${lbl}</span>
          </div>
          <div style="font-size:12px;color:var(--muted);margin-bottom:10px" class="mono">
            ${esc(n.os_info || (n.error?n.error.slice(0,60):"—"))}</div>
          ${miniBar("CPU", L.cpu_pct)}
          ${miniBar("内存", memP, fmtGB(L.mem_used_mb)+" / "+fmtGB(L.mem_total_mb))}
          ${miniBar("磁盘", diskP, L.disk_used_gb+"G / "+L.disk_total_gb+"G")}
          <div style="display:flex;gap:8px;margin-top:10px;flex-wrap:wrap">
            <span class="tag">${n.counts.total} 台实例</span>
            <span class="tag" style="color:${n.counts.running?'#86efac':'inherit'}">${n.counts.running} 运行</span>
            ${n.kind==="ssh"&&!n.lxc_ok&&n.status==="online"?`<button class="btn sm primary" data-install="${n.id}">⚡ 安装 LXC</button>`:""}
          </div>
          <div class="actions-cell" style="margin-top:12px">
            <button class="btn sm" data-probe="${n.id}">${icon("activity",12)} 测试</button>
            ${n.kind==="agent"?`<button class="btn sm" data-agent-cmd="${n.id}">${icon("term",12)} 接入命令</button>`:""}
            <button class="btn sm danger" data-del="${n.id}" data-name="${esc(n.name)}">${icon("trash",12)} 删除</button>
          </div>
        </div>`;
      }).join("") || `<div class="empty" style="grid-column:1/-1;padding:60px 0">
        <p style="font-size:15px;margin-bottom:8px">还没有接入任何服务器</p>
        <p>点击右上角「接入服务器」，填入 SSH 信息即可远程创建和管理 LXC 实例</p></div>`;

      $$("#node-grid [data-probe]").forEach(b=>b.onclick=async()=>{
        b.disabled=true; b.textContent="测试中…";
        try{ const r=await api(`/nodes/${b.dataset.probe}/probe`,{method:"POST"});
          toast(`✓ ${r.hostname||""} · ${r.os} · LXC ${r.lxc_installed?("已安装 "+(r.lxc_version||"")):"未安装"}`,"ok",4200);
        }catch(e){ toast(e.message,"err",4200); }
        render();
      });
      $$("#node-grid [data-del]").forEach(b=>b.onclick=()=>deleteNode(+b.dataset.del,b.dataset.name));
      $$("#node-grid [data-agent-cmd]").forEach(b=>b.onclick=async()=>{
        const n = (await api("/nodes")).find(x=>String(x.id)===b.dataset.agentCmd);
        if(!n?.install_cmd){ toast("未生成安装命令","err"); return; }
        const ov = openModal(`Agent 接入命令 — <b>${esc(n.name)}</b>`, `
          <p style="color:var(--muted);font-size:12.5px;line-height:1.7;margin-bottom:10px">
            在目标 VPS 上以 root 执行以下命令（需 curl），完成后节点自动上线：</p>
          <div class="term" style="height:auto;padding:12px;user-select:all" id="cmd-box">curl -fsSL ${new URL(location.href).origin}/api/agent/install.sh | bash -s -- --api ${new URL(location.href).origin} --token ${n.agent_token}</div>
          <button class="btn primary block" style="margin-top:12px" onclick="copyText(document.getElementById('cmd-box').textContent);">📋 复制命令</button>
          <p style="color:var(--muted);font-size:11.5px;margin-top:10px">
            Agent 将反向连接面板（支持 NAT 后机器），每 3 秒心跳上报，Token 可随时轮换吊销。</p>`,
          null, "", {wide:true});
        ov.querySelector(".modal-foot").remove();
      });
      $$("#node-grid [data-install]").forEach(b=>b.onclick=async()=>{
        b.disabled=true; b.textContent="安装中…";
        toast("正在通过 SSH 安装 LXC，可能需要几分钟…","info",6000);
        try{ const r=await api(`/nodes/${b.dataset.install}/install`,{method:"POST"});
          toast(r.output.split("\n")[0],"ok",5000); }catch(e){ toast(String(e.message).slice(0,120),"err",5000); }
        render();
      });
    }catch(e){ $("#node-grid").innerHTML=`<div class="empty">${esc(e.message)}</div>`; }
  };

  $("#btn-add-node").onclick = openNodeModal;
  render();
  tickHandle = setInterval(render, 5000);
}

function deleteNode(id,name){
  confirmModal(`确定删除节点 <b>${esc(name)}</b>？其下实例将被一并删除。`,true)
  .then(async yes=>{
    if(!yes) return;
    try{
      await api(`/nodes/${id}`, {method:"DELETE"});       // 先尝试普通删除
      toast("节点已删除","ok"); viewNodes();
    }catch(e){
      if(String(e.message).includes("强制删除")){
        if(await confirmModal("该节点下仍有实例，确认<b>连同全部实例一起删除</b>？",true)){
          try{ await api(`/nodes/${id}?force=1`,{method:"DELETE"}); toast("节点及实例已删除","ok"); viewNodes(); }
          catch(e2){ toast(e2.message,"err"); }
        }
      } else toast(e.message,"err");
    }
  });
}

function openNodeModal(){
  openModal("接入服务器（SSH）", `
    <div class="form-grid">
      <label>节点名称 *<input id="n-name" placeholder="如 node-shanghai"></label>
      <label>节点类型 *
        <select id="n-kind"><option value="ssh">SSH 服务器</option><option value="demo">演示节点（虚拟）</option></select></label>
      <label class="full">主机地址 / 端口 *
        <div style="display:flex;gap:8px">
          <input id="n-host" placeholder="IP 或域名" style="flex:1">
          <input id="n-port" type="number" value="22" min="1" max="65535" style="width:88px">
        </div></label>
      <label>SSH 用户名 *<input id="n-user" value="root"></label>
      <label>认证方式 *
        <select id="n-auth"><option value="password">密码</option><option value="key">私钥</option></select></label>
      <label class="full" id="lbl-secret">密码 *<input id="n-secret" type="password" placeholder="SSH 登录密码"></label>
      <label class="full hidden" id="lbl-key">私钥（PEM）*
        <textarea id="n-keytext" rows="5" class="input mono"
          style="resize:vertical;font-family:var(--mono);font-size:11.5px" placeholder="-----BEGIN OPENSSH PRIVATE KEY-----&#10;..."></textarea></label>
      <p class="sub full" style="color:var(--muted);font-size:12px;line-height:1.7">
        凭据使用面板密钥加密存储；建议为面板创建专用账号并用 sudo 白名单限制 lxc 命令。<br>
        节点需已安装 LXC（未装可在添加后一键安装）。目标系统：Debian / Ubuntu / CentOS / Rocky / Alpine。</p>
    </div>`,
    async ()=>{
      const kind=$("#n-kind").value;
      const body={ name:$("#n-name").value.trim(), kind,
        host:$("#n-host").value.trim(), port:+$("#n-port").value||22,
        username:$("#n-user").value.trim()||"root",
        auth_type:$("#n-auth").value };
      if(kind==="ssh"){
        body.secret = body.auth_type==="key" ? $("#n-keytext").value.trim()
                                             : $("#n-secret").value;
        if(!body.host) return toast("请填写主机地址","err");
        if(!body.secret) return toast("请填写密码或私钥","err");
      }
      try{
        // 先测试连接再保存
        if(kind==="ssh"){
          toast("正在测试连接…","info");
          await api("/nodes/test",{method:"POST",body});
        }
        const created = await api("/nodes",{method:"POST",body});
        closeModal();
        toast(`节点 ${created.name} 已接入`,"ok");
        viewNodes();
      }catch(e){ toast(String(e.message).slice(0,150),"err",4500); }
    }, "接入");
  const kindSel=$("#n-kind"), authSel=$("#n-auth");
  const syncUI=()=>{
    const isSsh = kindSel.value==="ssh";
    ["n-host","n-port","n-user"].forEach(id=>$( "#"+id).parentElement.classList.toggle("hidden",!isSsh));
    $("#n-user").closest("label").classList.toggle("hidden",!isSsh);
    $("#lbl-secret").classList.toggle("hidden", !isSsh||authSel.value!=="password");
    $("#lbl-key").classList.toggle("hidden", !isSsh||authSel.value!=="key");
  };
  kindSel.onchange=syncUI; authSel.onchange=syncUI; syncUI();
}

/* ══════════════ 视图：一键部署(X-UI 8合1 移植) ══════════════ */
const SNI_PRESETS = ["addons.mozilla.org","www.apple.com","gateway.icloud.com",
  "itunes.apple.com","www.microsoft.com","www.yahoo.com"];
let deployJob = null;

async function viewApps(){
  $("#content").innerHTML = `
  <div class="page-head">
    <span class="sub">把代理协议栈一键下发到指定 LXC 容器（sing-box 内核 · 支持 8合1 全家桶）</span>
  </div>
  <div class="cols-2-1">
    <div>
      <div class="card">
        <h4><span class="dot"></span>选择目标</h4>
        <div class="form-grid">
          <label>目标容器 *
            <select id="d-container"><option value="">加载中…</option></select></label>
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
      <div class="card" style="margin-top:16px" id="deploy-log-card">
        <h4><span class="dot"></span>部署日志</h4>
        <div class="term" style="height:200px" id="deploy-log">等待发起部署…</div>
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
        <p style="color:var(--muted);font-size:11.5px;margin-top:8px">共用 UUID · Reality 密钥对自动生成 · 自动 DNAT 端口映射</p>
      </div>
      <div class="card" style="margin-top:16px;padding:6px 12px">
        <h4 style="padding:10px 6px 0"><span class="dot"></span>已部署应用</h4>
        <div class="table-wrap" style="margin-top:8px"><table>
          <thead><tr><th>实例</th><th>类型</th><th>状态</th><th>操作</th></tr></thead>
          <tbody id="apps-body"></tbody></table></div>
      </div>
    </div>
  </div>
  <div class="card" style="margin-top:16px" id="links-card">
    <h4><span class="dot"></span>分享链接 <button class="btn sm ghost" id="btn-copy-all" style="margin-left:auto;display:none">📋 复制全部</button></h4>
    <div id="links-box" style="display:flex;flex-direction:column;gap:8px;margin-top:10px">
      <span class="empty">尚无部署结果</span></div>
  </div>`;

  // 加载容器列表(排除 demo)
  try{
    const cts = await api("/containers");
    const sel = $("#d-container");
    const usable = cts.filter(c=>c.node_kind!=="demo");
    sel.innerHTML = usable.map(c=>
      `<option value="${c.id}">${esc(c.name)} · ${esc(c.node_name)} (${c.status==="running"?"运行中":"已停止"})</option>`).join("")
      || `<option value="">暂无真实容器，请先创建</option>`;
  }catch(e){}
  $("#d-app").onchange = e=>{
    const multi = e.target.value==="xui-8in1";
    $("#d-desc").textContent = multi ?
      "将向目标容器一次性下发 8 个防封协议（起始端口连续占用 8 个），自动生成 Reality 密钥对、自签证书并在宿主节点配置 DNAT 端口映射。"
      : "将在目标容器内以 sing-box 内核部署该单协议，并自动完成端口映射。";
  };
  $("#d-app").dispatchEvent(new Event("change"));

  loadApps();
  $("#btn-deploy").onclick = async ()=>{
    const cid = +$("#d-container").value;
    if(!cid) return toast("请先选择目标容器","err");
    if(!(await confirmModal(`确认向该容器下发 <b>${$("#d-app").options[$("#d-app").selectedIndex].text}</b> ？`))) return;
    try{
      const r = await api("/deploy",{method:"POST",body:{
        container_id:cid, app_type:$("#d-app").value,
        start_port:+$("#d-port").value||8881, sni:$("#d-sni").value.trim() }});
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
      <span class="mono" style="flex:1;font-size:11.5px;word-break:break-all;color:#a5d6ff">${esc(l)}</span>
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
    $("#apps-body").innerHTML = list.map(a=>{
      const n = JSON.parse(a.links||"[]").length;
      return `<tr><td><b>${esc(a.container||"(已删)")}</b></td>
      <td><span class="tag">${n?`${n} 节点`:"-"}</span></td>
      <td><span class="badge ${a.status==="done"?"running":a.status==="failed"?"stopped":"frozen"}">
        <span class="dot"></span>${a.status}</span></td>
      <td><div class="actions-cell">
        ${n?`<button class="btn sm" onclick='copyText(${JSON.stringify(a.links)})'>复制链接</button>`:""}
        <button class="btn sm danger" data-del-app="${a.id}">${icon("trash",12)}</button>
      </div></td></tr>`;
    }).join("") || `<tr><td colspan="4" class="empty">暂无部署记录</td></tr>`;
    $$("#apps-body [data-del-app]").forEach(b=>b.onclick=async()=>{
      if(!(await confirmModal("删除该应用？将停止容器内 sing-box 并移除 DNAT 映射。",true))) return;
      try{ await api(`/apps/${b.dataset.delApp}`,{method:"DELETE"}); toast("已删除","ok"); loadApps(); }
      catch(e){ toast(e.message,"err"); }
    });
  }catch(e){}
}

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
          <span class="mono" style="font-size:11.5px;color:var(--muted)">${fmtGB(c.live.mem_used_mb)}/${fmtGB(c.mem)}</span>
        </div>`:`<span style="color:var(--muted)">— / ${fmtGB(c.mem)}</span>`}</td>
      <td>${c.disk} GB</td>
      <td>${c.snapshots?`<span class="tag">${icon("camera",11)} ${c.snapshots}</span>`:"—"}</td>
      <td class="mono" style="font-size:12px">${fmtUp(c.live.uptime_s)}</td>
      <td><div class="actions-cell">
        <button class="act-btn ok" title="启动" ${run?"disabled":""} onclick="ctAction(${c.id},'start')">${icon("play")}</button>
        <button class="act-btn warn" title="停止" ${!run?"disabled":""} onclick="ctAction(${c.id},'stop')">${icon("stop")}</button>
        <button class="act-btn warn" title="重启" ${!run?"disabled":""} onclick="ctAction(${c.id},'restart')">${icon("rotate")}</button>
        <button class="act-btn" title="控制台" onclick="openConsole(${c.id},'${esc(c.name)}')">${icon("term")}</button>
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
      <label>磁盘 GB<input id="c-disk" type="number" min="1" max="2048" value="10"></label>
      <label>备注<input id="c-note" placeholder="选填"></label>
      <label class="full check-line"><input type="checkbox" id="c-auto" checked style="accent-color:var(--accent)">
        创建完成后立即启动</label>
      <p class="sub full" style="color:var(--muted);font-size:12px">
        内存支持 64MB 起步、64MB 步进；小规格适合 Alpine/轻量进程。</p>
    </div>`,
    async ()=>{
      const memV = +$("#c-mem").value;
      if(!memV || memV < 64) return toast("内存最低 64 MB","err");
      if(memV % 64 !== 0) return toast("内存需为 64 的整数倍","err");
      try{
        await api("/containers", { method:"POST", body:{
          name:$("#c-name").value.trim().toLowerCase(), template:$("#c-tpl").value,
          node_id:+$("#c-node").value,
          cpu:+$("#c-cpu").value, mem:memV, disk:+$("#c-disk").value,
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
              offline:["var(--err)","离线"],unknown:["#94a3b8","待探测"]};
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
  $("#content").innerHTML = `
  <div class="grid stat-grid" style="grid-template-columns:repeat(auto-fit,minmax(300px,1fr))">
    <div class="card"><h4><span class="dot"></span>运行环境</h4>
      <dl class="kv">
        <dt>面板版本</dt><dd>LXC Deck ${esc(state.meta?.version||"v0.2.0")}</dd>
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
    ${state.user.role==="admin"?`
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
  const rd = $("#reset-demo");
  if(rd) rd.onclick = async ()=>{
    if(!(await confirmModal("⚠ 确定清空所有节点上的全部实例与快照？",true))) return;
    try{ await api("/admin/reset-instances",{method:"POST"}); toast("已清空全部实例数据","ok");
      setTimeout(()=>location.reload(), 800); }
    catch(e){ toast(e.message,"err"); }
  };
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
  document.getElementById("modals").appendChild(ov);
  ov.addEventListener("click", e=>{ if(e.target===ov) closeModal(); });
  ov.querySelectorAll("[data-x]").forEach(b=>b.onclick=closeModal);
  if(onOk) ov.querySelector("[data-ok]").onclick = onOk;
  return ov;
}
function closeModal(){ $$("#modals .overlay").forEach(o=>o.remove()); }

function confirmModal(msgHTML, danger=false){
  return new Promise(resolve=>{
    const ov = openModal("请确认", `<p style="font-size:13.5px;line-height:1.8">${msgHTML}</p>`,
      ()=>{ closeModal(); resolve(true); }, danger?"确认执行":"确定");
    if(danger) ov.querySelector("[data-ok]").className="btn danger";
    ov.addEventListener("click", e=>{ if(e.target===ov) resolve(false); });
    ov.querySelectorAll("[data-x]").forEach(b=>b.addEventListener("click",()=>resolve(false)));
  });
}

/* ══════════════ WebSocket 终端 ══════════════ */
function closeWS(){ if(wsRef){ try{ wsRef.close(); }catch(e){} wsRef=null; } }

window.openConsole = function(cid, name){
  const ov = openModal(`<span style="display:inline-flex;gap:8px;align-items:center">
      ${icon("term",16)} root@${esc(name)} — 交互式控制台</span>`,
    `<div class="term" id="term-out"></div>
     <div style="position:absolute;left:-9999px"><input id="term-input"></div>
     <p class="sub" style="color:var(--muted);font-size:11.5px;margin-top:8px">
       提示：试试 <code>help</code> / <code>neofetch</code> / <code>free -m</code> / <code>ip a</code>，
       ↑↓ 可翻阅历史命令</p>`,
    null, "", { wide:true });
  ov.querySelector(".modal-foot").remove();

  const out = ov.querySelector("#term-out");
  const input = ov.querySelector("#term-input");
  let buf = ""; const history = []; let hi = -1;
  const promptHTML = `<span class="t-prompt">root@${esc(name)}:~#</span>&nbsp;`;

  const scroll = ()=>{ out.scrollTop = out.scrollHeight; };
  const addLine = (html, cls="")=>{
    const div = document.createElement("div");
    div.className = `t-line ${cls}`; div.innerHTML = html;
    out.appendChild(div); scroll();
  };
  const redrawInput = ()=>{
    let el = out.querySelector(".t-input-line");
    if(!el){ el=document.createElement("div"); el.className="t-line t-input-line"; out.appendChild(el); }
    el.innerHTML = `${promptHTML}<span class="t-cmd">${esc(buf)}</span><span class="t-caret"></span>`;
    scroll();
  };

  out.addEventListener("click", ()=>input.focus());

  function send(line){
    buf=""; history.push(line); hi=history.length;
    addLine(`${promptHTML}<span class="t-cmd">${esc(line)}</span>`);
    const ph = out.querySelector(".t-input-line"); if(ph) ph.remove();
    if(wsRef && wsRef.readyState===1) wsRef.send(line);
  }

  input.addEventListener("keydown", e=>{
    if(e.key==="Enter"){ send(buf); e.preventDefault(); }
    else if(e.key==="Backspace"){ buf = buf.slice(0,-1); redrawInput(); e.preventDefault(); }
    else if(e.key==="ArrowUp"){ if(hi>0){ hi--; buf=history[hi]||""; redrawInput(); } e.preventDefault(); }
    else if(e.key==="ArrowDown"){ if(hi<history.length){ hi++; buf=history[hi]||""; redrawInput(); } e.preventDefault(); }
    else if(e.key==="l" && e.ctrlKey){ out.innerHTML=""; redrawInput(); e.preventDefault(); }
    else if(e.key.length===1 && !e.ctrlKey && !e.metaKey){ buf+=e.key; redrawInput(); e.preventDefault(); }
  });

  // 建立 WebSocket
  const proto = location.protocol==="https:"?"wss":"ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws/terminal/${cid}?token=${encodeURIComponent(state.token)}`);
  wsRef = ws;
  ws.onmessage = ev=>{
    let m; try{ m=JSON.parse(ev.data); }catch(_){ return; }
    if(m.type==="clear"){ out.innerHTML=""; redrawInput(); return; }
    if(m.type==="out"){
      m.text.split(/\r?\n/).forEach((ln,i)=>{
        ln = ln.replace(/&/g,"&amp;").replace(/</g,"&lt;");
        addLine(ln || "&nbsp;");
      });
    }
    if(m.type==="closed"){ addLine('<span style="color:var(--warn)">— 连接已断开 —</span>'); }
  };
  ws.onopen = ()=>{ redrawInput(); input.focus(); };
  ws.onclose = ()=>{
    if(wsRef===ws){ wsRef=null; }
    addLine('<span style="color:var(--warn)">— 会话结束 —</span>');
  };
};
