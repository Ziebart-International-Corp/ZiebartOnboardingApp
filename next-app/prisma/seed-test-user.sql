-- Run this in Neon SQL Editor to create/update test user asymons@ziebart.com / password "password"
-- (If user exists, updates password; otherwise inserts.)

UPDATE users
SET password_hash = '$2a$10$w3b9Gma5FeSZ3dh2oLaGB.VmNE049QtXtCc8vSkaGX0waIo.9EQ6u',
    full_name = 'Test Admin',
    role = 'admin',
    username = 'asymons'
WHERE email = 'asymons@ziebart.com';

INSERT INTO users (username, email, password_hash, full_name, role)
SELECT 'asymons', 'asymons@ziebart.com', '$2a$10$w3b9Gma5FeSZ3dh2oLaGB.VmNE049QtXtCc8vSkaGX0waIo.9EQ6u', 'Test Admin', 'admin'
WHERE NOT EXISTS (SELECT 1 FROM users WHERE email = 'asymons@ziebart.com');
