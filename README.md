# LCP CLI module

> Command-line tool for converting CONLLU files and uploading the corpus to LCP

## Installation

Make sure you have python 3.11+ with `pip` installed in your local environment, then run:

```bash
pip install lcpcli
```

## Usage

**Examples:**

Conversion of a CoNLL-U (Plus) corpus:

```bash
lcpcli -i ~/conll_ext/ -o ~/upload/
```

Data upload:

```bash
lcpcli -c ~/upload/ -k $API_KEY -s $API_SECRET -p "my project" --live
```

Including `--live` points the upload to the live instance of LCP. Leave it out if you want to add a corpus to an instance of LCP running on `localhost`.

**Help:**

```bash
lcpcli --help
```

`lcpcli` can take a corpus of CoNLL-U (PLUS) files and import it to a collection created on LCP.

Besides the standard token-level CoNLL-U fields (`form`, `lemma`, `upos`, `xpos`, `feats`, `head`, `deprel`, `deps`) one can also provide document-, paragraph- and sentence-level annotations using comment lines in the files (see [the CoNLL-U Format section](#conll-u-format)).

### CoNLL-U Format

The CoNLL-U format is documented at: https://universaldependencies.org/format.html

The LCP CLI converter will treat all the comments that start with `# newdoc KEY = VALUE` as document-level attributes, and all the comments that start with `# newpar KEY = VALUE` as paragraph-level attributes. All other comment lines following the format `# key = value` will be treated sentence-level attributes.

The key-value pairs in the `FEATS` and `MISC` columns of a token line will be mapped to corresponding attributes in the LCP corpus. Additionally, if the `MISC` cell includes `SpaceAfter=Yes` or `SpaceAfter=No` (case senstive) the token will be represented with (respectively, without) a trailing space character in the database.

#### CoNLL-U Plus

CoNLL-U Plus is an extension to the CoNLLU-U format documented at: https://universaldependencies.org/ext-format.html

If your files start with a comment line of the form `# global.columns = ID FORM LEMMA UPOS XPOS FEATS HEAD DEPREL DEPS MISC`, `lcpcli` will treat them as CoNLL-U PLUS files and process the columns according to the names you set in that line.

### CoNLL-U conversion and upload

1. Create a directory in which you have all your properly-fromatted CoNLL-U files.

2. Visit an LCP instance (e.g. _catchphrase_) and create a new collection if you don't already have one where your corpus should go.

3. Retrieve the API key and secret for your project by clicking on the button that says: "Create API Key".

4. Once you have your API key and secret, you can start converting and uploading your corpus by running the following command:

```
lcpcli -i $CONLLU_FOLDER -o $OUTPUT_FOLDER -k $API_KEY -s $API_SECRET -p $PROJECT_NAME --live
```

- `$CONLLU_FOLDER` should point to the folder that contains your CONLLU files
- `$OUTPUT_FOLDER` should point to *another* folder that will be used to store the converted files to be uploaded
- `$API_KEY` is the key you copied from your project on LCP (still visible when you visit the page)
- `$API_SECRET` is the secret you copied from your project on LCP (only visible upon API Key creation)
- `$PROJECT_NAME` is the name of the project exactly as displayed on LCP -- it is case-sensitive, and space characters should be escaped

### Other input formats, rich data

Previous versions of `lcpcli` defined procedures to include rich annotations in CoNLL-U files, including time-anchored media files, in combination with annex non-CoNLL-U files. These methods are no longer supported -- use an older version of `lcpcli` if you require those features.

`lcpcli` now ships with a Python module called `lcpcli.builder` that you can use to convert any input format. The default CoNLL-U converter included in `lcpcli` uses `lcpcli.builder` under the hood.

You can find a short tutorial on how to use the module [in BUILDER.md](BUILDER.md). Further information can be found in [the LCP documentation](https://lcp.linguistik.uzh.ch/manual/builder.html).