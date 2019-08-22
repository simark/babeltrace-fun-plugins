import bt2

bt2.register_plugin(__name__, "demo")


class MyFirstSourceIter(bt2._UserMessageIterator):
    def __init__(self, output_port):
        ec = output_port.user_data
        sc = ec.stream_class
        tc = sc.trace_class

        trace = tc()
        stream = trace.create_stream(sc)

        # Here, we create all the messages from the start because we just have
        # a few, but a "real" source iterator generating a lot of data would
        # create them in __next__ as it reads the trace.
        self._msgs = [
            self._create_stream_beginning_message(stream),
            self._create_event_message(ec, stream, default_clock_snapshot=123),
            self._create_stream_end_message(stream),
        ]

    def __next__(self):
        if len(self._msgs) > 0:
            return self._msgs.pop(0)
        else:
            raise StopIteration


@bt2.plugin_component_class
class MyFirstSource(bt2._UserSourceComponent, message_iterator_class=MyFirstSourceIter):
    def __init__(self, params, obj):
        tc = self._create_trace_class()
        cc = self._create_clock_class()
        sc = tc.create_stream_class(default_clock_class=cc)
        ec = sc.create_event_class(name="my-event")

        self._add_output_port("some-name", ec)


@bt2.plugin_component_class
class MyFirstSink(bt2._UserSinkComponent):
    def __init__(self, params, obj):
        self._port = self._add_input_port("some-name")

    def _user_graph_is_configured(self):
        self._it = self._create_input_port_message_iterator(self._port)

    def _user_consume(self):
        # Consume one message and print it.
        msg = next(self._it)

        if type(msg) is bt2._StreamBeginningMessage:
            print("Stream beginning")
        elif type(msg) is bt2._EventMessage:
            ts = msg.default_clock_snapshot.value
            name = msg.event.name
            print("event {}, timestamp {}".format(name, ts))
        elif type(msg) is bt2._StreamEndMessage:
            print("Stream end")
        else:
            raise RuntimeError("Unhandled message type", type(msg))
