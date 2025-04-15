DELIMITER $$ DROP PROCEDURE IF EXISTS editPaymentPlan $$ CREATE PROCEDURE editPaymentPlan(IN user_id INT, IN plan_id INT) BEGIN
DECLARE EXIT HANDLER FOR SQLEXCEPTION BEGIN ROLLBACK;
SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'Error updating payment plan';
END;
START TRANSACTION;
-- Update the user's payment plan
UPDATE users
SET planId = plan_id,
    planDate = NOW()
WHERE userId = user_id;
-- Check if the update was successful
IF ROW_COUNT() = 0 THEN SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'User not found';
END IF;
COMMIT;
END $$ DELIMITER;