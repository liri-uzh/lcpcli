# Corpus builder - Tutorial

In this tutorial, we will build a small corpus from a CoNLL-U input, which is a standard format to represent data in corpus linguistics. Note that `lcpcli` ships with a built-in CoNLL-U converter; this tutorial partly reproduces what `lcpcli` implements natively for the sake of illustration.

The CoNLL-U input in this tutorial was generated from subtitles SRT files associated with videos. In a first step, we will simply take the forms and lemmas of the transcribed tokens in the CoNLL-U inpuyt and map them to segmented sentences. In a second step, we will incorporate additional attributes of the tokens and of the sentences present in the input. Finally, in a third step, we will associate the data with video files and correspondingly anchor the sentences along the time axis.

# Pre-requisites

Install `lcpcli` on your machine:

```bash
pip install lcpcli
```

Navigate to a working directory and create a subfolder named *test_corpus_output*:

```bash
mkdir test_corpus_output
```

# Sample data

We will start with this two-sentence CoNLL-U sample below, which was generated from a subtitles file:

```
# sent_id = 1
# text = It shouldn't be that complicated to carry out simple edits in a speech corpus.
# start = 10.433
# end = 14.366
1	It	It	_	_	_	_	_	_	_
2	should	should	_	_	_	_	_	_	SpaceAfter=No
3	n't	not	_	_	_	_	_	_	_
4	be	be	_	_	_	_	_	_	_
5	that	that	_	_	_	_	_	_	_
6	complicated	complicated	_	_	_	_	_	_	_
7	to	to	_	_	_	_	_	_	_
8	carry	carry	_	_	_	_	_	_	_
9	out	out	_	_	_	_	_	_	_
10	simple	simple	_	_	_	_	_	_	_
11	edits	edits	_	_	_	_	_	_	_
12	in	in	_	_	_	_	_	_	_
13	a	a	_	_	_	_	_	_	_
14	speech	speech	_	_	_	_	_	_	_
15	corpus	corpus	_	_	_	_	_	_	SpaceAfter=No
16	.	.	PUNCT	_	_	_	_	_	_

# sent_id = 2
# text = And luckily with databaseExplorer it isn't.
# start = 14.766
# end = 18.2
1	And	And	_	_	_	_	_	_	_
2	luckily	luckily	_	_	_	_	_	_	_
3	with	with	_	_	_	_	_	_	_
4	databaseExplorer	databaseExplorer	_	_	_	_	_	_	_
5	it	it	_	_	_	_	_	_	_
6	is	is	_	_	_	_	_	_	SpaceAfter=No
7	n't	not	_	_	_	_	_	_	SpaceAfter=No
8	.	.	PUNCT	_	_	_	_	_	_
```

Although most fields are empty (`_`) the sample contains enough information to create a corpus.

## First pass: sequences of (form,lemma)

Create a new file named *database_explorer.conllu* in your working directory and paste the content of the sample above.

Let us start by creating a corpus of sequences of form+lemma tokens, grouped in sentences:

```python
import os
from lcpcli.builder import Corpus

# The main corpus object
c = Corpus("CoNLL-U subtitles")

def make_sentence(corpus, doc, tokens):
    """Create a new segment entry in the corpus given a list of tokens"""
    if not tokens:
        return
    # call Segment on doc to signal the segments belong to doc
    # as direct arguments of doc.Segment, the tokens (created on corpus) will belong to the segment
    sentence = doc.Segment(*[corpus.Token(f, lemma=l) for f, l in tokens])
    sentence.make()

def process_file(fn):
    doc_name = os.path.basename(fn).removesuffix(".conllu")
    with open(fn, "r", encoding="utf-8") as input:
        doc = c.Document(name=doc_name)  # this file is one document
        tokens = []  # store (form,lemma) as we read them
        while line := input.readline():
            if line and line[0].isdigit():
                # token lines in conllu start with a digit
                token_id, form, lemma, *_ = line.split("\t")
                tokens.append((form, lemma))
                continue
            # when not on a token line: make a sentence with the stored tokens
            make_sentence(c, doc, tokens)
            tokens = []
        # final make sentence with the last tokens
        make_sentence(c, doc, tokens)
        # the document is now ready to be made
        doc.make()

process_file("database_explorer.conllu")

# generate the corpus files in the destination folder
c.make("./test_corpus_output/")
```

The script is pretty self-explanatory. Note that you can create entries in the corpus at multiple levels:

 1. at the corpus level (`c.Document`)
 2. at the document level (`doc.Segment`)
 3. as a direct argument to a segment (e.g. `doc.Segment(corpus.Token("hello"), corpus.Token("world"))`)

The created entries will exist below the level at which they are created:
 1. in the first case, the new document belongs to the corpus and has no parent
 2. in the second case, the new segment belongs to the document
 3. in the third case, the tokens exceptionally belong to the segment because, although created on `corpus`, they are passed as direct arguments to `doc.Segment`.

Note that `Token` accepts one direct (mandatory) argument, the form of the token. Additional attributes of the token, such as lemma, are passed as named arguments.

## Second pass: additional attributes

Now we will report all the values from the comment lines (`# text = ...`, `# start = ...`) as attributes of the sentences. We will also look up all the columns of the token lines and pass them as named arguments when creating the tokens; we handle `SpaceAfter=No` from `misc` separately so LCP can adequately control the display of spacing when rendering sentences.

The script below includes comments about the relevant changes:

```python
import os
import re  # to parse the comment lines
from lcpcli.builder import Corpus

c = Corpus("CoNLL-U subtitles")

# All the standard CoNLL-U columns (see https://universaldependencies.org/format.html)
CONLLU_COLUMNS = ("id","form","lemma","upos","xpos","feats","head","deprel","deps","misc",)

def make_sentence(corpus, doc, sentence_buffer):
    if not sentence_buffer["tokens"]:
        return
    # pass the token attributes fetched from CoNLL-U as named arguments
    tokens = [
        corpus.Token(
            t.get("form", ""),
            **{k: v for k, v in t.items() if k not in ("id", "form") and v},
        )
        for t in sentence_buffer["tokens"]
    ]
    # pass the sentence attributes fetched from the comment lines as named arguments
    sentence = doc.Segment(
        *tokens, **{k: v for k, v in sentence_buffer.items() if k != "tokens" and v}
    )
    sentence.make()
    sentence_buffer["tokens"] = []

def process_file(fn):
    doc_name = os.path.basename(fn).removesuffix(".conllu")
    with open(fn, "r", encoding="utf-8") as input:
        doc = c.Document(name=doc_name)
        # store the sentence's text and tokens in this dict
        sentence_buffer = {"tokens": []}
        while line := input.readline():
            line = line.strip()
            if comm := re.match(r"# ([^=]+) = (.+)", line):
                k, v = [x.strip() for x in comm.groups()]
                sentence_buffer[k] = v
            if line and line[0].isdigit():
                # in CoNLL-U, _ stands for "no value"
                token = {
                    k.strip(): v.strip().replace("_", "")
                    for k, v in zip(CONLLU_COLUMNS, line.split("\t"))
                }
                # special case: report this as its own attribute
                if token.pop("misc", "") == "SpaceAfter=No":
                    token["spaceAfter"] = "0"
                sentence_buffer["tokens"].append(token)
                continue
            make_sentence(c, doc, sentence_buffer)
        make_sentence(c, doc, sentence_buffer)
        doc.make()

process_file("database_explorer.conllu")

c.make("./test_corpus_output/")
```


## Third pass: time-anchoring and video file association

Finally, we will use the `start` and `end` values from the comments to temporally anchor the segments. We will additionally assume that the CoNLL-U file matches a correspondingly named video file, and associate the document with it.

```python
import os
import re
from lcpcli.builder import Corpus

c = Corpus("CoNLL-U subtitles")

CONLLU_COLUMNS = ("id","form","lemma","upos","xpos","feats","head","deprel","deps","misc",)

def make_sentence(corpus, doc, sentence_buffer):
    if not sentence_buffer["tokens"]:
        return
    tokens = [
        corpus.Token(
            t.get("form", ""),
            **{k: v for k, v in t.items() if k not in ("id", "form") and v},
        )
        for t in sentence_buffer["tokens"]
    ]
    sentence = doc.Segment(
        *tokens,
        **{
            k: v
            for k, v in sentence_buffer.items()
            if k not in ("tokens", "start", "end") and v
        },
    )
    # compute the time points as 25 frames per second (LCP convention)
    sentence_start, sentence_end = [
        int(float(sentence_buffer.get(x, "0.0")) * 25) for x in ("start", "end")
    ]
    # call set_time to tempoarlly anchor the sentence
    sentence.set_time(sentence_start, sentence_end)
    sentence.make()
    sentence_buffer["tokens"] = []

def process_file(fn):
    doc_name = os.path.basename(fn).removesuffix(".conllu")
    with open(fn, "r", encoding="utf-8") as input:
        doc = c.Document(name=doc_name)
        doc.set_media("video", f"{doc_name}.mp4")
        sentence_buffer = {"tokens": []}
        while line := input.readline():
            line = line.strip()
            if comm := re.match(r"# ([^=]+) = (.+)", line):
                k, v = [x.strip() for x in comm.groups()]
                sentence_buffer[k] = v
            if line and line[0].isdigit():
                token = {
                    k.strip(): v.strip().replace("_", "")
                    for k, v in zip(CONLLU_COLUMNS, line.split("\t"))
                }
                # special case: report this as its own attribute
                if token.pop("misc", "") == "SpaceAfter=No":
                    token["spaceAfter"] = "0"
                sentence_buffer["tokens"].append(token)
                continue
            make_sentence(c, doc, sentence_buffer)
        make_sentence(c, doc, sentence_buffer)
        doc.make()

process_file("database_explorer.conllu")

c.make("./test_corpus_output/")
```

# Multiple documents

Here, we will use two CoNLL-U files, `database_explorer.conllu` and `presenter_pro.conllu`. These files, along with their respective videos, can be found here: https://drive.switch.ch/index.php/s/v3uxBpNkeYuyPE2

The only thing we need to do to process multiple documents, besides iteratevely calling `process_file` with filenames, is handle temporal offsets.

LCP is agnostic as to whether multiple documents and their annotations should overlap time-wise, in an effort to accommodate a wide range of situations. In this case, the two documents are completely independent and should thus *not* overlap. As a solution, we will then have each document start with a temporal offset, as implemented in the script below.


```python
import os
import re
from lcpcli.builder import Corpus

c = Corpus("CoNLL-U subtitles")

CONLLU_COLUMNS = ("id","form","lemma","upos","xpos","feats","head","deprel","deps","misc",)

def make_sentence(corpus, doc, sentence_buffer, time_offset=0):
    if not sentence_buffer["tokens"]:
        return time_offset
    tokens = [
        corpus.Token(
            t.get("form", ""),
            **{k: v for k, v in t.items() if k not in ("id", "form") and v},
        )
        for t in sentence_buffer["tokens"]
    ]
    sentence = doc.Segment(
        *tokens,
        **{
            k: v
            for k, v in sentence_buffer.items()
            if k not in ("tokens", "start", "end") and v
        },
    )
    # add time_offset to prevent temporal cross-document overlap
    sentence_start, sentence_end = [
        time_offset + int(float(sentence_buffer.get(x, "0.0")) * 25)
        for x in ("start", "end")
    ]
    sentence.set_time(sentence_start, sentence_end)
    sentence.make()
    sentence_buffer["tokens"] = []
    # keep track of sentence_end for the next document's offset
    return sentence_end

def process_file(fn, time_offset=0):
    # will return end_time to compute the next document's offset
    end_time = time_offset
    doc_name = os.path.basename(fn).removesuffix(".conllu")
    with open(fn, "r", encoding="utf-8") as input:
        doc = c.Document(name=doc_name)
        doc.set_media("video", f"{doc_name}.mp4")
        sentence_buffer = {"tokens": []}
        while line := input.readline():
            line = line.strip()
            if comm := re.match(r"# ([^=]+) = (.+)", line):
                k, v = [x.strip() for x in comm.groups()]
                sentence_buffer[k] = v
            if line and line[0].isdigit():
                token = {
                    k.strip(): v.strip().replace("_", "")
                    for k, v in zip(CONLLU_COLUMNS, line.split("\t"))
                }
                if token.pop("misc", "") == "SpaceAfter=No":
                    token["spaceAfter"] = "0"
                sentence_buffer["tokens"].append(token)
                continue
            # no-token sentences return an inappropriate end_time
            end_time = max(
                make_sentence(c, doc, sentence_buffer, time_offset),
                end_time
            )
        end_time = max(make_sentence(c, doc, sentence_buffer, time_offset), end_time)
        # explicity set the doc's time so that it starts *before* its first sentence
        doc.set_time(time_offset, end_time)
        doc.make()
    # return end_time to compute the next document's offset
    return end_time

doc_time_offset = 0
for fn in ("database_explorer.conllu", "presenter_pro.conllu"):
    # keep track of the offset for each processed file
    doc_time_offset = process_file(fn, doc_time_offset)

c.make("./test_corpus_output/")
```

You can now place the mp4 files in a *media* subfolder of *test_corpus_output* and check the integrity of the generated corpus by running `lcpcli -c ./test_corpus_output/ --check-only`.

You can also upload it to a collection of your own by running `lcpcli -i ./test_corpus_output/ -k $KEY -s $SECRET -p "your collection name" --live`.