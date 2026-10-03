#include <assert.h>
#include <stdio.h>
#include "sh2.h"
#include "sh2_hal.h"
#include "sh2_err.h"
static unsigned opens,closes,reads;
static unsigned clock_us;
static int op(sh2_Hal_t *h){(void)h;++opens;return 0;}
static void cl(sh2_Hal_t *h){(void)h;++closes;}
static int rd(sh2_Hal_t *h,uint8_t *p,unsigned n,uint32_t *t){(void)h;(void)p;(void)n;(void)t;++reads;return 0;}
static int wr(sh2_Hal_t *h,uint8_t *p,unsigned n){(void)h;(void)p;return n;}
static uint32_t tm(sh2_Hal_t *h){(void)h;clock_us+=100;return clock_us;}
int main(void){
 sh2_Hal_t h={op,cl,rd,wr,tm};
 for(unsigned i=0;i<5;i++) {
  unsigned before=clock_us;
  assert(sh2_open(&h,0,0)==SH2_ERR_TIMEOUT);
  assert(clock_us-before>=2000000 && clock_us-before<2001000);
  sh2_close();
 }
 assert(opens==5 && closes==5 && reads>0);
 puts("PASS: missing boot response returns timeout, bounded 2s, five sessions reclaimed");
}
