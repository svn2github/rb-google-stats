import gStatsUtil
from gi.repository import GObject, RB, Peas, Gtk, PeasGtk, GLib
import rb
import json
import urllib, urllib2
import time
import sqlite3


def comparefunction(treemodel, iter1, iter2, user_data):
    lastPlayed1 = time.mktime(time.strptime(treemodel.get_value(iter1, 3), "%b %d %y %I:%M %p"))
    lastPlayed2 = time.mktime(time.strptime(treemodel.get_value(iter2, 3), "%b %d %y %I:%M %p"))
    
    val = lastPlayed2 - lastPlayed1
    
    if val != 0:
        return val

    return cmp(treemodel.get_value(iter1, 0), treemodel.get_value(iter2, 0))
	

	

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
        # Other things
        self.updating = False
        self.timer_id = None
        self.data_dir = None
        self.google_update_queue = {}



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

        self.data_dir = self.plugin_info.get_data_dir()

        # Get Login info 
        account_file = rb.find_plugin_file(self, 'account.dat')
        if account_file != None:
            f = open(account_file)
            self.username = f.readline()
            self.password = f.readline()

        # Add callback for database entry changes (playCount, lastPlayed, etc)
        self.entry_changed_id = shell.props.db.connect('entry-changed', self.entry_change_cb)

        # Restore and send any pending updates
        save_file = "{0}/save.json".format(self.data_dir)
        import os
        if os.path.isfile(save_file):    
            f = open(save_file, 'r')
            self.google_update_queue = json.load(f)
            f.close()
            os.remove(save_file)
            if len(self.google_update_queue) > 0:
                self.google_update_timer_cb()




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
        
        # Save any pending updates
        if len(self.google_update_queue) > 0:
            save_file = "{0}/save.json".format(self.data_dir)
            f = open(save_file, 'w')
            f.write(json.dumps(self.google_update_queue))
            f.close()

        


    def entry_change_cb(self, db, entry, changes):
        
        if self.username == None or self.password == None or self.updating:
            return

        print "entry_change_cb"

        updated=False
        track = {'id': self.rb_to_google_id(entry)}

        for i in range(changes.n_values):
            change = changes.get_nth(i)
            if change.prop == RB.RhythmDBPropType.PLAY_COUNT: 
                updated=True
                track['playCount'] = change.new
            elif change.prop == RB.RhythmDBPropType.LAST_PLAYED:
                updated=True
                track['lastPlayed'] = change.new * 1000000
            elif change.prop == RB.RhythmDBPropType.RATING:
                track['rating'] = change.new
                updated=True
            #else:
            #    print "GoogleSyncPlugin - entry_change_cb: %s" % (change.prop)

        if updated:
            # Add this track to the queue
            self.google_update_queue[track['id']] = track
            if self.timer_id == None:
                print "CREATED UPDATE TIMER"
                self.timer_id = GObject.timeout_add_seconds(12, self.google_update_timer_cb)



    def google_update_timer_cb(self):
        if len(self.google_update_queue) > 0:
            self.get_auth_tokens()
            entries_str = json.dumps({'entries': self.google_update_queue.values()})
            self.google_update_queue = {} 
            req = urllib2.Request(url='https://play.google.com/music/services/modifyentries',
                    data=urllib.urlencode({'u':0,'xt':self.xt_token, 'json': entries_str}),
                    headers={'Authorization': "GoogleLogin auth={0}".format(self.auth_token)})
            f = urllib2.urlopen(req)
            print "google_update_timer_cb result: {0}".format(f.read())
        
        self.timer_id = None
        return False



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
            gStatsUtil.save_account_info(username, password, self.data_dir)

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
        treeview.append_column(Gtk.TreeViewColumn('Plays', Gtk.CellRendererText(), text=1))
        treeview.append_column(Gtk.TreeViewColumn('Rating', Gtk.CellRendererText(),text=2))
        
        playedColumn = Gtk.TreeViewColumn('Last Played', Gtk.CellRendererText(),text=3)
        
        self.liststore.set_default_sort_func(comparefunction)
        self.liststore.set_sort_column_id(-1, 0)
        

        treeview.append_column(playedColumn)
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
        
        res = gStatsUtil.fetch_google_tracks(self.username, self.password,
                                    self.auth_token, self.xt_token, self.use_cache,
                                    self.dump_cache, self.data_dir)
        self.auth_token = res[0]
        self.xt_token = res[1]

        gStatsUtil.fetch_playlists(self.username, self.password, self.auth_token, self.xt_token, self.data_dir)

        if (self.auth_token != None and self.xt_token != None) or self.use_cache:
            self.update_db(shell)
        else:
            self.label.set_markup('<span color="red">Error: Unable to login to Google</span>')
            
        # cleanup 
        del self.progressbar
        del self.label
        del self.button
        del self.liststore
        del self.db
        del self.query_model


        

    def update_db(self, shell):
        
        self.updating = True

        size = len(self.query_model)
        threshold = self.progressbar.get_fraction() + 0.05

        self.label.set_text("Updating {0} tracks...".format(size))
        self.progressbar.set_fraction(0.10)

        
        db_filename = "{0}/cache.db".format(self.data_dir)
        conn = sqlite3.connect(db_filename)
        c = conn.cursor()

        for i in range(size):
            entry = self.query_model[i][0]
          
            rb_title = entry.get_string(RB.RhythmDBPropType.TITLE)

            # Rhythmbox track
            rbTrack = {'title':  unicode(rb_title,'utf-8'),
                       'artist': unicode(entry.get_string(RB.RhythmDBPropType.ARTIST),'utf-8'),
                       'album':  unicode(entry.get_string(RB.RhythmDBPropType.ALBUM),'utf-8'),
                       'uri':  unicode(entry.get_string(RB.RhythmDBPropType.LOCATION),'utf-8')}
            
            rb_count = entry.get_ulong(RB.RhythmDBPropType.PLAY_COUNT)
            rb_rating = entry.get_double(RB.RhythmDBPropType.RATING)
            rb_last_played = entry.get_ulong(RB.RhythmDBPropType.LAST_PLAYED)
            rb_genre =  unicode(entry.get_string(RB.RhythmDBPropType.GENRE), 'utf-8')

            # Lookup the entry in the db
            c.execute('''SELECT id,rating,lastPlayed,playCount,genre FROM google
                        WHERE title=? AND album=? AND artist=?''',
                        (rbTrack['title'], rbTrack['album'], rbTrack['artist']))

            row = c.fetchone()

            if row:

                google_id = row[0]
                google_rating = row[1]
                google_last_played = row[2] / 1000000
                google_count = row[3]
                google_genre = row[4]


                # Add it to a playlist
                for row in c.execute('SELECT playlist_name FROM playlist_entries WHERE track_id=?', [google_id]):
                    try:
                        shell.props.playlist_manager.create_static_playlist(row[0])
                    except:
                        print "WARN: Unable to create playlist \"{0}\"".format(row[0])
                            
                    try:
                        shell.props.playlist_manager.add_to_playlist(row[0], rbTrack['uri'])
                    except Exception, e:
                        print e
                        
                
                updated=False
                    
                # Play Count
                new_count = max(rb_count, google_count)
                if google_count > rb_count:
                    updated=True
                    print "playCount: %s (%d --> %d)" % (rb_title, rb_count, google_count)
                    if self.test == False:
                        self.db.entry_set(entry, RB.RhythmDBPropType.PLAY_COUNT, new_count)
                 
                # Rating
                new_rating = max(rb_rating, google_rating)
                if google_rating > rb_rating:
                    updated=True
                    print "rating: %s (%d --> %d)" % (rb_title, rb_rating, google_rating)
                    if self.test == False:
                        self.db.entry_set(entry, RB.RhythmDBPropType.RATING, new_rating)
                
                # Last Played
                new_last_played = max(rb_last_played, google_last_played)
                if google_last_played > rb_last_played and google_count > rb_count:
                    updated=True
                    print "lastPlayed: %s (%d --> %d)" % (rb_title, rb_last_played,
                                                          google_last_played)
                    if self.test == False:
                        self.db.entry_set(entry,
                                          RB.RhythmDBPropType.LAST_PLAYED,
                                          new_last_played)

                # Genre
                if rb_genre != google_genre:
                    updated=True
                    print "genre: %s (%s --> %s)" % (rb_title, rb_genre, google_genre)
                    if self.test == False:
                        self.db.entry_set(entry, RB.RhythmDBPropType.GENRE, str(google_genre))



                if updated:
                    lastPlayed_str = time.strftime("%b %d %y %I:%M %p",
                                                  time.localtime(new_last_played))

                    gStatsUtil.log ('INFO',
                        "updated \"{0} - {1}\" ({2}, {3}, {4}) --> ({5}, {6}, {7})".format(
                        rbTrack['artist'], rbTrack['title'], rb_count, rb_rating, rb_last_played,
                        google_count, google_rating, google_last_played))
                    
                    self.liststore.append(
                                    ["{0} - {1}".format(rbTrack['artist'], rbTrack['title']),
                                    new_count,
                                    new_rating,
                                    lastPlayed_str])

            else:
                print "GoogleSyncPlugin - no match for {0}".format(rb_title)

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

        self.updating = False




    def rb_to_google_id(self, entry):
        track_id = None
        db_file = rb.find_plugin_file(self, 'cache.db')
        conn = sqlite3.connect(db_file)
        c = conn.cursor()
        c.execute('SELECT id FROM google WHERE artist=? AND album=? AND title=?',
                        (entry.get_string(RB.RhythmDBPropType.ARTIST).decode('utf-8'),
                        entry.get_string(RB.RhythmDBPropType.ALBUM).decode('utf-8'),
                        entry.get_string(RB.RhythmDBPropType.TITLE).decode('utf-8')))
        row = c.fetchone()
        if row != None:
            track_id = row[0]
        c.close()
        conn.close()
        return track_id



class GoogleSyncConfig(GObject.GObject, PeasGtk.Configurable):
    object = GObject.property(type=GObject.GObject)

    def __init__(self):
        GObject.GObject.__init__(self)

    def do_create_configure_widget(self):
       
        def account_details_changed(entry, event):
            username = builder.get_object('usernameEntry').get_text()
            password = builder.get_object('passwordEntry').get_text()
            gStatsUtil.save_account_info(username, password, self.plugin_info.get_data_dir())
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


