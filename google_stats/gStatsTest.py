import json
import os

# Expects ~/.local/share/rhythmbox/plugins/google_stats/cache to exist
def fetch_google_tracks_test(username, password, plugin_dir):
    
    cache_file = "%s/%s" % (plugin_dir, 'cache')

    f = open(cache_file)
    tracks = json.load(f)['playlist']
    f.close()

    return tracks



def cache_tracks(tracks, plugin_dir):

    cache_file = "%s/%s" % (plugin_dir, 'cache')

    if os.path.isfile(cache_file):
        os.remove(cache_file)

    f = open(cache_file, 'w')
    f.write(json.dumps({'playlist': tracks}))
    f.close()
