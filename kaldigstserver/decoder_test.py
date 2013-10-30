'''
Created on Jun 27, 2013

@author: tanel
'''
import unittest
from gi.repository import GObject, Gst
import thread
import logging
from decoder import DecoderPipeline
import time

class DecoderPipelineTests(unittest.TestCase):

    def testDecoder(self):
        finished = [False]
        loop = GObject.MainLoop()
        thread.start_new_thread(loop.run, ())
                
        logging.basicConfig(level=logging.INFO)
        decoder_conf = {"model" : "test/models/estonian/tri2b_mmi_pruned/final.mdl",
                        "lda-mat" : "test/models/estonian/tri2b_mmi_pruned/final.mat",
                        "word-syms" : "test/models/estonian/tri2b_mmi_pruned/words.txt",
                        "fst" : "test/models/estonian/tri2b_mmi_pruned/HCLG.fst",
                        "silence-phones" : "6"}
        
        
        decoder_pipeline = DecoderPipeline({"decoder" : decoder_conf})
        
        words = []
        
        def word_getter(word):
            words.append(word)
            
        def set_finished(finished):
            finished[0] = True
        
        decoder_pipeline.set_word_handler(word_getter)
        decoder_pipeline.set_eos_handler(set_finished, finished)
        
        def do_shit():
            decoder_pipeline.init_request("test0", "audio/x-raw, layout=(string)interleaved, rate=(int)16000, format=(string)S16LE, channels=(int)1")
            f = open("test/data/lause2.raw", "rb")
            for block in iter(lambda: f.read(2*16000), ""):
                time.sleep(1)
                decoder_pipeline.process_data(block)
            
            decoder_pipeline.end_request()
    
        do_shit()
    
        while not finished[0]:
            time.sleep(1)
        self.assertItemsEqual(["see", "on", "teine", "lause", "<#s>"], words, "Recognition result")
        
        words = []
        
        finished[0] = False    
        do_shit()
        while not finished[0]:
            time.sleep(1)
            
        self.assertItemsEqual(["see", "on", "teine", "lause", "<#s>"], words, "Recognition result")
        
        # Now test cancelation
        words = []        
        decoder_pipeline.init_request("test0", "audio/x-raw, layout=(string)interleaved, rate=(int)16000, format=(string)S16LE, channels=(int)1")
        f = open("test/data/lause2.raw", "rb")
        decoder_pipeline.process_data(f.read(2*16000))
        decoder_pipeline.cancel()
        print "Pipeline cancelled"
        
        words = []
        finished[0] = False
        decoder_pipeline.init_request("test0", "audio/x-raw, layout=(string)interleaved, rate=(int)16000, format=(string)S16LE, channels=(int)1")
        # read and send everything
        f = open("test/data/lause2.raw", "rb")
        decoder_pipeline.process_data(f.read(10*16000))
        decoder_pipeline.end_request()
        while not finished[0]:
            time.sleep(1)            
        self.assertItemsEqual(["see", "on", "teine", "lause", "<#s>"], words, "Recognition result")
        
        #test cancelling without anything sent
        decoder_pipeline.init_request("test0", "audio/x-raw, layout=(string)interleaved, rate=(int)16000, format=(string)S16LE, channels=(int)1")
        decoder_pipeline.cancel()
        print "Pipeline cancelled"
        
        words = []
        finished[0] = False
        decoder_pipeline.init_request("test0", "audio/x-wav")
        # read and send everything
        f = open("test/data/lause2.wav", "rb")
        decoder_pipeline.process_data(f.read())
        decoder_pipeline.end_request()
        while not finished[0]:
            time.sleep(1)            
        self.assertItemsEqual(["see", "on", "teine", "lause", "<#s>"], words, "Recognition result")

        words = []
        finished[0] = False
        decoder_pipeline.init_request("test0", "audio/ogg")
        # read and send everything
        f = open("test/data/test_2lauset.ogg", "rb")
        decoder_pipeline.process_data(f.read(10*16000))

        decoder_pipeline.end_request()
        while not finished[0]:
            time.sleep(1)
        self.assertItemsEqual("see on esimene lause <#s> see on teine lause <#s>".split(), words, "Recognition result")


def main():
    unittest.main()

if __name__ == '__main__':
    main()