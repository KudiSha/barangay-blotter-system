-- Barangay Blotter Management System
-- Reference script only. System.py creates the same database and tables
-- automatically on first run, so importing this file is optional.

CREATE DATABASE IF NOT EXISTS `barangay_blotter`
    CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;

USE `barangay_blotter`;

CREATE TABLE IF NOT EXISTS users (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    password_hash CHAR(64) NOT NULL,
    full_name VARCHAR(100) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE IF NOT EXISTS person (
    person_id INT AUTO_INCREMENT PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL,
    address VARCHAR(255),
    contact_no VARCHAR(20),
    KEY idx_person_name (full_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE IF NOT EXISTS blotter (
    blotter_id INT AUTO_INCREMENT PRIMARY KEY,
    blotter_no VARCHAR(30) NOT NULL UNIQUE,
    case_type VARCHAR(50) NOT NULL,
    incident_date DATE NOT NULL,
    incident_place VARCHAR(255) NOT NULL,
    narrative TEXT,
    status VARCHAR(30) NOT NULL DEFAULT 'Pending',
    CONSTRAINT chk_blotter_status CHECK
        (status IN ('Pending', 'For Hearing', 'Settled', 'Referred to Police')),
    KEY idx_blotter_date (incident_date),
    KEY idx_blotter_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE IF NOT EXISTS involved (
    involved_id INT AUTO_INCREMENT PRIMARY KEY,
    blotter_id INT NOT NULL,
    person_id INT NOT NULL,
    role VARCHAR(20) NOT NULL,
    CONSTRAINT chk_involved_role CHECK (role IN ('Complainant', 'Respondent')),
    CONSTRAINT uq_involved UNIQUE (blotter_id, person_id, role),
    CONSTRAINT fk_involved_blotter FOREIGN KEY (blotter_id)
        REFERENCES blotter (blotter_id) ON DELETE CASCADE,
    CONSTRAINT fk_involved_person FOREIGN KEY (person_id)
        REFERENCES person (person_id) ON DELETE RESTRICT,
    KEY idx_involved_person (person_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE IF NOT EXISTS hearing (
    hearing_id INT AUTO_INCREMENT PRIMARY KEY,
    blotter_id INT NOT NULL,
    hearing_date DATE NOT NULL,
    hearing_time TIME NOT NULL,
    venue VARCHAR(150) NOT NULL,
    lupon_panel VARCHAR(150) NOT NULL,
    CONSTRAINT fk_hearing_blotter FOREIGN KEY (blotter_id)
        REFERENCES blotter (blotter_id) ON DELETE CASCADE,
    KEY idx_hearing_date (hearing_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE OR REPLACE VIEW v_summon_letter AS
SELECT h.hearing_id, b.blotter_id, b.blotter_no, b.case_type,
       p.full_name, p.address, i.role,
       h.hearing_date, h.hearing_time, h.venue, h.lupon_panel
FROM hearing h
JOIN blotter b ON b.blotter_id = h.blotter_id
JOIN involved i ON i.blotter_id = b.blotter_id
JOIN person p ON p.person_id = i.person_id;