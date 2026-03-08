import pandas as pd
import requests
import time
import numpy as np

# ==========================================
# 1. PERSIAPAN DATA MENTAH
# ==========================================
print("Membaca file DataLoggerGPSnew.xlsx...")
df_raw = pd.read_excel('GPS_LOGGER.xlsx')

total_awal = len(df_raw)

# Membersihkan koordinat error/kosong (Latitude atau Longitude = 0.0)
df_clean = df_raw[(df_raw['Latitude'] != 0.0) & (df_raw['Longitude'] != 0.0)].copy()
df_clean.reset_index(drop=True, inplace=True)
print(f"Data dibersihkan: {total_awal - len(df_clean)} baris error dihapus.")

# ==========================================
# 2. FUNGSI API OSRM MAP MATCHING (LOKAL)
# ==========================================
def get_osrm_match(coords_list):
    """
    Mengirim daftar koordinat ke server OSRM lokal via Docker.
    """
    # Menggabungkan koordinat menjadi string: lon,lat;lon,lat;...
    coords_str = ";".join([f"{lon},{lat}" for lon, lat in coords_list])
    
    # Radius pencarian toleransi GPS (20 meter dari titik asli)
    radiuses = ";".join(["20"] * len(coords_list))
    
    # URL mengarah ke localhost (127.0.0.1) port 5000 milik Docker
    url = f"http://127.0.0.1:5000/match/v1/driving/{coords_str}?overview=false&radiuses={radiuses}"
    
    try:
        response = requests.get(url)
        data = response.json()
        
        if data.get('code') == 'Ok':
            matched_points = []
            for point in data['tracepoints']:
                if point is not None:
                    # OSRM mengembalikan [Longitude, Latitude]
                    matched_points.append((point['location'][1], point['location'][0])) # (Lat, Lon)
                else:
                    matched_points.append((np.nan, np.nan)) # Jika gagal dicocokkan
            return matched_points
        else:
            print(f"Peringatan OSRM: {data.get('message', 'Unknown error')}")
            return [(np.nan, np.nan)] * len(coords_list)
            
    except Exception as e:
        print(f"Gagal menghubungi server OSRM lokal: {e}")
        return [(np.nan, np.nan)] * len(coords_list)

# ==========================================
# 3. PROSES CHUNKING (MEMOTONG DATA)
# ==========================================
# Memotong per 50 titik agar URL request tidak terlalu panjang
chunk_size = 50
fixed_lat = []
fixed_lon = []

print(f"Memulai proses Map Matching ke server OSRM lokal untuk {len(df_clean)} titik...")

for i in range(0, len(df_clean), chunk_size):
    chunk = df_clean.iloc[i:i+chunk_size]
    
    # OSRM meminta urutan (Longitude, Latitude)
    coords_list = list(zip(chunk['Longitude'], chunk['Latitude']))
    
    matched = get_osrm_match(coords_list)
    
    for lat, lon in matched:
        fixed_lat.append(lat)
        fixed_lon.append(lon)
        
    print(f"Memproses baris {i} hingga {min(i + chunk_size, len(df_clean))} dari {len(df_clean)}...")
    
    # Jeda dikecilkan menjadi 0.1 detik karena server lokal jauh lebih kuat dan tidak memblokir IP
    time.sleep(0.1)

# ==========================================
# 4. PENYIMPANAN HASIL
# ==========================================
df_clean['Fixed_Lat'] = fixed_lat
df_clean['Fixed_Lon'] = fixed_lon

# Hapus baris yang gagal di-matching oleh OSRM (bernilai NaN)
df_final = df_clean.dropna(subset=['Fixed_Lat', 'Fixed_Lon']).copy()

# Menyusun ulang kolom agar rapi untuk dashboard
df_final = df_final[['Tanggal', 'Waktu', 'Fixed_Lat', 'Fixed_Lon', 'Speed']]

# Simpan ke Excel
nama_file_output = 'gps_osrm_logger.xlsx'
df_final.to_excel(nama_file_output, index=False)

print("\n🎉 Proses Selesai!")
print(f"File berhasil disimpan dengan nama: {nama_file_output}")