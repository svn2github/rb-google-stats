import gStatsUtil, gStatsTest
from gi.repository import GObject, RB, Peas, Gtk, Gdk, PeasGtk
import rb
import json
import urllib, urllib2
import os
import stat

class GoogleSyncPlugin (GObject.Object, Peas.Activatable):
    object = GObject.property(type=GObject.Object)

    def __init__(self):
        super(GoogleSyncPlugin, self).__init__()
    
    def do_activate(self):
        shell = self.object
        self.action = Gtk.Action(name='GoogleSyncAction',
                                label=_("Sync with Google statistics..."),
                                tooltip=_("Synchronize music statistics with Google"),
                                stock_id='')
        self.action.connect ('activate', self.sync_google_stats, shell)
        self.action_group = Gtk.ActionGroup ('NewActionGroup')
        self.action_group.add_action_with_accel(self.action, "<control>G")
        uim = shell.props.ui_manager
        uim.insert_action_group (self.action_group)
        ui_file = rb.find_plugin_file(self, 'menu_ui.xml') 
        self.ui_id = uim.add_ui_from_file (ui_file)
        uim.ensure_update ()
        
        self.auth_token = None
        self.xt = None


    def do_deactivate(self):
        shell = self.object
        uim = shell.props.ui_manager
        uim.remove_action_group(self.action_group)
        uim.remove_ui(self.ui_id)
        uim.ensure_update()


    def dialog_callback(self, dialog, response_id=None):
        self.cancel = True
        dialog.destroy()


    def button_callback(self, button, dialog):
        self.cancel = True
        dialog.destroy()


    def get_account_info(self):
        
        username = None
        password = None
        account_file = rb.find_plugin_file(self, 'account.dat')

        if account_file != None:
            f = open(account_file)
            username = f.readline()
            password = f.readline()
        else:
            builder = Gtk.Builder()
            builder.add_from_file(rb.find_plugin_file(self, 'account_info.ui'))
    
            dialog = builder.get_object('dialog')
            dialog.run()

            username = builder.get_object('usernameEntry').get_text()
            password = builder.get_object('passwordEntry').get_text()
            save_account_info(username, password, self.plugin_info)

            dialog.destroy()

        return (username, password)


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

        treeview.append_column(Gtk.TreeViewColumn('Title', Gtk.CellRendererText(), text=0))
        treeview.append_column(Gtk.TreeViewColumn('Plays', Gtk.CellRendererText(), text=1))
        treeview.append_column(Gtk.TreeViewColumn('Rating', Gtk.CellRendererText(),text=2))
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

        #Gdk.threads_add_idle(0, self.fetch_google_tracks_idle_cb, [username, password])
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

        if False:
            tracks = gStatsTest.fetch_google_tracks_test(username, password)
        
        else:
            # Login (get auth token)
            if self.auth_token == None:
                self.auth_token = gStatsUtil.google_auth(username, password) 

            # Get xt token
            if self.xt == None:
                self.xt = gStatsUtil.google_xt(self.auth_token) 
            
            # Get first chunk of songs
            req = urllib2.Request(url='https://play.google.com/music/services/loadalltracks',
                        data=urllib.urlencode({'u':0, 'xt':self.xt}),  
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
                            data=urllib.urlencode({'u':0, 'xt':self.xt, 
                                'json': "{\"continuationToken\": \"%s\"}" % (ct)}),  
                            headers={'Authorization': "GoogleLogin auth=%s" % self.auth_token})
                f = urllib2.urlopen(req)
                res = f.read()
                jdata = json.loads(res)
                tracks.extend(jdata['playlist'])
    
            # Start the idle callback method to update
            #Gdk.threads_add_idle(0, self.update_db_idle_cb, None)
   

        # Create a dictionary of string --> track
        # key is Title:Album:Artist
        self.google_tracks = {}
        for track in tracks:
            key = "%s:%s:%s" % (track['title'], track['album'], track['artist'])
            self.google_tracks[key] = track
            


    def update_db(self):
        
        size = len(self.query_model)
        threshold = self.progressbar.get_fraction() + 0.05

        self.label.set_text("Updating %d tracks..." % (len(self.google_tracks)))
        self.progressbar.set_fraction(0.1)

        # build a list of tracks to be uploaded to Google
        google_updates = []

        for i in range(size):
            entry = self.query_model[i][0]
           
            # Rhythmbox track
            rbTrack = {'title':  entry.get_string(RB.RhythmDBPropType.TITLE),
                       'artist': entry.get_string(RB.RhythmDBPropType.ARTIST),
                       'album':  entry.get_string(RB.RhythmDBPropType.ALBUM)}
            
            rb_count = entry.get_ulong(RB.RhythmDBPropType.PLAY_COUNT)
            rb_rating = entry.get_double(RB.RhythmDBPropType.RATING)
            rb_last_played = entry.get_ulong(RB.RhythmDBPropType.LAST_PLAYED)

            # Lookup the entry in the self.google_tracks dictionary
            key = unicode("%s:%s:%s" % (rbTrack['title'],
                                        rbTrack['album'],
                                        rbTrack['artist']), 'utf-8')

            if key in self.google_tracks:
                
                gTrack = self.google_tracks[key]
                google_count = int(gTrack['playCount'])
                google_rating = int(gTrack['rating'])
                google_last_played = int(gTrack['lastPlayed']) / 1000000
                updated=False
                gDict = None

                # if Google > Rhythmbox --> update Rhythmbox
                # else if Rhythmbox > Google --> update Google
                    
                # Play Count
                new_count = max(rb_count, google_count)
                if new_count > rb_count:
                    updated=True
                    self.db.entry_set(entry, RB.RhythmDBPropType.PLAY_COUNT, new_count)
                elif rb_count > new_count:
                    updated=True
                    gDict = {'id': gTrack['id'],
                             'playCount': new_count}
                    
                # Rating
                new_rating = max(rb_rating, google_rating)
                if new_rating > rb_rating:
                    updated=True
                    self.db.entry_set(entry, RB.RhythmDBPropType.RATING, new_rating)
                elif rb_rating > new_rating:
                    updated=True
                    if gDict == None:
                        gDict = {'id': gTrack['id']}
                    gDict['rating'] = new_rating
                
                # Last Played
                new_last_played = max(rb_last_played, google_last_played)
                if new_last_played > rb_last_played:
                    updated=True
                    self.db.entry_set(entry, RB.RhythmDBPropType.LAST_PLAYED, new_last_played)
                elif rb_last_played > new_last_played:
                    updated=True
                    if gDict == None:
                        gDict = {'id': gTrack['id']}
                    gDict['lastPlayed'] = new_last_played * 1000000


                if gDict != None:
                    google_updates.append(gDict)


                if updated:
                    self.liststore.append([rbTrack['title'],
                                           new_count,
                                           new_rating])

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


        if len(google_updates) > 0:
            print "GoogleSyncPlugin - sending these changes to Google: %s" % (entries_str)
            entries_str = json.dumps({'entries': google_updates})
            req = urllib2.Request(url='https://play.google.com/music/services/modifyentries',
                           data=urllib.urlencode({'u':0,'xt':self.xt, 'json': entries_str}),  
                           headers={'Authorization': "GoogleLogin auth=%s" % self.auth_token})
            f = urllib2.urlopen(req)






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
