// UART-SHTP: retain partial frames between calls, never wait for absent bytes.
static uint8_t uartFrame[2048];
static unsigned uartSize;
static bool uartStarted, uartEscaped, uartOverflow;
static unsigned uartBytes, uartPackets, uartBad;
void bno_uart_dump() {
  Serial.printf("UART rx_bytes=%u frames=%u bad_frames=%u\n", uartBytes, uartPackets, uartBad);
}
static int uarthal_open(sh2_Hal_t *) {
  // UART was armed before hardware reset; preserve the boot advertisement.
  uartSize=0; uartStarted=uartEscaped=uartOverflow=false;
  uartBytes=uartPackets=uartBad=0;
  return 0;
}
static void uarthal_close(sh2_Hal_t *) { uart_dev->end(); }
static int uarthal_read(sh2_Hal_t *, uint8_t *out, unsigned capacity, uint32_t *stamp) {
  for (unsigned budget=0; budget<4096 && uart_dev->available(); ++budget) {
    uint8_t c=uart_dev->read(); ++uartBytes;
    if (c==0x7e) {
      const bool valid=uartStarted && !uartOverflow && !uartEscaped && uartSize>=5 && uartFrame[0]==1;
      unsigned size=uartSize ? uartSize-1 : 0;
      if (valid && size<=capacity && (((uartFrame[1] | (unsigned(uartFrame[2])<<8)) & 0x7fff)==size)) {
        memcpy(out,uartFrame+1,size); *stamp=micros(); ++uartPackets;
        uartSize=0; uartStarted=true; uartEscaped=uartOverflow=false;
        return size;
      }
      if (uartSize) ++uartBad;
      uartSize=0; uartStarted=true; uartEscaped=uartOverflow=false;
      continue;
    }
    if (!uartStarted || uartOverflow) continue;
    if (uartEscaped) { c^=0x20; uartEscaped=false; }
    else if (c==0x7d) { uartEscaped=true; continue; }
    if (uartSize<sizeof(uartFrame)) uartFrame[uartSize++]=c;
    else uartOverflow=true;
  }
  return 0;
}
static void uart_send_byte(uint8_t c) {
  uart_dev->write(c); uart_dev->flush(); delayMicroseconds(110);
}
static int uarthal_write(sh2_Hal_t *, uint8_t *data, unsigned size) {
  uart_send_byte(0x7e); uart_send_byte(1);
  for(unsigned i=0;i<size;++i) {
    uint8_t c=data[i];
    if(c==0x7e || c==0x7d) { uart_send_byte(0x7d); c^=0x20; }
    uart_send_byte(c);
  }
  uart_send_byte(0x7e);
  return size;
}
