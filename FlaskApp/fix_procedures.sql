DELIMITER $$ DROP PROCEDURE IF EXISTS createPlaylist $$ CREATE PROCEDURE createPlaylist(
    IN name_p VARCHAR(128),
    IN status_p ENUM('Public', 'Private'),
    IN userId INT
) BEGIN
DECLARE EXIT HANDLER FOR SQLEXCEPTION BEGIN ROLLBACK;
SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'Error creating playlist';
END;
START TRANSACTION;
INSERT INTO playlists (name, status, userId, tracks)
VALUES (name_p, status_p, userId, 0);
COMMIT;
END $$ DELIMITER;