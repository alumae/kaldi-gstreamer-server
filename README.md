Kaldi GStreamer server
======================

This is an implementation of a real-time full-duplex speech recognition server, based on
the Kaldi toolkit and the GStreamer framework.

Communication with the server is based on websockets. Client sends speech to the server using
small chunks, while the server sends partial and full recognition hypotheses back to
the client via the same websocket, thus enabling full-duplex communication (as in Google's
voice typing in Android).

Installation
------------

### Requirements

#### Tornado web framework

Install Tornado 3, see http://www.tornadoweb.org/en/stable/

#### Kaldi

Download and compile Kaldi (http://kaldi.sourceforge.net). Also compile the online extensions (`make ext`)
and the Kaldi GStreamer plugin (see `README` in Kaldi's `src/gst-plugin` directory).

#### Acoustic and language models for Kaldi

You need GMM-HMM-based acooustic and n-gram language models (actually their FST cascade) for your language.
Heavily pruned models for Estonian everyday speech are available in `test/models/estonian`).


Running the server
------------------

TODO

Server usage
------------

### Opening a session

To open a session, connect to the specified server websocket address (e.g. ws://server:8888/speech).
The server assumes by default that incoming audio is sent using 16 kHz, mono, 16bit little-endian format. This can be overriden
using the 'content-type' request parameter. The content type has to be specified using GStreamer 1.0 caps format,
e.g. to send 44100 Hz mono 16-bit data, use: "audio/x-raw, layout=(string)interleaved, rate=(int)44100, format=(string)S16LE, channels=(int)1".
This needs to be url-encoded of course, so the actual request is something like:

    ws://server:8888/speech?content-type=audio/x-raw,+layout=(string)interleaved,+rate=(int)44100,+format=(string)S16LE,+channels=(int)1

Audio can also be encoded using any codec recognized by GStreamer (assuming the needed packages are installed on the server).
E.g., to send audio encoded using the Speex codec in an Ogg container, use the following URL to open the session (server should
automatically recognize the codec):

    ws://server:8888/speech?content-type=audio/ogg

### Sending audio

Speech should be sent to the server in raw blocks of data, using the encoding specified when session was opened.
It is recommended that a new block is sent at least 4 times per second (less infrequent blocks would increase the recognition lag).
Blocks do not have to be of equal size.

After the last block of speech data, a special string "EOS"  ("end-of-stream") needs to be sent to the server. This tells the
server that no more speech is coming and the recognition can be finalized.

After sending "EOS", client has to keep the websocket open to receive recognition results from the server. Server
closes the connection itself when all recognition results have been sent to the client.
No more audio can be sent via the same websocket after an "EOS" has been sent. In order to process a new
audio stream, a new websocket connection has to be created by the client.

### Reading results

Server sends recognition results and other information to the client using the JSON format.
The response can contain the following fields:

  * status -- response status, see codes below
  * message -- (optional) status message
  * result -- (optional) recognition result, containing the following fields:
    - hypotheses - recognized words, a list with each item containing the following:
        + transcript -- recognized words
        + confidence -- (optional) confidence of the hypothesis (float, 0..1)
    - final -- true when the hypothesis is final, i.e., doesn't change any more

The following status codes are currently in use:

  * 0 -- Success. Usually used when recognition results are sent
  * 2 -- Aborted. Recognition was aborted for some reason.
  * 1 -- No speech. Sent when the incoming audio contains a large portion of silence or non-speech.
  * 9 -- Not avalailable. Used when all recognizer processes are currently in use and recognition cannot be performed.

Websocket is always closed by the server after sending a non-zero status update.

Examples of server responses:

    {"status": 9}
    {"status": 0, "result": {"hypotheses": [{"transcript": "see on"}], "final": false}}
    {"status": 0, "result": {"hypotheses": [{"transcript": "see on teine lause."}], "final": true}}

Server segments incoming audio on the fly. For each segment, many non-final hypotheses, followed by one final
hypothesis are sent. Non-final hypotheses are used to present partial recognition hypotheses
to the client. A sequence of non-final hypotheses is always followed by a final hypothesis for that segment.
After sending a final hypothesis for a segment,
server starts decoding the next segment, or closes the connection, if all audio sent by the client has been processed.

Client is reponsible for presenting the results to the user in a way
suitable for the application.

Client software
---------------

Javascript client is available here: http://kaljurand.github.io/dictate.js

