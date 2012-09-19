import gStatsUtil, gStatsTest
from gi.repository import GObject, RB, Peas, Gtk, Gdk, PeasGtk
import rb
import json
import urllib, urllib2
import os, stat
import time
import sqlite3

class GoogleSyncPlugin (GObject.Object, Peas.Activatable):
    object = GObject.property(type=GObject.Object)

    def __init__(self):
        super(GoogleSyncPlugin, self).__init__()
        # Testing flags
        self.use_cache  = False
        self.dump_cache = False
        self.test       = False
       
        # Authentication credentials
        self.username = None
        self.password = None
        self.auth_token = None
        self.xt_token = None
        

    def do_activate(self):
        shell = self.object
        self.action = Gtk.Action(name='GoogleSyncAction',
                                label=_("Sync Statistics..."),
                                tooltip=_("Synchronize music statistics with Google"),
                                stock_id='')
        self.action.connect ('activate', self.sync_google_stats, shell)
        self.action_group = Gtk.ActionGroup ('NewActionGroup')
        self.action_group.add_action_with_accel(self.action, "<control>G")
        uim = shell.props.ui_manager
        uim.insert_action_group (self.action_group)
        ui_file = rb.find_plugin_file(self, 'menu_ui.xml') 
        self.ui_id = uim.add_ui_from_file (ui_file)
        uim.ensure_update()

        # Get Login info 
        account_file = rb.find_plugin_file(self, 'account.dat')
        if account_file != None:
            f = open(account_file)
            self.username = f.readline()
            self.password = f.readline()

        # Add callback for database entry changes (playCount, lastPlayed, etc)
        shell.props.db.connect('entry-changed', self.entry_change_cb)



    def get_auth_tokens(self):
        if self.auth_token == None:
            self.auth_token = gStatsUtil.google_auth(self.username, self.password)
        if self.xt_token == None:
            self.xt_token = gStatsUtil.google_xt(self.auth_token)
        return (self.auth_token, self.xt_token)



    def do_deactivate(self):
        shell = self.object
        uim = shell.props.ui_manager
        uim.remove_action_group(self.action_group)
        uim.remove_ui(self.ui_id)
        uim.ensure_update()



    def entry_change_cb(self, db, entry, changes):
        if self.username == None or self.password == None:
            return
        
        updated=False
        track = {'id': build_key(entry)}

        for i in range(changes.n_values):
            change = changes.get_nth(i)
            if change.prop == RB.RhythmDBPropType.PLAY_COUNT: 
                updated=True
                track['playCount'] = change.new
            elif change.prop == RB.RhythmDBPropType.LAST_PLAYED:
                updated=True
                track['lastPlayed'] = change.new * 1000000
            #else:
            #    print "GoogleSyncPlugin - entry_change_cb: %s" % (change.prop)

        if updated:
            (auth_token, xt) = self.get_auth_tokens()
            entries_str = json.dumps({'entries': [track]})
            req = urllib2.Request(url='https://play.google.com/music/services/modifyentries',
                           data=urllib.urlencode({'u':0,'xt':xt, 'json': entries_str}),  
                           headers={'Authorization': "GoogleLogin auth=%s" % auth_token})
            f = urllib2.urlopen(req)
            print "GoogleSyncPlugin - %s" % (f.read())
        


    def dialog_callback(self, dialog, response_id=None):
        self.cancel = True
        dialog.destroy()



    def button_callback(self, button, dialog):
        self.cancel = True
        dialog.destroy()



    def get_account_info(self):
        if self.username == None or self.password == None:
            builder = Gtk.Builder()
            builder.add_from_file(rb.find_plugin_file(self, 'account_info.ui'))
    
            dialog = builder.get_object('dialog')
            dialog.run()

            self.username = builder.get_object('usernameEntry').get_text()
            self.password = builder.get_object('passwordEntry').get_text()
            save_account_info(username, password, self.plugin_info)

            dialog.destroy()

        return (self.username, self.password)



    def sync_google_stats(self, action, shell):
        (username, password) = self.get_account_info() 
       
        self.cancel = False

        builder = Gtk.Builder()
        builder.add_from_file(rb.find_plugin_file(self, 'progress.ui'))
        self.label = builder.get_object('label')
        self.progressbar = builder.get_object('progressbar')
        self.button =  builder.get_object('button')
        treeview = builder.get_object('treeview')
        self.liststore = builder.get_object('liststore')

        titleColumn = Gtk.TreeViewColumn('Title', Gtk.CellRendererText(), text=0)
        titleColumn.set_min_width(210)
        titleColumn.set_max_width(210)
        treeview.append_column(titleColumn)
        treeview.append_column(
                Gtk.TreeViewColumn('Plays', Gtk.CellRendererText(), text=1))
        treeview.append_column(
                Gtk.TreeViewColumn('Rating', Gtk.CellRendererText(),text=2))
        treeview.append_column(
                Gtk.TreeViewColumn('Last Played', Gtk.CellRendererText(),text=3))
        treeview.set_model(self.liststore)
        
        dialog = builder.get_object('dialog')
        self.button.connect('clicked', self.button_callback, dialog)
        dialog.connect('response', self.dialog_callback)

        dialog.show_all()

        while Gtk.events_pending():
             Gtk.main_iteration()


        if self.cancel:
            return
       

        self.query_model = shell.props.library_source.props.query_model
        self.db = shell.props.db

        self.fetch_google_tracks(username, password)
        self.update_db()

        # cleanup 
        del self.google_tracks
        del self.progressbar
        del self.label
        del self.button
        del self.liststore
        del self.db
        del self.query_model
        
        


    def fetch_google_tracks(self, username, password):

        if self.use_cache:
            tracks = gStatsTest.fetch_google_tracks_test(username,
                                            password,
                                            self.plugin_info.get_data_dir())
        else:
            # Login (get auth tokens)
            if self.auth_token == None or self.xt_token == None:
                self.get_auth_tokens()

            # Get first chunk of songs
            req = urllib2.Request(url='https://play.google.com/music/services/loadalltracks',
                        data=urllib.urlencode({'u':0, 'xt':self.xt_token}),  
                        headers={'Authorization': "GoogleLogin auth=%s" % self.auth_token})
            f = urllib2.urlopen(req)
            res = f.read()
            jdata = json.loads(res)
            tracks = jdata['playlist']
    
            # Get subsequent chunks
            while 'continuationToken' in jdata:
                ct = jdata['continuationToken']
                req = urllib2.Request(
                            url='https://play.google.com/music/services/loadalltracks',
                            data=urllib.urlencode({'u':0, 'xt':self.xt_token, 
                                'json': "{\"continuationToken\": \"%s\"}" % (ct)}),  
                            headers={'Authorization': "GoogleLogin auth=%s" % self.auth_token})
                f = urllib2.urlopen(req)
                res = f.read()
                jdata = json.loads(res)
                tracks.extend(jdata['playlist'])
    
        
        if self.dump_cache:
            gStatsTest.cache_tracks(tracks, self.plugin_info.get_data_dir())


        # Create a dictionary of string --> track
        # key is Title:Album:Artist
        self.google_tracks = {}
        for track in tracks:
            key = "%s|%s|%s" % (track['title'], track['album'], track['artist'])
            if key in self.google_tracks:
                print "GoogleSyncPlugin ERROR duplicate key: %s" % (key)
            self.google_tracks[key] = track
            



    def update_db(self):
        
        size = len(self.query_model)
        threshold = self.progressbar.get_fraction() + 0.05

        self.label.set_text("Updating %d tracks..." % (len(self.google_tracks)))
        self.progressbar.set_fraction(0.10)

        for i in range(size):
            entry = self.query_model[i][0]
           
            # Rhythmbox track
            rbTrack = {'title':  entry.get_string(RB.RhythmDBPropType.TITLE),
                       'artist': entry.get_string(RB.RhythmDBPropType.ARTIST),
                       'album':  entry.get_string(RB.RhythmDBPropType.ALBUM)}
            
            rb_count = entry.get_ulong(RB.RhythmDBPropType.PLAY_COUNT)
            rb_rating = entry.get_double(RB.RhythmDBPropType.RATING)
            rb_last_played = entry.get_ulong(RB.RhythmDBPropType.LAST_PLAYED)
            rb_genre =  unicode(entry.get_string(RB.RhythmDBPropType.GENRE), 'utf-8')

            # Lookup the entry in the self.google_tracks dictionary
            key = unicode("%s|%s|%s" % (rbTrack['title'],
                                        rbTrack['album'],
                                        rbTrack['artist']), 'utf-8')

            if key in self.google_tracks:
                
                gTrack = self.google_tracks[key]
                google_count = int(gTrack['playCount'])
                google_rating = int(gTrack['rating'])
                google_last_played = int(gTrack['lastPlayed']) / 1000000
                updated=False
                    
                # Play Count
                new_count = max(rb_count, google_count)
                if google_count > rb_count:
                    updated=True
                    if self.test == False:
                        self.db.entry_set(entry, RB.RhythmDBPropType.PLAY_COUNT, new_count)
                 
                # Rating
                new_rating = max(rb_rating, google_rating)
                if google_rating > rb_rating:
                    updated=True
                    if self.test == False:
                        self.db.entry_set(entry, RB.RhythmDBPropType.RATING, new_rating)
                
                # Last Played
                new_last_played = max(rb_last_played, google_last_played)
                if google_last_played > rb_last_played:
                    updated=True
                    if self.test == False:
                        self.db.entry_set(entry, RB.RhythmDBPropType.LAST_PLAYED, new_last_played)

                if updated:
                    lastPlayed_str = time.strftime("%b %d %I:%M %p",
                                                  time.localtime(new_last_played))
                    self.liststore.append([rbTrack['title'],
                                           new_count,
                                           new_rating,
                                           lastPlayed_str])

            else:
                print "GoogleSyncPlugin - no match for %s" % (key)

            # Update the progress in the GUI
            perc = i / float(size)
            if perc > threshold:
                self.progressbar.set_fraction(perc)
                self.progressbar.set_text("(%d/%d)..." % (i+1, size))
                threshold = perc + 0.01
                while Gtk.events_pending():
                    Gtk.main_iteration()

            if self.cancel:
                return

        self.progressbar.set_fraction(1.0)
        self.progressbar.set_text("100%")
        self.label.set_text("Finished")
        self.button.set_label("Done")




class GoogleSyncConfig(GObject.GObject, PeasGtk.Configurable):
    object = GObject.property(type=GObject.GObject)

    def __init__(self):
        GObject.GObject.__init__(self)

    def do_create_configure_widget(self):
       
        def account_details_changed(entry, event):
            username = builder.get_object('usernameEntry').get_text()
            password = builder.get_object('passwordEntry').get_text()
            save_account_info(username, password, self.plugin_info)
            return False


        self.configure_callback_dic = {
            "rb_google_sync_info_changed_cb" : account_details_changed,
        }

        builder = Gtk.Builder()
        builder.add_from_file(rb.find_plugin_file(self, 'preferences.ui'))

        dialog = builder.get_object('vbox1')
        builder.connect_signals(self.configure_callback_dic)

        account_file = rb.find_plugin_file(self, 'account.dat')
        if account_file != None:    
            f = open(account_file)
            builder.get_object('usernameEntry').set_text(f.readline().rstrip())
            builder.get_object('passwordEntry').set_text(f.readline())
            f.close()

        return dialog



def save_account_info(username, password, plugin_info):
    if username == None or username == "" or password == None or password == "":
        return

    filename = "%s/%s" % (plugin_info.get_data_dir(), 'account.dat')
    f = open(filename, 'w')
    f.write("%s\n%s" % (username, password))
    f.close()

    os.chmod(filename, (stat.S_IREAD | stat.S_IWRITE))




def compare_tracks(lhsTrack, rhsTrack):
    
    if lhsTrack['title'] == rhsTrack['title'].encode('utf-8'):
        if lhsTrack['album'] == rhsTrack['album'].encode('utf-8'):
            if lhsTrack['artist'] == rhsTrack['artist'].encode('utf-8'):
                return True
    
    return False




def build_key(entry):
    conn = sqlite3.connect('/home/grant/.config/google-musicmanager/ServerDatabase.db')
    c = conn.cursor()
    c.execute("SELECT ServerId FROM XFILES WHERE MusicName = \"%s\" AND MusicAlbum = \"%s\" AND MusicArtist = \"%s\"" % (entry.get_string(RB.RhythmDBPropType.TITLE),
                          entry.get_string(RB.RhythmDBPropType.ALBUM),
                          entry.get_string(RB.RhythmDBPropType.ARTIST)))
    track_id = c.fetchone()[0]
    c.close()
    conn.close()
    return track_id
