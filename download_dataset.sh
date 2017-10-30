#!/usr/bin/env bash

hash wget 2>/dev/null || { echo >&2 "Wget required.  Aborting."; exit 1; }
hash unzip 2>/dev/null || { echo >&2 "unzip required.  Aborting."; exit 1; }

wget http://alchem.usc.edu/~chao/download/book_datasets.zip
unzip -o "book_datasets.zip"
