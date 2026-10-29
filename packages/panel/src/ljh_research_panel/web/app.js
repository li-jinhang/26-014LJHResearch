// Frontend depends only on the versioned business contract, never Python/files.
const $ = (s) => document.querySelector(s);
const state = {token:'', tasks:[], selected:null, workspace:null, detail:null, decisions:[], events:[], settings:null};
const escape = (v='') => String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const labels = {queued:'待执行',running:'进行中',paused:'已暂停',awaiting_decision:'等待决定',completed:'已完成',cancelled:'已取消',failed:'失败',succeeded:'成功',unknown:'待核实',submitting:'提交中',driver_offline:'驱动离线，待接管',pending:'待决定',approved:'已批准',rejected:'已拒绝'};
const badge = (s) => `<span class="badge ${escape(s)}">${escape(labels[s]||s)}</span>`;
const lines = (s) => s.split(/\r?\n/).map(x=>x.trim()).filter(Boolean);
function notice(message){$('#notice').textContent=message;$('#notice').hidden=!message;}
async function api(method,params={},evidence){
 const response=await fetch('/api/operation',{method:'POST',headers:{'Content-Type':'application/json','X-LJH-Token':state.token},body:JSON.stringify({protocol_version:1,method,params,user_evidence:evidence})});
 const value=await response.json();if(!value.ok)throw new Error(value.error?.message||'操作失败');return value.result;
}
async function action(fn){try{notice('');await fn();await refresh();}catch(error){notice(error.message);}}
function view(name){for(const el of document.querySelectorAll('.view'))el.hidden=el.id!==name;for(const el of document.querySelectorAll('nav button'))el.classList.toggle('active',el.dataset.view===name);$('#breadcrumb').textContent='研究工作台 / '+({overview:'任务与运行',memory:'科研记录',environment:'配置与环境',events:'操作轨迹'}[name]);}
for(const button of document.querySelectorAll('nav button'))button.addEventListener('click',()=>view(button.dataset.view));
function renderTasks(){
 $('#task-count').textContent=state.tasks.length;
 $('#run-count').textContent=state.tasks.reduce((sum,t)=>sum+(t.active_runs||0),0);
 $('#decision-count').textContent=state.decisions.filter(d=>d.status==='pending').length;
 $('#task-list').innerHTML=state.tasks.length?state.tasks.map(t=>`<button class="task-item ${t.id===state.selected?'selected':''}" data-task="${escape(t.id)}"><div class="task-meta"><span class="task-id">${escape(t.id)}</span>${badge(t.status==='running'&&!t.driver_online?'driver_offline':t.status)}</div><h3>${escape(t.title)}</h3><div class="task-meta"><span>实验 ${t.runs_used} / ${t.authorization.max_runs}</span><span>${t.authorized?'已授权':t.status==='cancelled'?'未授权':'等待授权'}</span></div></button>`).join(''):'<div class="empty"><p>任务队列还是空的。<br>从一个值得回答的问题开始。</p></div>';
}
function renderDetail(){
 const t=state.detail;if(!t)return;
 const pending=state.decisions.filter(d=>d.task_id===t.id&&d.status==='pending');
 const ready=t.authorized&&!t.revoked&&['queued','paused'].includes(t.status);
 $('#task-detail').innerHTML=`<div class="detail-content"><div class="detail-top"><span class="task-id">${escape(t.id)}</span>${badge(t.status==='running'&&!t.driver_online?'driver_offline':t.status)}</div><h2>${escape(t.title)}</h2><p class="objective">${escape(t.objective)}</p>${t.last_error?`<div class="notice">${escape(t.last_error)}</div>`:""}<p class="subtle">停止条件：${escape(t.stop_condition)}</p><div class="budget"><span>实验预算<b>${t.runs_used} / ${t.authorization.max_runs}</b></span><span>推理预算<b>${t.reasoning_calls_used} / ${t.authorization.max_reasoning_calls}</b></span></div><div class="actions">${ready?'<button class="primary" data-action="start">由控制模块推进 →</button>':''}${['running','awaiting_decision'].includes(t.status)?'<button class="secondary" data-action="pause">暂停调度 / 释放控制权</button>':''}<button class="secondary" data-action="copy">复制 agent 接入请求</button></div>${t.owner&&!['completed','cancelled','failed'].includes(t.status)?`<p class="subtle">当前驱动：${escape(t.owner)}${t.lease_until*1000<Date.now()?' · 心跳已过期，请明确接管':''}</p>`:''}${t.summary?`<h3>结果与局限</h3><p class="objective">${escape(t.summary)}</p>`:''}${pending.map(d=>`<div class="decision"><h3>${d.kind==='task_authorization'?'批准这一次研究的范围':escape(d.kind)}</h3><pre>${escape(JSON.stringify(d.payload,null,2))}</pre><div class="actions"><button class="primary" data-decision="${escape(d.id)}" data-choice="approved">批准这一方案</button><button class="secondary" data-decision="${escape(d.id)}" data-choice="rejected">暂不批准</button></div></div>`).join('')}<div class="section-head"><h2>实验运行</h2></div>${t.runs.length?t.runs.map(r=>`<article class="run-row"><div><code>${escape(r.id)}</code>${badge(r.status)}</div><p>${escape(r.argv.join(' '))}</p><div class="actions"><button class="secondary" data-run="${escape(r.id)}" data-run-action="refresh">核实状态</button><button class="secondary" data-run="${escape(r.id)}" data-run-action="logs">查看输出</button>${!['succeeded','failed','cancelled'].includes(r.status)?`<button class="secondary" data-run="${escape(r.id)}" data-run-action="cancel">停止这次运行</button>`:''}</div></article>`).join(''):'<p class="subtle">尚未启动实验。驱动方会在授权范围内安排下一步。</p>'}</div>`;
}
function renderMemory(){
 const cards=state.workspace.cards;$('#cards').innerHTML=cards.length?cards.map(c=>`<article class="memory-card"><span class="task-id">${escape(c.id)}</span><h2>${escape(c.title)}</h2>${badge(c.status)}<p>${escape(c.path)}</p></article>`).join(''):'<div class="empty"><h2>科研记录会在工作中积累</h2><p>初始化仅创建结构。导入论文或建立研究点后，这里会显示真实记录。</p></div>';
}
function renderEvents(){
 $('#event-list').innerHTML=state.events.length?state.events.slice().reverse().map(e=>`<article class="event"><time>${new Date(e.at*1000).toLocaleTimeString('zh-CN',{hour12:false})}<br>#${e.seq}</time><div><strong>${escape(e.kind)}</strong><pre>${escape(JSON.stringify(e.data,null,2))}</pre></div></article>`).join(''):'<div class="empty">还没有操作轨迹。</div>';
}
function fillSettings(){
 const config=state.workspace.config,form=$('#conventions-form');
 for(const name of ['domain','framework','experiments_dir'])form.elements[name].value=config[name]||'';
 for(const name of ['code_roots','default_metrics'])form.elements[name].value=(config[name]||[]).join('\n');
 const b=$('#bindings-form'),s=state.settings;
 b.elements.kind.value=s.reasoning.kind||'command';b.elements.program.value=s.reasoning.command[0]||'';
 b.elements.extra.value=JSON.stringify(s.reasoning.command.slice(1));b.elements.timeout.value=s.reasoning.timeout_seconds||120;
 b.elements.executor.value=JSON.stringify(s.executor.command);b.elements.controller.value=JSON.stringify(s.controller.command);
 const c=state.workspace.capabilities;$('#capabilities').innerHTML=[['控制台 Python',c.python_version],['本地执行插件',c.local_execution?'可用':'未安装'],['参考控制模块',c.controller?'可用':'未安装']].map(([k,v])=>`<div class="capability ${v==='未安装'?'missing':''}">${k} · ${escape(v)}</div>`).join('');
}
async function refresh(initial=false){
 try{
  const [workspace,tasks,decisions,events]=await Promise.all([api('workspace.get'),api('task.list'),api('decision.list'),api('event.list')]);
  const active=tasks.filter(t=>t.active_runs>0);
  for(const task of active){
   const runs=await api('run.list',{task_id:task.id});
   for(const run of runs.filter(r=>!['succeeded','failed','cancelled'].includes(r.status))){
    try{await api('run.refresh',{run_id:run.id});}catch(error){notice('运行状态待核实：'+error.message);}
   }
  }
  Object.assign(state,{workspace,tasks:active.length?await api('task.list'):tasks,decisions,events});
  state.selected=state.selected||tasks[0]?.id||null;
  if(state.selected)state.detail=await api('task.get',{task_id:state.selected});
  $('#workspace-path').textContent=workspace.project_root;$('#connection').textContent='工作区已连接';
  renderTasks();renderDetail();renderMemory();renderEvents();
  if(initial){state.settings=await api('settings.get');fillSettings();}
 }catch(error){$('#connection').textContent='需要检查工作区';notice(error.message);}
}
$('#refresh').addEventListener('click',()=>action(()=>refresh(true)));
$('#new-task').addEventListener('click',()=>{$('#task-form').elements.programs.value=state.workspace?.capabilities.python||'';$('#task-dialog').showModal();});
$('#close-dialog').addEventListener('click',()=>$('#task-dialog').close());
$('#close-logs').addEventListener('click',()=>$('#logs-dialog').close());
$('#task-form').addEventListener('submit',event=>{event.preventDefault();action(async()=>{
 const f=event.currentTarget.elements;
 const result=await api('task.create',{title:f.title.value,objective:f.objective.value,stop_condition:f.stop.value||'问题获得回答、预算耗尽，或下一步信息增益不足',authorization:{allowed_roots:lines(f.roots.value),allowed_programs:lines(f.programs.value),max_runs:Number(f.max_runs.value),max_reasoning_calls:Number(f.max_calls.value),max_run_seconds:Number(f.minutes.value)*60}});
 state.selected=result.task.id;$('#task-dialog').close();$('#task-form').reset();view('overview');
});});
$('#task-list').addEventListener('click',event=>{const button=event.target.closest('[data-task]');if(button)action(async()=>{state.selected=button.dataset.task;state.detail=await api('task.get',{task_id:state.selected});});});
$('#task-detail').addEventListener('click',event=>action(async()=>{
 const button=event.target.closest('button');if(!button)return;
 if(button.dataset.decision){await api('decision.resolve',{decision_id:button.dataset.decision,decision:button.dataset.choice},`用户在面板明确${button.dataset.choice}方案 ${button.dataset.decision}`);return;}
 if(button.dataset.run){const id=button.dataset.run,which=button.dataset.runAction;
  if(which==='logs'){const logs=await api('run.logs',{run_id:id});$('#logs-output').textContent=`STDOUT\n${logs.stdout}\n\nSTDERR\n${logs.stderr}`;$('#logs-dialog').showModal();}
  else if(which==='refresh')await api('run.refresh',{run_id:id});
  else if(which==='cancel'&&confirm('确认停止这一次实验运行？这不会自动重置预算。'))await api('run.cancel',{run_id:id},'用户在面板明确要求停止运行 '+id);
  return;
 }
 if(button.dataset.action==='pause')await api('task.pause',{task_id:state.selected},'用户在面板要求暂停调度并释放控制权');
 if(button.dataset.action==='start'){
  const response=await fetch('/api/controller/start',{method:'POST',headers:{'Content-Type':'application/json','X-LJH-Token':state.token},body:JSON.stringify({task_id:state.selected})});const result=await response.json();if(!result.ok)throw new Error(result.error?.message||'控制模块启动失败');
 }
 if(button.dataset.action==='copy'){
  const request={protocol_version:1,project_root:state.workspace.project_root,method:'task.claim',params:{task_id:state.selected,driver_id:'coding-agent'}};
  await navigator.clipboard.writeText(JSON.stringify(request,null,2));notice('已复制接入请求。请让 coding agent 通过公开命令行接口提交。');
 }
}));
$('#conventions-form').addEventListener('submit',event=>{event.preventDefault();action(async()=>{
 const f=event.currentTarget.elements;
 for(const key of ['domain','framework','experiments_dir','code_roots','default_metrics']){
  const value=['code_roots','default_metrics'].includes(key)?lines(f[key].value):f[key].value.trim()||null;
  if(JSON.stringify(value)!==JSON.stringify(state.workspace.config[key]))await api('config.update',{key,value},'用户在面板修改项目默认约定 '+key);
 }
 notice('项目默认约定已保存。现有任务配置保持其已确认版本。');
});});
$('#bindings-form').addEventListener('submit',event=>{event.preventDefault();action(async()=>{
 const f=event.currentTarget.elements,program=f.program.value.trim();
 const reasoning={kind:f.kind.value,command:program?[program,...JSON.parse(f.extra.value||'[]')]:[],timeout_seconds:Number(f.timeout.value)};
 await api('settings.update',{reasoning,executor:{command:JSON.parse(f.executor.value)},controller:{command:JSON.parse(f.controller.value)}},'用户在面板明确修改后续任务的推理与执行接入配置');notice('接入配置已保存，将用于新建任务。');
});});
async function boot(){try{const response=await fetch('/api/bootstrap');state.token=(await response.json()).csrf_token;await refresh(true);setInterval(()=>{if(!document.hidden)refresh();},3500);}catch(error){notice(error.message);}}
$('#time').textContent=new Date().toLocaleDateString('zh-CN',{year:'numeric',month:'long',day:'numeric'});boot();
