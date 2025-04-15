from flask import Flask, render_template, request, url_for, session, redirect, jsonify
from datetime import datetime, timedelta
import pymysql
import re
import random
import sys
import db_config

app = Flask(__name__)

app.secret_key = 'streamtime'

#Set up pymysql connection arguments
pymysql_connect_kwargs = {'user': db_config.DB_USER, 
                          'password': db_config.DB_PASS, 
                          'host': db_config.DB_SERVER,
                          'database': db_config.DB}

# Create a function to get database connection
def get_db():
    return pymysql.connect(**pymysql_connect_kwargs)

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
                    # Continue to show playlists even if removal failed

            #Get the users playlist
            cursor.execute('CALL getPlaylistsUser(%s)', (session['id']))
            playlists = list(cursor.fetchall())

            #Get information on each of the users playlist and sum the total duration
            #of all the songs in the playlist
            for p in playlists:
                cursor.execute('CALL getPlaylistSongs(%s)', (p['playlistId']))
                playlistsongs = list(cursor.fetchall())
                p['duration'] = calculateTotalDuration(playlistsongs)
            
            return render_template('home.html', playlists = playlists)
        except Exception as e:
            print(f"Error in home route: {str(e)}")
            return render_template('home.html', playlists = [], error = f"An error occurred: {str(e)}")
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
                
                # Try direct insert first to see if it works
                try:
                    cursor.execute('INSERT INTO playlistsong (playlistId, songId) VALUES (%s, %s)',
                                 (playlist_id, song_id))
                    conn.commit()
                    print(f"Successfully added song {song_id} to playlist {playlist_id}")
                    # Redirect to playlist page to show updated list
                    return redirect(url_for('playlist', playlist_id=playlist_id))
                except pymysql.Error as e:
                    print(f"Error in direct insert: {str(e)}")
                    # If direct insert fails, try the stored procedure
                    cursor.callproc('addSongPlaylistLink', (playlist_id, song_id))
                    conn.commit()
                    print(f"Successfully added song via stored procedure")
                    # Redirect to playlist page to show updated list
                    return redirect(url_for('playlist', playlist_id=playlist_id))
            
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
        #If user wants to return to the playlist songs page
        if request.method == 'POST' and 'back' in request.form:
            return redirect(url_for('playlist', playlist_id = playlist_id))

        #Get information on individual song    
        cursor = get_db().cursor(pymysql.cursors.DictCursor)
        cursor.callproc('getSong', args = (song_id,))
        song = cursor.fetchone()
        #Render song details
        return render_template('songdetails.html', song = song)
    return redirect(url_for('login'))


if __name__ == '__main__':
    app.run(debug=True)
