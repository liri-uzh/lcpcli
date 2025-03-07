from os import path
from re import match


def check_ftsvector(vector: str) -> list[AssertionError]:
    errors: list[str] = []
    units = vector.split(" ")
    for unit in units:
        if not unit.startswith("'"):
            errors.append(
                f"Each value in the tsvector must start with a single quote character ({unit})"
            )
        elif not match(r"'\d+", unit):
            errors.append(
                f"Each value in the tsvector must start with a single quote character followed by an integer index ({unit})"
            )
        elif not match(r"'\d+.+':\d+$", unit):
            errors.append(
                f"Each value in the tsvector must end with a single quote followed by a colon and an integer index ({unit})"
            )
    return [AssertionError(e) for e in errors]


def check_range(range: str, name: str) -> list[AssertionError]:
    errors: list[str] = []
    m = match(r"\[(\d+),(\d+)\)", range)
    if not m:
        errors.append(f"Range '{name}' not in the right format: {range}")
    else:
        l, u = (m[1], m[2])
        try:
            li = int(l)
        except:
            errors.append(f"Invalid lower bound in range '{name}': {l}")
        try:
            ui = int(u)
        except:
            errors.append(f"Invalid upper bound in range '{name}': {u}")
        if li < 0:
            errors.append(f"Lower bound of range '{name}' cannot be negative: {l}")
        if ui < 0:
            errors.append(f"Upper bound of range '{name}' cannot be negative: {u}")
        if ui <= li:
            errors.append(
                f"Upper bound of range '{name}' ({ui}) must be strictly greater than its lower bound ({li})"
            )
    return [AssertionError(e) for e in errors]


def check_xybox(xybox: str, name: str) -> list[AssertionError]:
    errors: list[str] = []
    m = match(r"\((\d+),(\d+)\),\((\d+),(\d+)\)", xybox)
    if not m:
        errors.append(f"Range '{name}' not in the right format: {xybox}")
    else:
        x1, y1, x2, y2 = (m[1], m[2], m[3], m[4])
        try:
            x1i = int(x1)
        except:
            errors.append(f"Invalid x1 in xybox '{name}': {x1}")
        try:
            y1i = int(y1)
        except:
            errors.append(f"Invalid x1 in xybox '{name}': {y1}")
        try:
            x2i = int(x2)
        except:
            errors.append(f"Invalid x1 in xybox '{name}': {x2}")
        try:
            y2i = int(y2)
        except:
            errors.append(f"Invalid x1 in xybox '{name}': {y2}")
        if x2i <= x1i:
            errors.append(
                f"x2 in xybox '{name}' ({x2i}) must be strictly greater than x1 ({x1i})"
            )
        if y2i <= y1i:
            errors.append(
                f"y2 in xybox '{name}' ({y2i}) must be strictly greater than y1 ({y1i})"
            )
    return [AssertionError(e) for e in errors]


def check_attribute_name(name: str) -> list[AssertionError]:
    errors: list[str] = []
    if name != name.lower():
        errors.append(f"Attribute name '{name}' cannot contain uppercase characters")
    if " " in name:
        errors.append(f"Attribute name '{name}' cannot contain whitespace characters")
    if "'" in name:
        errors.append(f"Attribute name '{name}' cannot contain single-quote characters")
    return [AssertionError(e) for e in errors]


def check_layer(
    layer_name: str, layer_properties: dict, directory: str
) -> list[AssertionError]:
    errors: list[str] = []
    allowed_extensions = ("tsv", "csv")
    layer_name_low = layer_name.lower()
    if not any(
        path.exists(path.join(directory, f"{layer_name_low}.{x}"))
        for x in allowed_extensions
    ):
        errors.append(
            f"Could not find a main file {layer_name_low}.csv corresponding to the layer {layer_name}"
        )
    attributes = layer_properties.get("attributes", {})
    if not isinstance(attributes, dict):
        errors.append(
            f"The attributes of a layer must be reported as key-value dictionaries ({layer_name})"
        )
    else:
        for attribute_name, attribute_value in attributes.items():
            errors += [str(e) for e in check_attribute_name(attribute_name)]
            if not isinstance(attribute_value, dict):
                errors.append(
                    f"Each attribute must be defined with a key-value dictionary ({layer_name}->{attribute_name})"
                )
                continue
            aname_low = attribute_name.lower()
            if "ref" in attribute_value:
                if not any(
                    path.exists(
                        path.join(directory, f"global_attribute_{aname_low}.{x}")
                    )
                    for x in allowed_extensions
                ):
                    errors.append(
                        f"Attribute {layer_name}->{attribute_name} is a global attribute but there is no file named global_attribute_{aname_low}.csv"
                    )
                continue
            if not "type" in attribute_value:
                errors.append(
                    f"Each attribute must define a type ({layer_name}->{attribute_name})"
                )
                continue
            typ = attribute_value["type"]
            afn = f"{layer_name_low}_{aname_low}"
            if typ in ("dict", "text") and not any(
                path.exists(path.join(directory, f"{afn}.{x}"))
                for x in allowed_extensions
            ):
                errors.append(
                    f"Attribute {layer_name}->{attribute_name} is of type {typ} but there is no file named {afn}.csv"
                )
    return [AssertionError(e) for e in errors]


def check_config(config: dict) -> list[AssertionError]:
    errors: list[str] = []
    mandatory_keys = ("layer", "firstClass", "meta")
    for key in mandatory_keys:
        if key not in config:
            errors.append(f"The configuration file must contain the main key '{key}'")
    layer = config.get("layer", {})
    if first_class := config.get("firstClass", {}):
        if not isinstance(first_class, dict):
            errors.append(
                f"The value of 'firstClass' must be a key-value object with the keys 'document', 'segment' and 'token'"
            )
        mandatory_keys = ("document", "segment", "token")
        for key in mandatory_keys:
            if key not in first_class:
                errors.append(f"firstClass must contain the key '{key}'")
            elif layer and config[key] not in layer:
                errors.append(
                    f"layer must contain the key '{first_class[key]}' defined for {key}"
                )
    return [AssertionError(e) for e in errors]


def run_checks(config: dict, directory: str) -> bool:
    all_passed = True
    check_config(config)
    layer = config.get("layer", {})
    for layer_name, layer_properties in layer.items():
        check_layer(layer_name, layer_properties, directory)

    return all_passed
