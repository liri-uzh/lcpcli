import os

from lxml import etree

from ._parser import Parser

"""
<text id="TOR_C_0001">
<speech id="TOR_C_0001-u1" who="RS_DK" name="Dejan Krstić" gender="M" role_id="TOR_RS" role_name="Researcher">
pitáo   pitao   pitati-v    Vmp-sm
ljúbu   ljubu   ljuba-n Ncfsa
on  on  on-p    Pp3msn
káže    kaže    kazati-v    Vmr3s
príčajte    pričajte    pričati-v   Vmm2p
[pause]         
kólko   kolko   koliki-p    Pq-nsn
óćete   oćete   hteti-v Vmr2p
</speech>
<speech id="TOR_C_0001-u2" who="TIM_SPK_0001" name="-" gender="F" role_id="TOR_INF_D" role_name="Informant from the region, representative of the dialect">
he  he  he-n    Ncfpn
[pause]         
paa paa pa-c    Cc
ajdéte  ajdete  hajde-i I
ovámo   ovamo   ovamo-r Rgp
ví  vi  vi-p    Pp2-pn
</speech>
</text>

"""


class VERTParser(Parser):
    def __init__(self):
        super().__init__()

    def parse(self, input_data):

        root = etree.fromstring(input_data)
        # sentences = [sent for sent in input_data.split('>\n<s') if sent]

        vert_parsed = {}

        n_text_id = 0
        current_document = None
        # vert_parsed = {"meta": {}, "sentences": {}}

        for element in root:

            if (
                element.tag == "text"
            ):  # possible to find vert files with more texts, account for that
                current_document = {"meta": {}, "sentences": {}}
                id = n_text_id
                n_text_id += 1
                text = element
                for k, v in element.attrib.items():
                    if k.lower() == "id":
                        id = v
                    else:
                        vert_parsed["meta"][k] = v
                vert_parsed[id] = current_document

                for subelement in text:

                    if subelement.tag == "s":
                        sentence = subelement

                        sent_meta = sentence.attrib
                        sent_id = next(
                            (v for k, v in sent_meta.items() if "id" in k), None
                        )
                        if sent_id is None:
                            print("todo: handle the fact that sent_id is None!")

                        current_document["sentences"][sent_id] = {
                            "meta": dict(sent_meta),
                            "text": [],
                        }

                        sent_text = sentence.text.strip()
                        token_list = sent_text.split("\n")
                        for token in token_list:
                            form = token.split("\t")[0]
                            lemma = token.split("\t")[1]
                            pos = token.split("\t")[2]

                            token_dict = {"form": form, "lemma": lemma, "xpos": pos}

                            current_document["sentences"][sent_id]["text"].append(
                                token_dict
                            )
                    else:
                        print(subelement)
                        # for now processing only 's' elements. include 'p', 'title' and others
            else:
                print(element)
                # for now processing only 'text' elements

            return vert_parsed

    def doc_meta(self, id, meta):
        """
        content is a dict {id,meta}
        """
        vert_content = ['<text id="{}"'.format(id)]
        for key, value in meta.items():
            text = value.lstrip(" ").rstrip(" ") if value else None
            if not key or not text:
                continue
            vert_content.append(' {}="{}"'.format(key,text))
        vert_content.append(">\n")
        return "".join(vert_content)


    def combine(self, content):
        """
        content is a dict of filepaths and vert data strings. combine them into one corpus and return as string
        """
        vert_content = ["<corpus>\n"]

        for doc_id, doc_content in content.items():
            vert_content.append(self.doc_meta(doc_id, doc_content.get("meta", {})))
            vert_content.append(self.write(doc_content.get("sentences", {}), combine=True))
            vert_content.append("</text>\n")

        vert_content.append("/<corpus>\n")

        return "".join(vert_content)


    def write(self, content, filename=None, combine=True, meta={}):
        """
        content is a dict of sentences: key is the id, value is {meta,text}
        """

        vert_file_list = []

        if not combine:
            vert_file_list.append("<corpus>\n")
            vert_file_list.append("<text")
            for key, value in meta.items():
                vert_file_list.append(' {}="{}"'.format(key.strip(),value.strip()))
            vert_file_list.append(">\n")

        for sent_id, sent_data in content.items():

            sent_meta, sent_text = ({}, {})
            for item in sent_data:
                if "meta" in item:
                    sent_meta = sent_data[item]
                elif "text" in item:
                    sent_text = sent_data[item]

            vert_file_list.append("<s")

            found_id = False
            for k, v in sent_meta.items():
                kv_pair = ' {}="{}"'.format(k, v)
                vert_file_list.append(kv_pair)
                if k.lower() == "id":
                    found_id = True
            if not found_id:
                vert_file_list.append(f' id="{sent_id}"')

            vert_file_list.append(">\n")

            for token in sent_text:
                token_list = [v for k, v in token.items()]
                token_str = "\t".join(token_list[1:4])
                vert_file_list.append(token_str + "\n")

            vert_file_list.append("</s>\n")

        if not combine:
            vert_file_list.append("</text>\n")
            vert_file_list.append("</corpus>\n")

        return "".join(vert_file_list)
