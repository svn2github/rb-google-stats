import urllib, urllib2
import re

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
    
    pattern = re.compile('^.*xt=([^;]+);.*$')
    m = pattern.match(f.headers.getheader('Set-Cookie'))
    if m:
        xt = m.group(1)

    return xt

