"""
Here we create an abstract base class from which all parsers should be derived.

Parsers require a .parse() and a .write() method at the least.

Note that .write() doesn't write to file, but returns a string that can be written to file!

TODO: create a class for the entries in self._tables
TODO: it needs to be easy to make lookup files like *_form for that class too
TODO: update meta.json when new attributes are discovered
"""

import abc
import json
import os
import re

from ..utils import (
    get_ci,
    Table,
    EntityType,
    Document,
    Categorical,
    Dependency,
    Meta,
    Text,
    Sentence,
    NestedSet,
)


class Parser(abc.ABC):
    def __init__(self, *args, **kwargs):
        super().__init__()
        self.char_range_cur = 1
        self.frame_range_cur = 0
        self._tables = {}
        self.doc_frames = {}
        self.config = kwargs.get("config", {})

    @abc.abstractmethod
    def parse(self, content):
        """
        Turn a string of content into our abstract JSON format
        Format: {doc_id:{'meta':{},'sentences':{sent_id:{'meta':{},'text':{'id','form',...}}, ...}}}
        """
        pass

    @abc.abstractmethod
    def parse_generator(self, generator, config={}):
        """
        Takes an object with a reader method and yields (sentence,doc)
        """
        pass

    @abc.abstractmethod
    def write(self, content, filename=None, combine=True, meta={}):
        """
        Create a writeable string from JSON data
        Content should use our abstract JSON format
        """
        pass

    @abc.abstractmethod
    def write_generator(self, generator):
        """
        Takes a generator of (sentence, doc)'s and yields a sentence string
        """
        pass

    @abc.abstractmethod
    def combine(self, content):
        """
        Combine a dictionary of {original_filepath: json_representation}
        """
        pass

    def compute_doc(self, content, first_sentence, last_sentence):
        """
        Return (doc_id,char_range,meta) for a given pair of first and last sentences
        """
        meta_obj = {}
        start_idx = re.search(self.start_idx, first_sentence)[0]
        end_idx = re.search(self.end_idx, last_sentence)[0]
        char_range = f"{start_idx},{end_idx}"

        # meta_lines = [line for line in content.split("\n\n") if line.startswith("# text")]
        meta_lines = [
            line for line in content.split("\n") if line.startswith("# newdoc ")
        ]
        for line in meta_lines:
            if " = " not in line:
                continue
            k, v = line.split(" = ")
            meta_obj[k[9:].strip()] = v.strip()

        # if "text_id" in meta_obj:
        if "id" in meta_obj:
            doc_id = meta_obj.pop("id")
        else:
            self.text_id += 1
            doc_id = self.text_id

        return doc_id, char_range, json.dumps(meta_obj)

    def upload_new_doc(self, doc, table, docName="document"):
        """
        Take a document instance, a character_range cursor and a file handle, and write a line to the file
        """
        meta = doc.attributes.get("meta")
        col_names = [f"{docName}_id", "char_range"]
        cols = [
            str(table.cursor),
            f"[{str(doc.char_range_start)},{str(self.char_range_cur-1)})",
        ]
        if doc.frame_range[1] != 0:
            col_names.append("frame_range")
            cols.append(f"[{str(doc.frame_range[0])},{str(doc.frame_range[1])})")
            doc_frame_id = str(meta._value.get("name", doc.id) if meta else doc.id)
            self.doc_frames[doc_frame_id] = [*doc.frame_range]
        if meta:
            if "name" in meta._value:
                # dll_gen would require a lookup table to have a column of type text
                # cols.append( str(meta._value.pop('name')) )
                # col_names.append("name")
                pass
            if meta._value:
                col_names.append("meta")
                cols.append(str(meta.value))
        mediaSlots = self.config.get("meta", {}).get("mediaSlots", {})
        if mediaSlots:
            col_names.append("media")
            media = doc.attributes.get("media", Meta("dymmy", {})).value
            for name, attribs in mediaSlots.items():
                assert (
                    attribs.get("isOptional") is not False or name in media
                ), KeyError(
                    f"Filename missing for required media '{name}' from document {doc.id}"
                )
            cols.append(media)
        if table.cursor == 1:
            table.write(col_names)
        table.write(cols)
        table.cursor += 1

    def write_token_deps(self, table, working_on=""):
        """
        Take a file handle with a 'deps' key that contains NestedSet's to be linked and write to file, then clear memory
        """
        # head_id is None: this is a new head, process the previous one
        empty_segments = []
        nested_set_of_previous_head = None
        for segment_id, tokens in table.deps.items():
            if segment_id == working_on:
                continue
            for token_id, attrs in tokens.items():
                # Link the nested sets from the dependencies in memory
                hid = attrs["head_id"]
                if hid == "":
                    nested_set_of_previous_head = attrs["nested_set"]
                if hid not in tokens:
                    continue
                tokens[hid]["nested_set"].add(tokens[token_id]["nested_set"])
            anchor_right = table.anchor_right
            nested_set_of_previous_head.compute_anchors()
            for id in nested_set_of_previous_head.all_ids:
                nested_set = tokens[id]["nested_set"]
                parent_id = (
                    ""
                    if nested_set.parent is None
                    else str(nested_set.parent.cursor_id)
                )
                table.write(
                    [
                        str(parent_id),  # head
                        str(str(nested_set.cursor_id)),  # dependent (self)
                        nested_set.label,  # label
                        str(anchor_right + nested_set.left),  # left_anchor
                        str(anchor_right + nested_set.right),  # right_anchor
                    ]
                )
            table.anchor_right = anchor_right + nested_set_of_previous_head.right
            # Now clear the processed tokens
            for id in nested_set_of_previous_head.all_ids:
                tokens.pop(id)
            if not tokens:
                empty_segments.append(segment_id)
        # Clear the segments with no tokens left
        for s_id in empty_segments:
            table.deps.pop(s_id)

    def aligned_entity(self, entity, path, attribute, aligned_entities={}):
        aname_low = attribute.name.lower()
        assert isinstance(attribute, Text), TypeError(
            f"Foreign key '{attribute.name}' should be a simple text"
        )
        layer_name = next(
            (x for x in self.config.get("layer", {}).keys() if x.lower() == aname_low),
            None,
        )
        layer_attributes = (
            self.config["layer"].get(layer_name, {}).get("attributes", {})
            if layer_name
            else {}
        )
        if aname_low not in self._tables:
            self._tables[aname_low] = Table(
                aname_low, path, config=get_ci(self.config["layer"], layer_name)
            )
            table = self._tables[aname_low]
            with open(aligned_entities[aname_low]["fn"], "r") as aligned_file:
                entity_col_names = [f"{aname_low}_id"]
                entity_col_names += aligned_file.readline().rstrip().split("\t")[1:]
                table.colNames = [*entity_col_names]
                # TODO: form will need a lookup table here too
                # if 'form' not in entity_col_names:
                #     entity_col_names.append('form')
                entity_col_names.append("char_range")
                table.write(entity_col_names)
        table = self._tables[aname_low]
        fk = attribute.value.strip()
        ce = table.currentEntity
        if fk == ce.get("id", ""):
            # TODO: form will need a lookup table here too
            # if 'form' in ce and 'form' not in self._tables[aname_low]['col_names']:
            #     ce['form'] += token.attributes['form'].value + (' ' if token.spaceAfter else '')
            table.previousEntity = entity
            pass
        else:
            if ce:
                entity_cols = [table.cursor]
                table.cursor += 1
                entity_cols += ce["cols"]
                # Process labels
                lbls = table.labels
                for n, col_name in enumerate(table.colNames):
                    ctype = layer_attributes.get(col_name, {}).get("type", "")
                    if ctype != "labels":
                        continue
                    bits = int("0", 2)
                    for label in entity_cols[n].split(","):
                        l = label.strip()
                        idx = lbls.get(l, len(lbls))
                        lbls[l] = idx
                        bs = "1" + "".join(["0" for _ in range(idx - 1)])
                        bits = bits | int(bs, 2)
                    entity_cols[n] = bin(bits)[2:]
                # TODO: form will need a lookup table here too
                # if 'form' in ce and 'form' not in self._tables[aname_low]['col_names']:
                #     if ce['form'].endswith(' '):
                #         ce['form'] = ce['form'][:-1]
                #     entity_cols.append( ce['form'] )
                range_up = self.char_range_cur - 1  # Stop just before this entity
                entity_cols.append(f"[{str(ce['range_low'])},{str(range_up)})")
                table.write(entity_cols)
            if not fk or fk.strip() == "_":
                ce = {}
            else:
                ce = {"id": fk}
                with open(aligned_entities[aname_low]["fn"], "r") as aligned_file:
                    while True:
                        line = aligned_file.readline()
                        if not line:
                            break
                        line = line.rstrip().split("\t")
                        if line[0].strip() == fk:
                            ce["cols"] = line[1:]
                            # TODO: form will need a lookup table here too
                            # if 'form' not in self._tables[aname_low]['col_names']:
                            #     ce['form'] = token.attributes['form'].value + (' ' if token.spaceAfter else '')
                            ce["range_low"] = str(self.char_range_cur)
                            break
            table.currentEntity = ce

    def close_aligned_entity(self, name, path, aligned_entities={}):
        dummy_entity = EntityType()
        dummy_attribute = Text(name, "dummy")
        self.aligned_entity(dummy_entity, path, dummy_attribute, aligned_entities)
        if name in self._tables:
            self._tables[name].currentEntity = {}

    def close_upload_files(self, path="./"):
        if self._tables is None:
            return
        # Write label files
        for n, tab in self._tables.items():
            tab.file.close()
            if not tab.labels:
                continue
            nlabels = len(tab.labels)
            with open(os.path.join(path, f"{n}_labels.csv"), "w") as f:
                f.write("\t".join(["bit", "label"]) + "\n")
                for l, i in tab.labels.items():
                    f.write("\t".join([str(i), str(l)]) + "\n")
            tab.config["nlabels"] = nlabels
            # Pad 0s to match the bit length
            label_attributes = {}
            for n, v in tab.config.get("attributes", {}).items():
                # List all the attributes of type "labels"
                if v.get("type") != "labels":
                    continue
                label_attributes[n] = -1
            if not label_attributes:
                continue
            with open(tab.path, "r") as input, open(tab.path + ".tmp", "w") as output:
                while True:
                    il = input.readline()
                    if not il:
                        break
                    il = il.rstrip()
                    cols = il.split("\t")
                    if next(x for x in label_attributes.values()) == -1:
                        # First line = header
                        for n, c in enumerate(cols):
                            for la in label_attributes:
                                if not c.lower().startswith(la.lower()):
                                    continue
                                # Report the index of the column corresponding to the attribute
                                label_attributes[la] = n
                    else:
                        # Not first line = row
                        for n in label_attributes.values():
                            bits = cols[n]
                            if len(bits) < nlabels:
                                bits = (
                                    "".join(["0" for _ in range(nlabels - len(bits))])
                                    + bits
                                )
                            cols[n] = bits
                    output.write("\t".join(cols) + "\n")
            os.rename(tab.path + ".tmp", tab.path)

    def generate_upload_files_generator(
        self,
        reader,
        path="./",
        default_doc={},
        config={},
        aligned_entities={},
        aligned_entities_segment={},
    ):
        """
        Take a reader object and outputs verticalized LCP self._tables
        """
        docName = "document"
        segName = "segment"
        tokName = "token"
        if "firstClass" in config:
            docName = config["firstClass"].get("document", docName).lower()
            segName = config["firstClass"].get("segment", segName).lower()
            tokName = config["firstClass"].get("token", tokName).lower()

        self._tables = self._tables or {
            "document": Table(
                docName, path, config=get_ci(self.config["layer"], docName)
            ),
            "segment": Table(
                segName, path, config=get_ci(self.config["layer"], docName)
            ),
            "token": Table(tokName, path, config=get_ci(self.config["layer"], docName)),
        }
        token_table = self._tables["token"]
        char_range_start = self.char_range_cur
        has_frame_range = False
        offset_frame_range = self.frame_range_cur
        token_have_dependencies = False
        current_document = None
        for segment, doc in self.parse_generator(reader, config=config):

            char_range_segment_start = self.char_range_cur
            frame_range_segment_start = None

            if doc:
                if current_document is not doc:
                    if current_document:
                        self.upload_new_doc(
                            current_document, self._tables["document"], docName=docName
                        )
                    current_document = doc
                    current_document.char_range_start = char_range_segment_start

            if not segment:
                continue

            non_null_attributes = token_table.non_null_attributes
            if not non_null_attributes and token_table.cursor == 1:
                col_names = {f"{tokName}_id": None}
                for token in segment.tokens:
                    if token.frame_range:
                        has_frame_range = True
                    for attr_name, attr_value in token.attributes.items():
                        if not attr_value.value:
                            continue
                        non_null_attributes[attr_name] = True
                        if (
                            isinstance(attr_value, Dependency)
                            or attr_name.lower() in aligned_entities
                        ):
                            continue
                        if any(isinstance(attr_value, klass) for klass in (Text, Meta)):
                            col_names[attr_name + "_id"] = None
                        else:
                            col_names[attr_name] = None
                token_table.non_null_attributes = non_null_attributes
                col_names["char_range"] = None
                if has_frame_range:
                    col_names["frame_range"] = None
                col_names[f"{segName}_id"] = None
                token_table.write([c for c in col_names])

            print(
                "segment",
                segment.id,
                "meta",
                segment.attributes.get("meta", Meta("dummy", "dummy")).value,
            )
            for token in segment.tokens:
                cols = [str(token_table.cursor)]
                for attr_name in non_null_attributes:
                    attribute = token.attributes.get(attr_name, None)
                    aname_low = attr_name.lower()

                    if attribute is None:
                        cols.append("")
                        continue

                    if aname_low in aligned_entities and isinstance(attribute, Text):
                        self.aligned_entity(token, path, attribute, aligned_entities)
                        # if aname_low not in self._tables:
                        #     self._tables[aname_low] = {
                        #         'file': open(os.path.join(path,f"{aname_low}.csv"), "a"),
                        #         'cursor': 1,
                        #         'currentEntity': {},
                        #         'previousToken': None
                        #     }
                        #     with open(aligned_entities[aname_low]['fn'], "r") as aligned_file:
                        #         ne_col_names = [f"{aname_low}_id"]
                        #         ne_col_names += aligned_file.readline().split()[1:]
                        #         self._tables[aname_low]['col_names'] = [*ne_col_names]
                        #         # TODO: form will need a lookup table here too
                        #         # if 'form' not in ne_col_names:
                        #         #     ne_col_names.append('form')
                        #         ne_col_names.append("char_range")
                        #         self._tables[aname_low]['file'].write(
                        #             "\t".join(ne_col_names) + "\n"
                        #         )
                        # fk = attribute.value.strip()
                        # ce = self._tables[aname_low].get("currentEntity", {})
                        # if fk == ce.get("id", ""):
                        #     # TODO: form will need a lookup table here too
                        #     # if 'form' in ce and 'form' not in self._tables[aname_low]['col_names']:
                        #     #     ce['form'] += token.attributes['form'].value + (' ' if token.spaceAfter else '')
                        #     self._tables[aname_low]['previousToken'] = token
                        #     pass
                        # else:
                        #     # This below will need to be executed after the last iteration too, so make it a method
                        #     if ce:
                        #         ne_cols = [str(self._tables[aname_low]['cursor'])]
                        #         self._tables[aname_low]['cursor'] += 1
                        #         ne_cols += ce['cols']
                        #         # TODO: form will need a lookup table here too
                        #         # if 'form' in ce and 'form' not in self._tables[aname_low]['col_names']:
                        #         #     if ce['form'].endswith(' '):
                        #         #         ce['form'] = ce['form'][:-1]
                        #         #     ne_cols.append( ce['form'] )
                        #         range_up = self.char_range_cur - 1 # Stop just before this token
                        #         ne_cols.append( f"[{str(ce['range_low'])},{str(range_up)})" )
                        #         self._tables[aname_low]['file'].write(
                        #             "\t".join(ne_cols) + "\n"
                        #         )
                        #     if not fk or fk.strip() == "_":
                        #         ce = {}
                        #     else:
                        #         ce = {'id': fk}
                        #         with open(aligned_entities[aname_low]['fn'], "r") as aligned_file:
                        #             while True:
                        #                 line = aligned_file.readline().split()
                        #                 if not line:
                        #                     break
                        #                 if line[0].strip() == fk:
                        #                     ce['cols'] = line[1:]
                        #                     # TODO: form will need a lookup table here too
                        #                     # if 'form' not in self._tables[aname_low]['col_names']:
                        #                     #     ce['form'] = token.attributes['form'].value + (' ' if token.spaceAfter else '')
                        #                     ce['range_low'] = str(self.char_range_cur)
                        #                     break
                        #     self._tables[aname_low]['currentEntity'] = ce

                    elif isinstance(attribute, Categorical):
                        cols.append(str(attribute.value))

                    # if isinstance(attribute, Meta):
                    #     cols.append( json.dumps(attribute.value) )

                    # We create dicts for text attributes to keep track of their IDs
                    # One idea to optimize memory:
                    # - only using a dict (form -> id) and no verticalized file at all to start with
                    # - once the dict's length passes a certain threshold (e.g. 10k diff entries)
                    #   then start writing entries to self._tables whose name start with the text's first letter
                    # - if a text is not found in the dict, look up the file, and if not found in the file, write to it
                    elif any(isinstance(attribute, klass) for klass in (Text, Meta)):
                        name = f"{tokName}_{attribute.name}"
                        if name not in self._tables:
                            self._tables[name] = Table(name, path)
                        table = self._tables[name]
                        text = str(attribute.value)
                        id = table.texts.get(text, 0)
                        if id < 1:
                            id = table.cursor
                            table.texts[text] = id
                            if table.cursor == 1:
                                table.write([f"{attribute.name}_id", attribute.name])
                            table.cursor += 1
                            table.write([str(id), text])
                        cols.append(str(id))

                    elif isinstance(attribute, Dependency):
                        # token_have_dependencies = True
                        name = attribute.name
                        if name not in self._tables:
                            self._tables[name] = Table(name, path)
                            self._tables[name].write(
                                [
                                    "head",
                                    "dependent",
                                    "label",
                                    "left_anchor",
                                    "right_anchor",
                                ]
                            )
                        table = self._tables[name]
                        if str(segment.id) not in table.deps:
                            table.deps[str(segment.id)] = {}
                        deps = table.deps[str(segment.id)]
                        head_id = attribute.value
                        # We assume a new head necessarily means all of the previous head's dependencies have been parsed
                        if head_id == "" and deps:
                            # head_id is None: this is a new head, process the previous one
                            self.write_token_deps(
                                self._tables[name], working_on=str(segment.id)
                            )
                        deps[token.id] = {
                            "head_id": head_id,
                            "nested_set": NestedSet(
                                token.id, attribute.label, token_table.cursor
                            ),
                        }
                        self._tables[name].cursor += 1

                # If this token doesn't have an attribute for an aligned entity, close any pending one
                for aligned_entity in aligned_entities:
                    if aligned_entity in [a.lower() for a in non_null_attributes]:
                        continue
                    self.close_aligned_entity(aligned_entity, path, aligned_entities)

                left_char_range = self.char_range_cur
                self.char_range_cur += len(token.attributes["form"].value) - (
                    0 if token.spaceAfter else 1
                )
                cols.append(f"[{str(left_char_range)},{str(self.char_range_cur)})")
                self.char_range_cur += 1
                if token.frame_range:
                    has_frame_range = True  # Keep it here too for iterations where non_null_attributes is already set
                    left_frame_range, right_frame_range = token.frame_range
                    left_frame_range += offset_frame_range
                    right_frame_range += offset_frame_range
                    cols.append(f"[{str(left_frame_range)},{str(right_frame_range)})")
                    if current_document:
                        if current_document.frame_range[0] == 0:
                            current_document.frame_range[0] = (
                                offset_frame_range + token.frame_range[0]
                            )
                        current_document.frame_range[1] = (
                            offset_frame_range + token.frame_range[1]
                        )
                    if frame_range_segment_start is None:
                        frame_range_segment_start = (
                            offset_frame_range + token.frame_range[0]
                        )
                    self.frame_range_cur = right_frame_range
                cols.append(str(segment.id))
                token_table.write(cols)
                token_table.cursor += 1

            segment_table = self._tables["segment"]
            if segment_table.cursor == 1:
                col_names = [f"{segName}_id", "char_range"]
                if has_frame_range:
                    col_names.append("frame_range")
                # Add the names of all segment attributes
                for a in segment.attributes:
                    if a in aligned_entities_segment:
                        continue
                    col_names.append(a)
                segment_table.write(col_names)
            cols = [str(segment.id)]
            cols.append(f"[{char_range_segment_start},{self.char_range_cur-1})")
            if has_frame_range:
                cols.append(
                    f"[{str(frame_range_segment_start)},{str(self.frame_range_cur)})"
                )
            # Add all segment attributes
            for a in segment.attributes.values():
                aname_low = a.name.lower()
                if aname_low in aligned_entities_segment:
                    self.aligned_entity(segment, path, a, aligned_entities_segment)
                else:
                    cols.append(a.value)
            # If this segment doesn't have an attribute for one the aligned entities, close it
            for aligned_entity in aligned_entities_segment:
                if aligned_entity in [a.lower() for a in segment.attributes.keys()]:
                    continue
                self.close_aligned_entity(
                    aligned_entity, path, aligned_entities_segment
                )
            # Now write to the file and update cursor
            segment_table.write(cols)
            segment_table.cursor += 1

            # FTS VECTOR if no dependencies
            # Always run for now, since we don't use the same value for "LABEL_IN" and "LABELS_OUT"
            if not token_have_dependencies:
                name = "fts_vector"
                if name not in self._tables:
                    self._tables[name] = Table(name, path)
                fts_table = self._tables[name]
                vector = []
                for n, token in enumerate(segment.tokens, start=1):
                    attributes_to_fts = []
                    for an in non_null_attributes:
                        a = token.attributes[an]
                        if (
                            any(isinstance(a, k) for k in (Categorical, Text))
                            and an.lower() not in aligned_entities
                        ):
                            attributes_to_fts.append(a)
                        elif isinstance(
                            a, Dependency
                        ):  # same value for LABEL_IN and LABELS_OUT
                            attributes_to_fts.append(a)
                            attributes_to_fts.append(a)
                    for i, a in enumerate(attributes_to_fts, start=1):
                        vector.append(f"'{i}{str(a.value)}':{n}")
                cols[1:] = [" ".join(vector)]
                if fts_table.cursor == 1:
                    fts_table.write([f"{segName}_id", "vector"])
                fts_table.write(cols)
                fts_table.cursor += 1

        if token_have_dependencies:
            # Write any pending dependencies
            for _, tab in self._tables.items():
                if not tab.deps:
                    continue
                self.write_token_deps(tab)

        # Add any pending aligned entities
        for ename in aligned_entities:
            self.close_aligned_entity(ename, path, aligned_entities)
        for ename in aligned_entities_segment:
            self.close_aligned_entity(ename, path, aligned_entities_segment)

        if current_document is None:
            # No new document marker found when parsing: create an all-encompassing one
            current_document = Document()
            if default_doc:
                current_document.attributes["meta"] = Meta("meta", default_doc)
            current_document.char_range_start = char_range_start

        # Write the last document
        self.upload_new_doc(current_document, self._tables["document"], docName=docName)

        # for _, v in self._tables.items():
        #     v['file'].close()

    def generate_upload_files(self, content):
        """
        Return ([sentences], (doc_id,char_range,meta)) for a given document file
        """

        sentences = (sent for sent in content.split("\n\n") if sent)

        proc_sentences = []

        ncols = 0
        for sentence in sentences:
            lines = [x for x in sentence.split("\n") if x]

            sent = Sentence(lines, self)
            if sent._lines:
                sent.process()
                proc_sentences.append(sent)
                ncols = max([ncols, *[len(l) for l in sent.proc_lines]])

        for s in proc_sentences:
            for l in s.proc_lines:
                for _ in range(ncols - len(l)):
                    l.append("")

        if proc_sentences:
            doc = self.compute_doc(
                content,
                proc_sentences[0].proc_lines[0][6],
                proc_sentences[-1].proc_lines[-1][6],
            )
            # self.compute_doc()
            return proc_sentences, doc
        else:
            return None, None
