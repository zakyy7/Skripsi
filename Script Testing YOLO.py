import cv2
import numpy as np
from ultralytics import YOLO

MODEL_PATH = 'best.pt' # Pakai model terbaru
VIDEO_PATH = 'Dataset Video UIN.mp4'
OUTPUT_PATH = 'hasil_filter_logika.mp4'
IMG_SIZE = 832
CONF_THRESHOLD = 0.70 

def is_valid_pothole(box, img_w, img_h):
    x1, y1, x2, y2 = box
    
    # 1. HITUNG UKURAN (Luas Area)
    area = (x2 - x1) * (y2 - y1)
    total_screen_area = img_w * img_h
    ratio_area = area / total_screen_area
    
    # Aturan A: Jika objek terlalu besar (> 25% layar), anggap Mobil/Bayangan Besar
    if ratio_area > 0.25: 
        return False, "Too Big (Car?)"

    # 2. HITUNG POSISI (Region of Interest)
    # Lubang jalanan biasanya ada di bagian tengah ke bawah.
    # Titik tengah kotak (Center Y)
    cy = (y1 + y2) / 2
    
    # Aturan B: Jika posisi objek ada di 1/3 bagian ATAS layar, anggap Kepala/Langit
    if cy < (img_h * 0.35): 
        return False, "Too High (Head/Sky)"

    # 3. HITUNG BENTUK (Aspect Ratio)
    w = x2 - x1
    h = y2 - y1
    aspect_ratio = w / h
    
    # Aturan C: Jika kotak kurus tinggi (seperti orang berdiri/tiang)
    # Rasio < 0.3 artinya tinggi 3x lipat lebar
    if aspect_ratio < 0.3:
        return False, "Too Tall (Person?)"

    return True, "Valid"

def main():
    model = YOLO(MODEL_PATH)
    cap = cv2.VideoCapture(VIDEO_PATH)
    
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = int(cap.get(cv2.CAP_PROP_FPS))
    out = cv2.VideoWriter(OUTPUT_PATH, cv2.VideoWriter_fourcc(*'mp4v'), fps, (w, h))

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret: break

        results = model.predict(frame, conf=CONF_THRESHOLD, imgsz=IMG_SIZE, verbose=False)
        
        # Gambar manual hanya yang lolos filter
        for box in results[0].boxes:
            coords = box.xyxy[0].tolist()
            conf = box.conf[0].item()
            
            # --- CEK FILTER ---
            is_valid, reason = is_valid_pothole(coords, w, h)
            
            x1, y1, x2, y2 = map(int, coords)
            
            if is_valid:
                # Gambar Kotak HIJAU (Valid Pothole)
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(frame, f"Pothole {conf:.2f}", (x1, y1-10), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            else:
                # (Opsional) Gambar Kotak MERAH tipis untuk debug (objek yang dibuang)
                # Bisa dihapus nanti kalau mau video bersih
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 1)
                cv2.putText(frame, reason, (x1, y1-10), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)

        out.write(frame)
        cv2.imshow("Logic Filter Test", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'): break

    cap.release()
    out.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()