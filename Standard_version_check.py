import os
import ssl
import urllib3
import requests
import gspread
import streamlit as st
import pandas as pd

# Bypass SSL Verification
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
old_send = requests.Session.send
def new_send(self, request, **kwargs):
    kwargs["verify"] = False
    return old_send(self, request, **kwargs)
requests.Session.send = new_send

os.environ['CURL_CA_BUNDLE'] = ''
os.environ['PYTHONHTTPSVERIFY'] = '0'
ssl._create_default_https_context = ssl._create_unverified_context

# ---------------------------------------------------------
# ✅ SHEET_ID ที่ถูกต้อง
# ---------------------------------------------------------
SHEET_ID = "1YkTRa4Db4HEkDX-vBX9svDdlZfpbqdIvqrk7d5L1Q_w"

@st.cache_resource(ttl=5)
def get_gspread_client():
    try:
        credentials = dict(st.secrets["gcp_service_account"])
        if "private_key" in credentials:
            credentials["private_key"] = credentials["private_key"].replace("\\n", "\n")
        return gspread.service_account_from_dict(credentials)
    except Exception as e:
        st.error(f"❌ โหลดข้อมูลสิทธิ์จาก secrets.toml ล้มเหลว: {repr(e)}")
        return None

def fetch_data():
    gc = get_gspread_client()
    if not gc:
        return pd.DataFrame()
    
    try:
        sh = gc.open_by_key(SHEET_ID)
        worksheet = sh.get_worksheet(0)
        values = worksheet.get_all_values()
        
        if len(values) > 1:
            return pd.DataFrame(values[1:], columns=values[0])
        elif len(values) == 1:
            return pd.DataFrame(columns=values[0])
        return pd.DataFrame()
    except Exception as err:
        st.error(f"⚠️ เกิดข้อผิดพลาดในการดึงข้อมูล: {repr(err)}")
        return pd.DataFrame()

# --- Streamlit UI Config ---
st.set_page_config(page_title="ระบบบันทึกหมายเลขมาตรฐาน", page_icon="📝", layout="centered")
st.title("📝 ระบบบันทึกหมายเลขมาตรฐาน")

# ---------------------------------------------------------
# 💡 นิยาม Pop-up Modal ด้วย @st.dialog
# ---------------------------------------------------------
@st.dialog("➕ เพิ่มหมายเลขมาตรฐานใหม่")
def show_add_modal():
    std_num_input = st.text_input(
        "หมายเลขมาตรฐาน (Standard Number)", 
        placeholder="เช่น STD-2026-001", 
        key="popup_std_input"
    )
    
    col_save, col_close = st.columns([1, 1])
    
    with col_save:
        if st.button("💾 บันทึกข้อมูล", type="primary", use_container_width=True):
            if not std_num_input.strip():
                st.warning("⚠️ กรุณากรอกหมายเลขมาตรฐานก่อนบันทึก")
            else:
                try:
                    gc = get_gspread_client()
                    if gc:
                        sh = gc.open_by_key(SHEET_ID)
                        worksheet = sh.get_worksheet(0)
                        worksheet.append_row([std_num_input.strip()])
                        st.toast(f"✅ บันทึกหมายเลข '{std_num_input.strip()}' เรียบร้อยแล้ว!", icon="🎉")
                        st.rerun()
                except Exception as err:
                    st.error(f"❌ บันทึกข้อมูลล้มเหลว: {repr(err)}")

    with col_close:
        if st.button("❌ ยกเลิก", use_container_width=True):
            st.rerun()

# ---------------------------------------------------------
# 🔘 ปุ่มควบคุมหลัก
# ---------------------------------------------------------
col_btn1, col_btn2 = st.columns([2, 1])

with col_btn1:
    # กดปุ่มแล้วเรียกฟังก์ชัน dialog โดยตรง
    if st.button("➕ กรอกหมายเลขมาตรฐานใหม่", type="primary", use_container_width=True):
        show_add_modal()

with col_btn2:
    if st.button("🔄 รีเฟรชข้อมูล", use_container_width=True):
        st.cache_resource.clear()
        st.rerun()

st.divider()

# ---------------------------------------------------------
# 📊 แสดงผลตารางข้อมูลปัจจุบัน
# ---------------------------------------------------------
st.subheader("📊 รายการหมายเลขมาตรฐานปัจจุบันในระบบ")

data = fetch_data()
if not data.empty:
    st.dataframe(data, use_container_width=True, hide_index=True)
else:
    st.info("ℹ️ ไม่พบข้อมูลในตาราง หรือตารางยังว่างอยู่")