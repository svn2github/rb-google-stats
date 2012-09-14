import json


# Expects ~/.local/share/rhythmbox/plugins/google_stats/cache/cache.# to exist
def fetch_google_tracks_test(username, password):
    
    filename = '/home/grant/.local/share/rhythmbox/plugins/google_stats/cache/cache'

    f = open(filename)
    tracks = json.load(f)['playlist']
    f.close()

    return tracks



def cache_tracks(tracks):
    filename = '/home/grant/.local/share/rhythmbox/plugins/google_stats/cache/cache'
    
    f = open(filename, 'w')
    f.write(json.dumps({'playlist': tracks}))
    f.close()
