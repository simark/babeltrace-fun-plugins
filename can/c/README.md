Building this plugin requires the [cantools](https://github.com/aheit/cantools)
library.  I was able to build and use it in a shared object with:

    autoreconf -vif
    ./configure --disable-matlab --prefix=/tmp/cantools CFLAGS="-fPIC"
    make && make install

See README.md one level above for usage instructions.
