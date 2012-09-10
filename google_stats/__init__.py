from gi.repository import GObject, RB, Peas, Gtk, Gdk, PeasGtk
import rb
import json
import urllib2
import urllib
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
       
        query_model = shell.props.library_source.props.query_model

        self.cancel = False

        builder = Gtk.Builder()
        builder.add_from_file(rb.find_plugin_file(self, 'progress.ui'))
        label = builder.get_object('label')
        progressbar = builder.get_object('progressbar')
        button =  builder.get_object('button')
        textview = builder.get_object('textview')
        textbuffer = textview.get_buffer()
        dialog = builder.get_object('dialog')
        button.connect('clicked', self.button_callback, dialog)
        dialog.connect('response', self.dialog_callback)

        dialog.show_all()


        while Gtk.events_pending():
             Gtk.main_iteration()


        if self.cancel:
            return

        
        try:
            req = urllib2.Request(url='https://www.google.com/accounts/ClientLogin',
                    data=urllib.urlencode({'Email': username,
                                           'Passwd': password,
                                           'source': 'music', 'service': 'sj',
                                           'accountType': 'GOOGLE'}))
            f = urllib2.urlopen(req)
        
        # catch bad username/password here
        except urllib2.HTTPError, e:
            label.set_text("Error: %s" % (str(e)))
            return


        auth_token=""

        for line in (f.readlines()):
            if line.find('Auth=') > -1:
                auth_token=line[5:]
                break

        req = urllib2.Request(url='https://www.googleapis.com/sj/v1beta1/tracks',
                      headers={'Authorization': "GoogleLogin auth=%s" % auth_token})
        
        f = urllib2.urlopen(req)

        data = f.read()

        if self.cancel:
            return

        google_data = json.loads(data)["data"]["items"]
        
        size = len(query_model)

        label.set_text("Updating tracks...")
        progressbar.set_fraction(0.1)

        # Iterate over all entries and update their playCounts and ratings
        # ToDo: this should be done in an idle callback
        #       e.g. Gdk.threads_add_idle(0, self.idle_cb, None)
        #self.index = 0
        #Gdk.threads_add_idle(0, self.idle_cb, [google_data, page.props.query_model])

        threshold = progressbar.get_fraction() + 0.05
        #n_updated=0

        for i in range(size):
            entry = query_model[i][0]
            fs1 = entry.get_uint64(RB.RhythmDBPropType.FILE_SIZE)
            count = entry.get_ulong(RB.RhythmDBPropType.PLAY_COUNT)
            rating = entry.get_double(RB.RhythmDBPropType.RATING)
            title = ""

            # Lookup the entry in the google_data dictionary
            for track in google_data:
                fs2 = int(track["estimatedSize"])
                if fs1 == fs2:
                    title = entry.get_string(RB.RhythmDBPropType.TITLE)
                    google_count = int(track["playCount"])
                    google_rating = int(track["rating"])
                    if google_count > count:
                        print "GoogleSyncPlugin::run - updated count: ", title
                        #n_updated += 1
                        textbuffer.insert(textbuffer.get_end_iter(), "Updated \"%s\"\n" % (title))
                        shell.props.db.entry_set(entry, RB.RhythmDBPropType.PLAY_COUNT, google_count)
                    if google_rating > rating:
                        print "GoogleSyncPlugin::run - updated rating: ", title
                        #n_updated += 1
                        textbuffer.insert(textbuffer.get_end_iter(), "Updated \"%s\"\n" % (title))
                        shell.props.db.entry_set(entry, RB.RhythmDBPropType.RATING, google_rating)
                    google_data.remove(track)
                    break

            # Update the progress in the GUI
            perc = i / float(size)
            if perc > threshold:
                progressbar.set_fraction(perc)
                progressbar.set_text("Updating track (%d/%d)..." % (i+1, size))
                threshold = perc + 0.01
                while Gtk.events_pending():
                    Gtk.main_iteration()

            if self.cancel:
                return

        progressbar.set_fraction(1.0)
        progressbar.set_text("100%")
        label.set_text("Finished")
        button.set_label("Done")




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

    filename = "%s/%s" % (plugin_info.get_data_dir(), "account.dat")
    f = open(filename, 'w')
    f.write("%s\n%s" % (username, password))
    f.close()

    os.chmod(filename, (stat.S_IREAD | stat.S_IWRITE))
