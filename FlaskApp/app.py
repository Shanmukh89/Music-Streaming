from flask import Flask, render_template, request, url_for, session, redirect, jsonify
from datetime import datetime, timedelta
import pymysql
import re
import random
import sys
import db_config
from flask_socketio import SocketIO, emit
import json

app = Flask(__name__)

app.secret_key = 'streamtime'

#Set up pymysql connection arguments
pymysql_connect_kwargs = {'user': db_config.DB_USER, 
                          'password': db_config.DB_PASS, 
                          'host': db_config.DB_SERVER,
                          'database': db_config.DB}

# SQL Schema and Procedures
SCHEMA_SQL = """
SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0;
SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0;
SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION';

CREATE TABLE IF NOT EXISTS playlists (
  playlistId INT NOT NULL AUTO_INCREMENT,
  name VARCHAR(45) NOT NULL,
  status ENUM('Public', 'Private') NOT NULL,
  userId INT NOT NULL,
  tracks INT NOT NULL DEFAULT 0,
  PRIMARY KEY (playlistId)
) ENGINE = InnoDB;

CREATE TABLE IF NOT EXISTS users (
  userId INT NOT NULL AUTO_INCREMENT,
  firstName VARCHAR(64) NOT NULL,
  lastName VARCHAR(64) NOT NULL,
  email VARCHAR(128) NOT NULL,
  phone VARCHAR(10) NOT NULL,
  planId INT NOT NULL,
  planDate DATETIME NOT NULL,
  PRIMARY KEY (userId),
  UNIQUE INDEX email_UNIQUE (email ASC)
) ENGINE = InnoDB;

CREATE TABLE IF NOT EXISTS paymentplans (
  planId INT NOT NULL AUTO_INCREMENT,
  amount INT NOT NULL,
  type ENUM("Monthly", "Yearly", "Free") NOT NULL,
  PRIMARY KEY (planId)
) ENGINE = InnoDB;

CREATE TABLE IF NOT EXISTS genres (
  genreId INT NOT NULL AUTO_INCREMENT,
  name VARCHAR(128) NOT NULL,
  PRIMARY KEY (genreId),
  UNIQUE INDEX name_UNIQUE (name ASC)
) ENGINE = InnoDB;

CREATE TABLE IF NOT EXISTS songs (
  songId INT NOT NULL AUTO_INCREMENT,
  title VARCHAR(45) NOT NULL,
  releaseDate DATE NOT NULL,
  duration INT NOT NULL,
  PRIMARY KEY (songId)
) ENGINE = InnoDB;

CREATE TABLE IF NOT EXISTS albums (
  albumId INT NOT NULL AUTO_INCREMENT,
  title VARCHAR(45) NOT NULL,
  releaseDate DATE NOT NULL,
  coverArt VARCHAR(255) NULL,
  PRIMARY KEY (albumId)
) ENGINE = InnoDB;

CREATE TABLE IF NOT EXISTS artists (
  artistId INT NOT NULL AUTO_INCREMENT,
  name VARCHAR(128) NOT NULL,
  PRIMARY KEY (artistId)
) ENGINE = InnoDB;

CREATE TABLE IF NOT EXISTS playlistsong (
  playlistId INT NOT NULL,
  songId INT NOT NULL,
  PRIMARY KEY (playlistId, songId),
  INDEX songId_idx (songId ASC),
  CONSTRAINT fk_playlist_id
    FOREIGN KEY (playlistId)
    REFERENCES playlists (playlistId)
    ON DELETE CASCADE
    ON UPDATE CASCADE,
  CONSTRAINT fk_song_id
    FOREIGN KEY (songId)
    REFERENCES songs (songId)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION
) ENGINE = InnoDB;

CREATE TABLE IF NOT EXISTS artistsong (
  artistId INT NOT NULL,
  songId INT NOT NULL,
  PRIMARY KEY (artistId, songId),
  CONSTRAINT fk_artist_id
    FOREIGN KEY (artistId)
    REFERENCES artists (artistId)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION,
  CONSTRAINT fk_artist_song_id
    FOREIGN KEY (songId)
    REFERENCES songs (songId)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION
) ENGINE = InnoDB;

CREATE TABLE IF NOT EXISTS albumsong (
  albumId INT NOT NULL,
  songId INT NOT NULL,
  PRIMARY KEY (albumId, songId),
  CONSTRAINT fk_album_id
    FOREIGN KEY (albumId)
    REFERENCES albums (albumId)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION,
  CONSTRAINT fk_album_song_id
    FOREIGN KEY (songId)
    REFERENCES songs (songId)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION
) ENGINE = InnoDB;

CREATE TABLE IF NOT EXISTS genresong (
  genreId INT NOT NULL,
  songId INT NOT NULL,
  PRIMARY KEY (genreId, songId),
  CONSTRAINT fk_genre_id
    FOREIGN KEY (genreId)
    REFERENCES genres (genreId)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION,
  CONSTRAINT fk_genre_song_id
    FOREIGN KEY (songId)
    REFERENCES songs (songId)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION
) ENGINE = InnoDB;

CREATE TABLE IF NOT EXISTS songlikes (
  userId INT NOT NULL,
  songId INT NOT NULL,
  likedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (userId, songId),
  CONSTRAINT fk_like_user_id
    FOREIGN KEY (userId)
    REFERENCES users (userId)
    ON DELETE CASCADE
    ON UPDATE CASCADE,
  CONSTRAINT fk_like_song_id
    FOREIGN KEY (songId)
    REFERENCES songs (songId)
    ON DELETE CASCADE
    ON UPDATE CASCADE
) ENGINE = InnoDB;

CREATE TABLE IF NOT EXISTS songcomments (
  commentId INT NOT NULL AUTO_INCREMENT,
  userId INT NOT NULL,
  songId INT NOT NULL,
  comment TEXT NOT NULL,
  createdAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (commentId),
  CONSTRAINT fk_comment_user_id
    FOREIGN KEY (userId)
    REFERENCES users (userId)
    ON DELETE CASCADE
    ON UPDATE CASCADE,
  CONSTRAINT fk_comment_song_id
    FOREIGN KEY (songId)
    REFERENCES songs (songId)
    ON DELETE CASCADE
    ON UPDATE CASCADE
) ENGINE = InnoDB;

CREATE TABLE IF NOT EXISTS listening_history (
  historyId INT NOT NULL AUTO_INCREMENT,
  userId INT NOT NULL,
  songId INT NOT NULL,
  listenedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (historyId),
  INDEX idx_user_time (userId, listenedAt DESC),
  CONSTRAINT fk_history_user_id
    FOREIGN KEY (userId)
    REFERENCES users (userId)
    ON DELETE CASCADE
    ON UPDATE CASCADE,
  CONSTRAINT fk_history_song_id
    FOREIGN KEY (songId)
    REFERENCES songs (songId)
    ON DELETE CASCADE
    ON UPDATE CASCADE
) ENGINE = InnoDB;

CREATE TABLE IF NOT EXISTS chat_messages (
  messageId INT NOT NULL AUTO_INCREMENT,
  userId INT NOT NULL,
  message TEXT NOT NULL,
  createdAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (messageId),
  INDEX idx_time (createdAt DESC),
  CONSTRAINT fk_message_user_id
    FOREIGN KEY (userId)
    REFERENCES users (userId)
    ON DELETE CASCADE
    ON UPDATE CASCADE
) ENGINE = InnoDB;

SET SQL_MODE=@OLD_SQL_MODE;
SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS;
SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS;
"""

FUNCTIONS_SQL = """
DELIMITER //

-- Find user function
DROP FUNCTION IF EXISTS findUser //
CREATE FUNCTION findUser(email_p VARCHAR(128), phone_p VARCHAR(10)) 
RETURNS INT
DETERMINISTIC
READS SQL DATA
BEGIN 
    DECLARE uid_found INT;
    DECLARE uid_not_found INT;
    DECLARE user_cursor CURSOR FOR SELECT userId FROM users WHERE email = email_p AND phone = phone_p;
    DECLARE CONTINUE HANDLER FOR NOT FOUND
        SET uid_not_found = TRUE;

    SET uid_not_found = FALSE;
    OPEN user_cursor;
    
    FETCH user_cursor INTO uid_found;
    
    CLOSE user_cursor;
    
    RETURN uid_found;
END //

-- Count songs in playlist function
DROP FUNCTION IF EXISTS countSongsInPlaylist //
CREATE FUNCTION countSongsInPlaylist(playlist_id INT) 
RETURNS INT
DETERMINISTIC
READS SQL DATA
BEGIN 
    DECLARE song_count INT;
    SELECT count(*) INTO song_count FROM playlistsong WHERE playlistId = playlist_id;
    RETURN song_count;
END //

-- Get playlist name function
DROP FUNCTION IF EXISTS getPlaylistName //
CREATE FUNCTION getPlaylistName(playlist_id INT)
RETURNS VARCHAR(128)
DETERMINISTIC
READS SQL DATA
BEGIN
    DECLARE playlist_name VARCHAR(128);
    SELECT name INTO playlist_name FROM playlists WHERE playlistId = playlist_id;
    RETURN playlist_name;
END //

DELIMITER ;
"""

PROCEDURES_SQL = """
DELIMITER //

-- Create user procedure
DROP PROCEDURE IF EXISTS createUser //
CREATE PROCEDURE createUser(
    IN firstName_p VARCHAR(64),
    IN lastName_p VARCHAR(64),
    IN email_p VARCHAR(128),
    IN phone_p VARCHAR(10),
    IN plan_id INT
)
BEGIN
    DECLARE EXIT HANDLER FOR 1062 BEGIN
        SELECT "User already exists" as errorMessage;
    END;
    INSERT INTO users VALUES(0, firstName_p, lastName_p, email_p, phone_p, plan_id, now());
END //

-- Create playlist procedure
DROP PROCEDURE IF EXISTS createPlaylist //
CREATE PROCEDURE createPlaylist(
    IN name_p VARCHAR(45),
    IN status_p VARCHAR(64),
    IN userId_p INT
)
BEGIN
    INSERT INTO playlists (name, status, userId, tracks) VALUES (name_p, status_p, userId_p, 0);
END //

-- Add song to playlist procedure
DROP PROCEDURE IF EXISTS addSongPlaylistLink //
CREATE PROCEDURE addSongPlaylistLink(IN song_id INT, IN playlist_id INT, IN user_id INT)
BEGIN
    DECLARE duplicate_entry_for_key TINYINT DEFAULT FALSE;
    DECLARE EXIT HANDLER FOR 1062 BEGIN
        SELECT 'Song already exists in playlist' AS errorMessage;
    END;
    
    -- Add song to playlist
    INSERT INTO playlistsong VALUES(playlist_id, song_id);
    UPDATE playlists SET tracks = tracks + 1 WHERE playlistId = playlist_id;
    
    -- Add to listening history
    INSERT INTO listening_history (userId, songId) VALUES (user_id, song_id);
END //

-- Get payment plans procedure
DROP PROCEDURE IF EXISTS getPaymentPlans //
CREATE PROCEDURE getPaymentPlans()
BEGIN
    SELECT * FROM paymentplans;
END //

-- Get user information procedure
DROP PROCEDURE IF EXISTS getUserInformation //
CREATE PROCEDURE getUserInformation(IN user_id INT)
BEGIN
    SELECT * FROM users WHERE userId = user_id;
END //

-- Get payment information procedure
DROP PROCEDURE IF EXISTS getPaymentInformation //
CREATE PROCEDURE getPaymentInformation(IN plan_id INT)
BEGIN
    SELECT * FROM paymentplans WHERE planId = plan_id;
END //

-- Get playlist songs procedure
DROP PROCEDURE IF EXISTS getPlaylistSongs //
CREATE PROCEDURE getPlaylistSongs(IN playlist_id INT)
BEGIN
    SELECT s.songId, s.title, s.releaseDate, s.duration, a.name as artistName,
           c.title as albumTitle, g.name as genreName,
           (SELECT COUNT(*) FROM songlikes WHERE songId = s.songId) as likeCount
    FROM songs AS s
    JOIN playlistsong AS p ON s.songId = p.songId
    JOIN artistsong AS l ON s.songId = l.songId
    JOIN artists AS a ON l.artistId = a.artistId
    JOIN albumsong AS b ON s.songId = b.songId
    JOIN albums as c ON b.albumId = c.albumId
    JOIN genresong AS gs ON s.songId = gs.songId
    JOIN genres AS g ON gs.genreId = g.genreId
    WHERE p.playlistId = playlist_id;
END //

-- Get all songs procedure
DROP PROCEDURE IF EXISTS getSongs //
CREATE PROCEDURE getSongs()
BEGIN
    SELECT s.songId, s.title, s.releaseDate, s.duration, a.name as artistName,
           g.name as genreName, c.title as albumTitle
    FROM songs AS s
    JOIN albumsong AS b ON s.songId = b.songId
    JOIN albums as c ON b.albumId = c.albumId
    JOIN artistsong AS l ON s.songId = l.songId
    JOIN genresong AS gs ON s.songId = gs.songId
    JOIN genres AS g ON gs.genreId = g.genreId
    JOIN artists AS a ON l.artistId = a.artistId;
END //

-- Get songs not in playlist procedure
DROP PROCEDURE IF EXISTS getSongsForPlaylistView //
CREATE PROCEDURE getSongsForPlaylistView(IN playlist_id INT)
BEGIN
    SELECT s.songId, s.title, s.releaseDate, s.duration, a.name as artistName,
           g.name as genreName, c.title as albumTitle,
           (SELECT COUNT(*) FROM songlikes WHERE songId = s.songId) as likeCount
    FROM songs AS s
    JOIN artistsong AS l ON s.songId = l.songId
    JOIN genresong AS gs ON s.songId = gs.songId
    JOIN genres AS g ON gs.genreId = g.genreId
    JOIN artists AS a ON l.artistId = a.artistId
    JOIN albumsong AS b ON s.songId = b.songId
    JOIN albums as c ON b.albumId = c.albumId
    WHERE s.songId NOT IN (
        SELECT songId FROM playlistsong WHERE playlistId = playlist_id
    );
END //

-- Get user playlists procedure
DROP PROCEDURE IF EXISTS getPlaylistsUser //
CREATE PROCEDURE getPlaylistsUser(IN user_id INT)
BEGIN
    SELECT * FROM playlists AS p WHERE userId = user_id;
END //

-- Search songs procedure
DROP PROCEDURE IF EXISTS getSongsFromSearch //
CREATE PROCEDURE getSongsFromSearch(IN searchParam VARCHAR(127))
BEGIN
    SELECT s.songId, title, releaseDate, duration, name
    FROM songs AS s
    JOIN artistsong AS l ON s.songId = l.songId
    JOIN artists AS a ON l.artistId = a.artistId
    WHERE title LIKE searchParam;
END //

-- Get single song procedure
DROP PROCEDURE IF EXISTS getSong //
CREATE PROCEDURE getSong(IN song_id INT)
BEGIN
    SELECT s.songId, s.title, s.releaseDate, s.duration, a.name as artistName,
           g.name as genreName, c.title as albumTitle, c.coverArt,
           (SELECT COUNT(*) FROM songlikes WHERE songId = s.songId) as likeCount
    FROM songs AS s
    JOIN artistsong AS l ON s.songId = l.songId
    JOIN genresong AS gs ON s.songId = gs.songId
    JOIN genres AS g ON gs.genreId = g.genreId
    JOIN artists AS a ON l.artistId = a.artistId
    JOIN albumsong AS b ON s.songId = b.songId
    JOIN albums as c ON b.albumId = c.albumId
    WHERE s.songId = song_id;
END //

-- Edit playlist procedure
DROP PROCEDURE IF EXISTS editPlaylist //
CREATE PROCEDURE editPlaylist(
    IN name_p VARCHAR(45),
    IN status_p VARCHAR(64),
    IN playlist_id INT
)
BEGIN
    UPDATE playlists
    SET name = name_p, status = status_p
    WHERE playlistId = playlist_id;
END //

-- Edit payment plan procedure
DROP PROCEDURE IF EXISTS editPaymentPlan //
CREATE PROCEDURE editPaymentPlan(IN user_id INT, IN plan_id INT)
BEGIN
    UPDATE users
    SET planId = plan_id, planDate = now()
    WHERE userId = user_id;
END //

-- Remove song from playlist procedure
DROP PROCEDURE IF EXISTS removeSongFromPlaylist //
CREATE PROCEDURE removeSongFromPlaylist(IN playlist_id INT, IN song_id INT)
BEGIN
    DELETE FROM playlistsong
    WHERE playlistId = playlist_id AND songId = song_id;
    UPDATE playlists SET tracks = tracks - 1 WHERE playlistId = playlist_id;
END //

-- Remove playlist procedure
DROP PROCEDURE IF EXISTS removePlaylist //
CREATE PROCEDURE removePlaylist(IN playlist_id INT)
BEGIN
    DELETE FROM playlists WHERE playlistId = playlist_id;
END //

-- Remove user procedure
DROP PROCEDURE IF EXISTS removeUser //
CREATE PROCEDURE removeUser(IN user_id INT)
BEGIN
    DELETE FROM playlists WHERE userId = user_id;
    DELETE FROM users WHERE userId = user_id;
END //

-- Like song procedure
DROP PROCEDURE IF EXISTS likeSong //
CREATE PROCEDURE likeSong(IN user_id INT, IN song_id INT)
BEGIN
    INSERT IGNORE INTO songlikes (userId, songId) VALUES (user_id, song_id);
END //

-- Unlike song procedure
DROP PROCEDURE IF EXISTS unlikeSong //
CREATE PROCEDURE unlikeSong(IN user_id INT, IN song_id INT)
BEGIN
    DELETE FROM songlikes WHERE userId = user_id AND songId = song_id;
END //

-- Check if song is liked by user
DROP PROCEDURE IF EXISTS isLikedBySong //
CREATE PROCEDURE isLikedBySong(IN user_id INT, IN song_id INT)
BEGIN
    SELECT COUNT(*) as liked FROM songlikes WHERE userId = user_id AND songId = song_id;
END //

-- Add comment procedure
DROP PROCEDURE IF EXISTS addComment //
CREATE PROCEDURE addComment(
    IN user_id INT,
    IN song_id INT,
    IN comment_text TEXT
)
BEGIN
    INSERT INTO songcomments (userId, songId, comment) 
    VALUES (user_id, song_id, comment_text);
END //

-- Get comments for song procedure
DROP PROCEDURE IF EXISTS getSongComments //
CREATE PROCEDURE getSongComments(IN song_id INT)
BEGIN
    SELECT c.commentId, c.comment, c.createdAt, 
           u.firstName, u.lastName
    FROM songcomments c
    JOIN users u ON c.userId = u.userId
    WHERE c.songId = song_id
    ORDER BY c.createdAt DESC;
END //

-- Delete comment procedure
DROP PROCEDURE IF EXISTS deleteComment //
CREATE PROCEDURE deleteComment(
    IN comment_id INT,
    IN user_id INT
)
BEGIN
    DELETE FROM songcomments 
    WHERE commentId = comment_id 
    AND userId = user_id;
END //

-- Add listening history entry procedure
DROP PROCEDURE IF EXISTS addToHistory //
CREATE PROCEDURE addToHistory(
    IN user_id INT,
    IN song_id INT
)
BEGIN
    INSERT INTO listening_history (userId, songId) 
    VALUES (user_id, song_id);
END //

-- Get user's listening history procedure
DROP PROCEDURE IF EXISTS getListeningHistory //
CREATE PROCEDURE getListeningHistory(
    IN user_id INT,
    IN limit_count INT
)
BEGIN
    SELECT h.historyId, h.listenedAt, 
           s.songId, s.title, s.duration,
           a.name as artistName,
           al.title as albumTitle,
           al.coverArt,
           g.name as genreName,
           (SELECT COUNT(*) FROM songlikes WHERE songId = s.songId) as likeCount
    FROM (
        SELECT songId, MAX(listenedAt) as maxListenedAt
        FROM listening_history
        WHERE userId = user_id
        GROUP BY songId
    ) latest_plays
    JOIN listening_history h ON h.songId = latest_plays.songId 
        AND h.listenedAt = latest_plays.maxListenedAt
        AND h.userId = user_id
    JOIN songs s ON h.songId = s.songId
    JOIN artistsong ast ON s.songId = ast.songId
    JOIN artists a ON ast.artistId = a.artistId
    JOIN albumsong als ON s.songId = als.songId
    JOIN albums al ON als.albumId = al.albumId
    JOIN genresong gs ON s.songId = gs.songId
    JOIN genres g ON gs.genreId = g.genreId
    ORDER BY h.listenedAt DESC
    LIMIT limit_count;
END //

-- Add message procedure
DROP PROCEDURE IF EXISTS addChatMessage //
CREATE PROCEDURE addChatMessage(
    IN user_id INT,
    IN message_text TEXT
)
BEGIN
    INSERT INTO chat_messages (userId, message) 
    VALUES (user_id, message_text);
    
    -- Return the inserted message with user details
    SELECT m.messageId, m.message, m.createdAt,
           u.userId, u.firstName, u.lastName
    FROM chat_messages m
    JOIN users u ON m.userId = u.userId
    WHERE m.messageId = LAST_INSERT_ID();
END //

-- Get recent messages procedure
DROP PROCEDURE IF EXISTS getRecentMessages //
CREATE PROCEDURE getRecentMessages(
    IN limit_count INT
)
BEGIN
    SELECT m.messageId, m.message, m.createdAt,
           u.userId, u.firstName, u.lastName
    FROM chat_messages m
    JOIN users u ON m.userId = u.userId
    ORDER BY m.createdAt DESC
    LIMIT limit_count;
END //

DELIMITER ;
"""

# Create a function to get database connection
def get_db():
    return pymysql.connect(**pymysql_connect_kwargs)

def init_db():
    """Initialize the database with schema and stored procedures"""
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            # Drop all existing procedures and functions first
            procedures_to_drop = [
                'createUser', 'createPlaylist', 'addSongPlaylistLink', 'getPaymentPlans',
                'getUserInformation', 'getPaymentInformation', 'getPlaylistSongs', 'getSongs',
                'getSongsForPlaylistView', 'getPlaylistsUser', 'getSongsFromSearch', 'getSong',
                'editPlaylist', 'editPaymentPlan', 'removeSongFromPlaylist', 'removePlaylist',
                'removeUser', 'likeSong', 'unlikeSong', 'isLikedBySong', 'addComment', 'getSongComments', 'deleteComment', 'addToHistory', 'getListeningHistory', 'addChatMessage', 'getRecentMessages'
            ]
            
            functions_to_drop = ['findUser', 'countSongsInPlaylist', 'getPlaylistName']
            
            for proc in procedures_to_drop:
                cursor.execute(f"DROP PROCEDURE IF EXISTS {proc}")
            
            for func in functions_to_drop:
                cursor.execute(f"DROP FUNCTION IF EXISTS {func}")

            # Execute schema creation
            for statement in SCHEMA_SQL.split(';'):
                if statement.strip():
                    try:
                        cursor.execute(statement)
                    except Exception as e:
                        print(f"Error executing schema statement: {str(e)}")
                        print(f"Statement: {statement}")
            
            # Create functions
            cursor.execute("""
                CREATE FUNCTION findUser(email_p VARCHAR(128), phone_p VARCHAR(10)) 
                RETURNS INT
                DETERMINISTIC
                READS SQL DATA
                BEGIN 
                    DECLARE uid_found INT;
                    DECLARE uid_not_found INT;
                    DECLARE user_cursor CURSOR FOR SELECT userId FROM users WHERE email = email_p AND phone = phone_p;
                    DECLARE CONTINUE HANDLER FOR NOT FOUND
                        SET uid_not_found = TRUE;

                    SET uid_not_found = FALSE;
                    OPEN user_cursor;
                    FETCH user_cursor INTO uid_found;
                    CLOSE user_cursor;
                    RETURN uid_found;
                END
            """)

            cursor.execute("""
                CREATE FUNCTION countSongsInPlaylist(playlist_id INT) 
                RETURNS INT
                DETERMINISTIC
                READS SQL DATA
                BEGIN 
                    DECLARE song_count INT;
                    SELECT count(*) INTO song_count FROM playlistsong WHERE playlistId = playlist_id;
                    RETURN song_count;
                END
            """)

            cursor.execute("""
                CREATE FUNCTION getPlaylistName(playlist_id INT)
                RETURNS VARCHAR(128)
                DETERMINISTIC
                READS SQL DATA
                BEGIN
                    DECLARE playlist_name VARCHAR(128);
                    SELECT name INTO playlist_name FROM playlists WHERE playlistId = playlist_id;
                    RETURN playlist_name;
                END
            """)

            # Create procedures one by one
            cursor.execute("""
                CREATE PROCEDURE createUser(
                    IN firstName_p VARCHAR(64),
                    IN lastName_p VARCHAR(64),
                    IN email_p VARCHAR(128),
                    IN phone_p VARCHAR(10),
                    IN plan_id INT
                )
                BEGIN
                    DECLARE EXIT HANDLER FOR 1062 BEGIN
                        SELECT "User already exists" as errorMessage;
                    END;
                    INSERT INTO users VALUES(0, firstName_p, lastName_p, email_p, phone_p, plan_id, now());
                END
            """)

            cursor.execute("""
                CREATE PROCEDURE createPlaylist(
                    IN name_p VARCHAR(45),
                    IN status_p VARCHAR(64),
                    IN userId_p INT
                )
                BEGIN
                    INSERT INTO playlists (name, status, userId, tracks) VALUES (name_p, status_p, userId_p, 0);
                END
            """)

            cursor.execute("""
                CREATE PROCEDURE getPlaylistsUser(IN user_id INT)
                BEGIN
                    SELECT * FROM playlists AS p WHERE userId = user_id;
                END
            """)

            cursor.execute("""
                CREATE PROCEDURE addSongPlaylistLink(IN song_id INT, IN playlist_id INT, IN user_id INT)
                BEGIN
                    DECLARE duplicate_entry_for_key TINYINT DEFAULT FALSE;
                    DECLARE EXIT HANDLER FOR 1062 BEGIN
                        SELECT 'Song already exists in playlist' AS errorMessage;
                    END;
                    
                    -- Add song to playlist
                    INSERT INTO playlistsong VALUES(playlist_id, song_id);
                    UPDATE playlists SET tracks = tracks + 1 WHERE playlistId = playlist_id;
                    
                    -- Add to listening history
                    INSERT INTO listening_history (userId, songId) VALUES (user_id, song_id);
                END
            """)

            cursor.execute("""
                CREATE PROCEDURE getPaymentPlans()
                BEGIN
                    SELECT * FROM paymentplans;
                END
            """)

            cursor.execute("""
                CREATE PROCEDURE getUserInformation(IN user_id INT)
                BEGIN
                    SELECT * FROM users WHERE userId = user_id;
                END
            """)

            cursor.execute("""
                CREATE PROCEDURE getPaymentInformation(IN plan_id INT)
                BEGIN
                    SELECT * FROM paymentplans WHERE planId = plan_id;
                END
            """)

            cursor.execute("""
                CREATE PROCEDURE getPlaylistSongs(IN playlist_id INT)
                BEGIN
                    SELECT s.songId, s.title, s.releaseDate, s.duration, a.name as artistName,
                           c.title as albumTitle, g.name as genreName,
                           (SELECT COUNT(*) FROM songlikes WHERE songId = s.songId) as likeCount
                    FROM songs AS s
                    JOIN playlistsong AS p ON s.songId = p.songId
                    JOIN artistsong AS l ON s.songId = l.songId
                    JOIN artists AS a ON l.artistId = a.artistId
                    JOIN albumsong AS b ON s.songId = b.songId
                    JOIN albums as c ON b.albumId = c.albumId
                    JOIN genresong AS gs ON s.songId = gs.songId
                    JOIN genres AS g ON gs.genreId = g.genreId
                    WHERE p.playlistId = playlist_id;
                END
            """)

            cursor.execute("""
                CREATE PROCEDURE getSongs()
                BEGIN
                    SELECT s.songId, s.title, s.releaseDate, s.duration, a.name as artistName,
                           g.name as genreName, c.title as albumTitle
                    FROM songs AS s
                    JOIN albumsong AS b ON s.songId = b.songId
                    JOIN albums as c ON b.albumId = c.albumId
                    JOIN artistsong AS l ON s.songId = l.songId
                    JOIN genresong AS gs ON s.songId = gs.songId
                    JOIN genres AS g ON gs.genreId = g.genreId
                    JOIN artists AS a ON l.artistId = a.artistId;
                END
            """)

            cursor.execute("""
                CREATE PROCEDURE getSongsForPlaylistView(IN playlist_id INT)
                BEGIN
                    SELECT s.songId, s.title, s.releaseDate, s.duration, a.name as artistName,
                           g.name as genreName, c.title as albumTitle,
                           (SELECT COUNT(*) FROM songlikes WHERE songId = s.songId) as likeCount
                    FROM songs AS s
                    JOIN artistsong AS l ON s.songId = l.songId
                    JOIN genresong AS gs ON s.songId = gs.songId
                    JOIN genres AS g ON gs.genreId = g.genreId
                    JOIN artists AS a ON l.artistId = a.artistId
                    JOIN albumsong AS b ON s.songId = b.songId
                    JOIN albums as c ON b.albumId = c.albumId
                    WHERE s.songId NOT IN (
                        SELECT songId FROM playlistsong WHERE playlistId = playlist_id
                    );
                END
            """)

            cursor.execute("""
                CREATE PROCEDURE getSongsFromSearch(IN searchParam VARCHAR(127))
                BEGIN
                    SELECT s.songId, title, releaseDate, duration, name
                    FROM songs AS s
                    JOIN artistsong AS l ON s.songId = l.songId
                    JOIN artists AS a ON l.artistId = a.artistId
                    WHERE title LIKE searchParam;
                END
            """)

            cursor.execute("""
                CREATE PROCEDURE getSong(IN song_id INT)
                BEGIN
                    SELECT s.songId, s.title, s.releaseDate, s.duration, a.name as artistName,
                           g.name as genreName, c.title as albumTitle, c.coverArt,
                           (SELECT COUNT(*) FROM songlikes WHERE songId = s.songId) as likeCount
                    FROM songs AS s
                    JOIN artistsong AS l ON s.songId = l.songId
                    JOIN genresong AS gs ON s.songId = gs.songId
                    JOIN genres AS g ON gs.genreId = g.genreId
                    JOIN artists AS a ON l.artistId = a.artistId
                    JOIN albumsong AS b ON s.songId = b.songId
                    JOIN albums as c ON b.albumId = c.albumId
                    WHERE s.songId = song_id;
                END
            """)

            cursor.execute("""
                CREATE PROCEDURE editPlaylist(
                    IN name_p VARCHAR(45),
                    IN status_p VARCHAR(64),
                    IN playlist_id INT
                )
                BEGIN
                    UPDATE playlists
                    SET name = name_p, status = status_p
                    WHERE playlistId = playlist_id;
                END
            """)

            cursor.execute("""
                CREATE PROCEDURE editPaymentPlan(IN user_id INT, IN plan_id INT)
                BEGIN
                    UPDATE users
                    SET planId = plan_id, planDate = now()
                    WHERE userId = user_id;
                END
            """)

            cursor.execute("""
                CREATE PROCEDURE removeSongFromPlaylist(IN playlist_id INT, IN song_id INT)
                BEGIN
                    DELETE FROM playlistsong
                    WHERE playlistId = playlist_id AND songId = song_id;
                    UPDATE playlists SET tracks = tracks - 1 WHERE playlistId = playlist_id;
                END
            """)

            cursor.execute("""
                CREATE PROCEDURE removePlaylist(IN playlist_id INT)
                BEGIN
                    DELETE FROM playlists WHERE playlistId = playlist_id;
                END
            """)

            cursor.execute("""
                CREATE PROCEDURE removeUser(IN user_id INT)
                BEGIN
                    DELETE FROM playlists WHERE userId = user_id;
                    DELETE FROM users WHERE userId = user_id;
                END
            """)

            cursor.execute("""
                CREATE PROCEDURE likeSong(IN user_id INT, IN song_id INT)
                BEGIN
                    INSERT IGNORE INTO songlikes (userId, songId) VALUES (user_id, song_id);
                END
            """)

            cursor.execute("""
                CREATE PROCEDURE unlikeSong(IN user_id INT, IN song_id INT)
                BEGIN
                    DELETE FROM songlikes WHERE userId = user_id AND songId = song_id;
                END
            """)

            cursor.execute("""
                CREATE PROCEDURE isLikedBySong(IN user_id INT, IN song_id INT)
                BEGIN
                    SELECT COUNT(*) as liked FROM songlikes WHERE userId = user_id AND songId = song_id;
                END
            """)

            cursor.execute("""
                CREATE PROCEDURE addComment(
                    IN user_id INT,
                    IN song_id INT,
                    IN comment_text TEXT
                )
                BEGIN
                    INSERT INTO songcomments (userId, songId, comment) 
                    VALUES (user_id, song_id, comment_text);
                END
            """)

            cursor.execute("""
                CREATE PROCEDURE getSongComments(IN song_id INT)
                BEGIN
                    SELECT c.commentId, c.comment, c.createdAt, 
                           u.firstName, u.lastName
                    FROM songcomments c
                    JOIN users u ON c.userId = u.userId
                    WHERE c.songId = song_id
                    ORDER BY c.createdAt DESC;
                END
            """)

            cursor.execute("""
                CREATE PROCEDURE deleteComment(
                    IN comment_id INT,
                    IN user_id INT
                )
                BEGIN
                    DELETE FROM songcomments 
                    WHERE commentId = comment_id 
                    AND userId = user_id;
                END
            """)

            cursor.execute("""
                CREATE PROCEDURE addToHistory(
                    IN user_id INT,
                    IN song_id INT
                )
                BEGIN
                    INSERT INTO listening_history (userId, songId) 
                    VALUES (user_id, song_id);
                END
            """)

            cursor.execute("""
                CREATE PROCEDURE getListeningHistory(
                    IN user_id INT,
                    IN limit_count INT
                )
                BEGIN
                    SELECT h.historyId, h.listenedAt, 
                           s.songId, s.title, s.duration,
                           a.name as artistName,
                           al.title as albumTitle,
                           al.coverArt,
                           g.name as genreName,
                           (SELECT COUNT(*) FROM songlikes WHERE songId = s.songId) as likeCount
                    FROM (
                        SELECT songId, MAX(listenedAt) as maxListenedAt
                        FROM listening_history
                        WHERE userId = user_id
                        GROUP BY songId
                    ) latest_plays
                    JOIN listening_history h ON h.songId = latest_plays.songId 
                        AND h.listenedAt = latest_plays.maxListenedAt
                        AND h.userId = user_id
                    JOIN songs s ON h.songId = s.songId
                    JOIN artistsong ast ON s.songId = ast.songId
                    JOIN artists a ON ast.artistId = a.artistId
                    JOIN albumsong als ON s.songId = als.songId
                    JOIN albums al ON als.albumId = al.albumId
                    JOIN genresong gs ON s.songId = gs.songId
                    JOIN genres g ON gs.genreId = g.genreId
                    ORDER BY h.listenedAt DESC
                    LIMIT limit_count;
                END
            """)

            cursor.execute("""
                CREATE PROCEDURE addChatMessage(
                    IN user_id INT,
                    IN message_text TEXT
                )
                BEGIN
                    INSERT INTO chat_messages (userId, message) 
                    VALUES (user_id, message_text);
                    
                    -- Return the inserted message with user details
                    SELECT m.messageId, m.message, m.createdAt,
                           u.userId, u.firstName, u.lastName
                    FROM chat_messages m
                    JOIN users u ON m.userId = u.userId
                    WHERE m.messageId = LAST_INSERT_ID();
                END
            """)

            cursor.execute("""
                CREATE PROCEDURE getRecentMessages(
                    IN limit_count INT
                )
                BEGIN
                    SELECT m.messageId, m.message, m.createdAt,
                           u.userId, u.firstName, u.lastName
                    FROM chat_messages m
                    JOIN users u ON m.userId = u.userId
                    ORDER BY m.createdAt DESC
                    LIMIT limit_count;
                END
            """)

            # Insert default payment plans if they don't exist
            cursor.execute("SELECT COUNT(*) FROM paymentplans")
            if cursor.fetchone()[0] == 0:
                cursor.execute("""
                    INSERT INTO paymentplans (amount, type) VALUES 
                    (0, 'Free'),
                    (9, 'Monthly'),
                    (90, 'Yearly')
                """)
            
        conn.commit()
    except Exception as e:
        print(f"Error initializing database: {str(e)}")
    finally:
        conn.close()

# Initialize database when creating the app
with app.app_context():
    init_db()

# Initialize SocketIO with proper configuration
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

"""

Login Page

"""
@app.route("/")
@app.route("/login", methods=['GET', 'POST'])
def login():
    #Error message
    errorMessage = ''
    #Check if email and phone number is in POST
    if request.method == 'POST' and 'email' in request.form and 'phone' in request.form:

        # Create variables for easy access
        email = request.form['email']
        phone = request.form['phone']

        # Check if account exists using MySQL Function findUser
        cursor = get_db().cursor()
        cursor.execute('SELECT findUser(%s, %s) as foundUser', (email, phone,))
        account = cursor.fetchone()[0]

        # If account exists in accounts table in out database
        if account:
            # Session data with id and if the user is logged in
            session['userLoggedIn'] = True
            session['id'] = account
            # Redirect to home page
            return redirect(url_for('home'))
        else:
            # Account doesnt exist or username/password incorrect
            errorMessage = 'Invalid username/password!'
    # Show the login form with message
    return render_template('login.html', errorMessage = errorMessage)


"""

Logout Page

"""
@app.route('/logout')
def logout():
    # Remove session data, this will log the user out
    session.pop('userLoggedIn', None)
    session.pop('id', None)
    # Redirect to login page
    return redirect(url_for('login'))



"""

Register Page and dependencies

"""

"""

Verify fields of the user registration form

"""
def verifyUser(firstName, lastName, email, phone, plan):
    #Check email address format make sure @ has text on either side
    if not re.match(r'[^@]+@[^@]+\.[^@]+', email):
        return 'Invalid email address!'
    #Check first name for only alpha characters
    elif not re.match(r'[A-Za-z]+', firstName):
        return 'Name must cotain only characters!'
    #Check last name for only alpha characters
    elif not re.match(r'[A-Za-z]+', lastName):
        return 'Name must cotain only characters!'
    #Check to make sure phone number is only 10 digits
    elif not re.match(r'[0-9]{10}', phone):
        return 'Phone number must only be 10 digits!'
    #Check if form is filled out and no missing fields    
    elif not firstName or not lastName or not email or not phone or not plan:
        return 'Please fill out the form!'
    return '' 

@app.route('/register', methods=['GET', 'POST'])
def register():
    errorMessage = ''
    paymentPlans = []  # Initialize paymentPlans as an empty list
    conn = None
    try:
        #Get payment plan information for registration
        conn = get_db()
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        cursor.callproc('getPaymentPlans')
        paymentPlans = cursor.fetchall()
        cursor.close()

        # Check if firstname, lastname, email, phone and plan are selected
        if (request.method == 'POST' and 'firstName' in request.form and 
            'lastName' in request.form and 'email' in request.form and 
            'phone' in request.form and 'plan' in request.form): 

            # Create variables for easy access to each field in the signup form
            firstName = request.form['firstName']
            lastName = request.form['lastName']
            email = request.form['email']
            phone = request.form['phone']
            plan = request.form['plan']

            # Output message to let the user know if there is an error in the form
            errorMessage = verifyUser(firstName, lastName, email, phone, plan)
            # If account exists show error and validation checks
            if(errorMessage == ''):
                # Account doesnt exists and the form data is valid, now insert new account into accounts table
                cursor = conn.cursor()
                cursor.callproc('createUser', args = (firstName, lastName, email, phone, plan))
                errorMessage = cursor.fetchone()
                if(errorMessage):
                    errorMessage = errorMessage[0]
                conn.commit()
                cursor.close()

                # If account exists in accounts table in out database
                if not errorMessage:
                    # Check if account exists using MySQL Function findUser
                    cursor = conn.cursor()
                    cursor.execute('SELECT findUser(%s, %s) as foundUser', (email, phone,))
                    account = cursor.fetchone()
                    cursor.close()
                    if account:
                        # Session data with id and loggedin information
                        session['userLoggedIn'] = True
                        session['id'] = account[0]
                        # Redirect to home page
                        return redirect(url_for('home'))

        elif request.method == 'POST':
            # Form is empty
            errorMessage = 'Please complete the registration'
    except Exception as e:
        errorMessage = f'An error occurred: {str(e)}'
    finally:
        if conn:
            conn.close()
    # Show registration form with error message if incorrent form data
    return render_template('register.html', errorMessage = errorMessage, paymentplans = paymentPlans)


"""

Home Page and dependencies

"""
# Calculate the total duration of all the songs in the playlist
def calculateTotalDuration(playlistsongs):
    totalTime = 0
    for p in playlistsongs:
        if not totalTime:
            totalTime = p['duration']
        else:
            totalTime += p['duration']
    return totalTime

@app.route('/home', methods = ['GET', 'POST'])
def home():
    # Check if user is loggedin
    if 'userLoggedIn' in session:
        conn = None
        try:
            conn = get_db()
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            
            #Button to create a new playlist
            if request.method == 'POST' and 'new' in request.form:
                return redirect(url_for('newplaylist'))
            
            #View the songs within an individual playlist
            if request.method == 'POST' and 'view' in request.form:
                playlistId = request.form['view']
                return redirect(url_for('playlist', playlist_id=playlistId))

            #Remove playlist from the database
            if request.method == 'POST' and 'remove' in request.form:
                playlistId = request.form['remove']
                try:
                    cursor.execute('CALL removePlaylist(%s)', (playlistId))
                    conn.commit()
                    # Redirect to refresh the page after removal
                    return redirect(url_for('home'))
                except Exception as e:
                    print(f"Error removing playlist: {str(e)}")

            # Get liked songs count and details
            cursor.execute("""
                SELECT COUNT(*) as liked_count 
                FROM songlikes 
                WHERE userId = %s
            """, (session['id'],))
            liked_info = cursor.fetchone()

            # Get liked songs details
            cursor.execute("""
                SELECT s.songId, s.title, s.duration,
                       a.name as artistName,
                       al.title as albumTitle,
                       al.coverArt,
                       g.name as genreName,
                       sl.likedAt
                FROM songlikes sl
                JOIN songs s ON sl.songId = s.songId
                JOIN artistsong ast ON s.songId = ast.songId
                JOIN artists a ON ast.artistId = a.artistId
                JOIN albumsong als ON s.songId = als.songId
                JOIN albums al ON als.albumId = al.albumId
                JOIN genresong gs ON s.songId = gs.songId
                JOIN genres g ON gs.genreId = g.genreId
                WHERE sl.userId = %s
                ORDER BY sl.likedAt DESC
            """, (session['id'],))
            liked_songs = cursor.fetchall()

            #Get the users playlist
            cursor.execute('CALL getPlaylistsUser(%s)', (session['id']))
            playlists = list(cursor.fetchall())

            #Get information on each of the users playlist and sum the total duration
            #of all the songs in the playlist
            for p in playlists:
                cursor.execute('CALL getPlaylistSongs(%s)', (p['playlistId']))
                playlistsongs = list(cursor.fetchall())
                p['duration'] = calculateTotalDuration(playlistsongs)
            
            return render_template('home.html', 
                                playlists=playlists, 
                                liked_count=liked_info['liked_count'],
                                liked_songs=liked_songs)
        except Exception as e:
            print(f"Error in home route: {str(e)}")
            return render_template('home.html', 
                                playlists=[], 
                                liked_count=0,
                                liked_songs=[],
                                error=f"An error occurred: {str(e)}")
        finally:
            if conn:
                conn.close()
    # User is not loggedin redirect to login page
    return redirect(url_for('login'))


"""

Profile Page and dependencies

"""
@app.route('/profile', methods = ['POST', 'GET'])
def profile():
    # Check if user is loggedin
    if 'userLoggedIn' in session:
        if request.method == 'POST' and 'edit' in request.form:
            return redirect(url_for('editplan'))
        
        if request.method == 'POST' and 'delete' in request.form:
            cursor = get_db().cursor(pymysql.cursors.DictCursor)
            cursor.callproc("removeUser", args = (session['id'],))
            get_db().commit()
            return redirect(url_for('logout'))
        
        #Get information about the user to display
        cursor = get_db().cursor(pymysql.cursors.DictCursor)
        cursor.callproc('getUserInformation', args = (session['id'],))
        userInfo = cursor.fetchone()
        #Get information about the payment plan based on the users
        cursor.callproc('getPaymentInformation', (userInfo['planId'],))
        paymentInfo = cursor.fetchone()
        #Convert date user signed up for payment plan to a readable format
        dateStr = str(userInfo['planDate'].month) + '/' + str(userInfo['planDate'].day) + '/' + str(userInfo['planDate'].year)
        return render_template('profile.html', userinfo=userInfo, paymentinfo = paymentInfo, datestr = dateStr)
        
    # User is not loggedin redirect to login page
    return redirect(url_for('login'))


@app.route('/editplan', methods=['GET', 'POST'])
def editplan():
    # Check if user is loggedin
    if 'userLoggedIn' in session:
        conn = None
        try:
            conn = get_db()
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            
            #Get payment plans
            cursor.execute('call getPaymentPlans()')
            paymentPlans = cursor.fetchall()
            cursor.close()

            if request.method == 'POST' and 'plan' in request.form:
                plan = request.form['plan']
                # Call process to change payment plan
                cursor = conn.cursor(pymysql.cursors.DictCursor)
                try:
                    cursor.execute('call editPaymentPlan(%s, %s)', (session['id'], plan))
                    conn.commit()
                    cursor.close()
                    # Redirect to profile page
                    return redirect(url_for('profile'))
                except Exception as e:
                    print(f"Error updating payment plan: {str(e)}")
                    return render_template('editplan.html', plans=paymentPlans, error=f"Error updating payment plan: {str(e)}")
            
            return render_template('editplan.html', plans=paymentPlans)
        except Exception as e:
            print(f"Error in editplan route: {str(e)}")
            return render_template('editplan.html', plans=[], error=f"An error occurred: {str(e)}")
        finally:
            if conn:
                conn.close()
    # User is not loggedin redirect to login page
    return redirect(url_for('login'))


"""

New Playlist Page

"""
@app.route('/newplaylist', methods=['GET', 'POST'])
def newplaylist():
    status = ['Public', 'Private']
    conn = None
    try:
        # Check if user is loggedin
        if 'userLoggedIn' in session:
            #Check if name of playlist and the status is in the form
            if request.method == 'POST' and 'name' in request.form and 'status' in request.form:
                name = request.form['name']
                status = request.form['status']
                
                # Get database connection
                conn = get_db()
                cursor = conn.cursor(pymysql.cursors.DictCursor)
                
                # Call the stored procedure
                cursor.callproc('createPlaylist', args=(name, status, session['id']))
                
                # Commit the transaction
                conn.commit()
                
                # Close cursor and connection
                cursor.close()
                conn.close()
                
                # Redirect to home page
                return redirect(url_for('home'))
            return render_template('newplaylist.html', status=status)
        # User is not loggedin redirect to login page
        return redirect(url_for('login'))
    except Exception as e:
        # Log the error and return it to the template
        print(f"Error creating playlist: {str(e)}")
        if conn:
            conn.close()
        return render_template('newplaylist.html', status=status, error=f"Error creating playlist: {str(e)}")


"""

Edit Playlist Page

"""
@app.route('/editplaylist/<playlist_id>', methods=['GET', 'POST'])
def editplaylist(playlist_id):
    status = ['Public', 'Private']
    # Check if user is loggedin
    if 'userLoggedIn' in session:
        conn = get_db()
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        try:
            # Get current playlist name and status
            cursor.execute('SELECT name, status FROM playlists WHERE playlistId = %s', (playlist_id,))
            result = cursor.fetchone()
            if not result:
                return redirect(url_for('home'))
            current_name = result['name']
            current_status = result['status']

            #Check if the name of the playlist is in the form
            if request.method == 'POST' and 'name' in request.form:
                name = request.form['name']
                status = request.form['status']
                print(f"Updating playlist {playlist_id} with name: {name}, status: {status}")  # Debug log
                
                try:
                    cursor.callproc('editPlaylist', (name, status, playlist_id))
                    conn.commit()
                    print(f"Successfully updated playlist {playlist_id}")  # Debug log
                    return redirect(url_for('playlist', playlist_id=playlist_id))
                except Exception as e:
                    print(f"Error updating playlist: {str(e)}")  # Debug log
                    return render_template('editplaylist.html', 
                                        status=status, 
                                        name=current_name, 
                                        error=f"Error updating playlist: {str(e)}")

            return render_template('editplaylist.html', 
                                status=status, 
                                name=current_name,
                                current_status=current_status)
        except Exception as e:
            print(f"Error in editplaylist route: {str(e)}")  # Debug log
            return render_template('editplaylist.html', 
                                status=status, 
                                name="Error", 
                                error=str(e))
        finally:
            cursor.close()
            conn.close()
    return redirect(url_for('login'))


"""

Playlist Page

"""
@app.route('/playlist/<playlist_id>', methods=['GET', 'POST'])
def playlist(playlist_id):
    if 'userLoggedIn' in session:
        conn = get_db()
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        try:
            #View information about a song
            if request.method == 'POST' and 'view' in request.form:
                song_id = request.form['view']
                return redirect(url_for('song', song_id = song_id, playlist_id = playlist_id))
            
            #Remove song from the current playlist
            if request.method == 'POST' and 'delete' in request.form:
                song_id = request.form['delete']
                cursor.callproc('removeSongFromPlaylist', args = (playlist_id, song_id))
                conn.commit()
                # Refresh the page after deletion
                return redirect(url_for('playlist', playlist_id=playlist_id))
            
            #Edit name of playlist
            if request.method == 'POST' and 'edit' in request.form:
                return redirect(url_for('editplaylist', playlist_id=playlist_id))

            #Get name of the current playlist
            cursor.execute('SELECT name FROM playlists WHERE playlistId = %s', (playlist_id,))
            result = cursor.fetchone()
            if not result:
                return redirect(url_for('home'))
            playlistname = result['name']
            print(f"Playlist name: {playlistname}")  # Debug log

            #Get playlist songs using sql procedure
            cursor.callproc('getPlaylistSongs', args = (playlist_id,))
            playlistsongs = list(cursor.fetchall())
            print(f"Retrieved {len(playlistsongs)} songs for playlist {playlist_id}")  # Debug log
            for song in playlistsongs:
                print(f"Song data: {song}")  # Debug log

            return render_template('playlist.html', 
                                playlistsongs=playlistsongs, 
                                playlistId=playlist_id, 
                                name=playlistname)
        except Exception as e:
            print(f"Error in playlist route: {str(e)}")
            return render_template('playlist.html', 
                                playlistsongs=[], 
                                playlistId=playlist_id, 
                                name="Error", 
                                error=str(e))
        finally:
            cursor.close()
            conn.close()
    return redirect(url_for('login'))

"""

Songs Page

"""
@app.route('/songs/<playlist_id>', methods=['GET', 'POST'])
def songs(playlist_id):
    if 'userLoggedIn' in session:
        conn = get_db()
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        try:
            #View information on individual song
            if request.method == 'POST' and 'view' in request.form:
                song_id = request.form['view']
                return redirect(url_for('song', song_id = song_id, playlist_id = playlist_id))

            #If user wants to add song to playlist
            if request.method == 'POST' and 'add' in request.form:
                song_id = request.form['add']
                print(f"Attempting to add song {song_id} to playlist {playlist_id}")  # Debug log
                
                # First verify the song and playlist exist
                cursor.execute('SELECT COUNT(*) FROM songs WHERE songId = %s', (song_id,))
                if cursor.fetchone()['COUNT(*)'] == 0:
                    print(f"Song {song_id} does not exist")
                    return redirect(url_for('songs', playlist_id=playlist_id))
                
                cursor.execute('SELECT COUNT(*) FROM playlists WHERE playlistId = %s', (playlist_id,))
                if cursor.fetchone()['COUNT(*)'] == 0:
                    print(f"Playlist {playlist_id} does not exist")
                    return redirect(url_for('songs', playlist_id=playlist_id))
                
                # Add song to playlist and record in history
                try:
                    cursor.callproc('addSongPlaylistLink', (song_id, playlist_id, session['id']))
                    conn.commit()
                    print(f"Successfully added song {song_id} to playlist {playlist_id}")
                    return redirect(url_for('playlist', playlist_id=playlist_id))
                except Exception as e:
                    print(f"Error adding song: {str(e)}")
                    return redirect(url_for('songs', playlist_id=playlist_id))
            
            #Get songs that aren't in playlist using sql query
            cursor.execute('CALL getSongsForPlaylistView(%s)', (playlist_id))
            songs = list(cursor.fetchall())    

            return render_template('songs.html', songs = songs, playlistId = playlist_id)
        except Exception as e:
            print(f"Error in songs route: {str(e)}")
            return render_template('songs.html', songs = [], playlistId = playlist_id, error=str(e))
        finally:
            cursor.close()
            conn.close()
    return redirect(url_for('login'))

"""

Song Info Page

"""
@app.route('/playlist/<playlist_id>/song/<song_id>', methods=['GET', 'POST'])
def song(song_id, playlist_id):
    if 'userLoggedIn' in session:
        conn = get_db()
        try:
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            
            # Record this song view in listening history
            cursor.callproc('addToHistory', (session['id'], song_id))
            conn.commit()
            
            #If user wants to return to the playlist songs page
            if request.method == 'POST' and 'back' in request.form:
                return redirect(url_for('playlist', playlist_id = playlist_id))

            #Get information on individual song    
            cursor.callproc('getSong', args = (song_id,))
            song = cursor.fetchone()
            if song is None:
                return redirect(url_for('playlist', playlist_id=playlist_id))
            
            return render_template('songdetails.html', song=song)
        except Exception as e:
            print(f"Error in song route: {str(e)}")
            return redirect(url_for('playlist', playlist_id=playlist_id))
        finally:
            cursor.close()
            conn.close()
    return redirect(url_for('login'))

@app.route('/song/like/<int:song_id>', methods=['POST'])
def like_song(song_id):
    if 'userLoggedIn' in session:
        conn = get_db()
        try:
            cursor = conn.cursor()
            cursor.callproc('likeSong', (session['id'], song_id))
            conn.commit()
            return jsonify({'success': True})
        except Exception as e:
            print(f"Error liking song: {str(e)}")
            return jsonify({'success': False, 'error': str(e)})
        finally:
            cursor.close()
            conn.close()
    return jsonify({'success': False, 'error': 'Not logged in'})

@app.route('/song/unlike/<int:song_id>', methods=['POST'])
def unlike_song(song_id):
    if 'userLoggedIn' in session:
        conn = get_db()
        try:
            cursor = conn.cursor()
            cursor.callproc('unlikeSong', (session['id'], song_id))
            conn.commit()
            return jsonify({'success': True})
        except Exception as e:
            print(f"Error unliking song: {str(e)}")
            return jsonify({'success': False, 'error': str(e)})
        finally:
            cursor.close()
            conn.close()
    return jsonify({'success': False, 'error': 'Not logged in'})

@app.route('/song/is_liked/<int:song_id>', methods=['GET'])
def is_song_liked(song_id):
    if 'userLoggedIn' in session:
        conn = get_db()
        try:
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            cursor.callproc('isLikedBySong', (session['id'], song_id))
            result = cursor.fetchone()
            return jsonify({'liked': result['liked'] > 0})
        except Exception as e:
            print(f"Error checking if song is liked: {str(e)}")
            return jsonify({'error': str(e)})
        finally:
            cursor.close()
            conn.close()
    return jsonify({'liked': False})

@app.route('/song/comment/<int:song_id>', methods=['POST'])
def add_comment(song_id):
    if 'userLoggedIn' in session:
        if not request.json or 'comment' not in request.json:
            return jsonify({'success': False, 'error': 'No comment provided'})
            
        comment = request.json['comment'].strip()
        if not comment:
            return jsonify({'success': False, 'error': 'Comment cannot be empty'})
            
        conn = get_db()
        try:
            cursor = conn.cursor()
            cursor.callproc('addComment', (session['id'], song_id, comment))
            conn.commit()
            
            # Get the user's name for the response
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            cursor.execute('SELECT firstName, lastName FROM users WHERE userId = %s', (session['id'],))
            user = cursor.fetchone()
            
            return jsonify({
                'success': True,
                'comment': {
                    'comment': comment,
                    'firstName': user['firstName'],
                    'lastName': user['lastName'],
                    'createdAt': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
            })
        except Exception as e:
            print(f"Error adding comment: {str(e)}")
            return jsonify({'success': False, 'error': str(e)})
        finally:
            conn.close()
    return jsonify({'success': False, 'error': 'Not logged in'})

@app.route('/song/comments/<int:song_id>', methods=['GET'])
def get_comments(song_id):
    if 'userLoggedIn' in session:
        conn = get_db()
        try:
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            cursor.callproc('getSongComments', (song_id,))
            comments = cursor.fetchall()
            return jsonify({'success': True, 'comments': comments})
        except Exception as e:
            print(f"Error getting comments: {str(e)}")
            return jsonify({'success': False, 'error': str(e)})
        finally:
            conn.close()
    return jsonify({'success': False, 'error': 'Not logged in'})

@app.route('/song/comment/<int:comment_id>', methods=['DELETE'])
def delete_comment(comment_id):
    if 'userLoggedIn' in session:
        conn = get_db()
        try:
            cursor = conn.cursor()
            cursor.callproc('deleteComment', (comment_id, session['id']))
            conn.commit()
            return jsonify({'success': True})
        except Exception as e:
            print(f"Error deleting comment: {str(e)}")
            return jsonify({'success': False, 'error': str(e)})
        finally:
            conn.close()
    return jsonify({'success': False, 'error': 'Not logged in'})

@app.route('/history')
def listening_history():
    if 'userLoggedIn' in session:
        conn = get_db()
        try:
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            cursor.callproc('getListeningHistory', (session['id'], 50))  # Get last 50 songs
            history = cursor.fetchall()
            return render_template('history.html', history=history)
        except Exception as e:
            print(f"Error getting listening history: {str(e)}")
            return render_template('history.html', history=[], error=str(e))
        finally:
            cursor.close()
            conn.close()
    return redirect(url_for('login'))

@app.route('/chat')
def chat():
    if 'userLoggedIn' in session:
        conn = get_db()
        try:
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            cursor.callproc('getRecentMessages', (50,))  # Get last 50 messages
            messages = cursor.fetchall()
            # Sort messages by createdAt in ascending order for proper display
            messages.sort(key=lambda x: x['createdAt'])
            return render_template('chat.html', messages=messages)
        except Exception as e:
            print(f"Error getting chat messages: {str(e)}")
            return render_template('chat.html', messages=[], error=str(e))
        finally:
            cursor.close()
            conn.close()
    return redirect(url_for('login'))

@socketio.on('connect')
def handle_connect():
    if 'userLoggedIn' not in session:
        return False
    print(f"Client connected: {request.sid}")
    return True

@socketio.on('disconnect')
def handle_disconnect():
    print(f"Client disconnected: {request.sid}")

@socketio.on('send_message')
def handle_message(data):
    if 'userLoggedIn' not in session:
        return
    
    conn = get_db()
    try:
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        cursor.callproc('addChatMessage', (session['id'], data['message']))
        message = cursor.fetchone()
        conn.commit()  # Make sure to commit the transaction
        
        # Format the message for broadcast
        formatted_message = {
            'messageId': message['messageId'],
            'message': message['message'],
            'createdAt': message['createdAt'].strftime('%Y-%m-%d %H:%M:%S'),
            'userId': message['userId'],
            'firstName': message['firstName'],
            'lastName': message['lastName']
        }
        
        # Emit the message to all connected clients
        emit('new_message', formatted_message, broadcast=True)
        print(f"Message broadcasted: {formatted_message}")
    except Exception as e:
        print(f"Error sending message: {str(e)}")
        emit('error', {'error': str(e)})
    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    socketio.run(app, debug=True, allow_unsafe_werkzeug=True)
