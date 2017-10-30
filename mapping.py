#!/bin/pythona

f = open("books.csv", "r")
next(f)
d = {}

for line in f:
	strs = line.split(";")
#	print "%d, %s" % (int(strs[0]), strs[1])
        d[strs[1]]=strs[0]

f = open("book-ratings_small.csv", "r")
next(f)
for line in f:
        strs = line.split(";")
        if strs[1] in d:
            strs[1] = d[strs[1]]
            if int(strs[2]) == 0:
                print "%d;%d;%f" % (int(strs[0]), int(strs[1]), 5.0)
            else:
                print "%d;%d;%f" % (int(strs[0]), int(strs[1]), float(strs[2]))
