# LCP CLI module

> Command-line tool for converting CONLLU files and uploading the corpus to LCP

## Installation

Make sure you have python 3.11+ with `pip` installed in your local environment, then run:

```bash
pip install lcpcli==0.2.6
```

## Usage

**Example:**

Corpus conversion:

```bash
lcpcli -i ~/conll_ext/ -o ~/upload/
```

Data upload:

```bash
lcpcli -c ~/upload/ -k $API_KEY -s $API_SECRET -p my_project --live
```

Including `--live` points the upload to the live instance of LCP. Leave it out if you want to add a corpus to an instance of LCP running on `localhost`.

**Help:**

```bash
lcpcli --help
```

`lcpcli` takes a corpus of CoNLL-U (PLUS) files and imports it to a project created in an LCP instance, such as _catchphrase_.

Besides the standard token-level CoNLL-U fields (`form`, `lemma`, `upos`, `xpos`, `feats`, `head`, `deprel`, `deps`) one can also provide document- and sentence-level annotations using comment lines in the files (see [the CoNLL-U Format section](#conll-u-format)).

### Example corpus

`lcpcli` ships with an example one-video "corpus": the video is an excerpt from the CC-BY 3.0 "Big Buck Bunny" video ((c) copyright 2008, Blender Foundation / www.bigbuckbunny.org) and the "transcription" is a sample of the Declaration of the Human Rights

To populate a folder with the example data, use this command

```bash
lcpcli --example /destination/folder/
```

This will create a subfolder named *free_video_corpus* in */destination/folder* which, itself, contains two subfolders: *input* and *output*. The *input* subfolder contains four files:

 - *doc.conllu* is a CoNLL-U Plus file that contains the textual data, with time alignments in seconds at the token- (`start` and `end` in the MISC column), segment- (`# start = ` and `# end = ` comments) and document-level (`#newdoc start =` and `#newdoc end =`)
 - *namedentity.csv* is a comma-separated value lookup file that contains information about the named entities, where each row associates an ID reported in the `namedentity` token cells of *doc.conllu* with two attributes, `type` and `form`
 - *shot.csv* is a comma-separated value file that defines time-aligned annotations about the shots in the video in the `view` column, where the `start` and `end` columns are timestamps, in seconds, relative to the document referenced in the `doc_id` column
 - *meta.json* is a JSON file that defines the structure of the corpus, used both for pre-processing the data before upload, and when adding the data to the LCP database. Read on for information on the definitions in this file

### CoNLL-U Format

The CoNLL-U format is documented at: https://universaldependencies.org/format.html

The LCP CLI converter will treat all the comments that start with `# newdoc KEY = VALUE` as document-level attributes.
This means that if a CoNLL-U file contains the line `# newdoc author = Jane Doe`, then in LCP all the sentences from this file will be associated with a document whose `meta` attribute will contain `author: 'Jane Doe'`.

All other comment lines following the format `# key = value` will add an entry to the `meta` attribute of the _segment_ corresponding to the sentence below that line (i.e. not at the document level).

The key-value pairs in the `MISC` column of a token line will go in the `meta` attribute of the corresponding token, with the exceptions of these key-value combinations:
 - `SpaceAfter=Yes` vs. `SpaceAfter=No` (case senstive) controls whether the token will be represented with a trailing space character in the database
 - `start=n.m|end=o.p` (case senstive) will align tokens, segments (sentences) and documents along a temporal axis, where `n.m` and `o.p` should be floating values in seconds

See below how to report all the attributes in the template `.json` file.

#### CoNLL-U Plus

CoNLL-U Plus is an extension to the CoNLLU-U format documented at: https://universaldependencies.org/ext-format.html

If your files start with a comment line of the form `# global.columns = ID FORM LEMMA UPOS XPOS FEATS HEAD DEPREL DEPS MISC`, `lcpcli` will treat them as CoNLL-U PLUS files and process the columns according to the names you set in that line.


#### Media files

If your corpus includes media files, your `.json` template should report it under a `mediaSlots` key in `meta`, e.g.:

```json
"meta": {
    "name": "Free Single-Video Corpus",
    "author": "LiRI",
    "date": "2024-06-13",
    "version": 1,
    "corpusDescription": "Single, open-source video with annotated shots and a placeholder text stream from the Universal Declaration of Human Rights annotated with named entities",
    "mediaSlots": {
        "video": {
            "mediaType": "video",
            "isOptional": false
        }
    }
},
```

Your CoNLL-U file(s) should accordingly report each document's media file's name in a comment, like so:

```csv
# newdoc video = bunny.mp4
```

The `.json` template should also define a main key named `tracks` to control what annotations will be represented along the time axis. For example the following will tell the interface to display separate timeline tracks for the shot, named entity and segment annotations, with the latter being subdivided in as many tracks as there are distinct values for the attribute `speaker` of the segments:

```json
"tracks": {
    "layers": {
        "Shot": {},
        "NamedEntity": {},
        "Segment": {
            "split": [
                "speaker"
            ]
        }
    }
}
```

Finally, your **output** corpus folder should include a subfolder named `media` in which all the referenced media files have been placed


#### Attribute types


The values of each attribute (on tokens, segments, documents or at any other level) have a **type**; the most common types are `text`, `number` or `categorical`. The attributes must be reported in the template `.json` file, along with their type (you can see an example in the section **Convert and Upload**)

 - `text` vs `categorical`: while both types correspond to alpha-numerical values, `categorical` is meant for attributes that have a limited number of possible values (typically, less than 100 distinct values) of a limited length (as a rule of thumb, each value can have up to 50 characters). There is no such limits on values of attributes of type `text`. When a user starts typing a constraint on an attribute of type `categorical`, the DQD editor will offer autocompletition suggestions. The attributes of type `text` will have their values listed in a dedicated table (`lcpcli`'s conversion step produces corresponding `.csv` files) so a query that expresses a constraint on an attribute will be slower if that attribute if of type `text` than of type `categorical`

 - the type `labels` (with an `s` at the end) corresponds to a set of labels that users will be able to constrain in DQD using the `contain` keyword: for example, if an attribute named `genre` is of type `labels`, the user could write a constraint like `genre contain 'drama'` or `hobbies !contain 'comedy'`. The values of attributes of type `labels` should be one-line strings, with each value separated by a comma (`,`) character (as in, e.g., `# newdoc genre = drama, romance, coming of age, fiction`); as a consequence, no label can contain the character `,`.

 - the type `dict` corresponds to key-values pairs as represented in JSON

 - the type `date` requires values to be formatted in a way that can be parsed by PostgreSQL


### Convert and Upload

1. Create a directory in which you have all your properly-fromatted CONLLU files.

2. In the same directory, create a template `.json` file that describes your corpus structure (see above about the `attributes` key on `Document` and `Segment`), for example:

```json
{
    "meta": {
        "name": "Free Single-Video Corpus",
        "author": "LiRI",
        "date": "2024-06-13",
        "version": 1,
        "corpusDescription": "Single, open-source video with annotated shots and a placeholder text stream from the Universal Declaration of Human Rights annotated with named entities",
        "mediaSlots": {
            "video": {
                "mediaType": "video",
                "isOptional": false
            }
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
                "time": true
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
                "xpos": {
                    "isGlobal": false,
                    "type": "categorical",
                    "nullable": true
                },
                "ufeat": {
                    "isGlobal": false,
                    "type": "dict",
                    "nullable": true
                }
            }
        },
        "DepRel": {
            "abstract": true,
            "layerType": "relation",
            "attributes": {
                "udep": {
                    "type": "categorical",
                    "isGlobal": true,
                    "nullable": false
                },
                "source": {
                    "name": "dependent",
                    "entity": "Token",
                    "nullable": false
                },
                "target": {
                    "name": "head",
                    "entity": "Token",
                    "nullable": true
                },
                "left_anchor": {
                    "type": "number",
                    "nullable": false
                },
                "right_anchor": {
                    "type": "number",
                    "nullable": false
                }
            }
        },
        "NamedEntity": {
            "abstract": false,
            "layerType": "span",
            "contains": "Token",
            "anchoring": {
                "location": false,
                "stream": true,
                "time": false
            },
            "attributes": {
                "form": {
                    "isGlobal": false,
                    "type": "text",
                    "nullable": false
                },
                "type": {
                    "isGlobal": false,
                    "type": "categorical",
                    "nullable": true
                }
            }
        },
        "Shot": {
            "abstract": false,
            "layerType": "span",
            "anchoring": {
                "location": false,
                "stream": false,
                "time": true
            },
            "attributes": {
                "view": {
                    "isGlobal": false,
                    "type": "categorical",
                    "nullable": false
                }
            }
        },
        "Segment": {
            "abstract": false,
            "layerType": "span",
            "contains": "Token",
            "attributes": {
                "meta": {
                    "text": {
                        "type": "text"
                    },
                    "start": {
                        "type": "text"
                    },
                    "end": {
                        "type": "text"
                    }
                }
            }
        },
        "Document": {
            "abstract": false,
            "contains": "Segment",
            "layerType": "span",
            "attributes": {
                "meta": {
                    "audio": {
                        "type": "text",
                        "isOptional": true
                    },
                    "video": {
                        "type": "text",
                        "isOptional": true
                    },
                    "start": {
                        "type": "number"
                    },
                    "end": {
                        "type": "number"
                    },
                    "name": {
                        "type": "text"
                    }
                }
            }
        }
    },
    "tracks": {
        "layers": {
            "Shot": {},
            "Segment": {},
            "NamedEntity": {}
        }
    }
}
```

3. If your corpus defines a character-anchored entity type such as named entities, make sure you also include a properly named and formatted CSV file for it in the directory.

4. Visit an LCP instance (e.g. _catchphrase_) and create a new project if you don't already have one where your corpus should go.

5. Retrieve the API key and secret for your project by clicking on the button that says: "Create API Key".

6. Once you have your API key and secret, you can start converting and uploading your corpus by running the following command:

```
lcpcli -i $CONLLU_FOLDER -o $OUTPUT_FOLDER -k $API_KEY -s $API_SECRET -p $PROJECT_NAME --live
```

- `$CONLLU_FOLDER` should point to the folder that contains your CONLLU files
- `$OUTPUT_FOLDER` should point to *another* folder that will be used to store the converted files to be uploaded
- `$API_KEY` is the key you copied from your project on LCP (still visible when you visit the page)
- `$API_SECRET` is the secret you copied from your project on LCP (only visible upon API Key creation)
- `$PROJECT_NAME` is the name of the project exactly as displayed on LCP -- it is case-sensitive, and space characters should be escaped
