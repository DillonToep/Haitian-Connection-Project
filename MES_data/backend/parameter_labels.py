"""Tag/label dictionary for raw MES parameter codes.

Source: haitian_data_labels_csv.xlsx (id / remark / scale / use) for the
Haitian (H-prefixed) machines, merged with Toshiba_Data_Names.csv for the
Toshiba (T-prefixed) machines (see machineImageForPrefix in app.js for the
H/T device-id convention).

- id: the raw tag code as stored in dbo.vw_machine_tech.parameter_id
      (and, for a subset, the underlying source of the realtime /
      SPC views's named columns).
- label: human readable Chinese name to show on the web app.
- use: whether this machine/line actually uses this tag. Tags with
       use=False are hidden from the web app.

NOTE: a handful of tags only exist on one machine family. Where a Haitian
and a Toshiba tag clearly represent the same concept under a different raw
code (e.g. Haitian's EEJET / 托模时间 vs Toshiba's EEFT / 顶出时间, or
Haitian's ASTS / 警报状态 vs Toshiba's wm / 警报), both codes are kept as
separate dictionary entries rather than merged, since dbo.vw_machine_tech
keys off the raw tag code as sent by each gateway. If the SPC/realtime SQL
views (vw_machine_spc / vw_machine_realtime, not part of this repo) pivot
on one specific code for a named column, the other family's equivalent tag
will need to be added to that view's mapping too.
"""
import re

PARAMETER_LABELS: dict[str, dict] = {
    'TS1': {"label": '温度设定1', "use": True},
    'TS2': {"label": '温度设定2', "use": True},
    'TS3': {"label": '温度设定3', "use": True},
    'TS4': {"label": '温度设定4', "use": True},
    'TS5': {"label": '温度设定5', "use": True},
    'TS6': {"label": '温度设定6', "use": True},
    'TS7': {"label": '温度设定7', "use": True},
    'TS8': {"label": '温度设定8', "use": False},
    'TS9': {"label": '温度设定9', "use": False},
    'TS10': {"label": '温度设定10', "use": False},
    'TS11': {"label": '温度设定11', "use": False},
    'TS12': {"label": '温度设定12', "use": False},
    'IS1': {"label": '注射位置1', "use": True},
    'IS2': {"label": '注射位置2', "use": True},
    'IS3': {"label": '注射位置3', "use": True},
    'IS4': {"label": '注射位置4', "use": True},
    'IS5': {"label": '注射位置5', "use": True},
    'IS6': {"label": '注射位置6', "use": False},
    'IP1': {"label": '注射压力1', "use": True},
    'IP2': {"label": '注射压力2', "use": True},
    'IP3': {"label": '注射压力3', "use": True},
    'IP4': {"label": '注射压力4', "use": True},
    'IP5': {"label": '注射压力5', "use": True},
    'IP6': {"label": '注射压力6', "use": True},
    'IV1': {"label": '注射速度1', "use": True},
    'IV2': {"label": '注射速度2', "use": True},
    'IV3': {"label": '注射速度3', "use": True},
    'IV4': {"label": '注射速度4', "use": True},
    'IV5': {"label": '注射速度5', "use": True},
    'IV6': {"label": '注射速度6', "use": True},
    'SIPM': {"label": '切保压模式0位置，1时间', "use": True},
    'SIPT': {"label": '切保压时间', "use": True},
    'SIPP': {"label": '切保压压力', "use": True},
    'SIPS': {"label": '切保压位置', "use": True},
    'PP1': {"label": '保压压力1', "use": True},
    'PP2': {"label": '保压压力2', "use": True},
    'PP3': {"label": '保压压力3', "use": True},
    'PP4': {"label": '保压压力4', "use": True},
    'PP5': {"label": '保压压力5', "use": True},
    'PP6': {"label": '保压压力6', "use": True},
    'PV1': {"label": '保压速度1', "use": True},
    'PV2': {"label": '保压速度2', "use": True},
    'PV3': {"label": '保压速度3', "use": True},
    'PV4': {"label": '保压速度4', "use": True},
    'PV5': {"label": '保压速度5', "use": True},
    'PV6': {"label": '保压速度6', "use": True},
    'PT1': {"label": '保压时间1', "use": True},
    'PT2': {"label": '保压时间2', "use": True},
    'PT3': {"label": '保压时间3', "use": True},
    'PT4': {"label": '保压时间4', "use": True},
    'PT5': {"label": '保压时间5', "use": True},
    'PT6': {"label": '保压时间6', "use": True},
    'SBS1': {"label": '射退1位置', "use": True},
    'SBT1': {"label": '射退1时间', "use": True},
    'SBV1': {"label": '射退1速度', "use": False},
    'SBP1': {"label": '射退1压力', "use": False},
    'PLV1': {"label": '储料速度1', "use": True},
    'PLV2': {"label": '储料速度2', "use": True},
    'PLV3': {"label": '储料速度3', "use": True},
    'PLV4': {"label": '储料速度4', "use": True},
    'PLV5': {"label": '储料速度5', "use": True},
    'PLP1': {"label": '储料压力1', "use": True},
    'PLP2': {"label": '储料压力2', "use": True},
    'PLP3': {"label": '储料压力3', "use": True},
    'PLP4': {"label": '储料压力4', "use": True},
    'PLP5': {"label": '储料压力5', "use": True},
    'PLBP1': {"label": '储料背压1', "use": True},
    'PLBP2': {"label": '储料背压2', "use": True},
    'PLBP3': {"label": '储料背压3', "use": True},
    'PLBP4': {"label": '储料背压4', "use": True},
    'PLBP5': {"label": '储料背压5', "use": True},
    'PLS1': {"label": '储料位置1', "use": True},
    'PLS2': {"label": '储料位置2', "use": True},
    'PLS3': {"label": '储料位置3', "use": True},
    'PLS4': {"label": '储料位置4', "use": True},
    'PLS5': {"label": '储料位置5', "use": True},
    'SBP2': {"label": '射退2压力', "use": True},
    'SBS2': {"label": '射退2位置', "use": True},
    'SBT2': {"label": '射退2时间', "use": True},
    'SBV2': {"label": '射退2速度', "use": True},
    'SBM2': {"label": '射退模式1冷却后0储料后', "use": True},
    'CTBFPL': {"label": '储前冷却', "use": True},
    'CT': {"label": '冷却时间', "use": True},
    'MCP1': {"label": '合模压力1', "use": True},
    'MCP2': {"label": '合模压力2', "use": True},
    'MCP3': {"label": '合模压力3', "use": True},
    'MCP4': {"label": '合模压力4', "use": True},
    'MCP5': {"label": '合模压力5', "use": True},
    'MCV1': {"label": '合模速度1', "use": True},
    'MCV2': {"label": '合模速度2', "use": True},
    'MCV3': {"label": '合模速度3', "use": True},
    'MCV4': {"label": '合模速度4', "use": True},
    'MCV5': {"label": '合模速度5', "use": True},
    'MCS1': {"label": '合模位置1', "use": True},
    'MCS2': {"label": '合模位置2', "use": True},
    'MCS3': {"label": '合模位置3', "use": True},
    'MCS4': {"label": '合模位置4', "use": True},
    'MCS5': {"label": '合模位置5', "use": True},
    'MOP1': {"label": '开模压力1', "use": True},
    'MOP2': {"label": '开模压力2', "use": True},
    'MOP3': {"label": '开模压力3', "use": True},
    'MOP4': {"label": '开模压力4', "use": True},
    'MOP5': {"label": '开模压力5', "use": True},
    'MOV1': {"label": '开模速度1', "use": True},
    'MOV2': {"label": '开模速度2', "use": True},
    'MOV3': {"label": '开模速度3', "use": True},
    'MOV4': {"label": '开模速度4', "use": True},
    'MOV5': {"label": '开模速度5', "use": True},
    'MOS1': {"label": '开模位置1', "use": True},
    'MOS2': {"label": '开模位置2', "use": True},
    'MOS3': {"label": '开模位置3', "use": True},
    'MOS4': {"label": '开模位置4', "use": True},
    'MOS5': {"label": '开模位置5', "use": True},
    'EJET': {"label": '顶针次数', "use": True},
    'EJEM': {"label": '顶针模式0不用1停留2定次3震动', "use": True},
    'EFDT': {"label": '顶进延迟', "use": True},
    'EFP1': {"label": '顶进压力1', "use": True},
    'EFP2': {"label": '顶进压力2', "use": True},
    'EFV1': {"label": '顶进速度1', "use": True},
    'EFV2': {"label": '顶进速度2', "use": True},
    'EFV3': {"label": '顶进速度3', "use": True},
    'EFS1': {"label": '顶进位置1', "use": True},
    'EFS2': {"label": '顶进位置2', "use": True},
    'EFS3': {"label": '顶进位置3', "use": True},
    'EBDT': {"label": '顶退延迟', "use": True},
    'EBP1': {"label": '顶退压力1', "use": True},
    'EBP2': {"label": '顶退压力2', "use": True},
    'EBV1': {"label": '顶退速度1', "use": True},
    'EBV2': {"label": '顶退速度2', "use": True},
    'EBS1': {"label": '顶退位置1', "use": True},
    'EBS2': {"label": '顶退位置2', "use": True},
    'BLT1': {"label": 'A组吹气动作时间', "use": True},
    'BLDT1': {"label": 'A组吹气延迟时间', "use": True},
    'BLS1': {"label": 'A组吹气起始位置', "use": True},
    'BLT2': {"label": 'B组吹气动作时间', "use": True},
    'BLDT2': {"label": 'B组吹气延迟时间', "use": True},
    'BLS2': {"label": 'B组吹气起始位置', "use": True},
    'CP1M': {"label": '中子1模式', "use": True},
    'CP2M': {"label": '中子2模式', "use": True},
    'CP3M': {"label": '中子3模式', "use": True},
    'CP4M': {"label": '中子4模式', "use": True},
    'CPI1S': {"label": '中子1进位置', "use": True},
    'CPI2S': {"label": '中子2进位置', "use": True},
    'CPI3S': {"label": '中子3进位置', "use": True},
    'CPI4S': {"label": '中子4进位置', "use": True},
    'CPI1P': {"label": '中子1进压力', "use": True},
    'CPI2P': {"label": '中子2进压力', "use": True},
    'CPI3P': {"label": '中子3进压力', "use": True},
    'CPI4P': {"label": '中子4进压力', "use": True},
    'CPI1V': {"label": '中子1进速度', "use": True},
    'CPI2V': {"label": '中子2进速度', "use": True},
    'CPI3V': {"label": '中子3进速度', "use": True},
    'CPI4V': {"label": '中子4进速度', "use": True},
    'CPI1T': {"label": '中子1进时间', "use": True},
    'CPI2T': {"label": '中子2进时间', "use": True},
    'CPI3T': {"label": '中子3进时间', "use": True},
    'CPI4T': {"label": '中子4进时间', "use": True},
    'CPO1S': {"label": '中子1退位置', "use": True},
    'CPO2S': {"label": '中子2退位置', "use": True},
    'CPO3S': {"label": '中子3退位置', "use": True},
    'CPO4S': {"label": '中子4退位置', "use": True},
    'CPO1P': {"label": '中子1退压力', "use": True},
    'CPO2P': {"label": '中子2退压力', "use": True},
    'CPO3P': {"label": '中子3退压力', "use": True},
    'CPO4P': {"label": '中子4退压力', "use": True},
    'CPO1V': {"label": '中子1退速度', "use": True},
    'CPO2V': {"label": '中子2退速度', "use": True},
    'CPO3V': {"label": '中子3退速度', "use": True},
    'CPO4V': {"label": '中子4退速度', "use": True},
    'CPO1T': {"label": '中子1退时间', "use": True},
    'CPO2T': {"label": '中子2退时间', "use": True},
    'CPO3T': {"label": '中子3退时间', "use": True},
    'CPO4T': {"label": '中子4退时间', "use": True},
    'CFP1': {"label": '座进压力1', "use": True},
    'CFP2': {"label": '座进压力2', "use": True},
    'CFV1': {"label": '座进速度1', "use": True},
    'CFV2': {"label": '座进速度2', "use": True},
    'CFS1': {"label": '座进位置1', "use": True},
    'CFS2': {"label": '座进位置2', "use": True},
    'CFT1': {"label": '座进时间', "use": True},
    'CFT2': {"label": '座进时间2', "use": False},
    'CBP1': {"label": '座退压力1', "use": True},
    'CBP2': {"label": '座退压力2', "use": False},
    'CBV1': {"label": '座退速度1', "use": True},
    'CBV2': {"label": '座退速度2', "use": False},
    'CBS1': {"label": '座退位置1', "use": True},
    'CBDT1': {"label": '座退延迟时间1', "use": True},
    'CBT1': {"label": '座退时间1', "use": True},
    'CYCN': {"label": '模数', "use": True},
    'PARTN': {"label": '产品数量', "use": True},
    'ECYCT': {"label": '周期时间', "use": True},
    'EISS': {"label": '射出起点', "use": True},
    'EIVM': {"label": '最大射速', "use": True},
    'EIPM': {"label": '最大射压', "use": True},
    'ESIPT': {"label": '转保压(注射)时间', "use": True},
    'ESIPP': {"label": '转保压压力', "use": True},
    'ESIPS': {"label": '转保压位置', "use": True},
    'EIPT': {"label": '射出保压时间', "use": True},
    'EIPSE': {"label": '射出终点位置', "use": True},
    'EIPSMIN': {"label": '最小射出位置', "use": True},
    'EPLST': {"label": '储料时间', "use": True},
    'EPLSPM': {"label": '最大储料压力', "use": True},
    'EPLTorque': {"label": '储料扭矩', "use": True},
    'EMOS': {"label": '开模位置', "use": False},
    'EFCHT': {"label": '取出时间', "use": True},
    'EMCT': {"label": '关模时间', "use": True},
    'EMCLP': {"label": '低压时间', "use": True},
    'EMCHP': {"label": '高压时间', "use": True},
    'EMOT': {"label": '开模时间', "use": True},
    'EEJET': {"label": '托模时间', "use": True},
    'EEFT': {"label": '顶出时间', "use": True},
    'ESB2T': {"label": '射退时间', "use": True},
    'ET1': {"label": '生产温度1', "use": True},
    'ET2': {"label": '生产温度2', "use": True},
    'ET3': {"label": '生产温度3', "use": True},
    'ET4': {"label": '生产温度4', "use": True},
    'ET5': {"label": '生产温度5', "use": True},
    'ET6': {"label": '生产温度6', "use": True},
    'ET7': {"label": '生产温度7', "use": True},
    'ET8': {"label": '生产温度8', "use": False},
    'ET9': {"label": '生产温度9', "use": False},
    'ET10': {"label": '生产温度10', "use": False},
    'ET11': {"label": '生产温度11', "use": False},
    'ET12': {"label": '生产温度12', "use": False},
    'EOT': {"label": '生产油温', "use": True},
    'OPM': {"label": '模式', "use": True},
    'STS': {"label": '生产状态', "use": True},
    'ASTS': {"label": '警报状态', "use": True},
    'wm': {"label": '警报', "use": True},
    'T1': {"label": '温度1', "use": True},
    'T2': {"label": '温度2', "use": True},
    'T3': {"label": '温度3', "use": True},
    'T4': {"label": '温度4', "use": True},
    'T5': {"label": '温度5', "use": True},
    'T6': {"label": '温度6', "use": True},
    'T7': {"label": '温度7', "use": True},
    'T8': {"label": '温度8', "use": False},
    'T9': {"label": '温度9', "use": False},
    'T10': {"label": '温度10', "use": False},
    'T11': {"label": '温度11', "use": False},
    'T12': {"label": '温度12', "use": False},
    'OT': {"label": '油温', "use": True},
}


# ---------------------------------------------------------------------------
# 实时状态编码 (OPM / STS / ASTS) -- these come from vw_machine_realtime as
# small integer codes and need a code -> Chinese label lookup, unlike
# PARAMETER_LABELS (工艺参数 tag -> name).
# ---------------------------------------------------------------------------

OPERATION_MODE_LABELS: dict[int, str] = {
    0: '手动',
    1: '半自动',
    2: '电眼自动',
    3: '时间自动',
    4: '调模使用',
}

MACHINE_STATUS_LABELS: dict[int, str] = {
    1: '待机',
    2: '生产',
}

ALARM_STATUS_LABELS: dict[int, str] = {
    0: '-',
    2: '安全门未关',
    3: '请开安全门',
    28: '中子未到定位',
    46: '请按安全确认键',
    50: '背面安全门未关',
    62: '请开安全门二',
    90: '电热马达未启动',
}


def label_status_code(mapping: dict[int, str], value) -> str | None:
    """Map a raw OPM/STS/ASTS integer code to its Chinese label. Unknown
    codes fail open (return the raw value as text) instead of disappearing,
    same philosophy as the unmapped-工艺参数-tag handling in devices.py."""
    if value is None:
        return None
    try:
        code = int(value)
    except (TypeError, ValueError):
        return str(value)
    return mapping.get(code, str(value))


def get_label(parameter_id: str) -> dict | None:
    """Return the label metadata for a raw parameter id, or None if unknown."""
    return PARAMETER_LABELS.get(parameter_id)


# ---------------------------------------------------------------------------
# Tags that should never be offered as a 高级工艺参数 target/tolerance row
# (mold-specific targets or the global defaults template). These aren't
# continuous measurements: STS/ASTS/wm are categorical status/alarm codes
# (STS legitimately alternates 1/2 during normal operation; ASTS and wm are
# alarm ids, not a severity scale) and CYCN/PARTN are monotonically
# increasing shot/part counters.
# A numeric tolerance check against any of them (see _exceeds_tolerance in
# mqtt_monitor.py) is either meaningless or guaranteed to misfire.
# ---------------------------------------------------------------------------
EXCLUDED_FROM_TARGETS: set[str] = {"STS", "ASTS", "wm", "CYCN", "PARTN"}


# Per-tag category overrides for parameters whose Chinese label doesn't
# contain any of the _CATEGORY_KEYWORDS substrings and would otherwise
# fall into the 其他参数 catch-all despite being ordinary numeric
# position/speed/pressure/time values.
CATEGORY_OVERRIDES: dict[str, str] = {
    "EISS": "位置参数",   # 射出起点 -- injection start position
    "EIPSMIN": "位置参数", # 最小射出位置 -- min injection position (Toshiba)
    "EIVM": "速度参数",   # 最大射速 -- max injection speed
    "EIPM": "压力参数",   # 最大射压 -- max injection pressure
    "CTBFPL": "时间参数", # 储前冷却 -- pre-storage cooling duration
    "PARTN": "其他参数",  # 产品数量 -- product count (Toshiba)
    "EPLTorque": "其他参数",  # 储料扭矩 -- plasticizing torque (Toshiba)
}


def categorize_tag(tag: str, label: str) -> str:
    """Like categorize(), but checks CATEGORY_OVERRIDES by raw tag code
    first -- for parameters whose label text doesn't contain a keyword
    categorize() can match on."""
    override = CATEGORY_OVERRIDES.get(tag)
    if override:
        return override
    return categorize(label)


_CATEGORY_KEYWORDS = [
    ("温度", "温度参数"),
    ("压力", "压力参数"),
    ("背压", "压力参数"),
    ("速度", "速度参数"),
    ("位置", "位置参数"),
    ("时间", "时间参数"),
    ("延迟", "时间参数"),
    ("模式", "模式设置"),
]

def base_name(label: str) -> str:
    """Strip digit runs from a label to get its grouping key -- mirrors the
    frontend's groupTechParameters() base-name logic in frontend/js/app.js,
    e.g. '注射压力1'/'注射压力2' both map to '注射压力'."""
    stripped = re.sub(r"\d+", "", label).strip()
    return stripped or label


def categorize(label: str) -> str:
    """Best-effort grouping of a parameter into a display category
    based on keywords in its Chinese label, so the tech-parameters
    page can render related settings together instead of one flat list.
    """
    for keyword, category in _CATEGORY_KEYWORDS:
        if keyword in label:
            return category
    return "其他参数"