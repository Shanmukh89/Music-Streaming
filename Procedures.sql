USE streamingdatabase;
/*
 Create Procedures
 */
-- Create a user using given paramters. This will also make a payment plan for the user.
DROP PROCEDURE IF EXISTS createUser;
DELIMITER $$ CREATE PROCEDURE createUser(
	IN firstName_p VARCHAR(64),
	IN lastName_p VARCHAR(64),
	IN email_p VARCHAR(128),
	IN phone_p VARCHAR(10),
	IN plan_id INT
) BEGIN
DECLARE EXIT HANDLER FOR 1062 BEGIN
SELECT "User already exists" as errorMessage;
END;
INSERT INTO users
VALUES(
		0,
		firstName_p,
		lastName_p,
		email_p,
		phone_p,
		plan_id,
		now()
	);
END $$ DELIMITER;
;
-- Create a new playlist using name status and userId 
DROP PROCEDURE IF EXISTS createPlaylist;
DELIMITER $$ CREATE PROCEDURE createPlaylist(
	IN name_p VARCHAR(45),
	IN status_p VARCHAR(64),
	IN userId INT
) BEGIN
INSERT INTO playlists (name, status, userId, tracks)
VALUES (name_p, status_p, userId, 0);
END $$ DELIMITER;
;
-- Add song into playlist
DROP PROCEDURE IF EXISTS addSongPlaylistLink;
DELIMITER $$ CREATE PROCEDURE addSongPlaylistLink(IN song_id INT, IN playlist_id INT) BEGIN
DECLARE duplicate_entry_for_key TINYINT DEFAULT FALSE;
DECLARE EXIT HANDLER FOR 1062 BEGIN
SELECT 'Song already exists in playlist' AS errorMessage;
END;
INSERT INTO playlistsong
VALUES(song_id, playlist_id);
END $$ DELIMITER;
;
/*
 Get Procedures
 */
-- Get payment plan information
DROP PROCEDURE IF EXISTS getPaymentPlans;
DELIMITER $$ CREATE PROCEDURE getPaymentPlans() BEGIN
SELECT *
FROM paymentplans;
END $$ DELIMITER;
;
-- Get information about the user based on the email
DROP PROCEDURE IF EXISTS getUserInformation;
DELIMITER $$ CREATE PROCEDURE getUserInformation(IN user_id INT) BEGIN
SELECT *
FROM users
WHERE userId = user_id;
END $$ DELIMITER;
CALL getUserInformation(2);
;
-- Get information about the payment planId
DROP PROCEDURE IF EXISTS getPaymentInformation;
DELIMITER $$ CREATE PROCEDURE getPaymentInformation(IN plan_id INT) BEGIN
SELECT *
FROM paymentplans
WHERE planId = plan_id;
END $$ DELIMITER;
;
-- Gets songs in Playlist using playlist_id
DROP PROCEDURE IF EXISTS getPlaylistSongs;
DELIMITER $$ CREATE PROCEDURE getPlaylistSongs(IN playlist_id INT) BEGIN
SELECT s.songId,
	s.title,
	releaseDate,
	s.duration,
	a.name as artistName,
	c.title as albumTitle,
	g.name as genreName
FROM songs AS s
	JOIN playlistsong AS p ON s.songId = p.songId
	JOIN artistsong AS l ON s.songId = l.songId
	JOIN artists AS a ON l.artistId = a.artistId
	JOIN albumsong AS b ON s.songId = b.songId
	JOIN albums as c ON b.albumId = c.albumId
	JOIN genresong AS gs ON s.songId = gs.songId
	JOIN genres AS g ON gs.genreId = g.genreId
WHERE p.playlistId = playlist_id;
END $$ DELIMITER;
CALL getPlaylistSongs(1);
-- Get songs with all parameters
DROP PROCEDURE IF EXISTS getSongs;
DELIMITER $$ CREATE PROCEDURE getSongs() BEGIN
SELECT s.songId,
	s.title,
	releaseDate,
	s.duration,
	a.name as artistName,
	g.name as genreName,
	c.title as albumTitle
FROM songs AS s
	JOIN albumsong AS b ON s.songId = b.songId
	JOIN albums as c ON b.albumId = c.albumId
	JOIN artistsong AS l ON s.songId = l.songId
	JOIN genresong AS gs ON s.songId = gs.songId
	JOIN genres AS g ON gs.genreId = g.genreId
	JOIN artists AS a ON l.artistId = a.artistId;
END $$ DELIMITER;
CALL getSongs();
-- Get songs with not in selected playlist
DROP PROCEDURE IF EXISTS getSongsForPlaylistView;
DELIMITER $$ CREATE PROCEDURE getSongsForPlaylistView(IN playlist_id INT) BEGIN
SELECT s.songId,
	s.title,
	releaseDate,
	s.duration,
	a.name as artistName,
	g.name as genreName,
	c.title as albumTitle
FROM songs AS s
	JOIN artistsong AS l ON s.songId = l.songId
	JOIN genresong AS gs ON s.songId = gs.songId
	JOIN genres AS g ON gs.genreId = g.genreId
	JOIN artists AS a ON l.artistId = a.artistId
	JOIN albumsong AS b ON s.songId = b.songId
	JOIN albums as c ON b.albumId = c.albumId
WHERE s.songId NOT IN (
		SELECT songId
		FROM playlistsong
		WHERE playlistId = playlist_id
	);
END $$ DELIMITER;
CALL getSongsForPlaylistView(4);
-- Get playlists by user id
DROP PROCEDURE IF EXISTS getPlaylistsUser;
DELIMITER $$ CREATE PROCEDURE getPlaylistsUser(IN user_id INT) BEGIN
SELECT *
FROM playlists AS p
WHERE userId = user_id;
END $$ DELIMITER;
CALL getPlaylistsUser(1);
;
-- Get songs from a search parameter using %
DROP PROCEDURE IF EXISTS getSongsFromSearch;
DELIMITER $$ CREATE PROCEDURE getSongsFromSearch(IN searchParam VARCHAR(127)) BEGIN
SELECT s.songId,
	title,
	releaseDate,
	duration,
	name
FROM songs AS s
	JOIN artistsong AS l ON s.songId = l.songId
	JOIN artists AS a ON l.artistId = a.artistId
WHERE title LIKE searchParam;
END $$ DELIMITER;
CALL getSongsFromSearch("%F%");
;
-- Get songs with all parameters
DROP PROCEDURE IF EXISTS getSong;
DELIMITER $$ CREATE PROCEDURE getSong(IN song_id INT) BEGIN
SELECT s.songId,
	s.title,
	releaseDate,
	s.duration,
	a.name as artistName,
	g.name as genreName,
	c.title as albumTitle,
	coverArt
FROM songs AS s
	JOIN artistsong AS l ON s.songId = l.songId
	JOIN genresong AS gs ON s.songId = gs.songId
	JOIN genres AS g ON gs.genreId = g.genreId
	JOIN artists AS a ON l.artistId = a.artistId
	JOIN albumsong AS b ON s.songId = b.songId
	JOIN albums as c ON b.albumId = c.albumId
WHERE s.songId = song_id;
END $$ DELIMITER;
CALL getSong(1);
/*
 Update procedures
 */
-- Procedure to edit playlist title
DROP PROCEDURE IF EXISTS editPlaylist;
DELIMITER $$ CREATE PROCEDURE editPlaylist(
	IN name_p VARCHAR(45),
	IN status_p VARCHAR(64),
	IN playlist_id INT
) BEGIN
UPDATE playlists
SET name = name_p,
	status = status_p
WHERE playlistId = playlist_id;
END $$ DELIMITER;
;
-- Procedure to edit payment plan information
DROP PROCEDURE IF EXISTS editPaymentPlan;
DELIMITER $$ CREATE PROCEDURE editPaymentPlan(IN user_id INT, IN plan_id INT) BEGIN
UPDATE users
SET planId = plan_id,
	planDate = now()
WHERE userId = user_id;
END $$ DELIMITER;
;
/*
 Delete procedures
 */
-- Removes a song from a Playlist using playlist_id and song_id
DROP PROCEDURE IF EXISTS removeSongFromPlaylist;
DELIMITER $$ CREATE PROCEDURE removeSongFromPlaylist(IN playlist_id INT, IN song_id INT) BEGIN
DELETE FROM playlistsong
WHERE playlistId = playlist_id
	AND songId = song_id;
END $$ DELIMITER;
;
-- Removes a users playlist
DROP PROCEDURE IF EXISTS removePlaylist;
DELIMITER $$ CREATE PROCEDURE removePlaylist(IN playlist_id INT) BEGIN
DELETE FROM playlists
WHERE playlistId = playlist_id;
END $$ DELIMITER;
;
-- Removes a user from database
DROP PROCEDURE IF EXISTS removeUser;
DELIMITER $$ CREATE PROCEDURE removeUser(IN user_id INT) BEGIN
DELETE FROM playlists
WHERE userId = user_id;
DELETE FROM users
WHERE userId = user_id;
END $$ DELIMITER;
;
/*
 Triggers
 */
-- Trigger for inserting song into playlist
DROP TRIGGER IF EXISTS trackNumberPlaylistInsert;
DELIMITER // CREATE TRIGGER trackNumberPlaylistInsert
AFTER
INSERT ON playlistsong FOR EACH ROW BEGIN
DECLARE trackNumber INT;
SELECT count(songId) INTO trackNumber
FROM playlistsong
WHERE playlistId = NEW.playlistId;
UPDATE playlists
SET tracks = trackNumber
WHERE playlistId = NEW.playlistId;
END // DELIMITER;
;
-- Trigger for removing song into playlist
DROP TRIGGER IF EXISTS trackNumberPlaylistRemove;
DELIMITER // CREATE TRIGGER trackNumberPlaylistRemove
AFTER DELETE ON playlistsong FOR EACH ROW BEGIN
DECLARE trackNumber INT;
SELECT count(songId) INTO trackNumber
FROM playlistsong
WHERE playlistId = OLD.playlistId;
UPDATE playlists
SET tracks = trackNumber
WHERE playlistId = OLD.playlistId;
END //