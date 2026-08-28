let currentPage = "dashboard";
    let currentUser = null;
    let devices = [];
    let dashboardMachines = [];
    let molds = [];
    let moldImageFiles = [];
    let moldFaceIndex = 0;
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
    let activeDetailUtilTab = "overview";
    const detailUtilRenderedOnce = { overview: false, daily: false, monthly: false };
    const utilTabTitles = { overview: "总览" };
    const pageTitles = { dashboard: "设备看板", molds: "模具管理", utilization: "利用率报表", changelog: "参数变更记录", warnings: "预警通知" };
    const detailTabTitles = { realtime: "实时参数", tech: "工艺参数", spc: "SPC 数据", changelog: "变更记录", uptime: "利用率" };
    let seenWarningIds = new Set();
    let warningsInitialized = false;
    let editMoldId = null;
    let editImageItems = [];
    let editFaceIndex = 0;
    const techCategoryUnits = {
        "温度参数": " ℃",
        "压力参数": " MPa",
        "速度参数": " mm/s",
        "位置参数": " mm",
        "时间参数": " s"
    };
    let moldAdvancedLoaded = false;
    let moldDefaultsLoaded = false;
    let currentMachineTypeId = null;
    let currentMachineTypeName = "";
    let machineTypesCache = [];
    let compareSelectedDevices = new Set();
    const COMPARE_COLORS = ["#6BAB90","#5b8def","#c98a3c","#5E4C5A","#c2555c","#8a6fdb","#FFD400"];
    const CHANGING_MOLDS_STALL_MS = 60000;
    const RECENT_PARAM_CHANGE_MS = 60000;
    const LOCAL_PARAM_STORAGE_PREFIX = "mes-local-param:";
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

    const deviceMachineImages = {
        "C02": "/static/img/haitianMars.png",
        "H2-T4": "/static/img/toshiba.png"
    };

    function machineImageForPrefix(deviceId) {
        if (typeof deviceId === "string" && deviceId.length >= 4 && deviceId[2] === "-") {
            const typeChar = deviceId[3];
            if (typeChar === "T") return "/static/img/toshiba.png";
            if (typeChar === "H") return "/static/img/haitianMars.png";
        }
        return "/static/img/haitianMars.png";
    }

    function machineVisual(deviceId) {
        const image = deviceMachineImages[deviceId] || machineImageForPrefix(deviceId);
        const extraClass = image.endsWith("/toshiba.png") ? " machine-photo-toshiba" : "";
        return `<img class="machine-photo${extraClass}" src="${image}" alt="${escapeHtml(deviceId)} 机台照片">`;
    }

    function cycleCell(r) {
        if (r.spc_cycle_number != null) return `模次 #${r.spc_cycle_number}`;
        if (r.during_production === false || r.during_production === 0) return '<span class="changelog-non-production">非生产变更</span>';
        return '<span class="muted">待关联</span>';
    }
    function escapeHtml(value) { return String(value ?? "").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;").replaceAll("'","&#039;"); }
    function showValue(value, suffix="") { return value === null || value === undefined || value === "" ? "--" : `${escapeHtml(value)}${suffix}`; }
    function formatTime(value) { return value ? String(value).replace("T"," ").replace(/\.\d+$/,"") : "--"; }
    function selectedDeviceId() { return document.getElementById("device-select").value; }
    function metric(label,value,suffix="",primary=false) { return `<div class="metric${primary?" primary":""}"><div class="metric-label">${escapeHtml(label)}</div><div class="metric-value">${showValue(value,suffix)}</div></div>`; }
    function machineGraphic() { return `<svg class="machine-svg" viewBox="0 0 190 54" aria-hidden="true"><rect x="4" y="18" width="48" height="26" rx="2" fill="#d7dde4" stroke="#9099a4"/><rect x="10" y="12" width="33" height="14" fill="#f4f6f8" stroke="#9099a4"/><rect x="55" y="25" width="67" height="19" fill="#cbd3dc" stroke="#89939e"/><path d="M60 24 L78 8 L104 8 L118 24" fill="#eef1f4" stroke="#89939e"/><rect x="124" y="18" width="58" height="26" fill="#dbe1e7" stroke="#89939e"/><rect x="135" y="10" width="34" height="13" fill="#f4f6f8" stroke="#89939e"/><circle cx="24" cy="48" r="4" fill="#59636f"/><circle cx="148" cy="48" r="4" fill="#59636f"/><circle cx="174" cy="48" r="4" fill="#59636f"/></svg>`; }

    function rebuildCavityTable(cavitiesInputId = "mold-cavities", tableId = "mold-cavity-table") {
        const cavities = Math.max(1, Number(document.getElementById(cavitiesInputId).value) || 1);
        const tbody = document.querySelector(`#${tableId} tbody`);
        const existing = {};
        tbody.querySelectorAll("tr").forEach(row => {
            const label = row.dataset.label;
            const tempInput = row.querySelector(".cavity-temp-input");
            if (label) {
                existing[label] = { temp: tempInput && tempInput.value !== "" ? tempInput.value : "" };
            }
        });
        const rows = [];
        for (let i = 1; i <= cavities; i++) rows.push(String(i));
        tbody.innerHTML = rows.map(label => `
            <tr data-label="${label}">
                <td>${label}</td>
                <td><input type="number" step="0.1" class="cavity-temp-input" value="${existing[label]?.temp ?? ""}"></td>
            </tr>`).join("");
    }

    function updateCleaningFieldsVisibility(checkboxId, intervalFieldId, durationFieldId) {
        const checked = document.getElementById(checkboxId).checked;
        document.getElementById(intervalFieldId).classList.toggle("hidden", !checked);
        document.getElementById(durationFieldId).classList.toggle("hidden", !checked);
    }
    document.getElementById("mold-requires-cleaning").addEventListener("change", () =>
        updateCleaningFieldsVisibility("mold-requires-cleaning", "mold-cleaning-interval-field", "mold-cleaning-duration-field")
    );
    updateCleaningFieldsVisibility("mold-requires-cleaning", "mold-cleaning-interval-field", "mold-cleaning-duration-field");

    document.getElementById("mold-edit-requires-cleaning").addEventListener("change", () =>
        updateCleaningFieldsVisibility("mold-edit-requires-cleaning", "mold-edit-cleaning-interval-field", "mold-edit-cleaning-duration-field")
    );

    document.getElementById("mold-cavities").addEventListener("input", () => rebuildCavityTable());
    rebuildCavityTable();
    document.getElementById("mold-edit-cavities").addEventListener("input", () => rebuildCavityTable("mold-edit-cavities", "mold-edit-cavity-table"));

    document.getElementById("mold-cavity-add-row").addEventListener("click", () => {
        const input = document.getElementById("mold-cavities");
        input.value = Math.max(1, Number(input.value) || 0) + 1;
        rebuildCavityTable();
    });
    document.getElementById("mold-cavity-remove-row").addEventListener("click", () => {
        const input = document.getElementById("mold-cavities");
        input.value = Math.max(1, (Number(input.value) || 1) - 1);
        rebuildCavityTable();
    });
    document.getElementById("mold-edit-cavity-add-row").addEventListener("click", () => {
        const input = document.getElementById("mold-edit-cavities");
        input.value = Math.max(1, Number(input.value) || 0) + 1;
        rebuildCavityTable("mold-edit-cavities", "mold-edit-cavity-table");
    });
    document.getElementById("mold-edit-cavity-remove-row").addEventListener("click", () => {
        const input = document.getElementById("mold-edit-cavities");
        input.value = Math.max(1, (Number(input.value) || 1) - 1);
        rebuildCavityTable("mold-edit-cavities", "mold-edit-cavity-table");
    });

    function collectCavityTemperatures(tableId = "mold-cavity-table") {
        const result = {};
        document.querySelectorAll(`#${tableId} tbody tr`).forEach(row => {
            const label = row.dataset.label;
            const tempValue = row.querySelector(".cavity-temp-input").value;
            result[label] = { temperature_c: tempValue === "" ? null : Number(tempValue), tolerance_pct: null };
        });
        return result;
    }

    function applyCavityTemperatures(tableId, temps) {
        const map = {};
        (temps || []).forEach(t => { map[t.cavity_label] = t; });
        document.querySelectorAll(`#${tableId} tbody tr`).forEach(row => {
            const tempInput = row.querySelector(".cavity-temp-input");
            const entry = map[row.dataset.label];
            tempInput.value = (entry && entry.temperature_c != null) ? entry.temperature_c : "";
        });
    }

    function renderMoldImagePreviews() {
        const container = document.getElementById("mold-image-previews");
        container.innerHTML = moldImageFiles.map((file, i) => {
            const url = URL.createObjectURL(file);
            return `<div class="mold-image-preview${i===moldFaceIndex?" is-face":""}" data-index="${i}">
                <button type="button" class="mold-image-expand" data-url="${url}" aria-label="放大查看">⤢</button>
                <img src="${url}" alt="预览">
                <label class="face-select"><input type="radio" name="face-image" ${i===moldFaceIndex?"checked":""} value="${i}"> 封面</label>
                <button type="button" class="mold-image-remove" data-index="${i}">✕</button>
            </div>`;
        }).join("");
        container.querySelectorAll('input[name="face-image"]').forEach(radio => {
            radio.addEventListener("change", e => { moldFaceIndex = Number(e.target.value); renderMoldImagePreviews(); });
        });
        container.querySelectorAll(".mold-image-expand").forEach(button => {
            button.addEventListener("click", () => openImageLightbox(button.dataset.url));
        });
        container.querySelectorAll(".mold-image-remove").forEach(button => {
            button.addEventListener("click", () => {
                const idx = Number(button.dataset.index);
                moldImageFiles.splice(idx, 1);
                if (moldFaceIndex >= moldImageFiles.length) moldFaceIndex = 0;
                renderMoldImagePreviews();
            });
        });
    }

    function renderEditImagePreviews() {
        const container = document.getElementById("mold-edit-image-previews");
        container.innerHTML = editImageItems.map((item, i) => {
            const url = item.type === "existing" ? item.url : URL.createObjectURL(item.file);
            return `<div class="mold-image-preview${i===editFaceIndex?" is-face":""}" data-index="${i}">
                <button type="button" class="mold-image-expand" data-url="${url}" aria-label="放大查看">⤢</button>
                <img src="${url}" alt="预览">
                <label class="face-select"><input type="radio" name="edit-face-image" ${i===editFaceIndex?"checked":""} value="${i}"> 封面</label>
                <button type="button" class="mold-image-remove" data-index="${i}">✕</button>
            </div>`;
        }).join("");
        container.querySelectorAll('input[name="edit-face-image"]').forEach(radio => {
            radio.addEventListener("change", e => { editFaceIndex = Number(e.target.value); renderEditImagePreviews(); });
        });
        container.querySelectorAll(".mold-image-expand").forEach(button => {
            button.addEventListener("click", () => openImageLightbox(button.dataset.url));
        });
        container.querySelectorAll(".mold-image-remove").forEach(button => {
            button.addEventListener("click", () => {
                const idx = Number(button.dataset.index);
                editImageItems.splice(idx, 1);
                if (editFaceIndex >= editImageItems.length) editFaceIndex = 0;
                renderEditImagePreviews();
            });
        });
    }

    // Shared "expand" handler for the mold-image previews in both the
    // create form and edit dialog -- opens a real popup window (the
    // width/height/popup features below are what tell the browser to use
    // a separate chrome-less window instead of a new tab) containing just
    // the image, sized with object-fit:contain so it keeps rescaling to
    // fill the window as the person resizes it.
    function openImageLightbox(url) {
        const popup = window.open("", "_blank", "popup,width=900,height=700,resizable=yes,scrollbars=no");
        if (!popup) return; // popup blocked by the browser
        const doc = popup.document;
        doc.title = "图片预览";
        doc.body.style.cssText = "margin:0;height:100vh;background:#11151b;display:flex;align-items:center;justify-content:center;overflow:hidden;";
        const img = doc.createElement("img");
        img.src = url;
        img.alt = "图片预览";
        img.style.cssText = "width:100%;height:100%;object-fit:contain;";
        doc.body.appendChild(img);
    }

    document.getElementById("mold-edit-images-input").addEventListener("change", e => {
        const incoming = Array.from(e.target.files || []).map(file => ({ type: "new", file }));
        editImageItems = [...editImageItems, ...incoming];
        if (editFaceIndex >= editImageItems.length) editFaceIndex = 0;
        renderEditImagePreviews();
        e.target.value = "";
    });

    async function loadMoldOutputStats(moldId) {
        const el = document.getElementById("mold-edit-output-stats");
        if (!el) return;
        el.textContent = "正在读取产量……";
        try {
            const stats = await requestJson(`/api/molds/${encodeURIComponent(moldId)}/output`);
            const overLimit = stats.max_output != null && stats.total_output > stats.max_output;
            el.innerHTML = `
                <div class="metric-grid">
                    ${metric("今日产量", stats.today_output, " 模")}
                    ${metric("本周产量", stats.week_output, " 模")}
                    <div class="metric${overLimit ? "" : " primary"}">
                        <div class="metric-label">累计产量${stats.max_output != null ? ` / 上限 ${stats.max_output}` : ""}</div>
                        <div class="metric-value"${overLimit ? ' style="color:var(--red)"' : ""}>${showValue(stats.total_output," 模")}</div>
                    </div>
                </div>`;
        } catch (error) {
            el.innerHTML = `<div class="empty">读取失败：${escapeHtml(error.message)}</div>`;
        }
    }

    function openMoldEdit(moldId) {
        const m = molds.find(x => x.id === moldId);
        if (!m) return;
        editMoldId = moldId;
        document.getElementById("edit-mold-name").value = m.mold_name;
        document.getElementById("edit-mold-code").value = m.mold_code;
        document.getElementById("mold-edit-cavities").value = m.cavities;
        document.getElementById("edit-mold-remark").value = m.remark || "";
        document.getElementById("edit-mold-active").value = m.is_active ? "1" : "0";
        document.getElementById("mold-edit-requires-cleaning").checked = !!m.requires_cleaning;
        document.getElementById("mold-edit-cleaning-interval").value = m.cleaning_interval_hours ?? "";
        document.getElementById("mold-edit-cleaning-duration").value = m.cleaning_duration_minutes ?? "";
        updateCleaningFieldsVisibility("mold-edit-requires-cleaning", "mold-edit-cleaning-interval-field", "mold-edit-cleaning-duration-field");
        document.getElementById("mold-edit-current-device").textContent = m.mounted_device_id ? `当前装机设备：${m.mounted_device_id}` : "当前未装机";
        const maxOutputInput = document.getElementById("mold-edit-max-output");
        if (maxOutputInput) maxOutputInput.value = m.max_output ?? "";
        loadMoldOutputStats(moldId);

        editImageItems = (m.images || []).map(img => ({ type: "existing", id: img.id, url: img.url, is_face: img.is_face }));
        editFaceIndex = Math.max(0, editImageItems.findIndex(item => item.is_face));
        renderEditImagePreviews();

        rebuildCavityTable("mold-edit-cavities", "mold-edit-cavity-table");
        applyCavityTemperatures("mold-edit-cavity-table", m.cavity_temperatures);

        const readOnly = currentUser.role === "viewer";
        document.getElementById("mold-edit-form").querySelectorAll("input,textarea,select,button").forEach(el => el.disabled = readOnly);
        document.getElementById("mold-edit-reset-output-button").disabled = readOnly;

        moldAdvancedLoaded = false;
        moldExtendedFields = {};
        currentMachineTypeId = null;
        currentMachineTypeName = "";
        document.getElementById("mold-advanced-dialog").close();
        document.getElementById("mold-machine-types-dialog").close();
        document.getElementById("mold-advanced-groups").innerHTML = "";
        document.getElementById("mold-advanced-summary").textContent = "";

        document.getElementById("mold-edit-dialog").showModal();
    }

    document.getElementById("mold-edit-cancel").addEventListener("click", () => {
        document.getElementById("mold-advanced-dialog").close();
        document.getElementById("mold-machine-types-dialog").close();
        document.getElementById("mold-edit-dialog").close();
    });
    document.getElementById("mold-edit-delete-button").addEventListener("click", async () => {
        if (!confirm("确认永久删除该模具？该模具的装卸记录和高级参数也会一并删除，此操作不可恢复。")) return;
        try {
            await requestJson(`/api/molds/${editMoldId}`, { method: "DELETE" });
            document.getElementById("mold-advanced-dialog").close();
            document.getElementById("mold-edit-dialog").close();
            await loadMolds();
        } catch (error) { alert(error.message); }
    });
    document.getElementById("mold-edit-reset-output-button").addEventListener("click", async () => {
        if (!confirm("确认重置该模具的产量统计（今日/本周/累计）？如该模具当前已装机，对应设备的模次显示也会一并重置，此操作不可撤销。")) return;
        try {
            await requestJson(`/api/molds/${editMoldId}/output/reset`, { method: "POST" });
            await loadMoldOutputStats(editMoldId);
            await loadMolds();
        } catch (error) { alert(error.message); }
    });
    document.getElementById("device-mold-change-button").addEventListener("click", async () => {
        try { await openMoldAssignDialog(); } catch (error) { alert(error.message); }
    });
    document.getElementById("mold-assign-cancel").addEventListener("click", () => document.getElementById("mold-assign-dialog").close());
    document.getElementById("mold-assign-close-x").addEventListener("click", () => {
        document.getElementById("mold-assign-dialog").close();
    });
    document.getElementById("mold-assign-select").addEventListener("change", e => {
        const moldId = Number(e.target.value);
        if (moldId) populateAssignMachineTypeSelect(moldId, null);
    });

    document.getElementById("mold-assign-confirm").addEventListener("click", async () => {
        const moldId = document.getElementById("mold-assign-select").value;
        const machineTypeId = document.getElementById("mold-assign-machine-type-select").value;
        if (!moldId) return;
        if (!machineTypeId) { alert("请选择机型"); return; }
        try {
            const result = await requestJsonWithMismatch(`/api/devices/${encodeURIComponent(detailDeviceId)}/mold`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    mold_id: Number(moldId),
                    machine_type_id: Number(machineTypeId),
                    remark: document.getElementById("mold-assign-remark").value || null,
                }),
            });
            if (result === null) return;
            document.getElementById("mold-assign-dialog").close();
            await loadDeviceMoldCard(detailDeviceId);
            await loadDevices();
        } catch (error) { alert(error.message); }
    });

    document.getElementById("device-mold-info").addEventListener("click", async event => {
        if (!event.target.closest("#device-machine-type-apply")) return;
        const select = document.getElementById("device-machine-type-select");
        const machineTypeId = select ? select.value : "";
        const moldId = select ? select.dataset.moldId : "";
        if (!machineTypeId) { alert("请选择机型"); return; }
        try {
            const result = await requestJsonWithMismatch(`/api/devices/${encodeURIComponent(detailDeviceId)}/machine-type`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    mold_id: Number(moldId),
                    machine_type_id: Number(machineTypeId),
                }),
            });
            if (result === null) return;
            alert("机型已切换，后续预警将按新机型的规格判断");
        } catch (error) { alert(error.message); }
    });
    
    document.getElementById("device-mold-unmount-button").addEventListener("click", async () => {
        if (!confirm("确认卸载当前模具？")) return;
        try {
            await requestJson(`/api/devices/${encodeURIComponent(detailDeviceId)}/mold`, { method: "DELETE" });
            await loadDeviceMoldCard(detailDeviceId);
            await loadDevices();
        } catch (error) { alert(error.message); }
    });

    document.getElementById("device-delete-button").addEventListener("click", async () => {
        if (!confirm(
            `确认永久删除设备 ${detailDeviceId}？\n\n` +
            "该设备的全部历史数据（实时数据、工艺参数、变更记录、模具装卸记录）将被永久删除，此操作不可恢复。"
        )) return;
        try {
            await requestJson(`/api/devices/${encodeURIComponent(detailDeviceId)}`, { method: "DELETE" });
            await loadDevices();
            await switchPage("dashboard");
        } catch (error) {
            alert(error.message);
        }
    });

    document.getElementById("mold-edit-close-x").addEventListener("click", () => {
        document.getElementById("mold-advanced-dialog").close();
        document.getElementById("mold-machine-types-dialog").close();
        document.getElementById("mold-edit-dialog").close();
    });

    document.getElementById("mold-edit-form").addEventListener("submit", async event => {
        event.preventDefault();
        if (editImageItems.length < 1) return alert("请至少保留一张项目图片");

        const body = new FormData();
        body.set("mold_code", document.getElementById("edit-mold-code").value);
        body.set("product_code", document.getElementById("edit-mold-product-code").value || "");
        body.set("mold_name", document.getElementById("edit-mold-name").value);
        body.set("cavities", document.getElementById("mold-edit-cavities").value);
        body.set("remark", document.getElementById("edit-mold-remark").value || "");
        body.set("is_active", document.getElementById("edit-mold-active").value);
        body.set("cavity_temperatures", JSON.stringify(collectCavityTemperatures("mold-edit-cavity-table")));

        const keepIds = editImageItems.filter(i => i.type === "existing").map(i => i.id);
        body.set("keep_image_ids", JSON.stringify(keepIds));

        const faceItem = editImageItems[editFaceIndex];
        if (faceItem.type === "existing") {
            body.set("face_image_id", String(faceItem.id));
        } else {
            const newOnly = editImageItems.filter(i => i.type === "new");
            body.set("face_new_index", String(newOnly.indexOf(faceItem)));
        }
        body.set("requires_cleaning", document.getElementById("mold-edit-requires-cleaning").checked ? "1" : "0");
        body.set("cleaning_interval_hours", document.getElementById("mold-edit-cleaning-interval").value || "");
        body.set("cleaning_duration_minutes", document.getElementById("mold-edit-cleaning-duration").value || "");
        body.set("max_output", document.getElementById("mold-edit-max-output")?.value || "");
        editImageItems.filter(i => i.type === "new").forEach(i => body.append("images", i.file));

        try {
            await requestJson(`/api/molds/${editMoldId}`, { method: "PUT", body });
            document.getElementById("mold-edit-dialog").close();
            document.getElementById("mold-advanced-dialog").close();
            await loadMolds();
            await loadMolds();
        } catch (error) { alert(error.message); }
    });


    document.getElementById("mold-images-input").addEventListener("change", e => {
        const incoming = Array.from(e.target.files || []);
        moldImageFiles = [...moldImageFiles, ...incoming];
        if (moldFaceIndex >= moldImageFiles.length) moldFaceIndex = 0;
        renderMoldImagePreviews();
        e.target.value = "";
    });

    async function loadMolds() {
        molds = await requestJson("/api/molds");
        renderMoldList();
    }

    // Static face-image markup for a mold card -- only ever built once per
    // card. Kept separate from the badge/overlay builders below so a
    // refresh never has to touch (and therefore never has to re-decode)
    // the <img> itself.
    function moldItemFaceHtml(m) {
        return m.face_image_url
            ? `<img class="mold-card-face" src="${escapeHtml(m.face_image_url)}" alt="${escapeHtml(m.mold_name)}">`
            : `<div class="mold-card-face-empty">暂无图片</div>`;
    }
    function moldItemDeviceBadgeHtml(m) {
        return m.mounted_device_id
            ? `<div class="mold-card-device">设备 ${escapeHtml(m.mounted_device_id)}</div>`
            : `<div class="mold-card-device mold-card-device-empty">未装机</div>`;
    }
    function moldItemOverlayHtml(m) {
        return `<div class="mold-card-overlay">
            <div class="mold-card-title">${escapeHtml(m.mold_code)} · ${escapeHtml(m.mold_name)}</div>
            <div class="mold-card-meta">模穴：${showValue(m.cavities)}${m.requires_cleaning ? `　清洁每 ${showValue(m.cleaning_interval_hours)}h` : ""}　产量：${showValue(m.total_output)}${m.max_output != null ? `/${m.max_output}` : ""}</div>
        </div>`;
    }
    function moldItemHtml(m) {
        return `<div class="mold-item" data-mold-id="${m.id}">
            ${moldItemFaceHtml(m)}
            ${moldItemDeviceBadgeHtml(m)}
            ${moldItemOverlayHtml(m)}
        </div>`;
    }

    function renderMoldList() {
        const term = (document.getElementById("mold-search-input")?.value || "").trim().toLowerCase();
        const filtered = term
            ? molds.filter(m =>
                (m.mold_name || "").toLowerCase().includes(term) ||
                (m.mold_code || "").toLowerCase().includes(term))
            : molds;

        const container = document.getElementById("mold-list");

        if (!filtered.length) {
            container.innerHTML = `<div class="empty">${term ? "未找到匹配的模具" : "尚未建立模具档案"}</div>`;
            return;
        }

        const existingItems = [...container.querySelectorAll(".mold-item")];
        const existingIds = existingItems.map(item => Number(item.dataset.moldId));
        const currentIds = filtered.map(m => m.id);
        const sameLayout = existingIds.length === currentIds.length && existingIds.every((id, i) => id === currentIds[i]);

        if (sameLayout) {
            // Same set of molds, same order (the common case on the 2s
            // auto-refresh) -- patch the device badge and overlay text in
            // place, and only touch the face <img> if its URL actually
            // changed, instead of rebuilding every card from scratch
            // (which is what made the images flash on every refresh).
            filtered.forEach((m, i) => {
                const item = existingItems[i];

                const badgeEl = item.querySelector(".mold-card-device");
                if (badgeEl) badgeEl.outerHTML = moldItemDeviceBadgeHtml(m);

                const overlayEl = item.querySelector(".mold-card-overlay");
                if (overlayEl) overlayEl.outerHTML = moldItemOverlayHtml(m);

                const imgEl = item.querySelector(".mold-card-face");
                const emptyEl = item.querySelector(".mold-card-face-empty");
                if (m.face_image_url) {
                    if (imgEl) {
                        if (imgEl.getAttribute("src") !== m.face_image_url) imgEl.setAttribute("src", m.face_image_url);
                    } else if (emptyEl) {
                        emptyEl.outerHTML = `<img class="mold-card-face" src="${escapeHtml(m.face_image_url)}" alt="${escapeHtml(m.mold_name)}">`;
                    }
                } else if (imgEl) {
                    imgEl.outerHTML = `<div class="mold-card-face-empty">暂无图片</div>`;
                }
            });
            return;
        }

        container.innerHTML = filtered.map(moldItemHtml).join("");
        container.querySelectorAll(".mold-item").forEach(item => item.addEventListener("click", () => {
            openMoldEdit(Number(item.dataset.moldId));
        }));
    }

    async function loadDeviceMoldCard(id) {
        const container = document.getElementById("device-mold-info");
        container.innerHTML = '<div class="empty">正在读取……</div>';
        try {
            const current = await requestJson(`/api/devices/${encodeURIComponent(id)}/mold`);
            renderDeviceMoldCard(current);
            if (current) {
                requestJson(`/api/molds/${encodeURIComponent(current.mold_id)}/output`)
                    .then(renderDeviceMoldOutput)
                    .catch(() => {});
            }
        } catch (error) {
            container.innerHTML = `<div class="empty">读取失败：${escapeHtml(error.message)}</div>`;
        }
    }

    function renderDeviceMoldCard(current) {
        const container = document.getElementById("device-mold-info");
        const unmountButton = document.getElementById("device-mold-unmount-button");
        if (current) {
            container.innerHTML = `
                <div class="mold-current">
                    <div class="muted">产品编号</div>
                    <div class="mold-code">${escapeHtml(current.mold_code)}</div>
                    <div>${escapeHtml(current.mold_name)}</div>
                    <div class="muted">模穴：${showValue(current.cavities)}</div>${current.requires_cleaning ? `<div class="muted">清洗周期：每 ${showValue(current.cleaning_interval_hours)} 小时 · 约 ${showValue(current.cleaning_duration_minutes)} 分钟</div>` : ""}
                    <div class="device-machine-type-row" style="display:flex;align-items:center;gap:8px;margin-top:10px;">
                        <span class="muted" style="flex:0 0 auto;">机型（决定预警规格）</span>
                        <select id="device-machine-type-select" style="flex:1 1 auto;min-width:0;"></select>
                        <button id="device-machine-type-apply" class="secondary-button" type="button">应用</button>
                    </div>
                </div>
                <div class="metric-grid" id="device-mold-output" style="margin-top:10px;"></div>`;
            unmountButton.classList.remove("hidden");
            populateDeviceMachineTypeSelect(current.mold_id, current.machine_type_id);
        } else {
            container.innerHTML = '<div class="empty">该设备当前未分配模具</div>';
            unmountButton.classList.add("hidden");
        }
    }

    // Machine-type dropdowns share this: load the machine types configured
    // for a mold (same endpoint the 模具管理 -> 机型 list uses).
    async function loadMachineTypesFor(moldId) {
        const result = await requestJson(`/api/molds/${encodeURIComponent(moldId)}/machine-types`);
        return result.machine_types || [];
    }

    // Populates the quick-switch select inside the 当前模具 card for
    // whichever mold is currently mounted, preselecting the device's
    // actual current machine type.
    async function populateDeviceMachineTypeSelect(moldId, currentMachineTypeId) {
        const select = document.getElementById("device-machine-type-select");
        const applyButton = document.getElementById("device-machine-type-apply");
        if (!select) return;
        select.dataset.moldId = moldId;
        select.innerHTML = '<option value="">正在读取……</option>';
        try {
            const types = await loadMachineTypesFor(moldId);
            select.innerHTML = types.length
                ? types.map(mt => `<option value="${mt.id}"${mt.id === currentMachineTypeId ? " selected" : ""}>${escapeHtml(mt.machine_type)}${mt.is_main ? "（主要）" : ""}</option>`).join("")
                : '<option value="">该模具尚未配置机型</option>';
        } catch (error) {
            select.innerHTML = `<option value="">读取失败：${escapeHtml(error.message)}</option>`;
        }
        const readOnly = currentUser.role === "viewer";
        select.disabled = readOnly;
        if (applyButton) applyButton.disabled = readOnly;
    }

    // Populates the machine-type select inside the 分配模具 dialog for
    // whichever mold is currently chosen there. preferredId (if it
    // belongs to this mold) is preselected; otherwise the main machine
    // type (or the first one) is used.
    async function populateAssignMachineTypeSelect(moldId, preferredId) {
        const select = document.getElementById("mold-assign-machine-type-select");
        select.innerHTML = '<option value="">正在读取机型……</option>';
        try {
            const types = await loadMachineTypesFor(moldId);
            if (!types.length) {
                select.innerHTML = '<option value="">该模具尚未配置机型</option>';
                return;
            }
            select.innerHTML = types.map(mt =>
                `<option value="${mt.id}">${escapeHtml(mt.machine_type)}${mt.is_main ? "（主要）" : ""}</option>`
            ).join("");
            const toSelect = (preferredId != null && types.some(mt => mt.id === preferredId))
                ? preferredId
                : (types.find(mt => mt.is_main) || types[0]).id;
            select.value = String(toSelect);
        } catch (error) {
            select.innerHTML = `<option value="">读取失败：${escapeHtml(error.message)}</option>`;
        }
    }

    function renderDeviceMoldOutput(stats) {
        const el = document.getElementById("device-mold-output");
        if (!el) return;
        const overLimit = stats.max_output != null && stats.total_output > stats.max_output;
        el.innerHTML = `
            ${metric("今日产量", stats.today_output, " 模")}
            ${metric("本周产量", stats.week_output, " 模")}
            <div class="metric${overLimit ? "" : " primary"}">
                <div class="metric-label">累计产量${stats.max_output != null ? ` / 上限 ${stats.max_output}` : ""}</div>
                <div class="metric-value"${overLimit ? ' style="color:var(--red)"' : ""}>${showValue(stats.total_output," 模")}</div>
            </div>`;
    }

    async function openMoldAssignDialog() {
        const list = await requestJson("/api/molds");
        const active = list.filter(m => m.is_active);
        const select = document.getElementById("mold-assign-select");
        select.innerHTML = active.map(m => {
            const elsewhere = m.mounted_device_id && m.mounted_device_id !== detailDeviceId
                ? `（当前在设备 ${escapeHtml(m.mounted_device_id)}，将自动转移）`
                : "";
            return `<option value="${m.id}">${escapeHtml(m.mold_code)} · ${escapeHtml(m.mold_name)}${elsewhere}</option>`;
        }).join("");
        document.getElementById("mold-assign-remark").value = "";

        // Default to whatever's currently mounted on this device (mold +
        // machine type), so re-opening the dialog just to switch machine
        // type doesn't also force picking the mold again.
        let currentMoldId = null;
        let currentMachineTypeId = null;
        try {
            const current = await requestJson(`/api/devices/${encodeURIComponent(detailDeviceId)}/mold`);
            if (current && active.some(m => m.id === current.mold_id)) {
                currentMoldId = current.mold_id;
                currentMachineTypeId = current.machine_type_id;
            }
        } catch (error) { /* no current assignment -- fall back to first mold in list */ }

        if (currentMoldId != null) select.value = String(currentMoldId);
        if (select.value) await populateAssignMachineTypeSelect(Number(select.value), currentMachineTypeId);

        document.getElementById("mold-assign-dialog").showModal();
    }

    document.getElementById("mold-form").addEventListener("submit", async event => {
        event.preventDefault();
        if (moldImageFiles.length < 1) return alert("请至少上传一张项目图片");
        const f = new FormData(event.target);
        const body = new FormData();
        body.set("mold_code", f.get("mold_code"));
        body.set("mold_name", f.get("mold_name"));
        body.set("product_code", f.get("product_code") || "");
        body.set("cavities", f.get("cavities"));
        body.set("remark", f.get("remark") || "");
        body.set("cavity_temperatures", JSON.stringify(collectCavityTemperatures()));
        body.set("face_index", String(moldFaceIndex));
        body.set("requires_cleaning", document.getElementById("mold-requires-cleaning").checked ? "1" : "0");
        body.set("cleaning_interval_hours", document.getElementById("mold-cleaning-interval").value || "");
        body.set("cleaning_duration_minutes", document.getElementById("mold-cleaning-duration").value || "");
        body.set("max_output", document.getElementById("mold-max-output")?.value || "");
        moldImageFiles.forEach(file => body.append("images", file));
        try {
            await requestJson("/api/molds", { method: "POST", body });
            event.target.reset();
            document.getElementById("mold-requires-cleaning").checked = false;
            document.getElementById("mold-cleaning-interval").value = "";
            document.getElementById("mold-cleaning-duration").value = "";
            updateCleaningFieldsVisibility("mold-requires-cleaning", "mold-cleaning-interval-field", "mold-cleaning-duration-field");
            moldImageFiles = [];
            moldFaceIndex = 0;
            renderMoldImagePreviews();
            rebuildCavityTable();
            await loadMolds();
        } catch (error) { alert(error.message); }
    });

    function collectParameterRows(containerId) {
        return [...document.querySelectorAll(`#${containerId} .mold-param-row, #${containerId} .excel-param-cell`)].map(row => {
            const valueInput = row.querySelector(".mold-param-value");
            const value = valueInput ? valueInput.value.trim() : "";
            const mode = row.querySelector(".mold-param-tolerance-mode").value;
            const toleranceRaw = row.querySelector(".mold-param-tolerance").value.trim();
            const toleranceNum = toleranceRaw === "" ? null : Number(toleranceRaw);
            return {
                parameter_id: row.dataset.parameter,
                value: value || null,
                tolerance_mode: mode,
                tolerance_percent: mode === "percent" ? toleranceNum : null,
                tolerance_flat: mode === "flat" ? toleranceNum : null,
            };
        });
    }
    // ---- 工艺参数 grid blocks ------------------------------------------
    // Single source of truth for BOTH the 设备看板 -> 工艺参数 tab (read-only
    // live readings, rendered via techBlockTableHtml/techParamCell) and
    // 模具管理 -> 高级工艺参数 / 默认参数设置 (editable target value + tolerance,
    // rendered via excelBlockTableHtml/excelParamCell). Keeping one array
    // means the two pages can never drift apart in which parameters/rows/
    // columns they show -- a tag added here shows up identically in both
    // places. Titles that already carried a default-tolerance hint (the
    // original 7 blocks, e.g. "±10%") keep that hint; newly-merged blocks
    // use a plain title since there's no established default tolerance
    // convention for them yet.
    //
    // A few tags are categorical/counter values rather than settable
    // specs (see NON_EDITABLE_TAGS below, mirroring the backend's
    // EXCLUDED_FROM_TARGETS in parameter_labels.py) -- those still show up
    // here so their live reading is visible in 工艺参数, but excelParamCell
    // renders them as a plain "不适用" cell instead of an editable
    // value/tolerance input, since the backend silently drops any target/
    // tolerance saved against them.
    const PARAMETER_GRID_BLOCKS = [
        {
            title: "温度设定 ±10℃",
            colLabels: ["射嘴", "1段", "2段", "3段", "4段", "5段", "6段", "7段"],
            rows: [{ label: "温度", tags: ["local:nozzle_temp", "TS1", "TS2", "TS3", "TS4", "TS5", "TS6", "TS7"] }],
        },
        {
            title: "射胶设定 ±10%",
            colLabels: ["1段", "2段", "3段", "4段", "5段", "6段"],
            rows: [
                { label: "速度", tags: ["IV1", "IV2", "IV3", "IV4", "IV5", "IV6"] },
                { label: "压力", tags: ["IP1", "IP2", "IP3", "IP4", "IP5", "IP6"] },
                { label: "位置", tags: ["IS1", "IS2", "IS3", "IS4", "IS5", null] },
            ],
        },
        {
            title: "保压设定 ±10%",
            colLabels: ["1段", "2段", "3段", "4段", "5段", "6段"],
            rows: [
                { label: "速度", tags: ["PV1", "PV2", "PV3", "PV4", "PV5", "PV6"] },
                { label: "压力", tags: ["PP1", "PP2", "PP3", "PP4", "PP5", "PP6"] },
                { label: "时间(S)", tags: ["PT1", "PT2", "PT3", "PT4", "PT5", "PT6"] },
            ],
        },
        {
            title: "储料设定 ±10%",
            colLabels: ["1段", "2段", "3段", "抽胶", "背压", "螺杆位置"],
            rows: [
                { label: "速度", tags: ["PLV1", "PLV2", "PLV3", "PLV4", null, null] },
                { label: "压力", tags: ["PLP1", "PLP2", "PLP3", "PLP4", "PLBP1", "PLS5"] },
                { label: "位置", tags: ["PLS1", "PLS2", "PLS3", "PLS4", null, null] },
            ],
        },
        {
            title: "锁模设定 ±10%",
            colLabels: ["1段", "2段", "3段", "4段", "高压"],
            rows: [
                { label: "速度", tags: ["MCV1", "MCV2", "MCV3", "MCV4", "MCV5"] },
                { label: "压力", tags: ["MCP1", "MCP2", "MCP3", "MCP4", "MCP5"] },
                { label: "位置", tags: ["MCS1", "MCS2", "MCS3", "MCS4", "MCS5"] },
            ],
        },
        {
            title: "开模设定 ±10%",
            colLabels: ["1段", "2段", "3段", "4段", "终止"],
            rows: [
                { label: "速度", tags: ["MOV1", "MOV2", "MOV3", "MOV4", "MOV5"] },
                { label: "压力", tags: ["MOP1", "MOP2", "MOP3", "MOP4", "MOP5"] },
                { label: "位置", tags: ["MOS1", "MOS2", "MOS3", "MOS4", "MOS5"] },
            ],
        },
        {
            title: "顶针设定 ±10%",
            colLabels: ["顶进1", "顶进2", "顶进3", "顶退1", "顶退2"],
            rows: [
                { label: "速度", tags: ["EFV1", "EFV2", "EFV3", "EBV1", "EBV2"] },
                { label: "压力", tags: ["EFP1", "EFP2", null, "EBP1", "EBP2"] },
                { label: "位置", tags: ["EFS1", "EFS2", "EFS3", "EBS1", "EBS2"] },
                { label: "时间(S)", tags: ["EFDT", null, null, "EBDT", null] },
            ],
        },
        {
            title: "顶针次数",
            colLabels: ["数值"],
            rows: [
                { label: "顶针次数", tags: ["EJET"] },
                { label: "顶针模式", tags: ["EJEM"] },
            ],
        },
        {
            title: "吹气设定",
            colLabels: ["A组", "B组"],
            rows: [
                { label: "动作时间", tags: ["BLT1", "BLT2"] },
                { label: "延迟时间", tags: ["BLDT1", "BLDT2"] },
                { label: "起始位置", tags: ["BLS1", "BLS2"] },
            ],
        },
        {
            title: "中子设定",
            colLabels: ["中子1", "中子2", "中子3", "中子4"],
            rows: [
                { label: "模式", tags: ["CP1M", "CP2M", "CP3M", "CP4M"] },
                { label: "进位置", tags: ["CPI1S", "CPI2S", "CPI3S", "CPI4S"] },
                { label: "进压力", tags: ["CPI1P", "CPI2P", "CPI3P", "CPI4P"] },
                { label: "进速度", tags: ["CPI1V", "CPI2V", "CPI3V", "CPI4V"] },
                { label: "进时间", tags: ["CPI1T", "CPI2T", "CPI3T", "CPI4T"] },
                { label: "退位置", tags: ["CPO1S", "CPO2S", "CPO3S", "CPO4S"] },
                { label: "退压力", tags: ["CPO1P", "CPO2P", "CPO3P", "CPO4P"] },
                { label: "退速度", tags: ["CPO1V", "CPO2V", "CPO3V", "CPO4V"] },
                { label: "退时间", tags: ["CPO1T", "CPO2T", "CPO3T", "CPO4T"] },
            ],
        },
        {
            title: "座进座退设定",
            colLabels: ["座进1", "座进2", "座退"],
            rows: [
                { label: "压力", tags: ["CFP1", "CFP2", "CBP1"] },
                { label: "速度", tags: ["CFV1", "CFV2", "CBV1"] },
                { label: "位置", tags: ["CFS1", "CFS2", "CBS1"] },
                { label: "时间(S)", tags: ["CFT1", null, "CBT1"] },
                { label: "延迟时间", tags: [null, null, "CBDT1"] },
            ],
        },
        {
            title: "冷却 / 切保压设定",
            colLabels: ["数值"],
            rows: [
                { label: "储前冷却", tags: ["CTBFPL"] },
                { label: "冷却时间", tags: ["CT"] },
                { label: "切保压模式", tags: ["SIPM"] },
                { label: "切保压时间", tags: ["SIPT"] },
                { label: "切保压压力", tags: ["SIPP"] },
                { label: "切保压位置", tags: ["SIPS"] },
            ],
        },
        {
            title: "生产温度",
            colLabels: ["1段", "2段", "3段", "4段", "5段", "6段", "7段", "油温"],
            rows: [{ label: "温度", tags: ["ET1", "ET2", "ET3", "ET4", "ET5", "ET6", "ET7", "EOT"] }],
        },
        {
            title: "温度",
            colLabels: ["1段", "2段", "3段", "4段", "5段", "6段", "7段", "油温"],
            rows: [{ label: "温度", tags: ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "OT"] }],
        },
        {
            title: "生产参数汇总",
            colLabels: ["数值"],
            rows: [
                { label: "模数", tags: ["CYCN"] },
                { label: "产品数量", tags: ["PARTN"] },
                { label: "周期时间", tags: ["ECYCT"] },
                { label: "射出起点", tags: ["EISS"] },
                { label: "最大射速", tags: ["EIVM"] },
                { label: "最大射压", tags: ["EIPM"] },
                { label: "转保压时间", tags: ["ESIPT"] },
                { label: "转保压压力", tags: ["ESIPP"] },
                { label: "转保压位置", tags: ["ESIPS"] },
                { label: "射出保压时间", tags: ["EIPT"] },
                { label: "射出终点位置", tags: ["EIPSE"] },
                { label: "最小射出位置", tags: ["EIPSMIN"] },
                { label: "储料时间", tags: ["EPLST"] },
                { label: "最大储料压力", tags: ["EPLSPM"] },
                { label: "储料扭矩", tags: ["EPLTorque"] },
                { label: "取出时间", tags: ["EFCHT"] },
                { label: "关模时间", tags: ["EMCT"] },
                { label: "低压时间", tags: ["EMCLP"] },
                { label: "高压时间", tags: ["EMCHP"] },
                { label: "开模时间", tags: ["EMOT"] },
                { label: "托模时间", tags: ["EEJET"] },
                { label: "顶出时间", tags: ["EEFT"] },
                { label: "射退时间", tags: ["ESB2T"] },
            ],
        },
        {
            title: "生产状态",
            colLabels: ["数值"],
            rows: [
                { label: "模式", tags: ["OPM"] },
                { label: "生产状态", tags: ["STS"] },
                { label: "警报状态", tags: ["ASTS"] },
                { label: "警报", tags: ["wm"] },
            ],
        },
        {
            title: "射退设定",
            colLabels: ["射退1", "射退2"],
            rows: [
                { label: "速度", tags: [null, "SBV2"] },
                { label: "压力", tags: [null, "SBP2"] },
                { label: "位置", tags: ["SBS1", "SBS2"] },
                { label: "时间(S)", tags: ["SBT1", "SBT2"] },
                { label: "模式", tags: [null, "SBM2"] },
            ],
        },
    ];

    const ADVANCED_DIALOG_BLOCKS = PARAMETER_GRID_BLOCKS.slice(
        0,
        PARAMETER_GRID_BLOCKS.findIndex(b => b.title === "顶针次数") + 1
    );

    // Tags that are categorical status codes or monotonically-increasing
    // counters rather than settable specs (mirrors EXCLUDED_FROM_TARGETS
    // in backend/parameter_labels.py). PARAMETER_GRID_BLOCKS still lists
    // them so their live value shows up in 工艺参数, but excelParamCell
    // renders them as a plain non-editable cell in the 高级工艺参数 /
    // 默认参数设置 dialogs -- the backend silently ignores any
    // target/tolerance submitted for these tags (see valid_tags in
    // molds.py), so showing an editable box for them would be misleading.
    const NON_EDITABLE_TAGS = new Set(["CYCN", "PARTN", "STS", "ASTS", "wm"]);

    // Chinese category names the backend already attaches to each
    // parameter (see categorize()/categorize_tag() in parameter_labels.py)
    // -- used only as the block title for the safety-net "leftover" block
    // below, so a tag never silently disappears just because
    // PARAMETER_GRID_BLOCKS forgot to list it.
    const TECH_LEFTOVER_CATEGORY_ORDER = ["温度参数", "压力参数", "速度参数", "位置参数", "时间参数", "模式设置", "其他参数", "未知参数"];


    let moldExtendedFields = {};
    const EXTENDED_INFO_SECTIONS = [
        {
            title: "客户信息",
            rows: [
                { cols: [
                    { key: "customer_name", label: "客户名称" },
                    { key: "customer_machine_no", label: "注塑机编号" },
                    { key: "machine_model", label: "机型" },
                    { key: "machine_maker", label: "机台厂商" },
                    { key: "form_date", label: "日期", type: "date" },
                ]},
            ],
        },
        {
            title: "模具尺寸 / 文件版本",
            rows: [
                { cols: [
                    { key: "mold_dimensions", label: "模具尺寸(MM)" },
                    { key: "fit_tonnage", label: "适合机台吨位(T)" },
                    { key: "file_version", label: "文件版本" },
                ]},
            ],
        },
        {
            title: "原料信息",
            rows: [
                { cols: [
                    { key: "material_name", label: "原料名称" },
                    { key: "material_origin", label: "原料产地" },
                    { key: "color_code", label: "色种编号" },
                    { key: "color", label: "颜色" },
                    { key: "material_color_ratio", label: "原料:色粉比例" },
                    { key: "drying_time", label: "烘料时间" },
                    { key: "oven_temperature", label: "焗炉温度" },
                ]},
                { cols: [
                    { key: "supplied_by_factory", label: "本厂提供", type: "checkbox" },
                    { key: "supplied_by_customer", label: "客户提供", type: "checkbox" },
                ]},
            ],
        },
        {
            title: "产品重量",
            rows: [
                { cols: [
                    { key: "gross_weight", label: "毛重(g)" },
                    { key: "net_weight", label: "净重(g)" },
                    { key: "runner_weight", label: "水口重(g)" },
                ]},
            ],
            note: "0-10g 不可超出净重±3%，11-50g 不可超出净重±2%，50g 以上不可超出净重±1%",
        },
        {
            title: "热流道温度设定 ±10℃",
            rows: [
                { cols: Array.from({length:5},(_,i)=>({ key:`hot_runner_t${i+1}`, label:`${i+1}段` })) },
                { cols: Array.from({length:5},(_,i)=>({ key:`hot_runner_t${i+6}`, label:`${i+6}段` })) },
            ],
        },
        {
            title: "射胶方式 / 残余料量位置",
            rows: [
                { cols: [
                    { key: "injection_mode_position", label: "位置方式", type: "checkbox" },
                    { key: "injection_mode_time", label: "时间方式", type: "checkbox" },
                    { key: "residual_material_position", label: "残余料量位置(MM)" },
                ]},
            ],
        },
        {
            title: "运水 / 模温",
            rows: [
                { cols: [
                    { label: "运水类别", type: "label" },
                    { key: "water_temp_machine", label: "机水(℃)", type: "checkbox" },
                    { key: "water_temp_hot_water", label: "热水(℃)", type: "checkbox" },
                    { key: "water_temp_hot_oil", label: "热油(℃)", type: "checkbox" },
                    { key: "water_temp_cold_water", label: "冷水(℃)", type: "checkbox" },
                ]},
            ],
            // A real row-label x column-header grid: 运水设定(Ref) /
            // 标准温度±5℃ / 实测模温±5℃ down the left side, A板 / B板 /
            // 行呵 / 抽芯明细 across the top -- 12 independent cells,
            // replacing the old layout where all five were separate
            // single fields crammed into one row.
            grid: {
                colLabels: ["A板", "B板", "行呵"],
                rows: [
                    { label: "运水设定(Ref)", keys: ["water_ref_a", "water_ref_b", "water_ref_c"] },
                    { label: "标准温度±5℃", keys: ["water_std_a", "water_std_b", "water_std_c"] },
                    { label: "实测模温±5℃", keys: ["water_measured_a", "water_measured_b", "water_measured_c"] },
                ],
                spanColumn: { label: "抽芯明细", key: "water_cavity_detail" },
            },
            rows2: [
                { cols: [
                    { key: "ejector_stall_seconds", label: "停留时间(秒)" },
                    { key: "ejector_count", label: "顶出次数" },
                    { key: "ejector_position", label: "顶针位置" },
                ]},
            ],
        },
        {
            title: "周期设定",
            rows: [
                { cols: [
                    { key: "cycle_injection_total", label: "射胶总时间(秒)" },
                    { key: "cycle_cooling_total", label: "冷却总时间(秒)" },
                    { key: "cycle_suction_total", label: "抽呵时间(秒)" },
                    { key: "cycle_grand_total", label: "全程总时间(秒)" },
                ]},
            ],
        },
        {
            title: "操作设定",
            rows: [
                { cols: [
                    { key: "op_manual", label: "手动", type: "checkbox" },
                    { key: "op_semi_auto", label: "半自动", type: "checkbox" },
                    { key: "op_full_auto", label: "全自动", type: "checkbox" },
                    { key: "op_robot", label: "机械手", type: "checkbox" },
                    { key: "op_headcount", label: "需用人数(个)" },
                ]},
            ],
        },
    ];


    function localParamStorageKey(tag) {
        const scope = currentMachineTypeId ? `mt${currentMachineTypeId}` : `mold${editMoldId}`;
        return `${LOCAL_PARAM_STORAGE_PREFIX}${scope}:${tag}`;
    }
    function getLocalParamValue(tag) {
        try { return localStorage.getItem(localParamStorageKey(tag)) || ""; }
        catch (error) { return ""; }
    }
    function setLocalParamValue(tag, value) {
        try { localStorage.setItem(localParamStorageKey(tag), value); }
        catch (error) { /* ignore storage errors -- value just won't persist */ }
    }

    function excelLocalCell(tag, includeValue = true) {
        if (!includeValue) return '<td></td>';
        const value = getLocalParamValue(tag);
        return `<td class="excel-param-cell-local" data-local-parameter="${escapeHtml(tag)}">
            <input class="excel-value-input excel-local-input" type="text"
                value="${value ? escapeHtml(value) : ""}">
        </td>`;
    }

    function extendedFieldCellHtml(field) {
        if (field.type === "label") {
            return `<td class="excel-extended-cell excel-extended-cell-heading">
                <div class="excel-extended-label">${escapeHtml(field.label)}</div>
            </td>`;
        }
        const value = moldExtendedFields[field.key];
        if (field.type === "checkbox") {
            return `<td class="excel-extended-cell" data-extended-key="${escapeHtml(field.key)}">
                <div class="excel-extended-label">${escapeHtml(field.label)}</div>
                <input class="excel-extended-checkbox" type="checkbox" ${value ? "checked" : ""}>
            </td>`;
        }
        return `<td class="excel-extended-cell" data-extended-key="${escapeHtml(field.key)}">
            <div class="excel-extended-label">${escapeHtml(field.label)}</div>
            <input class="excel-extended-input" type="${field.type === "date" ? "date" : "text"}" value="${value != null ? escapeHtml(value) : ""}">
        </td>`;
    }

    // One cell inside a row-label x column-header grid (see the 运水/模温
    // section's `grid` above). Reuses the excel-extended-cell/-input
    // classes so collectExtendedFields() picks these up automatically --
    // no separate collection logic needed.
    function extendedGridCellHtml(key) {
        const value = moldExtendedFields[key];
        return `<td class="excel-extended-cell excel-extended-grid-cell" data-extended-key="${escapeHtml(key)}">
            <input class="excel-extended-input" type="text" value="${value != null ? escapeHtml(value) : ""}">
        </td>`;
    }

    function extendedGridHtml(grid) {
        const headerCells = grid.colLabels.map(label => `<th>${escapeHtml(label)}</th>`).join("");
        const spanHeaderHtml = grid.spanColumn ? `<th>${escapeHtml(grid.spanColumn.label)}</th>` : "";
        const spanCellHtml = grid.spanColumn ? (() => {
            const value = moldExtendedFields[grid.spanColumn.key];
            return `<td class="excel-extended-cell excel-extended-grid-span-cell" data-extended-key="${escapeHtml(grid.spanColumn.key)}" rowspan="${grid.rows.length}">
                <textarea class="excel-extended-input excel-extended-span-input">${value != null ? escapeHtml(value) : ""}</textarea>
            </td>`;
        })() : "";
        const bodyRows = grid.rows.map((row, i) => {
            const cells = row.keys.map(extendedGridCellHtml).join("");
            const spanCell = i === 0 ? spanCellHtml : "";
            return `<tr><th class="excel-extended-grid-label">${escapeHtml(row.label)}</th>${cells}${spanCell}</tr>`;
        }).join("");
        return `<table class="excel-style-table excel-extended-grid-table">
            <thead><tr><th></th>${headerCells}${spanHeaderHtml}</tr></thead>
            <tbody>${bodyRows}</tbody>
        </table>`;
    }

    function renderExtendedInfoSections() {
        return EXTENDED_INFO_SECTIONS.map(section => {
            const mainTableHtml = (section.rows && section.rows.length)
                ? `<table class="excel-style-table excel-extended-table"><tbody>${section.rows.map(row => `<tr>${row.cols.map(extendedFieldCellHtml).join("")}</tr>`).join("")}</tbody></table>`
                : "";
            const gridHtml = section.grid ? extendedGridHtml(section.grid) : "";
            const secondTableHtml = (section.rows2 && section.rows2.length)
                ? `<table class="excel-style-table excel-extended-table" style="margin-top:8px;"><tbody>${section.rows2.map(row => `<tr>${row.cols.map(extendedFieldCellHtml).join("")}</tr>`).join("")}</tbody></table>`
                : "";
            const noteHtml = section.note ? `<div class="excel-extended-note">${escapeHtml(section.note)}</div>` : "";
            return `<div class="excel-extended-section">
                <div class="excel-section-title">${escapeHtml(section.title)}</div>
                ${mainTableHtml}
                ${gridHtml}
                ${secondTableHtml}
                ${noteHtml}
            </div>`;
        }).join("");
    }

    function collectExtendedFields(containerId) {
        const result = {};
        document.querySelectorAll(`#${containerId} .excel-extended-cell`).forEach(cell => {
            const key = cell.dataset.extendedKey;
            if (!key) return; // heading-only cell (e.g. 运水类别 label), nothing to save
            const checkbox = cell.querySelector(".excel-extended-checkbox");
            if (checkbox) { result[key] = checkbox.checked; return; }
            const input = cell.querySelector(".excel-extended-input");
            result[key] = input && input.value !== "" ? input.value : null;
        });
        return result;
    }


    function excelParamCell(paramById, tag, includeValue = true) {
        if (!tag) return '<td></td>';
        if (NON_EDITABLE_TAGS.has(tag)) {
            return `<td class="excel-param-cell-readonly" data-parameter="${escapeHtml(tag)}"><div class="excel-value-readonly excel-cell-missing">不适用</div></td>`;
        }
        if (typeof tag === "string" && tag.startsWith("local:")) return excelLocalCell(tag, includeValue);
        const p = paramById.get(tag);
        if (!p) return '<td class="excel-cell-missing">--</td>';
        const mode = p.tolerance_mode || "percent";
        const toleranceValue = mode === "flat" ? p.tolerance_flat : p.tolerance_percent;
        const valueHtml = `<input class="mold-param-value excel-value-input" type="text" placeholder="${includeValue ? "实际值" : "默认值"}"
            value="${p.value != null ? escapeHtml(p.value) : ""}">`;
        return `<td class="excel-param-cell" data-parameter="${escapeHtml(tag)}">
            ${valueHtml}
            <div class="excel-tolerance-row">
                <select class="mold-param-tolerance-mode excel-tolerance-mode">
                    <option value="percent"${mode === "percent" ? " selected" : ""}>%</option>
                    <option value="flat"${mode === "flat" ? " selected" : ""}>固定</option>
                </select>
                <input class="mold-param-tolerance excel-tolerance-input" type="number" step="0.1" min="0"
                    placeholder="公差" value="${toleranceValue != null ? toleranceValue : ""}">
            </div>
        </td>`;
    }

    // Renders one block as a table with block.title occupying a single
    // rowspan-ed left cell, matching the sheet's "block label spans the
    // whole section" layout instead of a title bar sitting above the table.
    function excelBlockTableHtml(block, paramById, usedTags, includeValue = true) {
        const headerCells = block.colLabels.map(label => `<th>${escapeHtml(label)}</th>`).join("");
        const bodyRows = block.rows.map((row, i) => {
            const cells = row.tags.map(tag => {
                if (tag && !String(tag).startsWith("local:")) usedTags.add(tag);
                return excelParamCell(paramById, tag, includeValue);
            }).join("");
            const pad = "<td></td>".repeat(Math.max(0, block.colLabels.length - row.tags.length));
            const labelCell = i === 0
                ? `<th class="excel-block-label" rowspan="${block.rows.length}">${escapeHtml(block.title)}</th>`
                : "";
            return `<tr>${labelCell}<th>${escapeHtml(row.label)}</th>${cells}${pad}</tr>`;
        }).join("");
        return `<table class="excel-style-table excel-block-table">
            <thead><tr><th></th><th></th>${headerCells}</tr></thead>
            <tbody>${bodyRows}</tbody>
        </table>`;
    }

    function techParamCell(paramById, tag, usedTags) {
        if (!tag) return '<td></td>';
        usedTags.add(tag);
        const p = paramById.get(tag);
        const hasValue = p && p.value != null && p.value !== "";
        const changed = highlightParameter && p && p.parameter_id === highlightParameter.parameter_id;
        const boxClass = `excel-value-readonly${hasValue ? "" : " excel-cell-missing"}${changed ? " parameter-changed" : ""}`;
        return `<td class="excel-param-cell-readonly" data-parameter="${escapeHtml(tag)}"><div class="${boxClass}">${hasValue ? escapeHtml(p.value) : "--"}</div></td>`;
    }

    // True if at least one real (non-"local:") tag in this block has an
    // actual reported value -- used to hide whole sections the current
    // device/machine family never reports anything for (e.g. Toshiba-only
    // or Haitian-only blocks), instead of showing a full table of "--".
    function techBlockHasData(block, paramById) {
        return block.rows.some(row => row.tags.some(tag => {
            if (!tag || tag.startsWith("local:")) return false;
            const p = paramById.get(tag);
            return p && p.value != null && p.value !== "";
        }));
    }

    function techBlockTableHtml(block, paramById, usedTags) {
        if (!techBlockHasData(block, paramById)) {
            // Still mark every real tag as "used" so an empty block never
            // causes its tags to reappear in the leftover safety-net
            // section below (which already hides valueless tags anyway,
            // but this keeps the bookkeeping consistent either way).
            block.rows.forEach(row => row.tags.forEach(tag => { if (tag) usedTags.add(tag); }));
            return "";
        }
        const headerCells = block.colLabels.map(label => `<th>${escapeHtml(label)}</th>`).join("");
        const bodyRows = block.rows.map((row, i) => {
            const cells = row.tags.map(tag => techParamCell(paramById, tag, usedTags)).join("");
            const pad = "<td></td>".repeat(Math.max(0, block.colLabels.length - row.tags.length));
            const labelCell = i === 0
                ? `<th class="excel-block-label" rowspan="${block.rows.length}">${escapeHtml(block.title)}</th>`
                : "";
            return `<tr>${labelCell}<th>${escapeHtml(row.label)}</th>${cells}${pad}</tr>`;
        }).join("");
        return `<table class="excel-style-table excel-block-table excel-block-table-readonly">
            <thead><tr><th></th><th></th>${headerCells}</tr></thead>
            <tbody>${bodyRows}</tbody>
        </table>`;
    }

    function techLeftoverBlocksHtml(parameters, usedTags) {
        const byCategory = new Map();
        parameters.forEach(p => {
            if (usedTags.has(p.parameter_id)) return;
            if (p.value == null || p.value === "") return; // nothing to show
            if (!byCategory.has(p.category)) byCategory.set(p.category, []);
            byCategory.get(p.category).push(p);
        });
        const categories = [...byCategory.keys()].sort(
            (a, b) => TECH_LEFTOVER_CATEGORY_ORDER.indexOf(a) - TECH_LEFTOVER_CATEGORY_ORDER.indexOf(b)
        );
        return categories.map(category => {
            const rows = byCategory.get(category).map((p, i) => {
                const changed = highlightParameter && p.parameter_id === highlightParameter.parameter_id;
                const labelCell = i === 0
                    ? `<th class="excel-block-label" rowspan="${byCategory.get(category).length}">${escapeHtml(category)}</th>`
                    : "";
                return `<tr>${labelCell}<th>${escapeHtml(p.label)}</th><td class="excel-param-cell-readonly" data-parameter="${escapeHtml(p.parameter_id)}"><div class="excel-value-readonly${changed ? " parameter-changed" : ""}">${escapeHtml(p.value)}</div></td></tr>`;
            }).join("");
            return `<table class="excel-style-table excel-block-table excel-block-table-readonly">
                <thead><tr><th></th><th></th><th>数值</th></tr></thead>
                <tbody>${rows}</tbody>
            </table>`;
        }).join("");
    }

    // Small header strip mimicking the sheet's top info rows
    // (模具编号/产品名称/产品编号/模穴数/装机设备), pulled from the same
    // `molds` data already loaded for the mold list -- no new API call.
    // 模具编号/产品名称/模穴数 are editable here (saved alongside the
    // advanced parameters -- see saveMoldBasicFieldsFromAdvanced).
    // 产品编号 has no backing form field anywhere in this app (create/edit
    // mold forms never set it either) and 装机设备 is assignment state
    // managed from the device-detail page, so both stay read-only.
    function excelInfoStripHtml() {
        const m = molds.find(x => x.id === editMoldId);
        if (!m) return "";
        const readOnly = currentUser.role === "viewer";
        const cell = (label, innerHtml) => `<div class="excel-info-cell">
            <div class="excel-info-label">${escapeHtml(label)}</div>
            ${innerHtml}
        </div>`;
        const staticValue = value => `<div class="excel-info-value">${showValue(value)}</div>`;
        const textInput = (id, value) =>
            `<input id="${id}" class="excel-info-input" type="text" value="${value != null ? escapeHtml(value) : ""}" ${readOnly ? "disabled" : ""}>`;
        const numberInput = (id, value) =>
            `<input id="${id}" class="excel-info-input" type="number" min="1" step="1" value="${value != null ? escapeHtml(value) : ""}" ${readOnly ? "disabled" : ""}>`;
        return `<div class="excel-info-strip">
            ${cell("模具编号", textInput("excel-info-mold-code", m.mold_code))}
            ${cell("产品名称", textInput("excel-info-mold-name", m.mold_name))}
            ${cell("产品编号", textInput("excel-info-product-code", m.product_code))}
            ${cell("模穴数", numberInput("excel-info-cavities", m.cavities))}
            ${cell("装机设备", staticValue(m.mounted_device_id))}
        </div>`;
    }

    // Recomputes the 模穴温度 map for a (possibly changed) cavity count,
    // carrying over existing per-cavity values for labels that still
    // exist and leaving new labels blank -- same shape the create/edit
    // mold forms send as `cavity_temperatures`.
    function buildCavityTemperaturesForCount(mold, cavities) {
        const existing = {};
        (mold.cavity_temperatures || []).forEach(t => { existing[t.cavity_label] = t; });
        const result = {};
        for (let i = 1; i <= cavities; i++) {
            const label = String(i);
            const entry = existing[label];
            result[label] = {
                temperature_c: entry && entry.temperature_c != null ? entry.temperature_c : null,
                tolerance_pct: entry && entry.tolerance_pct != null ? entry.tolerance_pct : null,
            };
        }
        return result;
    }

    // Persists edits made to 模具编号/产品名称/模穴数 directly from the
    // advanced-parameters dialog. There's no partial-update endpoint, so
    // this builds a full multipart PUT /api/molds/{id} payload the same
    // shape as the main edit form, filling every other field from the
    // already-loaded mold record (m) so images, cleaning settings, etc.
    // are resubmitted unchanged. No-ops if nothing actually changed.
    async function saveMoldBasicFieldsFromAdvanced() {
    const codeInput = document.getElementById("excel-info-mold-code");
    const nameInput = document.getElementById("excel-info-mold-name");
    const productCodeInput = document.getElementById("excel-info-product-code");
    const cavitiesInput = document.getElementById("excel-info-cavities");
    if (!codeInput || !nameInput || !productCodeInput || !cavitiesInput) return;

    const m = molds.find(x => x.id === editMoldId);
    if (!m) return;

    const moldCode = codeInput.value.trim();
    const moldName = nameInput.value.trim();
    const productCode = productCodeInput.value.trim();
    const cavities = Math.max(1, Number(cavitiesInput.value) || 1);

    if (moldCode === m.mold_code && moldName === m.mold_name
        && productCode === (m.product_code || "") && cavities === m.cavities) return;
    if (!moldCode) throw new Error("模具编号不能为空");
    if (!moldName) throw new Error("产品名称不能为空");

    const body = new FormData();
    body.set("mold_code", moldCode);
    body.set("mold_name", moldName);
    body.set("product_code", productCode);
    body.set("cavities", String(cavities));
        body.set("remark", m.remark || "");
        body.set("is_active", m.is_active ? "1" : "0");
        body.set("cavity_temperatures", JSON.stringify(buildCavityTemperaturesForCount(m, cavities)));
        body.set("requires_cleaning", m.requires_cleaning ? "1" : "0");
        body.set("cleaning_interval_hours", m.cleaning_interval_hours ?? "");
        body.set("cleaning_duration_minutes", m.cleaning_duration_minutes ?? "");
        body.set("max_output", m.max_output ?? "");
        body.set("keep_image_ids", JSON.stringify((m.images || []).map(img => img.id)));
        const faceImage = (m.images || []).find(img => img.is_face);
        if (faceImage) body.set("face_image_id", String(faceImage.id));

        await requestJson(`/api/molds/${editMoldId}`, { method: "PUT", body });
    }

    function renderMoldAdvancedGroups(parameters) {
        const readOnly = currentUser.role === "viewer";
        const paramById = new Map(parameters.map(p => [p.parameter_id, p]));
        const usedTags = new Set();

        const blocksHtml = ADVANCED_DIALOG_BLOCKS
            .map(block => excelBlockTableHtml(block, paramById, usedTags))
            .join("");

        document.getElementById("mold-advanced-groups").innerHTML = `
            ${excelInfoStripHtml()}
            <div id="mold-advanced-extended">${renderExtendedInfoSections()}</div>
            <div class="excel-sections-wrap">${blocksHtml}</div>`;

        if (readOnly) {
            document.querySelectorAll("#mold-advanced-groups .excel-param-cell input, #mold-advanced-groups .excel-param-cell select")
                .forEach(el => { el.disabled = true; });
        }

        document.querySelectorAll("#mold-advanced-groups .excel-local-input").forEach(input => {
            const tag = input.closest("[data-local-parameter]").dataset.localParameter;
            input.addEventListener("change", () => setLocalParamValue(tag, input.value));
        });
        if (readOnly) {
            document.querySelectorAll("#mold-advanced-groups .excel-param-cell input, #mold-advanced-groups .excel-param-cell select, #mold-advanced-groups .excel-local-input")
                .forEach(el => { el.disabled = true; });
        }

        document.querySelectorAll("#mold-advanced-groups .excel-tolerance-mode").forEach(select => {
            select.addEventListener("change", e => {
                const input = e.target.closest(".excel-param-cell").querySelector(".excel-tolerance-input");
                input.placeholder = e.target.value === "flat" ? "公差" : "公差%";
            });
        });
    }

    // ---- Mold -> Machine Type (机型) -> Specifications --------------
    // 编辑模具型号's "机型 / 高级参数" button now opens the machine-type
    // list first; picking a machine type (or adding a new one) is what
    // opens the existing 高级工艺参数 dialog, scoped to that
    // Mold + Machine Type combination via currentMachineTypeId.

    document.getElementById("mold-edit-advanced-button").addEventListener("click", async () => {
        document.getElementById("machine-types-mold-title").textContent = molds.find(x => x.id === editMoldId)?.mold_code || "";
        document.getElementById("mold-machine-types-dialog").showModal();
        await loadMachineTypesList();
    });

    async function loadMachineTypesList() {
        const listEl = document.getElementById("machine-types-list");
        listEl.innerHTML = '<div class="empty">正在读取……</div>';
        try {
            const result = await requestJson(`/api/molds/${encodeURIComponent(editMoldId)}/machine-types`);
            machineTypesCache = result.machine_types || [];
            renderMachineTypesList();
        } catch (error) {
            listEl.innerHTML = `<div class="empty">读取失败：${escapeHtml(error.message)}</div>`;
        }
    }

    function renderMachineTypesList() {
        const listEl = document.getElementById("machine-types-list");
        const readOnly = currentUser.role === "viewer";
        listEl.innerHTML = machineTypesCache.length ? machineTypesCache.map(mt => `
            <div class="detail-card" data-machine-type-id="${mt.id}" style="margin-bottom:0;cursor:pointer;display:flex;align-items:center;justify-content:space-between;gap:10px;">
                <div>
                    <strong>${escapeHtml(mt.machine_type)}</strong>
                    ${mt.is_main ? '<span class="badge production" style="margin-left:8px;">主要机型</span>' : ""}
                </div>
                <div class="actions" style="margin:0;">
                    <button type="button" class="secondary-button view-favorites-button" data-id="${mt.id}" data-name="${escapeHtml(mt.machine_type)}">收藏</button>
                    <button type="button" class="secondary-button rename-machine-type-button" data-id="${mt.id}" data-name="${escapeHtml(mt.machine_type)}" ${readOnly?"disabled":""}>重命名</button>
                    ${mt.is_main ? "" : `<button type="button" class="secondary-button set-main-button" data-id="${mt.id}" ${readOnly?"disabled":""}>设为主要</button>`}
                    <button type="button" class="danger-button delete-machine-type-button" data-id="${mt.id}" ${readOnly || machineTypesCache.length<=1 ?"disabled":""}>删除</button>
                </div>
            </div>`).join("") : '<div class="empty">该模具尚未配置机型</div>';

        listEl.querySelectorAll(".view-favorites-button").forEach(button => {
            button.addEventListener("click", event => {
                event.stopPropagation();
                openFavoritesListDialog(Number(button.dataset.id), button.dataset.name);
            });
        });

        listEl.querySelectorAll("[data-machine-type-id]").forEach(card => {
            card.addEventListener("click", event => {
                if (event.target.closest("button")) return;
                const mt = machineTypesCache.find(x => x.id === Number(card.dataset.machineTypeId));
                openMachineTypeSpecs(mt.id, mt.machine_type);
            });
        });
        listEl.querySelectorAll(".rename-machine-type-button").forEach(button => {
            button.addEventListener("click", async event => {
                event.stopPropagation();
                const nextName = (prompt("机型名称：", button.dataset.name) || "").trim();
                if (!nextName || nextName === button.dataset.name) return;
                try {
                    await requestJson(`/api/molds/${encodeURIComponent(editMoldId)}/machine-types/${encodeURIComponent(button.dataset.id)}`, {
                        method: "PUT",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ machine_type: nextName }),
                    });
                    await loadMachineTypesList();
                } catch (error) { alert(error.message); }
            });
        });
        listEl.querySelectorAll(".set-main-button").forEach(button => {
            button.addEventListener("click", async event => {
                event.stopPropagation();
                try {
                    await requestJson(`/api/molds/${encodeURIComponent(editMoldId)}/machine-types/${encodeURIComponent(button.dataset.id)}/set-main`, { method: "POST" });
                    await loadMachineTypesList();
                } catch (error) { alert(error.message); }
            });
        });
        listEl.querySelectorAll(".delete-machine-type-button").forEach(button => {
            button.addEventListener("click", async event => {
                event.stopPropagation();
                if (!confirm("确认删除该机型？其对应的高级参数将一并删除，此操作不可恢复。")) return;
                try {
                    await requestJson(`/api/molds/${encodeURIComponent(editMoldId)}/machine-types/${encodeURIComponent(button.dataset.id)}`, { method: "DELETE" });
                    await loadMachineTypesList();
                } catch (error) { alert(error.message); }
            });
        });
    }

    document.getElementById("machine-types-close").addEventListener("click", () => {
        document.getElementById("mold-machine-types-dialog").close();
    });

    document.getElementById("machine-type-add-form").addEventListener("submit", async event => {
        event.preventDefault();
        const input = document.getElementById("machine-type-add-input");
        const machineType = input.value.trim();
        try {
            await requestJson(`/api/molds/${encodeURIComponent(editMoldId)}/machine-types`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ machine_type: machineType || null }),
            });
            input.value = "";
            await loadMachineTypesList();
        } catch (error) { alert(error.message); }
    });

    function openMachineTypeSpecs(machineTypeId, machineTypeName) {
        currentMachineTypeId = machineTypeId;
        currentMachineTypeName = machineTypeName;
        moldAdvancedLoaded = false;
        moldExtendedFields = {};
        document.getElementById("mold-advanced-machine-type-title").textContent = machineTypeName;
        document.getElementById("mold-advanced-groups").innerHTML = "";
        document.getElementById("mold-advanced-summary").textContent = "";
        document.getElementById("mold-machine-types-dialog").close();
        document.getElementById("mold-advanced-dialog").showModal();
        loadMoldAdvancedForMachineType();
    }

    async function loadMoldAdvancedForMachineType() {
        if (moldAdvancedLoaded || !currentMachineTypeId) return;
        document.getElementById("mold-advanced-summary").textContent = "正在读取……";
        try {
            const [result, extended] = await Promise.all([
                requestJson(`/api/molds/${encodeURIComponent(editMoldId)}/machine-types/${encodeURIComponent(currentMachineTypeId)}/parameters`),
                requestJson(`/api/molds/${encodeURIComponent(editMoldId)}/machine-types/${encodeURIComponent(currentMachineTypeId)}/extended`),
            ]);
            moldExtendedFields = extended.fields || {};
            renderMoldAdvancedGroups(result.parameters);
            document.getElementById("mold-advanced-summary").textContent = "";
            moldAdvancedLoaded = true;
        } catch (error) {
            document.getElementById("mold-advanced-summary").textContent = `读取失败：${error.message}`;
        }
    }

    document.getElementById("mold-advanced-close").addEventListener("click", () => {
        document.getElementById("mold-advanced-dialog").close();
        document.getElementById("mold-machine-types-dialog").showModal();
        loadMachineTypesList();
    });

    // Downloads the company's 成型参数表 (.xlsx) for the currently
    // open Mold + Machine Type, pre-filled with whatever matching values
    // are already saved in 高级工艺参数 -- see backend/export_xlsx.py for
    // exactly which cells get filled.
    document.getElementById("mold-advanced-export-button").addEventListener("click", async () => {
        if (!currentMachineTypeId) { alert("请先选择机型"); return; }
        const button = document.getElementById("mold-advanced-export-button");
        const originalLabel = button.textContent;
        button.disabled = true;
        button.textContent = "正在生成……";
        try {
            const response = await fetch(`/api/molds/${encodeURIComponent(editMoldId)}/machine-types/${encodeURIComponent(currentMachineTypeId)}/export`, {
                cache: "no-store",
            });
            if (response.status === 401) { window.location.replace("/login"); return; }
            if (!response.ok) {
                const body = await response.json().catch(() => ({}));
                throw new Error(body.detail || `HTTP ${response.status}`);
            }
            const blob = await response.blob();
            const disposition = response.headers.get("Content-Disposition") || "";
            const match = disposition.match(/filename\*=UTF-8''([^;]+)/);
            const filename = match ? decodeURIComponent(match[1]) : "成型参数表.xlsx";
            const url = URL.createObjectURL(blob);
            const link = document.createElement("a");
            link.href = url;
            link.download = filename;
            document.body.appendChild(link);
            link.click();
            link.remove();
            URL.revokeObjectURL(url);
        } catch (error) {
            alert(`导出失败：${error.message}`);
        } finally {
            button.disabled = false;
            button.textContent = originalLabel;
        }
    });

    document.getElementById("mold-advanced-save").addEventListener("click", async () => {
        if (!currentMachineTypeId) { alert("请先选择机型"); return; }
        const parameters = collectParameterRows("mold-advanced-groups");
        const extended = collectExtendedFields("mold-advanced-groups");
        try {
            await saveMoldBasicFieldsFromAdvanced();
            await Promise.all([
                requestJson(`/api/molds/${encodeURIComponent(editMoldId)}/machine-types/${encodeURIComponent(currentMachineTypeId)}/parameters`, {
                    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ parameters }),
                }),
                requestJson(`/api/molds/${encodeURIComponent(editMoldId)}/machine-types/${encodeURIComponent(currentMachineTypeId)}/extended`, {
                    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ fields: extended }),
                }),
            ]);
            moldExtendedFields = extended;
            const newName = (extended.machine_model || "").trim();
            if (newName && newName !== currentMachineTypeName) {
                currentMachineTypeName = newName;
                document.getElementById("mold-advanced-machine-type-title").textContent = newName;
            }

            await loadMolds();
            const m = molds.find(x => x.id === editMoldId);
            if (m) {
                document.getElementById("edit-mold-code").value = m.mold_code;
                document.getElementById("edit-mold-product-code").value = m.product_code || "";
                document.getElementById("edit-mold-name").value = m.mold_name;
                document.getElementById("mold-edit-cavities").value = m.cavities;
                document.getElementById("mold-edit-current-device").textContent =
                    m.mounted_device_id ? `当前装机设备：${m.mounted_device_id}` : "当前未装机";
                rebuildCavityTable("mold-edit-cavities", "mold-edit-cavity-table");
                applyCavityTemperatures("mold-edit-cavity-table", m.cavity_temperatures);
            }

            alert("高级参数已保存");
        } catch (error) { alert(error.message); }
    });
    
    function renderMoldDefaultsGroups(parameters) {
        const readOnly = currentUser.role === "viewer";
        const paramById = new Map(parameters.map(p => [p.parameter_id, p]));
        const usedTags = new Set();

        const blocksHtml = PARAMETER_GRID_BLOCKS
            .map(block => excelBlockTableHtml(block, paramById, usedTags, false))
            .join("");

        document.getElementById("mold-defaults-groups").innerHTML =
            `<div class="excel-sections-wrap">${blocksHtml}</div>`;

        if (readOnly) {
            document.querySelectorAll("#mold-defaults-groups .excel-param-cell input, #mold-defaults-groups .excel-param-cell select")
                .forEach(el => { el.disabled = true; });
        }

        document.querySelectorAll("#mold-defaults-groups .excel-tolerance-mode").forEach(select => {
            select.addEventListener("change", e => {
                const input = e.target.closest(".excel-param-cell").querySelector(".excel-tolerance-input");
                input.placeholder = e.target.value === "flat" ? "公差" : "公差%";
            });
        });
    }

    document.getElementById("mold-search-input")?.addEventListener("input", () => renderMoldList());
    document.getElementById("mold-defaults-button").addEventListener("click", async () => {
        document.getElementById("mold-defaults-dialog").showModal();
        if (moldDefaultsLoaded) return;
        document.getElementById("mold-defaults-summary").textContent = "正在读取……";
        try {
            const result = await requestJson("/api/molds/parameter-defaults");
            renderMoldDefaultsGroups(result.parameters);
            document.getElementById("mold-defaults-summary").textContent = "";
            moldDefaultsLoaded = true;
        } catch (error) {
            document.getElementById("mold-defaults-summary").textContent = `读取失败：${error.message}`;
        }
    });

    document.getElementById("mold-defaults-close").addEventListener("click", () => document.getElementById("mold-defaults-dialog").close());
    document.getElementById("mold-defaults-save").addEventListener("click", async () => {
        const parameters = collectParameterRows("mold-defaults-groups");
        try {
            await requestJson("/api/molds/parameter-defaults", {
                method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ parameters }),
            });
            alert("默认参数已保存，之后新建的模具将自动套用这些数值");
        } catch (error) { alert(error.message); }
    });

    async function fetchUptimeSummary(granularity, periods) {
        return requestJson(`/api/uptime-summary?granularity=${granularity}&periods=${periods}`, {}, 45000);
    }

    // ---- 利用率 · 总览 chart -----------------------------------------
    //
    // One line chart backs the 总览 tab. It can show either:
    //   - the fleet-wide combined trend (utilizationChartMode === "all"),
    //     or
    //   - one or more individually-selected devices
    //     (utilizationChartMode === "devices", devices listed in
    //     compareSelectedDevices).
    //
    // The chart is split into two independent DOM pieces so a selection
    // change never touches the grid:
    //   - a background <svg> (grid lines + x-axis day labels) rendered
    //     once per page-visit and left alone afterwards -- this is what
    //     stays visually "static" while the selection changes.
    //   - a foreground <svg> (the line paths + dots) that gets replaced
    //     and re-animated in (grow left-to-right) every time the
    //     selection changes.
    let utilizationChartMode = "all";
    let utilizationFleetBuckets = [];
    let renderedTrendSeriesKeys = new Set();
    const trendWrapSeries = new Map();
    function setTrendWrapSeries(wrapId, series) { trendWrapSeries.set(wrapId, series); }

    // ---- Shared hover tooltip for every uptime/utilization trend chart ----
    let trendTooltipEl = null;
    function ensureTrendTooltip() {
        if (trendTooltipEl) return trendTooltipEl;
        trendTooltipEl = document.createElement("div");
        trendTooltipEl.className = "trend-tooltip hidden";
        document.body.appendChild(trendTooltipEl);
        return trendTooltipEl;
    }
    function showTrendTooltip(dot, clientX, clientY) {
        const tooltip = ensureTrendTooltip();
        tooltip.textContent = dot.dataset.tooltip || "";
        tooltip.classList.remove("hidden");
        const offset = 14;
        let left = clientX + offset;
        if (left > window.innerWidth - 180) left = clientX - offset - 160;
        tooltip.style.left = `${left}px`;
        tooltip.style.top = `${clientY - 10}px`;
    }
    function hideTrendTooltip() {
        if (trendTooltipEl) trendTooltipEl.classList.add("hidden");
    }
    document.addEventListener("mousemove", event => {
        const dot = event.target.closest(".trend-dot-hit");
        if (dot) showTrendTooltip(dot, event.clientX, event.clientY);
        else hideTrendTooltip();
    });
    document.addEventListener("mouseout", event => { if (!event.relatedTarget) hideTrendTooltip(); });

    function svgPointFromEvent(svg, evt) {
        if (!svg) return null;
        const pt = svg.createSVGPoint();
        pt.x = evt.clientX;
        pt.y = evt.clientY;
        const ctm = svg.getScreenCTM();
        if (!ctm) return null;
        return pt.matrixTransform(ctm.inverse());
    }

    function showMultiTrendTooltip(items, dateLabel, clientX, clientY) {
        const tooltip = ensureTrendTooltip();
        const rows = items
            .slice()
            .sort((a, b) => b.pct - a.pct)
            .map(item => `<div style="display:flex;justify-content:space-between;gap:16px;"><span><i style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${item.color};margin-right:6px;"></i>${escapeHtml(item.label)}</span><span style="font-weight:700;">${item.pct}%</span></div>`)
            .join("");
        tooltip.innerHTML = `<div style="margin-bottom:4px;font-weight:700;opacity:.75;">${escapeHtml(dateLabel)}</div>${rows}`;
        tooltip.classList.remove("hidden");
        const offset = 14;
        let left = clientX + offset;
        if (left > window.innerWidth - 220) left = clientX - offset - 200;
        tooltip.style.left = `${left}px`;
        tooltip.style.top = `${clientY - 10}px`;
    }

    const TREND_DOT_HIT_RADIUS = 14;

    function attachTrendWrapHover(wrapId) {
        const wrap = document.getElementById(wrapId);
        if (!wrap) return;
        wrap.addEventListener("mousemove", event => {
            event.stopPropagation();
            const series = trendWrapSeries.get(wrapId) || [];
            if (!series.length) { hideTrendTooltip(); return; }
            const bgSvg = wrap.querySelector(".uptime-trend-bg");
            const point = svgPointFromEvent(bgSvg, event);
            if (!point) { hideTrendTooltip(); return; }

            const width = 920, height = 300, padL = 40, padR = 14, padT = 18, padB = 30;
            const innerW = width - padL - padR, innerH = height - padT - padB;
            const maxLen = Math.max(...series.map(s => s.buckets.length));
            if (maxLen < 1) { hideTrendTooltip(); return; }
            const stepX = maxLen > 1 ? innerW / (maxLen - 1) : 0;
            let index = stepX > 0 ? Math.round((point.x - padL) / stepX) : 0;
            index = Math.max(0, Math.min(maxLen - 1, index));

            const items = series
                .filter(s => s.buckets[index])
                .map(s => {
                    const dotX = padL + stepX * index;
                    const dotY = padT + innerH - (s.buckets[index].uptime_pct / 100) * innerH;
                    const dist = Math.hypot(point.x - dotX, point.y - dotY);
                    return { label: s.label, pct: s.buckets[index].uptime_pct, color: s.color, dist };
                })
                .filter(item => item.dist <= TREND_DOT_HIT_RADIUS);

            if (!items.length) { hideTrendTooltip(); return; }
            const dateLabel = (series[0].buckets[index] || {}).label || "";
            showMultiTrendTooltip(items, dateLabel, event.clientX, event.clientY);
        });
        wrap.addEventListener("mouseleave", () => hideTrendTooltip());
    }

    function renderTrendGrid(buckets) {
        const width=920, height=300, padL=40, padR=14, padT=18, padB=30;
        const innerW=width-padL-padR, innerH=height-padT-padB;
        const stepX = buckets.length>1 ? innerW/(buckets.length-1) : 0;
        const gridLines=[0,25,50,75,100].map(v=>{
            const y=padT+innerH-(v/100)*innerH;
            return `<line x1="${padL}" y1="${y}" x2="${width-padR}" y2="${y}" stroke="#e2e8f0" stroke-width="1"/><text x="${padL-8}" y="${y+4}" font-size="10" fill="#9098a2" text-anchor="end">${v}%</text>`;
        }).join("");
        const labelEvery=Math.max(1,Math.ceil(buckets.length/8));
        const xLabels = buckets.map((b,i)=> i%labelEvery===0 ? `<text x="${padL+stepX*i}" y="${height-8}" font-size="10" fill="#9098a2" text-anchor="middle">${escapeHtml(b.label)}</text>` : "").join("");
        return `<svg class="uptime-trend-svg uptime-trend-bg" viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet">${gridLines}${xLabels}</svg>`;
    }

    function seriesKey(s) { return s.label; }

    function renderTrendSeriesInner(s) {
        const width=920, height=300, padL=40, padR=14, padT=18, padB=30;
        const innerW=width-padL-padR, innerH=height-padT-padB;
        const stepX = s.buckets.length>1 ? innerW/(s.buckets.length-1) : 0;
        const points = s.buckets.map((b,i) => {
            const x = padL + stepX*i;
            const y = padT + innerH - (b.uptime_pct/100)*innerH;
            return {x,y,b};
        });
        const linePath = points.map((p,i)=>`${i===0?"M":"L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
        const dots = points.map((p)=>
            `<circle class="uptime-trend-dot" cx="${p.x}" cy="${p.y}" r="3" fill="${s.color}" style="pointer-events:none"/>`
        ).join("");
        return `<path d="${linePath}" fill="none" stroke="${s.color}" stroke-width="2"/>${dots}`;
    }

    function renderTrendSeriesSvg(s, animate) {
        const width=920, height=300;
        const startClip = animate ? "inset(0 100% 0 0)" : "inset(0 0% 0 0)";
        return `<svg class="uptime-trend-svg uptime-trend-fg" data-series-key="${escapeHtml(seriesKey(s))}" viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet" style="clip-path:${startClip}">${renderTrendSeriesInner(s)}</svg>`;
    }

    function renderTrendLegend(series) {
        if (series.length <= 1) return "";
        return series.map(s => `<span><i class="dot" style="background:${s.color}"></i>${escapeHtml(s.label)}</span>`).join("");
    }

    async function refreshUtilizationChart(animate) {
        const fgSlot = document.getElementById("util-trend-fg-slot");
        const legendEl = document.getElementById("util-trend-legend");
        if (!fgSlot) return;

        let series;
        if (utilizationChartMode === "devices" && compareSelectedDevices.size > 0) {
            const selected = [...compareSelectedDevices];
            try {
                const results = await Promise.all(selected.map(id =>
                    requestJson(`/api/uptime/${encodeURIComponent(id)}?granularity=day&periods=30`)
                ));
                series = selected.map((id, i) => ({
                    label: id, color: COMPARE_COLORS[i % COMPARE_COLORS.length], buckets: results[i].buckets,
                }));
            } catch (error) {
                fgSlot.innerHTML = "";
                renderedTrendSeriesKeys.clear();
                if (legendEl) legendEl.innerHTML = "";
                const wrap = document.getElementById("util-trend-wrap");
                if (wrap) wrap.insertAdjacentHTML("afterend", `<div class="empty" data-trend-error="1">读取失败：${escapeHtml(error.message)}</div>`);
                return;
            }
        } else {
            series = [{ label: "全部设备", color: "#19b58a", buckets: utilizationFleetBuckets }];
        }

        document.querySelectorAll('[data-trend-error="1"]').forEach(el => el.remove());
        setTrendWrapSeries("util-trend-wrap", series);

        const reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        const currentKeys = new Set(series.map(seriesKey));

        // Drop lines that are no longer selected.
        fgSlot.querySelectorAll(".uptime-trend-fg").forEach(el => {
            if (!currentKeys.has(el.dataset.seriesKey)) el.remove();
        });
        [...renderedTrendSeriesKeys].forEach(key => {
            if (!currentKeys.has(key)) renderedTrendSeriesKeys.delete(key);
        });

        // Redraw every selected line with fresh data, but only animate the
        // ones that haven't been shown before -- already-selected lines get
        // their data refreshed in place, staying visually static, and
        // critically their outer <svg> element is left completely alone.
        // Removing/re-inserting that element (the old behavior) tore out
        // whatever WAAPI entrance animation was still running on its
        // clip-path and replaced it with a fresh, already-finished element,
        // which is what made an in-progress line snap straight to its end
        // state whenever the device selection changed mid-animation. Each
        // line's entrance animation now plays out fully independently of
        // every other line and of later selection changes.
        series.forEach(s => {
            const key = seriesKey(s);
            const existing = fgSlot.querySelector(`.uptime-trend-fg[data-series-key="${CSS.escape(key)}"]`);
            const isNew = !renderedTrendSeriesKeys.has(key);

            if (existing && !isNew) {
                // Already on screen (and possibly still mid-animation) --
                // just refresh the drawn path/dots in place.
                existing.innerHTML = renderTrendSeriesInner(s);
                return;
            }

            if (existing) existing.remove();

            const shouldAnimate = animate && isNew && !reduceMotion;
            fgSlot.insertAdjacentHTML("beforeend", renderTrendSeriesSvg(s, shouldAnimate));

            if (shouldAnimate) {
                const el = fgSlot.querySelector(`.uptime-trend-fg[data-series-key="${CSS.escape(key)}"]`);
                requestAnimationFrame(() => requestAnimationFrame(() => {
                    el.animate(
                        [{ clipPath: "inset(0 100% 0 0)" }, { clipPath: "inset(0 0% 0 0)" }],
                        { duration: 4200, easing: "cubic-bezier(.4,0,.2,1)", fill: "both" }
                    );
                }));
            }
            renderedTrendSeriesKeys.add(key);
        });

        if (legendEl) legendEl.innerHTML = renderTrendLegend(series);
    }

    function renderCompareDeviceCheckboxes() {
        const container = document.getElementById("uptime-compare-devices");
        if (!container) return;
        const overviewChecked = utilizationChartMode === "all";
        const allDevicesChecked = utilizationChartMode === "devices"
            && devices.length > 0
            && devices.every(d => compareSelectedDevices.has(d.device_id));
        const deviceCheckboxes = devices.map(d => `
            <label class="uptime-compare-device-label">
                <input type="checkbox" class="compare-device-checkbox" value="${escapeHtml(d.device_id)}" ${(!overviewChecked && compareSelectedDevices.has(d.device_id))?"checked":""}>
                ${escapeHtml(d.device_id)}
            </label>`).join("");
        container.innerHTML = `
            <label class="uptime-compare-device-label uptime-compare-overview-label">
                <input type="checkbox" id="compare-overview-checkbox" ${overviewChecked?"checked":""}>
                总览（全部设备）
            </label>
            <label class="uptime-compare-device-label uptime-compare-overview-label">
                <input type="checkbox" id="compare-all-devices-checkbox" ${allDevicesChecked?"checked":""}>
                全部设备（分设备显示）
            </label>
            ${deviceCheckboxes || '<div class="muted">暂无设备</div>'}`;

        document.getElementById("compare-overview-checkbox").addEventListener("change", async e => {
            if (e.target.checked) {
                utilizationChartMode = "all";
                compareSelectedDevices.clear();
                renderCompareDeviceCheckboxes();
                await refreshUtilizationChart(true);
            } else if (compareSelectedDevices.size === 0) {
                e.target.checked = true;
            }
        });

        document.getElementById("compare-all-devices-checkbox").addEventListener("change", async e => {
            if (e.target.checked) {
                utilizationChartMode = "devices";
                compareSelectedDevices = new Set(devices.map(d => d.device_id));
            } else {
                compareSelectedDevices.clear();
                utilizationChartMode = "all";
            }
            renderCompareDeviceCheckboxes();
            await refreshUtilizationChart(true);
        });

        container.querySelectorAll(".compare-device-checkbox").forEach(cb => {
            cb.addEventListener("change", async () => {
                if (cb.checked) {
                    compareSelectedDevices.add(cb.value);
                    utilizationChartMode = "devices";
                } else {
                    compareSelectedDevices.delete(cb.value);
                    if (compareSelectedDevices.size === 0) utilizationChartMode = "all";
                }
                renderCompareDeviceCheckboxes();
                await refreshUtilizationChart(true);
            });
        });
    }

    async function renderUtilizationOverviewAll(containerId, renderedOnce) {
            const container = document.getElementById(containerId);
            const freshEntry = !renderedOnce.overview;

            let dayData, weekData, monthData;
            try {
                [dayData, weekData, monthData] = await Promise.all([
                    fetchUptimeSummary("day", 30),
                    fetchUptimeSummary("week", 2),
                    fetchUptimeSummary("month", 2),
                ]);
            } catch (error) {
                renderedOnce.overview = false;
                container.innerHTML = `<div class="empty">
                    读取失败：${escapeHtml(error.message)}
                    <div style="margin-top:10px;"><button id="util-overview-retry" class="secondary-button" type="button">重试</button></div>
                </div>`;
                document.getElementById("util-overview-retry")?.addEventListener("click", () => {
                    renderUtilizationOverviewAll(containerId, renderedOnce);
                });
                throw error;
            }

            const today = dayData.buckets[dayData.buckets.length-1];
            const thisWeek = weekData.buckets[weekData.buckets.length-1];
            const thisMonth = monthData.buckets[monthData.buckets.length-1];
            const deviceCount = dayData.device_count || 0;
            utilizationFleetBuckets = dayData.buckets;

            const summaryHtml = `
                <div class="uptime-summary-grid">
                    <div class="uptime-summary-card"><div class="muted">今日综合稼动率（${deviceCount} 台设备）</div><div class="uptime-summary-value">${today?today.uptime_pct:0}% ${renderUptimeDelta(today?.uptime_pct, dayData.comparable_previous_pct)}</div>${today?renderUptimeBar(today):""}</div>
                    <div class="uptime-summary-card"><div class="muted">本周综合稼动率</div><div class="uptime-summary-value">${thisWeek?thisWeek.uptime_pct:0}% ${renderUptimeDelta(thisWeek?.uptime_pct, weekData.comparable_previous_pct)}</div>${thisWeek?renderUptimeBar(thisWeek):""}</div>
                    <div class="uptime-summary-card"><div class="muted">本月综合稼动率</div><div class="uptime-summary-value">${thisMonth?thisMonth.uptime_pct:0}% ${renderUptimeDelta(thisMonth?.uptime_pct, monthData.comparable_previous_pct)}</div>${thisMonth?renderUptimeBar(thisMonth):""}</div>
                </div>`;

        if (freshEntry) {
            renderedTrendSeriesKeys.clear();
            container.innerHTML = `
                ${summaryHtml}
                <article class="detail-card">
                    <div class="detail-header"><div class="detail-title">稼动率趋势（近30日）</div></div>
                    <div class="muted" style="margin-bottom:10px;">默认展示全部设备的综合稼动率；勾选下方设备可切换为单台或多台设备的趋势对比</div>
                    <div class="uptime-trend-wrap" id="util-trend-wrap">
                        ${renderTrendGrid(utilizationFleetBuckets)}
                        <div id="util-trend-fg-slot"></div>
                    </div>
                    <div class="uptime-compare-legend" id="util-trend-legend"></div>
                    <div class="uptime-compare-devices" id="uptime-compare-devices" style="margin-top:14px;"></div>
                </article>`;
            renderCompareDeviceCheckboxes();
            playUtilEntranceAnimation(container);
            attachTrendWrapHover("util-trend-wrap");
        } else {
            const summaryGrid = container.querySelector(".uptime-summary-grid");
            if (summaryGrid) summaryGrid.outerHTML = summaryHtml;
            renderCompareDeviceCheckboxes();
        }

        await refreshUtilizationChart(freshEntry);
        renderedOnce.overview = true;
    }

    async function requestJson(url, options = {}, timeoutMs = 15000) {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
        let response;
        try {
            response = await fetch(url, { cache: "no-store", signal: controller.signal, ...options });
        } catch (error) {
            if (error.name === "AbortError") throw new Error("请求超时，请检查网络连接");
            throw error;
        } finally {
            clearTimeout(timeoutId);
        }
        if (response.status === 401) { window.location.replace("/login"); throw new Error("登录已失效"); }
        const body = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(body.detail || `HTTP ${response.status}`);
        return body;
    }

        function showMachineTypeMismatchDialog(deviceType, sheetType) {
        return new Promise(resolve => {
            document.getElementById("mismatch-device-type").textContent = deviceType || "（未设置）";
            document.getElementById("mismatch-sheet-type").textContent = sheetType || "（未命名）";
            const dialog = document.getElementById("machine-type-mismatch-dialog");
            const confirmBtn = document.getElementById("mismatch-force-button");
            const cancelBtn = document.getElementById("mismatch-cancel-button");
            const closeBtn = document.getElementById("mismatch-close-x");
            function cleanup(result) {
                dialog.close();
                confirmBtn.removeEventListener("click", onConfirm);
                cancelBtn.removeEventListener("click", onCancel);
                closeBtn.removeEventListener("click", onCancel);
                resolve(result);
            }
            function onConfirm() { cleanup(true); }
            function onCancel() { cleanup(false); }
            confirmBtn.addEventListener("click", onConfirm);
            cancelBtn.addEventListener("click", onCancel);
            closeBtn.addEventListener("click", onCancel);
            dialog.showModal();
        });
    }

    async function requestJsonWithMismatch(url, options = {}) {
        let response = await fetch(url, { cache: "no-store", ...options });
        if (response.status === 409) {
            const body = await response.json().catch(() => ({}));
            const detail = body.detail;
            if (detail && typeof detail === "object" && detail.error === "machine_type_mismatch") {
                const proceed = await showMachineTypeMismatchDialog(detail.device_machine_type, detail.sheet_machine_type);
                if (!proceed) return null;
                const payload = options.body ? JSON.parse(options.body) : {};
                payload.force = true;
                response = await fetch(url, { ...options, cache: "no-store", body: JSON.stringify(payload) });
            } else {
                throw new Error((detail && detail.message) || detail || `HTTP ${response.status}`);
            }
        }
        if (response.status === 401) { window.location.replace("/login"); throw new Error("登录已失效"); }
        const resultBody = await response.json().catch(() => ({}));
        if (!response.ok) {
            const detail = resultBody.detail;
            throw new Error((detail && detail.message) || detail || `HTTP ${response.status}`);
        }
        return resultBody;
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
        if (!machine.data_time) return "offline";
        const age = Date.now() - new Date(machine.data_time).getTime();
        if (!Number.isFinite(age) || age > 120000) return "offline";
        if (Number(machine.machine_status) === 2) return "production";

        const cycleAge = machine.cycle_data_time
            ? Date.now() - new Date(machine.cycle_data_time).getTime()
            : Infinity; // no SPC row ever seen -- treat as "stalled"
        const changeAge = machine.last_change_at
            ? Date.now() - new Date(machine.last_change_at).getTime()
            : Infinity;

        if (cycleAge > CHANGING_MOLDS_STALL_MS && changeAge <= RECENT_PARAM_CHANGE_MS) return "changing";
        return "waiting";
    }
    
    function statusMeta(status) {
    if (status === "production") return ["生产", "production"];
    if (status === "changing") return ["换模中", "changing"];
    if (status === "waiting") return ["待机", "waiting"];
    return ["离线", "offline"];
}

    function daySegmentMeta(status) {
        if (status === "active") return ["生产", "production"];
        if (status === "standby") return ["待机", "waiting"];
        return ["离线", "offline"];
    }

    function ageText(value) {
        if(!value) return "无数据";
        const seconds=Math.max(0,Math.floor((Date.now()-new Date(value).getTime())/1000));
        if(seconds<60) return `${seconds} 秒前`;
        if(seconds<3600) return `${Math.floor(seconds/60)} 分钟前`;
        return `${Math.floor(seconds/3600)} 小时前`;
    }

    // Formats a duration given in whole minutes as "X 分钟" under an hour, or
    // "X 小时 Y 分钟" (dropping the minutes if they're exactly 0) once it
    // crosses 60 minutes -- used by the day-detail timeline tooltip and the
    // scrolling segment list below it.
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
        document.getElementById("clear-all-warnings").disabled=readOnly;
        document.getElementById("device-mold-change-button").disabled = readOnly;
        document.getElementById("device-mold-unmount-button").disabled = readOnly;
        document.getElementById("mold-defaults-save").disabled = readOnly;
        document.getElementById("device-delete-button").disabled = readOnly;
    }
    async function loadDevices() {
        devices=await requestJson("/api/devices");
        const select=document.getElementById("device-select"),previous=select.value;
        select.innerHTML=devices.map(d=>`<option value="${escapeHtml(d.device_id)}">设备 ${escapeHtml(d.device_id)}</option>`).join("");
        if(devices.some(d=>d.device_id===previous)) select.value=previous;
    }
    async function loadDashboard() {
        dashboardMachines=await requestJson("/api/dashboard");
        renderDashboard();
    }
    function locationOf(deviceId) {
        return typeof deviceId === "string" ? deviceId[0] : null;
    }
    function filteredMachines() {
        const location=document.getElementById("filter-location").value;
        const statuses=new Set([...document.querySelectorAll(".status-filter:checked")].map(input=>input.value));
        return dashboardMachines.filter(m=>
            (!location||locationOf(m.device_id)===location)
            &&statuses.has(statusOf(m))
        );
    }
    function machineVisualHtml(machine) {
        return `<div class="machine-visual"><div class="device-name">${escapeHtml(machine.device_id)}</div>${machineVisual(machine.device_id)}</div>`;
    }
    function deviceInfoHtml(machine) {
        const status=statusOf(machine),meta=statusMeta(status);
        const readOnly = !currentUser || currentUser.role === "viewer";
        return `<div class="device-info">
                <div class="info-row"><span class="info-label">设备编号</span><span>${showValue(machine.device_id)}</span></div>
                <div class="info-row"><span class="info-label">机型</span><span class="device-type-row"><span class="device-type-value">${showValue(machine.machine_type)}</span>${readOnly?"":`<button type="button" class="device-type-edit-btn" data-device="${escapeHtml(machine.device_id)}" title="编辑机型">✎</button>`}</span></div>
                <div class="info-row"><span class="info-label">产品编号</span><strong>${showValue(machine.mold_code)}</strong></div>
                <div class="info-row"><span class="info-label">模具名称</span><span>${showValue(machine.mold_name)}</span></div>
                <div class="info-row"><span class="info-label">设备状态</span><span class="status-line"><span class="badge ${meta[1]}">${meta[0]}</span><span class="age">${ageText(machine.data_time)}</span></span></div>
                <div class="device-metrics">模次：${showValue(machine.cycle_number)}<br>周期时间：${showValue(machine.cycle_time," s")}<br>操作模式：${showValue(machine.operation_mode_label)}　油温：${showValue(machine.oil_temperature," ℃")}</div>
            </div>`;
    }
    function deviceCardInnerHtml(machine) {
        return machineVisualHtml(machine) + deviceInfoHtml(machine);
    }

    function renderDashboard() {
        const totals = { production: 0, waiting: 0, changing: 0, offline: 0 };
        dashboardMachines.forEach(m => totals[statusOf(m)]++);
        document.getElementById("production-count").textContent = totals.production;
        document.getElementById("waiting-count").textContent = totals.waiting;
        document.getElementById("changing-count").textContent = totals.changing;
        document.getElementById("offline-count").textContent = totals.offline;
        const filtered=filteredMachines(),pages=Math.max(1,Math.ceil(filtered.length/pageSize));
        dashboardPage=Math.min(dashboardPage,pages);
        const start=(dashboardPage-1)*pageSize,current=filtered.slice(start,start+pageSize);
        const grid=document.getElementById("device-grid");

        if (!current.length) {
            grid.innerHTML='<div class="empty panel">没有符合条件的设备</div>';
        } else {
            const existingCards=[...grid.querySelectorAll(".device-card")];
            const existingIds=existingCards.map(card=>card.dataset.device);
            const currentIds=current.map(m=>m.device_id);
            const sameLayout=existingIds.length===currentIds.length && existingIds.every((id,i)=>id===currentIds[i]);

        if (sameLayout) {
            current.forEach((machine,i)=>{
                const infoEl = existingCards[i].querySelector(".device-info");
                if (infoEl) infoEl.outerHTML = deviceInfoHtml(machine);
                else existingCards[i].innerHTML = deviceCardInnerHtml(machine); // fallback, shouldn't normally happen
            });
            } else {
                grid.innerHTML=current.map(machine=>
                    `<article class="device-card" data-device="${escapeHtml(machine.device_id)}">${deviceCardInnerHtml(machine)}</article>`
                ).join("");
            }
        }

        document.getElementById("page-summary").textContent=`共 ${filtered.length} 台，每页 ${pageSize} 台`;
        const buttons=document.getElementById("page-buttons");
        buttons.innerHTML=Array.from({length:pages},(_,i)=>`<button class="${i+1===dashboardPage?"active":""}" data-page-number="${i+1}">${i+1}</button>`).join("");
        buttons.querySelectorAll("button").forEach(button=>button.addEventListener("click",()=>{dashboardPage=Number(button.dataset.pageNumber);renderDashboard();}));
    }

    function renderDayTimeline(dayStart, dayEnd, segments) {
        const startMs = new Date(dayStart).getTime();
        const fullDayMs = 24 * 60 * 60 * 1000;
        const totalMs = fullDayMs;
        const blocks = segments.map(seg => {
            const segStart = new Date(seg.start).getTime();
            const segEnd = new Date(seg.end).getTime();
            const left = (segStart - startMs) / totalMs * 100;
            const width = Math.max(0.15, (segEnd - segStart) / totalMs * 100);
            const durationMin = Math.round((segEnd - segStart) / 60000);
            const meta = daySegmentMeta(seg.status);
            return `<div class="day-timeline-segment ${meta[1]}" style="left:${left}%;width:${width}%" title="${meta[0]} ${formatTime(seg.start)} - ${formatTime(seg.end)} (${formatDurationMinutes(durationMin)})"></div>`;
        }).join("");
        const hourLabels = Array.from({length:9},(_,i)=>`<span>${i*3}:00</span>`).join("");
        return `<div class="day-timeline">${blocks}</div><div class="day-timeline-hours">${hourLabels}</div>`;
    }

    function renderDaySegmentList(segments) {
        if(!segments.length) return '<div class="empty">暂无数据</div>';
        return `<div class="day-detail-segments">${segments.map(seg=>{
            const durationMin=Math.round((new Date(seg.end)-new Date(seg.start))/60000);
            const meta=daySegmentMeta(seg.status);
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
                ${renderDaySegmentList(data.segments.slice().reverse())}`;
        } catch(error) {
            document.getElementById("day-detail-body").innerHTML=`<div class="empty">读取失败：${escapeHtml(error.message)}</div>`;
        }
    }
    document.getElementById("day-detail-close").addEventListener("click",()=>document.getElementById("day-detail-dialog").close());

    async function loadRealtime(id) {
        const m=await requestJson(`/api/realtime/${encodeURIComponent(id)}`);
        const statusTiles=[
            metric("机器状态 (STS)",m.machine_status_label,"",true),
            metric("模式 (OPM)",m.operation_mode_label,"",true),
            metric("警报状态 (ASTS)",m.alarm_status_label,"",true),
            metric("生产油温 (OT)",m.oil_temperature," ℃",true),
        ].join("");
        const temperatureTiles=[1,2,3,4,5,6,7].map(i=>metric(`温度 T${i}`,m[`temperature_${i}`]," ℃")).join("");
        const readOnly = currentUser.role === "viewer";
        const cycleTile = metric("模次", m.cycle_number, "", true);
        document.getElementById("detail-tab-realtime").innerHTML=`
            <article class="detail-card">
                <div class="detail-header"><div class="detail-title">实时状态</div><div class="muted">数据时间：${formatTime(m.data_time)}</div></div>
                <div class="metric-grid">${cycleTile}${statusTiles}</div>
            </article>
            <article class="detail-card">
                <div class="detail-title">料筒温度</div>
                <div class="metric-grid">${temperatureTiles}</div>
            </article>`;

        document.getElementById("cycle-count-reset-button")?.addEventListener("click", async () => {
            if (!confirm("确认重置？将清零本页模次显示，以及当前装机模具的今日/本周/累计产量与产量超限提醒。机台原始 CYCN 计数不受影响，此操作不可撤销。")) return;
            try {
                await requestJson(`/api/devices/${encodeURIComponent(id)}/cycle-count/reset`, { method: "POST" });
                await loadRealtime(id);
                await loadDeviceMoldCard(id);
            } catch (error) { alert(error.message); }
        });
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

    async function loadTech(id) {
        const result=await requestJson(`/api/tech/${encodeURIComponent(id)}`);
        const paramById=new Map(result.parameters.map(p=>[p.parameter_id,p]));

        let highlightMatch=null;
        if(highlightParameter && highlightParameter.parameter_id){
            highlightMatch=result.parameters.find(p=>p.parameter_id===highlightParameter.parameter_id)||null;
        }

        const usedTags=new Set();
        const blocksHtml=PARAMETER_GRID_BLOCKS.map(block=>techBlockTableHtml(block,paramById,usedTags)).join("");
        const leftoverHtml=techLeftoverBlocksHtml(result.parameters,usedTags);
        const hasAnyData=result.parameters.some(p=>p.value!=null && p.value!=="");

        const highlightBanner=(highlightParameter && highlightParameter.parameter_id)?`<div class="changelog-banner">变更提示：<strong>${escapeHtml(highlightMatch?highlightMatch.label:highlightParameter.parameter_id)}</strong> ${showValue(highlightParameter.previous_value)} → <strong class="changelog-banner-new">${showValue(highlightParameter.new_value)}</strong></div>`:"";
        document.getElementById("detail-tab-tech").innerHTML=`<article class="detail-card">${highlightBanner}<div class="detail-header"><div class="detail-title">工艺参数</div><span class="muted">参数时间：${formatTime(result.data_time)}</span></div><div class="excel-sections-wrap">${hasAnyData?`${blocksHtml}${leftoverHtml}`:'<div class="empty">暂无工艺参数</div>'}</div></article>`;

        if(highlightParameter && highlightParameter.parameter_id && !highlightApplied){
            const target=document.querySelector(`#detail-tab-tech [data-parameter="${CSS.escape(highlightParameter.parameter_id)}"]`);
            target?.scrollIntoView({block:"center",behavior:"smooth"});
            highlightApplied=true;
        }
    }

    async function loadSpc(id) {
        const result=await requestJson(`/api/spc/${encodeURIComponent(id)}`);
        const has=name=>Object.hasOwn(result,name);
        const tile=name=>metric(spcFields[name][0],result[name],spcFields[name][1]);
        const overviewNames=["cycle_time","oil_temperature","injection_max_pressure"];
        const tempNames=["temperature_1","temperature_2","temperature_3","temperature_4","temperature_5","temperature_6","temperature_7"];
        const injectionNames=["injection_start_position","injection_max_speed","injection_time","injection_end_position","switch_pressure","switch_position","switch_time"];
        const timingNames=["mold_close_time","mold_open_time","plasticizing_time","plasticizing_max_pressure","pickup_time","low_pressure_time","high_pressure_time","screw_retract_time","eject_time"];
        const overviewTiles=overviewNames.filter(has).map(name=>metric(spcFields[name][0],result[name],spcFields[name][1],true)).join("");
        const tempTiles=tempNames.filter(has).map(tile).join("");
        const injectionTiles=injectionNames.filter(has).map(tile).join("");
        const timingTiles=timingNames.filter(has).map(tile).join("");

        document.getElementById("detail-tab-spc").innerHTML=[
            `<article class="detail-card"><div class="detail-header"><div class="detail-title">最新 SPC</div><div class="muted">数据时间：${formatTime(result.data_time)}</div></div><div class="metric-grid">${overviewTiles||'<div class="empty">暂无数据</div>'}</div></article>`,
            tempTiles&&`<article class="detail-card"><div class="detail-title">生产温度</div><div class="metric-grid">${tempTiles}</div></article>`,
            injectionTiles&&`<article class="detail-card"><div class="detail-title">注射 / 保压参数</div><div class="metric-grid">${injectionTiles}</div></article>`,
            timingTiles&&`<article class="detail-card"><div class="detail-title">工艺时间参数</div><div class="metric-grid">${timingTiles}</div></article>`,
        ].filter(Boolean).join("");
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


    function renderUptimeDelta(currentPct, previousPct) {
        if (currentPct == null || previousPct == null) return "";
        const delta = Math.round((currentPct - previousPct) * 10) / 10;
        if (delta === 0) return `<span class="uptime-delta uptime-delta-flat" title="较上一周期同时段持平">± 0%</span>`;
        const up = delta > 0;
        return `<span class="uptime-delta ${up ? "uptime-delta-up" : "uptime-delta-down"}" title="较上一周期同时段${up ? "上升" : "下降"}">${up ? "▲" : "▼"} ${up ? "+" : ""}${delta.toFixed(1)}%</span>`;
    }


    function renderUptimeTrendChart(buckets, wrapId, seriesLabel = "稼动率", color = "#19b58a") {
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
            `<circle class="uptime-trend-dot" cx="${p.x}" cy="${p.y}" r="3" fill="${color}" style="pointer-events:none"/>`
        ).join("");
        return `<div class="uptime-trend-wrap" id="${wrapId}">
            <svg class="uptime-trend-svg uptime-trend-bg" viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet">
                ${gridLines}
                ${xLabels}
            </svg>
            <svg class="uptime-trend-svg uptime-trend-fg" viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet">
                <path d="${linePath}" fill="none" stroke="${color}" stroke-width="2"/>
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
        // brand new nodes. Pin every element to its collapsed starting
        // point right away, synchronously, so nothing can ever paint at
        // full size first.
        segments.forEach(segment => { segment.style.transform = "scaleX(0)"; });
        trends.forEach(fg => { fg.style.clipPath = "inset(0 100% 0 0)"; });

        // Starting the actual .animate() calls is deferred to two
        // animation frames out. This matters because this function can
        // run in the very same synchronous tick that the container (or
        // an ancestor) is unhidden -- e.g. the 利用率 tab inside device
        // detail unhides its content right before fetching/rendering it.
        // Calling .animate() while an element has no render box yet
        // (display:none, or the unhide hasn't been painted) doesn't
        // animate at all -- the browser has nothing to interpolate
        // against, so it just snaps straight to the fill:"both" end
        // state the instant the element actually becomes visible, which
        // is exactly what read as the animation "abruptly finishing".
        // Waiting two frames guarantees the pinned collapsed state above
        // has already been painted at least once before playback starts.
        requestAnimationFrame(() => requestAnimationFrame(() => {
            segments.forEach(segment => {
                segment.animate(
                    [{ transform: "scaleX(0)" }, { transform: "scaleX(1)" }],
                    { duration: 3200, easing: "cubic-bezier(.4,0,.2,1)", fill: "both" }
                );
            });
            trends.forEach(fg => {
                fg.animate(
                    [{ clipPath: "inset(0 100% 0 0)" }, { clipPath: "inset(0 0% 0 0)" }],
                    { duration: 4200, easing: "cubic-bezier(.4,0,.2,1)", fill: "both" }
                );
            });
        }));
    }

    async function renderUptimeOverview(id, containerId, renderedOnce) {
        const container = document.getElementById(containerId);
        const freshEntry = !renderedOnce.overview;
        const [dayData, weekData, monthData] = await Promise.all([
            requestJson(`/api/uptime/${encodeURIComponent(id)}?granularity=day&periods=30`),
            requestJson(`/api/uptime/${encodeURIComponent(id)}?granularity=week&periods=2`),
            requestJson(`/api/uptime/${encodeURIComponent(id)}?granularity=month&periods=2`),
        ]);
        const today = dayData.buckets[dayData.buckets.length-1];
        const thisWeek = weekData.buckets[weekData.buckets.length-1];
        const thisMonth = monthData.buckets[monthData.buckets.length-1];
        container.innerHTML = `
            <div class="uptime-summary-grid">
               <div class="uptime-summary-card"><div class="muted">今日稼动率</div><div class="uptime-summary-value">${today?today.uptime_pct:0}% ${renderUptimeDelta(today?.uptime_pct, dayData.comparable_previous_pct)}</div>${today?renderUptimeBar(today):""}</div>
                <div class="uptime-summary-card"><div class="muted">本周稼动率</div><div class="uptime-summary-value">${thisWeek?thisWeek.uptime_pct:0}% ${renderUptimeDelta(thisWeek?.uptime_pct, weekData.comparable_previous_pct)}</div>${thisWeek?renderUptimeBar(thisWeek):""}</div>
                <div class="uptime-summary-card"><div class="muted">本月稼动率</div><div class="uptime-summary-value">${thisMonth?thisMonth.uptime_pct:0}% ${renderUptimeDelta(thisMonth?.uptime_pct, monthData.comparable_previous_pct)}</div>${thisMonth?renderUptimeBar(thisMonth):""}</div>
            </div>
            <article class="detail-card">
                <div class="detail-header"><div class="detail-title">近30日稼动率趋势</div>
                    <div class="uptime-legend"><span><i class="dot active"></i>生产</span><span><i class="dot standby"></i>待机</span><span><i class="dot off"></i>关机</span></div>
                </div>
                ${renderUptimeTrendChart(dayData.buckets, `${containerId}-trend-wrap`, "设备稼动率")}
            </article>`;
        setTrendWrapSeries(`${containerId}-trend-wrap`, [{ label: "设备稼动率", color: "#19b58a", buckets: dayData.buckets }]);
        attachTrendWrapHover(`${containerId}-trend-wrap`);
        if (freshEntry) playUtilEntranceAnimation(container);
        renderedOnce.overview = true;
    }

    async function renderUptimeDaily(id, containerId, renderedOnce) {
        const container = document.getElementById(containerId);
        const freshEntry = !renderedOnce.daily;
        const data = await requestJson(`/api/uptime/${encodeURIComponent(id)}?granularity=day&periods=30`);
        container.innerHTML = `
            <article class="detail-card">
                <div class="detail-header"><div class="detail-title">日稼动率趋势（近30日）</div></div>
                ${renderUptimeTrendChart(data.buckets, `${containerId}-trend-wrap`, "设备稼动率")}
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
        setTrendWrapSeries(`${containerId}-trend-wrap`, [{ label: "设备稼动率", color: "#19b58a", buckets: data.buckets }]);
        attachTrendWrapHover(`${containerId}-trend-wrap`);
        container.querySelectorAll(".uptime-bucket-row").forEach(row=>{
            row.addEventListener("click",()=>openDayDetail(id,row.dataset.date));
        });
        if (freshEntry) playUtilEntranceAnimation(container);
        renderedOnce.daily = true;
    }

    async function renderUptimeMonthly(id, containerId, renderedOnce) {
        const container = document.getElementById(containerId);
        const freshEntry = !renderedOnce.monthly;
        const data = await requestJson(`/api/uptime/${encodeURIComponent(id)}?granularity=month&periods=12`);
        container.innerHTML = `
            <article class="detail-card">
                <div class="detail-header"><div class="detail-title">月稼动率趋势（近12个月）</div></div>
                ${renderUptimeTrendChart(data.buckets, `${containerId}-trend-wrap`, "设备稼动率")}
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
        setTrendWrapSeries(`${containerId}-trend-wrap`, [{ label: "设备稼动率", color: "#19b58a", buckets: data.buckets }]);
        attachTrendWrapHover(`${containerId}-trend-wrap`);
        if (freshEntry) playUtilEntranceAnimation(container);
        renderedOnce.monthly = true;
    }

    async function loadUtilization() {
        await renderUtilizationOverviewAll("util-tab-overview", utilRenderedOnce);
    }

    // Device-detail 利用率 tab: same renderers, but always scoped to
    // whichever device's detail page is currently open (detailDeviceId),
    // never the standalone page's #device-select.
    async function loadDetailUptime(id, tab) {
        if(!id) return;
        if(tab==="overview") await renderUptimeOverview(id, "detail-util-tab-overview", detailUtilRenderedOnce);
        else if(tab==="daily") await renderUptimeDaily(id, "detail-util-tab-daily", detailUtilRenderedOnce);
        else if(tab==="monthly") await renderUptimeMonthly(id, "detail-util-tab-monthly", detailUtilRenderedOnce);
    }

    function switchDetailUtilTab(tab) {
        activeDetailUtilTab = tab;
        detailUtilRenderedOnce[tab] = false;
        collapseUtilAnimatables(document.getElementById(`detail-util-tab-${tab}`));
        document.querySelectorAll("#detail-tab-uptime .detail-util-tab-button").forEach(button => button.classList.toggle("active", button.dataset.detailUtilTab === tab));
        document.querySelectorAll("#detail-tab-uptime .detail-uptime-panel").forEach(panel => panel.classList.toggle("hidden", panel.id !== `detail-util-tab-${tab}`));
        loadDetailUptime(detailDeviceId, tab);
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
            ? `<table><thead><tr><th></th><th>时间</th><th>设备编号</th><th>变量</th><th>原值</th><th>新值</th><th>模数</th></tr></thead><tbody>${rows.map(r=>`<tr class="changelog-row" data-id="${r.id}"><td>${favoriteStarButtonHtml(r.id)}</td><td>${formatTime(r.data_time||r.detected_at)}</td><td>${escapeHtml(r.device_id)}</td><td>${escapeHtml(r.label)}</td><td>${showValue(r.previous_value)}</td><td class="changelog-new-value">${showValue(r.new_value)}</td><td>${cycleCell(r)}</td></tr>`).join("")}</tbody></table>`
            : '<div class="empty">没有符合筛选条件的变更记录</div>';
        table.querySelectorAll(".changelog-row").forEach(row=>row.addEventListener("click",event=>{
            if(event.target.closest(".favorite-star-button")) return;
            openChangelogDetail(row.dataset.id);
        }));
        table.querySelectorAll(".favorite-star-button").forEach(button=>button.addEventListener("click",event=>{
            event.stopPropagation();
            openFavoriteSaveDialog(button.dataset.changelogId);
        }));
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
        if (!resultsEl) return;
        resultsEl.innerHTML = rows.length
            ? `<table><thead><tr><th></th><th>时间</th><th>变量</th><th>原值</th><th>新值</th><th>模数</th></tr></thead><tbody>${rows.map(r=>`<tr class="changelog-row" data-id="${r.id}" data-parameter="${escapeHtml(r.parameter_id)}" data-previous="${escapeHtml(r.previous_value??"")}" data-new="${escapeHtml(r.new_value??"")}"><td>${favoriteStarButtonHtml(r.id)}</td><td>${formatTime(r.data_time||r.detected_at)}</td><td>${escapeHtml(r.label)}</td><td>${showValue(r.previous_value)}</td><td class="changelog-new-value">${showValue(r.new_value)}</td><td>${cycleCell(r)}</td></tr>`).join("")}</tbody></table>`
            : '<div class="empty">没有符合筛选条件的变更记录</div>';
        resultsEl.querySelectorAll(".changelog-row").forEach(row => {
            row.addEventListener("click", event => {
                if (event.target.closest(".favorite-star-button")) return;
                highlightParameter = {
                    parameter_id: row.dataset.parameter,
                    previous_value: row.dataset.previous,
                    new_value: row.dataset.new,
                };
                highlightApplied = false;
                switchDetailTab("tech");
            });
        });
        resultsEl.querySelectorAll(".favorite-star-button").forEach(button => button.addEventListener("click", event => {
            event.stopPropagation();
            openFavoriteSaveDialog(button.dataset.changelogId);
        }));
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

    // ---- 收藏 (favorites) --------------------------------------------
    // A favorite is a full 工艺参数 snapshot captured from a 变更记录 row
    // at the moment it happened (see POST /api/changelog/{id}/favorite),
    // saved against a Mold + Machine Type -- same scope as 高级工艺参数.

    function favoriteStarButtonHtml(changelogId) {
        return `<button type="button" class="favorite-star-button" data-changelog-id="${changelogId}" title="收藏该时刻的工艺参数快照">☆</button>`;
    }

    let favoriteSaveChangelogId = null;

    async function openFavoriteSaveDialog(changelogId) {
        favoriteSaveChangelogId = changelogId;
        document.getElementById("favorite-save-name").value = "";
        document.getElementById("favorite-save-status").textContent = "";

        const moldSelect = document.getElementById("favorite-save-mold-select");
        const list = await requestJson("/api/molds");
        const active = list.filter(m => m.is_active);
        moldSelect.innerHTML = active.map(m => `<option value="${m.id}">${escapeHtml(m.mold_code)} · ${escapeHtml(m.mold_name)}</option>`).join("");
        if (active.length) await populateFavoriteMachineTypeSelect(active[0].id);

        document.getElementById("favorite-save-dialog").showModal();
    }

    async function populateFavoriteMachineTypeSelect(moldId) {
        const select = document.getElementById("favorite-save-machine-type-select");
        select.innerHTML = '<option value="">正在读取机型……</option>';
        try {
            const types = await loadMachineTypesFor(moldId);
            select.innerHTML = types.length
                ? types.map(mt => `<option value="${mt.id}">${escapeHtml(mt.machine_type)}${mt.is_main ? "（主要）" : ""}</option>`).join("")
                : '<option value="">该模具尚未配置机型</option>';
        } catch (error) {
            select.innerHTML = `<option value="">读取失败：${escapeHtml(error.message)}</option>`;
        }
    }

    async function submitFavoriteSave(overwrite) {
        const machineTypeId = document.getElementById("favorite-save-machine-type-select").value;
        const name = document.getElementById("favorite-save-name").value.trim();
        const statusEl = document.getElementById("favorite-save-status");
        if (!machineTypeId) { statusEl.textContent = "请选择机型"; return; }
        if (!name) { statusEl.textContent = "请输入收藏名称"; return; }
        try {
            const response = await fetch(`/api/changelog/${encodeURIComponent(favoriteSaveChangelogId)}/favorite`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ machine_type_id: Number(machineTypeId), name, overwrite }),
            });
            if (response.status === 409) {
                const body = await response.json().catch(() => ({}));
                const message = (body.detail && body.detail.message) || "该名称已存在，是否覆盖？";
                if (confirm(message)) { await submitFavoriteSave(true); return; }
                return;
            }
            const body = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error((body.detail && body.detail.message) || body.detail || `HTTP ${response.status}`);
            document.getElementById("favorite-save-dialog").close();
            alert(body.unchanged ? body.message : "收藏成功");
        } catch (error) {
            statusEl.textContent = error.message;
        }
    }
    document.getElementById("favorite-save-confirm").addEventListener("click", () => submitFavoriteSave(false));

    // ---- Favorites list + viewer (opened from the 机型 dialog) --------

    let favoritesListMachineTypeId = null;

    async function openFavoritesListDialog(machineTypeId, machineTypeName) {
        favoritesListMachineTypeId = machineTypeId;
        document.getElementById("favorites-list-title").textContent = machineTypeName;
        const body = document.getElementById("favorites-list-body");
        body.innerHTML = '<div class="empty">正在读取……</div>';
        document.getElementById("favorites-list-dialog").showModal();
        await refreshFavoritesList();
    }

    // Backend already returns favorites ordered named-first (newest first),
    // then auto-backups (see apply_favorite_to_schematic) also newest
    // first -- this just renders that order and drops in a one-time
    // divider + muted styling at the boundary so the grouping is visible,
    // not just implied by position in the list.
    function favoriteListRowHtml(f, readOnly) {
        const backupBadge = f.is_backup ? '<span class="badge offline" style="margin-left:8px;font-size:10.5px;">自动备份</span>' : "";
        return `<div class="detail-card favorite-list-row${f.is_backup ? " favorite-list-row-backup" : ""}" data-id="${f.id}" style="margin-bottom:0;cursor:pointer;display:flex;align-items:center;justify-content:space-between;gap:10px;${f.is_backup ? "opacity:.8;" : ""}">
            <div>
                <strong>${escapeHtml(f.name)}</strong>${backupBadge}
                <div class="muted" style="font-size:12px;margin-top:3px;">设备 ${escapeHtml(f.device_id)} · 采集于 ${formatTime(f.captured_data_time)} · 更新于 ${formatTime(f.updated_at)}</div>
            </div>
            <div class="actions" style="margin:0;">
                <button type="button" class="secondary-button favorite-apply-button" data-id="${f.id}" ${readOnly ? "disabled" : ""}>应用到当前参数</button>
                <button type="button" class="danger-button favorite-delete-button" data-id="${f.id}" ${readOnly ? "disabled" : ""}>删除</button>
            </div>
        </div>`;
    }

    async function refreshFavoritesList() {
        const body = document.getElementById("favorites-list-body");
        try {
            const favorites = await requestJson(`/api/molds/${encodeURIComponent(editMoldId)}/machine-types/${encodeURIComponent(favoritesListMachineTypeId)}/favorites`);
            const readOnly = currentUser.role === "viewer";

            if (!favorites.length) {
                body.innerHTML = '<div class="empty">该机型尚未保存任何收藏</div>';
            } else {
                const firstBackupIndex = favorites.findIndex(f => f.is_backup);
                const rowsHtml = favorites.map((f, i) => {
                    // A single divider right before the first backup row --
                    // only rendered when the list actually has both named
                    // favorites and backups, so a list of only one kind
                    // never shows a pointless lone divider.
                    const divider = (i === firstBackupIndex && firstBackupIndex > 0)
                        ? '<div class="favorite-list-divider muted" style="font-size:11.5px;padding:6px 2px 2px;">早期版本 / 自动备份</div>'
                        : "";
                    return divider + favoriteListRowHtml(f, readOnly);
                }).join("");
                body.innerHTML = rowsHtml;
            }

            body.querySelectorAll(".favorite-list-row").forEach(row => row.addEventListener("click", event => {
                if (event.target.closest("button")) return;
                openFavoriteViewDialog(Number(row.dataset.id));
            }));
            body.querySelectorAll(".favorite-delete-button").forEach(button => button.addEventListener("click", async event => {
                event.stopPropagation();
                if (!confirm("确认删除该收藏？此操作不可恢复。")) return;
                try {
                    await requestJson(`/api/favorites/${encodeURIComponent(button.dataset.id)}`, { method: "DELETE" });
                    await refreshFavoritesList();
                } catch (error) { alert(error.message); }
            }));
            body.querySelectorAll(".favorite-apply-button").forEach(button => button.addEventListener("click", async event => {
                event.stopPropagation();
                if (!confirm("确认将该收藏应用为当前机型的高级工艺参数？\n如当前已设置参数，将自动备份为一份带日期的新收藏后再覆盖，此操作不可撤销。")) return;
                try {
                    const result = await requestJson(
                        `/api/molds/${encodeURIComponent(editMoldId)}/machine-types/${encodeURIComponent(favoritesListMachineTypeId)}/favorites/${encodeURIComponent(button.dataset.id)}/apply`,
                        { method: "POST" }
                    );
                    moldAdvancedLoaded = false; // force the 高级参数 dialog to re-fetch next time it's opened
                    await refreshFavoritesList();
                    alert(result.unchanged ? result.message : (result.backed_up ? "已应用，原参数已自动备份为一份新收藏" : "已应用"));
                } catch (error) { alert(error.message); }
            }));
        } catch (error) {
            body.innerHTML = `<div class="empty">读取失败：${escapeHtml(error.message)}</div>`;
        }
    }
    document.getElementById("favorites-list-close").addEventListener("click", () => document.getElementById("favorites-list-dialog").close());

    let favoriteViewId = null;

    async function openFavoriteViewDialog(favoriteId) {
        favoriteViewId = favoriteId;
        document.getElementById("favorite-view-title").textContent = "";
        document.getElementById("favorite-view-meta").textContent = "正在读取……";
        document.getElementById("favorite-view-groups").innerHTML = "";
        document.getElementById("favorite-view-dialog").showModal();
        try {
            const favorite = await requestJson(`/api/favorites/${encodeURIComponent(favoriteId)}`);
            document.getElementById("favorite-view-title").textContent = favorite.name;
            document.getElementById("favorite-view-meta").textContent =
                `设备 ${favorite.device_id} · 采集于 ${formatTime(favorite.captured_data_time)}`;

            const paramById = new Map(favorite.parameters.map(p => [p.parameter_id, p]));
            const usedTags = new Set();
            const blocksHtml = PARAMETER_GRID_BLOCKS.map(block => techBlockTableHtml(block, paramById, usedTags)).join("");
            const leftoverHtml = techLeftoverBlocksHtml(favorite.parameters, usedTags);
            document.getElementById("favorite-view-groups").innerHTML = `<div class="excel-sections-wrap">${blocksHtml}${leftoverHtml}</div>`;
        } catch (error) {
            document.getElementById("favorite-view-meta").textContent = `读取失败：${error.message}`;
        }
    }
    document.getElementById("favorite-view-close").addEventListener("click", () => document.getElementById("favorite-view-dialog").close());

    // Optional: only wired up if the corresponding button exists in
    // index.html (id="favorite-view-apply") -- lets a favorite be applied
    // straight from its detail viewer, same action as the "应用到当前参数"
    // button in the favorites list.
    document.getElementById("favorite-view-apply")?.addEventListener("click", async () => {
        if (!favoriteViewId || !favoritesListMachineTypeId) return;
        if (!confirm("确认将该收藏应用为当前机型的高级工艺参数？\n如当前已设置参数，将自动备份为一份带日期的新收藏后再覆盖，此操作不可撤销。")) return;
        try {
            const result = await requestJson(
                `/api/molds/${encodeURIComponent(editMoldId)}/machine-types/${encodeURIComponent(favoritesListMachineTypeId)}/favorites/${encodeURIComponent(favoriteViewId)}/apply`,
                { method: "POST" }
            );
            moldAdvancedLoaded = false;
            document.getElementById("favorite-view-dialog").close();
            alert(result.unchanged ? result.message : (result.backed_up ? "已应用，原参数已自动备份为一份新收藏" : "已应用"));
        } catch (error) { alert(error.message); }
    });

    // ---- 预警通知 (warnings) ----
    // A warning is an unacknowledged dbo.tech_parameter_changelog row (see
    // GET /api/warnings). Clicking a toast or a row in the 预警通知 tab
    // redirects to 参数变更记录 / the highlighted parameter, matching how
    // changelog rows already behave -- warnings are just "changelog entries
    // you haven't dismissed yet", not a separate record type.

    // A "parameter" warning is an unacknowledged dbo.tech_parameter_changelog
    // row; a "cleaning" warning is an unacknowledged dbo.cleaning_alerts row
    // (a device that's run continuously past its mold's cleaning threshold
    // -- see _raise_cleaning_alert_if_needed in mqtt_monitor.py). GET
    // /api/warnings merges both into one list tagged with `warning_type`,
    // sorted newest-first, so they share this one badge/toast/table.
    function warningKey(w) { return `${w.warning_type}-${w.id}`; }

    function showToast(warning) {
        const container=document.getElementById("toast-container");
        if(!container) return;
        const toast=document.createElement("div");
        toast.className="toast";
        if(warning.warning_type==="cleaning"){
            const hours=(warning.threshold_minutes/60).toFixed(1);
            toast.innerHTML=`
                <div class="toast-icon"></div>
                <div class="toast-body">
                    <div class="toast-title">清洗提醒：设备 ${escapeHtml(warning.device_id)}</div>
                    <div class="toast-detail">${escapeHtml(warning.mold_code||"")} 已连续生产约 ${formatDurationMinutes(warning.elapsed_minutes)}，超过清洗周期（${hours} 小时）</div>
                </div>
                <button class="toast-close" type="button" aria-label="关闭">✕</button>`;
        } else if(warning.warning_type==="output"){
            toast.innerHTML=`
                <div class="toast-icon"></div>
                <div class="toast-body">
                    <div class="toast-title">产量超限：设备 ${escapeHtml(warning.device_id)}</div>
                    <div class="toast-detail">${escapeHtml(warning.mold_code||"")} 已生产 ${showValue(warning.total_output)} 模，超过设定上限 ${showValue(warning.max_output)} 模</div>
                </div>
                <button class="toast-close" type="button" aria-label="关闭">✕</button>`;
        } else if(warning.warning_type==="auto_assign"){
            const pct=warning.match_score!=null?Math.round(warning.match_score*1000)/10:null;
            toast.innerHTML=`
                <div class="toast-icon"></div>
                <div class="toast-body">
                    <div class="toast-title">系统自动识别装机：设备 ${escapeHtml(warning.device_id)}</div>
                    <div class="toast-detail">检测到批量参数变更，已自动装机 ${escapeHtml(warning.mold_code||"")} · ${escapeHtml(warning.matched_machine_type_name||"")}${pct!=null?`（匹配度 ${pct}%）`:""}${warning.machine_type_mismatch?"　⚠ 机型不一致，请核对":""}</div>
                </div>
                <button class="toast-close" type="button" aria-label="关闭">✕</button>`;
        } else if(warning.warning_type==="unrecognized"){
            toast.innerHTML=`
                <div class="toast-icon"></div>
                <div class="toast-body">
                    <div class="toast-title">未识别的批量参数变更：设备 ${escapeHtml(warning.device_id)}</div>
                    <div class="toast-detail">检测到 ${showValue(warning.tags_changed_count)} 项参数同时变更，但未匹配到任何已有模具，可能需要在模具管理中录入</div>
                </div>
                <button class="toast-close" type="button" aria-label="关闭">✕</button>`;
        } else {
            toast.innerHTML=`
                <div class="toast-icon">⚠</div>
                <div class="toast-body">
                    <div class="toast-title">参数变更：设备 ${escapeHtml(warning.device_id)}</div>
                    <div class="toast-detail">${escapeHtml(warning.label)}　${showValue(warning.previous_value)} → ${showValue(warning.new_value)}</div>
                </div>
                <button class="toast-close" type="button" aria-label="关闭">✕</button>`;
        }
        toast.addEventListener("click",event=>{
            if(event.target.closest(".toast-close")) return;
            switchPage("warnings");
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

    async function pollWarnings() {
        try {
            const rows=await requestJson("/api/warnings");
            const badge=document.getElementById("warnings-badge");
            if(badge){
                if(rows.length>0){ badge.textContent=rows.length>99?"99+":rows.length; badge.classList.remove("hidden"); }
                else badge.classList.add("hidden");
            }
            if(!warningsInitialized){
                rows.forEach(r=>seenWarningIds.add(warningKey(r)));
                warningsInitialized=true;
                if(currentPage==="warnings") await loadWarnings();
                return;
            }
            const currentKeys = new Set(rows.map(warningKey));
            const newOnes = rows.filter(r=>!seenWarningIds.has(warningKey(r)));
            const removedKeys = [...seenWarningIds].filter(key=>!currentKeys.has(key));

            newOnes.forEach(r=>{ seenWarningIds.add(warningKey(r)); showToast(r); });
            removedKeys.forEach(key=>seenWarningIds.delete(key));

            if(currentPage==="warnings" && (newOnes.length || removedKeys.length)) await loadWarnings();
        } catch(error) { /* transient network errors shouldn't spam toasts */ }
    }

    function renderWarningRow(r, readOnly) {
        if(r.warning_type==="cleaning"){
            const hours=(r.threshold_minutes/60).toFixed(1);
            return `<tr class="warning-row" data-id="${r.id}" data-warning-type="cleaning" data-device="${escapeHtml(r.device_id)}">
                <td>${formatTime(r.detected_at)}</td>
                <td>${escapeHtml(r.device_id)}</td>
                <td> ${escapeHtml(r.mold_code||"")} 超过清洗周期</td>
                <td>已运行 ${formatDurationMinutes(r.elapsed_minutes)}</td>
                <td class="changelog-new-value">周期 ${hours} 小时</td>
                <td>${readOnly?"":`<button class="secondary-button warning-clear-button" data-id="${r.id}" data-warning-type="cleaning" type="button">清除</button>`}</td>
            </tr>`;
        }
        if(r.warning_type==="output"){
            return `<tr class="warning-row" data-id="${r.id}" data-warning-type="output" data-mold="${r.mold_id}">
                <td>${formatTime(r.detected_at)}</td>
                <td>${escapeHtml(r.device_id)}</td>
                <td>${escapeHtml(r.mold_code||"")} 超过最大产量</td>
                <td>已生产 ${showValue(r.total_output)} 模</td>
                <td class="changelog-new-value">上限 ${showValue(r.max_output)} 模</td>
                <td>${readOnly?"":`<button class="secondary-button warning-clear-button" data-id="${r.id}" data-warning-type="output" type="button">清除</button>`}</td>
            </tr>`;
        }
        if(r.warning_type==="auto_assign"){
            const pct=r.match_score!=null?Math.round(r.match_score*1000)/10:null;
            const mismatch=r.machine_type_mismatch?`　⚠ 机型不一致（设备：${escapeHtml(r.device_machine_type||"未设置")} / 规格表：${escapeHtml(r.sheet_machine_type||"未命名")}）`:"";
            return `<tr class="warning-row" data-id="${r.id}" data-warning-type="auto_assign" data-device="${escapeHtml(r.device_id)}" data-mold="${r.matched_mold_id??""}">
                <td>${formatTime(r.detected_at)}</td>
                <td>${escapeHtml(r.device_id)}</td>
                <td>系统自动识别装机（${showValue(r.tags_changed_count)} 项参数变更）</td>
                <td>${escapeHtml(r.mold_code||"")} · ${escapeHtml(r.matched_machine_type_name||"")}</td>
                <td class="changelog-new-value">匹配度 ${pct!=null?`${pct}%`:"--"}${mismatch}</td>
                <td>${readOnly?"":`<button class="secondary-button warning-clear-button" data-id="${r.id}" data-warning-type="auto_assign" type="button">清除</button>`}</td>
            </tr>`;
        }
        if(r.warning_type==="unrecognized"){
            return `<tr class="warning-row" data-id="${r.id}" data-warning-type="unrecognized" data-device="${escapeHtml(r.device_id)}">
                <td>${formatTime(r.detected_at)}</td>
                <td>${escapeHtml(r.device_id)}</td>
                <td>检测到批量参数变更，未匹配到已有模具</td>
                <td>${showValue(r.tags_changed_count)} 项参数同时变更</td>
                <td class="changelog-new-value">建议前往模具管理录入</td>
                <td>${readOnly?"":`<button class="secondary-button warning-clear-button" data-id="${r.id}" data-warning-type="unrecognized" type="button">清除</button>`}</td>
            </tr>`;
        }
        return `<tr class="warning-row" data-id="${r.id}" data-warning-type="parameter"><td>${formatTime(r.data_time||r.detected_at)}</td><td>${escapeHtml(r.device_id)}</td><td>${escapeHtml(r.label)}</td><td>${showValue(r.previous_value)}</td><td class="changelog-new-value">${showValue(r.new_value)}</td><td>${readOnly?"":`<button class="secondary-button warning-clear-button" data-id="${r.id}" data-warning-type="parameter" type="button">清除</button>`}</td></tr>`;
    }

    async function loadWarnings() {
        const rows=await requestJson("/api/warnings");
        document.getElementById("warnings-summary").textContent=`共 ${rows.length} 条待处理`;
        const readOnly=currentUser.role==="viewer";
        const table=document.getElementById("warnings-table");
        table.innerHTML=rows.length?`<table><thead><tr><th>时间</th><th>设备编号</th><th>变量</th><th>原值</th><th>新值</th><th></th></tr></thead><tbody>${rows.map(r=>renderWarningRow(r,readOnly)).join("")}</tbody></table>`:'<div class="empty">暂无预警</div>';
        table.querySelectorAll(".warning-row").forEach(row=>{
            row.addEventListener("click",event=>{
                if(event.target.closest(".warning-clear-button")) return;
                if(row.dataset.warningType==="cleaning") openDeviceDetail(row.dataset.device,{tab:"uptime"});
                else if(row.dataset.warningType==="output") openMoldEdit(Number(row.dataset.mold));
                else if(row.dataset.warningType==="auto_assign") openDeviceDetail(row.dataset.device);
                else if(row.dataset.warningType==="unrecognized") openDeviceDetail(row.dataset.device,{tab:"tech"});
                else openChangelogDetail(row.dataset.id);
            });
        });
        table.querySelectorAll(".warning-clear-button").forEach(button=>{
            button.addEventListener("click",async event=>{
                event.stopPropagation();
                try {
                    const endpoint = button.dataset.warningType==="cleaning"
                        ? `/api/warnings/cleaning/${encodeURIComponent(button.dataset.id)}/clear`
                        : button.dataset.warningType==="output"
                        ? `/api/warnings/output/${encodeURIComponent(button.dataset.id)}/clear`
                        : (button.dataset.warningType==="auto_assign" || button.dataset.warningType==="unrecognized")
                        ? `/api/warnings/detection/${encodeURIComponent(button.dataset.id)}/clear`
                        : `/api/warnings/${encodeURIComponent(button.dataset.id)}/clear`;
                    await requestJson(endpoint,{method:"POST"});
                    seenWarningIds.delete(`${button.dataset.warningType}-${button.dataset.id}`);
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
        if(activeDetailTab==="uptime") await loadDetailUptime(detailDeviceId, activeDetailUtilTab);
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
        // Reset the nested 利用率 sub-tab back to 总览 for every device
        // open, so a different machine never inherits the last one's
        // 日统计/月统计 selection, and force a fresh entrance animation.
        activeDetailUtilTab = "overview";
        detailUtilRenderedOnce.overview = false;
        detailUtilRenderedOnce.daily = false;
        detailUtilRenderedOnce.monthly = false;
        document.querySelectorAll("#detail-tab-uptime .detail-uptime-panel").forEach(panel=>panel.classList.toggle("hidden",panel.id!=="detail-util-tab-overview"));
        document.querySelectorAll(".tab-button").forEach(button=>button.classList.toggle("active",button.dataset.tab===activeDetailTab));
        document.querySelectorAll("#device-detail-page .tab-content").forEach(content=>content.classList.toggle("hidden",content.id!==`detail-tab-${activeDetailTab}`));

        // The generic .tab-button toggle above also touches the nested
        // 利用率 sub-tab buttons (they share the "tab-button" class for
        // styling) and clears their "active" state since their
        // data-detail-util-tab attribute never matches activeDetailTab --
        // reapply it explicitly here.
        document.querySelectorAll("#detail-tab-uptime .detail-util-tab-button").forEach(button=>button.classList.toggle("active",button.dataset.detailUtilTab==="overview"));
        await switchPage("device-detail");
        loadDeviceMoldCard(deviceId);
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
        document.querySelectorAll("#device-detail-page .tab-content").forEach(content=>content.classList.toggle("hidden",content.id!==`detail-tab-${tab}`));
        document.querySelectorAll("#detail-tab-uptime .detail-util-tab-button").forEach(button=>button.classList.toggle("active",button.dataset.detailUtilTab===activeDetailUtilTab));
        document.getElementById("page-title").textContent=`设备 ${detailDeviceId} · ${detailTabTitles[tab]}`;
        scheduleAutoRefresh();
    }


    async function switchPage(page) {
        currentPage=page;
        if(page==="device-detail") {
            document.getElementById("page-title").textContent=`设备 ${detailDeviceId} · ${detailTabTitles[activeDetailTab]}`;
            document.getElementById("detail-device-title").textContent=`设备 ${detailDeviceId}`;
            try { await loadActiveDetailTab(); } catch(error) { /* handled by refreshPage below */ }
        } else {
            document.getElementById("page-title").textContent=pageTitles[page];
        }
        if(page==="utilization") {
            utilRenderedOnce.overview = false;
            collapseUtilAnimatables(document.getElementById("util-tab-overview"));
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
    // Scoped to the outer tab bar only (direct child of #device-detail-page):
    // the nested 利用率 sub-tab bar inside #detail-tab-uptime also uses the
    // "tab-button" class for shared styling, but must only trigger
    // switchDetailUtilTab, not this top-level switchDetailTab.
    document.querySelectorAll("#device-detail-page > .detail-tabs > .tab-button").forEach(button=>button.addEventListener("click",()=>switchDetailTab(button.dataset.tab)));
    document.getElementById("device-select").addEventListener("change",refreshPage);
    document.querySelectorAll(".status-filter").forEach(input=>input.addEventListener("change",()=>{dashboardPage=1;renderDashboard();}));
    document.getElementById("filter-location").addEventListener("change",()=>{dashboardPage=1;renderDashboard();});
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
    document.querySelectorAll(".detail-util-tab-button").forEach(button => button.addEventListener("click", () => switchDetailUtilTab(button.dataset.detailUtilTab)));
    const passwordDialog=document.getElementById("password-dialog");
    document.getElementById("password-button").addEventListener("click",()=>passwordDialog.showModal());
    document.getElementById("password-cancel").addEventListener("click",()=>passwordDialog.close());
    document.getElementById("password-form").addEventListener("submit",async event=>{event.preventDefault();const f=new FormData(event.target);try{await requestJson("/api/auth/change-password",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({current_password:f.get("current_password"),new_password:f.get("new_password")})});event.target.reset();passwordDialog.close();alert("密码修改成功");}catch(error){alert(error.message);}});
        document.getElementById("device-grid").addEventListener("click", event => {
        const editButton = event.target.closest(".device-type-edit-btn");
        if (editButton) {
            event.stopPropagation();
            editDeviceMachineType(editButton.dataset.device);
            return;
        }
        const card = event.target.closest(".device-card");
        if (card) openDeviceDetail(card.dataset.device);
    });

    async function editDeviceMachineType(deviceId) {
        if (currentUser.role === "viewer") return;
        const machine = dashboardMachines.find(m => m.device_id === deviceId);
        const current = machine ? (machine.machine_type || "") : "";
        const next = prompt(`设置设备 ${deviceId} 的机型：`, current);
        if (next === null) return;
        try {
            await requestJson(`/api/devices/${encodeURIComponent(deviceId)}/type`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ machine_type: next.trim() || null }),
            });
            await loadDashboard();
        } catch (error) { alert(error.message); }
    }
    
    let refreshChain = Promise.resolve();

    async function runRefreshOnce() {
        const status = document.getElementById("connection-status");
        try {
            if (currentPage === "dashboard") await loadDashboard();
            if (currentPage === "device-detail") await loadActiveDetailTab();
            if (currentPage === "molds") await loadMolds();
            if (currentPage === "changelog") await loadChangelog();
            if (currentPage === "warnings") await loadWarnings();
            if (currentPage === "utilization") await loadUtilization();
            status.className = "connection";
            status.textContent = `更新于 ${new Date().toLocaleTimeString()}`;
        } catch (error) {
            status.className = "connection error";
            status.textContent = `读取失败：${error.message}`;
        }
    }

    function refreshPage() {
        refreshChain = refreshChain.then(runRefreshOnce, runRefreshOnce);
        return refreshChain;
    }

    let autoRefreshTimer = null;
    function scheduleAutoRefresh() {
        if (autoRefreshTimer) clearTimeout(autoRefreshTimer);
        autoRefreshTimer = setTimeout(async () => {
            const onUptimeTab = currentPage === "device-detail" && activeDetailTab === "uptime";
            if ((currentPage === "dashboard" || currentPage === "device-detail" || currentPage === "molds") && !onUptimeTab) {
                await refreshPage();
            }
            scheduleAutoRefresh();
        }, 2000);
    }

    async function initialize(){try{await loadSession();await loadDevices();await refreshPage();await pollWarnings();}catch(error){document.getElementById("connection-status").textContent=error.message;}}
    initialize();
    scheduleAutoRefresh();
    setInterval(pollWarnings,5000);