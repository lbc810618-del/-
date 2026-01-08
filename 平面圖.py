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
st.set_page_config(
    page_title="專業標註系統",
    layout="wide",
    initial_sidebar_state="collapsed"  # 手機平板友善：預設收起側邊欄
)

COLOR_MAP = {
    "商品": "#FF5252", "價格": "#FFD740", "清潔": "#69F0AE",
    "備品": "#448AFF", "流程": "#E040FB", "其他": "#90A4AE"
}

# 繪圖與判定參數
FIXED_FONT_SCALE = 0.020
DRAW_RADIUS_RATIO = 0.012
HIT_RADIUS_RATIO = 0.015

# --- 狀態初始化 ---
if "marker_data" not in st.session_state: st.session_state.marker_data = []
if "active_tag" not in st.session_state: st.session_state.active_tag = ""
if "zoom_level" not in st.session_state: st.session_state.zoom_level = 1.0
if "rotation_angle" not in st.session_state: st.session_state.rotation_angle = 0
if "file_id" not in st.session_state: st.session_state.file_id = None
if "last_processed_coords" not in st.session_state: st.session_state.last_processed_coords = None
if "memo_reset_trigger" not in st.session_state: st.session_state.memo_reset_trigger = 0

# 2. 核心 CSS
active_color = COLOR_MAP.get(st.session_state.active_tag, "#448AFF")
st.markdown(f"""
    <style>
    .block-container {{ padding-top: 3.5rem !important; }}
    .stButton button {{ height: 40px !important; border-radius: 8px !important; font-weight: 800 !important; }}
    div[data-testid="stHorizontalBlock"] button[kind="primary"] {{
        background-color: {active_color} !important;
        color: black !important;
        border: 2px solid #333 !important;
    }}
    .stImage {{ background-color: #f0f2f6; border-radius: 10px; overflow: hidden; }}
    /* 優化平板觸控區域 */
    div[data-testid="stImageCoordinates"] {{ cursor: crosshair; }}
    </style>
    """, unsafe_allow_html=True)


# --- 優化函數區 ---

@st.cache_data(show_spinner=False)
def load_processed_images(uploaded_file):
    """
    核心優化：同時讀取原圖(用於導出)與建立縮圖(用於平板顯示)
    """
    original_img = None

    # 1. 讀取原始檔案
    if uploaded_file.type == "application/pdf":
        pdf_data = uploaded_file.read()
        doc = fitz.open(stream=pdf_data, filetype="pdf")
        page = doc.load_page(0)
        # 設定為 1.5 倍縮放，兼顧清晰度與記憶體
        pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
        original_img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        doc.close()
    else:
        original_img = Image.open(uploaded_file).convert("RGB")

    # 2. 建立顯示用縮圖 (限制寬度 1000px，大幅提升平板效能)
    display_width = 1000
    w_percent = (display_width / float(original_img.size[0]))

    if w_percent < 1:
        h_size = int((float(original_img.size[1]) * float(w_percent)))
        view_img = original_img.resize((display_width, h_size), Image.Resampling.LANCZOS)
    else:
        view_img = original_img.copy()

    return original_img, view_img


@st.cache_data(show_spinner=False)
def get_rotated_view(image, angle):
    """快取旋轉後的背景圖，避免每次 rerun 都重算"""
    if angle == 0:
        return image
    return image.rotate(-angle, expand=True)


@st.cache_resource
def get_cached_font(size):
    # 嘗試載入系統中文字體，若無則使用預設
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

        # 呼叫優化後的讀取函數
        base_img, view_img = load_processed_images(uploaded_file)

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

        # --- 導出邏輯：使用 base_img (高畫質原圖) ---
        export_img = base_img.copy()
        if st.session_state.rotation_angle != 0:
            export_img = export_img.rotate(-st.session_state.rotation_angle, expand=True)

        ew, eh = export_img.size
        edraw = ImageDraw.Draw(export_img)
        eradius = ew * DRAW_RADIUS_RATIO
        efont = get_cached_font(int(ew * FIXED_FONT_SCALE))

        for m in st.session_state.marker_data:
            # 使用相對座標計算，確保位置正確
            ex, ey = m['rel_x'] * ew, m['rel_y'] * eh
            ec = COLOR_MAP.get(m['標籤'], "#000000")
            edraw.ellipse([ex - eradius, ey - eradius, ex + eradius, ey + eradius], fill=ec, outline="white", width=2)
            edraw.text((ex, ey), str(m['序號']), fill="black", font=efont, anchor="mm")

        img_byte_arr = io.BytesIO()
        export_img.save(img_byte_arr, format='JPEG', quality=95)  # 高品質存檔

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
        op_mode = st.radio("模式", ["新增標註", "點選移除"], horizontal=True, label_visibility="collapsed")
    with t_col[1]:
        next_n = len(st.session_state.marker_data) + 1
        pos_opts = [f"#{next_n}"] + [f"插入:{i + 1}" for i in range(len(st.session_state.marker_data))]
        insert_pos = st.selectbox("序號", options=pos_opts, disabled=(op_mode == "點選移除"),
                                  label_visibility="collapsed")
    with t_col[2]:
        cur_loc = st.selectbox("位置", options=["騎樓", "收銀", "生鮮", "日配", "加一", "加二", "百貨", "菸酒"],
                               disabled=(op_mode == "點選移除"), label_visibility="collapsed")
    with t_col[3]:
        # ✨ 動態 Key 確保點擊後清空
        memo = st.text_input(
            "備註",
            placeholder="輸入備註...",
            key=f"memo_input_{st.session_state.memo_reset_trigger}",
            disabled=(op_mode == "點選移除"),
            label_visibility="collapsed"
        )

    # 標籤按鈕列
    b_cols = st.columns(6)
    for i, name in enumerate(COLOR_MAP.keys()):
        is_active = (name == st.session_state.active_tag)
        # 按鈕邏輯
        if b_cols[i].button(name, use_container_width=True, key=f"btn_{name}",
                            type="primary" if is_active else "secondary", disabled=(op_mode == "點選移除")):
            st.session_state.active_tag = name
            st.rerun()

    st.markdown("---")

    # --- 圖片顯示優化邏輯 ---
    # 1. 使用快取的旋轉底圖 (使用 view_img 小圖)
    rotated_bg = get_rotated_view(view_img, st.session_state.rotation_angle)
    display_img = rotated_bg.copy()

    mw, mh = display_img.size
    mdraw = ImageDraw.Draw(display_img)

    # 字體與圓圈大小會自動隨縮圖比例適應
    p_radius = mw * DRAW_RADIUS_RATIO
    p_font = get_cached_font(int(mw * FIXED_FONT_SCALE))

    # 繪製標註點
    for m in st.session_state.marker_data:
        px, py = m['rel_x'] * mw, m['rel_y'] * mh
        c = COLOR_MAP.get(m['標籤'], "#000000")
        mdraw.ellipse([px - p_radius, py - p_radius, px + p_radius, py + p_radius], fill=c, outline="white", width=2)
        mdraw.text((px, py), str(m['序號']), fill="black", font=p_font, anchor="mm")

    # ✨ 穩定 Key：不包含 active_tag 以防止閃爍
    stable_key = f"map_{st.session_state.file_id}_{st.session_state.zoom_level}_{st.session_state.rotation_angle}"

    with st.container():
        coords = streamlit_image_coordinates(
            display_img,
            width=int(mw * st.session_state.zoom_level),
            key=stable_key
        )

    # --- 點擊後的資料處理 ---
    if coords:
        current_coord_id = f"{coords['x']}_{coords['y']}"

        # 只有當點擊新位置時才執行
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
                new_pt = {"序號": 0, "位置": cur_loc, "標籤": st.session_state.active_tag, "備註": memo, "rel_x": rx,
                          "rel_y": ry}

                if "#" in insert_pos:
                    st.session_state.marker_data.append(new_pt)
                else:
                    idx = int(insert_pos.split(":")[-1]) - 1
                    st.session_state.marker_data.insert(idx, new_pt)

                # 重編序號
                for idx, m in enumerate(st.session_state.marker_data): m["序號"] = idx + 1

                # 觸發備註欄清空
                st.session_state.memo_reset_trigger += 1

                # 立即刷新介面
                st.session_state.last_processed_coords = current_coord_id
                st.rerun()

    # 清單顯示
    if st.session_state.marker_data:
        st.markdown("---")
        st.subheader("📋 標註清單")
        data_df = pd.DataFrame(st.session_state.marker_data).drop(columns=['rel_x', 'rel_y'])
        st.dataframe(data_df, hide_index=True, use_container_width=True)