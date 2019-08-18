CANTOOLS_ROOT = /tmp/cantools

CPPFLAGS = \
	$(shell pkg-config --cflags babeltrace2) \
	-I/usr/include/c++/7/ -I/usr/include/x86_64-linux-gnu/c++/7/ \
	-I$(CANTOOLS_ROOT)/include

CFLAGS = -g3 -O0 -Werror -Wall -fPIC
LDFLAGS = \
	  -L$(CANTOOLS_ROOT)/lib \
	  -lcandbc
CC = g++

.PHONY: all
all: test babeltrace-plugin-can.so

test: test.o
	gcc -o test test.o -L/tmp/cantools/lib -lcandbc -lm

test.o: test.c
	gcc -o test.o -c test.c -g3 -O0 -I /tmp/cantools/include


babeltrace-plugin-can.so: can.o
	$(CC) -o $@ $^ -shared $(LDFLAGS)

can.o: can.cpp
	$(CC) -c $< $(CPPFLAGS) $(CFLAGS)

.PHONY: clean
clean:
	rm -f babeltrace-plugin-can.so can.o
