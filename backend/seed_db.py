"""
seed_db.py
----------
Creates a sample e-commerce SQLite database with realistic, deterministic
sample data: customers, products, orders, order_items, inventory.

Run manually:
    python seed_db.py

It is also auto-run by app.py on startup if the DB file does not exist yet.
"""

import os
import random
import sqlite3
from datetime import datetime, timedelta

DB_PATH = os.environ.get("DATABASE_PATH", "./ecommerce.db")

random.seed(42)

FIRST_NAMES = ["Aditi", "Rahul", "Sneha", "Vikram", "Priya", "Arjun", "Meera",
               "Karthik", "Ananya", "Rohan", "Divya", "Suresh", "Kavya", "Amit",
               "Neha", "Sanjay", "Pooja", "Raj", "Isha", "Vivek"]
LAST_NAMES = ["Sharma", "Verma", "Iyer", "Nair", "Reddy", "Gupta", "Menon",
              "Rao", "Pillai", "Das", "Kapoor", "Chandra", "Bhat", "Shah"]
CITIES = ["Chennai", "Bengaluru", "Mumbai", "Delhi", "Hyderabad", "Pune",
          "Kolkata", "Ahmedabad", "Kochi", "Coimbatore"]

CATEGORIES = {
    "Electronics": [("Wireless Earbuds", 2499), ("Smartwatch", 4999),
                    ("Bluetooth Speaker", 1999), ("Laptop Stand", 899),
                    ("USB-C Hub", 1299), ("Mechanical Keyboard", 3499),
                    ("Wireless Mouse", 799), ("Power Bank 20000mAh", 1599)],
    "Fashion": [("Cotton T-Shirt", 599), ("Denim Jeans", 1799),
                ("Running Shoes", 2999), ("Leather Wallet", 899),
                ("Sunglasses", 1299), ("Backpack", 1999)],
    "Home & Kitchen": [("Non-stick Pan Set", 1599), ("Air Fryer", 4499),
                       ("Vacuum Flask", 599), ("LED Desk Lamp", 799),
                       ("Ceramic Dinner Set", 2199)],
    "Books": [("The Data Science Handbook", 799), ("Atomic Habits", 399),
              ("Clean Code", 899), ("Sapiens", 499)],
    "Sports": [("Yoga Mat", 799), ("Dumbbell Set 10kg", 2499),
               ("Cricket Bat", 1999), ("Football", 899)],
}

ORDER_STATUSES = ["Delivered", "Delivered", "Delivered", "Shipped",
                   "Processing", "Cancelled", "Delivered"]


def build_schema(cur: sqlite3.Cursor) -> None:
    cur.executescript(
        """
        DROP TABLE IF EXISTS order_items;
        DROP TABLE IF EXISTS orders;
        DROP TABLE IF EXISTS inventory;
        DROP TABLE IF EXISTS products;
        DROP TABLE IF EXISTS customers;

        CREATE TABLE customers (
            customer_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name    TEXT NOT NULL,
            last_name     TEXT NOT NULL,
            email         TEXT UNIQUE NOT NULL,
            city          TEXT NOT NULL,
            signup_date   TEXT NOT NULL
        );

        CREATE TABLE products (
            product_id    INTEGER PRIMARY KEY AUTOINCREMENT,
            product_name  TEXT NOT NULL,
            category      TEXT NOT NULL,
            unit_price    REAL NOT NULL
        );

        CREATE TABLE inventory (
            inventory_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id        INTEGER NOT NULL REFERENCES products(product_id),
            warehouse         TEXT NOT NULL,
            quantity_in_stock INTEGER NOT NULL,
            reorder_level     INTEGER NOT NULL
        );

        CREATE TABLE orders (
            order_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id   INTEGER NOT NULL REFERENCES customers(customer_id),
            order_date    TEXT NOT NULL,
            status        TEXT NOT NULL
        );

        CREATE TABLE order_items (
            order_item_id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id      INTEGER NOT NULL REFERENCES orders(order_id),
            product_id    INTEGER NOT NULL REFERENCES products(product_id),
            quantity      INTEGER NOT NULL,
            unit_price    REAL NOT NULL
        );
        """
    )


def seed(cur: sqlite3.Cursor) -> None:
    # Customers
    customer_ids = []
    used_emails = set()
    for i in range(60):
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        email_base = f"{first.lower()}.{last.lower()}"
        email = f"{email_base}{i}@example.com"
        used_emails.add(email)
        city = random.choice(CITIES)
        signup = datetime(2024, 1, 1) + timedelta(days=random.randint(0, 600))
        cur.execute(
            "INSERT INTO customers (first_name,last_name,email,city,signup_date) "
            "VALUES (?,?,?,?,?)",
            (first, last, email, city, signup.strftime("%Y-%m-%d")),
        )
        customer_ids.append(cur.lastrowid)

    # Products
    product_ids = {}  # name -> id
    for category, items in CATEGORIES.items():
        for name, price in items:
            cur.execute(
                "INSERT INTO products (product_name,category,unit_price) VALUES (?,?,?)",
                (name, category, price),
            )
            product_ids[name] = cur.lastrowid

    # Inventory
    warehouses = ["Chennai-WH1", "Mumbai-WH2", "Delhi-WH3"]
    for name, pid in product_ids.items():
        for wh in warehouses:
            cur.execute(
                "INSERT INTO inventory (product_id,warehouse,quantity_in_stock,reorder_level) "
                "VALUES (?,?,?,?)",
                (pid, wh, random.randint(5, 300), random.randint(10, 40)),
            )

    # Orders + order_items across the last 12 months (for trend queries)
    start_date = datetime(2025, 8, 1)
    end_date = datetime(2026, 7, 31)
    days_span = (end_date - start_date).days

    all_products = list(product_ids.items())

    for _ in range(500):
        cust = random.choice(customer_ids)
        order_day = start_date + timedelta(days=random.randint(0, days_span))
        status = random.choice(ORDER_STATUSES)
        cur.execute(
            "INSERT INTO orders (customer_id,order_date,status) VALUES (?,?,?)",
            (cust, order_day.strftime("%Y-%m-%d"), status),
        )
        order_id = cur.lastrowid

        n_items = random.randint(1, 4)
        chosen = random.sample(all_products, n_items)
        for name, pid in chosen:
            qty = random.randint(1, 5)
            # fetch current unit price
            cur.execute("SELECT unit_price FROM products WHERE product_id=?", (pid,))
            price = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO order_items (order_id,product_id,quantity,unit_price) "
                "VALUES (?,?,?,?)",
                (order_id, pid, qty, price),
            )


def main():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    build_schema(cur)
    seed(cur)
    conn.commit()
    conn.close()
    print(f"Seeded database at {DB_PATH}")


if __name__ == "__main__":
    main()
