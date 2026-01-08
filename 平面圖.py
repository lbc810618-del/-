import streamlit as st
from PIL import Image, ImageDraw, ImageFont
import pandas as pd
from streamlit_image_coordinates import streamlit_image_coordinates
import math
import io
import fitz  # PyMuPDF
from datetime import datetime
import os

# 1. 頁面配置
st.set_page_config(page_title="專業標註系統", layout="wide")

COLOR_MAP = {
    "商品": "#FF5252", "價格": "#FFD740", "清潔": "#69F0AE",
    "備品": "#448AFF", "流程": "#E040FB", "其他": "#90A4AE"
}

# 繪圖與判定參數
FIXED_FONT_SCALE = 0.020
DRAW_RADIUS_RATIO = 0.012
HIT_RADIUS_RATIO = 0.015

# 狀態初始化
if "marker_data" not in st.session_state: st.session_state.marker_data = []
if "active_tag" not in st.session_state: st.session_state.active_tag = ""
if "zoom_level" not in st.session_state: st.session_state.zoom_level = 1.0
if "rotation_angle" not in st.session_state: st.session_state.rotation_angle = 0
if "file_id" not in st.session_state: st.session_state.file_id = None
if "last_processed_coords" not in st.session_state: st.session_state.last_processed_coords = None

# --- 核心優化：備註欄位狀態管理 ---
if "memo_reset_trigger" not in st.session_state: st.session_state.memo_reset_trigger = 0

# 2. 核心 CSS
active_color = COLOR_MAP.get(st.session_state.active_tag, "#448AFF")
st.markdown(f"""
    <style>
    .block-container {{ padding-top: 5.5rem !important; }}
    .stButton button {{ height: 35px !important; border-radius: 6px !important; font-weight: 800 !important; }}
    div[data-testid="stHorizontalBlock"] button[kind="primary"] {{
        background-color: {active_color} !important;
        color: black !important;
        border: 2px solid #333 !important;
    }}
    .stImage {{ background-color: #f0f2f6; border-radius: 10px; overflow: hidden; }}
    </style>
    """, unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def load_base_image(uploaded_file):
    if uploaded_file.type == "application/pdf":
        pdf_data = uploaded_file.read()
        doc = fitz.open(stream=pdf_data, filetype="pdf")
        page = doc.load_page(0)
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        doc.close()
        return img
    else:
        return Image.open(uploaded_file).convert("RGB")


@st.cache_resource
def get_cached_font(size):
    font_names = ["msjhbd.ttc", "msjh.ttc", "arialbd.ttf", "arial.ttf", "/System/Library/Fonts/STHeiti Light.ttc",
                  "DejaVuSans.ttf"]
    for name in font_names:
        try:
            return ImageFont.truetype(name, size)
        except:
            continue
    return ImageFont.load_default()


# --- 側邊欄 ---
with st.sidebar:
    st.header("📂 檔案管理")
    uploaded_file = st.file_uploader("1. 上傳地圖", type=["png", "jpg", "jpeg", "pdf"])

    if uploaded_file:
        current_file_id = f"{uploaded_file.name}_{uploaded_file.size}"
        if st.session_state.file_id != current_file_id:
            st.session_state.marker_data = []
            st.session_state.file_id = current_file_id
            st.rerun()

        base_img = load_base_image(uploaded_file)
        today_str = datetime.now().strftime("%Y%m%d")
        base_filename = os.path.splitext(uploaded_file.name)[0]
        export_filename_base = f"{today_str}_{base_filename}"

        st.divider()
        st.subheader("🔍 視圖調整")
        col_z1, col_z2 = st.columns(2)
        with col_z1:
            if st.button("➕ 放大", use_container_width=True):
                st.session_state.zoom_level += 0.2;
                st.rerun()
        with col_z2:
            if st.button("➖ 縮小", use_container_width=True):
                st.session_state.zoom_level = max(0.4, st.session_state.zoom_level - 0.2);
                st.rerun()

        st.session_state.rotation_angle = st.select_slider("旋轉角度", options=[0, 90, 180, 270],
                                                           value=st.session_state.rotation_angle)

        st.divider()
        st.subheader("💾 導出與管理")

        export_img = base_img.copy()
        if st.session_state.rotation_angle != 0:
            export_img = export_img.rotate(-st.session_state.rotation_angle, expand=True)
        ew, eh = export_img.size
        edraw = ImageDraw.Draw(export_img)
        eradius = ew * DRAW_RADIUS_RATIO
        efont = get_cached_font(int(ew * FIXED_FONT_SCALE))
        for m in st.session_state.marker_data:
            ex, ey = m['rel_x'] * ew, m['rel_y'] * eh
            ec = COLOR_MAP.get(m['標籤'], "#000000")
            edraw.ellipse([ex - eradius, ey - eradius, ex + eradius, ey + eradius], fill=ec, outline="white", width=2)
            edraw.text((ex, ey), str(m['序號']), fill="black", font=efont, anchor="mm")

        img_byte_arr = io.BytesIO()
        export_img.save(img_byte_arr, format='JPEG', quality=90)

        st.download_button(label="🖼 下載標註圖面 (.jpg)", data=img_byte_arr.getvalue(),
                           file_name=f"{export_filename_base}.jpg", use_container_width=True)

        if st.session_state.marker_data:
            df = pd.DataFrame(st.session_state.marker_data).drop(columns=['rel_x', 'rel_y'])
            csv_data = df.to_csv(index=False).encode('utf-8-sig')
            st.download_button(label="📊 下載數據 (.csv)", data=csv_data, file_name=f"{export_filename_base}.csv",
                               mime="text/csv", use_container_width=True)

            if st.button("🗑 全部清空", use_container_width=True):
                st.session_state.marker_data = [];
                st.rerun()

# --- 主畫面 ---
if not uploaded_file:
    st.title("🚀 專業標註系統")
    st.info("👋 您好！請從左側上傳地圖檔案開始標註。")
else:
    # 頂部控制台
    t_col = st.columns([1, 1, 1, 1.5])
    with t_col[0]:
        op_mode = st.radio("模式選擇", ["新增標註", "點選移除"], horizontal=True, label_visibility="collapsed")
    with t_col[1]:
        next_n = len(st.session_state.marker_data) + 1
        pos_opts = [f"#{next_n}"] + [f"插入:{i + 1}" for i in range(len(st.session_state.marker_data))]
        insert_pos = st.selectbox("序號", options=pos_opts, disabled=(op_mode == "點選移除"),
                                  label_visibility="collapsed")
    with t_col[2]:
        cur_loc = st.selectbox("位置", options=["騎樓", "收銀", "生鮮", "日配", "加一", "加二", "百貨", "菸酒"],
                               disabled=(op_mode == "點選移除"), label_visibility="collapsed")
    with t_col[3]:
        # ✨ 使用特定 Key 並結合動態觸發器確保清空
        memo = st.text_input(
            "備註",
            placeholder="輸入說明並點擊地圖...",
            key=f"memo_input_{st.session_state.memo_reset_trigger}",
            disabled=(op_mode == "點選移除"),
            label_visibility="collapsed"
        )

    # 標籤按鈕列
    b_cols = st.columns(6)
    for i, name in enumerate(COLOR_MAP.keys()):
        is_active = (name == st.session_state.active_tag)
        if b_cols[i].button(name, use_container_width=True, key=f"btn_{name}",
                            type="primary" if is_active else "secondary", disabled=(op_mode == "點選移除")):
            st.session_state.active_tag = name
            st.rerun()

    st.markdown("---")

    # 圖片渲染處理
    display_img = base_img.copy()
    if st.session_state.rotation_angle != 0:
        display_img = display_img.rotate(-st.session_state.rotation_angle, expand=True)

    mw, mh = display_img.size
    mdraw = ImageDraw.Draw(display_img)
    p_radius = mw * DRAW_RADIUS_RATIO
    p_font = get_cached_font(int(mw * FIXED_FONT_SCALE))

    for m in st.session_state.marker_data:
        px, py = m['rel_x'] * mw, m['rel_y'] * mh
        c = COLOR_MAP.get(m['標籤'], "#000000")
        mdraw.ellipse([px - p_radius, py - p_radius, px + p_radius, py + p_radius], fill=c, outline="white", width=2)
        mdraw.text((px, py), str(m['序號']), fill="black", font=p_font, anchor="mm")

    # ✨ 固定 Key 解決閃爍，但確保 coords 能被正確捕捉
    stable_key = f"map_render_{st.session_state.file_id}_{st.session_state.zoom_level}_{st.session_state.rotation_angle}"

    coords = streamlit_image_coordinates(
        display_img,
        width=int(mw * st.session_state.zoom_level),
        key=stable_key
    )

    # 座標邏輯處理 (放置在渲染之後，確保 rerun 能立即看到點)
    if coords:
        current_coord_id = f"{coords['x']}_{coords['y']}"
        if st.session_state.last_processed_coords != current_coord_id:
            rx, ry = coords['x'] / coords['width'], coords['y'] / coords['height']

            if op_mode == "點選移除":
                candidates = []
                for idx, m in enumerate(st.session_state.marker_data):
                    dist = math.sqrt((m['rel_x'] - rx) ** 2 + (m['rel_y'] - ry) ** 2)
                    if dist <= HIT_RADIUS_RATIO:
                        candidates.append((dist, idx))
                if candidates:
                    candidates.sort(key=lambda x: x[0])
                    st.session_state.marker_data.pop(candidates[0][1])
                    for idx, m in enumerate(st.session_state.marker_data): m["序號"] = idx + 1
                    st.session_state.last_processed_coords = current_coord_id
                    st.rerun()

            elif op_mode == "新增標註" and st.session_state.active_tag:
                # 建立新標註
                new_pt = {"序號": 0, "位置": cur_loc, "標籤": st.session_state.active_tag, "備註": memo, "rel_x": rx,
                          "rel_y": ry}
                if "#" in insert_pos:
                    st.session_state.marker_data.append(new_pt)
                else:
                    idx = int(insert_pos.split(":")[-1]) - 1
                    st.session_state.marker_data.insert(idx, new_pt)

                # 重新排序
                for idx, m in enumerate(st.session_state.marker_data): m["序號"] = idx + 1

                # ✨ 強制清空備註欄：改變 Widget 的 Key
                st.session_state.memo_reset_trigger += 1

                # 更新狀態並強制刷新，標註點會立刻出現
                st.session_state.last_processed_coords = current_coord_id
                st.rerun()

    # 清單顯示
    if st.session_state.marker_data:
        st.markdown("---")
        st.subheader("📋 標註清單")
        data_df = pd.DataFrame(st.session_state.marker_data).drop(columns=['rel_x', 'rel_y'])
        st.dataframe(data_df, hide_index=True, use_container_width=True)