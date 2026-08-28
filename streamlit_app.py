"""Streamlit front end for the MES data-management features.

This is a thin client on top of the existing FastAPI backend -- it never
talks to SQL Server directly, so every validation rule / tolerance check
/ FK constraint that already lives in backend/routers/*.py and
backend/security.py stays enforced in exactly one place.

Run with:
    streamlit run streamlit_app.py

Configure the backend location with an environment variable if it's not
running on localhost:8000:
    setx MES_API_BASE "http://192.168.1.9:8000"      (Windows, persistent)
    $env:MES_API_BASE = "http://192.168.1.9:8000"    (PowerShell, this session)
"""
import io
import os

import pandas as pd
import requests
import streamlit as st

API_BASE = os.environ.get("MES_API_BASE", "http://127.0.0.1:8000")

st.set_page_config(page_title="乔丰 MES · Streamlit", layout="wide")


# --------------------------------------------------------------------- #
# Session / auth
# --------------------------------------------------------------------- #

def get_session() -> requests.Session:
    if "http_session" not in st.session_state:
        st.session_state.http_session = requests.Session()
    return st.session_state.http_session


def api(method: str, path: str, **kwargs):
    """Wraps requests.<method> against the FastAPI backend, using the
    session's login cookie. Raises a RuntimeError with the backend's own
    `detail` message on failure, so callers can just show str(error)."""
    session = get_session()
    response = session.request(method, f"{API_BASE}{path}", timeout=30, **kwargs)
    if response.status_code == 401:
        st.session_state.pop("user", None)
        raise RuntimeError("登录已失效，请重新登录")
    if not response.ok:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        raise RuntimeError(str(detail))
    if response.headers.get("content-type", "").startswith("application/json"):
        return response.json()
    return response


def login_form():
    st.title("乔丰 MES 登录")
    with st.form("login"):
        username = st.text_input("用户名")
        password = st.text_input("密码", type="password")
        submitted = st.form_submit_button("登录")
    if submitted:
        try:
            result = api("POST", "/api/auth/login", json={"username": username, "password": password})
            st.session_state.user = result["user"]
            st.rerun()
        except RuntimeError as error:
            st.error(str(error))


def require_login():
    if "user" not in st.session_state:
        login_form()
        st.stop()


# --------------------------------------------------------------------- #
# Generic dataframe export/import helpers (pandas)
# --------------------------------------------------------------------- #

def dataframe_download_button(df: pd.DataFrame, filename: str, label: str = "导出为 Excel"):
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Sheet1")
    st.download_button(label, data=buffer.getvalue(), file_name=filename,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def dataframe_upload(label: str = "上传 Excel 文件") -> pd.DataFrame | None:
    uploaded = st.file_uploader(label, type=["xlsx", "xls"])
    if uploaded is None:
        return None
    try:
        return pd.read_excel(uploaded)
    except Exception as error:  # noqa: BLE001
        st.error(f"文件读取失败：{error}")
        return None


# --------------------------------------------------------------------- #
# Pages
# --------------------------------------------------------------------- #

def page_molds():
    st.header("模具管理")

    try:
        molds = api("GET", "/api/molds")
    except RuntimeError as error:
        st.error(str(error))
        return

    df = pd.DataFrame([
        {
            "id": m["id"], "项目编号": m["mold_code"], "项目名称": m["mold_name"],
            "产品编号": m.get("product_code"), "模穴数": m["cavities"],
            "启用": m["is_active"], "累计产量": m["total_output"], "最大产量": m.get("max_output"),
            "当前装机设备": m.get("mounted_device_id"),
        }
        for m in molds
    ])

    st.dataframe(df, width="stretch", hide_index=True)
    dataframe_download_button(df, "molds_export.xlsx", "导出模具列表为 Excel")

    st.divider()
    st.subheader("批量编辑模具基本信息")
    st.caption("下载列表 → 在 Excel 中编辑 项目名称/产品编号/最大产量 等字段 → 重新上传即可批量保存（id 列用于匹配，请勿更改）。")
    edited = dataframe_upload("上传编辑后的模具列表")
    if edited is not None and st.button("应用批量修改", type="primary"):
        errors = []
        progress = st.progress(0.0)
        for i, row in edited.iterrows():
            mold = next((m for m in molds if m["id"] == row["id"]), None)
            if mold is None:
                errors.append(f"id={row['id']} 未找到，已跳过")
                continue
            form = {
                "mold_code": mold["mold_code"],  # unique constraint -- not editable in bulk here
                "mold_name": str(row.get("项目名称", mold["mold_name"])),
                "product_code": str(row.get("产品编号") or ""),
                "cavities": str(mold["cavities"]),
                "remark": mold.get("remark") or "",
                "is_active": "1" if bool(row.get("启用", mold["is_active"])) else "0",
                "cavity_temperatures": "{}",
                "requires_cleaning": "1" if mold.get("requires_cleaning") else "0",
                "cleaning_interval_hours": str(mold.get("cleaning_interval_hours") or ""),
                "cleaning_duration_minutes": str(mold.get("cleaning_duration_minutes") or ""),
                "max_output": str(row.get("最大产量") or ""),
                "keep_image_ids": str([img["id"] for img in mold.get("images", [])]).replace("'", '"'),
            }
            try:
                api("PUT", f"/api/molds/{mold['id']}", data=form)
            except RuntimeError as error:
                errors.append(f"id={row['id']}：{error}")
            progress.progress((i + 1) / len(edited))
        if errors:
            st.warning("部分记录未能保存：\n" + "\n".join(errors))
        else:
            st.success("批量修改已保存")
        st.rerun()


def page_trial_parameter_sheet():
    st.header("试模成型参数表 · 导出 / 导入")

    try:
        molds = api("GET", "/api/molds")
    except RuntimeError as error:
        st.error(str(error))
        return

    mold_options = {f"{m['mold_code']} · {m['mold_name']}": m["id"] for m in molds}
    mold_label = st.selectbox("选择模具", list(mold_options.keys()))
    if not mold_label:
        return
    mold_id = mold_options[mold_label]

    try:
        machine_types = api("GET", f"/api/molds/{mold_id}/machine-types")["machine_types"]
    except RuntimeError as error:
        st.error(str(error))
        return

    if not machine_types:
        st.info("该模具尚未配置机型")
        return

    mt_options = {f"{mt['machine_type']}{'（主要）' if mt['is_main'] else ''}": mt["id"] for mt in machine_types}
    mt_label = st.selectbox("选择机型", list(mt_options.keys()))
    machine_type_id = mt_options[mt_label]

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("导出")
        if st.button("生成并下载试模成型参数表"):
            try:
                response = api("GET", f"/api/molds/{mold_id}/machine-types/{machine_type_id}/export")
                st.download_button(
                    "点击下载", data=response.content,
                    file_name=f"{mold_label.split(' · ')[0]}_试模成型参数表.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            except RuntimeError as error:
                st.error(str(error))

    with col2:
        st.subheader("导入")
        st.caption("上传一份填写过的试模成型参数表；只有表格中实际填写的单元格会被写入，空白单元格不会清空已有数值。")
        uploaded = st.file_uploader("选择 .xlsx 文件", type=["xlsx"], key="trial_sheet_upload")
        if uploaded is not None and st.button("导入到该机型", type="primary"):
            try:
                result = api(
                    "POST",
                    f"/api/molds/{mold_id}/machine-types/{machine_type_id}/import",
                    files={"file": (uploaded.name, uploaded.getvalue(),
                                     "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                )
                st.success(
                    f"导入成功：写入 {result['parameters_imported']} 项工艺参数、"
                    f"{result['extended_fields_imported']} 项扩展字段"
                )
                if result.get("header_read_only"):
                    st.info(f"表头读取到（未自动应用，请手动核对）：{result['header_read_only']}")
            except RuntimeError as error:
                st.error(str(error))


def page_changelog():
    st.header("参数变更记录")
    try:
        rows = api("GET", "/api/changelog")
    except RuntimeError as error:
        st.error(str(error))
        return
    df = pd.DataFrame(rows)
    if df.empty:
        st.info("暂无变更记录")
        return
    st.dataframe(df, width="stretch", hide_index=True)
    dataframe_download_button(df, "changelog_export.xlsx", "导出变更记录为 Excel")


def page_warnings():
    st.header("预警通知")
    try:
        rows = api("GET", "/api/warnings")
    except RuntimeError as error:
        st.error(str(error))
        return
    df = pd.DataFrame(rows)
    if df.empty:
        st.success("暂无待处理预警")
        return
    st.dataframe(df, width="stretch", hide_index=True)
    dataframe_download_button(df, "warnings_export.xlsx", "导出预警为 Excel")


# --------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------- #

def main():
    require_login()

    with st.sidebar:
        st.write(f"已登录：{st.session_state.user['username']} · {st.session_state.user['role']}")
        if st.button("退出登录"):
            try:
                api("POST", "/api/auth/logout")
            except RuntimeError:
                pass
            st.session_state.clear()
            st.rerun()
        st.divider()
        page = st.radio("导航", ["模具管理", "试模成型参数表", "参数变更记录", "预警通知"])

    if page == "模具管理":
        page_molds()
    elif page == "试模成型参数表":
        page_trial_parameter_sheet()
    elif page == "参数变更记录":
        page_changelog()
    elif page == "预警通知":
        page_warnings()


if __name__ == "__main__":
    main()