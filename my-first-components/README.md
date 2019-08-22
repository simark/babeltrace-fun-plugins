This directory contains very simple source and sink component classes.

`MyFirstSource` produces three messages: one stream beginning message, one
event message and one stream end message.

`MyFirstSink` prints the consumed upstream messages in a very simple way.

You can execute them with:

    babeltrace2 --plugin-path . -c source.demo.MyFirstSource -c sink.demo.MyFirstSink
