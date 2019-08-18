#include <dbcmodel.h>
#include <dbcreader.h>
#include <stdio.h>

int main() {
    dbc_t *dbc = dbc_read_file("../can/database.dbc");
    printf("%p\n", dbc);
    return 0;
}