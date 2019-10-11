#! /bin/bash

BASE_URL=http://kaldi-asr.org/models/11/
MODEL=0011_multi_cn_chain_sp_online.tar.gz

modeldir=`dirname $0`/chinese/multi_cn_chain_sp_online

mkdir -p $modeldir

cd $modeldir

wget -N $BASE_URL/$MODEL || exit 1
tar -zxvf $MODEL
rm $MODEL

cd -
