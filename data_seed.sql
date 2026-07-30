-- ============================================================
-- Data migrated from data/centre.db (SQLite) into PostgreSQL
-- Generated automatically. Run AFTER schema.sql:
--   psql "$DATABASE_URL" -f schema.sql
--   psql "$DATABASE_URL" -f data_seed.sql
-- ============================================================

BEGIN;

-- users (2 rows)
INSERT INTO users (id, username, password_hash, full_name, role, is_active, created_at) VALUES (6, 'ywam', 'ec54e99514663edb97adef400fbf34a77daae108303d3da8008a7dfb4cdf0f52', 'YWAM Administrator', 'Admin', 1, '2026-07-28 13:03:49') ON CONFLICT DO NOTHING;
INSERT INTO users (id, username, password_hash, full_name, role, is_active, created_at) VALUES (53, 'e2estaff', 'ecd71870d1963316a97e3ac3408c9835ad8cf0f3c1bc703527c30265534f75ae', 'E2E Staff', 'Staff', 1, '2026-07-28 15:10:23') ON CONFLICT DO NOTHING;

-- students (3 rows)
INSERT INTO students (id, name, dob, age, gender, marital_status, father_husband_name, mother_name, education, occupation, employment_status, community, religion, family_income, special_skill, prev_experience, course, batch, address, mobile, alt_mobile, email, emergency_name, emergency_relation, emergency_mobile, admission_date, start_date, end_date, duration_months, monthly_fee, status, device_user_id, created_at, photo_filename) VALUES (1, 'samuel roshan', '2026-07-02', 22, 'Male', 'Unmarried', 'wfgwwf', 'fdgdg', 'dgdg', 'dddd', 'Employed', 'OBC', 'fvfxc', '434334', 'fhjhfj', 'fsggsgsf', 'Fashion Designing', 'Evening', 'sfggsgsdf', '9361743345', '4444444444444', 'samuelroshanin@gmail.com', 'sfs', 'sfgs', '444444444444444', '2026-07-08', '2026-07-01', '2026-07-30', 3, 200.0, 'Active', 'N', '2026-07-28 12:36:22', NULL) ON CONFLICT DO NOTHING;
INSERT INTO students (id, name, dob, age, gender, marital_status, father_husband_name, mother_name, education, occupation, employment_status, community, religion, family_income, special_skill, prev_experience, course, batch, address, mobile, alt_mobile, email, emergency_name, emergency_relation, emergency_mobile, admission_date, start_date, end_date, duration_months, monthly_fee, status, device_user_id, created_at, photo_filename) VALUES (2, 'E2E Student', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'Basic Tailoring', 'Morning', NULL, '0700000000', NULL, NULL, NULL, NULL, NULL, NULL, '2026-07-01', '2026-10-01', 3, 0.0, 'Active', NULL, '2026-07-28 15:08:08', NULL) ON CONFLICT DO NOTHING;
INSERT INTO students (id, name, dob, age, gender, marital_status, father_husband_name, mother_name, education, occupation, employment_status, community, religion, family_income, special_skill, prev_experience, course, batch, address, mobile, alt_mobile, email, emergency_name, emergency_relation, emergency_mobile, admission_date, start_date, end_date, duration_months, monthly_fee, status, device_user_id, created_at, photo_filename) VALUES (3, 'E2E Student', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'Basic Tailoring', 'Morning', NULL, '0700000000', NULL, NULL, NULL, NULL, NULL, NULL, '2026-07-01', '2026-10-01', 3, 0.0, 'Active', NULL, '2026-07-28 15:10:23', NULL) ON CONFLICT DO NOTHING;

-- attendance (1 rows)
INSERT INTO attendance (id, student_id, date, status, source) VALUES (1, 1, '2026-07-28', 'Present', 'Manual') ON CONFLICT DO NOTHING;

SELECT setval(pg_get_serial_sequence('users', 'id'), COALESCE((SELECT MAX(id) FROM users), 1), true);
SELECT setval(pg_get_serial_sequence('students', 'id'), COALESCE((SELECT MAX(id) FROM students), 1), true);
SELECT setval(pg_get_serial_sequence('attendance', 'id'), COALESCE((SELECT MAX(id) FROM attendance), 1), true);
SELECT setval(pg_get_serial_sequence('fees', 'id'), COALESCE((SELECT MAX(id) FROM fees), 1), true);
SELECT setval(pg_get_serial_sequence('certificates', 'id'), COALESCE((SELECT MAX(id) FROM certificates), 1), true);

COMMIT;
