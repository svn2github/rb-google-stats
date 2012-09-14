#!/usr/bin/env sh
#

RHYTHMBOX_PLUGIN_DIR="$HOME/.local/share/rhythmbox/plugins/"

if [ ! -d "$RHYTHMBOX_PLUGIN_DIR" ]
then
    mkdir -p "$HOME/.local/share/rhythmbox/plugins/"
fi

cp google_stats.plugin $RHYTHMBOX_PLUGIN_DIR
cp -r google_stats $RHYTHMBOX_PLUGIN_DIR
