let currentPage = "dashboard";
    let currentUser = null;
    let devices = [];
    let dashboardMachines = [];
    let molds = [];
    let dashboardPage = 1;
    const pageSize = 8;

    const pageTitles = { dashboard: "设备看板", realtime: "实时参数", tech: "工艺参数", spc: "SPC 数据", molds: "模具管理" };

    // SPC page fields: sourced from dbo.vw_machine_spc, scaled server-side
    // using the raw tag's scale factor (see backend/parameter_labels.py).
    // Values already arrive pre-scaled from the API, so this dict is only
    // used for labels/units, not for scaling in the browser.
    const spcFields = {
        cycle_number:["模数",""],
        cycle_time:["周期时间"," s"],
        eject_time:["托模时间"," s"],
        injection_max_pressure:["最大射压",""],
        injection_end_position:["射出终点位置",""],
        injection_time:["射出保压时间"," s"],
        injection_start_position:["射出起点",""],
        injection_max_speed:["最大射速",""],
        mold_close_time:["关模时间"," s"],
        mold_open_time:["开模时间"," s"],
        switch_pressure:["转保压压力",""],
        switch_position:["转保压位置",""],
        switch_time:["转保压(注射)时间"," s"],
        temperature_1:["生产温度1"," ℃"],
        temperature_2:["生产温度2"," ℃"],
        temperature_3:["生产温度3"," ℃"],
        temperature_4:["生产温度4"," ℃"],
        temperature_5:["生产温度5"," ℃"],
        temperature_6:["生产温度6"," ℃"],
        temperature_7:["生产温度7"," ℃"],
        plasticizing_time:["储料时间"," s"],
        plasticizing_max_pressure:["最大储料压力",""],
        pickup_time:["取出时间"," s"],
        low_pressure_time:["低压时间"," s"],
        high_pressure_time:["高压时间"," s"],
        screw_retract_time:["射退时间"," s"],
        oil_temperature:["生产油温",""]
    };

    // Map specific device IDs to a real machine photo instead of the generic SVG.
    const deviceMachineImages = {
        "C02": "/static/img/haitianMars.png"
    };

    function escapeHtml(value) { return String(value ?? "").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;").replaceAll("'","&#039;"); }
    function showValue(value, suffix="") { return value === null || value === undefined || value === "" ? "--" : `${escapeHtml(value)}${suffix}`; }
    function formatTime(value) { return value ? String(value).replace("T"," ").replace(/\.\d+$/,"") : "--"; }
    function selectedDeviceId() { return document.getElementById("device-select").value; }
    function metric(label,value,suffix="",primary=false) { return `<div class="metric${primary?" primary":""}"><div class="metric-label">${escapeHtml(label)}</div><div class="metric-value">${showValue(value,suffix)}</div></div>`; }
    function machineGraphic() { return `<svg class="machine-svg" viewBox="0 0 190 54" aria-hidden="true"><rect x="4" y="18" width="48" height="26" rx="2" fill="#d7dde4" stroke="#9099a4"/><rect x="10" y="12" width="33" height="14" fill="#f4f6f8" stroke="#9099a4"/><rect x="55" y="25" width="67" height="19" fill="#cbd3dc" stroke="#89939e"/><path d="M60 24 L78 8 L104 8 L118 24" fill="#eef1f4" stroke="#89939e"/><rect x="124" y="18" width="58" height="26" fill="#dbe1e7" stroke="#89939e"/><rect x="135" y="10" width="34" height="13" fill="#f4f6f8" stroke="#89939e"/><circle cx="24" cy="48" r="4" fill="#59636f"/><circle cx="148" cy="48" r="4" fill="#59636f"/><circle cx="174" cy="48" r="4" fill="#59636f"/></svg>`; }
    function machineVisual(deviceId) {
        const image = deviceMachineImages[deviceId];
        if (image) return `<img class="machine-photo" src="${image}" alt="${escapeHtml(deviceId)} 机台照片">`;
        return machineGraphic();
    }

    async function requestJson(url,options={}) {
        const response=await fetch(url,{cache:"no-store",...options});
        if(response.status===401){window.location.replace("/login");throw new Error("登录已失效");}
        const body=await response.json().catch(()=>({}));
        if(!response.ok) throw new Error(body.detail||`HTTP ${response.status}`);
        return body;
    }

    function statusOf(machine) {
        if(!machine.received_at) return "offline";
        const age=Date.now()-new Date(machine.received_at).getTime();
        if(!Number.isFinite(age)||age>120000) return "offline";
        return Number(machine.machine_status)===1 ? "production" : "waiting";
    }
    function statusMeta(status) { return status==="production"?["生产","production"]:status==="waiting"?["待机","waiting"]:["离线","offline"]; }
    function ageText(value) {
        if(!value) return "无数据";
        const seconds=Math.max(0,Math.floor((Date.now()-new Date(value).getTime())/1000));
        if(seconds<60) return `${seconds} 秒前`;
        if(seconds<3600) return `${Math.floor(seconds/60)} 分钟前`;
        return `${Math.floor(seconds/3600)} 小时前`;
    }

    async function loadSession() {
        currentUser=await requestJson("/api/auth/me");
        document.getElementById("user-label").textContent=`${currentUser.username} · ${currentUser.role}`;
        const readOnly=currentUser.role==="viewer";
        document.getElementById("mold-form").querySelectorAll("input,textarea,button").forEach(el=>el.disabled=readOnly);
        document.getElementById("mount-button").disabled=readOnly;
        document.getElementById("unmount-button").disabled=readOnly;
    }
    async function loadDevices() {
        devices=await requestJson("/api/devices");
        const select=document.getElementById("device-select"),previous=select.value;
        select.innerHTML=devices.map(d=>`<option value="${escapeHtml(d.device_id)}">设备 ${escapeHtml(d.device_id)}</option>`).join("");
        if(devices.some(d=>d.device_id===previous)) select.value=previous;
    }
    function updateFilterSelect(id,values,label) {
        const select=document.getElementById(id),previous=select.value;
        const unique=[...new Set(values.filter(Boolean))].sort();
        select.innerHTML=`<option value="">${label}</option>`+unique.map(v=>`<option value="${escapeHtml(v)}">${escapeHtml(v)}</option>`).join("");
        if(unique.includes(previous)) select.value=previous;
    }
    async function loadDashboard() {
        dashboardMachines=await requestJson("/api/dashboard");
        updateFilterSelect("filter-device",dashboardMachines.map(m=>m.device_id),"全部设备编号");
        updateFilterSelect("filter-mold",dashboardMachines.map(m=>m.mold_code),"全部模具编号");
        updateFilterSelect("filter-product",dashboardMachines.map(m=>m.product_code),"全部产品编号");
        renderDashboard();
    }
    function filteredMachines() {
        const device=document.getElementById("filter-device").value;
        const mold=document.getElementById("filter-mold").value;
        const product=document.getElementById("filter-product").value;
        const statuses=new Set([...document.querySelectorAll(".status-filter:checked")].map(input=>input.value));
        return dashboardMachines.filter(m=>(!device||m.device_id===device)&&(!mold||m.mold_code===mold)&&(!product||m.product_code===product)&&statuses.has(statusOf(m)));
    }
    function renderDashboard() {
        const totals={production:0,waiting:0,offline:0};
        dashboardMachines.forEach(m=>totals[statusOf(m)]++);
        document.getElementById("production-count").textContent=totals.production;
        document.getElementById("waiting-count").textContent=totals.waiting;
        document.getElementById("offline-count").textContent=totals.offline;
        const filtered=filteredMachines(),pages=Math.max(1,Math.ceil(filtered.length/pageSize));
        dashboardPage=Math.min(dashboardPage,pages);
        const start=(dashboardPage-1)*pageSize,current=filtered.slice(start,start+pageSize);
        const grid=document.getElementById("device-grid");
        grid.innerHTML=current.length?current.map(machine=>{
            const status=statusOf(machine),meta=statusMeta(status);
            return `<article class="device-card" data-device="${escapeHtml(machine.device_id)}"><div class="machine-visual"><div class="device-name">${escapeHtml(machine.device_id)}</div>${machineVisual(machine.device_id)}</div><div class="device-info">
                <div class="info-row"><span class="info-label">设备编号</span><span>${showValue(machine.device_id)}</span></div>
                <div class="info-row"><span class="info-label">产品编号</span><span>${showValue(machine.product_code)}</span></div>
                <div class="info-row"><span class="info-label">模具编号</span><strong>${showValue(machine.mold_code)}</strong></div>
                <div class="info-row"><span class="info-label">模具名称</span><span>${showValue(machine.mold_name)}</span></div>
                <div class="info-row"><span class="info-label">设备状态</span><span class="status-line"><span class="badge ${meta[1]}">${meta[0]}</span><span class="age">${ageText(machine.received_at)}</span></span></div>
                <div class="device-metrics">模次：${showValue(machine.cycle_number)}<br>周期时间：${showValue(machine.cycle_time," s")}<br>操作模式：${showValue(machine.operation_mode)}　油温：${showValue(machine.oil_temperature," ℃")}</div>
            </div></article>`;
        }).join(""):'<div class="empty panel">没有符合条件的设备</div>';
        grid.querySelectorAll(".device-card").forEach(card=>card.addEventListener("click",()=>{
            document.getElementById("device-select").value=card.dataset.device;
            switchPage("realtime");
        }));
        document.getElementById("page-summary").textContent=`共 ${filtered.length} 台，每页 ${pageSize} 台`;
        const buttons=document.getElementById("page-buttons");
        buttons.innerHTML=Array.from({length:pages},(_,i)=>`<button class="${i+1===dashboardPage?"active":""}" data-page-number="${i+1}">${i+1}</button>`).join("");
        buttons.querySelectorAll("button").forEach(button=>button.addEventListener("click",()=>{dashboardPage=Number(button.dataset.pageNumber);renderDashboard();}));
    }

    // Realtime page: labelled status + temperature tiles. Values arrive
    // already scaled from the API (backend/parameter_labels.py).
    async function loadRealtime() {
        const id=selectedDeviceId(); if(!id)return;
        const m=await requestJson(`/api/realtime/${encodeURIComponent(id)}`);
        const statusTiles=[
            metric("机器状态 (STS)",m.machine_status,"",true),
            metric("模式 (OPM)",m.operation_mode,"",true),
            metric("警报状态 (ASTS)",m.alarm_status,"",true),
            metric("生产油温 (OT)",m.oil_temperature," ℃",true),
        ].join("");
        const temperatureTiles=[1,2,3,4,5,6,7].map(i=>metric(`温度 T${i}`,m[`temperature_${i}`]," ℃")).join("");
        document.getElementById("realtime-page").innerHTML=`
            <article class="detail-card">
                <div class="detail-header"><div class="detail-title">设备 ${escapeHtml(id)} 实时参数</div><div class="muted">数据时间：${formatTime(m.data_time)}</div></div>
                <div class="metric-grid">${statusTiles}</div>
            </article>
            <article class="detail-card">
                <div class="detail-title">料筒温度</div>
                <div class="metric-grid">${temperatureTiles}</div>
            </article>`;
    }

    // Tech (工艺参数) page: fully driven by the API, which already joins
    // each parameter_id against the label file, applies scale, drops
    // parameters flagged use=0, and assigns a display category.
    async function loadTech() {
        const id=selectedDeviceId(); if(!id)return;
        const result=await requestJson(`/api/tech/${encodeURIComponent(id)}`);
        const groups=new Map();
        result.parameters.forEach(p=>{
            if(!groups.has(p.category)) groups.set(p.category,[]);
            groups.get(p.category).push(p);
        });
        const categoryOrder=["温度参数","压力参数","速度参数","位置参数","时间参数","模式设置","其他参数","未知参数"];
        const orderedCategories=[...groups.keys()].sort((a,b)=>categoryOrder.indexOf(a)-categoryOrder.indexOf(b));
        const sections=orderedCategories.map(category=>{
            const items=groups.get(category);
            const rows=items.map(p=>`<div class="parameter"><span>${escapeHtml(p.label)}</span><span>${showValue(p.value)}</span></div>`).join("");
            return `<div class="tech-group"><div class="tech-group-title">${escapeHtml(category)}</div><div class="parameter-grid">${rows}</div></div>`;
        }).join("");
        document.getElementById("tech-page").innerHTML=`<article class="detail-card"><div class="detail-header"><div class="detail-title">${escapeHtml(id)} 工艺参数</div><div class="muted">参数时间：${formatTime(result.data_time)}</div></div>${sections||'<div class="empty">暂无工艺参数</div>'}</article>`;
    }
    async function loadSpc() {
        const id=selectedDeviceId(); if(!id)return;
        const result=await requestJson(`/api/spc/${encodeURIComponent(id)}`),fields=Object.entries(spcFields).filter(([name])=>Object.hasOwn(result,name));
        document.getElementById("spc-page").innerHTML=`<article class="detail-card"><div class="detail-header"><div class="detail-title">${escapeHtml(id)} 最新 SPC</div><div class="muted">数据时间：${formatTime(result.data_time)}</div></div><div class="metric-grid">${fields.map(([name,meta])=>metric(meta[0],result[name],meta[1])).join("")}</div></article>`;
    }
    async function loadMolds() {
        const id=selectedDeviceId(); if(!id)return;
        [molds,devices]=await Promise.all([requestJson("/api/molds"),requestJson("/api/devices")]);
        const device=devices.find(d=>d.device_id===id);
        document.getElementById("current-mold").innerHTML=device?.mold_id?`<div class="muted">设备 ${escapeHtml(id)} 当前模具</div><div class="mold-code">${escapeHtml(device.mold_code)}</div><strong>${escapeHtml(device.mold_name)}</strong><div class="muted">产品：${showValue(device.product_code)} · ${showValue(device.cavities)} 穴</div><div class="muted">装模时间：${formatTime(device.mounted_at)}</div>`:`<div class="muted">设备 ${escapeHtml(id)}</div><div class="mold-code">未装模</div><div>请选择模具后执行装模。</div>`;
        const available=molds.filter(m=>m.is_active&&(!m.mounted_device_id||m.mounted_device_id===id));
        document.getElementById("mold-select").innerHTML='<option value="">选择模具</option>'+available.map(m=>`<option value="${m.id}">${escapeHtml(m.mold_code)} · ${escapeHtml(m.mold_name)}</option>`).join("");
        document.getElementById("unmount-button").disabled=currentUser.role==="viewer"||!device?.mold_id;
        document.getElementById("mold-list").innerHTML=molds.length?molds.map(m=>`<div class="mold-item"><strong>${escapeHtml(m.mold_code)} · ${escapeHtml(m.mold_name)}</strong><div class="muted">产品：${showValue(m.product_code)}　模穴：${showValue(m.cavities)}</div><div class="muted">${m.mounted_device_id?`已安装：${escapeHtml(m.mounted_device_id)}`:"当前空闲"}</div></div>`).join(""):'<div class="empty">尚未建立模具档案</div>';
        const history=await requestJson(`/api/devices/${encodeURIComponent(id)}/mold-history`);
        document.getElementById("mold-history").innerHTML=history.length?`<table><thead><tr><th>模具</th><th>装模时间</th><th>卸模时间</th><th>操作人</th></tr></thead><tbody>${history.map(h=>`<tr><td>${escapeHtml(h.mold_code)}</td><td>${formatTime(h.mounted_at)}</td><td>${formatTime(h.unmounted_at)}</td><td>${showValue(h.operator_username)}</td></tr>`).join("")}</tbody></table>`:'<div class="empty">暂无装模履历</div>';
    }

    async function refreshPage() {
        const status=document.getElementById("connection-status");
        try {
            if(currentPage==="dashboard")await loadDashboard();
            if(currentPage==="realtime")await loadRealtime();
            if(currentPage==="tech")await loadTech();
            if(currentPage==="spc")await loadSpc();
            if(currentPage==="molds")await loadMolds();
            status.className="connection";status.textContent=`更新于 ${new Date().toLocaleTimeString()}`;
        } catch(error){status.className="connection error";status.textContent=`读取失败：${error.message}`;}
    }
    async function switchPage(page) {
        currentPage=page;document.getElementById("page-title").textContent=pageTitles[page];
        document.querySelectorAll(".nav-item").forEach(item=>item.classList.toggle("active",item.dataset.page===page));
        document.querySelectorAll("main > section").forEach(section=>section.classList.add("hidden"));
        document.getElementById(`${page}-page`).classList.remove("hidden");
        await refreshPage();
    }

    const themeToggle=document.getElementById("theme-toggle");
    const themeIcon=document.getElementById("theme-icon");
    const themeLabel=document.getElementById("theme-label");
    function applyTheme(theme) {
        document.documentElement.setAttribute("data-theme",theme);
        const logoSrc=theme==="dark"?"/static/img/transparentLogo.png":"/static/img/logo.png";
        document.querySelectorAll(".logo-img").forEach(img=>img.src=logoSrc);
        if(themeIcon) themeIcon.textContent=theme==="dark"?"☀":"☾";
        if(themeLabel) themeLabel.textContent=theme==="dark"?"浅色模式":"深色模式";
        try{localStorage.setItem("mes-theme",theme);}catch(error){/* ignore storage errors */}
    }
    themeToggle?.addEventListener("click",()=>{
        const next=document.documentElement.getAttribute("data-theme")==="dark"?"light":"dark";
        applyTheme(next);
    });
    let savedTheme="light";
    try{savedTheme=localStorage.getItem("mes-theme")||"light";}catch(error){/* ignore storage errors */}
    applyTheme(savedTheme);

    document.querySelectorAll(".nav-item[data-page]").forEach(item=>item.addEventListener("click",()=>switchPage(item.dataset.page)));
    document.getElementById("device-select").addEventListener("change",refreshPage);
    document.getElementById("search-button").addEventListener("click",()=>{dashboardPage=1;renderDashboard();});
    document.querySelectorAll(".status-filter").forEach(input=>input.addEventListener("change",()=>{dashboardPage=1;renderDashboard();}));
    document.getElementById("logout-button").addEventListener("click",async()=>{await fetch("/api/auth/logout",{method:"POST"});window.location.replace("/login");});

    document.getElementById("mold-form").addEventListener("submit",async event=>{event.preventDefault();const f=new FormData(event.target);try{await requestJson("/api/molds",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({mold_code:f.get("mold_code"),mold_name:f.get("mold_name"),product_code:f.get("product_code")||null,cavities:Number(f.get("cavities")),remark:f.get("remark")||null})});event.target.reset();event.target.cavities.value=1;await loadMolds();}catch(error){alert(error.message);}});
    document.getElementById("mount-button").addEventListener("click",async()=>{const moldId=Number(document.getElementById("mold-select").value);if(!moldId)return alert("请先选择模具");if(!confirm(`确认将所选模具安装到设备 ${selectedDeviceId()}？`))return;try{await requestJson(`/api/devices/${encodeURIComponent(selectedDeviceId())}/mold`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({mold_id:moldId,remark:null})});await loadMolds();}catch(error){alert(error.message);}});
    document.getElementById("unmount-button").addEventListener("click",async()=>{if(!confirm(`确认卸下设备 ${selectedDeviceId()} 当前模具？`))return;try{await requestJson(`/api/devices/${encodeURIComponent(selectedDeviceId())}/mold`,{method:"DELETE"});await loadMolds();}catch(error){alert(error.message);}});

    const passwordDialog=document.getElementById("password-dialog");
    document.getElementById("password-button").addEventListener("click",()=>passwordDialog.showModal());
    document.getElementById("password-cancel").addEventListener("click",()=>passwordDialog.close());
    document.getElementById("password-form").addEventListener("submit",async event=>{event.preventDefault();const f=new FormData(event.target);try{await requestJson("/api/auth/change-password",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({current_password:f.get("current_password"),new_password:f.get("new_password")})});event.target.reset();passwordDialog.close();alert("密码修改成功");}catch(error){alert(error.message);}});

    async function initialize(){try{await loadSession();await loadDevices();await refreshPage();}catch(error){document.getElementById("connection-status").textContent=error.message;}}
    initialize();
    setInterval(()=>{if(currentPage==="dashboard"||currentPage==="realtime")refreshPage();},2000);
