-- Create and use the database
CREATE DATABASE IF NOT EXISTS DB_Project;
USE DB_Project;

-- Drop existing tables if needed
DROP TABLE IF EXISTS 
    accommodation_user, accommodation,
    make, can_evaluate, can_register,
    payments, evaluation, event_user,
    events, venue, judges, event_organizer,
    sponsors, users, sponsorship_requests;

-- USERS table (renamed from 'user' to 'users')
CREATE TABLE users (
  user_id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  email VARCHAR(255) UNIQUE NOT NULL,
  password VARCHAR(255) NOT NULL,
  phone_number VARCHAR(20) UNIQUE NOT NULL,
  role ENUM('admin', 'user') NOT NULL,
  accommodation_status BOOLEAN NOT NULL
);


-- SPONSORS table (fund NASCON overall)
CREATE TABLE sponsors (
  sponsor_id INT AUTO_INCREMENT PRIMARY KEY,
  company_name VARCHAR(255) NOT NULL,
  sponsorship_category VARCHAR(100) NOT NULL,
  email VARCHAR(255) UNIQUE NOT NULL,
  amount DECIMAL(10,2) NOT NULL,
  sponsor_representative_name VARCHAR(255) NOT NULL
);

-- EVENT ORGANIZER table (updated columns)
CREATE TABLE event_organizer (
  event_organizer_id INT AUTO_INCREMENT PRIMARY KEY,
  society VARCHAR(100) NOT NULL,
  head VARCHAR(100) NOT NULL,
  department VARCHAR(100) NOT NULL
);
select * from event_organizer;

-- JUDGES table
CREATE TABLE judges (
  judge_id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  email VARCHAR(255) UNIQUE NOT NULL
);
ALTER TABLE judges
ADD COLUMN password VARCHAR(255) NOT NULL;


-- VENUE table
CREATE TABLE venue (
  venue_id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(255) NOT NULL,
  capacity INT NOT NULL
);

-- EVENTS table (with timestamp fields)
CREATE TABLE events (
  event_id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(255) NOT NULL,
  rules TEXT NOT NULL,
  max_participants INT NOT NULL,
  registration_fees DECIMAL(10,2) NOT NULL,
  event_date DATE NOT NULL,
  start_time TIME NOT NULL,
  end_time TIME NOT NULL,
  event_type ENUM('computing', 'engineering', 'social', 'sports') NOT NULL,
  venue_id INT NOT NULL,
  event_organizer_id INT NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (venue_id) REFERENCES venue(venue_id),
  FOREIGN KEY (event_organizer_id) REFERENCES event_organizer(event_organizer_id)
);
select * from events;


CREATE TABLE event_user (
  event_id INT NOT NULL,
  user_id INT NOT NULL,
  PRIMARY KEY (event_id, user_id),
  FOREIGN KEY (event_id) REFERENCES events(event_id),
  FOREIGN KEY (user_id) REFERENCES users(user_id)
);

-- EVALUATION table
CREATE TABLE evaluation (
  evaluation_id INT AUTO_INCREMENT PRIMARY KEY,
  score INT NOT NULL,
  comments TEXT,
  event_id INT NOT NULL,
  FOREIGN KEY (event_id) REFERENCES events(event_id)
);

select * from evaluation;

-- USER-EVALUATION Mapping table
CREATE TABLE user_evaluation (
  user_id INT NOT NULL,
  evaluation_id INT NOT NULL,
  PRIMARY KEY (user_id, evaluation_id),
  FOREIGN KEY (user_id) REFERENCES users(user_id),
  FOREIGN KEY (evaluation_id) REFERENCES evaluation(evaluation_id)
);
select * from user_evaluation;

-- PAYMENTS table
CREATE TABLE payments (
  payment_id INT AUTO_INCREMENT PRIMARY KEY,
  amount DECIMAL(10,2) NOT NULL,
  payment_status enum('pending' , 'paid') default 'pending',
  payment_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  user_id INT NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(user_id)
);
select * from payments;

-- ACCOMMODATION table
CREATE TABLE accommodation (
  package varchar(20) not null,
  room_no INT AUTO_INCREMENT PRIMARY KEY,
  rent DECIMAL(10,2) NOT NULL,
  capacity INT NOT NULL
);


-- ACCOMMODATION-USER Mapping table
CREATE TABLE accommodation_user (
  room_no INT NOT NULL,
  user_id INT NOT NULL,
  PRIMARY KEY (room_no, user_id),
  FOREIGN KEY (room_no) REFERENCES accommodation(room_no),
  FOREIGN KEY (user_id) REFERENCES users(user_id)
);

-- EVENT REGISTRATION Permission table
CREATE TABLE user_events (
  user_id INT NOT NULL,
  event_id INT NOT NULL,
  fee_submitted bool default false,
  PRIMARY KEY (user_id, event_id),
  FOREIGN KEY (user_id) REFERENCES users(user_id),
  FOREIGN KEY (event_id) REFERENCES events(event_id)
);
select * from events;
select * from payments;

-- JUDGE EVALUATION Permission table
CREATE TABLE can_evaluate (
  judge_id INT NOT NULL,
  event_id INT NOT NULL,
  PRIMARY KEY (judge_id, event_id),
  FOREIGN KEY (judge_id) REFERENCES judges(judge_id),
  FOREIGN KEY (event_id) REFERENCES events(event_id)
);

        

-- MAKE Evaluation table (which judge made which evaluation)
CREATE TABLE make (
  judge_id INT NOT NULL,
  evaluation_id INT NOT NULL,
  PRIMARY KEY (judge_id, evaluation_id),
  FOREIGN KEY (judge_id) REFERENCES judges(judge_id),
  FOREIGN KEY (evaluation_id) REFERENCES evaluation(evaluation_id)
);
select * from make;

-- SPONSORSHIP REQUESTS table
CREATE TABLE sponsorship_requests (
  request_id INT AUTO_INCREMENT PRIMARY KEY,
  company_name VARCHAR(255) NOT NULL,
  sponsorship_category VARCHAR(100) NOT NULL,
  email VARCHAR(255) UNIQUE NOT NULL,
  amount DECIMAL(10,2) NOT NULL,
  sponsor_representative_name VARCHAR(255) NOT NULL,
  status ENUM('pending', 'accepted', 'rejected') DEFAULT 'pending',
  requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


select * from sponsorship_requests;

DELIMITER $$

CREATE TRIGGER assign_sponsorship_category
BEFORE INSERT ON sponsorship_requests
FOR EACH ROW
BEGIN
  IF NEW.amount >= 100000 THEN
    SET NEW.sponsorship_category = 'Platinum';
  ELSEIF NEW.amount >= 80000 THEN
    SET NEW.sponsorship_category = 'Gold';
  ELSEIF NEW.amount >= 50000 THEN
    SET NEW.sponsorship_category = 'Silver';
  ELSE
    SET NEW.sponsorship_category = 'Bronze';
  END IF;
END$$

DELIMITER ;


-- Event to delete 7days older reviewed requests every day.
SET GLOBAL event_scheduler = ON;

CREATE EVENT IF NOT EXISTS delete_old_sponsorship_requests
ON SCHEDULE EVERY 1 DAY
DO
  DELETE FROM sponsorship_requests
  WHERE status IN ('accepted', 'rejected')
    AND requested_at < NOW() - INTERVAL 7 DAY;
    
-- trigger for when fee_submitted of user_events is updated to true the payment_status of payments is set to paid.
DELIMITER $$

CREATE TRIGGER update_payment_status
AFTER UPDATE ON user_events
FOR EACH ROW
BEGIN
  IF NEW.fee_submitted = TRUE AND OLD.fee_submitted = FALSE THEN
    UPDATE payments
    SET payment_status = 'paid'
    WHERE user_id = NEW.user_id;
  END IF;
END$$

DELIMITER ;

select * from user_events;

CREATE VIEW participant_accommodation_view AS
SELECT 
    u.name AS user_name,
    u.email,
    u.phone_number AS phone,
    a.package AS accommodation_package,
    e.name AS event_name
FROM 
    users u
INNER JOIN 
    user_events ue ON u.user_id = ue.user_id
INNER JOIN 
    events e ON ue.event_id = e.event_id
INNER JOIN 
    accommodation_user au ON u.user_id = au.user_id
INNER JOIN 
    accommodation a ON au.room_no = a.room_no
WHERE 
    u.role = 'user';



-- For fast user/event lookup
CREATE INDEX idx_user_email ON users(email);
CREATE INDEX idx_event_name ON events(name);
CREATE INDEX idx_event_date ON events(event_date);
CREATE INDEX idx_payment_user ON payments(user_id);
CREATE INDEX idx_evaluation_event ON evaluation(event_id);
CREATE INDEX idx_accommodation_user ON accommodation_user(user_id);


DELIMITER $$

CREATE PROCEDURE auto_schedule_event (
    IN p_name VARCHAR(255),
    IN p_rules TEXT,
    IN p_max_participants INT,
    IN p_registration_fees DECIMAL(10,2),
    IN p_event_date DATE,
    IN p_start_time TIME,
    IN p_end_time TIME,
    IN p_event_type ENUM('computing', 'engineering', 'social', 'sports'),
    IN p_event_organizer_id INT
)
BEGIN
    DECLARE v_venue_id INT;

    -- Find venue with the least number of events scheduled on the given date
    SELECT v.venue_id
    INTO v_venue_id
    FROM venue v
    LEFT JOIN events e ON v.venue_id = e.venue_id AND e.event_date = p_event_date
    GROUP BY v.venue_id
    ORDER BY COUNT(e.event_id)
    LIMIT 1;

    -- Insert event with the selected venue
    INSERT INTO events (
        name, rules, max_participants, registration_fees,
        event_date, start_time, end_time, event_type,
        venue_id, event_organizer_id
    )
    VALUES (
        p_name, p_rules, p_max_participants, p_registration_fees,
        p_event_date, p_start_time, p_end_time, p_event_type,
        v_venue_id, p_event_organizer_id
    );
END$$

DELIMITER ;