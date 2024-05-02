from ._parser import Parser

from lxml import etree

import io
import json
import xmltodict
import jsonpickle


# Need to update this to new JSON format (also what's with input_file in parse?)
class TEISpokenParser(Parser):
    # created based on Spoken Torlak Corpus 1.0 (http://hdl.handle.net/11356/1281)
    def __init__(self):
        super().__init__()

    def parse(self, content):
        # content here is a file, if the content were something else, like described in README, the beginning would need to be slightly changed

        # Parse xml and get root without namespaces
        tree = etree.parse(io.BytesIO(open(input_file, 'rb').read()))
        root = tree.getroot()

        # Remove namespaces
        # Iterate through all XML elements
        for elem in root.getiterator():
            # Skip comments and processing instructions,
            # because they do not have names
            if not (
                    isinstance(elem, etree._Comment)
                    or isinstance(elem, etree._ProcessingInstruction)
            ):
                # Remove a namespace URI in the element's name
                elem.tag = etree.QName(elem).localname
        # Remove unused namespace declarations
        etree.cleanup_namespaces(root)

        # Create dictionary / JSON representation of each document
        tei_spoken_parsed = {
            "meta": xmltodict.parse(etree.tostring(root.find('.//teiHeader'))),  # not used for VRT and CONLL-U
            'sentences': {}
        }

        # Get speaker info from file header
        speaker_dict = {}
        for person in root.iter('person'):
            speaker_dict[person.attrib['{http://www.w3.org/XML/1998/namespace}id']] = person.attrib

        # Get discreete timestamps from 'timeline'
        timeline = root.find('.//timeline')
        timeline_dict = {}
        for item in timeline:
            # timeline_dict
            dict_key = item.attrib['{http://www.w3.org/XML/1998/namespace}id']
            item.attrib.pop('{http://www.w3.org/XML/1998/namespace}id')
            timeline_dict[dict_key] = item.attrib

        # Get utterance elements from file
        utterances = root.findall('.//u')

        # Iterate through utterances to extract tokens
        for utterance in utterances:
            # sent_id, sent_metadata = get_sent_metadata(utterance, speaker_dict)
            # Get sentence id
            sent_id = utterance.attrib['{http://www.w3.org/XML/1998/namespace}id']

            # Get sentence metadata
            sent_metadata = {
                'sent_id': utterance.attrib['{http://www.w3.org/XML/1998/namespace}id'],
                'speaker': utterance.attrib['who'].strip('#'),
                'speaker_gender': speaker_dict[utterance.attrib['who'].strip('#')]['sex'],
                'speaker_role': speaker_dict[utterance.attrib['who'].strip('#')]['role'].strip('#')
            }
            utterance_discrete_start = utterance.attrib['start'].split('.')
            utterance_discrete_start = '.'.join([utterance_discrete_start[0], utterance_discrete_start[1].lower()])
            try:
                sent_metadata['start_time'] = timeline_dict[utterance_discrete_start]['interval']
            except KeyError:
                sent_metadata['start_time'] = 0.0
            utterance_discrete_end = utterance.attrib['end'].split('.')
            utterance_discrete_end = '.'.join([utterance_discrete_end[0], utterance_discrete_end[1].lower()])
            try:
                sent_metadata['end_time'] = timeline_dict[utterance_discrete_end]['interval']
            except KeyError:
                # I think there is an error in one of the original files with time distribution
                sent_metadata['end_time'] = 0.0

            # Add metadata and text for each sentence
            tei_spoken_parsed['sentences'][sent_id] = {
                'sent_metadata': sent_metadata,
                "text": []}

            # Extract content of each sentence
            sent_text = []
            for num, token in enumerate(utterance):
                id = str(num + 1)
                upos = '_'
                feats = '_'
                head = '_'
                deprel = '_'
                deps = '_'
                if token.tag == 'w':
                    form = token.text
                    lemma = token.attrib['lemma']
                    xpos = token.attrib['ana'].strip('mte:')
                    misc = '_'
                elif token.tag == 'pc':
                    form = token.text
                    lemma = token.text
                    xpos = token.attrib['ana'].strip('mte:')
                    misc = '_'
                elif token.tag in ['pause', 'del']:
                    form = f'[{token.tag}]'
                    lemma = f'[{token.tag}]'
                    xpos = 'X'
                    misc = '_'
                elif token.tag in ['vocal', 'incident']:
                    form = f'[{token.tag}]'
                    lemma = f'[{token.tag}]'
                    xpos = 'X'
                    misc = f'type={token.attrib["type"]}'
                elif token.tag == 'unclear':
                    if [word for word in token]:
                        for word in token:
                            if token.tag == 'w':
                                form = token.text
                                lemma = token.attrib['lemma']
                                xpos = token.attrib['ana'].strip('mte:')
                                misc = '_'
                            elif token.tag == 'pc':
                                form = token.text
                                lemma = token.text
                                xpos = token.attrib['ana'].strip('mte:')
                                misc = '_'
                            elif token.tag in ['pause', 'del']:
                                form = f'[{token.tag}]'
                                lemma = f'[{token.tag}]'
                                xpos = 'X'
                                misc = '_'
                            elif token.tag in ['vocal', 'incident']:
                                form = f'[{token.tag}]'
                                lemma = f'[{token.tag}]'
                                xpos = 'X'
                                misc = f'type={token.attrib["type"]}'
                    else:
                        form = "[del]"
                        lemma = "[del]"
                        xpos = 'X'
                        misc = 'unclear'
                else:
                    pass

                token_text = [id, form, lemma, upos, xpos, feats, head, deprel, deps, misc]
                tei_spoken_parsed['sentences'][sent_id]["text"].append(token_text)

        # json_tei_spoken_parsed = json.dumps(jsonpickle.decode(jsonpickle.encode(tei_spoken_parsed)), indent=4)

        return tei_spoken_parsed

    def write(self, content, filepath=None, combine=True):
        pass

    def combine(self, content):
        """
        content is a dict of filepaths and tei data strings. combine them into one corpus and return as string
        """
        raise NotImplementedError("todo")


class TEIParser(Parser):
    """
    This does not parse a standard TEI format
    Parses XML structures where tokens are embeded the deepest
    """
    def __init__(self):
        super().__init__()

    # Need to adapt to new JSON format
    def parse(self, content):

        firstClass = {'document': '', 'segment': '', 'token': ''}

        tree = etree.parse(io.BytesIO(open(content, 'rb').read()))
        root = tree.getroot()

        # Remove namespaces
        # Iterate through all XML elements
        for elem in root.getiterator():
            name = etree.QName(elem).localname
            if elem.get("id") and not firstClass['document']:
                firstClass['document'] = name
            # if len(elem) == 0:
            if elem.get("lemma"):
                firstClass['token'] = name
                firstClass['segment'] = etree.QName(elem.getparent()).localname
                break

        output = {}

        current_document = None
        current_sentence = None
        current_sentences = {}
        for elem in root.getiterator():
            name = etree.QName(elem).localname
            parent = elem.getparent()
            if name == firstClass['document']:
                assert current_document or not current_sentences, RuntimeError("Found first document after orphan segments.")
                if current_document and current_sentences:
                    current_document["sentences"] = current_sentences
                id = elem.get("id")
                if id is None:
                    continue
                current_document = {"meta": {}, "sentences": {}}
                output[id] = current_document
                current_sentences = {}
            elif name == firstClass['segment']:
                id = elem.get("id")
                current_sentence = {"meta": {}, "text": []}
                current_sentences.append(current_sentence)
            elif name == firstClass['token']:
                assert current_sentence, RuntimeError("Found a token before any segment could be found.")
                # <w id="5" lemma="z" pos="APPR" rf="VFIN.Full.3.Sg.Past.Ind">z</w>
                token = {"form": elem.text}
                for attr in ("id","lemma","upos","xpos","feats","head","deprel","deps","misc"):
                    token[attr] = elem.get(attr,"")
                current_sentence["text"].append(token)
            elif parent is not None and etree.QName(parent).localname == firstClass['document']:
                if not current_document:
                    continue
                # document meta attribute
                text = elem.text.replace("\n", "") if elem.text else None
                current_document["meta"][name] = text

        if current_sentences:
            if not current_document:
                current_document = {"meta": {}, "sentences": []}
                output["1"] = current_document
            current_document["sentences"] = current_sentences

        # Remove unused namespace declarations
        etree.cleanup_namespaces(root)
        return output

    def write(self, content, filepath=None, combine=True):
        pass

    def combine(self, content):
        """
        content is a dict of filepaths and tei data strings. combine them into one corpus and return as string
        """
        raise NotImplementedError("todo")
