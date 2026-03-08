import streamlit as st
import cv2
import pandas as pd
import folium
from streamlit_folium import st_folium
import tempfile
import os
from datetime import datetime, timedelta
from ultralytics import YOLO
import base64
import math
from geopy.distance import geodesic 

# ================= KONFIGURASI HALAMAN =================
st.set_page_config(page_title="Dashboard Pothole UIN", layout="wide")
st.title("🛣️ Dashboard Deteksi & Pemetaan Lubang Jalan (YOLOv11)")
st.markdown("Sistem Deteksi, Visualisasi GPS, dan Perhitungan Jarak Tempuh Otomatis")

# ================= INISIALISASI SESSION STATE =================
if 'proses_selesai' not in st.session_state:
    st.session_state.proses_selesai = False
if 'df_hasil' not in st.session_state:
    st.session_state.df_hasil = None
if 'final_video_path' not in st.session_state:
    st.session_state.final_video_path = None
if 'final_potholes' not in st.session_state:
    st.session_state.final_potholes = 0
if 'final_distance' not in st.session_state:
    st.session_state.final_distance = 0.0

# ================= FUNGSI CACHE =================
@st.cache_resource
def load_model(model_path):
    return YOLO(model_path)

def get_gps_at_timestamp(target_time, df_gps):
    df_gps['diff'] = (df_gps['DT_Full'] - target_time).abs()
    idx_min = df_gps['diff'].idxmin()
    val_min = df_gps.loc[idx_min, 'diff'].total_seconds()
    if val_min <= 5.0:
        return df_gps.loc[idx_min]
    return None

# ================= SIDEBAR (INPUT DATA) =================
with st.sidebar:
    st.header("📂 1. Upload Data")
    uploaded_model = st.file_uploader("Upload Model YOLO (.pt)", type=['pt'])
    uploaded_video = st.file_uploader("Upload Video Dashcam (.mp4)", type=['mp4', 'avi'])
    uploaded_gps   = st.file_uploader("Upload Data GPS (.xlsx, .csv)", type=['xlsx', 'csv'])
    
    st.header("⚙️ 2. Konfigurasi Waktu")
    video_start = st.text_input("Waktu Mulai Video (HH:MM:SS)", value="12:19:51")
    
    st.markdown("---")
    st.header("🎛️ 3. Kalibrasi Sistem")
    
    time_offset = st.slider("Time Offset / Lookahead (Detik)", -5.0, 20.0, 5.0, 0.1)
    conf_thresh = st.slider("Confidence Threshold", 0.10, 1.00, 0.70, 0.01)
    batas_dekat = st.slider("Garis Batas Jarak (% dari Atas Layar)", 10, 100, 60, 5)
    jarak_min_pixel = st.slider("Jarak Visual Antar Lubang (Pixel)", 10, 300, 100, 10)
    batas_detik = st.slider("Batasi Durasi Video (Detik)", 0, 600, 0, 10, help="Isi 0 untuk full video.")

    mulai_btn = st.button("🚀 Mulai Pemrosesan", use_container_width=True)

    if st.button("🔄 Reset Dashboard"):
        st.session_state.proses_selesai = False
        st.session_state.df_hasil = None
        st.session_state.final_video_path = None
        st.session_state.final_potholes = 0
        st.session_state.final_distance = 0.0
        st.rerun()

# ================= PROSES VIDEO =================
if mulai_btn:
    if not (uploaded_model and uploaded_video and uploaded_gps):
        st.error("⚠️ Mohon upload Model, Video, dan File GPS terlebih dahulu!")
    else:
        with st.spinner('Menyiapkan file...'):
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pt') as tmp_model:
                tmp_model.write(uploaded_model.read())
                model_path = tmp_model.name
            
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as tmp_vid:
                tmp_vid.write(uploaded_video.getbuffer())
                video_path = tmp_vid.name
                
            if uploaded_gps.name.endswith('.csv'):
                df_gps_input = pd.read_csv(uploaded_gps)
            else:
                df_gps_input = pd.read_excel(uploaded_gps)

            df_gps_input['Tanggal'] = df_gps_input['Tanggal'].astype(str)
            df_gps_input['Waktu'] = df_gps_input['Waktu'].astype(str)
            df_gps_input['DT_Full'] = pd.to_datetime(df_gps_input['Tanggal'] + ' ' + df_gps_input['Waktu'], dayfirst=True, format='mixed')
            
            base_date = df_gps_input['DT_Full'].iloc[0].date()
            start_dt = datetime.strptime(f"{base_date} {video_start}", "%Y-%m-%d %H:%M:%S")

        model = load_model(model_path)
        cap = cv2.VideoCapture(video_path)
        
        if not cap.isOpened():
            st.error("🚨 ERROR: OpenCV gagal membaca video! Pastikan file video tidak korup.")
            st.stop()
            
        fps = cap.get(cv2.CAP_PROP_FPS) or 60.0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        # PERSIAPAN PEREKAM VIDEO OUTPUT (Format WebM agar bisa diplay di Streamlit)
        out_temp = tempfile.NamedTemporaryFile(delete=False, suffix='.webm')
        out_video_path = out_temp.name
        out_temp.close()
        fourcc = cv2.VideoWriter_fourcc(*'vp80')
        out_video = cv2.VideoWriter(out_video_path, fourcc, fps, (width, height))
        
        st.success("✅ File siap! Memulai pemrosesan...")
        
        col1, col2 = st.columns([2, 1])
        with col1:
            st.markdown("#### 📹 Live Detection Feed")
            frame_placeholder = st.empty()
        with col2:
            st.markdown("#### 📊 Status Sementara")
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            st.markdown("---")
            m1, m2 = st.columns(2)
            metric_pothole = m1.empty()
            metric_distance = m2.empty()
            
            metric_pothole.metric("Total Lubang Terdeteksi", 0)
            metric_distance.metric("Jarak Tempuh", "0.0 M")

        detected_data = []
        counted_ids = set() 
        saved_pixel_memory = [] 
        pothole_count = 0
        total_distance_m = 0.0
        last_valid_coords = None

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
                
            frame_id = cap.get(cv2.CAP_PROP_POS_FRAMES)
            
            tinggi_frame = frame.shape[0]
            lebar_frame = frame.shape[1]
            y_batas = int(tinggi_frame * (batas_dekat / 100.0))
            
            if frame_id % 10 == 0:
                progress = min(int((frame_id / total_frames) * 100), 100)
                progress_bar.progress(progress)
                status_text.text(f"Memproses Frame {int(frame_id)} / {total_frames}")

            current_time = start_dt + timedelta(seconds=frame_id / fps)
            target_time = current_time + timedelta(seconds=time_offset)
            current_time_sec = current_time.timestamp()
            
            durasi_berjalan = frame_id / fps
            if batas_detik > 0 and durasi_berjalan >= batas_detik:
                st.info(f"🛑 Berhenti otomatis pada detik ke-{batas_detik} (Mode Testing).")
                break 

            row = get_gps_at_timestamp(target_time, df_gps_input)
            if row is not None:
                current_coords = (row['Fixed_Lat'], row['Fixed_Lon'])
                
                if last_valid_coords is not None and current_coords != last_valid_coords:
                    dist = geodesic(last_valid_coords, current_coords).meters
                    total_distance_m += dist
                    
                    if total_distance_m >= 1000:
                        metric_distance.metric("Jarak Tempuh", f"{total_distance_m / 1000:.2f} KM")
                    else:
                        metric_distance.metric("Jarak Tempuh", f"{total_distance_m:.1f} M")
                        
                last_valid_coords = current_coords

            results = model.track(frame, conf=conf_thresh, imgsz=832, persist=True, tracker="botsort.yaml", verbose=False)
            
            if results[0].boxes is not None and results[0].boxes.id is not None:
                for box_data in results[0].boxes:
                    if box_data.id is None:
                        continue
                        
                    track_id = int(box_data.id[0]) 
                    x1, y1, x2, y2 = map(int, box_data.xyxy[0].tolist())
                    conf = float(box_data.conf[0])
                    
                    x_center = (x1 + x2) / 2
                    y_center = (y1 + y2) / 2
                    
                    if y2 >= y_batas:
                        if track_id not in counted_ids:
                            if row is not None:
                                is_really_new = True
                                
                                for px, py, p_time in saved_pixel_memory[-10:]:
                                    if (current_time_sec - p_time) < 3.0:
                                        jarak_layar = math.sqrt((x_center - px)**2 + (y_center - py)**2)
                                        if jarak_layar < jarak_min_pixel:
                                            is_really_new = False
                                            break
                                
                                counted_ids.add(track_id) 
                                
                                if is_really_new:
                                    saved_pixel_memory.append((x_center, y_center, current_time_sec))
                                    
                                    pothole_count += 1
                                    metric_pothole.metric("Total Lubang Terdeteksi", pothole_count)
                                    
                                    small_frame = cv2.resize(frame, (320, 240))
                                    _, buffer = cv2.imencode('.jpg', small_frame)
                                    img_base64 = base64.b64encode(buffer).decode('utf-8')

                                    detected_data.append({
                                        'ID_Lubang': track_id, 
                                        'Waktu_Asli': current_time.strftime('%H:%M:%S'),
                                        'Waktu_Offset': target_time.strftime('%H:%M:%S'),
                                        'Latitude': row['Fixed_Lat'],
                                        'Longitude': row['Fixed_Lon'],
                                        'Speed': row['Speed'],
                                        'Conf': conf,
                                        'Image_Base64': img_base64
                                    })
                            
                    warna_kotak = (0, 255, 0) if y2 >= y_batas else (0, 165, 255)
                    cv2.rectangle(frame, (x1, y1), (x2, y2), warna_kotak, 2)
                    cv2.putText(frame, f"ID:{track_id} Conf:{conf:.2f}", (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, warna_kotak, 2)

            # SIMPAN FRAME KE DALAM FILE VIDEO OUTPUT
            out_video.write(frame)

            if frame_id % 5 == 0:
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                frame_placeholder.image(frame_rgb, channels="RGB", use_container_width=True)

        cap.release()
        out_video.release() # Selesai merekam video
        
        # SIMPAN STATUS AKHIR KE MEMORI
        st.session_state.final_video_path = out_video_path
        st.session_state.final_potholes = pothole_count
        st.session_state.final_distance = total_distance_m
        
        progress_bar.progress(100)
        status_text.success("🎉 Pemrosesan Video Selesai!")
        
        if detected_data:
            st.session_state.df_hasil = pd.DataFrame(detected_data)
            st.session_state.proses_selesai = True
        else:
            st.warning("Tidak ada lubang yang terdeteksi.")

# ================= TAMPILKAN PETA DAN STATUS AKHIR =================
if st.session_state.proses_selesai and st.session_state.df_hasil is not None:
    st.markdown("---")
    
    st.markdown("### 🏁 Ringkasan Pemrosesan")
    c1, c2 = st.columns([2, 1])
    with c1:
        st.markdown("#### 📹 Putar Ulang Hasil Deteksi")
        # TAMPILKAN VIDEO YANG BISA DI-PLAY
        if st.session_state.final_video_path is not None:
            st.video(st.session_state.final_video_path)
            
    with c2:
        st.markdown("#### 📊 Status Keseluruhan")
        st.success("Tugas Selesai!")
        m1, m2 = st.columns(2)
        m1.metric("Total Lubang Terdeteksi", st.session_state.final_potholes)
        
        dist_m = st.session_state.final_distance
        if dist_m >= 1000:
            m2.metric("Jarak Tempuh", f"{dist_m / 1000:.2f} KM")
        else:
            m2.metric("Jarak Tempuh", f"{dist_m:.1f} M")
            
    st.markdown("---")
    
    st.markdown("### 🗺️ Hasil Pemetaan Geospasial")
    
    df_out = st.session_state.df_hasil
    df_tampil = df_out.drop(columns=['Image_Base64'])
    st.dataframe(df_tampil, use_container_width=True)
    
    avg_lat = df_out['Latitude'].mean()
    avg_lon = df_out['Longitude'].mean()
    m = folium.Map(location=[avg_lat, avg_lon], zoom_start=18)
    
    for _, r in df_out.iterrows():
        popup_html = f"""
        <div style="font-family: Arial; width: 320px;">
            <b style="font-size: 14px;">Lubang ID: {r['ID_Lubang']}</b><br>
            <span style="font-size: 12px; color: gray;">Waktu: {r['Waktu_Asli']} | Conf: {r['Conf']:.2f}</span>
            <hr style="margin: 5px 0;">
            <img src='data:image/jpeg;base64,{r['Image_Base64']}' style="width:100%; border-radius:5px;"><br>
        </div>
        """
        
        folium.CircleMarker(
            location=[r['Latitude'], r['Longitude']], 
            radius=6, color='black', weight=1.5,
            fill=True, fill_color='red', fill_opacity=1.0,
            popup=folium.Popup(popup_html, max_width=350)
        ).add_to(m)
    
    st_folium(m, width="100%", height=600, returned_objects=[])
    
    csv = df_tampil.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Download Laporan Excel (CSV)", data=csv, file_name="Hasil_Deteksi_Dashboard.csv", mime="text/csv")

    