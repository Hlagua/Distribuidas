from flask import Flask, jsonify, request
import pyodbc
import time
import threading
import cetifi
import pytds

app = Flask(__name__)
produck_lock = threading.Lock()

def getConnection():
    return pyodbc.connect(
        "DRIVER={ODBC Driver 17 for SQL Server};"
        "SERVER=ad-2026-henry.database.windows.net;"
        "DATABASE=AppDistribuidas_2026_DB;"
        "UID=henry;" 
        "PWD=@Hdlf6116;"
        'TrustServerCertificate=yes'
    )

def getConeccion():
    return pytds.connect(
        server=os.environ["DB_SERVER"],
        database=os.environ['DB_NAME'],
        user=os.environ['DB_USER'],
        password=os.environ['DB_PASSWORD'],
        port=1433,
        cafile=certifi.where(),
        validate_host=True
    )




@app.route('/test-db', methods=['GET'])
def test_db():
    try:
        conn = getConnection()
        cursor = conn.cursor()
        cursor.execute("select DB_NAME()")
        database = cursor.fetchone()[0]
        conn.close()
        return jsonify({
            "mensaje": "conexion exitosa",
            "base_datos": database
        }), 200
    except Exception as e:
        return jsonify({
            "mensaje": "error",
            "error": str(e)
        }), 500

# Obtener con la vista (Se agregó 'version' al SELECT)
@app.route('/api/products', methods=['GET'])
def get_productos():
    try:
        conn = getConnection()
        cursor = conn.cursor()

        cursor.execute("SELECT id, names, price, stock, version FROM products_vw")
        productos = []
        for row in cursor.fetchall():
            productos.append({
                "id": row.id,
                "names": row.names,
                "price": row.price,
                "stock": row.stock,
                "version": row.version
            })

        cursor.close()
        conn.close()
        return jsonify(productos), 200
    except Exception as e:  
        return jsonify({
            "mensaje": "error",
            "error": str(e)
        }), 500

# API para obtener un producto
@app.route('/api/products/<int:id>', methods=['GET'])
def get_producto(id):
    try:
        conn = getConnection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, names, price, stock, version FROM products WHERE id = ?", id)
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if row:
            producto = {
                "id": row.id,
                "names": row.names,
                "price": row.price,
                "stock": row.stock,
                "version": row.version
            }
            return jsonify(producto), 200
        else:
            return jsonify({"mensaje": "Producto no encontrado"}), 404
    except Exception as e:
        return jsonify({
            "mensaje": "error",
            "error": str(e)
        }), 500

# API para crear un producto
@app.route('/api/products', methods=['POST'])
def create_producto():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"mensaje": "no hay datos"}), 400

        names = data.get('names')
        price = data.get('price')
        stock = data.get('stock')

        if not names or price is None or stock is None:
            return jsonify({"mensaje": "faltan datos"}), 400

        conn = getConnection()
        cursor = conn.cursor()
        cursor.execute("exec products_insert_sp ?, ?, ?", (names, price, stock))
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"mensaje": "Producto creado exitosamente"}), 201
    except Exception as e:
        return jsonify({
            "mensaje": "error",
            "error": str(e)
        }), 500

# API 4: Update sin controles
@app.route('/api/products', methods=['PUT'])
def update_producto():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "no hay datos"}), 400

        conn = getConnection()
        cursor = conn.cursor()
        time.sleep(5) 

        cursor.execute("update products set names=?, price=?, stock=? where id=?",
                       data.get('names'), data.get('price'), data.get('stock'), data.get('id'))

        if cursor.rowcount == 0:
            conn.rollback()
            cursor.close()
            conn.close()
            return jsonify({"msg": "registro no encontrado"}), 404

        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"msg": "producto actualizado exitosamente"}), 200 
    except Exception as e:
        return jsonify({
            "error": "error al actualizar producto",
            "msg": str(e)
        }), 500

# API 5: Update con bloqueo
@app.route('/api/products/lock', methods=['PUT'])
def update_lock():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "no hay datos"}), 400

        with produck_lock:
            print("Entra al bloqueo")
            conn = getConnection()
            cursor = conn.cursor()
            cursor.execute("update products set names=?, price=?, stock=? where id=?",
                           data.get('names'), data.get('price'), data.get('stock'), data.get('id'))
            if cursor.rowcount == 0:
                conn.rollback()
                cursor.close()
                conn.close()
                return jsonify({"msg": "registro no encontrado"}), 404
            conn.commit()
            cursor.close()
            conn.close() 
            print("Sale del bloqueo")

        return jsonify({"msg": "producto actualizado exitosamente con bloqueo"}), 200
    except Exception as e:
        return jsonify({
            "error": "error al actualizar producto con bloqueo",
            "msg": str(e)
        }), 500

# API 6: Update con control de versiones (Optimistic Concurrency)
@app.route('/api/products/version', methods=['PUT'])
def update_version():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "no hay datos"}), 400
        if data.get("version") is None:
            return jsonify({"error": "Faltan parametros (version)"}), 400

        conn = getConnection()
        cursor = conn.cursor()
        
        # Corregido 's1' por '+ 1'
        cursor.execute("update products set names=?, price=?, stock=?, version=version + 1 where id=? and version=?",
                       data.get('names'), data.get('price'), data.get('stock'), data.get('id'), data.get('version'))
        
        if cursor.rowcount == 0:
            cursor.execute("SELECT version FROM products WHERE id = ?", data.get('id'))
            row = cursor.fetchone()
            conn.rollback()
            cursor.close()
            conn.close()
            if row:
                producto_actual = {"version": row.version}
                return jsonify({
                    "msg": "ya actualizaron este registro",
                    "error": producto_actual
                }), 409
            else:
                return jsonify({"msg": "registro no encontrado o version incorrecta"}), 404

        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"msg": "producto actualizado con exito"}), 200
    except Exception as e:
        return jsonify({
            "error": "error al actualizar producto con version",
            "msg": str(e)
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)