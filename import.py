import os
import pandas as pd
import psycopg2

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "DE1",
    "user": "postgres",
    "password": "2281337"
}

# ПОИСК ФАЙЛОВ
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMPORT_DIR = os.path.join(BASE_DIR, "import")

def find_file(keywords):
    if not os.path.exists(IMPORT_DIR):
        raise Exception(f"Папка {IMPORT_DIR} не существует! Создай её рядом со скриптом.")

    for f in os.listdir(IMPORT_DIR):
        for k in keywords:
            if k.lower() in f.lower() and not f.startswith('~'):
                return os.path.join(IMPORT_DIR, f)

    files_in_dir = os.listdir(IMPORT_DIR)
    raise FileNotFoundError(f"Файл ({keywords}) не найден в {IMPORT_DIR}. В папке сейчас лежат: {files_in_dir}")

def read_data(path, is_points=False):
    if path.endswith('.csv'):
        return pd.read_csv(path, header=None if is_points else 'infer')
    else:
        return pd.read_excel(path, header=None if is_points else 0)

#SQL СХЕМА
SCHEMA_SQL = """
DROP SCHEMA public CASCADE;
CREATE SCHEMA public;

CREATE TABLE roles (role_id SERIAL PRIMARY KEY, name VARCHAR(100) UNIQUE NOT NULL);
CREATE TABLE categories (category_id SERIAL PRIMARY KEY, name VARCHAR(100) UNIQUE NOT NULL);
CREATE TABLE manufacturers (manufacturer_id SERIAL PRIMARY KEY, name VARCHAR(100) UNIQUE NOT NULL);
CREATE TABLE suppliers (supplier_id SERIAL PRIMARY KEY, name VARCHAR(100) UNIQUE NOT NULL);
CREATE TABLE units (unit_id SERIAL PRIMARY KEY, name VARCHAR(20) UNIQUE NOT NULL);
CREATE TABLE order_statuses (status_id SERIAL PRIMARY KEY, name VARCHAR(50) UNIQUE NOT NULL);
CREATE TABLE pickup_points (pickup_point_id SERIAL PRIMARY KEY, address VARCHAR(500) UNIQUE NOT NULL);

CREATE TABLE users (
    user_id SERIAL PRIMARY KEY,
    full_name VARCHAR(255) NOT NULL,
    login VARCHAR(255) UNIQUE NOT NULL,
    user_password VARCHAR(255) NOT NULL,
    role_id INTEGER REFERENCES roles(role_id) ON DELETE SET NULL
);

CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    article VARCHAR(50) UNIQUE NOT NULL,
    product_name VARCHAR(255) NOT NULL,
    price NUMERIC(10,2) NOT NULL CHECK (price >= 0),
    discount NUMERIC(5,2) DEFAULT 0 CHECK (discount >= 0),
    stock_quantity INTEGER DEFAULT 0 CHECK (stock_quantity >= 0),
    description TEXT,
    photo VARCHAR(255),
    unit_id INTEGER REFERENCES units(unit_id) ON DELETE SET NULL,
    supplier_id INTEGER REFERENCES suppliers(supplier_id) ON DELETE SET NULL,
    manufacturer_id INTEGER REFERENCES manufacturers(manufacturer_id) ON DELETE SET NULL,
    category_id INTEGER REFERENCES categories(category_id) ON DELETE SET NULL
);

CREATE TABLE orders (
    order_id SERIAL PRIMARY KEY,
    order_date DATE NOT NULL,
    delivery_date DATE,
    pickup_code INTEGER,
    status_id INTEGER REFERENCES order_statuses(status_id) ON DELETE SET NULL,
    pickup_point_id INTEGER REFERENCES pickup_points(pickup_point_id) ON DELETE SET NULL,
    user_id INTEGER REFERENCES users(user_id) ON DELETE SET NULL
);

CREATE TABLE order_items (
    order_item_id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    quantity INTEGER NOT NULL CHECK (quantity > 0)
);
"""

def get_or_create(cur, table, pk_col, name_col, value):
    if pd.isna(value) or str(value).strip() == "": return None
    val_str = str(value).strip()
    cur.execute(f"INSERT INTO {table} ({name_col}) VALUES (%s) ON CONFLICT ({name_col}) DO UPDATE SET {name_col} = EXCLUDED.{name_col} RETURNING {pk_col};", (val_str,))
    return cur.fetchone()[0]

def main():
    print("⏳ Подключение к БД...")
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    try:
        print("1. Очистка старой БД и создание правильных таблиц...")
        cur.execute(SCHEMA_SQL)

        # --- ИМПОРТ ---
        path_points = find_file(['point', 'пункт'])
        print(f"2. Читаем пункты выдачи из: {os.path.basename(path_points)}")
        points = read_data(path_points, is_points=True)
        point_map = {}
        for idx, row in points.iterrows():
            addr = str(row.iloc[0]).strip().strip('"')
            if addr:
                point_map[idx + 1] = get_or_create(cur, 'pickup_points', 'pickup_point_id', 'address', addr)

        path_users = find_file(['user', 'пользовател'])
        print(f"3. Читаем пользователей из: {os.path.basename(path_users)}")
        users = read_data(path_users)
        for _, row in users.iterrows():
            role_id = get_or_create(cur, 'roles', 'role_id', 'name', row["Роль сотрудника"])
            cur.execute("INSERT INTO users (full_name, login, user_password, role_id) VALUES (%s, %s, %s, %s) ON CONFLICT (login) DO NOTHING;",
                        (row["ФИО"], row["Логин"], row["Пароль"], role_id))

        path_tovar = find_file(['tovar', 'товар'])
        print(f"4. Читаем товары из: {os.path.basename(path_tovar)}")
        products = read_data(path_tovar)
        for _, row in products.iterrows():
            photo = row["Фото"] if pd.notna(row.get("Фото")) else "picture.png"
            unit_id = get_or_create(cur, 'units', 'unit_id', 'name', row["Единица измерения"])
            sup_id = get_or_create(cur, 'suppliers', 'supplier_id', 'name', row["Поставщик"])
            man_id = get_or_create(cur, 'manufacturers', 'manufacturer_id', 'name', row["Производитель"])
            cat_id = get_or_create(cur, 'categories', 'category_id', 'name', row["Категория товара"])

            cur.execute("""INSERT INTO products (article, product_name, price, discount, stock_quantity, description, photo, unit_id, supplier_id, manufacturer_id, category_id) 
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (article) DO NOTHING;""",
                        (row["Артикул"], row["Наименование товара"], float(row["Цена"]), float(row["Действующая скидка"]), int(row["Кол-во на складе"]), row["Описание товара"], photo, unit_id, sup_id, man_id, cat_id))

        path_orders = find_file(['order', 'заказ'])
        print(f"5. Читаем заказы из: {os.path.basename(path_orders)}")
        orders = read_data(path_orders)
        for _, row in orders.iterrows():
            order_date = pd.to_datetime(row["Дата заказа"], errors="coerce")
            if pd.isna(order_date): continue

            del_date = pd.to_datetime(row["Дата доставки"], errors="coerce")
            delivery_date_val = del_date.date() if pd.notna(del_date) else None

            status_id = get_or_create(cur, 'order_statuses', 'status_id', 'name', row["Статус заказа"])
            p_id = point_map.get(int(row["Адрес пункта выдачи"]))

            cur.execute("SELECT user_id FROM users WHERE full_name=%s;", (str(row["ФИО авторизированного клиента"]).strip(),))
            u_id = cur.fetchone()
            u_id = u_id[0] if u_id else None

            cur.execute("INSERT INTO orders (order_date, delivery_date, pickup_code, status_id, pickup_point_id, user_id) VALUES (%s, %s, %s, %s, %s, %s) RETURNING order_id;",
                        (order_date.date(), delivery_date_val, int(row["Код для получения"]), status_id, p_id, u_id))
            order_id = cur.fetchone()[0]

            parts = [p.strip() for p in str(row["Артикул заказа"]).split(",") if p.strip()]
            for i in range(0, len(parts), 2):
                cur.execute("SELECT id FROM products WHERE article=%s;", (parts[i],))
                prod = cur.fetchone()
                if prod:
                    qty = int(parts[i+1]) if i+1 < len(parts) else 1
                    cur.execute("INSERT INTO order_items (order_id, product_id, quantity) VALUES (%s, %s, %s);", (order_id, prod[0], qty))

        conn.commit()
        print("\nИМПОРТ УСПЕШНО ЗАВЕРШЕН!")
    except Exception as e:
        conn.rollback()
        print(f"\nОШИБКА: {e}")
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    main()