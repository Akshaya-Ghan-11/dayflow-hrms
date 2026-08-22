"""
Database connection for Dayflow HRMS (MySQL / mysql-connector-python).

Edit the credentials below to match your local MySQL Workbench setup.
Run the schema.sql script in Workbench first to create the database & tables.
"""

import mysql.connector

db = mysql.connector.connect(
    host="localhost",
    user="root",          # <-- change to your MySQL username
    password="root",          # <-- change to your MySQL password
    database="dayflow_hrms"
)

# dictionary=True makes cursor.fetchone()/fetchall() return dicts
# instead of plain tuples, so we can do row["full_name"] etc.
cursor = db.cursor(dictionary=True)
