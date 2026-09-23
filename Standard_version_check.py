import os
import ssl
import json
import re
import time
import urllib3
import requests
import gspread
import streamlit as st
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

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
# ✅ CONFIGURATION & SETTINGS
# ---------------------------------------------------------
SHEET_ID = "1YkTRa4Db4HEkDX-vBX9svDdlZfpbqdIvqrk7d5L1Q_w"

# ระบุตำแหน่งไฟล์ emails.json
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EMAIL_FILE = os.path.join(BASE_DIR, "emails.json")

# ---------------------------------------------------------
# 🧹 ฟังก์ชันสำหรับปรับข้อความให้เป็นมาตรฐานเดียวกันก่อนเปรียบเทียบ
# ---------------------------------------------------------
def normalize_text(text):
    """
    แปลงข้อความให้เป็นตัวพิมพ์เล็ก ลบช่องว่างทั้งหมด และตัดขีดออก 
    เพื่อให้เปรียบเทียบแล้วได้ผลลัพธ์เหมือนกันแน่นอน
    ตัวอย่าง: ' STD - 2026 / 001 ' -> 'std2026/001'
    """
    if not text:
        return ""
    clean_str = str(text).lower().replace(" ", "")
    clean_str = re.sub(r'[-_]', '', clean_str)
    return clean_str

# ---------------------------------------------------------
# 📧 ฟังก์ชันจัดการรายชื่ออีเมลจากไฟล์ emails.json
# ---------------------------------------------------------
def load_saved_emails():
    """โหลดรายชื่ออีเมลจากไฟล์ emails.json"""
    if not os.path.exists(EMAIL_FILE):
        return []
    try:
        with open(EMAIL_FILE, "r", encoding="utf-8") as f:
            emails = json.load(f)
            return [e.strip() for e in emails if e.strip()]
    except Exception as e:
        st.error(f"❌ อ่านไฟล์ {EMAIL_FILE} ไม่สำเร็จ: {repr(e)}")
        return []

def save_saved_emails(email_list):
    """บันทึกรายชื่ออีเมลลงไฟล์ emails.json ถาวร"""
    try:
        with open(EMAIL_FILE, "w", encoding="utf-8") as f:
            json.dump(email_list, f, indent=4, ensure_ascii=False)
        st.toast("💾 บันทึกรายชื่ออีเมลเรียบร้อยแล้ว!", icon="✅")
    except Exception as e:
        st.error(f"❌ ไม่สามารถบันทึกไฟล์อีเมลได้: {repr(e)}")

def add_saved_email(email_str):
    email_clean = email_str.strip()
    if not email_clean:
        st.warning("⚠️ กรุณากรอกอีเมลก่อนเพิ่ม")
        return False
    
    emails = load_saved_emails()
    if any(e.lower() == email_clean.lower() for e in emails):
        st.warning(f"⚠️ อีเมล '{email_clean}' มีอยู่ในรายการแล้ว")
        return False
    
    emails.append(email_clean)
    save_saved_emails(emails)
    return True

def remove_saved_email(email_str):
    emails = load_saved_emails()
    if email_str in emails:
        emails.remove(email_str)
        save_saved_emails(emails)
        return True
    return False

# ---------------------------------------------------------
# 📨 ฟังก์ชันส่ง Email แจ้งเตือน (พร้อมรายงานผลสำเร็จ)
# ---------------------------------------------------------
def send_email_notification(std_num, old_version, new_version, receiver_emails):
    """
    ฟังก์ชันส่งอีเมลแจ้งเตือนเมื่อมีการอัปเดต Version
    """
    if not receiver_emails:
        st.error("❌ ไม่พบรายชื่ออีเมลผู้รับในระบบ!")
        return False

    email_sec = None
    if "email_config" in st.secrets:
        email_sec = st.secrets["email_config"]
    elif "email" in st.secrets:
        email_sec = st.secrets["email"]
    else:
        st.error("❌ ไม่พบการตั้งค่า [email_config] หรือ [email] ใน st.secrets / secrets.toml")
        return False

    try:
        smtp_server = email_sec["smtp_server"]
        smtp_port = int(email_sec["smtp_port"])
        sender_email = email_sec["sender_email"]
        sender_password = email_sec["sender_password"]

        subject = f"🔔 แจ้งเตือน: มีการเปลี่ยน Version ของ {std_num}"
        body = f"""สวัสดีครับ,

มีการปรับเปลี่ยนเวอร์ชันของหมายเลขมาตรฐานในระบบ:

📌 หมายเลขมาตรฐาน (Standard Number): {std_num}
🔄 เวอร์ชันเดิม (Old Version): {old_version if old_version else 'รายการใหม่'}
🆕 เวอร์ชันใหม่ (New Version): {new_version}

โปรดตรวจสอบข้อมูลล่าสุดในระบบ
"""

        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = ", ".join(receiver_emails)
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain', 'utf-8'))

        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

        if smtp_port == 465:
            with smtplib.SMTP_SSL(smtp_server, smtp_port, context=context) as server:
                server.login(sender_email, sender_password)
                server.sendmail(sender_email, receiver_emails, msg.as_string())
        else:
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls(context=context)
                server.login(sender_email, sender_password)
                server.sendmail(sender_email, receiver_emails, msg.as_string())

        # 📌 รายงานการส่งอีเมลสำเร็จบนหน้าจอ
        email_list_str = ", ".join([f"`{e}`" for e in receiver_emails])
        st.success(f"✅ ส่งอีเมลแจ้งเตือนสำเร็จไปยัง {len(receiver_emails)} รายการ:\n{email_list_str}")
        st.toast("📧 ส่งอีเมลแจ้งเตือนสำเร็จเรียบร้อยแล้ว!", icon="📨")
        return True

    except Exception as e:
        st.error(f"❌ เกิดข้อผิดพลาดในการส่งอีเมลผ่าน SMTP: {str(e)}")
        return False

# ---------------------------------------------------------
# 📊 GOOGLE SHEETS CLIENT
# ---------------------------------------------------------
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
            df = pd.DataFrame(values[1:], columns=values[0])
            return df
        elif len(values) == 1:
            return pd.DataFrame(columns=values[0])
        return pd.DataFrame()
    except Exception as err:
        st.error(f"⚠️ เกิดข้อผิดพลาดในการดึงข้อมูล: {repr(err)}")
        return pd.DataFrame()

def delete_row_from_sheet(std_num, version):
    gc = get_gspread_client()
    if not gc:
        return False
    try:
        sh = gc.open_by_key(SHEET_ID)
        worksheet = sh.get_worksheet(0)
        values = worksheet.get_all_values()
        
        row_to_delete = None
        target_std_norm = normalize_text(std_num)
        target_ver_norm = normalize_text(version)

        for idx, row in enumerate(values):
            if idx == 0:
                continue
            if len(row) >= 2:
                row_std_norm = normalize_text(row[0])
                row_ver_norm = normalize_text(row[1])
                if row_std_norm == target_std_norm and row_ver_norm == target_ver_norm:
                    row_to_delete = idx + 1
                    break

        if row_to_delete:
            worksheet.delete_rows(row_to_delete)
            return True
        else:
            st.error("❌ ไม่พบบรรทัดที่ต้องการลบใน Google Sheets")
            return False
    except Exception as e:
        st.error(f"❌ เกิดข้อผิดพลาดในการลบข้อมูล: {repr(e)}")
        return False

# --- Streamlit UI Config ---
st.set_page_config(page_title="ระบบบันทึกหมายเลขมาตรฐาน", page_icon="📝", layout="centered")
st.title("📝 ระบบบันทึกหมายเลขมาตรฐาน")

# ---------------------------------------------------------
# ⚙️ POP-UP MODAL จัดการอีเมลสำหรับ ALARM
# ---------------------------------------------------------
@st.dialog("⚙️ จัดการรายชื่ออีเมลรับแจ้งเตือน (Alarm Email List)")
def show_email_manager_modal():
    st.caption("อีเมลในรายการนี้จะถูกบันทึกไว้ในไฟล์ emails.json ถาวร")
    
    col_add_input, col_add_btn = st.columns([3, 1])
    with col_add_input:
        new_email = st.text_input("เพิ่มอีเมลใหม่", placeholder="example@domain.com", label_visibility="collapsed")
    with col_add_btn:
        if st.button("➕ เพิ่ม", type="primary", use_container_width=True):
            if add_saved_email(new_email):
                st.rerun()

    st.divider()
    
    current_emails = load_saved_emails()
    st.subheader(f"📋 รายชื่ออีเมลปัจจุบัน ({len(current_emails)} รายการ)")
    
    if current_emails:
        for idx, email in enumerate(current_emails):
            c_mail, c_del = st.columns([3, 1])
            with c_mail:
                st.write(f"• `{email}`")
            with c_del:
                if st.button("🗑️ ลบ", key=f"del_email_{idx}", use_container_width=True):
                    remove_saved_email(email)
                    st.rerun()
    else:
        st.info("ℹ️ ยังไม่มีรายการอีเมลในระบบ")

# ---------------------------------------------------------
# 💡 POP-UP MODAL เพิ่ม/แก้ไข หมายเลขมาตรฐาน & VERSION
# ---------------------------------------------------------
@st.dialog("➕ เพิ่ม / อัปเดตหมายเลขมาตรฐาน")
def show_add_modal():
    std_num_input = st.text_input(
        "หมายเลขมาตรฐาน (Standard Number)", 
        placeholder="เช่น STD-2026-001", 
        key="popup_std_input"
    )
    
    version_input = st.text_input(
        "เวอร์ชัน (Version)", 
        placeholder="เช่น v1.0, v1.1, 2.0", 
        key="popup_ver_input"
    )

    saved_emails = load_saved_emails()
    if saved_emails:
        st.info(f"📨 **จะส่งแจ้งเตือนไปยัง ({len(saved_emails)} อีเมล):**\n" + ", ".join([f"`{e}`" for e in saved_emails]))
    else:
        st.warning("⚠️ ยังไม่ได้ตั้งค่าอีเมลรับแจ้งเตือนใน emails.json (กดเพิ่มที่ '⚙️ จัดการอีเมล Alarm')")

    col_save, col_close = st.columns([1, 1])
    
    with col_save:
        if st.button("💾 บันทึกข้อมูล", type="primary", use_container_width=True):
            std_num_clean = std_num_input.strip()
            version_clean = version_input.strip()

            if not std_num_clean or not version_clean:
                st.warning("⚠️ กรุณากรอกทั้ง 'หมายเลขมาตรฐาน' และ 'Version' ก่อนบันทึก")
            else:
                try:
                    gc = get_gspread_client()
                    if gc:
                        sh = gc.open_by_key(SHEET_ID)
                        worksheet = sh.get_worksheet(0)
                        values = worksheet.get_all_values()
                        
                        if not values:
                            worksheet.append_row(["Standard Number", "Version"])
                            values = [["Standard Number", "Version"]]

                        found_row_idx = None
                        existing_version = None
                        is_exact_duplicate = False

                        input_std_norm = normalize_text(std_num_clean)
                        input_ver_norm = normalize_text(version_clean)

                        for idx, row in enumerate(values):
                            if idx == 0:
                                continue
                            if len(row) > 0:
                                row_std_norm = normalize_text(row[0])
                                row_ver_norm = normalize_text(row[1]) if len(row) > 1 else ""

                                if row_std_norm == input_std_norm:
                                    found_row_idx = idx + 1
                                    existing_version = row[1].strip() if len(row) > 1 else ""
                                    if row_ver_norm == input_ver_norm:
                                        is_exact_duplicate = True
                                    break

                        if is_exact_duplicate:
                            st.error(f"⚠️ หมายเลขมาตรฐาน '{std_num_clean}' เวอร์ชัน '{version_clean}' มีอยู่ในระบบแล้ว!")
                        
                        # อัปเดต Version เดิม
                        elif found_row_idx:
                            worksheet.update_cell(found_row_idx, 2, version_clean)
                            st.toast(f"🔄 อัปเดตเวอร์ชันของ '{std_num_clean}' เป็น '{version_clean}' เรียบร้อยแล้ว!", icon="🎉")

                            # เรียกส่งอีเมลแจ้งเตือน
                            if saved_emails:
                                send_email_notification(std_num_clean, existing_version, version_clean, saved_emails)

                            st.cache_resource.clear()
                            time.sleep(2.5)  # แสดงกล่องข้อความรายงานผลส่งอีเมล 2.5 วินาทีก่อนปิด Pop-up
                            st.rerun()

                        # เพิ่มรายการใหม่
                        else:
                            worksheet.append_row([std_num_clean, version_clean])
                            st.toast(f"✅ บันทึกหมายเลขใหม่ '{std_num_clean}' (Ver. {version_clean}) เรียบร้อยแล้ว!", icon="🎉")

                            # เรียกส่งอีเมลแจ้งเตือน
                            if saved_emails:
                                send_email_notification(std_num_clean, None, version_clean, saved_emails)

                            st.cache_resource.clear()
                            time.sleep(2.5)  # แสดงกล่องข้อความรายงานผลส่งอีเมล 2.5 วินาทีก่อนปิด Pop-up
                            st.rerun()

                except Exception as err:
                    st.error(f"❌ บันทึกข้อมูลล้มเหลว: {repr(err)}")

    with col_close:
        if st.button("❌ ยกเลิก", use_container_width=True):
            st.rerun()

# ---------------------------------------------------------
# 💡 POP-UP MODAL ยืนยันการลบข้อมูล
# ---------------------------------------------------------
@st.dialog("🗑️ ยืนยันการลบหมายเลขมาตรฐาน")
def show_delete_modal(selected_items, data_df):
    st.write("คุณต้องการลบรายการมาตรฐานที่เลือกต่อไปนี้ใช่หรือไม่?")
    
    rows_to_delete = data_df.iloc[selected_items]
    st.dataframe(rows_to_delete, use_container_width=True, hide_index=True)
    
    col_del_confirm, col_del_cancel = st.columns([1, 1])
    
    with col_del_confirm:
        if st.button("🔴 ยืนยันลบข้อมูล", type="primary", use_container_width=True):
            success_count = 0
            for idx in selected_items:
                row = data_df.iloc[idx]
                std_num = str(row.get("Standard Number", row.iloc[0]))
                version = str(row.get("Version", row.iloc[1] if len(row) > 1 else ""))
                
                if delete_row_from_sheet(std_num, version):
                    success_count += 1
            
            st.toast(f"🗑️ ลบข้อมูลสำเร็จ {success_count} รายการ", icon="✅")
            st.cache_resource.clear()
            st.rerun()

    with col_del_cancel:
        if st.button("❌ ยกเลิก", use_container_width=True):
            st.rerun()

# ---------------------------------------------------------
# 🔘 ปุ่มควบคุมหลัก
# ---------------------------------------------------------
col_btn1, col_btn2, col_btn3 = st.columns([2, 1.5, 1])

with col_btn1:
    if st.button("➕ กรอกหมายเลขมาตรฐานใหม่ / แก้ไข", type="primary", use_container_width=True):
        show_add_modal()

with col_btn2:
    if st.button("⚙️ จัดการอีเมล Alarm", use_container_width=True):
        show_email_manager_modal()

with col_btn3:
    if st.button("🔄 รีเฟรช", use_container_width=True):
        st.cache_resource.clear()
        st.rerun()

st.divider()

# ---------------------------------------------------------
# 📊 แสดงผลตารางข้อมูลปัจจุบัน
# ---------------------------------------------------------
st.subheader("📊 รายการหมายเลขมาตรฐานปัจจุบันในระบบ")

data = fetch_data()

if not data.empty:
    event = st.dataframe(
        data, 
        use_container_width=True, 
        hide_index=True,
        on_select="rerun",
        selection_mode="multi-row"
    )
    
    selected_rows = event.selection.rows if event and hasattr(event, 'selection') else []
    
    col_info, col_delete_btn = st.columns([2, 1])
    
    with col_info:
        if selected_rows:
            st.write(f"📌 เลือกอยู่ **{len(selected_rows)}** รายการ")
        else:
            st.caption("💡 *ติ๊กถูกที่ช่องหน้าแถวเพื่อเลือกรายการที่ต้องการลบ*")
            
    with col_delete_btn:
        if st.button("🗑️ ลบรายการที่เลือก", type="secondary", disabled=len(selected_rows) == 0, use_container_width=True):
            show_delete_modal(selected_rows, data)

else:
    st.info("ℹ️ ไม่พบข้อมูลในตาราง หรือตารางยังว่างอยู่")
