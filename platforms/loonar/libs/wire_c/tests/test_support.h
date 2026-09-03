#ifndef LOONAR_WIRE_TEST_SUPPORT_H
#define LOONAR_WIRE_TEST_SUPPORT_H

#include <stdio.h>

#define TEST_CHECK(expression)                                                    \
  do {                                                                            \
    if (!(expression)) {                                                           \
      fprintf(stderr, "%s:%d: check failed: %s\n", __FILE__, __LINE__, #expression); \
      return 1;                                                                    \
    }                                                                              \
  } while (0)

#endif

