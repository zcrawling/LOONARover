"""Generate a diagnostic BNO driver with bounded waits and no timeout resets."""
from pathlib import Path
Import('env')

PREAMBLE = r'''
#include "test_compat.h"
#ifdef BNO_TEENSY_UART
void bno_uart_dump();
#endif
struct BnoTrace {
  unsigned reads, writes, int_timeouts, resets, zero_headers, oversized;
  int open_status, product_status;
  uint8_t headers[8][4];
  uint8_t tx[8];
  unsigned tx_size;
};
static BnoTrace trace;
#ifdef BNO_MKR_SOFT_SPI
static BnoSoftSPI soft_spi;
static BnoSoftSPI *diag_spi = &soft_spi;
#else
static SPIClass *diag_spi;
#endif
static uint8_t diag_cs_pin, diag_int_pin;
static volatile uint32_t falling_edges, rising_edges, first_fall_us;
static uint32_t reset_release_us;
#ifndef BNO_MKR_SOFT_SPI
static void diag_int_change() {
  if (digitalRead(diag_int_pin)) ++rising_edges;
  else { if (!falling_edges) first_fall_us = micros(); ++falling_edges; }
}

#endif
void bno_diag_dump() {
#ifndef BNO_MKR_SOFT_SPI
  noInterrupts();
  const uint32_t falls=falling_edges, rises=rising_edges, first=first_fall_us;
  interrupts();
#endif
#if defined(BNO_TEENSY_UART)
  bno_uart_dump();
#elif defined(BNO_MKR_SOFT_SPI)
  Serial.println("INT edge trace=N/A; INT2 is level-polled");
#else
  testPrintf("INT edges falling=%lu rising=%lu first_fall_after_release_us=%ld\n",
                (unsigned long)falls,(unsigned long)rises,
                falls ? (long)(int32_t)(first-reset_release_us) : -1L);
#endif
  testPrintf("DIAG sh2_open=%d product_id=%d (-999=not reached) resets=%u int_timeouts=%u\n",
                trace.open_status, trace.product_status, trace.resets, trace.int_timeouts);
#ifndef BNO_TEENSY_UART
  testPrintf("DIAG SPI reads=%u writes=%u zero_headers=%u oversized=%u\n",
                trace.reads, trace.writes, trace.zero_headers, trace.oversized);
  for (unsigned i=0; i<trace.reads && i<8; ++i) {
    const uint8_t *p=trace.headers[i];
    testPrintf("RX HEADER[%u] %02X %02X %02X %02X length=%u channel=%u seq=%u\n",
                  i,p[0],p[1],p[2],p[3],(p[0] | (p[1]<<8)) & 0x7fff,p[2],p[3]);
  }
  Serial.print("LAST TX prefix:");
  for (unsigned i=0;i<trace.tx_size;++i) testPrintf(" %02X",trace.tx[i]);
  Serial.println();
#endif
}
'''

def instrument(build_env, node):
    original=Path(node.srcnode().get_abspath())
    text=original.read_text()
    def replace(old,new):
        nonlocal text
        if old in ('  // Determine amount to read\n', '  if (packet_size > len) {'):
            cut = text.index('static int spihal_open(sh2_Hal_t *self) {')
            prefix, body = text[:cut], text[cut:]
            if body.count(old) != 1:
                raise RuntimeError('Pinned SPI driver changed: ' + old)
            text = prefix + body.replace(old, new)
            return
        if text.count(old)!=1:
            raise RuntimeError('Pinned BNO driver changed: '+old[:70])
        text=text.replace(old,new)
    replace('#include "Adafruit_BNO08x.h"', '#include "Adafruit_BNO08x.h"\n'+PREAMBLE)
    replace('  i2c_dev = NULL;\n\n  _int_pin = int_pin;',
            '  trace = {}; trace.open_status = trace.product_status = -999;\n  i2c_dev = NULL;\n\n  _int_pin = int_pin;')
    replace('  status = sh2_open(&_HAL, hal_callback, NULL);',
            '  status = sh2_open(&_HAL, hal_callback, NULL);\n  trace.open_status = status;')
    replace('  status = sh2_getProdIds(&prodIds);',
            '  status = sh2_getProdIds(&prodIds);\n  trace.product_status = status;')
    if build_env.subst('$PIOENV') == 'teensy41_uart':
        begin_uart = text.index('static int uarthal_open(sh2_Hal_t *self) {')
        end_uart = text.index('static int spihal_open(sh2_Hal_t *self) {', begin_uart)
        text = text[:begin_uart] + (Path(build_env.subst('$PROJECT_DIR'))/'uart_transport.inc').read_text() + '\n' + text[end_uart:]
        replace('  uart_dev = serial;', '  trace = {}; trace.open_status = trace.product_status = -999;\n  uart_dev = serial;')
    # Replace only the SPI HAL definitions; keep upstream I2C/UART untouched.
    begin = text.index('static int spihal_open(sh2_Hal_t *self) {')
    end = text.index('/**************************************** HAL interface', begin)
    text = text[:begin] + (Path(build_env.subst('$PROJECT_DIR'))/'spi_transport.inc').read_text() + '\n' + text[end:]
    replace('static bool spihal_wait_for_int(void);', '')
    reset_begin = text.index('static void hal_hardwareReset(void) {')
    reset_end = text.index('static uint32_t hal_getTimeUs(', reset_begin)
    text = text[:reset_begin] + r"""static void hal_hardwareReset(void) {
  ++trace.resets;
  if (_reset_pin != -1) {
#ifdef BNO_TEENSY_UART
    uart_dev->begin(3000000);
#endif
    pinMode(_reset_pin, OUTPUT);
    digitalWrite(_reset_pin, LOW);
    delay(100);
#ifdef BNO_TEENSY_UART
    while (uart_dev->available()) uart_dev->read();
#else
    pinMode(diag_int_pin, INPUT_PULLUP);
    pinMode(diag_cs_pin, OUTPUT);
    digitalWrite(diag_cs_pin, HIGH);
#endif
    noInterrupts();
    falling_edges = rising_edges = first_fall_us = 0;
    reset_release_us = micros();
    digitalWrite(_reset_pin, HIGH);
    interrupts();
    // Requested boot settling experiment; IRQ trace stays active during wait.
    delay(200);
  }
}

""" + text[reset_end:]
    if build_env.subst('$PIOENV') == 'mkrzero':
        start = text.index('  spi_dev = new Adafruit_SPIDevice(cs_pin,')
        stop = text.index('  _HAL.open = spihal_open;', start)
        text = text[:start] + '  soft_spi.begin();\n' + text[stop:]
    replace('  _int_pin = int_pin;',
            '#ifndef BNO_MKR_SOFT_SPI\n  diag_spi = theSPI;\n#endif\n  diag_cs_pin = cs_pin; diag_int_pin = int_pin;\n  _int_pin = int_pin;')
    replace('  pinMode(_int_pin, INPUT_PULLUP);',
            '  pinMode(_int_pin, INPUT_PULLUP);\n#ifndef BNO_MKR_SOFT_SPI\n  attachInterrupt(digitalPinToInterrupt(_int_pin), diag_int_change, CHANGE);\n#endif')
    replace('  uint32_t t = millis() * 1000;', '  uint32_t t = micros();')
    # Late/report-setup callbacks must never decode through a null pointer.
    replace('  rc = sh2_decodeSensorEvent(_sensor_value, event);',
            '  if (!_sensor_value) return;\n  rc = sh2_decodeSensorEvent(_sensor_value, event);')
    destination=Path(build_env.subst('$BUILD_DIR'))/'bno-diagnostic'/'Adafruit_BNO08x.cpp'
    destination.parent.mkdir(parents=True,exist_ok=True)
    if not destination.exists() or destination.read_text()!=text:destination.write_text(text)
    build_env.AppendUnique(CPPPATH=[str(original.parent)])
    return build_env.File(str(destination.resolve()))

env.AppendUnique(CPPPATH=[env.subst('$PROJECT_DIR')])

env.AddBuildMiddleware(instrument, '*Adafruit_BNO08x.cpp')

def instrument_sh2(build_env, node):
    original = Path(node.srcnode().get_abspath())
    text = original.read_text()
    old = "    // No errors.\n    return SH2_OK;\n}"
    new = "    return pSh2->resetComplete && pSh2->controlChan != 0xFF ? SH2_OK : SH2_ERR_TIMEOUT;\n}"
    if text.count(old) != 1:
        raise RuntimeError('Pinned SH2 open changed')
    text = text.replace(old, new)
    for old, new in [('#define ADVERT_TIMEOUT_US (200000)', '#define ADVERT_TIMEOUT_US (2000000)'),
                     ('(!pSh2->resetComplete))', '(!pSh2->resetComplete || pSh2->controlChan == 0xFF))')]:
        if text.count(old) != 1: raise RuntimeError('Pinned SH2 startup changed: ' + old)
        text = text.replace(old, new)
    destination = Path(build_env.subst('$BUILD_DIR'))/'bno-diagnostic'/'sh2.c'
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists() or destination.read_text() != text: destination.write_text(text)
    build_env.AppendUnique(CPPPATH=[str(original.parent)])
    return build_env.File(str(destination.resolve()))

env.AddBuildMiddleware(instrument_sh2, '*Adafruit BNO08x/src/sh2.c')
