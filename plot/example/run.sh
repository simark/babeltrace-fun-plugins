#!/bin/bash

# run the script from its directory
cd $(dirname $0)

# example code
BABELTRACE2="${BABELTRACE2:-babeltrace2}"

DATA1="[\"timed\", \"Data 1\", \"math:cos\", \"value\"]"
DATA2="[\"timed\", \"Data 2\", \"math:sin\", \"value\"]"
DATA3="[\"interpolated\", \"Curve 1\", \"math:cos\", \"value\", \"math:sin\", \"value\"]"
DATA4="[\"interpolated\", \"Curve 1\", \"math:sin\", \"value\", \"math:cos\", \"value\"]"

PLOT1="[\"Data 1\", \"t\", \"y\", [$DATA1]]"
PLOT2="[\"Data 2\", \"t\", \"y\", [$DATA2]]"
PLOT3="[\"Both 1\", \"t\", \"y\", [$DATA1, $DATA2]]"
PLOT4="[\"Curve 1\", \"x\", \"y\", [$DATA3]]"
PLOT5="[\"Curve 2\", \"x\", \"y\", [$DATA4]]"
PLOT6="[\"Both 2\", \"x\", \"y\", [$DATA3, $DATA4]]"

"$BABELTRACE2" --plugin-path=.. --component sink.plot.PlotSink 		\
	--params="plots=[$PLOT1,$PLOT2,$PLOT3,$PLOT4,$PLOT5,$PLOT6]"	\
	"$(pwd)/data"

