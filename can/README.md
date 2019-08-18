This directory contains two Babeltrace plugins to read a CAN Bus according to a
CAN bus message database (dbc file).  One plugin uses the Python bindings and
the other uses the C bindings (but is actually written in C++).  They are
expected to accept the same parameters and produce the same results (verifiable
by comparing `sink.text.details` output).

Supported parameters are:

 * `inputs`: array of strings, the inputs files.  Only one input is supported
   at the moment.
 * `databases`: array of strings, the database files.

Files `test.data` and `database.dbc` are provided as an example.

* Python: `babeltrace2 --plugin-path ./python -c source.can.CANSource --params 'inputs=["./test.data"],databases=["./database.dbc"]'`
* C: `babeltrace2 --plugin-path ./c -c source.can.CANSource --params 'inputs=["./test.data"],databases=["./database.dbc"]'`

Note that the plugin using the C bindings needs to be compiled first,
instructions are within its directory.
