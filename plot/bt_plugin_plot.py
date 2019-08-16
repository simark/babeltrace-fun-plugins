import bt2
import bintrees
import itertools
import matplotlib.pyplot as plt

class DataLogger(object):
    def __init__(self, name="Untitled"):
            self._name = name

    def get_name(self):
        return self._name

    def get_x_data(self):
        raise NotImplementedError

    def get_y_data(self):
        raise NotImplementedError

    def received_event(self, ts, event):
        raise NotImplementedError

class TimedDataLogger(DataLogger):
    """
        This class allow a simple set of data of the form (ts, value) to be
        plotted.
    """
    def __init__(self, data, *args, **kwargs):
        super(TimedDataLogger, self).__init__(*args, **kwargs)

        (self._event, self._field) = data

        self._timestamps = []
        self._values = []

    def get_x_data(self):
        return self._timestamps

    def get_y_data(self):
        return self._values

    def received_event(self, ts, event):
        if event.name == self._event and self._field in event.payload_field:
            value = event.payload_field[self._field]
            self._add_data_point(ts, value)

    def _add_data_point(self, ts, value):
        self._timestamps.append(ts)
        self._values.append(value)

class InterpolatedDataLogger(DataLogger):
    """
        This class allow two set of data of the form (t1, v1) and (t2, v2) to
        be plot against each other like v1 versus v2 (e.g. when plotting
        an hysteresis curve or implicit function).

        Missing points from one set of data are linearly interpolated and data
        added to this plot is assumed to be in order, that is if we have the
        following data: 

            { (tX_0, vX_0), (tX_1, vX_1), ..., (tX_N, vX_N) },

        then we also must have:

            tX_0 < tX_1 < ... < tX_N.
    """
    def __init__(self, data1, data2, *args, **kwargs):
        super(InterpolatedDataLogger, self).__init__(*args, **kwargs)

        (self._event1, self._field1) = data1
        (self._event2, self._field2) = data2

        self._x_timestamps = []
        self._x_values = []
        self._x_needs_interpolation = dict()
        self._x_received_values = bintrees.AVLTree()

        self._y_timestamps = []
        self._y_values = []
        self._y_needs_interpolation = dict()
        self._y_received_values = bintrees.AVLTree()

    def get_x_data(self):
        self._interpolate_x_data()
        return self._x_values

    def get_y_data(self):
        self._interpolate_y_data()
        return self._y_values

    def received_event(self, ts, event):
        if event.name == self._event1 and self._field1 in event.payload_field:
            value = event.payload_field[self._field1]
            self._add_x_data_point(ts, value)

        if event.name == self._event2 and self._field2 in event.payload_field:
            value = event.payload_field[self._field2]
            self._add_y_data_point(ts, value)

    def _interpolate(self, ts, received_values):
        try:
            (after_ts, after_value) = received_values.ceiling_item(ts)
        except KeyError:
            (before_ts, before_value) = received_values.floor_item(ts)
            return before_value
        
        try:
            (before_ts, before_value) = received_values.floor_item(ts)
        except KeyError:
            return after_value

        if before_ts == after_ts:
            return before_value

        a = (ts - before_ts)
        x = (after_value - before_value)/(after_ts - before_ts)
        b = before_value

        return a*x + b

    def _interpolate_x(self, ts):
        return self._interpolate(ts, self._x_received_values)

    def _interpolate_y(self, ts):
        return self._interpolate(ts, self._y_received_values)

    def _interpolate_x_data(self):
        for (index, interpolated_ts) in self._x_needs_interpolation.items():
            interpolated_value = self._interpolate_x(interpolated_ts)
            self._x_timestamps[index] = interpolated_ts
            self._x_values[index]     = interpolated_value
        self._x_needs_interpolation.clear()

    def _interpolate_y_data(self):
        for (index, interpolated_ts) in self._y_needs_interpolation.items():
            interpolated_value = self._interpolate_y(interpolated_ts)
            self._y_timestamps[index] = interpolated_ts
            self._y_values[index]     = interpolated_value
        self._y_needs_interpolation.clear()

    def _add_x_data_point(self, ts, value):
        self._x_timestamps.append(ts)
        self._x_values.append(value)
        self._x_received_values[ts] = value

        self._interpolate_x_data()

        self._y_timestamps.append(None)
        self._y_values.append(None)
        self._y_needs_interpolation[len(self._y_timestamps)-1] = ts

    def _add_y_data_point(self, ts, value):
        self._y_timestamps.append(ts)
        self._y_values.append(value)
        self._y_received_values[ts] = value

        self._interpolate_y_data()

        self._x_timestamps.append(None)
        self._x_values.append(None)
        self._x_needs_interpolation[len(self._y_timestamps)-1] = ts

class Plot(object):
    def __init__(self, loggers, title="Untitled", x_label="Untitled", y_label="Untitled"):
        self._loggers = loggers
        self._title = title
        self._x_label = x_label
        self._y_label = y_label

    def received_event(self, ts, event):
        for logger in self._loggers:
            logger.received_event(ts, event)

    def plot(self):
        figure = plt.figure()
        plt.title(self._title)
        plt.xlabel(self._x_label, figure=figure)
        plt.ylabel(self._y_label, figure=figure)

        for logger in self._loggers:
            x = logger.get_x_data()
            y = logger.get_y_data()
            line, = plt.plot(x, y, figure=figure)
            line.set_label(logger.get_name())

        figure.gca().legend()
        plt.savefig(Plot._format_filename(self._title))

    @staticmethod
    def _format_filename(title):
        title = title.lower()
        title = "".join("-" if not c.isalnum() else c for c in title)
        title = "".join(["".join(j) if i != '-' else i for (i, j) in itertools.groupby(title)])
        return f"{title}.pdf"

@bt2.plugin_component_class
class PlotSink(bt2._UserSinkComponent):
    def __init__(self, params, obj):
        self._plots = []

        for plot in params["plots"]:
            self._plots.append(PlotSink.create_plot(plot))

        self._add_input_port("in")

    def _user_consume(self):
        msg = next(self._iter)
        if isinstance(msg, bt2._PacketBeginningMessage):
            return
        if isinstance(msg, bt2._PacketEndMessage):
            return
        if isinstance(msg, bt2._StreamBeginningMessage):
            return
        if isinstance(msg, bt2._StreamEndMessage):
            { plot.plot() for plot in self._plots }
            return

        ts = msg.default_clock_snapshot.value
        for plot in self._plots:
            plot.received_event(ts, msg.event)

    def _user_graph_is_configured(self):
        self._iter = self._create_input_port_message_iterator(self._input_ports["in"])

    @staticmethod
    def create_plot(params):
        loggers = []
        for logger in params[3]:
            if logger[0] == 'timed':
                logger = PlotSink.create_timed_logger(logger)
            elif logger[0] == 'interpolated':
                logger = PlotSink.create_interpolated_logger(logger)
            else:
                raise ValueError

            loggers.append(logger)

        title = str(params[0])
        x_label = str(params[1])
        y_label = str(params[2])

        return Plot(
            loggers,
            title=title,
            x_label=x_label,
            y_label=y_label
        )

    @staticmethod
    def create_timed_logger(params):
        return TimedDataLogger(
            (str(params[2]), str(params[3])),
            name=str(params[1])
        )

    @staticmethod
    def create_interpolated_logger(params):
        return InterpolatedDataLogger(
            (str(params[2]), str(params[3])),
            (str(params[4]), str(params[5])),
            name=str(params[1])
        )

bt2.register_plugin(
    module_name=__name__,
    name="plot",
    description="Plot Sink",
    author="Gabriel-Andrew Pollo-Guilbert",
    license="GPL",
    version=(1, 0, 0),
)
