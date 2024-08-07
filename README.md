# LCP CLI module

> Command-line tool for converting CONLLU files and uploading the corpus to LCP

## Installation

Make sure you have python 3.11+ with `pip` installed in your local environment, then run

```bash
pip install lcpcli
```

## Usage

**Example:**

```bash
lcpcli -i ~/conll_ext/ -o ~/upload/ -m upload -k $API_KEY -s $API_SECRET -p my_project
```

**Help:**

```bash
lcpcli --help
```

`lcpcli` takes a corpus of CoNLL-U (PLUS) files and imports it to a project created in an LCP instance, such as _catchphrase_.

Besides the standard token-level CoNLL-U fields (`form`, `lemma`, `upos`, `xpos`, `feats`, `head`, `deprel`, `deps`) one can also provide document- and sentence-level annotations using comment lines in the files (see [the CoNLL-U Format section](#conll-u-format))

A more advanced functionality, `lcpcli` supports annotations aligned at the character level, such as named entities. See [the Named Entities section](#named-entities) for more information

### CoNLL-U Format

The CoNLL-U format is documented at: https://universaldependencies.org/format.html

The LCP CLI converter will treat all the comments that start with `# newdoc KEY = VALUE` as document-level attributes.
This means that if a CoNLL-U file contains the line `# newdoc author = Jane Doe`, then in LCP all the sentences from this file will be associated with a document whose `meta` attribute will contain `author: 'Jane Doe'`

All other comment lines following the format `# key = value` will add an entry to the `meta` attribute of the _segment_ corresponding to the sentence below that line (ie not at the document level)

The key-value pairs in the `misc` column in a column line will go in the `meta` attribute of the corresponding token, with the exceptions of these key-value combinations:
 - `SpaceAfter=Yes` vs. `SpaceAfter=No` controls whether the token will be represented with a trailing space character in the database
 - `start=n.m|end=o.p` will align tokens, segments (sentences) and documents along a temporal axis, where `n.m` and `o.p` should be floating values in seconds

See below how to report all the attributes in the template `.json` file

#### CoNLL-U PLUS

CoNLL-U PLUS is an extension to the CoNLLU-U format documented at: https://universaldependencies.org/ext-format.html

If your files start with a comment line of the form `# global.columns = ID FORM LEMMA UPOS XPOS FEATS HEAD DEPREL DEPS MISC`, `lcpcli` will treat them as CoNLL-U PLUS files and process the columns according to the names you set in that line

#### Named Entities

Besides the nested token-, segment- and document-level entities, you can use `lcpcli` to define other character-aligned entities, such as named entities. To do so, you will need to prepare your corpus as CoNLL-U PLUS files which must define a dedicated column, e.g. `NAMEDENTITY`:

```conllu
# global.columns = ID FORM LEMMA UPOS NAMEDENTITY
```

All the tokens belonging to the same named entity should report the same index in that column, or `_` if it doesn't belong to a named entity. For example (assuming the columns defined above):

```conllu
0	Christoph	Christoph	PROPN	114
1	W.	W.	PROPN	114
2	Bauer	Bauer	PROPN	114
3	erzählt	erzählen	VERB	_
4	die	der	DET	_
5	Geschichte	Geschichte	NOUN	_
6	von	von	ADP	_
7	Innsbruck	Innsbruck	PROPN	115
8	,	,	PUNCT	_
```

In this example, the three first tokens belong to the same named entity ("Christoph W. Bauer") and "Innsbruck" forms another named entity.

The directory containing your corpus files should also include one TSV file named after that column (in this example, it could be named `namedentity.tsv` -- the extension doesn't matter, as long as it's not the same as your CoNLLU files). Its first line should report headers, starting with `ID` and then any attributes associated with a named entity. The value in the first column for all the other lines should correspond to the ones listed in the CoNLLU file(s). For example:

```tsv
ID	type
114	PER
115	LOC
```

Along with the CoNLLU-PLUS lines above, this would associate the corresponding occurrence of the sequence "Christoph W. Bauer" with a named entity of type `PER` and the corresponding occurrence of "Innsbruck" with a named entity of type `LOC`.

Finally, you need to report a corresponding entity type in the template `.json` under the `layer` key, for example:

```json
"NamedEntity": {
    "abstract": false,
    "layerType": "span",
    "contains": "Token",
    "attributes": {
        "type": {
            "isGlobal": false,
            "type": "categorical",
            "values": [
                "PER",
                "LOC",
                "MISC",
                "ORG"
            ],
            "nullable": true
        }
    }
},
```

Make sure to set the `abstract`, `layerType` and `contains` attributes as illustrated above. See the section [Convert and Upload](#convert-and-upload) for a full example of a template `.json` file.

#### Other anchored entities

Your corpus can include other entities besides tokens, sentences, documents and annotations that enter in a subset/superset relation with those. For example, a video corpus could include _gestures_ that are **time-anchored** but do not necessarily align with tokens or segments on the time axis (e.g. a gesture could start in the middle of a sentence and end some time after its end)

In such a case, your template `.json` file should report that entity under `layer`, for example:

```json
"Gesture": {
    "abstract": false,
    "layerType": "unit",
    "anchoring": {
        "location": false,
        "stream": false,
        "time": true
    },
    "attributes": {
        "name": {
            "type": "categorical",
            "values": [
                "waving",
                "thumbsup"
            ]
        }
    }
},
```

Much like in the case of named entities described above, you should also include a TSV file that lists the entities, named `<entity>.csv`. The first column should be named `<entity>_id` and list unique IDs; one column should be named `doc_id` and report the ID of the corresponding document (make sure to include corresponding `# newdoc id = <ID>` comments in your CoNLLU files); two columns named `start` and `end` should list the time points for temporal anchoring, measured in seconds from the start of the document's media file; with additional columns for the entity's attributes. For example, `gesture.csv`:

```tsv
gesture_id	doc_id	start	end	name
1	video1	1.2	3.5	waving
2	video1	2.3	4.7	thumbsup
3	video2	3.2	4.5	thumbsup
4	video2	8.3	9.7	waving
```

#### Global attributes

In some cases, it makes sense for multiple entity types to share references: in those cases, they can define _global attributes_. An example of a global attribute is a speaker or an agent that can have a name, an age, etc. and be associated with both a segment (a sentence) and, say, a gesture. The corpus template would include definitions along these lines:

```json
"globalAttributes": {
    "agent": {
        "type": "dict",
        "keys": {
            "name": {
                "type": "text"
            },
            "age": {
                "type": "number"
            }
        }
    }
},
"layer": {
    "Segment": {
        "abstract": false,
        "layerType": "span",
        "contains": "Token",
        "attributes": {
            "agent": {
                "ref": "agent"
            }
        }
    },
    "Gesture": {
        "abstract": false,
        "layerType": "unit",
        "anchoring": {
            "time": true
        },
        "attributes": {
            "agent": {
                "ref": "agent"
            }
        }
    }
}
```

You should include a file named `global_attribute_agent.csv` (mind the singular on `attribute`) with three columns: `agent_id`, `name` and `age`, and reference the values of `agent_id` appropriately as a sentence-level comment in your CoNLL-U files as well as in a file named `gesture.csv`. For example:

*global_attribute_agent.csv*:
```tsv
agent_id	agent
10	{"name": "Jane Doe", "age": 37}
```

CoNLL-U file:
```conllu
# newdoc id = video1

# sent_id = 1
# agent_id = 10
The the _ _ _
```

*gesture.csv*:
```tsv
gesture_id	agent_id	doc_id	start	end
1	10	video1	1.25	2.6
```

#### Media files

If your corpus include media files, your `.json` template should report it under a main `mediaSlots` key, e.g.:

```json
"mediaSlots": {
    "interview": {
        "type": "audio",
        "isOptional": false
    }
}
```

Your CoNLL-U file(s) should accordingly report each document's media file's name in a comment, like so:

```tsv
# newdoc interview = itvw1.mp3
```

Finally, your **output** corpus folder should include a subfolder named `media` in which all the referenced media files have been placed


### Convert and Upload

1. Create a directory in which you have all your properly-fromatted CONLLU files

2. In the same directory, create a template `.json` file that describes your corpus structure (see above about the `attributes` key on `Document` and `Segment`), for example:

```json
{
    "meta":{
        "name":"My corpus",
        "author":"Myself",
        "date":"2023",
        "version": 1,
        "corpusDescription":"This is my corpus"
    },
    "mediaSlots": {
        "interview": {
            "type": "audio",
            "isOptional": false
        }
    },
    "firstClass": {
        "document": "Document",
        "segment": "Segment",
        "token": "Token"
    },
    "layer": {
        "Token": {
            "abstract": false,
            "layerType": "unit",
            "anchoring": {
                "location": false,
                "stream": true,
                "time": false
            },
            "attributes": {
                "form": {
                    "isGlobal": false,
                    "type": "text",
                    "nullable": true
                },
                "lemma": {
                    "isGlobal": false,
                    "type": "text",
                    "nullable": false
                },
                "upos": {
                    "isGlobal": true,
                    "type": "categorical",
                    "nullable": true
                },
                "misc": {
                    "type": "jsonb"
                }
            }
        },
        "NamedEntity": {
            "abstract": false,
            "layerType": "span",
            "contains": "Token",
            "attributes": {
                "type": {
                    "isGlobal": false,
                    "type": "categorical",
                    "values": [
                        "PER",
                        "LOC",
                        "MISC",
                        "ORG"
                    ],
                    "nullable": true
                }
            }
        },
        "Gesture": {
            "abstract": false,
            "layerType": "unit",
            "anchoring": {
                "time": true
            },
            "attributes": {
                "agent": {
                    "ref": "agent"
                }
            }
        },
        "Segment": {
            "abstract": false,
            "layerType": "span",
            "contains": "Token",
            "attributes": {
                "agent": {
                    "ref": "agent"
                }
            }
        },
        "Document": {
            "abstract": false,
            "contains": "Segment",
            "layerType": "span",
            "attributes": {
                "meta": {
                    "Autor": {
                        "type": "text",
                        "nullable": true
                    },
                    "promethia_id": {
                        "type": "text",
                        "nullable": true
                    },
                    "ISBN": {
                        "type": "text",
                        "nullable": true
                    },
                    "Titel": {
                        "type": "text",
                        "nullable": true
                    }
                }
            }
        }
    },
    "globalAttributes": {
        "agent": {
            "type": "dict",
            "keys": {
                "name": {
                    "type": "text"
                },
                "age": {
                    "type": "number"
                }
            }
        }
    }
}
```

3. If your corpus defines a character-anchored entity type such as named entities, make sure you also include a properly named and formatted TSV file for it in the directory (see [the Named Entities section](#named-entities))

4. Visit an LCP instance (e.g. _catchphrase_) and create a new project if you don't already have one where your corpus should go

5. Retrieve the API key and secret for your project by clicking on the button that says: "Create API Key"

    The secret will appear at the bottom of the page and remain visible only for 120s, after which it will disappear forever (you would then need to revoke the API key and create a new one)
    
    The key itself is listed above the button that says "Revoke API key" (make sure to **not** copy the line that starts with "Secret Key" along with the API key itself)

6. Once you have your API key and secret, you can start converting and uploading your corpus by running the following command:

```
lcpcli -i $CONLLU_FOLDER -o $OUTPUT_FOLDER -m upload -k $API_KEY -s $API_SECRET -p $PROJECT_NAME --live
```

- `$CONLLU_FOLDER` should point to the folder that contains your CONLLU files
- `$OUTPUT_FOLDER` should point to *another* folder that will be used to store the converted files to be uploaded
- `$API_KEY` is the key you copied from your project on LCP (still visible when you visit the page)
- `$API_SECRET` is the secret you copied from your project on LCP (only visible upon API Key creation)
- `$PROJECT_NAME` is the name of the project exactly as displayed on LCP -- it is case-sensitive, and space characters should be escaped
