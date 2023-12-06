# LCP CLI module

> Helper for converting CONLLU files and uploading the corpus to LCP

## Installation

```bash
# use python 3.11
pip install lcpcli
```

or 

```bash
# use python 3.11
python setup.py install
```

## Usage

Help:

```bash
lcpcli --help
```

Convert and upload:

1. Create a parent directory in which you have child directory that contains all your properly-fromatted CONLLU files

2. In the **parent** directory, next to the folder containing the CONLLU files, create a template `.json` file that describes your corpus structure, for example:

```
{
    "meta":{
        "name":"My corpus",
        "author":"Myself",
        "date":"2023",
        "version": 1,
        "corpusDescription":"This is my corpus"
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
                    "nullable": false
                },
                "lemma": {
                    "isGlobal": false,
                    "type": "text",
                    "nullable": true
                },
                "upos": {
                    "isGlobal": true,
                    "type": "categorical",
                    "nullable": false
                }
            }
        },
        "Segment": {
            "abstract": false,
            "layerType": "span",
            "contains": "Token"
        },
        "Document": {
            "abstract": false,
            "contains": "Segment",
            "layerType": "span",
            "attributes": {
                "meta": {
                    "language": {
                      "type": "text",
                      "nullable": true
                    },
                    "author": {
                      "type": "text",
                      "nullable": true
                    }
                }
            }
        }
    }
}
```

3. Visit LCP and create a new project if you don't already have one where your corpus should go

4. Retrieve the API key and secret for your project by clicking on the button that says: "Create API Key". The secret will appear at the bottom of the page and remain visible only for 120s, after which it will disappear forever (you would then need to revoke the API key and create a new one) -- the key itself is listed above the button that says "Revoke API key" (make sure to **not** copy the line that starts with "Secret Key" along with the API key itself)

5. Once you have your API key and secret, you can start converting and uploading your corpus by running the following command:

```
lcpcli -i $CONLLU_FOLDER -m upload -k $API_KEY -s $API_SECRET -p $PROJECT_NAME --live
```

- `$CONLLU_FOLDER` should point to the folder that contains your CONLLU files (ie. **inside** the parent folder)
- `$API_KEY` is the key you copied from your project on LCP (still visible when you visit the page)
- `$API_SECRET` is the secret you copied from your project on LCP (only visible upon API Key creation)
- `$PROJECT_NAME` is the name of the project exactly as displayed on LCP -- it is case-sensitive, and space characters should be escaped
