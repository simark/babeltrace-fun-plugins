common="-c source.can.CANSource --params inputs=[\"./test.data\"],databases=[\"./database.dbc\"] -c sink.text.details"

echo "Running with Python plugin."
babeltrace2 --plugin-path python $common > python.details
echo "Running with C plugin."
babeltrace2 --plugin-path c $common > c.details

diff -u python.details c.details | head -n 100
