let currentPage = "dashboard";
    let currentUser = null;
    let devices = [];
    let dashboardMachines = [];
    let molds = [];
    let dashboardPage = 1;
    const pageSize = 8;
    let uptimeChartIdCounter = 0;
    const utilRenderedOnce = { overview: false, daily: false, monthly: false };
    let detailDeviceId = null;
    let activeDetailTab = "realtime";
    let activeUtilTab = "overview";
    let techOpenCategories = new Set();
    let highlightParameter = null;
    let changelogFilters = { date: "", field: "", sub: "" };
    let deviceChangelogFilters = { date: "", field: "", sub: "" };
    let changelogFieldTree = null;
    const utilTabTitles = { overview: "总览", daily: "日统计", monthly: "月统计"};
    const pageTitles = { dashboard: "设备看板", molds: "模具管理", utilization: "利用率报表", changelog: "参数变更记录", warnings: "预警通知" };
    const detailTabTitles = { realtime: "实时参数", tech: "工艺参数", spc: "SPC 数据", changelog: "变更记录" };
    let seenWarningIds = new Set();
    let warningsInitialized = false;
    const techCategoryUnits = {
        "温度参数": " ℃",
        "压力参数": " MPa",
        "速度参数": " mm/s",
        "位置参数": " mm",
        "时间参数": " s"
    };

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

    async function loadChangelogFieldTree() {
        if (changelogFieldTree) return changelogFieldTree;
        changelogFieldTree = await requestJson("/api/changelog/filters");
        return changelogFieldTree;
    }

    function changelogQuery(filters) {
        const params = new URLSearchParams();
        if (filters.date) params.set("date", filters.date);
        if (filters.field) params.set("field", filters.field);
        if (filters.sub) params.set("sub", filters.sub);
        const qs = params.toString();
        return qs ? `?${qs}` : "";
    }

    function statusOf(machine) {
        if(!machine.received_at) return "offline";
        const age=Date.now()-new Date(machine.received_at).getTime();
        if(!Number.isFinite(age)||age>120000) return "offline";
        return Number(machine.machine_status)===2 ? "production" : "waiting";
    }
    function statusMeta(status) { return status==="production"?["生产","production"]:status==="waiting"?["待机","waiting"]:["离线","offline"]; }

    function ageText(value) {
        if(!value) return "无数据";
        const seconds=Math.max(0,Math.floor((Date.now()-new Date(value).getTime())/1000));
        if(seconds<60) return `${seconds} 秒前`;
        if(seconds<3600) return `${Math.floor(seconds/60)} 分钟前`;
        return `${Math.floor(seconds/3600)} 小时前`;
    }

    function ageText(value) {
        if(!value) return "无数据";
        const seconds=Math.max(0,Math.floor((Date.now()-new Date(value).getTime())/1000));
        if(seconds<60) return `${seconds} 秒前`;
        if(seconds<3600) return `${Math.floor(seconds/60)} 分钟前`;
        return `${Math.floor(seconds/3600)} 小时前`;
    }

    function formatDurationMinutes(totalMinutes) {
        if (totalMinutes < 60) return `${totalMinutes} 分钟`;
        const hours = Math.floor(totalMinutes / 60);
        const minutes = totalMinutes % 60;
        return minutes > 0 ? `${hours} 小时 ${minutes} 分钟` : `${hours} 小时`;
    }

    async function loadSession() {
        currentUser=await requestJson("/api/auth/me");
        document.getElementById("user-label").textContent=`${currentUser.username} · ${currentUser.role}`;
        const readOnly=currentUser.role==="viewer";
        document.getElementById("mold-form").querySelectorAll("input,textarea,button").forEach(el=>el.disabled=readOnly);
        document.getElementById("mount-button").disabled=readOnly;
        document.getElementById("unmount-button").disabled=readOnly;
        document.getElementById("clear-all-warnings").disabled=readOnly;
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
                <div class="device-metrics">模次：${showValue(machine.cycle_number)}<br>周期时间：${showValue(machine.cycle_time," s")}<br>操作模式：${showValue(machine.operation_mode_label)}　油温：${showValue(machine.oil_temperature," ℃")}</div>
            </div></article>`;
        }).join(""):'<div class="empty panel">没有符合条件的设备</div>';
        grid.querySelectorAll(".device-card").forEach(card=>card.addEventListener("click",()=>openDeviceDetail(card.dataset.device)));
        document.getElementById("page-summary").textContent=`共 ${filtered.length} 台，每页 ${pageSize} 台`;
        const buttons=document.getElementById("page-buttons");
        buttons.innerHTML=Array.from({length:pages},(_,i)=>`<button class="${i+1===dashboardPage?"active":""}" data-page-number="${i+1}">${i+1}</button>`).join("");
        buttons.querySelectorAll("button").forEach(button=>button.addEventListener("click",()=>{dashboardPage=Number(button.dataset.pageNumber);renderDashboard();}));
    }

    function renderDayTimeline(dayStart, dayEnd, segments) {
        const startMs = new Date(dayStart).getTime();
        const endMs = new Date(dayEnd).getTime();
        const totalMs = Math.max(1, endMs - startMs);
        const blocks = segments.map(seg => {
            const segStart = new Date(seg.start).getTime();
            const segEnd = new Date(seg.end).getTime();
            const left = (segStart - startMs) / totalMs * 100;
            const width = Math.max(0.15, (segEnd - segStart) / totalMs * 100);
            const durationMin = Math.round((segEnd - segStart) / 60000);
            const meta = statusMeta(seg.status);
            return `<div class="day-timeline-segment ${meta[1]}" style="left:${left}%;width:${width}%" title="${meta[0]} ${formatTime(seg.start)} - ${formatTime(seg.end)} (${formatDurationMinutes(durationMin)})"></div>`;
        }).join("");
        const hourLabels = Array.from({length:9},(_,i)=>`<span>${i*3}:00</span>`).join("");
        return `<div class="day-timeline">${blocks}</div><div class="day-timeline-hours">${hourLabels}</div>`;
    }

    function renderDaySegmentList(segments) {
        if(!segments.length) return '<div class="empty">暂无数据</div>';
        return `<div class="day-detail-segments">${segments.map(seg=>{
            const durationMin=Math.round((new Date(seg.end)-new Date(seg.start))/60000);
            const meta=statusMeta(seg.status);
            return `<div class="day-detail-segment-row"><span class="badge ${meta[1]}">${meta[0]}</span><span>${formatTime(seg.start)} → ${formatTime(seg.end)}</span><span class="muted">${formatDurationMinutes(durationMin)}</span></div>`;
        }).join("")}</div>`;
    }

    async function openDayDetail(deviceId, dateStr) {
        const dialog=document.getElementById("day-detail-dialog");
        document.getElementById("day-detail-title").textContent=`设备 ${deviceId} · ${dateStr}`;
        document.getElementById("day-detail-body").innerHTML='<div class="empty">正在读取……</div>';
        dialog.showModal();
        try {
            const data=await requestJson(`/api/uptime/${encodeURIComponent(deviceId)}/day?date=${encodeURIComponent(dateStr)}`);
            document.getElementById("day-detail-body").innerHTML=`
                ${renderDayTimeline(data.day_start,data.day_end,data.segments)}
                <div class="day-detail-legend"><span><i class="dot active"></i>生产</span><span><i class="dot standby"></i>待机</span><span><i class="dot off"></i>关机</span></div>
                ${renderDaySegmentList(data.segments)}`;
        } catch(error) {
            document.getElementById("day-detail-body").innerHTML=`<div class="empty">读取失败：${escapeHtml(error.message)}</div>`;
        }
    }
    document.getElementById("day-detail-close").addEventListener("click",()=>document.getElementById("day-detail-dialog").close());

    // Realtime tab: labelled status + temperature tiles. Values arrive
    // already scaled from the API (backend/parameter_labels.py).
    async function loadRealtime(id) {
        const m=await requestJson(`/api/realtime/${encodeURIComponent(id)}`);
        const statusTiles=[
            metric("机器状态 (STS)",m.machine_status_label,"",true),
            metric("模式 (OPM)",m.operation_mode_label,"",true),
            metric("警报状态 (ASTS)",m.alarm_status_label,"",true),
            metric("生产油温 (OT)",m.oil_temperature," ℃",true),
        ].join("");
        const temperatureTiles=[1,2,3,4,5,6,7].map(i=>metric(`温度 T${i}`,m[`temperature_${i}`]," ℃")).join("");
        document.getElementById("detail-tab-realtime").innerHTML=`
            <article class="detail-card">
                <div class="detail-header"><div class="detail-title">实时状态</div><div class="muted">数据时间：${formatTime(m.data_time)}</div></div>
                <div class="metric-grid">${statusTiles}</div>
            </article>
            <article class="detail-card">
                <div class="detail-title">料筒温度</div>
                <div class="metric-grid">${temperatureTiles}</div>
            </article>`;
    }

    function groupTechParameters(items) {
        const groups=new Map();
        const order=[];
        items.forEach(p=>{
            const match=p.label.match(/\d+/);
            const number=match?parseInt(match[0],10):null;
            const baseKey=p.label.replace(/\d+/g,"").trim()||p.label;
            if(!groups.has(baseKey)){groups.set(baseKey,[]);order.push(baseKey);}
            groups.get(baseKey).push({...p,number});
        });
        return order.map(key=>({key,items:groups.get(key)}));
    }

    // Tech (工艺参数) tab: fully driven by the API, which already joins
    // each parameter_id against the label file, applies scale, drops
    // parameters flagged use=0, and assigns a display category. The
    // category also picks which unit (if any) is appended to the value.
    // Within each category, numbered variants of the same parameter are
    // grouped onto a single row (see groupTechParameters above).
    //
    // Categories render collapsed by default when a device is first opened
    // (techOpenCategories starts empty); the "展开全部" / "收起全部" buttons
    // and each section's own toggle update techOpenCategories so state
    // survives the 2-second auto-refresh.
    //
    // When this tab is opened from a changelog entry (see openChangelogDetail),
    // highlightParameter names the changed tag: its category is force-opened
    // and its row gets the .parameter-changed style, with a banner showing
    // the previous -> new value at the top of the card. The force-open and
    // the scroll-into-view below only happen the FIRST time loadTech() runs
    // for this highlight (see highlightApplied) -- loadTech() also runs on
    // every 2-second auto-refresh while this tab stays open, and without
    // this guard it would keep re-opening the category (even if the user
    // just closed it) and re-scrolling the page on every tick.
    async function loadTech(id) {
        const result=await requestJson(`/api/tech/${encodeURIComponent(id)}`);
        const groups=new Map();
        result.parameters.forEach(p=>{
            if(!groups.has(p.category)) groups.set(p.category,[]);
            groups.get(p.category).push(p);
        });

        let highlightMatch=null;
        if(highlightParameter && highlightParameter.parameter_id){
            highlightMatch=result.parameters.find(p=>p.parameter_id===highlightParameter.parameter_id)||null;
            if(highlightMatch && !highlightApplied) techOpenCategories.add(highlightMatch.category);
        }

        const categoryOrder=["温度参数","压力参数","速度参数","位置参数","时间参数","模式设置","其他参数","未知参数"];
        const orderedCategories=[...groups.keys()].sort((a,b)=>categoryOrder.indexOf(a)-categoryOrder.indexOf(b));
        function renderCategory(category) {
            const items=groups.get(category);
            const unit=techCategoryUnits[category]||"";
            const paramGroups=groupTechParameters(items);
            const rows=paramGroups.map(group=>{
                if(group.items.length===1){
                    const p=group.items[0];
                    const changed=highlightParameter && p.parameter_id===highlightParameter.parameter_id;
                    return `<div class="parameter${changed?" parameter-changed":""}" data-parameter="${escapeHtml(p.parameter_id)}"><span>${escapeHtml(p.label)}</span><span>${showValue(p.value,unit)}</span></div>`;
                }
                const sorted=[...group.items].sort((a,b)=>(a.number??0)-(b.number??0));
                const chips=sorted.map(p=>{
                    const changed=highlightParameter && p.parameter_id===highlightParameter.parameter_id;
                    return `<span class="parameter-chip${changed?" parameter-changed":""}" data-parameter="${escapeHtml(p.parameter_id)}"><span class="chip-index">${p.number??""}</span><span class="chip-value">${showValue(p.value,unit)}</span></span>`;
                }).join("");
                return `<div class="parameter-group"><span class="parameter-group-label">${escapeHtml(group.key)}</span><span class="parameter-group-values">${chips}</span></div>`;
            }).join("");
            const isOpen=techOpenCategories.has(category);
            return `<details class="tech-group" data-category="${escapeHtml(category)}"${isOpen?" open":""}>
                <summary class="tech-group-title">
                    <span class="tech-group-title-text">${escapeHtml(category)}</span>
                    <span class="tech-group-meta"><span class="tech-group-count">${items.length}</span><span class="chevron">▸</span></span>
                </summary>
                <div class="parameter-grid">${rows}</div>
            </details>`;
        }
        // Categories are split into two fixed columns up front (instead of
        // CSS multi-column flow) so opening/closing one section never moves
        // another section into a different column -- each category has a
        // permanent left/right slot for the lifetime of this render.
        const leftCategories=orderedCategories.filter((_,i)=>i%2===0);
        const rightCategories=orderedCategories.filter((_,i)=>i%2===1);
        const leftHtml=leftCategories.map(renderCategory).join("");
        const rightHtml=rightCategories.map(renderCategory).join("");
        const hasSections=orderedCategories.length>0;
        const highlightBanner=(highlightParameter && highlightParameter.parameter_id)?`<div class="changelog-banner">变更提示：<strong>${escapeHtml(highlightMatch?highlightMatch.label:highlightParameter.parameter_id)}</strong> ${showValue(highlightParameter.previous_value)} → <strong class="changelog-banner-new">${showValue(highlightParameter.new_value)}</strong></div>`:"";
        document.getElementById("detail-tab-tech").innerHTML=`<article class="detail-card">${highlightBanner}<div class="detail-header"><div class="detail-title">工艺参数</div><div class="tech-header-actions"><button type="button" class="tech-action-button" id="tech-toggle-all">全部展开</button><span class="muted">参数时间：${formatTime(result.data_time)}</span></div></div><div class="tech-groups-grid">${hasSections?`<div class="tech-groups-column">${leftHtml}</div><div class="tech-groups-column">${rightHtml}</div>`:'<div class="empty">暂无工艺参数</div>'}</div></article>`;

        function updateToggleAllLabel() {
            const button=document.getElementById("tech-toggle-all");
            if(!button) return;
            const allDetails=document.querySelectorAll("#detail-tab-tech details.tech-group");
            const allOpen=allDetails.length>0 && [...allDetails].every(details=>details.open);
            button.textContent=allOpen?"全部收起":"全部展开";
        }

        document.querySelectorAll("#detail-tab-tech details.tech-group").forEach(details=>{
            details.addEventListener("toggle",()=>{
                const category=details.dataset.category;
                if(details.open) techOpenCategories.add(category);
                else techOpenCategories.delete(category);
                updateToggleAllLabel();
            });
        });
        document.getElementById("tech-toggle-all")?.addEventListener("click",()=>{
            const allDetails=document.querySelectorAll("#detail-tab-tech details.tech-group");
            const allOpen=allDetails.length>0 && [...allDetails].every(details=>details.open);
            const nextOpen=!allOpen;
            allDetails.forEach(details=>{
                details.open=nextOpen;
                if(nextOpen) techOpenCategories.add(details.dataset.category);
                else techOpenCategories.delete(details.dataset.category);
            });
            updateToggleAllLabel();
        });
        updateToggleAllLabel();

        if(highlightParameter && highlightParameter.parameter_id && !highlightApplied){
            const target=document.querySelector(`#detail-tab-tech [data-parameter="${CSS.escape(highlightParameter.parameter_id)}"]`);
            target?.scrollIntoView({block:"center",behavior:"smooth"});
            highlightApplied=true;
        }
    }
    async function loadSpc(id) {
        const result=await requestJson(`/api/spc/${encodeURIComponent(id)}`),fields=Object.entries(spcFields).filter(([name])=>Object.hasOwn(result,name));
        document.getElementById("detail-tab-spc").innerHTML=`<article class="detail-card"><div class="detail-header"><div class="detail-title">最新 SPC</div><div class="muted">数据时间：${formatTime(result.data_time)}</div></div><div class="metric-grid">${fields.map(([name,meta])=>metric(meta[0],result[name],meta[1])).join("")}</div></article>`;
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

    function renderUptimeBar(bucket) {
        const total = bucket.total_seconds || 1;
        const activePct = bucket.active_seconds/total*100;
        const standbyPct = bucket.standby_seconds/total*100;
        const offPct = bucket.off_seconds/total*100;
        return `<div class="uptime-bar" title="生产 ${activePct.toFixed(1)}% · 待机 ${standbyPct.toFixed(1)}% · 关机 ${offPct.toFixed(1)}%">
            <div class="uptime-bar-segment off" style="width:${Math.min(100, activePct+standbyPct+offPct)}%"></div>
            <div class="uptime-bar-segment standby" style="width:${Math.min(100, activePct+standbyPct)}%"></div>
            <div class="uptime-bar-segment active" style="width:${Math.min(100, activePct)}%"></div>
        </div>`;
    }

    function renderUptimeTrendChart(buckets) {
        if(!buckets.length) return '<div class="empty">暂无数据</div>';
        const width=920, height=300, padL=40, padR=14, padT=18, padB=30;
        const innerW=width-padL-padR, innerH=height-padT-padB;
        const stepX = buckets.length>1 ? innerW/(buckets.length-1) : 0;
        const points = buckets.map((b,i)=>{
            const x = padL + stepX*i;
            const y = padT + innerH - (b.uptime_pct/100)*innerH;
            return {x,y,b};
        });
        const linePath = points.map((p,i)=>`${i===0?"M":"L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");

        const gridLines=[0,25,50,75,100].map(v=>{
            const y=padT+innerH-(v/100)*innerH;
            return `<line x1="${padL}" y1="${y}" x2="${width-padR}" y2="${y}" stroke="#e2e8f0" stroke-width="1"/><text x="${padL-8}" y="${y+4}" font-size="10" fill="#9098a2" text-anchor="end">${v}%</text>`;
        }).join("");
        const labelEvery=Math.max(1,Math.ceil(buckets.length/8));
        const xLabels = points.map((p,i)=> i%labelEvery===0 ? `<text x="${p.x}" y="${height-8}" font-size="10" fill="#9098a2" text-anchor="middle">${escapeHtml(p.b.label)}</text>` : "").join("");
        const dots = points.map((p)=>
            `<circle class="uptime-trend-dot" cx="${p.x}" cy="${p.y}" r="3" fill="#19b58a"><title>${escapeHtml(p.b.label)}: ${p.b.uptime_pct}%</title></circle>`
        ).join("");
        return `<div class="uptime-trend-wrap">
            <svg class="uptime-trend-svg uptime-trend-bg" viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet">
                ${gridLines}
                ${xLabels}
            </svg>
            <svg class="uptime-trend-svg uptime-trend-fg" viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet">
                <path d="${linePath}" fill="none" stroke="#19b58a" stroke-width="2"/>
                ${dots}
            </svg>
        </div>`;
    }


    // Collapses whatever bars/trend-line are currently sitting in a
    // 利用率 tab's DOM -- leftover from a previous visit -- back to their
    // zero-width starting point. Must be called synchronously, in the
    // same tick as deciding a tab needs a fresh entrance animation and
    // BEFORE that tab's container is unhidden. Without this, the stale
    // fully-drawn content (kept around on purpose so refreshes don't
    // flash) stays visible for the whole async data fetch every time you
    // click back into a tab, and then visibly snaps to empty the instant
    // the fetch resolves and playUtilEntranceAnimation() takes over --
    // that snap is the bug, not the animation itself.
    function collapseUtilAnimatables(container) {
        // Cancel any still-active entrance animations left over from the
        // last time this container was rendered. playUtilEntranceAnimation
        // uses fill:"both", which means a *finished* animation keeps
        // forcing its end-state (full size) onto the element with higher
        // priority than any inline style set below. Without canceling it
        // first, the stale bars/chart stay visually stuck at full size for
        // the whole time this container sits here waiting for fresh data
        // on a return visit -- our collapse below would otherwise silently
        // have no visible effect, which is exactly the "shows fully, then
        // swaps" flash this function exists to prevent.
        container.getAnimations({ subtree: true }).forEach(animation => animation.cancel());
        container.querySelectorAll(".uptime-bar-segment").forEach(segment => {
            segment.style.transform = "scaleX(0)";
        });
        container.querySelectorAll(".uptime-trend-fg").forEach(fg => {
            fg.style.clipPath = "inset(0 100% 0 0)";
        });
    }

    function playUtilEntranceAnimation(container) {
        if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

        const segments = container.querySelectorAll(".uptime-bar-segment");
        const trends = container.querySelectorAll(".uptime-trend-fg");

        // The freshly-rendered bars/chart just landed in the DOM (via
        // innerHTML) at their real, final size -- none of these elements
        // have ever had the collapsed inline style applied, since they're
        // brand new nodes. For each element we pin it to its collapsed
        // starting point AND start its animation in the same step, back to
        // back, rather than doing "reset all elements to collapsed" and
        // "start all animations" as two separate passes over the list.
        // With ~90 bar segments on the daily/monthly views, a two-pass
        // approach leaves a real window, after the reset pass finishes but
        // before every element's animate() call has run, where the
        // browser can paint the elements at their true uncollapsed size --
        // that's what read as "everything shows fully, then flashes into
        // the animation". Setting the inline style immediately before
        // calling .animate() on the very same element closes that window,
        // since nothing else can be painted in between the two calls.
        segments.forEach(segment => {
            segment.style.transform = "scaleX(0)";
            segment.animate(
                [{ transform: "scaleX(0)" }, { transform: "scaleX(1)" }],
                { duration: 3200, easing: "cubic-bezier(.4,0,.2,1)", fill: "both" }
            );
        });

        trends.forEach(fg => {
            fg.style.clipPath = "inset(0 100% 0 0)";
            fg.animate(
                [{ clipPath: "inset(0 100% 0 0)" }, { clipPath: "inset(0 0% 0 0)" }],
                { duration: 4200, easing: "cubic-bezier(.4,0,.2,1)", fill: "both" }
            );
        });
    }

    async function loadUtilizationOverview(id) {
        const overviewContainer = document.getElementById("util-tab-overview");
        const freshEntry = !utilRenderedOnce.overview;
        const [dayData, weekData, monthData] = await Promise.all([
            requestJson(`/api/uptime/${encodeURIComponent(id)}?granularity=day&periods=30`),
            requestJson(`/api/uptime/${encodeURIComponent(id)}?granularity=week&periods=1`),
            requestJson(`/api/uptime/${encodeURIComponent(id)}?granularity=month&periods=1`),
        ]);
        const today = dayData.buckets[dayData.buckets.length-1];
        const thisWeek = weekData.buckets[weekData.buckets.length-1];
        const thisMonth = monthData.buckets[monthData.buckets.length-1];
        overviewContainer.innerHTML = `
            <div class="uptime-summary-grid">
                <div class="uptime-summary-card"><div class="muted">今日稼动率</div><div class="uptime-summary-value">${today?today.uptime_pct:0}%</div>${today?renderUptimeBar(today):""}</div>
                <div class="uptime-summary-card"><div class="muted">本周稼动率</div><div class="uptime-summary-value">${thisWeek?thisWeek.uptime_pct:0}%</div>${thisWeek?renderUptimeBar(thisWeek):""}</div>
                <div class="uptime-summary-card"><div class="muted">本月稼动率</div><div class="uptime-summary-value">${thisMonth?thisMonth.uptime_pct:0}%</div>${thisMonth?renderUptimeBar(thisMonth):""}</div>
            </div>
            <article class="detail-card">
                <div class="detail-header"><div class="detail-title">近30日稼动率趋势</div>
                    <div class="uptime-legend"><span><i class="dot active"></i>生产</span><span><i class="dot standby"></i>待机</span><span><i class="dot off"></i>关机</span></div>
                </div>
                ${renderUptimeTrendChart(dayData.buckets)}
            </article>`;
        if (freshEntry) playUtilEntranceAnimation(overviewContainer);
        utilRenderedOnce.overview = true;
    }

    async function loadUtilizationDaily(id) {
        const dailyContainer = document.getElementById("util-tab-daily");
        const freshEntry = !utilRenderedOnce.daily;
        const data = await requestJson(`/api/uptime/${encodeURIComponent(id)}?granularity=day&periods=30`);
        dailyContainer.innerHTML = `
            <article class="detail-card">
                <div class="detail-header"><div class="detail-title">日稼动率趋势（近30日）</div></div>
                ${renderUptimeTrendChart(data.buckets)}
            </article>
            <article class="detail-card">
                <div class="detail-title">每日明细</div>
                <div class="uptime-bucket-list">${data.buckets.slice().reverse().map((b)=>`
                        <div class="uptime-bucket-row" data-date="${b.period_start}">
                        <span class="uptime-bucket-label">${escapeHtml(b.label)}</span>
                        ${renderUptimeBar(b)}
                        <span class="uptime-bucket-pct">${b.uptime_pct}%</span>
                    </div>`).join("")}</div>
            </article>`;
        document.querySelectorAll("#util-tab-daily .uptime-bucket-row").forEach(row=>{
            row.addEventListener("click",()=>openDayDetail(id,row.dataset.date));
        });
        if (freshEntry) playUtilEntranceAnimation(dailyContainer);
        utilRenderedOnce.daily = true;
    }

    async function loadUtilizationMonthly(id) {
        const monthlyContainer = document.getElementById("util-tab-monthly");
        const freshEntry = !utilRenderedOnce.monthly;
        const data = await requestJson(`/api/uptime/${encodeURIComponent(id)}?granularity=month&periods=12`);
        monthlyContainer.innerHTML = `
            <article class="detail-card">
                <div class="detail-header"><div class="detail-title">月稼动率趋势（近12个月）</div></div>
                ${renderUptimeTrendChart(data.buckets)}
            </article>
            <article class="detail-card">
                <div class="detail-title">每月明细</div>
                <div class="uptime-bucket-list">${data.buckets.slice().reverse().map((b)=>`
                    <div class="uptime-bucket-row">
                        <span class="uptime-bucket-label">${escapeHtml(b.label)}</span>
                        ${renderUptimeBar(b)}
                        <span class="uptime-bucket-pct">${b.uptime_pct}%</span>
                    </div>`).join("")}</div>
            </article>`;
        if (freshEntry) playUtilEntranceAnimation(monthlyContainer);
        utilRenderedOnce.monthly = true;
    }

    async function loadUtilization(tab) {
        const id = selectedDeviceId();
        if(!id) { document.getElementById(`util-tab-${tab}`).innerHTML = '<div class="empty panel">请先选择设备</div>'; return; }
        if(tab==="overview") await loadUtilizationOverview(id);
        else if(tab==="daily") await loadUtilizationDaily(id);
        else if(tab==="monthly") await loadUtilizationMonthly(id);
    }

    async function loadChangelog() {
        const tree = await loadChangelogFieldTree();
        const fieldSelect = document.getElementById("changelog-filter-field");
        if (!fieldSelect.dataset.populated) {
            fieldSelect.innerHTML = '<option value="">全部分类</option>' +
                Object.keys(tree).map(f => `<option value="${escapeHtml(f)}">${escapeHtml(f)}</option>`).join("");
            fieldSelect.dataset.populated = "1";
        }

        const rows = await requestJson(`/api/changelog${changelogQuery(changelogFilters)}`);
        document.getElementById("changelog-summary").textContent = `共 ${rows.length} 条记录`;
        const table = document.getElementById("changelog-table");
        table.innerHTML = rows.length
            ? `<table><thead><tr><th>时间</th><th>设备编号</th><th>变量</th><th>原值</th><th>新值</th><th>SPC</th></tr></thead><tbody>${rows.map(r=>`<tr class="changelog-row" data-id="${r.id}"><td>${formatTime(r.data_time||r.detected_at)}</td><td>${escapeHtml(r.device_id)}</td><td>${escapeHtml(r.label)}</td><td>${showValue(r.previous_value)}</td><td class="changelog-new-value">${showValue(r.new_value)}</td><td>${r.spc_message_id?`SPC #${r.spc_message_id}`:'<span class="muted">待关联</span>'}</td></tr>`).join("")}</tbody></table>`
            : '<div class="empty">没有符合筛选条件的变更记录</div>';
        table.querySelectorAll(".changelog-row").forEach(row=>row.addEventListener("click",()=>openChangelogDetail(row.dataset.id)));
    }

    // The 变更记录 tab is split into a "shell" (card header + filter bar)
    // and a "results" pane (count + table). loadDeviceChangelog() is what
    // the 2-second auto-refresh calls; it only rebuilds the shell the
    // first time a device's changelog tab is opened (or when switching to
    // a different device) and otherwise just refreshes the results pane.
    // This keeps the filter <select>/<input> elements untouched by the
    // periodic refresh, so an open dropdown or a focused date field never
    // gets yanked out from under the user mid-interaction.
    async function loadDeviceChangelog(id) {
        const container = document.getElementById("detail-tab-changelog");
        if (container.dataset.deviceId !== id || !container.querySelector(".filter-body")) {
            await renderDeviceChangelogShell(id);
        } else {
            await refreshDeviceChangelogRows(id);
        }
    }

    async function renderDeviceChangelogShell(id) {
        const tree = await loadChangelogFieldTree();
        const container = document.getElementById("detail-tab-changelog");
        container.dataset.deviceId = id;

        const fieldOptions = Object.keys(tree).map(f =>
            `<option value="${escapeHtml(f)}"${deviceChangelogFilters.field===f?" selected":""}>${escapeHtml(f)}</option>`).join("");
        const subOptions = (deviceChangelogFilters.field && tree[deviceChangelogFilters.field])
            ? Object.keys(tree[deviceChangelogFilters.field]).map(s =>
                `<option value="${escapeHtml(s)}"${deviceChangelogFilters.sub===s?" selected":""}>${escapeHtml(s)}</option>`).join("")
            : "";

        container.innerHTML = `<article class="detail-card">
            <div class="detail-header"><div class="detail-title">变更记录</div><div class="muted" id="device-changelog-count"></div></div>
            <div class="filter-body" style="padding:0 0 14px;">
                <div class="field"><label>日期</label><input type="date" id="device-changelog-filter-date" value="${escapeHtml(deviceChangelogFilters.date)}"></div>
                <div class="field"><label>参数分类</label><select id="device-changelog-filter-field"><option value="">全部分类</option>${fieldOptions}</select></div>
                <div class="field"><label>具体参数</label><select id="device-changelog-filter-sub" ${deviceChangelogFilters.field?"":"disabled"}><option value="">全部参数</option>${subOptions}</select></div>
                <div class="field"><label>&nbsp;</label><button id="device-changelog-filter-clear" class="secondary-button" type="button">清除筛选</button></div>
            </div>
            <div id="device-changelog-results"></div>
        </article>`;

        document.getElementById("device-changelog-filter-date").addEventListener("change", async e => {
            deviceChangelogFilters.date = e.target.value;
            await refreshDeviceChangelogRows(id);
        });
        document.getElementById("device-changelog-filter-field").addEventListener("change", async e => {
            deviceChangelogFilters.field = e.target.value;
            deviceChangelogFilters.sub = "";
            const subSelect = document.getElementById("device-changelog-filter-sub");
            if (deviceChangelogFilters.field && tree[deviceChangelogFilters.field]) {
                subSelect.innerHTML = '<option value="">全部参数</option>' +
                    Object.keys(tree[deviceChangelogFilters.field]).map(s => `<option value="${escapeHtml(s)}">${escapeHtml(s)}</option>`).join("");
                subSelect.disabled = false;
            } else {
                subSelect.innerHTML = '<option value="">全部参数</option>';
                subSelect.disabled = true;
            }
            await refreshDeviceChangelogRows(id);
        });
        document.getElementById("device-changelog-filter-sub").addEventListener("change", async e => {
            deviceChangelogFilters.sub = e.target.value;
            await refreshDeviceChangelogRows(id);
        });
        document.getElementById("device-changelog-filter-clear").addEventListener("click", async () => {
            deviceChangelogFilters = { date: "", field: "", sub: "" };
            document.getElementById("device-changelog-filter-date").value = "";
            document.getElementById("device-changelog-filter-field").value = "";
            const subSelect = document.getElementById("device-changelog-filter-sub");
            subSelect.innerHTML = '<option value="">全部参数</option>';
            subSelect.disabled = true;
            await refreshDeviceChangelogRows(id);
        });

        await refreshDeviceChangelogRows(id);
    }

    async function refreshDeviceChangelogRows(id) {
        const rows = await requestJson(`/api/changelog/by-device/${encodeURIComponent(id)}${changelogQuery(deviceChangelogFilters)}`);
        const countEl = document.getElementById("device-changelog-count");
        if (countEl) countEl.textContent = `共 ${rows.length} 条记录`;
        const resultsEl = document.getElementById("device-changelog-results");
        if (!resultsEl) return; // tab was navigated away from mid-fetch
        resultsEl.innerHTML = rows.length
            ? `<table><thead><tr><th>时间</th><th>变量</th><th>原值</th><th>新值</th><th>SPC</th></tr></thead><tbody>${rows.map(r=>`<tr class="changelog-row" data-id="${r.id}" data-parameter="${escapeHtml(r.parameter_id)}" data-previous="${escapeHtml(r.previous_value??"")}" data-new="${escapeHtml(r.new_value??"")}"><td>${formatTime(r.data_time||r.detected_at)}</td><td>${escapeHtml(r.label)}</td><td>${showValue(r.previous_value)}</td><td class="changelog-new-value">${showValue(r.new_value)}</td><td>${r.spc_message_id?`SPC #${r.spc_message_id}`:'<span class="muted">待关联</span>'}</td></tr>`).join("")}</tbody></table>`
            : '<div class="empty">没有符合筛选条件的变更记录</div>';
        resultsEl.querySelectorAll(".changelog-row").forEach(row => {
            row.addEventListener("click", () => {
                highlightParameter = {
                    parameter_id: row.dataset.parameter,
                    previous_value: row.dataset.previous,
                    new_value: row.dataset.new,
                };
                highlightApplied = false;
                switchDetailTab("tech");
            });
        });
    }

    async function openChangelogDetail(id) {
        try {
            const entry=await requestJson(`/api/changelog/${encodeURIComponent(id)}`);
            await openDeviceDetail(entry.device_id,{
                tab:"tech",
                highlight:{parameter_id:entry.parameter_id,previous_value:entry.previous_value,new_value:entry.new_value}
            });
        } catch(error){ alert(error.message); }
    }

    // ---- 预警通知 (warnings) ----
    // A warning is an unacknowledged dbo.tech_parameter_changelog row (see
    // GET /api/warnings). Clicking a toast or a row in the 预警通知 tab
    // redirects to 参数变更记录 / the highlighted parameter, matching how
    // changelog rows already behave -- warnings are just "changelog entries
    // you haven't dismissed yet", not a separate record type.

    function showToast(warning) {
        const container=document.getElementById("toast-container");
        if(!container) return;
        const toast=document.createElement("div");
        toast.className="toast";
        toast.innerHTML=`
            <div class="toast-icon">⚠</div>
            <div class="toast-body">
                <div class="toast-title">参数变更：设备 ${escapeHtml(warning.device_id)}</div>
                <div class="toast-detail">${escapeHtml(warning.label)}　${showValue(warning.previous_value)} → ${showValue(warning.new_value)}</div>
            </div>
            <button class="toast-close" type="button" aria-label="关闭">✕</button>`;
        toast.addEventListener("click",event=>{
            if(event.target.closest(".toast-close")) return;
            switchPage("changelog");
            toast.remove();
        });
        toast.querySelector(".toast-close").addEventListener("click",event=>{
            event.stopPropagation();
            toast.remove();
        });
        container.appendChild(toast);
        setTimeout(()=>{
            toast.classList.add("toast-hide");
            setTimeout(()=>toast.remove(),300);
        },8000);
    }

    // Polls pending warnings independently of the current page/tab, so a
    // toast can appear (and the sidebar badge update) no matter what the
    // user is looking at. Runs on its own interval -- see setInterval call
    // near initialize() below -- separate from scheduleAutoRefresh, which
    // only ticks while on the dashboard/device-detail pages.
    async function pollWarnings() {
        try {
            const rows=await requestJson("/api/warnings");
            const badge=document.getElementById("warnings-badge");
            if(badge){
                if(rows.length>0){ badge.textContent=rows.length>99?"99+":rows.length; badge.classList.remove("hidden"); }
                else badge.classList.add("hidden");
            }
            if(!warningsInitialized){
                rows.forEach(r=>seenWarningIds.add(r.id));
                warningsInitialized=true;
                return;
            }
            const newOnes=rows.filter(r=>!seenWarningIds.has(r.id)).sort((a,b)=>a.id-b.id);
            newOnes.forEach(r=>{ seenWarningIds.add(r.id); showToast(r); });
            if(currentPage==="warnings" && newOnes.length) await loadWarnings();
        } catch(error) { /* transient network errors shouldn't spam toasts */ }
    }

    async function loadWarnings() {
        const rows=await requestJson("/api/warnings");
        document.getElementById("warnings-summary").textContent=`共 ${rows.length} 条待处理`;
        const readOnly=currentUser.role==="viewer";
        const table=document.getElementById("warnings-table");
        table.innerHTML=rows.length?`<table><thead><tr><th>时间</th><th>设备编号</th><th>变量</th><th>原值</th><th>新值</th><th></th></tr></thead><tbody>${rows.map(r=>`<tr class="warning-row" data-id="${r.id}"><td>${formatTime(r.data_time||r.detected_at)}</td><td>${escapeHtml(r.device_id)}</td><td>${escapeHtml(r.label)}</td><td>${showValue(r.previous_value)}</td><td class="changelog-new-value">${showValue(r.new_value)}</td><td>${readOnly?"":`<button class="secondary-button warning-clear-button" data-id="${r.id}" type="button">清除</button>`}</td></tr>`).join("")}</tbody></table>`:'<div class="empty">暂无预警</div>';

        table.querySelectorAll(".warning-row").forEach(row=>{
            row.addEventListener("click",event=>{
                if(event.target.closest(".warning-clear-button")) return;
                openChangelogDetail(row.dataset.id);
            });
        });
        table.querySelectorAll(".warning-clear-button").forEach(button=>{
            button.addEventListener("click",async event=>{
                event.stopPropagation();
                try {
                    await requestJson(`/api/warnings/${encodeURIComponent(button.dataset.id)}/clear`,{method:"POST"});
                    seenWarningIds.delete(Number(button.dataset.id));
                    await loadWarnings();
                    await pollWarnings();
                } catch(error){ alert(error.message); }
            });
        });
    }

    // Loads whichever tab is currently active inside the device detail view.
    async function loadActiveDetailTab() {
        if(!detailDeviceId) return;
        if(activeDetailTab==="realtime") await loadRealtime(detailDeviceId);
        if(activeDetailTab==="tech") await loadTech(detailDeviceId);
        if(activeDetailTab==="spc") await loadSpc(detailDeviceId);
        if(activeDetailTab==="changelog") await loadDeviceChangelog(detailDeviceId);
    }

    // options.tab: which detail tab to open on ("realtime" by default).
    // options.highlight: {parameter_id, previous_value, new_value} to flag
    // in the 工艺参数 tab -- set when arriving from a changelog entry, and
    // cleared automatically otherwise (e.g. clicking a device card).
    //
    // Data for the target tab is fetched and rendered BEFORE switchPage()
    // makes the device-detail section visible (see switchPage), so opening
    // a device never flashes an empty or stale (previous device's) panel
    // before the real content swaps in.
    async function openDeviceDetail(deviceId, options={}) {
        detailDeviceId=deviceId;
        activeDetailTab=options.tab||"realtime";
        techOpenCategories=new Set();
        highlightParameter=options.highlight||null;
        // Fresh page open -- reset so loadTech() will force-open the
        // highlighted category and scroll to it exactly once.
        highlightApplied=false;
        deviceChangelogFilters = { date: "", field: "", sub: "" };
        document.querySelectorAll(".tab-button").forEach(button=>button.classList.toggle("active",button.dataset.tab===activeDetailTab));
        document.querySelectorAll(".tab-content").forEach(content=>content.classList.toggle("hidden",content.id!==`detail-tab-${activeDetailTab}`));
        await switchPage("device-detail");
    }

    // Switching detail tabs: the newly-selected tab's data is fetched and
    // rendered first, while the previously-active tab stays visible on
    // screen, and only then do we flip which panel is shown. This avoids
    // revealing an empty/stale panel and then hard-swapping in the real
    // content a moment later (the stutter this replaces).
    async function switchDetailTab(tab) {
        document.querySelectorAll(".tab-button").forEach(button=>button.classList.toggle("active",button.dataset.tab===tab));
        const previousTab=activeDetailTab;
        const previousHighlight=highlightParameter;
        if(tab!=="tech") highlightParameter=null;
        activeDetailTab=tab;
        try {
            await loadActiveDetailTab();
        } catch(error) {
            activeDetailTab=previousTab;
            highlightParameter=previousHighlight;
            document.querySelectorAll(".tab-button").forEach(button=>button.classList.toggle("active",button.dataset.tab===previousTab));
            const status=document.getElementById("connection-status");
            status.className="connection error";
            status.textContent=`读取失败：${error.message}`;
            return;
        }
        document.querySelectorAll(".tab-content").forEach(content=>content.classList.toggle("hidden",content.id!==`detail-tab-${tab}`));
        document.getElementById("page-title").textContent=`设备 ${detailDeviceId} · ${detailTabTitles[tab]}`;
        scheduleAutoRefresh();
    }

    function switchUtilTab(tab) {
        activeUtilTab = tab;
        // Replays the grow-in animation every time this tab is re-entered
        // (see loadUtilizationOverview/Daily/Monthly, which call
        // playUtilEntranceAnimation() via element.animate() right after
        // rendering when utilRenderedOnce[tab] is false). The previous
        // render is deliberately left in place -- not cleared -- so the
        // bars/chart stay static and visible right up until the fresh data
        // arrives and replaces them. But that stale content must not be
        // visible in its old, fully-drawn state during the async fetch
        // that's about to happen -- collapse it now, synchronously, before
        // this container is unhidden below (see collapseUtilAnimatables).
        utilRenderedOnce[tab] = false;
        collapseUtilAnimatables(document.getElementById(`util-tab-${tab}`));
        document.querySelectorAll(".util-tab-button").forEach(button => button.classList.toggle("active", button.dataset.utilTab === tab));
        document.querySelectorAll("#utilization-page .tab-content").forEach(content => content.classList.toggle("hidden", content.id !== `util-tab-${tab}`));
        document.getElementById("page-title").textContent = `利用率报表 · ${utilTabTitles[tab]}`;
        refreshPage();
        scheduleAutoRefresh();
    }

    async function switchPage(page) {
        currentPage=page;
        document.getElementById("device-select").classList.toggle("hidden", page!=="molds" && page!=="utilization");
        if(page==="device-detail") {
            document.getElementById("page-title").textContent=`设备 ${detailDeviceId} · ${detailTabTitles[activeDetailTab]}`;
            document.getElementById("detail-device-title").textContent=`设备 ${detailDeviceId}`;
            // Load the active tab's data before this section is revealed
            // below, so entering the device detail view never flashes an
            // empty panel or stale content left over from a previously
            // viewed device/tab. Errors are surfaced via the normal
            // connection-status handling inside refreshPage() further down.
            try { await loadActiveDetailTab(); } catch(error) { /* handled by refreshPage below */ }
        } else if(page==="utilization") {
            activeUtilTab="overview";
            // See switchUtilTab -- same fix applies here: collapse the
            // stale overview content synchronously, before it's unhidden
            // below, so nothing flashes at its old full-drawn state while
            // the fresh data fetch is in flight.
            utilRenderedOnce.overview = false;
            collapseUtilAnimatables(document.getElementById("util-tab-overview"));
            document.querySelectorAll(".util-tab-button").forEach(button=>button.classList.toggle("active",button.dataset.utilTab==="overview"));
            document.querySelectorAll("#utilization-page .tab-content").forEach(content=>content.classList.toggle("hidden",content.id!=="util-tab-overview"));
            document.getElementById("page-title").textContent = `利用率报表 · ${utilTabTitles.overview}`;
        } else {
            document.getElementById("page-title").textContent=pageTitles[page];
        }
        document.querySelectorAll(".nav-item[data-page]").forEach(item=>item.classList.toggle("active",item.dataset.page===page));
        document.querySelectorAll("main > section").forEach(section=>section.classList.add("hidden"));
        const sectionId = page==="device-detail" ? "device-detail-page" : `${page}-page`;
        document.getElementById(sectionId).classList.remove("hidden");
        await refreshPage();
        scheduleAutoRefresh();
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
    document.getElementById("detail-back-button").addEventListener("click",()=>switchPage("dashboard"));
    document.querySelectorAll(".tab-button").forEach(button=>button.addEventListener("click",()=>switchDetailTab(button.dataset.tab)));
    document.getElementById("device-select").addEventListener("change",refreshPage);
    document.getElementById("search-button").addEventListener("click",()=>{dashboardPage=1;renderDashboard();});
    document.querySelectorAll(".status-filter").forEach(input=>input.addEventListener("change",()=>{dashboardPage=1;renderDashboard();}));
    document.getElementById("logout-button").addEventListener("click",async()=>{await fetch("/api/auth/logout",{method:"POST"});window.location.replace("/login");});
    document.getElementById("clear-all-warnings").addEventListener("click",async()=>{
        if(!confirm("确认清除全部预警？"))return;
        try {
            await requestJson("/api/warnings/clear-all",{method:"POST"});
            seenWarningIds.clear();
            await loadWarnings();
            await pollWarnings();
        } catch(error){ alert(error.message); }
    });
    document.getElementById("changelog-filter-date").addEventListener("change", async e => {
        changelogFilters.date = e.target.value;
        await loadChangelog();
    });
    document.getElementById("changelog-filter-field").addEventListener("change", async e => {
        changelogFilters.field = e.target.value;
        changelogFilters.sub = "";
        const tree = await loadChangelogFieldTree();
        const subSelect = document.getElementById("changelog-filter-sub");
        if (changelogFilters.field && tree[changelogFilters.field]) {
            subSelect.innerHTML = '<option value="">全部参数</option>' +
                Object.keys(tree[changelogFilters.field]).map(s => `<option value="${escapeHtml(s)}">${escapeHtml(s)}</option>`).join("");
            subSelect.disabled = false;
        } else {
            subSelect.innerHTML = '<option value="">全部参数</option>';
            subSelect.disabled = true;
        }
        await loadChangelog();
    });
    document.getElementById("changelog-filter-sub").addEventListener("change", async e => {
        changelogFilters.sub = e.target.value;
        await loadChangelog();
    });
    document.getElementById("changelog-filter-clear").addEventListener("click", async () => {
        changelogFilters = { date: "", field: "", sub: "" };
        document.getElementById("changelog-filter-date").value = "";
        document.getElementById("changelog-filter-field").value = "";
        const subSelect = document.getElementById("changelog-filter-sub");
        subSelect.innerHTML = '<option value="">全部参数</option>';
        subSelect.disabled = true;
        await loadChangelog();
    });
    document.querySelectorAll(".util-tab-button").forEach(button => button.addEventListener("click", () => switchUtilTab(button.dataset.utilTab)));
    document.getElementById("mold-form").addEventListener("submit",async event=>{event.preventDefault();const f=new FormData(event.target);try{await requestJson("/api/molds",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({mold_code:f.get("mold_code"),mold_name:f.get("mold_name"),product_code:f.get("product_code")||null,cavities:Number(f.get("cavities")),remark:f.get("remark")||null})});event.target.reset();event.target.cavities.value=1;await loadMolds();}catch(error){alert(error.message);}});
    document.getElementById("mount-button").addEventListener("click",async()=>{const moldId=Number(document.getElementById("mold-select").value);if(!moldId)return alert("请先选择模具");if(!confirm(`确认将所选模具安装到设备 ${selectedDeviceId()}？`))return;try{await requestJson(`/api/devices/${encodeURIComponent(selectedDeviceId())}/mold`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({mold_id:moldId,remark:null})});await loadMolds();}catch(error){alert(error.message);}});
    document.getElementById("unmount-button").addEventListener("click",async()=>{if(!confirm(`确认卸下设备 ${selectedDeviceId()} 当前模具？`))return;try{await requestJson(`/api/devices/${encodeURIComponent(selectedDeviceId())}/mold`,{method:"DELETE"});await loadMolds();}catch(error){alert(error.message);}});

    const passwordDialog=document.getElementById("password-dialog");
    document.getElementById("password-button").addEventListener("click",()=>passwordDialog.showModal());
    document.getElementById("password-cancel").addEventListener("click",()=>passwordDialog.close());
    document.getElementById("password-form").addEventListener("submit",async event=>{event.preventDefault();const f=new FormData(event.target);try{await requestJson("/api/auth/change-password",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({current_password:f.get("current_password"),new_password:f.get("new_password")})});event.target.reset();passwordDialog.close();alert("密码修改成功");}catch(error){alert(error.message);}});

    let isRefreshingPage = false;
    let pendingRefresh = false;
    async function refreshPage() {
        if (isRefreshingPage) { pendingRefresh = true; return; }
        isRefreshingPage = true;
        const status=document.getElementById("connection-status");
        try {
            if(currentPage==="dashboard")await loadDashboard();
            if(currentPage==="device-detail")await loadActiveDetailTab();
            if(currentPage==="molds")await loadMolds();
            if(currentPage==="changelog")await loadChangelog();
            if(currentPage==="warnings")await loadWarnings();
            if(currentPage==="utilization") await loadUtilization(activeUtilTab);
            status.className="connection";status.textContent=`更新于 ${new Date().toLocaleTimeString()}`;
        } catch(error){status.className="connection error";status.textContent=`读取失败：${error.message}`;}
        finally {
            isRefreshingPage = false;
            if (pendingRefresh) {
                pendingRefresh = false;
                refreshPage();
            }
        }
    }

    let autoRefreshTimer = null;
    function scheduleAutoRefresh() {
        if (autoRefreshTimer) clearTimeout(autoRefreshTimer);
        autoRefreshTimer = setTimeout(async () => {
            if (currentPage === "dashboard" || currentPage === "device-detail") {
                await refreshPage();
            }
            scheduleAutoRefresh();
        }, 2000);
    }

    async function initialize(){try{await loadSession();await loadDevices();await refreshPage();await pollWarnings();}catch(error){document.getElementById("connection-status").textContent=error.message;}}
    initialize();
    scheduleAutoRefresh();
    setInterval(pollWarnings,5000);