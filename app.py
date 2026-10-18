from flask import Flask, render_template, request, jsonify
import sqlite3
import datetime
import os

app = Flask (__name__)

def get_db_connection():
    if os.environ.get('VERCEL'):
        db_path = '/tmp/database.db'
    else:
        db_path = 'database.db'
        
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    # Tabel Produk
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS produk (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kode TEXT UNIQUE NOT NULL,
            nama TEXT NOT NULL,
            harga REAL NOT NULL,
            stok INTEGER NOT NULL,
            kategori TEXT NOT NULL
        )
    ''')
    # Tabel Transaksi Utama
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transaksi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            faktur TEXT UNIQUE NOT NULL,
            total REAL NOT NULL,
            diskon REAL NOT NULL,
            total_akhir REAL NOT NULL,
            bayar REAL NOT NULL,
            kembali REAL NOT NULL,
            metode_bayar TEXT NOT NULL,
            tanggal TEXT NOT NULL
        )
    ''')
    # Tabel Detail Transaksi (Item yang dibeli)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS detail_transaksi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            faktur TEXT NOT NULL,
            nama_produk TEXT NOT NULL,
            harga REAL NOT NULL,
            qty INTEGER NOT NULL,
            subtotal REAL NOT NULL,
            FOREIGN KEY (faktur) REFERENCES transaksi (faktur)
        )
    ''')
    
    # Isi data awal jika database masih kosong
    cursor.execute("SELECT COUNT(*) FROM produk")
    if cursor.fetchone()[0] == 0:
        sample_produk = [
            ("P001", "Espresso Premium", 18000, 50, "Minuman"),
            ("P002", "Iced Cafe Latte", 24000, 40, "Minuman"),
            ("P003", "Croissant Butter", 22000, 25, "Makanan"),
            ("P004", "Matcha Latte", 26000, 30, "Minuman"),
            ("P005", "French Fries", 15000, 60, "Makanan")
        ]
        cursor.executemany("INSERT INTO produk (kode, nama, harga, stok, kategori) VALUES (?, ?, ?, ?, ?)", sample_produk)
        conn.commit()
    conn.close()

init_db()

# --- ROUTE HALAMAN UTAMA ---
@app.route('/')
def index():
    return render_template('pos.html')

# --- API PRODUK (GET, POST, DELETE) ---
@app.route('/api/produk', methods=['GET'])
def get_produk():
    conn = get_db_connection()
    produk_list = conn.execute("SELECT * FROM produk ORDER BY id DESC").fetchall()
    conn.close()
    return jsonify([dict(p) for p in produk_list])

@app.route('/api/produk', methods=['POST'])
def tambah_produk():
    try:
        data = request.json
        kode = data.get('kode')
        nama = data.get('nama')
        harga = float(data.get('harga', 0))
        stok = int(data.get('stok', 0))
        kategori = data.get('kategori', 'Umum')

        if not kode or not nama or harga <= 0:
            return jsonify({'success': False, 'message': 'Data produk tidak valid!'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO produk (kode, nama, harga, stok, kategori) VALUES (?, ?, ?, ?, ?)",
            (kode, nama, harga, stok, kategori)
        )
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Produk berhasil ditambahkan!'})
    except sqlite3.IntegrityError:
        return jsonify({'success': False, 'message': 'Kode produk sudah ada!'}), 400
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/produk/<int:id>', methods=['DELETE'])
def hapus_produk(id):
    try:
        conn = get_db_connection()
        conn.execute("DELETE FROM produk WHERE id = ?", (id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Produk berhasil dihapus!'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# --- API CHECKOUT / TRANSAKSI ---
@app.route('/api/checkout', methods=['POST'])
def checkout():
    try:
        data = request.json
        items = data.get('items', [])
        bayar = float(data.get('bayar', 0))
        metode_bayar = data.get('metode_bayar', 'Cash')
        
        if not items:
            return jsonify({'success': False, 'message': 'Keranjang kosong!'}), 400
        
        total = sum(item['harga'] * item['qty'] for item in items)
        
        # Logika Diskon Bertingkat (Sesuai Materi Percabangan)
        diskon = 0
        if total >= 100000:
            diskon = total * 0.10  # Diskon 10%
        elif total >= 50000:
            diskon = total * 0.05  # Diskon 5%
            
        total_akhir = total - diskon
        
        if bayar < total_akhir:
            return jsonify({'success': False, 'message': f'Uang pembayaran kurang! Minimum: Rp {total_akhir:,.0f}'}), 400

        kembali = bayar - total_akhir
        faktur = "INV-" + datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        waktu_sekarang = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Perulangan Potong Stok & Simpan Detail
        for item in items:
            # Cek stok cukup
            prod = cursor.execute("SELECT stok FROM produk WHERE id = ?", (item['id'],)).fetchone()
            if not prod or prod['stok'] < item['qty']:
                conn.close()
                return jsonify({'success': False, 'message': f"Stok {item['nama']} tidak mencukupi!"}), 400
                
            cursor.execute("UPDATE produk SET stok = stok - ? WHERE id = ?", (item['qty'], item['id']))
            cursor.execute('''
                INSERT INTO detail_transaksi (faktur, nama_produk, harga, qty, subtotal)
                VALUES (?, ?, ?, ?, ?)
            ''', (faktur, item['nama'], item['harga'], item['qty'], item['harga'] * item['qty']))
            
        cursor.execute('''
            INSERT INTO transaksi (faktur, total, diskon, total_akhir, bayar, kembali, metode_bayar, tanggal)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (faktur, total, diskon, total_akhir, bayar, kembali, metode_bayar, waktu_sekarang))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'faktur': faktur,
            'total': total,
            'diskon': diskon,
            'total_akhir': total_akhir,
            'bayar': bayar,
            'kembali': kembali,
            'tanggal': waktu_sekarang,
            'items': items
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error Server: {str(e)}'}), 500

# --- API LAPORAN / RIWAYAT TRANSAKSI ---
@app.route('/api/laporan', methods=['GET'])
def get_laporan():
    conn = get_db_connection()
    transaksi = conn.execute("SELECT * FROM transaksi ORDER BY id DESC LIMIT 20").fetchall()
    total_omset = conn.execute("SELECT SUM(total_akhir) FROM transaksi").fetchone()[0] or 0
    total_transaksi = conn.execute("SELECT COUNT(*) FROM transaksi").fetchone()[0] or 0
    conn.close()
    
    return jsonify({
        'total_omset': total_omset,
        'total_transaksi': total_transaksi,
        'transaksi': [dict(t) for t in transaksi]
    })

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
