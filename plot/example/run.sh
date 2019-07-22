#!/bin/bash

DATA1='["math:cos", "value", "Data 1", "x", "y"]'
DATA2='["math:sin", "value", "Data 2", "x", "y"]'
CURVE1='["math:cos", "value", "math:sin", "value", "Curve 1", "x", "y"]'
CURVE2='["math:sin", "value", "math:cos", "value", "Curve 2", "x", "y"]'

babeltrace2 --plugin-path=.. --component sink.plot.PlotSink 	\
	--params="timed=[$DATA1, $DATA2]"			\
	--params="interpolated=[$CURVE1, $CURVE2]" 		\
	"$(pwd)/data"

