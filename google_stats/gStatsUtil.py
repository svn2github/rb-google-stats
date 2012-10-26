import gStatsTest
import urllib, urllib2
import json
import time



# Retrieves the Auth token from Google
def google_auth(username, password):
    auth_token = None 
    req = urllib2.Request(url='https://www.google.com/accounts/ClientLogin',
                data=urllib.urlencode({'Email': username,
                                       'Passwd': password,
                                       'source': 'music', 'service': 'sj',
                                       'accountType': 'GOOGLE'}))
    f = urllib2.urlopen(req)
    
    for line in (f.readlines()):
        if line.find('Auth=') > -1:
            auth_token=line[5:].rstrip()
            break

    return auth_token






# Retrieves the xt token from Google (required for api calls)
def google_xt(auth_token):
    xt = None
    req = urllib2.Request(url='https://play.google.com/music/services/loadalltracks',
                        data="u=0",
                        headers={'Authorization': "GoogleLogin auth={0}".format(auth_token)})
        
    f = urllib2.urlopen(req)
   
    import re
   
    pattern = re.compile('^.*xt=([^;]+);.*$')
    m = pattern.match(f.headers.getheader('Set-Cookie'))
    if m:
        xt = m.group(1)

    return xt



def fetch_google_tracks(username, password, auth_token, xt_token,
                        use_cache=False, dump_cache=False, data_dir=None):

    if use_cache:
        tracks = gStatsTest.fetch_google_tracks_test(username,
                                                     password,
                                                     data_dir)
    else:
        # Login (get auth tokens)
        if auth_token == None:
            auth_token = google_auth(username, password)
        
        if xt_token == None:
            xt_token = google_xt(auth_token)

        if auth_token != None and xt_token != None:
            # Get first chunk of songs
            req = urllib2.Request(url='https://play.google.com/music/services/loadalltracks',
                        data=urllib.urlencode({'u':0, 'xt':xt_token}),  
                        headers={'Authorization': "GoogleLogin auth={0}".format(auth_token)})
            f = urllib2.urlopen(req)
            res = f.read()
            jdata = json.loads(res)
            tracks = jdata['playlist']
    
            # Get subsequent chunks
            while 'continuationToken' in jdata:
                ct = jdata['continuationToken']
                req = urllib2.Request(
                        url='https://play.google.com/music/services/loadalltracks',
                        data=urllib.urlencode({'u':0, 'xt':xt_token, 
                                'json': "{\"continuationToken\": \"%s\"}" % (ct)}),  
                        headers={'Authorization': "GoogleLogin auth={0}".format(auth_token)})
                f = urllib2.urlopen(req)
                res = f.read()
                jdata = json.loads(res)
                tracks.extend(jdata['playlist'])
    
        
        if dump_cache:
            gStatsTest.cache_tracks(tracks, data_dir)


        # Write the tracks to cache.db
        import sqlite3

        db_filename = "{0}/cache.db".format(data_dir)
        conn = sqlite3.connect(db_filename)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS google
                                     (id TEXT PRIMARY KEY,
                                      rating INTEGER,
                                      lastPlayed INTEGER,
                                      playCount INTEGER,
                                      genre TEXT,
                                      artist TEXT,
                                      album TEXT,
                                      title TEXT)''')

        for track in tracks:
            c.execute('INSERT OR REPLACE INTO google VALUES (?,?,?,?,?,?,?,?)',
                        (track['id'], track['rating'], track['lastPlayed'], track['playCount'],
                        track['genre'], track['artist'], track['album'], track['title']))

        conn.commit()
        c.close()
        conn.close()


    return (auth_token, xt_token)




def fetch_playlists(username, password, auth_token, xt_token, data_dir):

    # Write the tracks to cache.db
    import sqlite3

    db_filename = "{0}/cache.db".format(data_dir)
    conn = sqlite3.connect(db_filename)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS playlists
                                 (id TEXT PRIMARY KEY,
                                  name TEXT)''')

    c.execute('''CREATE TABLE IF NOT EXISTS playlist_entries
                                 (track_id TEXT,
                                  playlist_id TEXT,
                                  playlist_name TEXT)''')
    
    if auth_token == None:
        auth_token = google_auth(username, password)
        
    if xt_token == None:
        xt_token = google_xt(auth_token)

    # Get user playlists
    req = urllib2.Request(url='https://play.google.com/music/services/loadplaylist',
                        data=urllib.urlencode({'u':0, 'xt':xt_token}),  
                        headers={'Authorization': "GoogleLogin auth={0}".format(auth_token)})
    f = urllib2.urlopen(req)
    res = f.read()
    jdata = json.loads(res)
    
    # Iterate over each user playlist
    for playlist in jdata['playlists']:
        # Add it to the 'playlists' table
        c.execute('INSERT OR REPLACE INTO playlists VALUES (?,?)', (playlist['playlistId'], playlist['title']))
        # Add track IDs from this playlist to the table
        for track in playlist['playlist']:
            try:
                # Check if it already exists
                c.execute('SELECT track_id FROM playlist_entries WHERE track_id=? AND playlist_id=?', (track['id'], playlist['playlistId']))
                row = c.fetchone()
                if row == None:
                    c.execute('INSERT INTO playlist_entries VALUES (?,?,?)', (track['id'], playlist['playlistId'], playlist['title']))
            except Exception, e:
                print "ERROR: track: {0}; playlist: {1}; {2}".format(track['id'], playlist['playlistId'], e)
                

    conn.commit()
    c.close()
    conn.close()

    print "DONE"
    

def save_account_info(username, password, data_dir):
    if username == None or username == "" or password == None or password == "":
        return

    filename = "{0}/account.dat".format(data_dir)
    f = open(filename, 'w')
    f.write("{0}\n{0}".format(username, password))
    f.close()

    from os import chmod
    from stat import S_IREAD, S_IWRITE
    chmod(filename, (S_IREAD | S_IWRITE))


    
def log(level, message):
    time_str = time.strftime("%b %d %H:%M:%S", time.localtime())                         
    f = open('/home/grant/.local/share/rhythmbox/plugins/google_stats/log.txt', 'a')
    f.write("{0} [{1}]: {2}\n".format(time_str, level, message))
    f.close()


