CREATE DATABASE IF NOT EXISTS dayflow_hrms;
USE dayflow_hrms;

-- Users table
CREATE TABLE IF NOT EXISTS users (
    employee_id INT PRIMARY KEY AUTO_INCREMENT,
    full_name VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    role ENUM('Admin','Employee') NOT NULL,
    phone VARCHAR(15),
    address TEXT
);

-- Attendance table
CREATE TABLE IF NOT EXISTS attendance (
    attendance_id INT PRIMARY KEY AUTO_INCREMENT,
    employee_id INT,
    date DATE,
    check_in TIME,
    check_out TIME,
    status ENUM('Present','Absent','Half-Day','Leave'),
    FOREIGN KEY (employee_id) REFERENCES users(employee_id) ON DELETE CASCADE,
    UNIQUE KEY uniq_emp_date (employee_id, date)
);

-- Leave table
CREATE TABLE IF NOT EXISTS leave_requests (
    leave_id INT PRIMARY KEY AUTO_INCREMENT,
    employee_id INT,
    leave_type ENUM('Paid','Sick','Unpaid'),
    start_date DATE,
    end_date DATE,
    remarks TEXT,
    status ENUM('Pending','Approved','Rejected') DEFAULT 'Pending',
    admin_comment TEXT,
    FOREIGN KEY (employee_id) REFERENCES users(employee_id) ON DELETE CASCADE
);

-- Payroll table
CREATE TABLE IF NOT EXISTS payroll (
    payroll_id INT PRIMARY KEY AUTO_INCREMENT,
    employee_id INT UNIQUE,
    basic_salary DECIMAL(10,2) DEFAULT 0,
    bonus DECIMAL(10,2) DEFAULT 0,
    total_salary DECIMAL(10,2) DEFAULT 0,
    FOREIGN KEY (employee_id) REFERENCES users(employee_id) ON DELETE CASCADE
);
