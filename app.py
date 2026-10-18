from flask import Flask, render_template, request, jsonify
import sqlite3
import datetime

app = Flask(__name__)

def get_db_connection():
    if os.environ.get('VERCEL'):
        db_path = '/tmp/database.db'
    else:
        db_path = 'database.db'
        
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

# Inisialisasi Database
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
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
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transaksi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            faktur TEXT NOT NULL,
            total REAL NOT NULL,
            diskon REAL NOT NULL,
            total_akhir REAL NOT NULL,
            metode_bayar TEXT NOT NULL,
            tanggal TEXT NOT NULL
        )
    ''')
    
    # Masukkan data awal jika kosong
    cursor.execute("SELECT COUNT(*) FROM produk")
    if cursor.fetchone()[0] == 0:
        sample_produk = [
            ("P001", "Espresso Premium", 18000, 50, "Minuman"),
            ("P002", "Iced Cafe Latte", 24000, 40, "Minuman"),
            ("P003", "Croissant Butter", 22000, 25, "Makanan"),
            ("P004", "Matcha Latte", 26000, 30, "Minuman")
        ]
        cursor.executemany("INSERT INTO produk (kode, nama, harga, stok, kategori) VALUES (?, ?, ?, ?, ?)", sample_produk)
        conn.commit()
    conn.close()

init_db()

@app.route('/')
def index():
    return render_template('pos.html')

@app.route('/api/produk', methods=['GET'])
def get_produk():
    conn = get_db_connection()
    produk_list = conn.execute("SELECT * FROM produk").fetchall()
    conn.close()
    return jsonify([dict(p) for p in produk_list])

@app.route('/api/checkout', methods=['POST'])
def checkout():
    try:
        data = request.json
        items = data.get('items', [])
        metode_bayar = data.get('metode_bayar', 'Cash')
        
        if not items:
            return jsonify({'success': False, 'message': 'Keranjang kosong!'}), 400
        
        total = sum(item['harga'] * item['qty'] for item in items)
        
        # Percabangan Diskon Perusahaan
        diskon = 0
        if total >= 100000:
            diskon = total * 0.10 # Diskon 10%
        elif total >= 50000:
            diskon = total * 0.05 # Diskon 5%
            
        total_akhir = total - diskon
        faktur = "INV-" + datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        waktu_sekarang = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Potong Stok & Simpan Transaksi (Perulangan)
        for item in items:
            cursor.execute("UPDATE produk SET stok = stok - ? WHERE id = ?", (item['qty'], item['id']))
            
        cursor.execute('''
            INSERT INTO transaksi (faktur, total, diskon, total_akhir, metode_bayar, tanggal)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (faktur, total, diskon, total_akhir, metode_bayar, waktu_sekarang))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'faktur': faktur,
            'total': total,
            'diskon': diskon,
            'total_akhir': total_akhir,
            'tanggal': waktu_sekarang
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Terjadi kesalahan server: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(debug=True)
