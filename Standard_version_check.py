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
from google import genai
from google.genai import types

# Bypass SSL Verification สำหรับการเชื่อมต่อภายนอก
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

# รายชื่อหัวคอลัมน์มาตรฐานทั้ง 7 คอลัมน์
COLUMNS = [
    "Standard number", 
    "Standard name", 
    "Version", 
    "Announced", 
    "Enforcement", 
    "Detail of the changes",
    "Reference website"
]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EMAIL_FILE = os.path.join(BASE_DIR, "emails.json")

# ---------------------------------------------------------
# 🧹 ฟังก์ชันปรับข้อความก่อนเทียบ
# ---------------------------------------------------------
def normalize_text(text):
    if not text:
        return ""
    clean_str = str(text).lower().replace(" ", "")
    clean_str = re.sub(r'[-_]', '', clean_str)
    return clean_str
# ---------------------------------------------------------
# 🤖 ฟังก์ชันค้นหาข้อมูลด้วย GEMINI AI (อัปเดตเป็น gemini-3.6-flash)
# ---------------------------------------------------------
def search_standard_info_with_ai(std_number):
    """
    ใช้ Gemini 3.6 Flash API ค้นหาข้อมูลหมายเลขมาตรฐานจาก Google Search
    """
    api_key = st.secrets.get("GEMINI_API_KEY")
    if not api_key:
        st.error("❌ ไม่พบ GEMINI_API_KEY ใน Streamlit Secrets")
        return None

    try:
        client = genai.Client(api_key=api_key)

        prompt = f"""
        คุณคือผู้เชี่ยวชาญด้านมาตรฐานอุตสาหกรรม (เช่น IEC, ISO, EN, TISI)
        กรุณาสืบค้นข้อมูลล่าสุดทางอินเทอร์เน็ตสำหรับหมายเลขมาตรฐาน: "{std_number}"

        แล้วสรุปข้อมูลส่งกลับมาเป็น JSON ตามโครงสร้างนี้เท่านั้น (ห้ามใส่คำเกริ่นนำหรือ markdown แวดล้อม):
        {{
            "standard_name": "ชื่อมาตรฐานภาษาอังกฤษหรือไทยแบบเต็ม",
            "version": "เวอร์ชันล่าสุดหรือปี ค.ศ. ของเวอร์ชัน เช่น Edition 6.0 หรือ 2020",
            "announced": "วันที่ประกาศใช้ (รูปแบบ YYYY-MM-DD หรือระบุปีถ้าไม่ทราบวัน)",
            "enforcement": "วันที่มีผลบังคับใช้ (รูปแบบ YYYY-MM-DD หรือระบุปีถ้าไม่ทราบวัน)",
            "details_of_changes": "สรุปสาระสำคัญหรือข้อแตกต่างของการปรับปรุงในเวอร์ชันนี้โดยสังเขป",
            "reference_website": "URL เว็บไซต์อ้างอิงหลักที่พบข้อมูล เช่น iec.ch, iso.org หรือเว็บทางการอื่นๆ"
        }}
        """

        # เปลี่ยนชื่อโมเดลเป็น gemini-3.6-flash ตามที่ API แนะนำ
        response = client.models.generate_content(
            model='gemini-3.6-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[{"google_search": {}}],  # เปิดระบบ Google Search Grounding
                response_mime_type="application/json"
            )
        )

        result_data = json.loads(response.text)
        return result_data

    except Exception as e:
        st.error(f"❌ เกิดข้อผิดพลาดในการดึงข้อมูลจาก AI: {repr(e)}")
        return None


# ---------------------------------------------------------
# 📧 ฟังก์ชันจัดการรายชื่ออีเมลจากไฟล์ emails.json
# ---------------------------------------------------------
def load_saved_emails():
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
# 📨 ฟังก์ชันส่ง Email แจ้งเตือน
# ---------------------------------------------------------
def send_email_notification(std_num, std_name, old_version, new_version, announced, enforcement, details, ref_web, receiver_emails):
    if not receiver_emails:
        st.error("❌ ไม่พบรายชื่ออีเมลผู้รับในระบบ!")
        return False

    email_sec = None
    if "email_config" in st.secrets:
        email_sec = st.secrets["email_config"]
    elif "email" in st.secrets:
        email_sec = st.secrets["email"]
    else:
        st.error("❌ ไม่พบการตั้งค่า [email_config] หรือ [email] ใน st.secrets")
        return False

    try:
        smtp_server = email_sec["smtp_server"]
        smtp_port = int(email_sec["smtp_port"])
        sender_email = email_sec["sender_email"]
        sender_password = email_sec["sender_password"]

        subject = f"🔔 แจ้งเตือน: มีการอัปเดตข้อมูลมาตรฐาน {std_num}"
        body = f"""สวัสดีครับ/ค่ะ,

มีการปรับเปลี่ยนข้อมูลหมายเลขมาตรฐานในระบบ:

📌 หมายเลขมาตรฐาน (Standard Number): {std_num}
📝 ชื่อมาตรฐาน (Standard Name): {std_name if std_name else '-'}
🔄 เวอร์ชันเดิม (Old Version): {old_version if old_version else 'รายการใหม่'}
🆕 เวอร์ชันใหม่ (New Version): {new_version if new_version else '-'}
📅 วันที่ประกาศ (Announced): {announced if announced else '-'}
⚖️ วันที่มีผลบังคับใช้ (Enforcement): {enforcement if enforcement else '-'}
📜 รายละเอียดการเปลี่ยนแปลง (Details of Changes):
{details if details else '-'}
🔗 เว็บไซต์อ้างอิง (Reference Website): {ref_web if ref_web else '-'}

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
        st.error(f"❌ โหลดข้อมูลสิทธิ์จาก secrets ล้มเหลว: {repr(e)}")
        return None

def fetch_data():
    gc = get_gspread_client()
    if not gc:
        return pd.DataFrame(columns=COLUMNS)
    
    try:
        sh = gc.open_by_key(SHEET_ID)
        worksheet = sh.get_worksheet(0)
        values = worksheet.get_all_values()
        
        # ปรับแก้หัวตารางใน Google Sheets ให้ตรงกันทั้ง 7 คอลัมน์โดยอัตโนมัติ
        if len(values) == 0 or values[0] != COLUMNS:
            worksheet.update('A1:G1', [COLUMNS])
            values = worksheet.get_all_values()

        if len(values) > 1:
            df = pd.DataFrame(values[1:], columns=values[0])
            for col in COLUMNS:
                if col not in df.columns:
                    df[col] = ""
            return df[COLUMNS]
        return pd.DataFrame(columns=COLUMNS)
    except Exception as err:
        st.error(f"⚠️ เกิดข้อผิดพลาดในการดึงข้อมูล: {repr(err)}")
        return pd.DataFrame(columns=COLUMNS)

def delete_row_from_sheet(std_num):
    gc = get_gspread_client()
    if not gc:
        return False
    try:
        sh = gc.open_by_key(SHEET_ID)
        worksheet = sh.get_worksheet(0)
        values = worksheet.get_all_values()
        
        row_to_delete = None
        target_std_norm = normalize_text(std_num)

        for idx, row in enumerate(values):
            if idx == 0:
                continue
            if len(row) > 0:
                row_std_norm = normalize_text(row[0])
                if row_std_norm == target_std_norm:
                    row_to_delete = idx + 1
                    break

        if row_to_delete:
            worksheet.delete_rows(row_to_delete)
            return True
        else:
            st.error(f"❌ ไม่พบบรรทัดหมายเลขมาตรฐาน '{std_num}' ใน Google Sheets")
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
# 💡 POP-UP MODAL เพิ่ม/แก้ไข หมายเลขมาตรฐาน
# ---------------------------------------------------------
@st.dialog("➕ เพิ่ม / อัปเดตหมายเลขมาตรฐาน")
def show_add_modal():
    if "ai_data" not in st.session_state:
        st.session_state.ai_data = {}

    col_std, col_ai_btn = st.columns([2.7, 1.3])
    with col_std:
        std_num_input = st.text_input(
            "หมายเลขมาตรฐาน (Standard Number) *", 
            placeholder="เช่น IEC 60335-1", 
            key="popup_std_input"
        )
    with col_ai_btn:
        st.write("")
        st.write("")
        if st.button("🤖 ให้ AI ตรวจเช็ก", use_container_width=True, type="primary"):
            if std_num_input.strip():
                with st.spinner("🔍 AI กำลังค้นหาข้อมูลบนอินเทอร์เน็ต..."):
                    ai_res = search_standard_info_with_ai(std_num_input.strip())
                    if ai_res:
                        st.session_state.ai_data = ai_res
                        st.success("✅ AI ค้นหาข้อมูลสำเร็จ!")
                        st.rerun()
            else:
                st.warning("⚠️ กรุณากรอกหมายเลขมาตรฐานก่อน")

    ai = st.session_state.ai_data

    std_name_input = st.text_input("ชื่อมาตรฐาน (Standard Name)", value=ai.get("standard_name", ""), key="popup_std_name")
    version_input = st.text_input("เวอร์ชัน (Version) [AI ตรวจเช็กให้อัตโนมัติ]", value=ai.get("version", ""), key="popup_version", disabled=True)

    col_ann, col_enf = st.columns(2)
    with col_ann:
        announced_input = st.text_input("Announced (วันที่ประกาศ)", value=ai.get("announced", ""), key="popup_ann")
    with col_enf:
        enforcement_input = st.text_input("Enforcement (วันบังคับใช้)", value=ai.get("enforcement", ""), key="popup_enf")

    details_input = st.text_area("Detail of the changes", value=ai.get("details_of_changes", ""), key="popup_details")
    ref_web_input = st.text_input("Reference Website (เว็บไซต์อ้างอิง)", value=ai.get("reference_website", ""), key="popup_ref")

    saved_emails = load_saved_emails()
    if saved_emails:
        st.info(f"📨 **จะส่งแจ้งเตือนไปยัง ({len(saved_emails)} อีเมล):**\n" + ", ".join([f"`{e}`" for e in saved_emails]))
    else:
        st.warning("⚠️ ยังไม่ได้ตั้งค่าอีเมลรับแจ้งเตือนใน emails.json")

    col_save, col_close = st.columns([1, 1])
    
    with col_save:
        if st.button("💾 บันทึกข้อมูลลง Google Sheets", type="primary", use_container_width=True):
            std_num_clean = std_num_input.strip()
            std_name_clean = std_name_input.strip()
            version_clean = version_input.strip()
            announced_clean = announced_input.strip()
            enforcement_clean = enforcement_input.strip()
            details_clean = details_input.strip()
            ref_web_clean = ref_web_input.strip()

            if not std_num_clean:
                st.warning("⚠️ กรุณากรอก 'หมายเลขมาตรฐาน' ก่อนบันทึก")
            elif not version_clean:
                st.warning("⚠️ กรุณากดปุ่ม '🤖 ให้ AI ตรวจเช็ก' ก่อนบันทึก")
            else:
                try:
                    gc = get_gspread_client()
                    if gc:
                        sh = gc.open_by_key(SHEET_ID)
                        worksheet = sh.get_worksheet(0)
                        values = worksheet.get_all_values()
                        
                        worksheet.update('A1:G1', [COLUMNS])
                        if not values or values[0] != COLUMNS:
                            values = [COLUMNS]

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
                                row_ver_norm = normalize_text(row[2]) if len(row) > 2 else ""

                                if row_std_norm == input_std_norm:
                                    found_row_idx = idx + 1
                                    existing_version = row[2].strip() if len(row) > 2 else ""
                                    if row_ver_norm == input_ver_norm:
                                        is_exact_duplicate = True
                                    break

                        new_row_data = [
                            std_num_clean,      # Col A
                            std_name_clean,     # Col B
                            version_clean,      # Col C
                            announced_clean,    # Col D
                            enforcement_clean,  # Col E
                            details_clean,      # Col F
                            ref_web_clean       # Col G
                        ]

                        if is_exact_duplicate:
                            st.error(f"⚠️ หมายเลขมาตรฐาน '{std_num_clean}' เวอร์ชัน '{version_clean}' มีอยู่ในระบบแล้ว!")
                        
                        elif found_row_idx:
                            cell_range = f"A{found_row_idx}:G{found_row_idx}"
                            worksheet.update(cell_range, [new_row_data])
                            st.toast(f"🔄 อัปเดตข้อมูลของ '{std_num_clean}' เรียบร้อยแล้ว!", icon="🎉")

                            if saved_emails:
                                send_email_notification(
                                    std_num_clean, std_name_clean, existing_version, version_clean, 
                                    announced_clean, enforcement_clean, details_clean, ref_web_clean, saved_emails
                                )

                            st.session_state.ai_data = {}
                            st.cache_resource.clear()
                            time.sleep(2.5)
                            st.rerun()

                        else:
                            worksheet.append_row(new_row_data)
                            st.toast(f"✅ บันทึกหมายเลขใหม่ '{std_num_clean}' (Ver. {version_clean}) เรียบร้อยแล้ว!", icon="🎉")

                            if saved_emails:
                                send_email_notification(
                                    std_num_clean, std_name_clean, None, version_clean, 
                                    announced_clean, enforcement_clean, details_clean, ref_web_clean, saved_emails
                                )

                            st.session_state.ai_data = {}
                            st.cache_resource.clear()
                            time.sleep(2.5)
                            st.rerun()

                except Exception as err:
                    st.error(f"❌ บันทึกข้อมูลล้มเหลว: {repr(err)}")

    with col_close:
        if st.button("❌ ยกเลิก", use_container_width=True):
            st.session_state.ai_data = {}
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
                std_num = str(row.get("Standard number", row.iloc[0]))
                
                if delete_row_from_sheet(std_num):
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
