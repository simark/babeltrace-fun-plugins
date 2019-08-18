This directory contains a source that reads tracks from
[gpx](https://en.wikipedia.org/wiki/GPS_Exchange_Format) files as traces.

Note that only gpx files exported from Strava were tested so far.

You can execute the included example with:

    babeltrace2 --plugin-path . -c source.gpx.GpxSource --params 'inputs=["Example.gpx"]'

Or, simpler, using automatic source discovery:

    babeltrace2 --plugin-path . .
