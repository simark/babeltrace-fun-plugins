# Plot Plugin

This babeltrace source plugin creates X-Y plots.

## Python Dependencies

* `matplotlib` for creating the plots
* `bintrees` for interpolating values

## Usage

In order to use this plugin, you need to configure datasets and the plot.

### Event Field vs. Time Dataset Configuration

If you wish to plot simple event field values against their timestamps, you
may define your dataset using the following format:

```bash
DATA=["timed", "NAME", "EVENT", "FIELD"]
```

where `NAME` is the name that will be used in the legend and `EVENT`/`FIELD`
are the event and the field respectively that are going to be used for the
dataset.

### Event Field vs. Event Field Dataset Configuration

If you wish to plot two different event field values against each other, you
may define you dataset using the following format:

```bash
DATA=["interpolated", "NAME", "EVENT1", "FIELD1", "EVENT2", "FIELD2"]
```

where `NAME` is the name that will be used in the legend and `EVENT1`/`FIELD1`
are the event/field for the X axis, and `EVENT2`/`FIELD2` are the event/field 
for the Y axis

In order to plot two different lists of values against each other, each value
from a list must match one from the other list (same timestamp). _Since the two
different fields may come from different events, missing values at a timestamp
are interpolated linearly_.

### Plot Configuration

A plot is then configured using the following format:

```bash
PLOT=["TITLE", "X-AXIS", "Y-AXIS", ["$DATA1", ..., "$DATAn"]]
```

where `TITLE` is the top title of the plot, `X/Y-AXIS` are the name of the
X and Y axes, and `$DATA1`, `...`, `$DATAn` are a list of dataset to plot.


### Executing the Plugin

The plugin allow multiple plots to be generated in a single run using the
following format:

```bash
babeltrace2 --component sink.plot.PlotSink \
            --params="plots=[$PLOT1, ..., $PLOTn]" \
           ...
```

_Some double quotes have been omitted for clarity, please check `example/run.sh`
for a working example_.

## TODO

* move list-based arguments into a dictionnary-based arguments
* use default names/titles when not specified
* allow custom X and Y scaling factor
* allow optional legend

