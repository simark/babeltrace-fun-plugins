import bt2
import os
import xml.etree.ElementTree as etree
from datetime import datetime


class GpxIter(bt2._UserMessageIterator):
    def __init__(self, port):
        print("GpxIter: Creating for port {}".format(port))
        self._trk_elem, self._trace_class = port.user_data

        self._trace = self._trace_class()

        self._trk_stream_class = self._trace_class[0]
        assert self._trk_stream_class.name == "trk"
        self._trk_stream = self._trace.create_stream(self._trk_stream_class)

        self._trkpt_event_class = self._trk_stream_class[0]
        assert self._trkpt_event_class.name == "trkpt"

        self._init_msgs = [self._create_stream_beginning_message(self._trk_stream)]

        self._end_msgs = [self._create_stream_end_message(self._trk_stream)]

        self._trkpt_iter = self._trk_elem.iter(
            "{http://www.topografix.com/GPX/1/1}trkpt"
        )

        self._next = self._next_init

    def _next_init(self):
        if len(self._init_msgs) > 0:
            return self._init_msgs.pop(0)
        else:
            self._next = self._next_events
            return self._next()

    def _next_events(self):
        try:
            trkpt = next(self._trkpt_iter)

            lat = float(trkpt.attrib["lat"])
            lon = float(trkpt.attrib["lon"])
            ele_elem = trkpt.find("{http://www.topografix.com/GPX/1/1}ele")
            ele = float(ele_elem.text)

            time_elem = trkpt.find("{http://www.topografix.com/GPX/1/1}time")
            time = datetime.strptime(time_elem.text, "%Y-%m-%dT%H:%M:%SZ")
            ts = int(datetime.timestamp(time))

            event_msg = self._create_event_message(
                self._trkpt_event_class, self._trk_stream, default_clock_snapshot=ts
            )
            event_msg.event.payload_field["lat"] = lat
            event_msg.event.payload_field["lon"] = lon
            event_msg.event.payload_field["ele"] = ele
            return event_msg
        except StopIteration:
            self._next = self._next_end
            return self._next()

    def _next_end(self):
        if len(self._end_msgs) > 0:
            return self._end_msgs.pop(0)
        else:
            raise StopIteration

    def __next__(self):
        return self._next()


@bt2.plugin_component_class
class GpxSource(bt2._UserSourceComponent, message_iterator_class=GpxIter):
    def __init__(self, params, obj):
        print("GpxSource: Creating with params {}".format(params))

        if "inputs" not in params:
            raise ValueError("GpxSource: missing `inputs` parameter")

        inputs = params["inputs"]

        if type(inputs) != bt2.ArrayValue:
            raise TypeError(
                "GpxSource: expecting `inputs` parameter to be a list, got a {}".format(
                    type(inputs)
                )
            )

        if len(inputs) != 1:
            raise ValueError(
                "GpxSource: expecting `inputs` parameter to be of length, got {}".format(
                    len(inputs)
                )
            )

        if type(inputs[0]) != bt2.StringValue:
            raise TypeError(
                "GpxSource: expecting `inputs[0]` parameter to be a string, got a {}".format(
                    type(inputs[0])
                )
            )

        trace_class = self._create_metadata()

        self._create_ports_for_file(str(inputs[0]), trace_class)

    def _create_metadata(self):
        clock_class = self._create_clock_class(frequency=1)
        trace_class = self._create_trace_class()

        sc = trace_class.create_stream_class(
            name="trk", default_clock_class=clock_class
        )

        # 'trkpt' event
        trkpt_payload = trace_class.create_structure_field_class()
        trkpt_payload.append_member("lat", trace_class.create_real_field_class())
        trkpt_payload.append_member("lon", trace_class.create_real_field_class())
        trkpt_payload.append_member("ele", trace_class.create_real_field_class())
        sc.create_event_class(name="trkpt", payload_field_class=trkpt_payload)

        print("GpxSource: Created trace class", trace_class)
        print("GpxSource:     with stream class trk", trace_class[0])
        print("GpxSource:     with event class trkpt", trace_class[0][0])

        return trace_class

    def _create_ports_for_file(self, input, trace_class):
        if not os.path.isfile(input):
            raise ValueError("GpxSource: {} is not a file".format(input))

        tree = etree.parse(input)
        assert tree.getroot().tag == "{http://www.topografix.com/GPX/1/1}gpx"

        for trk in tree.findall("{http://www.topografix.com/GPX/1/1}trk"):
            print("GpxSource: Adding output port for track", trk)
            self._add_output_port("out", (trk, trace_class))

    @staticmethod
    def _user_query(query_executor, obj, params, log_level):
        if obj == "babeltrace.support-info":
            if params["type"] == "file" and str(params["input"]).endswith(".gpx"):
                w = 0.25
            else:
                w = 0.0

            return {"weight": w}
        else:
            raise bt2.UnknownObject


bt2.register_plugin(
    module_name=__name__,
    name="gpx",
    description="GPX format",
    author="Simon Marchi",
    license="MIT",
    version=(1, 0, 0),
)
