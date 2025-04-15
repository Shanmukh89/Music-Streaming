DELIMITER $$ DROP PROCEDURE IF EXISTS removePlaylist $$ CREATE PROCEDURE removePlaylist(IN playlist_id INT) BEGIN
DECLARE EXIT HANDLER FOR SQLEXCEPTION BEGIN ROLLBACK;
SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'Error removing playlist';
END;
START TRANSACTION;
-- First delete from playlistsong table to avoid foreign key constraints
DELETE FROM playlistsong
WHERE playlistId = playlist_id;
-- Then delete from playlists table
DELETE FROM playlists
WHERE playlistId = playlist_id;
COMMIT;
END $$ DELIMITER;