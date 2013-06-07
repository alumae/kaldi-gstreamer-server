'''
Created on May 17, 2013

@author: tanel
'''
import gi
gi.require_version('Gst', '1.0')
from gi.repository import GObject, Gst

GObject.threads_init()
Gst.init(None)
import thread
import threading
import logging

import pdb
import time

from multiprocessing import Process, Pipe

logger = logging.getLogger(__name__)

class DecoderPipeline(object):
    def __init__(self):
        self.create_pipeline()
        self.outdir = "tmp"
        self.recognizing = False
        self.word_handler = None
        self.eos_handler = None
        
    def create_pipeline(self):
        self.appsrc = Gst.ElementFactory.make("appsrc", "appsrc")
        
        self.filesrc = Gst.ElementFactory.make("filesrc", "filesrc")
        self.filesrc.set_property("location", "tmp/intervjuu201108091200_0332.723-0338.381.wav")
         
        
        #caps = Gst.caps_from_string("audio/x-raw,rate=16000,channels=1,format=(string)S16LE")
        #self.appsrc.set_property("caps", caps)
        
        self.decodebin = Gst.ElementFactory.make("decodebin", "decodebin")
        self.audioconvert = Gst.ElementFactory.make("audioconvert", "audioconvert")
        self.audioresample = Gst.ElementFactory.make("audioresample", "audioresample")    
        self.tee = Gst.ElementFactory.make("tee", "tee")
        self.queue1 = Gst.ElementFactory.make("queue", "queue1")
        self.filesink = Gst.ElementFactory.make("filesink", "filesink")
        self.queue2 = Gst.ElementFactory.make("queue", "queue2")
        self.asr = Gst.ElementFactory.make("onlinegmmfasterdecoder", "asr")
        self.fakesink = Gst.ElementFactory.make("fakesink", "fakesink")

        #self.asr.set_property("fst", "tmp/models/tri2b_mmi/HCLG.fst")
        #self.asr.set_property("model", "tmp/models/tri2b_mmi/model")
        #self.asr.set_property("word-syms", "tmp/models/tri2b_mmi/words.txt")
        #self.asr.set_property("lda-mat", "tmp/models/tri2b_mmi/matrix")
        #self.asr.set_property("silence-phones", "6:7:8:9:10")
        #self.asr.set_property("acoustic-scale", 1.0/13)

     
        self.filesink.set_property("location", "/dev/null")
        
        logger.info('Created GStreamer elements')
          
        self.pipeline = Gst.Pipeline()
        #for element in [self.filesrc, self.appsrc, self.decodebin, self.audioconvert, self.audioresample, self.tee, 
        #                self.queue1, self.filesink, 
        #                self.queue2, self.asr, self.appsink]:
        for element in [self.appsrc, self.asr, self.fakesink]:
            logger.debug("Adding %s to the pipeline" % element)       
            self.pipeline.add(element) 
        
        
        logger.info('Linking GStreamer elements')
        
        self.appsrc.link(self.asr)
        #self.decodebin.connect('pad-added', self._connect_decoder)
        
        #self.audioconvert.link(self.audioresample)
        #self.audioresample.link(self.asr)
        self.asr.link(self.fakesink)
        #self.appsrc.link(self.fakesink)
        
        # Create bus and connect several handlers
        self.bus = self.pipeline.get_bus()
        self.bus.add_signal_watch()
        self.bus.enable_sync_message_emission()
        self.bus.connect('message::eos', self._on_eos)
        self.bus.connect('message::error', self._on_error)
        self.loop = GObject.MainLoop()
        self.asr.connect('hyp-word', self._on_word)
        #self.filesink.get_bus().connect('message::eos', self.on_eos)
    
    def _connect_decoder(self, element, pad):
        logger.info("Connecting audio decoder")
        pad.link(self.audioconvert.get_static_pad("sink"))        
    
    def _on_word(self, asr, word):
        logger.info("Got word: %s" % word)    
        if self.word_handler:
            self.word_handler(word)

    def _on_error(self, bus, msg):
        self.error = msg.parse_error()
        logger.error(self.error)
        
    def _on_eos(self, bus, msg):
        logger.info('Pipeline received eos signal')
        self.pipeline.set_state(Gst.State.NULL)
        if self.eos_handler:
            self.eos_handler[0](self.eos_handler[1])
                
    def init_request(self, id, caps_str):
        pass
        #caps = Gst.caps_from_string(caps_str)
        #self.appsrc.set_property("caps", caps)
        #self.appsrc.set_state(Gst.State.PAUSED)
                
        #self.pipeline.set_state(Gst.State.PAUSED)
        #if self.outdir:
        #    self.filesink.set_state(Gst.State.NULL)
        #    self.filesink.set_property('location', "%s/%s.raw" % (self.outdir, id))
        #self.filesrc.set_state(Gst.State.PLAYING)
        #self.filesink.set_state(Gst.State.PLAYING)        
        #self.decodebin.set_state(Gst.State.PLAYING)
        #self.pipeline.set_state(Gst.State.PLAYING)        

                
    def process_data(self, data):    
        logger.info('Pushing buffer of size %d to pipeline' % len(data))    
        buf = Gst.Buffer.new_allocate(None, len(data), None)
        for (i, c) in enumerate(data):
            buf.memset(i, c, 1)
        self.appsrc.emit("push-buffer", buf)
        #self.filesink.set_state(Gst.State.PLAYING) 
        self.pipeline.set_state(Gst.State.PLAYING)
        self.recognizing = True        
        
        
    def end_request(self):
        logger.info("Pushing EOS to pipeline")
        self.pipeline.send_event(Gst.Event.new_eos())
        
        
    def set_word_handler(self, handler):
        self.word_handler = handler
        
    def set_eos_handler(self, handler, user_data=None):
        self.eos_handler = (handler, user_data) 
    
    def cancel(self):
        logger.info("Cancelling pipeline")
        #if (self.pipeline.get_state() == Gst.State.PLAYING):
        #logger.debug("Sending EOS to pipeline")
        #self.pipeline.send_event(Gst.Event.new_eos())
        self.pipeline.set_state(Gst.State.READY)       
    
        
   
if __name__ == '__main__':
    finished = [False]
    loop = GObject.MainLoop()
    thread.start_new_thread(loop.run, ())
            
    logging.basicConfig(level=logging.INFO)
    decoder_pipeline = DecoderPipeline()
    
    def word_printer(word):
        print word
        
    def set_finished(finished):
        finished[0] = True
    
    decoder_pipeline.set_word_handler(word_printer)
    decoder_pipeline.set_eos_handler(set_finished, finished)
    
    def do_shit():
        decoder_pipeline.init_request("test0", "audio/x-raw,rate=16000,channels=1,format=(string)S16LE")
        f = open("test/data/test.raw", "rb")
        for block in iter(lambda: f.read(2*16000), ""):
            #time.sleep(1)
            decoder_pipeline.process_data(block)
        
        decoder_pipeline.end_request()

    do_shit()

    while not finished[0]:
        time.sleep(1)
        print finished[0]
    
    finished[0] = False    
    do_shit()
    while not finished[0]:
        time.sleep(1)
        print finished[0]
