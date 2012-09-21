import gStatsTest
import urllib, urllib2
import json



# Retrieves the Auth token from Google
def google_auth(username, password):
    
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
                            headers={'Authorization': "GoogleLogin auth=%s" % auth_token})
        
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

        # Get first chunk of songs
        req = urllib2.Request(url='https://play.google.com/music/services/loadalltracks',
                        data=urllib.urlencode({'u':0, 'xt':xt_token}),  
                        headers={'Authorization': "GoogleLogin auth=%s" % auth_token})
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
                        headers={'Authorization': "GoogleLogin auth=%s" % auth_token})
            f = urllib2.urlopen(req)
            res = f.read()
            jdata = json.loads(res)
            tracks.extend(jdata['playlist'])
    
        
    if dump_cache:
        gStatsTest.cache_tracks(tracks, data_dir)


    # Write the tracks to cache.db
    import sqlite3

    db_filename = "%s/%s" % (data_dir, 'cache.db')
    conn = sqlite3.connect(db_filename)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS google
                                 (id TEXT PRIMARY KEY,
                                  rating INTEGER,
                                  lastPlayed INTEGER,
                                  playCount INTEGER,
                                  artist TEXT,
                                  album TEXT,
                                  title TEXT)''')

    for track in tracks:
        c.execute('INSERT OR REPLACE INTO google VALUES (?,?,?,?,?,?,?)',
                    (track['id'], track['rating'], track['lastPlayed'], track['playCount'],
                    track['artist'], track['album'], track['title']))


    conn.commit()
    c.close()
    conn.close()

    return (auth_token, xt_token)




def save_account_info(username, password, data_dir):
    if username == None or username == "" or password == None or password == "":
        return

    filename = "%s/%s" % (data_dir, 'account.dat')
    f = open(filename, 'w')
    f.write("%s\n%s" % (username, password))
    f.close()

    from os import chmod
    from stat import S_IREAD, S_IWRITE
    os.chmod(filename, (stat.S_IREAD | stat.S_IWRITE))


