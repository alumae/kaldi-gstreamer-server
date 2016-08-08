#! /bin/bash

BASE_URL=http://kaldi-asr.org/downloads/build/6/trunk/egs/librispeech/s5

MODEL=exp/nnet2_online/nnet_a_online
GRAPH=exp/tri6b

modeldir=`dirname $0`/english/librispeech_nnet_a_online

mkdir -p $modeldir

cd $modeldir

wget -N $BASE_URL/$MODEL/final.mdl || exit 1
(mkdir -p ivector_extractor; cd ivector_extractor; wget -N $BASE_URL/$MODEL/ivector_extractor/{final.ie,final.dubm,final.mat,global_cmvn.stats}) || exit 1
(mkdir -p conf; cd conf; wget -N $BASE_URL/$MODEL/conf/{ivector_extractor.conf,online_nnet2_decoding.conf,mfcc.conf,online_cmvn.conf,splice.conf}) || exit 1

wget -N $BASE_URL/$GRAPH/graph_tgsmall/HCLG.fst || exit 1
wget -N $BASE_URL/$GRAPH/graph_tgsmall/words.txt || exit 1


cat conf/ivector_extractor.conf | perl -npe "s/=.*nnet_a_online\//=test\/models\/english\/librispeech_nnet_a_online\//" > conf/ivector_extractor.fixed.conf

cat conf/online_nnet2_decoding.conf | perl -npe "s/=.*nnet_a_online\//=test\/models\/english\/librispeech_nnet_a_online\//" > conf/online_nnet2_decoding.fixed.conf


cd -