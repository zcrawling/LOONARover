// Test-only SPI HAL: no sleeping reads, no reset on timeout, one CS per packet.
static int spihal_open(sh2_Hal_t *) { return 0; }
static void spihal_close(sh2_Hal_t *) {}

static int spihal_read(sh2_Hal_t *, uint8_t *buffer, unsigned capacity,
                      uint32_t *timestamp) {
  if (capacity < 4 || digitalRead(diag_int_pin)) return 0;
  *timestamp = micros();
  diag_spi->beginTransaction(SPISettings(1000000, MSBFIRST, SPI_MODE3));
  digitalWrite(diag_cs_pin, LOW);
  delayMicroseconds(1);
  for (unsigned i=0; i<4; ++i) buffer[i] = diag_spi->transfer(0);
  if (trace.reads < 8) memcpy(trace.headers[trace.reads], buffer, 4);
  ++trace.reads;
  const unsigned size = (buffer[0] | (unsigned(buffer[1]) << 8)) & 0x7fff;
  const bool valid = size >= 4 && size <= capacity;
  if (!size) ++trace.zero_headers;
  if (size > capacity) ++trace.oversized;
  if (valid) {
    // CS already acknowledged INT. Do not wait for a second INT mid-packet.
    for (unsigned i=4; i<size; ++i) buffer[i] = diag_spi->transfer(0);
  }
  digitalWrite(diag_cs_pin, HIGH);
  diag_spi->endTransaction();
  return valid ? int(size) : 0;
}

static int spihal_write(sh2_Hal_t *, uint8_t *buffer, unsigned size) {
  // No WAKE GPIO is wired: bound the wait and report the actual failure.
  // Returning 0 forever makes upstream shtp_send retry forever.
  const uint32_t start = micros();
  while (digitalRead(diag_int_pin)) {
    if (uint32_t(micros()-start) >= 100000) {
      ++trace.int_timeouts;
      return SH2_ERR_TIMEOUT;
    }
    delayMicroseconds(20);
  }
  diag_spi->beginTransaction(SPISettings(1000000, MSBFIRST, SPI_MODE3));
  digitalWrite(diag_cs_pin, LOW);
  delayMicroseconds(1);
  ++trace.writes;
  trace.tx_size = size < 8 ? size : 8;
  memcpy(trace.tx, buffer, trace.tx_size);
  for (unsigned i=0; i<size; ++i) diag_spi->transfer(buffer[i]);
  digitalWrite(diag_cs_pin, HIGH);
  diag_spi->endTransaction();
  return int(size);
}
