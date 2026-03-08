import cv2
import os

# =============================
# Konfigurasi
# =============================
video_path = 'Dataset video UIN(2).mp4'
output_folder = 'frames_5(1)fps'
target_fps = 5

os.makedirs(output_folder, exist_ok=True)

# =============================
# Buka video
# =============================
cap = cv2.VideoCapture(video_path)

if not cap.isOpened():
    print("Gagal membuka video")
    exit()

# FPS asli video
original_fps = cap.get(cv2.CAP_PROP_FPS)
frame_interval = original_fps / target_fps

print(f"FPS video asli : {original_fps}")
print(f"Target FPS     : {target_fps}")

frame_count = 0
saved_count = 0
accumulator = 0.0

# =============================
# Ekstrak frame
# =============================
while True:
    ret, frame = cap.read()
    if not ret:
        break

    accumulator += 1

    if accumulator >= frame_interval:
        filename = os.path.join(
            output_folder, f"frame_{saved_count:06d}.jpg"
        )
        cv2.imwrite(filename, frame)
        saved_count += 1
        accumulator = 0

    frame_count += 1

cap.release()

print(f"Selesai!")
print(f"Total frame dibaca : {frame_count}")
print(f"Total frame disimpan (@5fps): {saved_count}")