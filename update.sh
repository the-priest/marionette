#!/bin/sh
# Update MARIONETTE — just re-runs the smart installer, which handles
# force-pushes and divergent branches cleanly.
cd "$(dirname "$0")"
echo "[1/1] re-running install.sh ..."
exec sh ./install.sh
