#define _POSIX_C_SOURCE 200809L
#include <gst/gst.h>
#include <gst/video/video.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <signal.h>
static volatile sig_atomic_t running=1;
static uint64_t seq=0, outseq=0, stamps[4096];
static FILE *stats;
static uint64_t us(void){struct timespec t;clock_gettime(CLOCK_REALTIME,&t);return (uint64_t)t.tv_sec*1000000+t.tv_nsec/1000;}
static uint16_t crc16(const uint8_t *b,int len){uint16_t crc=0xffff;for(int i=0;i<len;i++){crc^=(uint16_t)b[i]<<8;for(int j=0;j<8;j++)crc=(crc&0x8000)?(crc<<1)^0x1021:crc<<1;}return crc;}
static void stop(int sig){(void)sig;running=0;}
static GstPadProbeReturn stamp(GstPad *pad,GstPadProbeInfo *pi,gpointer unused){
 (void)unused; GstBuffer *buf=gst_buffer_make_writable(GST_PAD_PROBE_INFO_BUFFER(pi));GST_PAD_PROBE_INFO_DATA(pi)=buf;
 GstCaps *caps=gst_pad_get_current_caps(pad);GstVideoInfo vi;gst_video_info_from_caps(&vi,caps);gst_caps_unref(caps);
 GstVideoFrame f;if(!gst_video_frame_map(&f,&vi,buf,GST_MAP_WRITE))return GST_PAD_PROBE_DROP;
 uint64_t now=us();uint8_t b[13]={0xa5};for(int i=0;i<8;i++)b[1+i]=(now>>(56-8*i))&255;
 b[9]=(seq>>8)&255;b[10]=seq&255;uint16_t crc=crc16(b,11);b[11]=crc>>8;b[12]=crc&255;
 int bw=GST_VIDEO_FRAME_WIDTH(&f)/128, bh=16*GST_VIDEO_FRAME_WIDTH(&f)/640;
 int nv12=GST_VIDEO_FRAME_FORMAT(&f)==GST_VIDEO_FORMAT_NV12;
 for(int plane=0;plane<(nv12?2:3);plane++){
  uint8_t *data=GST_VIDEO_FRAME_PLANE_DATA(&f,plane);int stride=GST_VIDEO_FRAME_PLANE_STRIDE(&f,plane);
  for(int y=0;y<(plane?bh/2:bh);y++){
   if(plane)memset(data+y*stride,128,nv12?104*bw:104*bw/2);
   else for(int bit=0;bit<104;bit++)memset(data+y*stride+bit*bw,(b[bit/8]&(1<<(7-bit%8)))?235:16,bw);
  }
 }
 gst_video_frame_unmap(&f);stamps[seq%4096]=now;seq++;return GST_PAD_PROBE_OK;
}
static GstPadProbeReturn encoded(GstPad *pad,GstPadProbeInfo *pi,gpointer unused){
 (void)pad;(void)pi;(void)unused;uint64_t now=us();fprintf(stats,"%llu,%llu,%llu\n",(unsigned long long)outseq,(unsigned long long)stamps[outseq%4096],(unsigned long long)now);outseq++;return GST_PAD_PROBE_OK;
}
int main(int argc,char **argv){
 if(argc!=3){fprintf(stderr,"usage: stamped_sender PIPELINE ENCODE_CSV\n");return 2;}
 gst_init(&argc,&argv);stats=fopen(argv[2],"w");if(!stats)return 2;
 fprintf(stats,"sequence,stamp_us,encoded_us\n");GError *error=NULL;GstElement *p=gst_parse_launch(argv[1],&error);
 if(error){fprintf(stderr,"%s\n",error->message);return 3;}
 GstElement *enc=gst_bin_get_by_name(GST_BIN(p),"enc");GstPad *sink=gst_element_get_static_pad(enc,"sink"),*src=gst_element_get_static_pad(enc,"src");
 gst_pad_add_probe(sink,GST_PAD_PROBE_TYPE_BUFFER,stamp,NULL,NULL);gst_pad_add_probe(src,GST_PAD_PROBE_TYPE_BUFFER,encoded,NULL,NULL);
 signal(SIGINT,stop);signal(SIGTERM,stop);gst_element_set_state(p,GST_STATE_PLAYING);GstBus *bus=gst_element_get_bus(p);
 while(running){
  GstMessage *m=gst_bus_timed_pop_filtered(bus,100*GST_MSECOND,GST_MESSAGE_ERROR|GST_MESSAGE_EOS|GST_MESSAGE_LATENCY);
  if(!m)continue;
  if(GST_MESSAGE_TYPE(m)==GST_MESSAGE_LATENCY){gst_bin_recalculate_latency(GST_BIN(p));gst_message_unref(m);continue;}
  if(GST_MESSAGE_TYPE(m)==GST_MESSAGE_ERROR){gchar *debug;gst_message_parse_error(m,&error,&debug);fprintf(stderr,"%s %s\n",error->message,debug);running=0;}
  gst_message_unref(m);break;
 }
 gst_element_set_state(p,GST_STATE_NULL);fclose(stats);gst_object_unref(bus);gst_object_unref(sink);gst_object_unref(src);gst_object_unref(enc);gst_object_unref(p);return error?1:0;
}
