-- MySQL Setup Script for NeuroMotion - Auth & Logging Enabled
CREATE DATABASE IF NOT EXISTS neuromotion_db;
USE neuromotion_db;

-- 1. Patients Table
CREATE TABLE IF NOT EXISTS patients (
    protocol_no VARCHAR(50) PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    age INT,
    gender VARCHAR(20),
    dominant_side VARCHAR(20),
    onset_year INT,
    diagnosis VARCHAR(100),
    doctor_name VARCHAR(100),
    contact_phone VARCHAR(50),
    clinical_history TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Tests Table
CREATE TABLE IF NOT EXISTS tests (
    id INT AUTO_INCREMENT PRIMARY KEY,
    patient_name VARCHAR(100),
    test_type VARCHAR(50),
    file_path TEXT,
    score DOUBLE,
    extra DOUBLE,
    notes TEXT,
    test_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    doctor_name VARCHAR(100), -- New: Track who did the test
    FOREIGN KEY (patient_name) REFERENCES patients(name) ON DELETE CASCADE
);

-- 3. Calibration Table
CREATE TABLE IF NOT EXISTS device_calibration (
    id INT AUTO_INCREMENT PRIMARY KEY,
    device_id VARCHAR(50) DEFAULT 'Main_Device',
    offset_ax DOUBLE DEFAULT 0,
    offset_ay DOUBLE DEFAULT 0,
    offset_az DOUBLE DEFAULT 0,
    offset_gx DOUBLE DEFAULT 0,
    offset_gy DOUBLE DEFAULT 0,
    offset_gz DOUBLE DEFAULT 0,
    calibrated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Doctors Table (Updated)
CREATE TABLE IF NOT EXISTS doctors (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password VARCHAR(255) DEFAULT '1234',
    specialty VARCHAR(100),
    is_approved TINYINT(1) DEFAULT 0,
    is_admin TINYINT(1) DEFAULT 0
);

-- 5. System Logs Table (New)
CREATE TABLE IF NOT EXISTS system_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    log_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    level VARCHAR(20), -- INFO, WARNING, ERROR
    message TEXT,
    doctor_name VARCHAR(100)
);

-- Initial Data
INSERT IGNORE INTO doctors (name, email, password, specialty, is_approved, is_admin) VALUES ('Admin', 'admin@neuromotion.com', 'admin123', 'System Administrator', 1, 1);
INSERT IGNORE INTO doctors (name, email, password, specialty, is_approved) VALUES ('Dr. Aytaç Durmaz', 'aytac@neuromotion.com', '1234', 'Neurology', 1);
