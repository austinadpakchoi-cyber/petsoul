"use strict";
(() => {
  const $ = id => document.getElementById(id);
  const LABELS = {START:"开始记录",CLAIM:"领取记录",PROGRESS:"进展",HANDOFF:"交接",RELEASE:"释放记录",ACCEPT:"接收 / 验证记录",INTEGRATED:"接入记录",VERIFY:"检查记录",CORRECTION:"更正",CHANGE_REQUEST:"协作请求",SCOPE_CHANGE:"范围变更",BLOCKED:"阻塞记录",WAITING:"等待记录",NOTE:"记录"};
  let data = null, selected = "all", tab = "activity", limit = 30, loading = false, timer = null;
  const openRecords = new Set();
  try {
    const saved = JSON.parse(localStorage.getItem("petsoul.live.board") || "{}");
    selected = saved.selected || "all";
    tab = ["activity","requests","review"].includes(saved.tab) ? saved.tab : "activity";
    $("auto").checked = saved.auto !== false;
  } catch (_) { /* No storage is required to read the board. */ }
  function save() {try {localStorage.setItem("petsoul.live.board", JSON.stringify({selected,tab,auto:$("auto").checked}));} catch (_) {}}
  function node(tag, cls, text) {const n = document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n;}
  function time(value, full=false) {
    if(!value)return "时间未明确";
    const d = new Date(value);
    if(Number.isNaN(d.valueOf()))return value;
    return new Intl.DateTimeFormat("zh-CN", {timeZone:"Asia/Shanghai",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",second:full?"2-digit":undefined,hour12:false}).format(d);
  }
  function eventOf(w) {return data.events.find(e=>e.id===w.latestEventId);}
  function choose(owner) {selected=owner;limit=30;save();render();}
  function metric(number, label) {const item=node("div","number");item.append(node("strong","",String(number)),node("span","",label));return item;}
  function renderWindows() {
    $("windows").replaceChildren();
    $("all-windows").classList.toggle("selected",selected==="all");
    $("all-windows").setAttribute("aria-pressed",String(selected==="all"));
    for(const w of data.windows) {
      const button=node("button","window"+(selected===w.owner?" selected":""));button.type="button";
      button.setAttribute("aria-pressed",String(selected===w.owner));button.dataset.owner=w.owner;
      const top=node("span","window-top");top.append(node("span","package",w.package),node("span","window-name",w.name));
      if(w.changedSinceReview)top.append(node("span","updated-dot","有更新"));
      button.append(top,node("span","window-meta",`文件更新 ${time(w.source.modifiedAt)} · ${w.owner.split("-").at(-1)}`));
      const e=eventOf(w);if(e)button.append(node("span","window-meta",`${LABELS[e.kinds[0]]||e.kinds[0]} · ${time(e.recordedAt)}`));
      button.addEventListener("click",()=>choose(w.owner));$("windows").append(button);
    }
    $("window-count").textContent=`${data.windows.length} 个已登记窗口`;
    $("numbers").replaceChildren(metric(data.windows.length,"窗口日志"),metric(data.windows.filter(w=>w.changedSinceReview).length,"份日志新于人工核验"),metric(data.events.length,"条可追溯记录"));
  }
  function renderRecord(e) {
    const details=node("details","record"+(e.kinds.includes("CORRECTION")?" correction":""));details.dataset.event=e.id;details.open=openRecords.has(e.id);
    details.addEventListener("toggle",()=>{if(details.open)openRecords.add(e.id);else openRecords.delete(e.id);});
    const summary=node("summary");const meta=node("div","record-meta");
    meta.append(node("span","package",e.package),node("span","",time(e.recordedAt,true)),node("span","badge",e.kinds.map(k=>LABELS[k]||k).join(" / ")),node("span","",e.owner.split("-").at(-1)));
    summary.append(meta,node("div","record-title",e.title));
    const excerpt=e.summary.length?e.summary.join(" · "):e.body.split("\n").slice(1,5).join(" ");
    if(excerpt)summary.append(node("p","record-excerpt",excerpt));
    details.append(summary);
    if(e.timeNotes.length)details.append(node("p","time-warning",e.timeNotes.join("；")));
    const source=node("div","source-line");
    source.append(node("span","",e.taskId?`任务 ${e.taskId}`:"任务 ID 未单列"),node("span","badge warning",e.tier));
    const a=node("a","",`${e.file} · L${e.line}`);a.href=`/api/log?name=${encodeURIComponent(e.file)}`;a.target="_blank";a.rel="noopener";source.append(a);
    const w=data.windows.find(w=>w.owner===e.owner);
    if(w)source.append(node("span","",`当前文件 SHA ${w.source.sha256.slice(0,12)}`));
    details.append(source,node("pre","raw",e.body));return details;
  }
  function renderRecords() {
    const query=$("search").value.trim().toLowerCase();
    const events=data.events.filter(e=>(selected==="all"||e.owner===selected)&&(!query||(e.title+e.body).toLowerCase().includes(query))&&(tab!=="requests"||e.kinds.some(k=>["CHANGE_REQUEST","CORRECTION","SCOPE_CHANGE"].includes(k))||e.mentions.some(m=>m.startsWith("CR-"))));
    $("event-count").textContent=`${events.length} 条`;
    $("records").replaceChildren(...events.slice(0,limit).map(renderRecord));
    if(!events.length)$("records").append(node("p","empty","没有符合条件的记录。"));
    $("more").hidden=events.length<=limit||tab==="review";
    $("more").textContent=`再显示 ${Math.min(30,Math.max(0,events.length-limit))} 条`;
  }
  function reviewFields(title, fields) {
    const block=node("section","review-block");block.append(node("h3","",title));const dl=node("dl");
    for(const [key,value] of fields) {if(value===undefined||value===null)continue;dl.append(node("dt","",key),node("dd","",Array.isArray(value)?value.join("；"):String(value)));}
    block.append(dl);return block;
  }
  function renderReview() {
    const target=$("review");target.replaceChildren();const r=data.review;
    if(!r){target.append(node("p","empty","人工核验快照暂不可读。最新日志仍可单独查看。"));return;}
    target.append(node("div","review-banner",`人工核验截至 ${time(r.snapshotAt,true)}（北京时间）。网页刷新只更新日志，不改变这些结论。黄色“有更新”表示该窗口文件在核验后发生过变化，未必是新的业务交付。`));
    const packages=r.packages.filter(p=>selected==="all"||p.owner===selected);
    for(const p of packages)target.append(reviewFields(`${p.id} · ${p.name}`,[["当时状态",p.status],["已核对的进展",p.doing],["证据与限制",p.proof],["下一步",p.next],["归属边界",p.boundary],["来源",p.source],["时间说明",p.time]]));
    if(selected==="all") {
      const c=r.contractResults||{}, n=r.naturalTimeGate||{}, runtime=r.runtimeObservation||{};
      target.append(reviewFields("独立合同 · 历史证据",[["记录时间",time(c.observedAt,true)],["通过",c.pass],["失败",c.fail],["适用范围",c.coverageBoundary]]));
      target.append(reviewFields("自然时间 E2 · 上次核验",[["状态",n.status],["原计划判定时间",time(n.judgeAfter,true)],["要求",n.requirement]]));
      target.append(reviewFields("本地运行 · 上次观测",[["观测时间",time(runtime.observedAt,true)],["版本",runtime.version],["证据边界",runtime.tier]]));
    }
    if(!packages.length&&selected!=="all")target.append(node("p","empty","此窗口没有单列人工核验结论，请查看最新记录原文。"));
  }
  function render() {
    if(!data)return;
    if(selected!=="all"&&!data.windows.some(w=>w.owner===selected))selected="all";
    const w=data.windows.find(w=>w.owner===selected);
    $("selection-title").textContent=w?`${w.package} · ${w.name}`:"全部窗口的最新进展";
    $("selection-subtitle").textContent=w?`${w.owner} · ${w.processState}`:"直接读取本机协作日志；展开任一条即可核对来源。";
    document.querySelectorAll("[data-tab]").forEach(b=>b.setAttribute("aria-pressed",String(b.dataset.tab===tab)));
    $("records").hidden=tab==="review";$("review").hidden=tab!=="review";$("activity-tools").hidden=tab==="review";
    $("view-note").textContent=tab==="review"?"人工判断与自动日志聚合分开保留。":tab==="requests"?"协作请求与更正原文；提到请求不等于对方已接收或解决。":"按明确记录时间排序；缺失时间单列提示。更正保留原文，HANDOFF、ACCEPT 与 RELEASE 不自动转换成验收通过或文件可接管。";
    renderWindows();renderRecords();if(tab==="review")renderReview();
  }
  async function refresh() {
    if(loading)return;loading=true;$("refresh").disabled=true;
    try {
      const response=await fetch("/api/board",{cache:"no-store",signal:AbortSignal.timeout(10000)});
      if(!response.ok)throw new Error(`HTTP ${response.status}`);
      const next=await response.json();if(next.application!=="petsoul-live-blackboard"||!Array.isArray(next.events))throw new Error("返回数据不完整");
      const changed=!data||next.revision!==data.revision;const previous=data;data=next;
      $("connection").textContent=data.errors.length?"部分来源待重读":"本地日志已同步";$("connection").classList.toggle("offline",data.errors.length>0);
      $("read-at").textContent=`本次读取 ${time(data.readAt,true)} · 北京时间`;
      $("review-at").textContent=`人工核验 ${time(data.review?.snapshotAt,true)}`;
      $("change-note").textContent=previous?(changed?"检测到记录变化，已更新":"与上次读取相比无变化"):"";
      $("revision").textContent=`内容指纹 ${data.revision.slice(0,12)}`;
      $("error").hidden=!data.errors.length;$("error").textContent=data.errors.map(e=>`${e.source}：${e.message}`).join("；");
      if(changed||JSON.stringify(previous?.errors)!==JSON.stringify(data.errors))render();
    } catch(error) {
      $("connection").textContent="读取失败";$("connection").classList.add("offline");$("error").hidden=false;
      $("error").textContent=`未能读取最新日志（${error.message}）。${data?"当前保留的是上次成功读取的内容，时间未更新。":"请先运行 scripts/start_blackboard.ps1 启动本地服务。"}`;
    } finally {loading=false;$("refresh").disabled=false;}
  }
  function schedule() {clearInterval(timer);timer=$("auto").checked?setInterval(()=>{if(!document.hidden)refresh();},15000):null;}
  $("refresh").addEventListener("click",refresh);
  $("auto").addEventListener("change",()=>{save();schedule();});
  $("all-windows").addEventListener("click",()=>choose("all"));
  $("search").addEventListener("input",()=>{limit=30;if(data)renderRecords();});
  $("more").addEventListener("click",()=>{limit+=30;renderRecords();});
  document.querySelectorAll("[data-tab]").forEach(button=>button.addEventListener("click",()=>{tab=button.dataset.tab;limit=30;save();render();}));
  document.addEventListener("visibilitychange",()=>{if(!document.hidden&&$("auto").checked)refresh();});
  refresh();schedule();
})();
